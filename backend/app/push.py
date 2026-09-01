"""
Notificação push — o aviso que chega na tela bloqueada do celular.

## Como isso chega no aparelho

O navegador do aluno gera uma inscrição (`endpoint` + duas chaves) e o servidor
guarda. Para entregar, o servidor manda a mensagem **cifrada** para o endpoint,
assinada com a chave VAPID; quem roteia (Google no Android, Apple no iPhone)
encaminha sem conseguir ler o conteúdo. O `sw.js` recebe e desenha a
notificação.

## O que é preciso saber antes de mexer

**No iPhone só funciona com o app instalado na tela inicial.** Aberto no
Safari, o `Notification.requestPermission()` nem existe. É por isso que o PWA
veio antes desta função, e por isso a tela de opt-in explica isso em vez de
mostrar um botão que não faz nada.

**Trocar o par VAPID invalida todas as inscrições.** Cada aluno teria de
autorizar de novo, e não há canal para avisar — o canal é justamente o que
parou de funcionar. As chaves nascem em `scripts/gerar_vapid.py`.

**Sem `VAPID_PUBLIC_KEY` o recurso simplesmente não aparece**, do mesmo jeito
que a Lumi sem chave de IA: o `/api/health` acusa e o frontend não desenha o
botão. Nada aqui derruba o app.
"""

import json
import logging
import os
from typing import Any, Optional

logger = logging.getLogger("agenda.push")

# Quantas rejeições seguidas antes de descartar a inscrição. Uma falha isolada
# é rede; 404/410 é aparelho que não existe mais e some na primeira.
MAX_FALHAS = 5


# As chaves são lidas na hora do uso, não no import. Constante de módulo aqui
# amarraria o valor à ordem dos imports, e quem carrega o `.env` é o `main` —
# que importa este arquivo. O `os.getenv` é barato.
def chave_publica() -> str:
    """Chave VAPID pública. Vai para o navegador na hora de inscrever."""
    return os.getenv("VAPID_PUBLIC_KEY", "").strip()


def _chave_privada() -> str:
    return os.getenv("VAPID_PRIVATE_KEY", "").strip()


def _assunto() -> str:
    """Contato de quem envia — para onde o serviço de push reclama."""
    return os.getenv("VAPID_SUBJECT", "mailto:jaimehansenfilho@gmail.com").strip()


def configurado() -> bool:
    """As duas chaves estão presentes? Sem isso o recurso não existe."""
    return bool(chave_publica() and _chave_privada())


class InscricaoMorta(Exception):
    """O serviço de push disse que este endpoint não existe mais (404/410)."""


def enviar(
    inscricao: dict,
    titulo: str,
    corpo: str,
    url: str = "/",
    tag: Optional[str] = None,
) -> None:
    """
    Entrega uma notificação. Levanta `InscricaoMorta` quando o aparelho sumiu.

    `tag` faz o navegador substituir a notificação anterior de mesmo nome em
    vez de empilhar: o resumo das 7h de hoje ocupa o lugar do de ontem, que o
    aluno já não vai ler.
    """
    if not configurado():
        raise RuntimeError("VAPID não configurado")

    from pywebpush import WebPushException, webpush

    payload = json.dumps(
        {"titulo": titulo, "corpo": corpo, "url": url, "tag": tag or "agenda"}
    )

    try:
        webpush(
            subscription_info={
                "endpoint": inscricao["endpoint"],
                "keys": {"p256dh": inscricao["p256dh"], "auth": inscricao["auth"]},
            },
            data=payload,
            vapid_private_key=_chave_privada(),
            vapid_claims={"sub": _assunto()},
            # O serviço de push guarda a mensagem por 12h se o celular estiver
            # desligado. Mais que isso e o resumo da manhã chegaria à noite,
            # dizendo "hoje" sobre um dia que já acabou.
            ttl=43200,
        )
    except WebPushException as exc:
        status = getattr(exc.response, "status_code", None)
        if status in (404, 410):
            raise InscricaoMorta(str(exc)) from exc
        raise


# ---------------------------------------------------------------------------
# Textos
#
# Cada função devolve (titulo, corpo, url) ou None quando não há o que dizer.
# Ficam aqui, juntas, porque o que define este recurso é o texto — o transporte
# é o mesmo para todas.
# ---------------------------------------------------------------------------

def _sem_codigo(disciplina: str) -> str:
    """"28743 - Engenharia de Software" → "Engenharia de Software"."""
    partes = disciplina.split(" - ", 1)
    return partes[1] if len(partes) == 2 and partes[0].strip().isdigit() else disciplina


def _lista(nomes: list[str], limite: int = 2) -> str:
    """"Cálculo, Redes e mais 2" — o corpo da notificação tem duas linhas."""
    if len(nomes) <= limite:
        return " e ".join([", ".join(nomes[:-1]), nomes[-1]] if len(nomes) > 1 else nomes)
    return f"{', '.join(nomes[:limite])} e mais {len(nomes) - limite}"


def _plural(n: int, singular: str, plural: str) -> str:
    """"1 prova" / "2 provas". Notificação não é lugar para "entrega(s)"."""
    return f"{n} {singular if n == 1 else plural}"


