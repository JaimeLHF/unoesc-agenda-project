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


def resumo_do_dia(eventos: list[dict]) -> Optional[tuple[str, str, str]]:
    """O que vence hoje. É o aviso que chega todo dia no mesmo horário."""
    if not eventos:
        return None

    provas = [e for e in eventos if e["type"] == "exam"]
    resto = [e for e in eventos if e["type"] != "exam"]

    # A prova encabeça: é o compromisso que não dá para remarcar.
    if provas:
        p = provas[0]
        hora = f" às {p['time']}" if p.get("time") else ""
        titulo = f"Prova hoje{hora}"
        corpo = _sem_codigo(p["subject"])
        if len(provas) > 1:
            corpo += f" — e mais {len(provas) - 1} prova(s)"
        if resto:
            corpo += f" · {len(resto)} entrega(s) também vencem hoje"
    else:
        titulo = f"Hoje: {len(resto)} entrega(s)"
        corpo = _lista([_sem_codigo(e["subject"]) for e in resto])

    return titulo, corpo, "/"


def vespera(eventos: list[dict]) -> Optional[tuple[str, str, str]]:
    """O que vence amanhã. Sai à noite, quando ainda dá tempo de fazer."""
    if not eventos:
        return None

    provas = [e for e in eventos if e["type"] == "exam"]
    if provas:
        p = provas[0]
        hora = f" às {p['time']}" if p.get("time") else ""
        return f"Amanhã tem prova{hora}", _sem_codigo(p["subject"]), "/"

    nomes = [_sem_codigo(e["subject"]) for e in eventos]
    return (
        f"Amanhã: {len(eventos)} entrega(s)",
        _lista(nomes),
        "/",
    )


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
