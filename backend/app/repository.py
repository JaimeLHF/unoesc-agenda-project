"""
Repositório — encapsula leituras/escritas no banco.

Não tem lógica de negócio: só CRUD + upsert. Os endpoints do FastAPI
chamam as funções daqui.

**Regra do multi-tenant**: toda função que toca cache do aluno recebe
`user_id` e filtra por ele. Não existe query global neste módulo — se um dia
aparecer uma, ela vaza a agenda de um aluno para outro.
"""

import secrets
from typing import Optional

from sqlalchemy import delete, select, update
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.orm import Session

from app.database import (
    AppSession,
    DoneEvent,
    Event,
    Meta,
    ReminderSent,
    SessionLocal,
    Subject,
    User,
    event_key,
    new_id,
    utc_now,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def get_session() -> Session:
    """Sessão única para um request. Quem chama é responsável pelo close()."""
    return SessionLocal()


# ---------------------------------------------------------------------------
# Usuários
# ---------------------------------------------------------------------------

def get_or_create_user(session: Session, moodle_username: str) -> User:
    """
    Devolve o usuário do login informado, criando na primeira vez.

    Não há cadastro no app: quem valida a senha é o Moodle, e só chegamos aqui
    depois de um login bem-sucedido.
    """
    normalized = moodle_username.strip().lower()
    user = session.execute(
        select(User).where(User.moodle_username == normalized)
    ).scalar_one_or_none()

    if user is None:
        user = User(id=new_id(), moodle_username=normalized)
        session.add(user)
        session.flush()
    else:
        user.last_login_at = utc_now()

    return user


def get_user(session: Session, user_id: str) -> Optional[User]:
    return session.get(User, user_id)


def delete_user(session: Session, user_id: str) -> None:
    """
    Apaga a conta e tudo que pertence a ela: cache, concluídos, metadados e
    sessões abertas. Suporte ao "excluir minha conta" exigido pela LGPD.
    """
    session.execute(delete(Event).where(Event.user_id == user_id))
    session.execute(delete(Subject).where(Subject.user_id == user_id))
    session.execute(delete(DoneEvent).where(DoneEvent.user_id == user_id))
    session.execute(delete(Meta).where(Meta.user_id == user_id))
    session.execute(delete(ReminderSent).where(ReminderSent.user_id == user_id))
    session.execute(delete(AppSession).where(AppSession.user_id == user_id))
    session.execute(delete(User).where(User.id == user_id))


def set_email(session: Session, user_id: str, email: str) -> None:
    """Guarda o e-mail do cadastro do Moodle, usado só pelo lembrete."""
    session.execute(update(User).where(User.id == user_id).values(email=email.strip()))


def set_reminders_enabled(session: Session, user_id: str, enabled: bool) -> None:
    session.execute(
        update(User).where(User.id == user_id).values(reminders_enabled=enabled)
    )


def get_or_create_ics_token(session: Session, user_id: str) -> Optional[str]:
    """Chave do calendário assinável do aluno, criada na primeira vez."""
    user = session.get(User, user_id)
    if user is None:
        return None
    if not user.ics_token:
        user.ics_token = secrets.token_urlsafe(24)
        session.flush()
    return user.ics_token


def reset_ics_token(session: Session, user_id: str) -> Optional[str]:
    """Troca a chave: o endereço antigo para de funcionar na hora."""
    user = session.get(User, user_id)
    if user is None:
        return None
    user.ics_token = secrets.token_urlsafe(24)
    session.flush()
    return user.ics_token


def get_user_by_ics_token(session: Session, token: str) -> Optional[User]:
    """
    Dono de uma chave de calendário.

    É a única leitura do módulo que não recebe `user_id` — ela existe
    justamente para descobrir de quem é a agenda, a partir de um segredo que
    só o dono tem. Quem chama usa o `id` devolvido para filtrar tudo o mais.
    """
    if not token:
        return None
    return session.execute(
        select(User).where(User.ics_token == token)
    ).scalar_one_or_none()


# ---------------------------------------------------------------------------
# Subjects + Events (cache do scraping)
# ---------------------------------------------------------------------------

def upsert_subjects(session: Session, user_id: str, subjects: list[dict]) -> None:
    """Insere ou atualiza cada disciplina. A PK é (user_id, name)."""
    for s in subjects:
        stmt = sqlite_insert(Subject).values(
            user_id=user_id,
            name=s["name"],
            content=s.get("content"),
            dof=s.get("dof"),
            course_id=str(s["course_id"]) if s.get("course_id") else None,
            course_url=s.get("course_url"),
            start_date=s.get("start_date"),
            end_date=s.get("end_date"),
            final_grade=s.get("final_grade"),
            updated_at=utc_now(),
        )
        stmt = stmt.on_conflict_do_update(
            index_elements=[Subject.user_id, Subject.name],
            set_={
                "content": stmt.excluded.content,
                "dof": stmt.excluded.dof,
                "course_id": stmt.excluded.course_id,
                "course_url": stmt.excluded.course_url,
                "start_date": stmt.excluded.start_date,
                "end_date": stmt.excluded.end_date,
                "final_grade": stmt.excluded.final_grade,
                "updated_at": utc_now(),
            },
        )
        session.execute(stmt)


def upsert_events(session: Session, user_id: str, events: list[dict]) -> None:
    """
    Insere ou atualiza cada evento usando (user_id, stable_key) como identidade.
    Eventos antigos (que não vieram no scrape mais recente) NÃO são removidos
    — preserva histórico.
    """
    for e in events:
        key = event_key(e)
        e["stable_key"] = key  # devolvido ao frontend, que não recalcula mais
        stmt = sqlite_insert(Event).values(
            user_id=user_id,
            stable_key=key,
            title=e["title"],
            date=e["date"],
            time=e.get("time"),
            description=e.get("description"),
            subject=e["subject"],
            type=e["type"],
            source=e.get("source"),
            url=e.get("url"),
            last_seen_at=utc_now(),
        )
        stmt = stmt.on_conflict_do_update(
            index_elements=[Event.user_id, Event.stable_key],
            set_={
                "title": stmt.excluded.title,
                "date": stmt.excluded.date,
                "time": stmt.excluded.time,
                "description": stmt.excluded.description,
                "type": stmt.excluded.type,
                "source": stmt.excluded.source,
                "url": stmt.excluded.url,
                "last_seen_at": utc_now(),
            },
        )
        session.execute(stmt)


def set_google_event_id(
    session: Session, user_id: str, stable_key: str, google_event_id: str
) -> None:
    """
    Registra o ID do evento criado no Google Calendar. É o que permite ao
    frontend mostrar o evento como já sincronizado depois de um reload.
    """
    session.execute(
        update(Event)
        .where(Event.user_id == user_id, Event.stable_key == stable_key)
        .values(google_event_id=google_event_id)
    )


def list_synced_keys(session: Session, user_id: str) -> list[str]:
    """`stable_key` de todo evento do aluno que já foi para o Google Calendar."""
    rows = session.execute(
        select(Event.stable_key).where(
            Event.user_id == user_id, Event.google_event_id.is_not(None)
        )
    ).all()
    return [r[0] for r in rows]


def list_subjects(session: Session, user_id: str) -> list[Subject]:
    return list(
        session.execute(
            select(Subject).where(Subject.user_id == user_id).order_by(Subject.name)
        ).scalars()
    )


def get_subject(session: Session, user_id: str, name: str) -> Optional[Subject]:
    return session.get(Subject, (user_id, name))


def get_event(session: Session, user_id: str, stable_key: str) -> Optional[Event]:
    """
    Um evento do aluno pela chave estável.

    A busca é sempre por (user_id, stable_key) — a chave primária composta. É
    o que faz um link de atividade compartilhado abrir só para quem tem aquela
    atividade na própria agenda.
    """
    return session.get(Event, (user_id, stable_key))


def list_events(session: Session, user_id: str) -> list[Event]:
    return list(
        session.execute(
            select(Event)
            .where(Event.user_id == user_id)
            .order_by(Event.date.asc(), Event.time.asc().nulls_first())
        ).scalars()
    )


# ---------------------------------------------------------------------------
# Done events
# ---------------------------------------------------------------------------

def list_done_keys(session: Session, user_id: str) -> list[str]:
    rows = session.execute(
        select(DoneEvent.stable_key).where(DoneEvent.user_id == user_id)
    ).all()
    return [r[0] for r in rows]


def mark_done(session: Session, user_id: str, stable_key: str) -> None:
    """Idempotente — marcar duas vezes não dá erro."""
    stmt = sqlite_insert(DoneEvent).values(
        user_id=user_id, stable_key=stable_key, completed_at=utc_now()
    )
    stmt = stmt.on_conflict_do_nothing(
        index_elements=[DoneEvent.user_id, DoneEvent.stable_key]
    )
    session.execute(stmt)


def unmark_done(session: Session, user_id: str, stable_key: str) -> None:
    session.execute(
        delete(DoneEvent).where(
            DoneEvent.user_id == user_id, DoneEvent.stable_key == stable_key
        )
    )


# ---------------------------------------------------------------------------
# Meta (timestamps livres)
# ---------------------------------------------------------------------------

def set_meta(session: Session, user_id: str, key: str, value: str) -> None:
    stmt = sqlite_insert(Meta).values(user_id=user_id, key=key, value=value)
    stmt = stmt.on_conflict_do_update(
        index_elements=[Meta.user_id, Meta.key], set_={"value": stmt.excluded.value}
    )
    session.execute(stmt)


def get_meta(session: Session, user_id: str, key: str) -> Optional[str]:
    row = session.execute(
        select(Meta.value).where(Meta.user_id == user_id, Meta.key == key)
    ).first()
    return row[0] if row else None


# ---------------------------------------------------------------------------
# Operações de manutenção
# ---------------------------------------------------------------------------

def clear_cache(session: Session, user_id: str) -> None:
    """
    Apaga subjects, events e meta **do aluno informado**. Mantém
    intencionalmente os done_events — o usuário não quer perder o que já marcou
    como concluído ao limpar cache.
    """
    session.execute(delete(Event).where(Event.user_id == user_id))
    session.execute(delete(Subject).where(Subject.user_id == user_id))
    session.execute(delete(Meta).where(Meta.user_id == user_id))
