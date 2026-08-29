"""
Lumi — a assistente de organização da agenda.

Recebe uma pergunta do aluno e responde sobre **planejamento**: o que vence
primeiro, como distribuir o estudo até o prazo, onde há acúmulo de entregas no
mesmo dia.

O contexto enviado ao modelo é montado aqui, a partir do que já está em cache:
título, data, hora, disciplina e tipo do evento.

**O enunciado entra, e só para resumir.** Até 29/08/2026 nada do conteúdo da
atividade chegava aqui, porque o assistente que resolvia provas foi removido
por isso. O aluno perguntava "sobre o que é essa atividade?" e ouvia "não
tenho acesso" — que é a pergunta mais natural de quem olha um título e uma
data. Agora, quando a pergunta é sobre o que a atividade pede, o backend busca
o enunciado **daquela** atividade e o injeta no prompt com uma ordem única:
resumir o que foi proposto. Continua valendo o que nunca pode voltar — nenhuma
resposta, nenhum trecho pronto do trabalho, e o modelo recusa mesmo com o
enunciado à mão (`REGRAS DO ENUNCIADO` em `build_system_prompt`). A escolha da
atividade é feita por `escolher_atividade`, aqui, e não pelo modelo: só uma
atividade da agenda do próprio aluno pode ser aberta.
"""

import os
import re
import unicodedata
from dataclasses import dataclass

from sqlalchemy.orm import Session

from app import repository as repo
from app.database import User, utc_now

# Quantas perguntas cada plano permite por mês. O padrão do gratuito subiu
# de 5 para 20 em 19/08/2026: com 5 o aluno gastava a cota na primeira
# semana de prova, que é justamente quando a Lumi serve para alguma coisa.
FREE_MONTHLY_QUOTA = int(os.getenv("FREE_AI_QUOTA", "20"))
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


def eventos_pendentes(session: Session, user_id: str) -> list:
    """Eventos futuros e não concluídos, em ordem de data."""
    hoje = utc_now().strftime("%Y-%m-%d")
    done = set(repo.list_done_keys(session, user_id))
    return [
        ev for ev in repo.list_events(session, user_id)
        if ev.date >= hoje and ev.stable_key not in done
    ]


def build_context(session: Session, user_id: str) -> str:
    """
    Linha por evento pendente, em ordem de data. Só metadados.

    Eventos já marcados como concluídos e eventos passados ficam de fora: o
    aluno pergunta sobre o que ainda tem pela frente, e cada linha a menos é
    contexto mais barato e mais preciso.
    """
    linhas = []
    for event in eventos_pendentes(session, user_id):
        tipo = TYPE_LABELS.get(event.type, event.type)
        hora = f" às {event.time}" if event.time else ""
        linhas.append(f"- {event.date}{hora} | {event.subject} | {tipo}: {event.title}")
        if len(linhas) >= MAX_EVENTS_IN_CONTEXT:
            break

    if not linhas:
        return "O aluno não tem nenhuma atividade pendente no momento."

    return "\n".join(linhas)


# ---------------------------------------------------------------------------
# Qual atividade o aluno quer que seja resumida
# ---------------------------------------------------------------------------

# Palavras que denunciam pergunta sobre o **conteúdo** da atividade, e não
# sobre a agenda. "quando" e "qual o prazo" ficam de fora de propósito: essas
# a Lumi já responde com o que está em cache, sem custar uma ida ao Moodle.
_INTENCAO_CONTEUDO = re.compile(
    r"(sobre o que|do que (se )?trata|o que (e|eh) (essa|esse|a|o) "
    r"|o que (eu )?(preciso|tenho que|devo) (fazer|entregar|produzir)"
    r"|o que (a |essa |esse )?(atividade|trabalho|tarefa|prova|avaliacao)"
    r"|enunciado|resum(o|ir|a|e)|explica|explique|me diga o que|em que consiste"
    r"|qual (e|eh) (a proposta|o objetivo|o tema))",
    re.IGNORECASE,
)

# Palavras curtas e conectivos não identificam disciplina nenhuma.
_VAZIAS = {
    "de", "da", "do", "das", "dos", "e", "em", "para", "por", "com", "sem",
    "no", "na", "nos", "nas", "a", "o", "as", "os", "um", "uma", "ao", "aos",
    "atividade", "trabalho", "tarefa", "entrega", "prova", "avaliativa",
    "avaliacao", "disciplina", "materia", "sobre", "que", "qual", "essa",
    "esse", "este", "esta", "meu", "minha", "the",
}


def _normalizar(texto: str) -> str:
    """Minúsculas, sem acento — para comparar "avaliação" com "avaliacao"."""
    sem_acento = unicodedata.normalize("NFKD", texto)
    sem_acento = "".join(c for c in sem_acento if not unicodedata.combining(c))
    return sem_acento.lower()


def _palavras(texto: str) -> set[str]:
    return {
        p for p in re.split(r"[^a-z0-9]+", _normalizar(texto))
        if len(p) >= 3 and p not in _VAZIAS
    }


def quer_conteudo(pergunta: str) -> bool:
    """A pergunta é sobre o que a atividade pede, e não sobre a agenda?"""
    return bool(_INTENCAO_CONTEUDO.search(_normalizar(pergunta)))


