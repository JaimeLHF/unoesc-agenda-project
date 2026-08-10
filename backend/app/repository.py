"""
Repositório — encapsula leituras/escritas no banco.

Não tem lógica de negócio: só CRUD + upsert. Os endpoints do FastAPI
chamam as funções daqui.
"""

from typing import Iterable, Optional

from sqlalchemy import delete, select, update
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.orm import Session

from app.database import (
    DoneEvent,
    Event,
    Meta,
    SessionLocal,
    Subject,
    event_key,
    utc_now,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def get_session() -> Session:
    """Sessão única para um request. Quem chama é responsável pelo close()."""
    return SessionLocal()


# ---------------------------------------------------------------------------
# Subjects + Events (cache do scraping)
# ---------------------------------------------------------------------------

def upsert_subjects(session: Session, subjects: list[dict]) -> None:
    """Insere ou atualiza cada disciplina. `name` é a PK."""
    for s in subjects:
        stmt = sqlite_insert(Subject).values(
            name=s["name"],
            content=s.get("content"),
            dof=s.get("dof"),
            course_id=str(s["course_id"]) if s.get("course_id") else None,
            course_url=s.get("course_url"),
            updated_at=utc_now(),
        )
        stmt = stmt.on_conflict_do_update(
            index_elements=[Subject.name],
            set_={
                "content": stmt.excluded.content,
                "dof": stmt.excluded.dof,
                "course_id": stmt.excluded.course_id,
                "course_url": stmt.excluded.course_url,
                "updated_at": utc_now(),
            },
        )
        session.execute(stmt)


def upsert_events(session: Session, events: list[dict]) -> None:
    """
    Insere ou atualiza cada evento usando `stable_key` como identidade.
    Eventos antigos (que não vieram no scrape mais recente) NÃO são removidos
    — preserva histórico.
    """
    for e in events:
        key = event_key(e)
        e["stable_key"] = key  # devolvido ao frontend, que não recalcula mais
        stmt = sqlite_insert(Event).values(
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
            index_elements=[Event.stable_key],
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


def set_google_event_id(session: Session, stable_key: str, google_event_id: str) -> None:
    """
    Registra o ID do evento criado no Google Calendar. É o que permite ao
    frontend mostrar o evento como já sincronizado depois de um reload.
    """
    session.execute(
        update(Event)
        .where(Event.stable_key == stable_key)
        .values(google_event_id=google_event_id)
    )


def list_synced_keys(session: Session) -> list[str]:
    """`stable_key` de todo evento que já foi para o Google Calendar."""
    rows = session.execute(
        select(Event.stable_key).where(Event.google_event_id.is_not(None))
    ).all()
    return [r[0] for r in rows]


def list_subjects(session: Session) -> list[Subject]:
    return list(session.execute(select(Subject).order_by(Subject.name)).scalars())


def list_events(session: Session) -> list[Event]:
    return list(
        session.execute(
            select(Event).order_by(Event.date.asc(), Event.time.asc().nulls_first())
        ).scalars()
    )


# ---------------------------------------------------------------------------
# Done events
# ---------------------------------------------------------------------------

def list_done_keys(session: Session) -> list[str]:
    rows = session.execute(select(DoneEvent.stable_key)).all()
    return [r[0] for r in rows]


def mark_done(session: Session, stable_key: str) -> None:
    """Idempotente — marcar duas vezes não dá erro."""
    stmt = sqlite_insert(DoneEvent).values(
        stable_key=stable_key, completed_at=utc_now()
    )
    stmt = stmt.on_conflict_do_nothing(index_elements=[DoneEvent.stable_key])
    session.execute(stmt)


def unmark_done(session: Session, stable_key: str) -> None:
    session.execute(delete(DoneEvent).where(DoneEvent.stable_key == stable_key))


# ---------------------------------------------------------------------------
# Meta (timestamps livres)
# ---------------------------------------------------------------------------

def set_meta(session: Session, key: str, value: str) -> None:
    stmt = sqlite_insert(Meta).values(key=key, value=value)
    stmt = stmt.on_conflict_do_update(
        index_elements=[Meta.key], set_={"value": stmt.excluded.value}
    )
    session.execute(stmt)


def get_meta(session: Session, key: str) -> Optional[str]:
    row = session.execute(select(Meta.value).where(Meta.key == key)).first()
    return row[0] if row else None


# ---------------------------------------------------------------------------
# Operações de manutenção
# ---------------------------------------------------------------------------

def clear_cache(session: Session) -> None:
    """
    Apaga subjects, events e meta. Mantém intencionalmente os done_events —
    o usuário não quer perder o que já marcou como concluído ao limpar cache.
    """
    session.execute(delete(Event))
    session.execute(delete(Subject))
    session.execute(delete(Meta))
