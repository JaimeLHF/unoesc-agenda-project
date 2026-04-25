"""
Camada de persistência do UNOESC Agenda — SQLite + SQLAlchemy.

A aplicação é local/single-user: cada instalação usa o próprio arquivo
`agenda.db` no diretório do backend. Sem autenticação, sem multi-tenant.
"""

from datetime import datetime
from pathlib import Path
from typing import Optional

from sqlalchemy import String, Text, DateTime, create_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker

# Arquivo do banco fica ao lado do package `app/`
DB_PATH = Path(__file__).resolve().parent.parent / "agenda.db"
DATABASE_URL = f"sqlite:///{DB_PATH}"

# `check_same_thread=False` permite que o pool seja usado por threads
# diferentes (FastAPI executa endpoints em workers diferentes).
engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False},
    future=True,
)

SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False, future=True)


class Base(DeclarativeBase):
    """Base declarativa do SQLAlchemy 2.x."""


# ---------------------------------------------------------------------------
# Modelos
# ---------------------------------------------------------------------------

class Subject(Base):
    """Cache do conteúdo bruto extraído de cada disciplina."""

    __tablename__ = "subjects"

    name: Mapped[str] = mapped_column(String, primary_key=True)
    content: Mapped[Optional[str]] = mapped_column(Text)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )


class Event(Base):
    """
    Cache dos eventos extraídos. `stable_key` é a chave que sobrevive entre
    scrapings (UUIDs internos do scraper são regerados a cada run).
    """

    __tablename__ = "events"

    stable_key: Mapped[str] = mapped_column(String, primary_key=True)
    title: Mapped[str] = mapped_column(String, nullable=False)
    date: Mapped[str] = mapped_column(String, nullable=False)        # AAAA-MM-DD
    time: Mapped[Optional[str]] = mapped_column(String)              # HH:MM
    description: Mapped[Optional[str]] = mapped_column(Text)
    subject: Mapped[str] = mapped_column(String, nullable=False, index=True)
    type: Mapped[str] = mapped_column(String, nullable=False)        # webconference|deadline|exam|other
    source: Mapped[Optional[str]] = mapped_column(String)            # moodle_calendar | gemini
    url: Mapped[Optional[str]] = mapped_column(String)               # link direto pro evento no portal
    last_seen_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )


class DoneEvent(Base):
    """Marcação local de evento concluído pelo aluno."""

    __tablename__ = "done_events"

    stable_key: Mapped[str] = mapped_column(String, primary_key=True)
    completed_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class Meta(Base):
    """Pares chave/valor pra metadados livres (último scrape, versão, etc.)."""

    __tablename__ = "meta"

    key: Mapped[str] = mapped_column(String, primary_key=True)
    value: Mapped[str] = mapped_column(String)


# ---------------------------------------------------------------------------
# Funções utilitárias
# ---------------------------------------------------------------------------

def stable_event_key(subject: str, date: str, title: str) -> str:
    """
    Chave estável para um evento entre execuções do scraper.
    Mesma fórmula usada no frontend para identidade entre sessões.
    """
    return f"{subject}|{date}|{title}".lower().strip()


def init_db() -> None:
    """Cria tabelas que ainda não existem. Chamado no startup do FastAPI."""
    Base.metadata.create_all(bind=engine)
    _run_lightweight_migrations()


def _run_lightweight_migrations() -> None:
    """
    Migração pragmática para desenvolvimento single-user: detecta colunas
    declaradas no modelo que faltam na tabela e adiciona via ALTER TABLE.

    Funciona porque (1) só adicionamos colunas — nunca renomeamos/removemos —
    e (2) SQLite suporta `ALTER TABLE ... ADD COLUMN` sem reescrever a tabela.
    Para mudanças mais complexas (renames, drops), o fluxo segue sendo apagar
    o `agenda.db` e refazer o scrape.
    """
    from sqlalchemy import inspect, text

    inspector = inspect(engine)

    with engine.begin() as conn:
        for table in Base.metadata.sorted_tables:
            existing_cols = {col["name"] for col in inspector.get_columns(table.name)}
            for column in table.columns:
                if column.name in existing_cols:
                    continue

                # Constrói "TYPE [NULL|NOT NULL] [DEFAULT ...]"
                col_type = column.type.compile(dialect=engine.dialect)
                pieces = [f'ALTER TABLE "{table.name}" ADD COLUMN "{column.name}" {col_type}']
                if column.nullable is False and column.default is None:
                    # SQLite não permite ADD COLUMN NOT NULL sem default;
                    # caímos no fluxo manual nesses raros casos.
                    print(
                        f"[DB] coluna '{column.name}' em '{table.name}' é NOT NULL sem default. "
                        f"Apague backend/agenda.db para recriar do zero."
                    )
                    continue
                if column.default is not None and getattr(column.default, "is_scalar", False):
                    default_value = column.default.arg
                    if isinstance(default_value, str):
                        default_value = f"'{default_value}'"
                    pieces.append(f"DEFAULT {default_value}")

                stmt = " ".join(pieces)
                print(f"[DB] migração: {stmt}")
                conn.execute(text(stmt))