def escolher_atividade(pergunta: str, eventos: list, anteriores: str = ""):
    """
    Qual atividade da agenda a pergunta está citando — ou `None`.

    A escolha é do servidor e não do modelo: o que for aberto no Moodle tem
    que ser uma atividade **desta** agenda, senão o assistente vira um
    navegador com a senha do aluno.

    Pontua por palavra em comum, com o título valendo o dobro da disciplina —
    "Atividade Avaliativa 2" identifica melhor do que o nome do componente,
    que se repete em várias entregas. Quando a pergunta não cita nada
    ("sobre o que é essa atividade?"), a busca cai para o que já foi dito
    antes na conversa, que é onde o "essa" aponta.
    """
    if not eventos:
        return None

    for texto in (pergunta, anteriores):
        if not texto:
            continue
        palavras = _palavras(texto)
        if not palavras:
            continue

        melhor, melhor_score = None, 0
        for ev in eventos:
            subject = re.sub(r"^\d+\s*-\s*", "", ev.subject or "")
            score = len(_palavras(subject) & palavras)
            score += 2 * len(_palavras(ev.title or "") & palavras)
            # Os eventos chegam em ordem de data, então o `>` mantém o mais
            # próximo quando dois empatam — é o que o aluno tem em mente.
            if score > melhor_score:
                melhor, melhor_score = ev, score

        if melhor is not None:
            return melhor

    return None


def formatar_enunciado(evento, conteudo: dict, limite: int = 4000) -> str:
    """
    O texto da atividade, cortado no que cabe num prompt.

    4000 caracteres cobrem o enunciado inteiro das tarefas vistas até hoje; o
    corte existe para a página que traz o PDF colado dentro, que já veio com
    dezenas de milhares de caracteres.
    """
    intro = (conteudo.get("intro") or "").strip()
    if not intro:
        return ""
    if len(intro) > limite:
        intro = intro[:limite].rstrip() + " […]"
    return (
        f"Atividade: {evento.title} ({evento.subject}), prazo {evento.date}.\n"
        f"Enunciado publicado pelo professor:\n{intro}"
    )


# ---------------------------------------------------------------------------
# Prompt
# ---------------------------------------------------------------------------

# O modelo abre a resposta com esta linha quando não conseguiu ajudar. O
# backend a remove antes de devolver e, nesse caso, não desconta a pergunta do
# saldo do mês: cobrar por "não sei" é cobrar pelo que o aluno não recebeu.
MARCA_SEM_AJUDA = "SEM_AJUDA"


def separar_marca(resposta: str) -> tuple[str, bool]:
    """Devolve (texto limpo, ajudou?)."""
    texto = (resposta or "").strip()
    if texto.upper().startswith(MARCA_SEM_AJUDA):
        limpo = texto[len(MARCA_SEM_AJUDA):].lstrip(" :-\u2013\u2014\n").strip()
        return (limpo or "Não consegui ajudar com isso."), False
    return texto, True


_REGRAS_SEM_ENUNCIADO = (
    "- Você conhece o título, a data e a disciplina de cada atividade — nada "
    "além disso. Se perguntarem sobre o enunciado ou o conteúdo, diga que não "
    "conseguiu abrir a atividade no Moodle."
)

_REGRAS_COM_ENUNCIADO = """- O enunciado abaixo é o texto que o professor publicou na atividade. Use-o para explicar, em suas palavras, o que a atividade pede: tema, formato, o que precisa ser entregue e o que o professor exige.
- Nunca produza o trabalho nem parte dele: nada de resposta, código pronto, texto para copiar, exemplo resolvido ou rascunho da entrega. Se pedirem isso, recuse numa linha e ofereça o plano de execução até o prazo.
- Não invente o que não está no enunciado. Se algo não estiver escrito ali, diga que o enunciado não diz."""


def build_system_prompt(context: str, enunciado: str = "") -> str:
    bloco_enunciado = (
        f"\n\nENUNCIADO DA ATIVIDADE SOBRE A QUAL O ALUNO PERGUNTOU:\n{enunciado}"
        if enunciado else ""
    )
    regras_conteudo = _REGRAS_COM_ENUNCIADO if enunciado else _REGRAS_SEM_ENUNCIADO

    return f"""Você é Lumi, assistente de organização da Agenda UNOESC. Ajuda o aluno a se planejar: o que fazer primeiro, como dividir o tempo até cada prazo, onde há acúmulo de entregas. E, quando o enunciado da atividade estiver no contexto, explica o que a atividade pede.

Hoje é {utc_now().strftime('%d/%m/%Y')}.

Atividades pendentes do aluno:
{context}{bloco_enunciado}

REGRAS:
- Responda sobre organização, prazos, planejamento de estudo e sobre o que cada atividade pede.
{regras_conteudo}
- Nunca responda questões de prova, exercício ou trabalho, mesmo que o aluno cole o enunciado na pergunta. Nesse caso, ofereça ajuda para planejar o tempo de estudo daquela atividade.
- Seja concreto: cite datas e nomes de disciplinas em vez de conselhos genéricos.
- Português brasileiro.

QUANDO NÃO DER PARA AJUDAR:
- Se você não tem o dado pedido, não pode responder aquilo ou o pedido está fora do que você faz, comece a resposta com a linha exata {MARCA_SEM_AJUDA} e, na linha seguinte, diga em uma frase o que dá para fazer no lugar.
- Use essa marca só quando a resposta não ajudar de verdade. Resposta útil, mesmo curta, nunca leva a marca.

TAMANHO — o aluno lê isso no celular, entre uma aula e outra:
- No máximo 5 linhas na resposta inteira. Se não couber, corte o que é menos urgente.
- Sem saudação, sem repetir a pergunta, sem parágrafo de encerramento e sem oferecer ajuda extra no fim.
- Quando listar, no máximo 4 itens, um por linha, cada um numa frase.
- Data e nome da disciplina em toda linha que fala de uma atividade; o resto sobra.
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
