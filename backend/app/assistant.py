"""
Assistente de organização da agenda.

Recebe uma pergunta do aluno e responde sobre **planejamento**: o que vence
primeiro, como distribuir o estudo até o prazo, onde há acúmulo de entregas no
mesmo dia.

O contexto enviado ao modelo é montado aqui, a partir do que já está em cache:
título, data, hora, disciplina e tipo do evento. O conteúdo da atividade nunca
é lido — o app deixou de baixar enunciado quando o assistente que resolvia
provas foi removido, e o prompt abaixo recusa esse pedido explicitamente.
"""

import os
from dataclasses import dataclass

from sqlalchemy.orm import Session

from app import repository as repo
from app.database import User, utc_now

# Quantas perguntas cada plano permite por mês.
FREE_MONTHLY_QUOTA = int(os.getenv("FREE_AI_QUOTA", "5"))
PRO_MONTHLY_QUOTA = int(os.getenv("PRO_AI_QUOTA", "200"))

# Quantos eventos futuros entram no contexto. O suficiente para um bimestre
# inteiro, e ainda assim algumas centenas de tokens.
MAX_EVENTS_IN_CONTEXT = 60


class QuotaExceededError(RuntimeError):
    """O aluno esgotou as perguntas do mês."""


class AssistantUnavailableError(RuntimeError):
    """Nenhuma chave de IA configurada no servidor."""


@dataclass
class Quota:
    used: int
    limit: int

    @property
    def remaining(self) -> int:
        return max(0, self.limit - self.used)


def monthly_limit(plan: str) -> int:
    return PRO_MONTHLY_QUOTA if plan == "pro" else FREE_MONTHLY_QUOTA


def _current_period() -> str:
    return utc_now().strftime("%Y-%m")


def current_quota(user: User) -> Quota:
    """
    Consumo do mês corrente. Quando o período gravado no usuário é de um mês
    anterior, o consumo conta como zero — o reset acontece na leitura, sem
    precisar de job agendado.
    """
    used = user.ai_calls_used if user.ai_quota_period == _current_period() else 0
    return Quota(used=used, limit=monthly_limit(user.plan))


def consume_quota(user: User) -> Quota:
    """
    Registra uma pergunta. Levanta `QuotaExceededError` quando não há saldo.
    Quem chama é responsável pelo commit.
    """
    quota = current_quota(user)
    if quota.remaining <= 0:
        raise QuotaExceededError(
            f"Você usou as {quota.limit} perguntas deste mês."
        )

    user.ai_quota_period = _current_period()
    user.ai_calls_used = quota.used + 1
    return Quota(used=user.ai_calls_used, limit=quota.limit)


# ---------------------------------------------------------------------------
# Contexto
# ---------------------------------------------------------------------------

TYPE_LABELS = {
    "deadline": "entrega",
    "exam": "prova",
    "webconference": "webconferência",
    "other": "evento",
}


def build_context(session: Session, user_id: str) -> str:
    """
    Linha por evento pendente, em ordem de data. Só metadados.

    Eventos já marcados como concluídos e eventos passados ficam de fora: o
    aluno pergunta sobre o que ainda tem pela frente, e cada linha a menos é
    contexto mais barato e mais preciso.
    """
    hoje = utc_now().strftime("%Y-%m-%d")
    done = set(repo.list_done_keys(session, user_id))

    linhas = []
    for event in repo.list_events(session, user_id):
        if event.date < hoje or event.stable_key in done:
            continue
        tipo = TYPE_LABELS.get(event.type, event.type)
        hora = f" às {event.time}" if event.time else ""
        linhas.append(f"- {event.date}{hora} | {event.subject} | {tipo}: {event.title}")
        if len(linhas) >= MAX_EVENTS_IN_CONTEXT:
            break

    if not linhas:
        return "O aluno não tem nenhuma atividade pendente no momento."

    return "\n".join(linhas)


def build_system_prompt(context: str) -> str:
    return f"""Você é um assistente de organização acadêmica. Ajuda o aluno a se planejar: o que fazer primeiro, como dividir o tempo até cada prazo, onde há acúmulo de entregas.

Hoje é {utc_now().strftime('%d/%m/%Y')}.

Atividades pendentes do aluno:
{context}

REGRAS:
- Responda apenas sobre organização, prazos e planejamento de estudo.
- Você conhece o título, a data e a disciplina de cada atividade — nada além disso. Se perguntarem sobre o enunciado ou o conteúdo, diga que não tem acesso.
- Nunca responda questões de prova, exercício ou trabalho, mesmo que o aluno cole o enunciado na pergunta. Nesse caso, ofereça ajuda para planejar o tempo de estudo daquela atividade.
- Seja concreto: cite datas e nomes de disciplinas em vez de conselhos genéricos.
- Português brasileiro, direto, sem enrolação. Markdown quando ajudar a ler.
"""


# ---------------------------------------------------------------------------
# Provedores
# ---------------------------------------------------------------------------

def _provider() -> str:
    return os.getenv("AI_PROVIDER", "gemini").lower()


def is_configured() -> bool:
    key = "ANTHROPIC_API_KEY" if _provider() == "claude" else "GEMINI_API_KEY"
    return bool(os.getenv(key))


def _call_gemini(system_prompt: str, messages: list[dict]) -> str:
    from google import genai
    from google.genai import types as genai_types

    client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))
    # O padrão precisa ser um modelo vivo: o `gemini-2.0-flash` foi aposentado
    # pelo Google em 18/08/2026 e a API passou a responder 404 pedindo a troca.
    model = os.getenv("GEMINI_MODEL", "gemini-3.6-flash")

    contents = [
        genai_types.Content(
            role="user" if m["role"] == "user" else "model",
            parts=[genai_types.Part(text=m["content"])],
        )
        for m in messages
    ]

    response = client.models.generate_content(
        model=model,
        contents=contents,
        config=genai_types.GenerateContentConfig(system_instruction=system_prompt),
    )
    return (response.text or "").strip()


def _call_claude(system_prompt: str, messages: list[dict]) -> str:
    import anthropic

    client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
    model = os.getenv("CLAUDE_MODEL", "claude-haiku-4-5-20251001")

    response = client.messages.create(
        model=model,
        max_tokens=2048,
        system=system_prompt,
        messages=[{"role": m["role"], "content": m["content"]} for m in messages],
    )
    # Percorre os blocos em vez de assumir `content[0].text`: a resposta pode
    # começar com um bloco que não é texto, e indexar direto quebraria.
    return "".join(bloco.text for bloco in response.content if bloco.type == "text")


def ask(system_prompt: str, messages: list[dict]) -> str:
    """Chama o provedor configurado. Síncrono — rode fora do event loop."""
    if not is_configured():
        raise AssistantUnavailableError(
            "O assistente não está disponível no momento."
        )

    answer = _call_claude(system_prompt, messages) if _provider() == "claude" else _call_gemini(system_prompt, messages)
    return answer or "Não consegui gerar uma resposta. Tente reformular a pergunta."
