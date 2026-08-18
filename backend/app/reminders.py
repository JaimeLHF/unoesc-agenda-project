"""
Lembrete por e-mail antes do prazo.

## Por que existe

O app só avisa quem abre o app. Quem esquece da entrega não abre — é essa a
definição de esquecer. O lembrete é a única parte do projeto que trabalha com
a tela fechada.

## Como é disparado

Por uma chamada externa em `POST /api/tasks/reminders`, protegida por
`TASK_KEY`, e não por um agendador dentro do processo: a máquina no Fly dorme
quando ninguém acessa, e um `while True` dentro dela simplesmente não roda. Um
cron de fora (o workflow em `.github/workflows/lembretes.yml`) acorda o app e
manda rodar.

## O que ele consegue avisar

Só o que já está no banco — o job não tem a senha do aluno para ir ao Moodle
buscar novidade. Na prática isso avisa de prazo que o aluno já viu uma vez, que
é o caso comum: a entrega estava lá, ele viu há duas semanas, e esqueceu.
"""

import logging
import os
import smtplib
from datetime import datetime, timedelta
from email.message import EmailMessage

from sqlalchemy import select

from app.database import Event, ReminderSent, User, utc_now
from app.moodle import TZ_BR
from app.repository import get_session

logger = logging.getLogger("agenda.reminders")

# Janela do aviso: eventos que caem entre 12h e 36h à frente. É larga de
# propósito — o cron roda uma vez por dia e um evento não pode cair no vão
# entre duas execuções.
HORAS_MIN = 12
HORAS_MAX = 36


def _smtp_configurado() -> bool:
    return bool(os.getenv("SMTP_HOST") and os.getenv("SMTP_FROM"))


def _enviar(destino: str, assunto: str, corpo: str) -> None:
    """Envia um e-mail simples. Exceção sobe para quem chama registrar."""
    msg = EmailMessage()
    msg["Subject"] = assunto
    msg["From"] = os.getenv("SMTP_FROM", "")
    msg["To"] = destino
    msg.set_content(corpo)

    host = os.getenv("SMTP_HOST", "")
    porta = int(os.getenv("SMTP_PORT", "587"))
    usuario = os.getenv("SMTP_USER")
    senha = os.getenv("SMTP_PASSWORD")

    with smtplib.SMTP(host, porta, timeout=20) as servidor:
        servidor.starttls()
        if usuario and senha:
            servidor.login(usuario, senha)
        servidor.send_message(msg)


def _texto(nome: str, eventos: list[Event]) -> tuple[str, str]:
    """Assunto e corpo do aviso. Texto puro: chega igual em qualquer cliente."""
    if len(eventos) == 1:
        e = eventos[0]
        assunto = f"Amanhã: {e.title} ({e.subject})"
    else:
        assunto = f"Amanhã você tem {len(eventos)} compromissos na UNOESC"

    linhas = [f"Oi, {nome or 'tudo bem'}?", "", "O que vence nas próximas horas:", ""]
    for e in eventos:
        hora = f" às {e.time}" if e.time else ""
        linhas.append(f"• {e.title} — {e.subject}{hora}")
        if e.url:
            linhas.append(f"  {e.url}")
    linhas += [
        "",
        "Ver a agenda completa: https://unoesc-agenda.fly.dev/",
        "",
        "Para parar de receber, desligue os lembretes no seu perfil no app.",
        "Este é um projeto de alunos e não é serviço oficial da UNOESC.",
    ]
    return assunto, "\n".join(linhas)


def enviar_lembretes(agora: datetime | None = None) -> dict:
    """
    Percorre quem pediu lembrete e avisa do que vence nas próximas horas.

    Devolve um resumo com o que foi enviado — é o corpo da resposta do
    endpoint, e é como se descobre que o cron rodou sem fazer nada.
    """
    agora = agora or datetime.now(TZ_BR)
    inicio = agora + timedelta(hours=HORAS_MIN)
    fim = agora + timedelta(hours=HORAS_MAX)

    resumo = {"alunos": 0, "emails": 0, "eventos": 0, "erros": 0, "enviando": _smtp_configurado()}

    with get_session() as db:
        alunos = list(
            db.execute(
                select(User).where(User.reminders_enabled.is_(True), User.email.is_not(None))
            ).scalars()
        )

        for aluno in alunos:
            resumo["alunos"] += 1

            # A busca é sempre por user_id — a regra de sempre; aqui ela também
            # decide para quem vai o e-mail, que é o pior lugar para errar.
            eventos = list(
                db.execute(select(Event).where(Event.user_id == aluno.id)).scalars()
            )

            ja_avisados = {
                r.stable_key
                for r in db.execute(
                    select(ReminderSent).where(ReminderSent.user_id == aluno.id)
                ).scalars()
            }

            pendentes = []
            for e in eventos:
                if e.stable_key in ja_avisados:
                    continue
                try:
                    quando = datetime.strptime(
                        f"{e.date} {e.time or '23:59'}", "%Y-%m-%d %H:%M"
                    ).replace(tzinfo=TZ_BR)
                except ValueError:
                    continue
                if inicio <= quando <= fim:
                    pendentes.append(e)

            if not pendentes:
                continue

            pendentes.sort(key=lambda e: (e.date, e.time or ""))
            assunto, corpo = _texto(aluno.moodle_username.split("@")[0], pendentes)

            if not _smtp_configurado():
                # Sem SMTP o job continua rodando e registrando o que faria:
                # é assim que dá para testar o recorte sem mandar e-mail.
                logger.info("SMTP desligado — %d evento(s) para %s", len(pendentes), aluno.email)
                continue

            try:
                _enviar(aluno.email or "", assunto, corpo)
            except Exception as exc:  # um destinatário quebrado não para a fila
                resumo["erros"] += 1
                logger.warning("Lembrete não saiu para %s: %s", aluno.email, exc)
                continue

            for e in pendentes:
                db.add(ReminderSent(user_id=aluno.id, stable_key=e.stable_key, sent_at=utc_now()))
            db.commit()

            resumo["emails"] += 1
            resumo["eventos"] += len(pendentes)

    return resumo
