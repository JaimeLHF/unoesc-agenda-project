"""
Camada de persistência do UNOESC Agenda — SQLite + SQLAlchemy.

A aplicação é local/single-user: cada instalação usa o próprio arquivo
`agenda.db` no diretório do backend. Sem autenticação, sem multi-tenant.
"""

from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from sqlalchemy import String, Text, DateTime, create_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker


def utc_now() -> datetime:
    """
    Instante atual em UTC, com timezone. Substitui `datetime.utcnow()`, que é
    deprecado desde o Python 3.12 e devolvia um datetime ingênuo (sem tz) —
    fonte clássica de erro de fuso ao serializar.

    O SQLite descarta o offset ao gravar e devolve datetime ingênuo na leitura,
    então o valor persistido continua sendo o mesmo de antes: hora de parede
    em UTC. A diferença aparece no `.isoformat()`, que agora sai com `+00:00`
    e é interpretado corretamente pelo `new Date()` do frontend.
    """
    return datetime.now(timezone.utc)


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
    dof: Mapped[Optional[str]] = mapped_column(String)  # código da disciplina no portal
    course_id: Mapped[Optional[str]] = mapped_column(String)   # id do curso no Moodle
    course_url: Mapped[Optional[str]] = mapped_column(String)  # link direto pra disciplina
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=utc_now, onupdate=utc_now
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
    # ID do evento correspondente no Google Calendar. Preenchido após uma
    # sincronização bem-sucedida; é o que faz o frontend saber que o evento
    # já foi sincronizado (antes disso o flag `synced` era sempre falso e
    # re-sincronizar duplicava o evento na agenda do usuário).
    google_event_id: Mapped[Optional[str]] = mapped_column(String)
    last_seen_at: Mapped[datetime] = mapped_column(
        DateTime, default=utc_now, onupdate=utc_now
    )


class DoneEvent(Base):
    """Marcação local de evento concluído pelo aluno."""

    __tablename__ = "done_events"

    stable_key: Mapped[str] = mapped_column(String, primary_key=True)
    completed_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)


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
    Chave derivada do conteúdo do evento. Fallback para eventos sem id próprio.

    Frágil por natureza: renomear a atividade ou mudar a data gera uma chave
    nova, e o evento perde a marcação de concluído e o vínculo com o Google
    Calendar. Prefira `event_key()`.
    """
    return f"{subject}|{date}|{title}".lower().strip()


def moodle_event_key(moodle_event_id: int | str) -> str:
    """Chave a partir do id do evento no Moodle — imutável."""
    return f"moodle:{moodle_event_id}"


def event_key(event: dict) -> str:
    """
    Identidade de um evento, preferindo o id do Moodle.

    Só cai no hash de conteúdo quando o evento não tem id — o que hoje não
    acontece, já que tudo vem do calendário, mas mantém o caminho aberto para
    eventos de outra origem.
    """
    moodle_id = event.get("moodle_event_id")
    if moodle_id:
        return moodle_event_key(moodle_id)
    return stable_event_key(event["subject"], event["date"], event["title"])


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
