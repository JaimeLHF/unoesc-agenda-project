"""
Módulo de sincronização com o Google Calendar — UNOESC Agenda.

Utiliza as bibliotecas google-api-python-client e google-auth para:
  - Autenticar o usuário via OAuth2
  - Criar eventos no Google Calendar a partir dos eventos acadêmicos extraídos
"""

import asyncio
from datetime import datetime, date, timedelta
from typing import Any

from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

# Escopo necessário para criar e gerenciar eventos no Google Calendar
SCOPES = ["https://www.googleapis.com/auth/calendar.events"]

# ID do calendário onde os eventos serão criados ('primary' = calendário principal do usuário)
CALENDAR_ID = "primary"


class CalendarSyncService:
    """Serviço responsável por criar eventos no Google Calendar do usuário."""

    def __init__(self, oauth_token: str) -> None:
        """
        Inicializa o serviço com o token OAuth2 do usuário.

        Parâmetros:
            oauth_token: Token de acesso OAuth2 obtido via fluxo de autorização do Google.
        """
        # Cria credenciais a partir do token de acesso fornecido pelo frontend
        credentials = Credentials(token=oauth_token, scopes=SCOPES)
        # Constrói o cliente da API do Google Calendar (versão 3)
        self._service = build("calendar", "v3", credentials=credentials)

    async def sync_events(self, events: list[Any]) -> tuple[list[str], list[str]]:
        """
        Sincroniza uma lista de eventos acadêmicos com o Google Calendar.

        Parâmetros:
            events: Lista de eventos acadêmicos (objetos Pydantic ou dicionários).

        Retorna:
            Tupla com (lista de IDs dos eventos criados, lista de links dos eventos).
        """
        synced_ids: list[str] = []
        calendar_links: list[str] = []

        for event in events:
            event_id, link = await self._create_event(event)
            if event_id:
                synced_ids.append(event_id)
                calendar_links.append(link)

        return synced_ids, calendar_links

    # ------------------------------------------------------------------
    # Métodos privados
    # ------------------------------------------------------------------

    async def _create_event(self, event: Any) -> tuple[str, str]:
        """
        Cria um único evento no Google Calendar.

        Para webconferências e provas com horário definido, cria evento com duração de 1 hora.
        Para prazos de entrega sem horário, cria evento de dia inteiro às 23:59.

        Retorna:
            Tupla (id do evento criado, link para o evento no Google Calendar).
        """
        # Suporta objetos Pydantic e dicionários simples
        title = event.title if hasattr(event, "title") else event["title"]
        date_str = event.date if hasattr(event, "date") else event["date"]
        time_str = event.time if hasattr(event, "time") else event.get("time") if isinstance(event, dict) else None
        description = event.description if hasattr(event, "description") else event.get("description", "")
        subject = event.subject if hasattr(event, "subject") else event.get("subject", "")
        event_type = event.type if hasattr(event, "type") else event.get("type", "other")

        # Monta o corpo do evento conforme o tipo e disponibilidade de horário
        if time_str:
            google_event = self._build_timed_event(title, date_str, time_str, description, subject)
        elif event_type == "deadline":
            google_event = self._build_deadline_event(title, date_str, description, subject)
        else:
            google_event = self._build_allday_event(title, date_str, description, subject)

        try:
            # Executa a chamada à API de forma síncrona dentro de um executor
            # (a biblioteca google-api-python-client é síncrona)
            loop = asyncio.get_event_loop()
            created = await loop.run_in_executor(
                None,
                lambda: self._service.events()
                .insert(calendarId=CALENDAR_ID, body=google_event)
                .execute(),
            )
            return created.get("id", ""), created.get("htmlLink", "")
        except HttpError as exc:
            # Registra o erro mas não interrompe a sincronização dos demais eventos
            print(f"Erro ao criar evento '{title}': {exc}")
            return "", ""

    @staticmethod
    def _build_timed_event(
        title: str, date_str: str, time_str: str, description: str, subject: str
    ) -> dict:
        """Monta um evento com data e horário definidos (duração padrão de 1 hora)."""
        start_dt = datetime.fromisoformat(f"{date_str}T{time_str}:00")
        end_dt = start_dt + timedelta(hours=1)
        return {
            "summary": title,
            "description": f"Disciplina: {subject}\n\n{description}",
            "start": {"dateTime": start_dt.isoformat(), "timeZone": "America/Sao_Paulo"},
            "end": {"dateTime": end_dt.isoformat(), "timeZone": "America/Sao_Paulo"},
        }

    @staticmethod
    def _build_deadline_event(
        title: str, date_str: str, description: str, subject: str
    ) -> dict:
        """
        Monta um evento de prazo de entrega.
        Cria como evento de hora definida às 23:59 para destacar no calendário.
        """
        start_dt = datetime.fromisoformat(f"{date_str}T23:59:00")
        end_dt = start_dt + timedelta(minutes=1)
        return {
            "summary": f"[Entrega] {title}",
            "description": f"Disciplina: {subject}\n\nPrazo de entrega.\n\n{description}",
            "start": {"dateTime": start_dt.isoformat(), "timeZone": "America/Sao_Paulo"},
            "end": {"dateTime": end_dt.isoformat(), "timeZone": "America/Sao_Paulo"},
        }

    @staticmethod
    def _build_allday_event(
        title: str, date_str: str, description: str, subject: str
    ) -> dict:
        """Monta um evento de dia inteiro (sem horário específico)."""
        return {
            "summary": title,
            "description": f"Disciplina: {subject}\n\n{description}",
            "start": {"date": date_str},
            "end": {"date": date_str},
        }
