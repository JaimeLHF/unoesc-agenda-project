"""
Módulo de sincronização com o Google Calendar — UNOESC Agenda.

Utiliza as bibliotecas google-api-python-client e google-auth para:
  - Autenticar o usuário via OAuth2
  - Criar eventos no Google Calendar a partir dos eventos acadêmicos extraídos
"""

import asyncio
import base64
import hashlib
from datetime import datetime, date, timedelta
from typing import Any

from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from app.database import stable_event_key

# Escopo necessário para criar e gerenciar eventos no Google Calendar
SCOPES = ["https://www.googleapis.com/auth/calendar.events"]

# ID do calendário onde os eventos serão criados ('primary' = calendário principal do usuário)
CALENDAR_ID = "primary"


def google_event_id(key: str) -> str:
    """
    ID determinístico do evento no Google Calendar, derivado da `stable_key`.

    A API exige de 5 a 1024 caracteres do alfabeto base32hex (`0-9`, `a-v`),
    e o mesmo ID nunca pode existir duas vezes no calendário. Derivar o ID do
    evento em vez de deixar o Google gerar um aleatório torna a sincronização
    idempotente: re-sincronizar atualiza o evento existente em vez de criar
    uma cópia — inclusive depois de um `make clean`, quando o banco local
    perdeu o vínculo mas o evento continua lá no calendário do usuário.
    """
    digest = hashlib.sha256(key.encode("utf-8")).digest()[:20]
    return base64.b32hexencode(digest).decode("ascii").lower()


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

    async def sync_events(self, events: list[Any]) -> list[dict]:
        """
        Sincroniza uma lista de eventos acadêmicos com o Google Calendar.

        Parâmetros:
            events: Lista de eventos acadêmicos (objetos Pydantic ou dicionários).

        Retorna:
            Lista de `{stable_key, google_event_id, link}` — só dos eventos que
            foram sincronizados com sucesso. A `stable_key` volta junto para o
            endpoint conseguir gravar o vínculo no banco.
        """
        results: list[dict] = []

        for event in events:
            stable_key, event_id, link = await self._create_event(event)
            if event_id:
                results.append({
                    "stable_key": stable_key,
                    "google_event_id": event_id,
                    "link": link,
                })

        return results

    # ------------------------------------------------------------------
    # Métodos privados
    # ------------------------------------------------------------------

    async def _create_event(self, event: Any) -> tuple[str, str, str]:
        """
        Cria (ou atualiza) um único evento no Google Calendar.

        Para webconferências e provas com horário definido, cria evento com duração de 1 hora.
        Para prazos de entrega sem horário, cria evento de dia inteiro às 23:59.

        Retorna:
            Tupla (stable_key, id do evento no Google, link para o evento).
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

        # ID determinístico: mesma atividade → mesmo evento, sem duplicar
        key = stable_event_key(subject, date_str, title)
        google_event["id"] = google_event_id(key)

        try:
            # A biblioteca google-api-python-client é síncrona — roda numa thread
            created = await asyncio.to_thread(self._upsert, google_event)
            return key, created.get("id", ""), created.get("htmlLink", "")
        except HttpError as exc:
            # Registra o erro mas não interrompe a sincronização dos demais eventos
            print(f"Erro ao criar evento '{title}': {exc}")
            return key, "", ""

    def _upsert(self, google_event: dict) -> dict:
        """
        Insere o evento; se o ID já existe no calendário, atualiza no lugar.

        O Google responde 409 tanto para um evento que ainda está lá quanto para
        um que o usuário apagou (fica como `cancelled`); o `update` cobre os dois
        casos. Função síncrona — chamada via `asyncio.to_thread`.
        """
        events = self._service.events()
        try:
            return events.insert(calendarId=CALENDAR_ID, body=google_event).execute()
        except HttpError as exc:
            if exc.resp.status != 409:
                raise
            return events.update(
                calendarId=CALENDAR_ID, eventId=google_event["id"], body=google_event
            ).execute()

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
        """
        Monta um evento de dia inteiro (sem horário específico).

        No Google Calendar o `end.date` é **exclusivo**: para um evento de um
        dia só, `end` precisa ser o dia seguinte. Com `end == start` a duração
        é zero e a API rejeita com 400.
        """
        start = date.fromisoformat(date_str)
        return {
            "summary": title,
            "description": f"Disciplina: {subject}\n\n{description}",
            "start": {"date": start.isoformat()},
            "end": {"date": (start + timedelta(days=1)).isoformat()},
        }
