"""
Camada de persistência do UNOESC Agenda — SQLite + SQLAlchemy.

A aplicação é **multi-tenant**: um único banco atende vários alunos, e cada
linha de cache (disciplinas, eventos, concluídos, metadados) carrega o
`user_id` do dono. Toda leitura precisa filtrar por ele — ver `repository.py`,
onde nenhuma query é global.

Antes disso o app era local/single-user, com uma instalação por aluno. O que
tornou a mudança obrigatória foi hospedar numa URL pública: sem `user_id`, o
segundo aluno a logar sobrescreveria e enxergaria a agenda do primeiro.
"""

import logging
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from sqlalchemy import String, Text, DateTime, Integer, Float, create_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker

logger = logging.getLogger("agenda.db")


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


def new_id() -> str:
    """Identificador opaco para novas linhas (usuários)."""
    return uuid.uuid4().hex


# Caminho do banco. Em produção aponta para o volume persistente do provedor
# (Fly.io/Railway) via `DATABASE_PATH` — sem volume, o arquivo é recriado a
# cada deploy e todo mundo perde a agenda.
_env_path = os.getenv("DATABASE_PATH")
DB_PATH = Path(_env_path) if _env_path else Path(__file__).resolve().parent.parent / "agenda.db"
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

class User(Base):
    """
    Um aluno. Criado no primeiro login bem-sucedido no Moodle — não existe
    cadastro próprio, e o Moodle continua sendo a única autoridade de senha.
    """

    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=new_id)
    moodle_username: Mapped[str] = mapped_column(String, unique=True, nullable=False, index=True)
    plan: Mapped[str] = mapped_column(String, nullable=False, default="free")  # free | pro
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)
    last_login_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)

    # Cota do assistente de organização. `ai_quota_period` guarda o mês
    # corrente ("2026-08"); quando vira o mês, o contador zera na primeira
    # chamada — evita precisar de job agendado só para resetar contador.
    ai_calls_used: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    ai_quota_period: Mapped[Optional[str]] = mapped_column(String)

    # Chave do endereço .ics que o Google/Apple Calendar assina. É um segredo
    # de leitura: quem tem o endereço vê a agenda, e por isso ele nasce só
    # quando o aluno pede e pode ser trocado sem mexer na senha. Fica em claro
    # porque o servidor precisa comparar com o que veio na URL — o valor não
    # abre sessão nem dá acesso a mais nada além dos eventos.
    ics_token: Mapped[Optional[str]] = mapped_column(String, unique=True, index=True)


class AppSession(Base):
    """
    Sessão de aplicação: troca a senha do Moodle por um token opaco.

    Persistida em banco (antes era um `dict` de processo) por dois motivos:
    todo deploy deslogava todo mundo, e com mais de uma instância metade das
    requisições caía em 401.

    Guarda o token **hasheado**: quem ler o banco não consegue se passar por um
    usuário logado. A senha vai cifrada — ver `crypto.py` para o porquê de ela
    precisar continuar recuperável.
    """

    __tablename__ = "sessions"

    token_hash: Mapped[str] = mapped_column(String, primary_key=True)
    user_id: Mapped[str] = mapped_column(String, nullable=False, index=True)
    password_enc: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)
    last_used_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)


class Subject(Base):
    """Cache do conteúdo bruto extraído de cada disciplina, por aluno."""

    __tablename__ = "subjects"

    user_id: Mapped[str] = mapped_column(String, primary_key=True)
    name: Mapped[str] = mapped_column(String, primary_key=True)
    content: Mapped[Optional[str]] = mapped_column(Text)
    dof: Mapped[Optional[str]] = mapped_column(String)  # código da disciplina no portal
    course_id: Mapped[Optional[str]] = mapped_column(String)   # id do curso no Moodle
    course_url: Mapped[Optional[str]] = mapped_column(String)  # link direto pra disciplina
    # Início e fim do componente no Moodle, epoch em segundos. É o único dado
    # que diz a qual semestre a disciplina pertence — a matrícula continua
    # ativa depois do fim, então sem isso a lista mistura os períodos.
    start_date: Mapped[Optional[int]] = mapped_column(Integer)
    end_date: Mapped[Optional[int]] = mapped_column(Integer)
    # Nota final do relatório de notas do Moodle, na escala 0–100 que ele usa.
    # Nulo enquanto o professor não lança nada — ausência não é zero.
    final_grade: Mapped[Optional[float]] = mapped_column(Float)
    # A nota anterior e quando a mudança foi percebida. Mesma ideia do
    # `previous_date` do evento: o aluno abre o Moodle várias vezes por semana
    # só para ver se saiu nota, e é a agenda que pode responder isso por ele.
    # `previous_grade` nulo com `grade_changed_at` preenchido é o caso mais
    # comum — a primeira nota da disciplina, que não tinha valor anterior.
    previous_grade: Mapped[Optional[float]] = mapped_column(Float)
    grade_changed_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=utc_now, onupdate=utc_now
    )


