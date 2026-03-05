"""
Módulo de interpretação de texto — UNOESC Agenda.

Usa o SDK Python do Google Gemini para analisar o conteúdo extraído
de cada disciplina e identificar eventos acadêmicos estruturados
(webconferências, entregas, provas, etc.).
"""

import json
import os
import uuid
from typing import Any

import google.generativeai as genai
from dotenv import load_dotenv

# Carrega variáveis de ambiente do arquivo .env (se existir)
load_dotenv()

# Configuração da chave de API do Gemini
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")

# Modelo Gemini a ser utilizado
GEMINI_MODEL = "gemini-1.5-flash"


class ParserService:
    """Serviço que usa o Gemini para extrair eventos acadêmicos do texto."""

    def __init__(self) -> None:
        if not GEMINI_API_KEY:
            raise EnvironmentError(
                "Variável de ambiente GEMINI_API_KEY não definida. "
                "Configure-a no arquivo .env antes de usar o serviço."
            )
        genai.configure(api_key=GEMINI_API_KEY)
        self._model = genai.GenerativeModel(GEMINI_MODEL)

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

            events = await self._extract_from_content(name, content)
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
            response = self._model.generate_content(prompt)
            raw_text = response.text.strip()

            # Remove possíveis marcadores de bloco de código markdown (```json ... ```)
            if raw_text.startswith("```"):
                raw_text = raw_text.split("```", 2)[1]
                if raw_text.lower().startswith("json"):
                    raw_text = raw_text[4:]
                raw_text = raw_text.rsplit("```", 1)[0].strip()

            events_data: list[dict] = json.loads(raw_text)

        except json.JSONDecodeError:
            # Gemini retornou texto não-JSON; considera sem eventos para esta disciplina
            return []
        except Exception:
            # Erro de comunicação com a API; considera sem eventos
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
    def _build_prompt(subject_name: str, content: str) -> str:
        """
        Monta o prompt em português para o Gemini analisar o conteúdo da disciplina.

        O prompt instrui o modelo a retornar somente um array JSON válido,
        sem texto adicional, para facilitar o parsing automático.
        """
        return f"""Você é um assistente especializado em extrair eventos acadêmicos de textos do portal universitário da UNOESC.

Analise o texto abaixo, proveniente da disciplina "{subject_name}", e identifique todos os eventos acadêmicos presentes, como:
- Webconferências (videoaulas ao vivo)
- Prazos de entrega de atividades e trabalhos
- Provas e avaliações
- Qualquer outra atividade com data definida

Retorne APENAS um array JSON válido (sem texto adicional, sem markdown) com os eventos encontrados.
Se não houver nenhum evento, retorne um array vazio: []

Cada evento deve ter exatamente os seguintes campos:
- "title": string — título ou nome do evento
- "date": string — data no formato ISO 8601 (AAAA-MM-DD); use o ano atual se não estiver explícito
- "time": string ou null — horário no formato HH:MM (24h), se disponível
- "description": string — breve descrição do evento
- "subject": string — nome da disciplina (use "{subject_name}")
- "type": string — um dos valores: "webconference", "deadline", "exam", "other"

Texto da disciplina:
\"\"\"
{content[:4000]}
\"\"\"

Responda somente com o array JSON."""
