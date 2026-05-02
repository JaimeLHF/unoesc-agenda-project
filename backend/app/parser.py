"""
Módulo de interpretação de texto — UNOESC Agenda.

Usa o SDK Python do Google Gemini para analisar o conteúdo extraído
de cada disciplina e identificar eventos acadêmicos estruturados
(webconferências, entregas, provas, etc.).
"""

import json
import os
import re
import uuid
from typing import Any

from dotenv import load_dotenv
from google import genai
from google.genai import types as genai_types

# Carrega variáveis de ambiente do arquivo .env (se existir)
load_dotenv()

# Configuração da chave de API do Gemini
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")

# Modelo Gemini a ser utilizado
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")

# Limite de caracteres do conteúdo enviado ao Gemini por disciplina.
# Gemini 2.5 Flash aceita ~1M tokens (~4M chars). 250k cobre disciplinas
# longas com folga e mantém o custo controlado.
MAX_CONTENT_CHARS = 250_000


class ParserService:
    """Serviço que usa o Gemini para extrair eventos acadêmicos do texto."""

    def __init__(self) -> None:
        if not GEMINI_API_KEY:
            raise EnvironmentError(
                "GEMINI_API_KEY não configurada. "
                "Edite backend/.env e adicione sua chave da Gemini API. "
                "Como obter: https://aistudio.google.com/ → Get API key. "
                "Veja README.md, seção 'Configurando o Gemini'."
            )
        self._client = genai.Client(api_key=GEMINI_API_KEY)

    async def extract_events(self, subjects: list[Any]) -> list[dict]:
        """
        Itera sobre as disciplinas e usa o Gemini para extrair eventos de cada uma.

        Parâmetros:
            subjects: Lista de objetos/dicionários com 'id', 'name' e 'content'.

        Retorna:
            Lista consolidada de eventos acadêmicos estruturados.
        """
        all_events: list[dict] = []

        for subject in subjects:
            # Suporta tanto objetos Pydantic quanto dicionários simples
            name = subject.name if hasattr(subject, "name") else subject["name"]
            content = subject.content if hasattr(subject, "content") else subject.get("content", "")

            if not content or not content.strip():
                # Sem conteúdo para analisar; pula a disciplina
                continue

            # A URL do curso fica no header injetado pelo scraper ("URL: ...")
            course_url_match = re.search(r"^URL:\s*(\S+)", content, re.MULTILINE)
            course_url = course_url_match.group(1) if course_url_match else None

            events = await self._extract_from_content(name, content)
            for e in events:
                if course_url:
                    e["url"] = course_url
            all_events.extend(events)

        return all_events

    # ------------------------------------------------------------------
    # Métodos privados
    # ------------------------------------------------------------------

    async def _extract_from_content(self, subject_name: str, content: str) -> list[dict]:
        """
        Envia o conteúdo de uma disciplina ao Gemini e parseia a resposta JSON.

        O prompt é escrito em português para melhores resultados com conteúdo
        acadêmico brasileiro.
        """
        prompt = self._build_prompt(subject_name, content)

        try:
            response = self._client.models.generate_content(
                model=GEMINI_MODEL,
                contents=prompt,
                config=genai_types.GenerateContentConfig(
                    response_mime_type="application/json",
                    response_schema=self._response_schema(),
                ),
            )
            raw_text = (response.text or "").strip()
        except Exception as exc:
            msg = str(exc)
            if "SERVICE_DISABLED" in msg or "has not been used in project" in msg:
                print(
                    f"[Parser] Gemini API ainda não foi habilitada no seu projeto Google. "
                    f"Abra o link que aparece na mensagem de erro e clique em 'Ativar'. "
                    f"Detalhes: {msg[:200]}"
                )
            else:
                print(f"[Parser] Erro chamando Gemini para '{subject_name}': {exc}")
            return []

        try:
            events_data: list[dict] = json.loads(raw_text) if raw_text else []
        except json.JSONDecodeError:
            print(f"[Parser] Resposta do Gemini não é JSON válido para '{subject_name}': {raw_text[:200]}")
            return []

        # Enriquece cada evento com ID único e nome da disciplina
        structured_events = []
        for event in events_data:
            structured_events.append({
                "id": str(uuid.uuid4()),
                "title": event.get("title", "Evento sem título"),
                "date": event.get("date", ""),
                "time": event.get("time"),
                "description": event.get("description", ""),
                "subject": subject_name,
                "type": event.get("type", "other"),
                "synced": False,
            })

        return structured_events

    @staticmethod
    def _response_schema() -> dict:
        """Schema JSON que o Gemini deve retornar (array de eventos)."""
        return {
            "type": "ARRAY",
            "items": {
                "type": "OBJECT",
                "properties": {
                    "title": {"type": "STRING"},
                    "date": {"type": "STRING"},
                    "time": {"type": "STRING", "nullable": True},
                    "description": {"type": "STRING"},
                    "type": {
                        "type": "STRING",
                        "enum": ["webconference", "deadline", "exam", "other"],
                    },
                },
                "required": ["title", "date", "description", "type"],
            },
        }

    @staticmethod
    def _build_prompt(subject_name: str, content: str) -> str:
        """
        Monta o prompt em português para o Gemini analisar o conteúdo da disciplina.

        O prompt instrui o modelo a retornar somente um array JSON válido,
        sem texto adicional, para facilitar o parsing automático.
        """
        return f"""Você extrai eventos acadêmicos de páginas do Moodle da UNOESC.

Disciplina: "{subject_name}"

Analise o texto abaixo (extraído da página do curso no Moodle) e identifique
TODOS os eventos com data definida. Tipos típicos:
- Tarefas/Atividades a entregar (geralmente com texto "Aberto até", "Entrega até",
  "Prazo final", "Encerramento") → type="deadline"
- Questionários/Provas (texto "Quiz", "Avaliação", "Prova") → type="exam"
- Webconferências (texto "Webconferência", "Encontro síncrono", "Aula ao vivo",
  "Live") → type="webconference"
- Demais eventos com data → type="other"

REGRAS IMPORTANTES:
- Inclua apenas eventos com data minimamente identificável.
- Se a data não tiver ano explícito, assuma o ano atual.
- Se houver intervalo "de DD/MM até DD/MM", use a data FINAL (prazo).
- Não inclua materiais de leitura, vídeos gravados ou recursos sem prazo.
- Não duplique eventos idênticos.

Retorne APENAS um array JSON (sem markdown, sem texto fora do JSON).
Se não houver eventos, retorne [].

Cada evento deve ter EXATAMENTE estes campos:
- "title": string — nome curto do evento
- "date": string — data ISO 8601 (AAAA-MM-DD)
- "time": string ou null — horário "HH:MM" (24h), se houver
- "description": string — descrição breve (até 200 chars)
- "subject": string — use "{subject_name}"
- "type": "webconference" | "deadline" | "exam" | "other"

Texto do curso:
\"\"\"
{content[:MAX_CONTENT_CHARS]}
\"\"\"

Responda somente com o array JSON."""