class Event(Base):
    """
    Cache dos eventos extraídos. `stable_key` é a chave que sobrevive entre
    scrapings (UUIDs internos do scraper são regerados a cada run); junto com
    `user_id` forma a identidade da linha.
    """

    __tablename__ = "events"

    user_id: Mapped[str] = mapped_column(String, primary_key=True)
    stable_key: Mapped[str] = mapped_column(String, primary_key=True)
    title: Mapped[str] = mapped_column(String, nullable=False)
    date: Mapped[str] = mapped_column(String, nullable=False)        # AAAA-MM-DD
    time: Mapped[Optional[str]] = mapped_column(String)              # HH:MM
    description: Mapped[Optional[str]] = mapped_column(Text)
    subject: Mapped[str] = mapped_column(String, nullable=False, index=True)
    type: Mapped[str] = mapped_column(String, nullable=False)        # webconference|deadline|exam|other
    source: Mapped[Optional[str]] = mapped_column(String)            # moodle_calendar
    url: Mapped[Optional[str]] = mapped_column(String)               # link direto pro evento no portal
    # ID do evento correspondente no Google Calendar. Preenchido após uma
    # sincronização bem-sucedida; é o que faz o frontend saber que o evento
    # já foi sincronizado (antes disso o flag `synced` era sempre falso e
    # re-sincronizar duplicava o evento na agenda do usuário).
    google_event_id: Mapped[Optional[str]] = mapped_column(String)
    # Data que este evento tinha antes de o professor mexer, e quando a troca
    # foi percebida. Só existe porque a agenda trocava a data em silêncio: quem
    # já tinha se programado para a data velha não tinha como saber. A
    # comparação é possível porque `stable_key` sobrevive à mudança de data —
    # vem do id do evento no Moodle, não do conteúdo.
    previous_date: Mapped[Optional[str]] = mapped_column(String)   # AAAA-MM-DD
    date_changed_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    # Quanto a avaliação vale, quando o PDF da disciplina diz ("Peso: 4"). Só o
    # garimpo de PDF preenche: o calendário do Moodle não carrega peso.
    weight: Mapped[Optional[float]] = mapped_column(Float)
    last_seen_at: Mapped[datetime] = mapped_column(
        DateTime, default=utc_now, onupdate=utc_now
    )


class DoneEvent(Base):
    """Marcação de evento concluído pelo aluno."""

    __tablename__ = "done_events"

    user_id: Mapped[str] = mapped_column(String, primary_key=True)
    stable_key: Mapped[str] = mapped_column(String, primary_key=True)
    completed_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)


class CourseItem(Base):
    """
    Item publicado na sala da disciplina (arquivo, fórum, tarefa), por aluno.

    Existe para responder "o que apareceu desde a última vez que olhei". No
    curso presencial esse é o *único* sinal que a sala emite: 58 arquivos e
    nenhum evento de calendário — sem isto a agenda não tem o que mostrar e o
    aluno volta a abrir o Moodle disciplina por disciplina.

    `baseline` marca o que já estava lá quando o aluno chegou. Sem essa
    distinção o primeiro scrape anunciaria o semestre inteiro como novidade, e
    a tela nasceria pedindo para ser ignorada.
    """

    __tablename__ = "course_items"

    user_id: Mapped[str] = mapped_column(String, primary_key=True)
    # `cmid` é o id do módulo no Moodle: único dentro da instância e estável
    # enquanto o professor não apagar o item.
    cmid: Mapped[str] = mapped_column(String, primary_key=True)
    subject: Mapped[str] = mapped_column(String, nullable=False, index=True)
    name: Mapped[str] = mapped_column(String, nullable=False)
    modname: Mapped[Optional[str]] = mapped_column(String)  # resource | forum | ...
    url: Mapped[Optional[str]] = mapped_column(String)
    first_seen_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)
    baseline: Mapped[int] = mapped_column(Integer, nullable=False, default=0)