def _agrupar(eventos: list[dict]) -> dict[str, list[dict]]:
    """
    Separa por natureza. Webconferência não é entrega: tem hora marcada, quem
    perde não recupera, e chamá-la de "entrega" no aviso mandava o aluno olhar
    o lugar errado da agenda.
    """
    grupos: dict[str, list[dict]] = {"exam": [], "webconference": [], "outros": []}
    for e in eventos:
        grupos.get(e.get("type"), grupos["outros"]).append(e)
    return grupos


def _com_hora(evento: dict, prefixo: str) -> str:
    """"Prova hoje às 19:00" — a hora entra só quando o evento tem hora."""
    hora = evento.get("time")
    return f"{prefixo} às {hora}" if hora else prefixo


def _resumo(eventos: list[dict], quando: str) -> Optional[tuple[str, str, str]]:
    """
    O texto de "o que tem hoje" e "o que tem amanhã" — a diferença entre os
    dois é uma palavra, então é o mesmo código.

    O título é o compromisso mais duro do dia (prova, depois webconferência,
    depois entrega) e o corpo é a disciplina. Um título genérico do tipo
    "3 eventos" obrigaria a abrir o app para saber se dá para ignorar.
    """
    if not eventos:
        return None

    g = _agrupar(eventos)
    resto = []

    if g["exam"]:
        titulo = _com_hora(g["exam"][0], f"Prova {quando}")
        corpo = _sem_codigo(g["exam"][0]["subject"])
        resto = g["exam"][1:] + g["webconference"] + g["outros"]
    elif g["webconference"]:
        titulo = _com_hora(g["webconference"][0], f"Webconferência {quando}")
        corpo = _sem_codigo(g["webconference"][0]["subject"])
        resto = g["webconference"][1:] + g["outros"]
    else:
        titulo = f"{quando.capitalize()}: {_plural(len(g['outros']), 'entrega', 'entregas')}"
        corpo = _lista([_sem_codigo(e["subject"]) for e in g["outros"]])

    if resto:
        corpo += f" · e mais {_plural(len(resto), 'compromisso', 'compromissos')}"

    return titulo, corpo, "/"


def resumo_do_dia(eventos: list[dict]) -> Optional[tuple[str, str, str]]:
    """O que vence hoje. É o aviso que chega todo dia no mesmo horário."""
    return _resumo(eventos, "hoje")


def vespera(eventos: list[dict]) -> Optional[tuple[str, str, str]]:
    """O que vence amanhã. Sai à noite, quando ainda dá tempo de fazer."""
    return _resumo(eventos, "amanhã")


_NOME_DO_TIPO = {
    "exam": "Prova",
    "webconference": "Webconferência",
    "deadline": "Entrega",
}


def _daqui(minutos: int) -> str:
    """"em 2h" / "em 40 min" — quanto falta, do jeito que se fala."""
    if minutos < 90:
        return f"em {max(minutos, 1)} min"
    return f"em {round(minutos / 60)}h"


def lembrete(eventos: list[dict], minutos: int) -> Optional[tuple[str, str, str]]:
    """
    Falta pouco para o compromisso de hoje — o aviso da tarde.

    O resumo das 7h fala do dia inteiro e é lido antes da aula; a webconferência
    das 19h chega horas depois disso, quando o resumo já saiu da tela. Este é o
    empurrão perto da hora, e por isso o título diz quanto falta em vez de
    repetir a data. `minutos` é o que falta para o primeiro da lista.
    """
    if not eventos:
        return None

    e = eventos[0]
    nome = _NOME_DO_TIPO.get(e.get("type") or "", "Compromisso")
    corpo = f"{e.get('title') or nome} — {_sem_codigo(e['subject'])}"
    if e.get("time"):
        corpo += f" · {e['time']}"
    if len(eventos) > 1:
        corpo += f" · e mais {_plural(len(eventos) - 1, 'compromisso', 'compromissos')}"

    return f"{nome} {_daqui(minutos)}", corpo, "/"


def notas_novas(disciplinas: list[dict]) -> Optional[tuple[str, str, str]]:
    """
    Saiu nota. É o aviso que a UNOESC não manda por e-mail, e o motivo pelo
    qual o aluno abre o Moodle no celular várias vezes por semana.
    """
    if not disciplinas:
        return None

    if len(disciplinas) == 1:
        d = disciplinas[0]
        nota = d.get("final_grade")
        # O Moodle usa 0–100 e o aluno lê 0–10: 85 é o 8,5 do boletim.
        texto = f" — {nota / 10:.1f}".replace(".", ",") if nota is not None else ""
        return "Saiu nota", f"{_sem_codigo(d['name'])}{texto}", "/"

    return (
        f"Saíram {len(disciplinas)} notas",
        _lista([_sem_codigo(d["name"]) for d in disciplinas]),
        "/",
    )


def _sem_tipo(nome: str) -> str:
    """"Tarefa ATIVIDADE AVALIATIVA 1" → "ATIVIDADE AVALIATIVA 1"."""
    for prefixo in ("Tarefa ", "Questionário ", "Fórum ", "Arquivo ", "Pesquisa "):
        if nome.startswith(prefixo):
            return nome[len(prefixo):].strip()
    return nome


