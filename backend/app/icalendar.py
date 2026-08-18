"""
Agenda em formato iCalendar (RFC 5545), para o aluno assinar no calendário.

## Por que existe, tendo `calendar_sync.py`

A sincronização com o Google escreve os eventos uma vez, com OAuth — e a tela
de consentimento está parada na verificação do Google, então na prática ela
fica desligada para quem não é testador. A assinatura resolve o mesmo problema
por outro caminho: o aluno cola um endereço no Google Agenda, no Apple
Calendário ou no Outlook, e o calendário volta sozinho de tempos em tempos
buscar a versão nova. Nenhum consentimento, nenhuma biblioteca.

A contrapartida é que o app não escolhe a hora da atualização — cada cliente
tem o seu ritmo, o do Google costuma ser de horas. Para prazo de entrega, que
é marcado com semanas de antecedência, isso serve; para avisar de algo que
mudou hoje, não. Por isso o lembrete por e-mail existe à parte.

## Sobre o conteúdo

Só o que o app já mostra na tela: título, disciplina, tipo e o link da
atividade no Moodle. Nada de enunciado — o mesmo motivo do assistente.
"""

from datetime import datetime, timedelta
from typing import Iterable

from app.database import Event

# O Moodle da UNOESC marca tudo no horário de Brasília, e os eventos são
# gravados sem fuso. Em vez de declarar um VTIMEZONE inteiro, cada horário sai
# convertido para UTC — é o formato que todo cliente entende sem ambiguidade.
UTC_OFFSET = timedelta(hours=3)

TIPO_LEGIVEL = {
    "webconference": "Webconferência",
    "deadline": "Entrega",
    "exam": "Prova",
    "other": "Evento",
}


def _escapar(texto: str) -> str:
    """Escapa vírgula, ponto e vírgula e quebra de linha, como manda a RFC."""
    return (
        (texto or "")
        .replace("\\", "\\\\")
        .replace(";", "\\;")
        .replace(",", "\\,")
        .replace("\n", "\\n")
    )


def _dobrar(linha: str) -> str:
    """
    Quebra linhas acima de 75 octetos, continuando com um espaço.

    Sem isso o Outlook rejeita o arquivo inteiro quando o título de uma
    atividade é longo — e títulos de atividade da UNOESC são longos.
    """
    bruto = linha.encode("utf-8")
    if len(bruto) <= 75:
        return linha

    pedacos = []
    atual = b""
    for char in linha:
        codificado = char.encode("utf-8")
        limite = 75 if not pedacos else 74  # continuação começa com espaço
        if len(atual) + len(codificado) > limite:
            pedacos.append(atual.decode("utf-8"))
            atual = b""
        atual += codificado
    pedacos.append(atual.decode("utf-8"))
    return "\r\n ".join(pedacos)


def _instante(data: str, hora: str | None) -> tuple[str, str]:
    """
    Converte data/hora do evento em (DTSTART, DTEND) no formato UTC.

    Evento sem hora vira dia inteiro: `VALUE=DATE`, que é como o calendário
    mostra "vence hoje" numa faixa no topo do dia em vez de um horário
    inventado à meia-noite.
    """
    if not hora:
        inicio = datetime.strptime(data, "%Y-%m-%d")
        fim = inicio + timedelta(days=1)
        return (
            f"DTSTART;VALUE=DATE:{inicio.strftime('%Y%m%d')}",
            f"DTEND;VALUE=DATE:{fim.strftime('%Y%m%d')}",
        )

    inicio = datetime.strptime(f"{data} {hora}", "%Y-%m-%d %H:%M") + UTC_OFFSET
    fim = inicio + timedelta(hours=1)
    return (
        f"DTSTART:{inicio.strftime('%Y%m%dT%H%M%SZ')}",
        f"DTEND:{fim.strftime('%Y%m%dT%H%M%SZ')}",
    )


def build_calendar(events: Iterable[Event], *, nome: str = "Agenda UNOESC") -> str:
    """
    Monta o texto do `.ics` a partir dos eventos do aluno.

    `UID` sai da `stable_key`, que sobrevive entre atualizações — é o que faz o
    calendário do aluno atualizar o evento existente em vez de criar um
    segundo quando o professor muda a data.
    """
    agora = datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")

    linhas = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//Agenda UNOESC//PT-BR//",
        "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH",
        f"X-WR-CALNAME:{_escapar(nome)}",
        "X-WR-TIMEZONE:America/Sao_Paulo",
        # Dica de atualização para os clientes que a respeitam.
        "REFRESH-INTERVAL;VALUE=DURATION:PT6H",
        "X-PUBLISHED-TTL:PT6H",
    ]

    for e in events:
        try:
            dtstart, dtend = _instante(e.date, e.time)
        except ValueError:  # data fora do formato: um evento não derruba o feed
            continue

        tipo = TIPO_LEGIVEL.get(e.type or "other", "Evento")
        descricao = " · ".join(filter(None, [tipo, e.subject, e.description or ""]))

        linhas += [
            "BEGIN:VEVENT",
            f"UID:{e.stable_key}@unoesc-agenda",
            f"DTSTAMP:{agora}",
            dtstart,
            dtend,
            _dobrar(f"SUMMARY:{_escapar(f'{e.title} — {e.subject}')}"),
            _dobrar(f"DESCRIPTION:{_escapar(descricao)}"),
        ]
        if e.url:
            linhas.append(_dobrar(f"URL:{_escapar(e.url)}"))
        linhas.append("END:VEVENT")

    linhas.append("END:VCALENDAR")
    return "\r\n".join(linhas) + "\r\n"