class PushSubscription(Base):
    """
    Inscrição de notificação push de um aluno — uma por navegador/aparelho.

    O `endpoint` é a URL que o navegador dá ao autorizar; é ela que o servidor
    chama para entregar a mensagem, e é única por aparelho, então serve de
    chave primária. `p256dh` e `auth` são as chaves com que o navegador decifra
    a mensagem: o conteúdo trafega cifrado ponta a ponta, e nem o Google (que
    roteia o push no Android) consegue ler.

    `password_enc` é a parte que não é óbvia. Para avisar "saiu nota" com o app
    fechado, o servidor precisa consultar o Moodle sozinho — e a senha da
    sessão morre em 8h de inatividade, ou seja, nunca está lá às 7h da manhã.
    Guardar aqui estende a retenção da senha de "enquanto a sessão dura" para
    "enquanto o aluno quiser receber notificação". É por isso que o aviso está
    escrito na tela de opt-in e a linha é apagada assim que ele desliga. Cifrada
    com a mesma chave da sessão — ver `crypto.py`.

    `falhas` conta rejeições seguidas do serviço de push. Inscrição de aparelho
    formatado responde 404/410 para sempre; sem esse contador o servidor
    tentaria entregar todo dia, para sempre.
    """

    __tablename__ = "push_subscriptions"

    endpoint: Mapped[str] = mapped_column(String, primary_key=True)
    user_id: Mapped[str] = mapped_column(String, nullable=False, index=True)
    p256dh: Mapped[str] = mapped_column(String, nullable=False)
    auth: Mapped[str] = mapped_column(String, nullable=False)
    password_enc: Mapped[Optional[str]] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)
    last_sent_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    falhas: Mapped[int] = mapped_column(Integer, nullable=False, default=0)


class Meta(Base):
    """Pares chave/valor por aluno (último scrape, versão, etc.)."""

    __tablename__ = "meta"

    user_id: Mapped[str] = mapped_column(String, primary_key=True)
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
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    _drop_pre_multitenant_tables()
    Base.metadata.create_all(bind=engine)
    _run_lightweight_migrations()


# Tabelas de cache que passaram a ter `user_id` na chave primária.
_TENANT_TABLES = (
    "subjects", "events", "done_events", "meta", "course_items",
    "push_subscriptions",
)


def _drop_pre_multitenant_tables() -> None:
    """
    Descarta as tabelas de cache do formato antigo (sem `user_id`).

    `ALTER TABLE` do SQLite não redefine chave primária, então não há migração
    incremental possível aqui. Descartar é seguro porque tudo nessas tabelas é
    reconstruído pelo próximo `/api/scrape` — a única perda real são as
    marcações de "concluído" de um banco pré-multi-tenant, que por definição
    pertenciam a uma instalação de um usuário só.
    """
    from sqlalchemy import inspect, text

    inspector = inspect(engine)
    existing = set(inspector.get_table_names())
    legacy = [
        table for table in _TENANT_TABLES
        if table in existing
        and "user_id" not in {col["name"] for col in inspector.get_columns(table)}
    ]
    if not legacy:
        return

    logger.warning(
        "Banco no formato antigo (single-user) detectado. Recriando %s com "
        "suporte a múltiplos usuários — faça login e atualize para repopular.",
        ", ".join(legacy),
    )
    with engine.begin() as conn:
        for table in legacy:
            conn.execute(text(f'DROP TABLE "{table}"'))


def _run_lightweight_migrations() -> None:
    """
    Migração pragmática: detecta colunas declaradas no modelo que faltam na
    tabela e adiciona via ALTER TABLE.

    Funciona porque (1) só adicionamos colunas — nunca renomeamos/removemos —
    e (2) SQLite suporta `ALTER TABLE ... ADD COLUMN` sem reescrever a tabela.
    Mudanças de chave primária não passam por aqui: veja
    `_drop_pre_multitenant_tables()`.
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
                    logger.warning(
                        "Coluna '%s' em '%s' é NOT NULL sem default. Apague o banco "
                        "(%s) para recriar do zero.",
                        column.name,
                        table.name,
                        DB_PATH,
                    )
                    continue
                if column.default is not None and getattr(column.default, "is_scalar", False):
                    default_value = column.default.arg
                    if isinstance(default_value, str):
                        default_value = f"'{default_value}'"
                    pieces.append(f"DEFAULT {default_value}")

                stmt = " ".join(pieces)
                logger.info("Migração: %s", stmt)
                conn.execute(text(stmt))