def _nota_legivel(nota: float, maximo: Optional[float]) -> str:
    """"9,0" na escala do item; "45,0/50" quando a escala não é 0–10."""
    texto = f"{nota:.1f}".replace(".", ",")
    if maximo and abs(maximo - 10) > 0.01:
        return f"{texto}/{maximo:g}"
    return texto


def notas_de_item(itens: list[dict]) -> Optional[tuple[str, str, str]]:
    """
    Saiu nota numa avaliação — o aviso que o total da disciplina não dá.

    O total (`notas_novas`) só existe quando o Moodle já atribuiu peso a tudo,
    e no meio do semestre ele vem vazio: em Desenvolvimento Mobile o professor
    lançou 9,0 na Avaliativa 1, a UNOESC mandou e-mail de nota parcial, e o
    app ficou calado porque o total continuava `None`. Este texto fala do item.
    """
    if not itens:
        return None

    if len(itens) == 1:
        item = itens[0]
        nota = _nota_legivel(item["grade"], item.get("max"))
        disciplina = _sem_codigo(item["subject"])
        return "Saiu nota", f"{disciplina} · {_sem_tipo(item['name'])} — {nota}", "/"

    disciplinas = list(dict.fromkeys(_sem_codigo(i["subject"]) for i in itens))
    return f"Saíram {len(itens)} notas", _lista(disciplinas), "/"


def prazos_alterados(eventos: list[dict]) -> Optional[tuple[str, str, str]]:
    """Mudou a data de algo. É notícia, não lembrete — por isso sai na hora."""
    if not eventos:
        return None

    if len(eventos) == 1:
        e = eventos[0]
        movimento = "adiado" if (e.get("previous_date") or "") < e["date"] else "antecipado"
        return (
            f"Prazo {movimento}",
            f"{e['title']} — {_sem_codigo(e['subject'])}",
            "/",
        )

    return (
        f"{len(eventos)} prazos mudaram de data",
        _lista([e["title"] for e in eventos]),
        "/",
    )


# ---------------------------------------------------------------------------
# O empurrãozinho de quem sumiu
#
# Aviso sem fato novo é o que queima o canal mais rápido — no Android, quem
# bloqueia não é perguntado de novo. Por isso este repertório só sai para quem
# **não abre o app há dias**, no máximo um a cada três dias, e nunca no mesmo
# disparo em que já saiu nota ou mudança de prazo (ver `_habito` no
# `scheduler.py`). A rotação é sequencial e guardada por aluno: repetir a mesma
# frase duas vezes seguidas é o que faz o aviso virar paisagem.
#
# Toda frase aqui precisa ser verdade sobre o app. "Assine o calendário" existe
# no perfil, a Lumi existe no botão flutuante, o boletim existe na disciplina —
# um convite para uma tela que não existe custa a confiança de quem abriu.
# ---------------------------------------------------------------------------

LEMBRETES_DE_HABITO: list[tuple[str, str, str]] = [
    ("Sua agenda pode ter mudado",
     "Abra e atualize — leva alguns segundos.", "/"),
    ("Por onde começar esta semana?",
     "Pergunte para a Lumi, no botão do canto da tela.", "/"),
    ("Prazo não avisa duas vezes",
     "Dê uma olhada no que vem pela frente.", "/"),
    ("Saiu nota nova?",
     "O boletim de cada disciplina está na agenda.", "/"),
    ("Semana cheia ou tranquila?",
     "A agenda conta quantos compromissos vêm aí.", "/"),
    ("Todas as disciplinas num lugar só",
     "Prazos, provas e webconferências na mesma tela.", "/"),
    ("Organize os estudos com a Lumi",
     "Ela responde em cinco linhas o que fazer primeiro.", "/"),
    ("Cinco minutos agora poupam a correria",
     "Confira os prazos da semana.", "/"),
    ("Sua agenda no calendário do celular",
     "Assine o link no seu perfil e nunca mais copie data na mão.", "/"),
    ("Instale na tela inicial",
     "Assim a agenda abre como app, e os avisos chegam sempre.", "/"),
    ("O que você entrega esta semana?",
     "Abra a agenda e confira.", "/"),
    ("Marque o que já fez",
     "O concluído sai da frente e sobra só o que falta.", "/"),
]


def habito(indice: int) -> tuple[str, str, str]:
    """A frase da vez. O índice gira sozinho quando passa do fim da lista."""
    return LEMBRETES_DE_HABITO[indice % len(LEMBRETES_DE_HABITO)]


def payload_de_teste() -> tuple[str, str, str]:
    """O que o botão "enviar teste" manda. Existe para o aluno conferir."""
    return (
        "Notificação de teste",
        "Deu certo — é assim que os avisos vão chegar.",
        "/",
    )


def para_dict(inscricao: Any) -> dict:
    """Linha do banco → o formato que `enviar()` espera."""
    return {
        "endpoint": inscricao.endpoint,
        "p256dh": inscricao.p256dh,
        "auth": inscricao.auth,
    }
