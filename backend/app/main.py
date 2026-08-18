"""
Ponto de entrada da aplicação FastAPI — UNOESC Agenda.

Configura o app, CORS, os endpoints REST sob `/api` e — em produção — a
entrega do frontend já compilado. Um processo só serve as duas coisas: um
deploy, um domínio, sem CORS entre front e back.
"""

import asyncio
import os
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path
from typing import Optional

from fastapi import Depends, FastAPI, File, Form, Header, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import PlainTextResponse
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException
from pydantic import BaseModel

from app import assistant
from app import observability
from app import ratelimit
from app import repository as repo
from app import session as app_session
from app.calendar_sync import CalendarSyncService
from app.icalendar import build_calendar
from app.database import init_db, utc_now
from app.moodle import TZ_BR, MoodleClient, clear_session_cache
from app.observability import mensagem_amigavel, registrar_falha

# ---------------------------------------------------------------------------
# Modelos de Requisição e Resposta (Pydantic)
# ---------------------------------------------------------------------------

class LoginCredentials(BaseModel):
    """Credenciais do Moodle. Enviadas uma única vez, em /api/login."""
    username: str
    password: str


class LoginResponse(BaseModel):
    """Token que substitui as credenciais nas chamadas seguintes."""
    token: str


class SubjectModel(BaseModel):
    """Representa uma disciplina com seu conteúdo extraído."""
    id: str
    name: str
    content: Optional[str] = None
    # Epoch em segundos. O frontend usa `end_date` para separar o semestre
    # corrente das disciplinas já encerradas.
    start_date: Optional[int] = None
    end_date: Optional[int] = None
    # Nota final na escala 0–100 do Moodle; nula enquanto nada foi lançado.
    final_grade: Optional[float] = None


class AcademicEvent(BaseModel):
    """Evento acadêmico vindo do calendário do Moodle."""
    id: str
    title: str
    date: str                # ISO 8601 (ex: "2025-06-10")
    time: Optional[str] = None  # ex: "19:00"
    description: str
    subject: str
    type: str                # webconference | deadline | exam | other
    synced: Optional[bool] = False
    url: Optional[str] = None  # link direto pra atividade no Moodle
    # Identidade do evento, calculada no backend a partir do id do Moodle.
    # O frontend usa este valor em vez de recalcular a chave por conta própria
    # — antes as duas fórmulas precisavam ser mantidas idênticas na mão.
    stable_key: Optional[str] = None
    event_type: Optional[str] = None  # due | open | close
    module: Optional[str] = None      # assign | quiz | ...


class ScrapeResponse(BaseModel):
    """Resposta do endpoint /api/scrape."""
    subjects: list[SubjectModel]
    calendar_events: list[AcademicEvent] = []


class SyncCalendarRequest(BaseModel):
    """Requisição para o endpoint /api/sync-calendar."""
    events: list[AcademicEvent]
    google_token: str        # Token OAuth2 do usuário para o Google Calendar


class SyncCalendarResponse(BaseModel):
    """Resposta do endpoint /api/sync-calendar."""
    synced_event_ids: list[str]
    calendar_links: list[str]


class CacheResponse(BaseModel):
    """
    Resposta do endpoint /api/cache.
    Permite o frontend abrir o app sem refazer o scraping se já houver
    dados no banco.
    """
    subjects: list[SubjectModel]
    events: list[AcademicEvent]
    done_keys: list[str]
    last_scraped_at: Optional[str] = None  # ISO 8601, UTC


class DoneEventRequest(BaseModel):
    """Marcar/desmarcar evento concluído."""
    stable_key: str


class DoneEventsResponse(BaseModel):
    done_keys: list[str]


class MeResponse(BaseModel):
    """Quem está logado, em que plano, e quanto resta do assistente."""
    username: str
    plan: str
    assistant_available: bool
    assistant_used: int
    assistant_limit: int


class MoodleProfile(BaseModel):
    """O cadastro do aluno como o Moodle o guarda."""
    moodle_id: Optional[int] = None
    fullname: str = ""
    firstname: str = ""
    lastname: str = ""
    username: str = ""
    email: str = ""
    department: str = ""
    institution: str = ""
    city: str = ""
    country: str = ""
    timezone: str = ""
    first_access: Optional[str] = None
    last_access: Optional[str] = None
    avatar: Optional[str] = None


class ProfileStats(BaseModel):
    """O que a agenda do aluno diz sobre ele — contado no banco, não no Moodle."""
    subjects: int
    events_total: int
    events_upcoming: int
    events_done: int
    next_event_title: Optional[str] = None
    next_event_date: Optional[str] = None
    next_event_time: Optional[str] = None
    next_event_subject: Optional[str] = None
    last_scraped_at: Optional[str] = None


class ProfileResponse(BaseModel):
    """
    Perfil = cadastro no Moodle + conta no app + resumo da agenda.

    `moodle` vem nulo quando o Moodle não responde; `moodle_error` explica. O
    resto da tela não depende dele e continua de pé.
    """
    account_username: str
    plan: str
    member_since: Optional[str] = None
    last_login_at: Optional[str] = None
    moodle: Optional[MoodleProfile] = None
    moodle_error: Optional[str] = None
    stats: ProfileStats


class StatusLinha(BaseModel):
    """Uma linha da tabela de status do envio, como o Moodle a mostra."""
    label: str
    value: str


class ArquivoNoRascunho(BaseModel):
    """Arquivo que já está no envio desta tarefa."""
    name: str
    size: int


class SubmissionInfo(BaseModel):
    """O que esta tarefa aceita hoje — e por que não, quando não aceita."""
    can_submit: bool
    reason: Optional[str] = None
    accepts_files: bool = False
    accepts_text: bool = False
    max_files: int = 0
    max_file_mb: int = 0
    # Salvar manda junto o que já estava anexado — a tela precisa mostrar.
    existing_files: list[ArquivoNoRascunho] = []
    # Já entregue: a tela troca o formulário por um aviso do que o Moodle diz.
    submitted: bool = False
    draft: bool = False
    submitted_label: Optional[str] = None
    submitted_at: Optional[str] = None
    status: list[StatusLinha] = []


class SubmissionResult(BaseModel):
    """O resultado lido de volta no Moodle depois de salvar."""
    saved: bool
    status: list[StatusLinha] = []
    moodle_url: str


class AssistantMessage(BaseModel):
    role: str  # "user" | "assistant"
    content: str


class AssistantRequest(BaseModel):
    """Pergunta de organização + histórico da conversa."""
    messages: list[AssistantMessage]


class AssistantResponse(BaseModel):
    response: str
    used: int
    limit: int


# ---------------------------------------------------------------------------
# Inicialização do app FastAPI
# ---------------------------------------------------------------------------

@asynccontextmanager
async def lifespan(_app: FastAPI):
    """
    Ciclo de vida do app. Substitui `@app.on_event("startup")`, deprecado no
    FastAPI. O que vem antes do `yield` roda na subida; depois, no shutdown.
    """
    observability.setup_logging()
    init_db()
    removidas = app_session.purge_expired()
    if removidas:
        observability.logger.info("%d sessão(ões) expirada(s) removida(s).", removidas)
    observability.logger.info("API pronta (APP_ENV=%s).", os.getenv("APP_ENV", "development"))
    yield


app = FastAPI(
    title="UNOESC Agenda API",
    description="API para extração e organização de atividades acadêmicas da UNOESC.",
    version="2.0.0",
    lifespan=lifespan,
)

# Em produção o frontend é servido por este mesmo processo (mesma origem), e
# não há CORS a liberar. `ALLOWED_ORIGINS` existe para o desenvolvimento, onde
# o Vite roda em outra porta, e para um eventual front hospedado à parte.
# Endereço público do app, usado para montar o link do calendário assinável.
# Em desenvolvimento o backend responde na 8880; em produção tudo sai do mesmo
# domínio, então o padrão é o de produção.
PUBLIC_BASE_URL = os.getenv("PUBLIC_BASE_URL", "https://unoesc-agenda.fly.dev").rstrip("/")

_origins = [o.strip() for o in os.getenv("ALLOWED_ORIGINS", "").split(",") if o.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=_origins,
    allow_origin_regex=None if _origins else r"http://localhost:51\d{2}",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Uma linha de log por requisição, e a última rede de proteção contra exceção
# não tratada — sem ela o erro sairia como traceback no corpo da resposta.
app.middleware("http")(observability.log_requests)

# ---------------------------------------------------------------------------
# Autenticação
# ---------------------------------------------------------------------------

def require_session(
    authorization: Optional[str] = Header(default=None),
) -> app_session.PortalSession:
    """
    Resolve o token do header `Authorization: Bearer <token>`.

    Dependência de **todo** endpoint que lê ou escreve dados do aluno. Num app
    multi-usuário não existe endpoint sem sessão: é a sessão que diz de quem
    são as linhas a devolver.
    """
    token = ""
    if authorization and authorization.lower().startswith("bearer "):
        token = authorization[len("bearer "):].strip()

    session = app_session.get(token)
    if session is None:
        raise HTTPException(
            status_code=401,
            detail="Sessão expirada ou inválida. Faça login novamente.",
        )
    return session


@app.post("/api/login", response_model=LoginResponse)
async def login(credentials: LoginCredentials):
    """
    Valida as credenciais no Moodle e devolve um token de sessão. Cria o
    usuário no primeiro acesso.

    É o único endpoint que recebe a senha. A partir daqui o frontend usa o
    token, e a senha não volta a trafegar nem fica guardada no navegador.
    """
    chave = credentials.username.strip().lower()

    espera = ratelimit.seconds_until_allowed(chave)
    if espera:
        raise HTTPException(
            status_code=429,
            detail=f"Muitas tentativas de login. Tente de novo em {espera // 60 + 1} min.",
            headers={"Retry-After": str(espera)},
        )

    try:
        with MoodleClient() as moodle:
            await asyncio.to_thread(
                moodle.login, credentials.username, credentials.password
            )
    except PermissionError as exc:
        # Credencial recusada: a mensagem vem do nosso próprio código e é
        # escrita para o aluno ("usuário ou senha incorretos").
        ratelimit.register_failure(chave)
        raise HTTPException(status_code=401, detail=str(exc)) from exc
    except Exception as exc:
        codigo = registrar_falha("login no Moodle", exc)
        raise HTTPException(
            status_code=502, detail=mensagem_amigavel(codigo, "entrar no Moodle")
        ) from exc

    ratelimit.reset(chave)
    return LoginResponse(token=app_session.create(credentials.username, credentials.password))


@app.post("/api/logout", status_code=200)
async def logout(authorization: Optional[str] = Header(default=None)):
    """Encerra a sessão do token informado. Idempotente."""
    if authorization and authorization.lower().startswith("bearer "):
        app_session.revoke(authorization[len("bearer "):].strip())
    return {"status": "ok"}


@app.get("/api/me", response_model=MeResponse)
async def me(session: app_session.PortalSession = Depends(require_session)):
    """Dados da conta logada — plano e saldo do assistente."""
    with repo.get_session() as db:
        user = repo.get_user(db, session.user_id)
        if user is None:
            raise HTTPException(status_code=401, detail="Conta não encontrada.")
        quota = assistant.current_quota(user)
        return MeResponse(
            username=user.moodle_username,
            plan=user.plan,
            assistant_available=assistant.is_configured(),
            assistant_used=quota.used,
            assistant_limit=quota.limit,
        )


@app.get("/api/profile", response_model=ProfileResponse)
async def profile(session: app_session.PortalSession = Depends(require_session)):
    """
    Perfil do aluno: o cadastro que o Moodle guarda, mais a conta no app e um
    resumo da agenda dele.

    Tudo é lido a partir da sessão — o `user_id` para as contagens no banco e a
    própria sessão do Moodle para o cadastro. Não existe parâmetro de quem ver.

    O Moodle é consultado a cada visita em vez de guardado: nome, e-mail e
    departamento mudam pela secretaria, sem o app saber, e uma cópia velha aqui
    seria mais confusa do que útil. Se ele não responder, a tela abre com o que
    o app já sabe e diz o que faltou.
    """
    with repo.get_session() as db:
        user = repo.get_user(db, session.user_id)
        if user is None:
            raise HTTPException(status_code=401, detail="Conta não encontrada.")

        eventos = repo.list_events(db, session.user_id)
        concluidos = set(repo.list_done_keys(db, session.user_id))
        stats = ProfileStats(
            subjects=len(repo.list_subjects(db, session.user_id)),
            events_total=len(eventos),
            events_upcoming=0,
            events_done=len([e for e in eventos if e.stable_key in concluidos]),
            last_scraped_at=repo.get_meta(db, session.user_id, "last_scraped_at"),
        )

        # "Futuro" é do dia de hoje em diante, pelo calendário de Brasília: um
        # prazo que vence hoje às 23h59 ainda conta como pendente.
        hoje = datetime.now(TZ_BR).strftime("%Y-%m-%d")
        pendentes = sorted(
            (e for e in eventos
             if e.stable_key not in concluidos and (e.date or "") >= hoje),
            key=lambda e: (e.date or "", e.time or "00:00"),
        )
        stats.events_upcoming = len(pendentes)
        if pendentes:
            proximo = pendentes[0]
            stats.next_event_title = proximo.title
            stats.next_event_date = proximo.date
            stats.next_event_time = proximo.time
            stats.next_event_subject = proximo.subject

        resposta = ProfileResponse(
            account_username=user.moodle_username,
            plan=user.plan,
            member_since=user.created_at.isoformat() if user.created_at else None,
            last_login_at=user.last_login_at.isoformat() if user.last_login_at else None,
            stats=stats,
        )

    try:
        with MoodleClient() as moodle:
            await asyncio.to_thread(moodle.login, session.username, session.password)
            dados = await asyncio.to_thread(moodle.profile)
            resposta.moodle = MoodleProfile(**dados)
    except PermissionError as exc:
        resposta.moodle_error = str(exc)
    except Exception as exc:
        codigo = registrar_falha(f"perfil no Moodle (user={session.user_id})", exc)
        resposta.moodle_error = mensagem_amigavel(codigo, "buscar seu cadastro no Moodle")

    return resposta


@app.delete("/api/account")
async def delete_account(session: app_session.PortalSession = Depends(require_session)):
    """
    Apaga a conta e todos os dados do aluno — cache, concluídos e credenciais.

    Direito de exclusão da LGPD. Sem volta: o próximo login recria a conta do
    zero e refaz o scrape.
    """
    with repo.get_session() as db:
        repo.delete_user(db, session.user_id)
        db.commit()
    return {"status": "ok", "message": "Conta e dados apagados."}


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@app.get("/api/health/live")
async def liveness():
    """
    "O processo está de pé?" — nada além disso.

    É o alvo do health check do Fly (`fly.toml`), que roda a cada 30s. Por isso
    não toca no Moodle nem no banco: um check que faz requisição externa vira
    milhares de acessos por dia ao servidor da UNOESC sem ninguém usar o app.
    O diagnóstico completo é o `/api/health` abaixo, chamado sob demanda.
    """
    return {"status": "ok"}


@app.get("/api/health")
async def health_check():
    """
    Diagnóstico das dependências externas. Útil para identificar rapidamente
    o que está faltando configurar ao subir o app pela primeira vez.
    """
    checks = {
        "api": True,
        # A chave de IA nunca foi obrigatória: os eventos vêm estruturados do
        # calendário do Moodle, sem LLM. Ela só serve ao assistente de
        # organização, que é opcional.
        "ai_key_optional": assistant.is_configured(),
        "moodle": False,
        "database": False,
    }
    hints: list[str] = []

    # Moodle acessível (não valida credencial — só se o serviço responde)
    try:
        import httpx as _httpx
        from app.moodle import MOODLE_BASE
        resp = await asyncio.to_thread(
            lambda: _httpx.get(f"{MOODLE_BASE}/login/index.php", timeout=10.0)
        )
        checks["moodle"] = resp.status_code == 200
    except Exception:
        checks["moodle"] = False

    # Banco
    try:
        from sqlalchemy import text
        with repo.get_session() as session:
            session.execute(text("SELECT 1"))
            checks["database"] = True
    except Exception:
        checks["database"] = False

    if not checks["ai_key_optional"]:
        hints.append(
            "Chave de IA não configurada — a agenda funciona normalmente, "
            "só o assistente de organização fica indisponível."
        )
    if not checks["moodle"]:
        hints.append(
            "Sem resposta do Moodle (on.unoesc.edu.br). Verifique sua conexão."
        )

    return {
        "status": "ok" if all(checks.values()) else "warn",
        "checks": checks,
        "hints": hints,
    }


@app.post("/api/scrape", response_model=ScrapeResponse)
async def scrape_portal(session: app_session.PortalSession = Depends(require_session)):
    """
    Extrai disciplinas + calendário do Moodle e persiste tudo no banco, sob o
    `user_id` da sessão.

    Usa as credenciais guardadas na sessão do token — nada de senha no corpo.
    """
    try:
        # O cliente é síncrono; roda fora do event loop do FastAPI.
        with MoodleClient() as moodle:
            result = await asyncio.to_thread(
                moodle.run, session.username, session.password
            )

        events = result.get("calendar_events", [])

        with repo.get_session() as db:
            repo.upsert_subjects(db, session.user_id, result["subjects"])
            if events:
                # Preenche `stable_key` em cada evento — o frontend usa esse
                # valor para marcar concluído.
                repo.upsert_events(db, session.user_id, events)
            repo.set_meta(db, session.user_id, "last_scraped_at", utc_now().isoformat())
            synced_keys = set(repo.list_synced_keys(db, session.user_id))
            db.commit()

        for ev in events:
            ev["synced"] = ev.get("stable_key") in synced_keys

        return ScrapeResponse(subjects=result["subjects"], calendar_events=events)
    except PermissionError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc
    except Exception as exc:
        codigo = registrar_falha(f"scrape do Moodle (user={session.user_id})", exc)
        raise HTTPException(
            status_code=502, detail=mensagem_amigavel(codigo, "buscar sua agenda no Moodle")
        ) from exc


@app.get("/api/cache", response_model=CacheResponse)
async def get_cache(session: app_session.PortalSession = Depends(require_session)):
    """
    Retorna disciplinas + eventos persistidos do último scraping bem-sucedido
    **do aluno logado**, junto com a lista de eventos marcados como concluídos.
    """
    with repo.get_session() as db:
        subjects = [
            SubjectModel(
                id=s.name,
                name=s.name,
                content=s.content,
                start_date=s.start_date,
                end_date=s.end_date,
                final_grade=s.final_grade,
            )
            for s in repo.list_subjects(db, session.user_id)
        ]
        events = [
            AcademicEvent(
                id=e.stable_key,
                stable_key=e.stable_key,
                title=e.title,
                date=e.date,
                time=e.time,
                description=e.description or "",
                subject=e.subject,
                type=e.type,
                synced=e.google_event_id is not None,
                url=e.url,
            )
            for e in repo.list_events(db, session.user_id)
        ]
        done_keys = repo.list_done_keys(db, session.user_id)
        last_scraped_at = repo.get_meta(db, session.user_id, "last_scraped_at")

    return CacheResponse(
        subjects=subjects,
        events=events,
        done_keys=done_keys,
        last_scraped_at=last_scraped_at,
    )


@app.get("/api/done-events", response_model=DoneEventsResponse)
async def list_done_events(session: app_session.PortalSession = Depends(require_session)):
    """Lista as `stable_keys` de todos os eventos marcados como concluídos."""
    with repo.get_session() as db:
        return DoneEventsResponse(done_keys=repo.list_done_keys(db, session.user_id))


@app.post("/api/done-events", response_model=DoneEventsResponse, status_code=200)
async def mark_event_done(
    request: DoneEventRequest,
    session: app_session.PortalSession = Depends(require_session),
):
    """Marca um evento como concluído (idempotente)."""
    with repo.get_session() as db:
        repo.mark_done(db, session.user_id, request.stable_key)
        db.commit()
        return DoneEventsResponse(done_keys=repo.list_done_keys(db, session.user_id))


@app.delete("/api/done-events", response_model=DoneEventsResponse)
async def unmark_event_done(
    request: DoneEventRequest,
    session: app_session.PortalSession = Depends(require_session),
):
    """Desmarca um evento como concluído."""
    with repo.get_session() as db:
        repo.unmark_done(db, session.user_id, request.stable_key)
        db.commit()
        return DoneEventsResponse(done_keys=repo.list_done_keys(db, session.user_id))


class CalendarFeedResponse(BaseModel):
    """Endereço da assinatura de calendário do aluno."""
    url: str


@app.get("/api/calendar-feed", response_model=CalendarFeedResponse)
async def get_calendar_feed(
    session: app_session.PortalSession = Depends(require_session),
):
    """
    Endereço que o aluno cola no Google Agenda, no Apple Calendário ou no
    Outlook. A chave nasce aqui, na primeira vez que ele pede.
    """
    with repo.get_session() as db:
        token = repo.get_or_create_ics_token(db, session.user_id)
        db.commit()
    return CalendarFeedResponse(url=f"{PUBLIC_BASE_URL}/calendario/{token}.ics")


@app.post("/api/calendar-feed/reset", response_model=CalendarFeedResponse)
async def reset_calendar_feed(
    session: app_session.PortalSession = Depends(require_session),
):
    """Troca a chave — o endereço antigo para de responder na hora."""
    with repo.get_session() as db:
        token = repo.reset_ics_token(db, session.user_id)
        db.commit()
    return CalendarFeedResponse(url=f"{PUBLIC_BASE_URL}/calendario/{token}.ics")


@app.get("/calendario/{token}.ics", response_class=PlainTextResponse)
async def calendar_feed(token: str):
    """
    A agenda do aluno em iCalendar, buscada pelo cliente de calendário dele.

    Fora de `/api` e sem sessão de propósito: quem faz esta requisição é o
    servidor do Google ou do Apple, que não tem como carregar um token de
    sessão. A chave da URL é a credencial — comprida, aleatória, trocável pelo
    aluno e boa só para ler os eventos.

    Os eventos saem do cache: este endereço não dispara busca no Moodle, que
    precisaria da senha e demoraria mais do que um cliente de calendário
    espera.
    """
    with repo.get_session() as db:
        user = repo.get_user_by_ics_token(db, token)
        if user is None:
            # 404 e não 403: um endereço inválido não deve confirmar que
            # existem endereços válidos parecidos.
            raise HTTPException(status_code=404, detail="Calendário não encontrado.")
        eventos = repo.list_events(db, user.id)
        ics = build_calendar(eventos)

    return PlainTextResponse(
        ics,
        media_type="text/calendar; charset=utf-8",
        headers={"Content-Disposition": 'inline; filename="agenda-unoesc.ics"'},
    )


@app.delete("/api/cache")
async def clear_cache(session: app_session.PortalSession = Depends(require_session)):
    """
    Apaga o cache do aluno (subjects, events, meta). Mantém done_events para
    não perder o progresso ao limpar.

    Encerra também as sessões abertas dele — limpar o cache significa
    recomeçar do zero, inclusive o login. As sessões dos outros alunos não são
    tocadas.
    """
    with repo.get_session() as db:
        repo.clear_cache(db, session.user_id)
        db.commit()
    clear_session_cache()
    app_session.revoke_for_user(session.user_id)
    return {"status": "ok", "message": "Cache limpo. Faça login para recarregar os dados."}


@app.post("/api/assistant", response_model=AssistantResponse)
async def ask_assistant(
    request: AssistantRequest,
    session: app_session.PortalSession = Depends(require_session),
):
    """
    Assistente de organização: prioridades, plano de estudo, acúmulo de prazos.

    Só recebe metadados dos eventos já em cache — título, data, disciplina.
    Não abre atividade no Moodle e não responde questão de prova; ver o prompt
    em `assistant.build_system_prompt`.
    """
    if not request.messages:
        raise HTTPException(status_code=400, detail="Envie ao menos uma mensagem.")

    with repo.get_session() as db:
        user = repo.get_user(db, session.user_id)
        if user is None:
            raise HTTPException(status_code=401, detail="Conta não encontrada.")

        if not assistant.is_configured():
            raise HTTPException(
                status_code=503,
                detail="O assistente não está disponível no momento.",
            )

        try:
            quota = assistant.consume_quota(user)
        except assistant.QuotaExceededError as exc:
            raise HTTPException(status_code=429, detail=str(exc)) from exc

        context = assistant.build_context(db, session.user_id)
        # Grava o consumo antes de chamar o modelo: numa falha da API o aluno
        # perde uma pergunta do saldo, o que é preferível a deixar a chamada
        # sair de graça quando a resposta chega e o commit não.
        db.commit()

    system_prompt = assistant.build_system_prompt(context)
    messages = [{"role": m.role, "content": m.content} for m in request.messages]

    try:
        answer = await asyncio.to_thread(assistant.ask, system_prompt, messages)
    except assistant.AssistantUnavailableError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:
        codigo = registrar_falha("chamada ao assistente", exc)
        raise HTTPException(
            status_code=502, detail=mensagem_amigavel(codigo, "falar com o assistente")
        ) from exc

    return AssistantResponse(response=answer, used=quota.used, limit=quota.limit)


class GradeItem(BaseModel):
    """Uma linha do boletim da disciplina."""
    name: str
    weight: Optional[float] = None   # % do total do curso
    grade: Optional[float] = None    # nota lançada; nulo = ainda não avaliada
    max: Optional[float] = None      # topo da escala do item


class GradesResponse(BaseModel):
    """
    Boletim da disciplina e o que ainda falta para atingir a média.

    `needed` é a nota necessária **no que sobrou**, e vem nulo quando o cálculo
    não é honesto — ver o endpoint.
    """
    items: list[GradeItem]
    current: Optional[float] = None       # média parcial, escala 0–10
    pending_count: int = 0
    pending_weight: float = 0.0           # soma dos pesos sem nota, em %
    needed: Optional[float] = None
    passing_grade: float = 7.0


class GradesRequest(BaseModel):
    subject_name: str


@app.post("/api/grades", response_model=GradesResponse)
async def grades(
    request: GradesRequest,
    session: app_session.PortalSession = Depends(require_session),
):
    """
    Boletim de uma disciplina e a conta de quanto falta para passar.

    A disciplina é resolvida por (user_id, nome) — o nome vem do corpo, mas
    quem não tiver a disciplina no próprio cache recebe 404.

    Sobre o cálculo: o Moodle só dá peso a um item **depois** que a nota é
    lançada, então na maior parte do semestre a soma dos pesos pendentes é
    zero. Nesse caso `needed` volta nulo e a tela diz que ainda não dá para
    calcular, em vez de inventar um número — errar para menos aqui faria o
    aluno relaxar numa prova que decide a aprovação.
    """
    with repo.get_session() as db:
        subject = repo.get_subject(db, session.user_id, request.subject_name)
        if not subject or not subject.course_id:
            raise HTTPException(status_code=404, detail="Disciplina não encontrada.")
        course_id = int(subject.course_id)

    try:
        with MoodleClient() as moodle:
            await asyncio.to_thread(moodle.login, session.username, session.password)
            itens = await asyncio.to_thread(moodle.course_grade_items, course_id)
    except PermissionError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc
    except Exception as exc:
        codigo = registrar_falha(f"boletim (user={session.user_id})", exc)
        raise HTTPException(
            status_code=502, detail=mensagem_amigavel(codigo, "ler suas notas no Moodle")
        ) from exc

    parcial = 0.0
    peso_pendente = 0.0
    pendentes = 0
    for item in itens:
        peso = (item.get("peso") or 0) / 100
        maximo = item.get("maximo") or 10
        nota = item.get("nota")
        if nota is None:
            pendentes += 1
            peso_pendente += item.get("peso") or 0
            continue
        parcial += peso * (nota / maximo) * 10

    passing = float(os.getenv("PASSING_GRADE", "7"))
    needed = None
    if peso_pendente > 0:
        falta = (passing - parcial) / (peso_pendente / 100)
        # Abaixo de zero significa aprovado independente do resto; acima de 10,
        # inalcançável. Os dois casos a tela trata em texto, não em número.
        needed = round(falta, 2)

    return GradesResponse(
        items=[
            GradeItem(
                name=i["nome"], weight=i.get("peso"), grade=i.get("nota"), max=i.get("maximo")
            )
            for i in itens
        ],
        current=round(parcial, 2) if itens else None,
        pending_count=pendentes,
        pending_weight=round(peso_pendente, 2),
        needed=needed,
        passing_grade=passing,
    )


class OpenCourseRequest(BaseModel):
    """Requisição para obter o link de uma atividade/disciplina no Moodle."""
    subject_name: str
    target_url: Optional[str] = None  # URL da atividade específica (mod/quiz, mod/assign, etc.)


@app.post("/api/open-course")
async def open_course(
    request: OpenCourseRequest,
    session: app_session.PortalSession = Depends(require_session),
):
    """
    Devolve o link direto da atividade (ou da disciplina) no Moodle.

    Antes isso gerava um link SSO pelo portal, para o aluno cair já autenticado.
    Com o login direto no Moodle o backend tem sessão, mas o navegador do aluno
    não — e transferir a sessão do servidor para o navegador não seria seguro.
    Então devolvemos a URL real: na primeira vez o Moodle pede login, e o cookie
    dele vale 8 horas. Foi o que permitiu apagar o portal e o Playwright.
    """
    if request.target_url:
        return {"url": request.target_url}

    with repo.get_session() as db:
        subject = repo.get_subject(db, session.user_id, request.subject_name)
        if not subject or not subject.course_url:
            raise HTTPException(
                status_code=404,
                detail="Disciplina não encontrada. Tente atualizar os dados.",
            )
        return {"url": subject.course_url}


@app.get("/api/activity/{stable_key:path}")
async def activity_detail(
    stable_key: str,
    session: app_session.PortalSession = Depends(require_session),
):
    """
    Tudo o que sabemos de uma atividade, para a página de detalhe.

    O evento sai do cache do próprio aluno — a busca é sempre filtrada por
    `user_id`, então um link compartilhado só abre para quem tem aquela
    atividade na própria agenda; para os outros dá 404, não vaza nada.

    O conteúdo da página é buscado no Moodle com a sessão do servidor, o que
    poupa o aluno de logar de novo só para ler o enunciado. Ele é devolvido
    **apenas para esta tela**: `assistant.py` continua montando o contexto com
    data, disciplina e título, e nunca recebe este texto.
    """
    with repo.get_session() as db:
        evento = repo.get_event(db, session.user_id, stable_key)
        if not evento:
            raise HTTPException(status_code=404, detail="Atividade não encontrada.")

        done_keys = set(repo.list_done_keys(db, session.user_id))
        synced_keys = set(repo.list_synced_keys(db, session.user_id))

        detalhe = {
            "stable_key": evento.stable_key,
            "title": evento.title,
            "date": evento.date,
            "time": evento.time,
            "description": evento.description or "",
            "subject": evento.subject,
            "type": evento.type,
            "url": evento.url or "",
            "done": evento.stable_key in done_keys,
            "synced": evento.stable_key in synced_keys,
            "content": None,
            "content_error": None,
        }

    if not detalhe["url"]:
        detalhe["content_error"] = "Esta atividade não tem página própria no Moodle."
        return detalhe

    # A falha aqui não derruba a página: o aluno ainda vê data, título e a
    # descrição do calendário, com um aviso no lugar do enunciado.
    try:
        with MoodleClient() as moodle:
            await asyncio.to_thread(moodle.login, session.username, session.password)
            detalhe["content"] = await asyncio.to_thread(
                moodle.activity_content, detalhe["url"], detalhe["title"]
            )
    except PermissionError as exc:
        detalhe["content_error"] = str(exc)
    except Exception as exc:
        codigo = registrar_falha(f"conteúdo da atividade (user={session.user_id})", exc)
        detalhe["content_error"] = mensagem_amigavel(codigo, "abrir a atividade no Moodle")

    return detalhe


# O limite do Moodle é 250 MB por arquivo. Não é o nosso: a máquina de
# produção tem 512 MB de RAM e atende todo mundo ao mesmo tempo, e o arquivo
# passa inteiro por ela no caminho. 20 MB cobre PDF, DOCX e slides — que é o
# que essas tarefas pedem — e mantém a máquina de pé.
MAX_ARQUIVO_BYTES = 20 * 1024 * 1024
MAX_TOTAL_BYTES = 25 * 1024 * 1024
MAX_ARQUIVOS = 5


async def _tarefa_do_aluno(stable_key: str, user_id: str) -> str:
    """A URL da atividade, se ela for mesmo da agenda deste aluno."""
    with repo.get_session() as db:
        evento = repo.get_event(db, user_id, stable_key)
        if not evento:
            raise HTTPException(status_code=404, detail="Atividade não encontrada.")
        if not evento.url:
            raise HTTPException(
                status_code=409,
                detail="Esta atividade não tem página de envio no Moodle.",
            )
        return evento.url


@app.get("/api/submission/{stable_key:path}", response_model=SubmissionInfo)
async def submission_info(
    stable_key: str,
    session: app_session.PortalSession = Depends(require_session),
):
    """
    O que o Moodle aceita nesta tarefa: arquivo, texto, quantos, e o status de
    envio de agora. Só lê — nada é alterado por aqui.
    """
    url = await _tarefa_do_aluno(stable_key, session.user_id)

    try:
        with MoodleClient() as moodle:
            await asyncio.to_thread(moodle.login, session.username, session.password)
            status = await asyncio.to_thread(moodle.activity_content, url, "")

            # O formulário é a parte que pode faltar: tarefa entregue e travada
            # não abre `editsubmission`, e o Moodle responde isso de formas
            # diferentes conforme o tema. Falhar aqui não pode apagar a tela —
            # o aluno ainda precisa ver que a entrega dele está lá.
            try:
                form = await asyncio.to_thread(moodle.submission_form, url)
            except Exception as exc:
                observability.logger.info(
                    "Formulário de envio indisponível (user=%s): %s", session.user_id, exc
                )
                form = {"can_submit": False,
                        "reason": "O Moodle não abriu o formulário de envio desta tarefa."}
    except PermissionError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc
    except Exception as exc:
        codigo = registrar_falha(f"formulário de envio (user={session.user_id})", exc)
        raise HTTPException(
            status_code=502, detail=mensagem_amigavel(codigo, "abrir o envio no Moodle")
        ) from exc

    linhas = status.get("status") or []
    estado = MoodleClient.submission_state(linhas)

    return SubmissionInfo(
        # Entregue é entregue: mesmo que o Moodle ainda deixe reabrir o
        # formulário, a tela mostra o aviso em vez de convidar a reenviar.
        can_submit=form.get("can_submit", False) and not estado["submitted"],
        reason=form.get("reason"),
        accepts_files=form.get("accepts_files", False),
        accepts_text=form.get("accepts_text", False),
        max_files=min(form.get("max_files") or MAX_ARQUIVOS, MAX_ARQUIVOS),
        max_file_mb=MAX_ARQUIVO_BYTES // (1024 * 1024),
        existing_files=[ArquivoNoRascunho(**f) for f in (form.get("existing_files") or [])],
        submitted=estado["submitted"],
        draft=estado["draft"],
        submitted_label=estado["label"],
        submitted_at=estado["modified"],
        status=[StatusLinha(**linha) for linha in linhas],
    )


@app.post("/api/submission/{stable_key:path}", response_model=SubmissionResult)
async def submit_assignment(
    stable_key: str,
    files: list[UploadFile] = File(default=[]),
    online_text: str = Form(default=""),
    session: app_session.PortalSession = Depends(require_session),
):
    """
    Salva o envio da tarefa como **rascunho** no Moodle.

    O que o app faz aqui é o "salvar mudanças" do Moodle: o arquivo passa a
    aparecer na tarefa e pode ser trocado ou apagado depois. O "enviar para
    avaliação", que na maioria das tarefas o aluno não consegue desfazer,
    continua sendo um clique dele lá dentro — não é o tipo de decisão que um
    app de agenda deve tomar no lugar de alguém.

    O sucesso não é declarado por nós: depois do POST a página é relida e o que
    volta para a tela é a tabela de status que o próprio Moodle mostra.
    """
    url = await _tarefa_do_aluno(stable_key, session.user_id)

    if len(files) > MAX_ARQUIVOS:
        raise HTTPException(
            status_code=413,
            detail=f"Envie no máximo {MAX_ARQUIVOS} arquivos por vez.",
        )

    conteudos: list[tuple[str, bytes]] = []
    total = 0
    for arquivo in files:
        dados = await arquivo.read()
        total += len(dados)
        if len(dados) > MAX_ARQUIVO_BYTES:
            raise HTTPException(
                status_code=413,
                detail=f"“{arquivo.filename}” passa de "
                       f"{MAX_ARQUIVO_BYTES // (1024 * 1024)} MB, o limite do app.",
            )
        if total > MAX_TOTAL_BYTES:
            raise HTTPException(
                status_code=413,
                detail=f"Os arquivos somam mais que "
                       f"{MAX_TOTAL_BYTES // (1024 * 1024)} MB juntos.",
            )
        conteudos.append((arquivo.filename or "arquivo", dados))

    if not conteudos and not online_text.strip():
        raise HTTPException(status_code=400, detail="Não há nada para enviar.")

    try:
        with MoodleClient() as moodle:
            await asyncio.to_thread(moodle.login, session.username, session.password)

            # Tarefa já entregue não se reenvia por acidente: mesmo que o
            # Moodle deixe o formulário aberto, o app para aqui. A tela não
            # oferece o botão, mas a checagem é do backend — é ele que escreve.
            atual = await asyncio.to_thread(moodle.activity_content, url, "")
            estado = MoodleClient.submission_state(atual.get("status") or [])
            if estado["submitted"]:
                raise HTTPException(
                    status_code=409,
                    detail="Esta tarefa já foi enviada para avaliação no Moodle. "
                           "Para trocar o envio, use o Moodle.",
                )

            # O `itemid` do rascunho nasce neste GET e vale para os POSTs
            # seguintes; por isso o formulário é aberto agora, e não na tela.
            form = await asyncio.to_thread(moodle.submission_form, url)
            if not form.get("can_submit"):
                raise HTTPException(status_code=409, detail=form.get("reason") or
                                    "O Moodle não está aceitando envio nesta tarefa.")
            ja_anexados = len(form.get("existing_files") or [])
            if form.get("max_files") and ja_anexados + len(conteudos) > form["max_files"]:
                raise HTTPException(
                    status_code=409,
                    detail=f"Esta tarefa aceita {form['max_files']} arquivo(s) e já tem "
                           f"{ja_anexados} anexado(s).",
                )
            if conteudos and not form.get("accepts_files"):
                raise HTTPException(status_code=409,
                                    detail="Esta tarefa não aceita arquivo, só texto.")
            if online_text.strip() and not form.get("accepts_text"):
                raise HTTPException(status_code=409,
                                    detail="Esta tarefa não aceita texto, só arquivo.")

            for nome, dados in conteudos:
                await asyncio.to_thread(moodle.upload_to_draft, form, nome, dados)

            status = await asyncio.to_thread(moodle.save_submission, form, online_text)
    except HTTPException:
        raise
    except PermissionError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc
    except RuntimeError as exc:
        # Recusa do próprio Moodle (tipo de arquivo, prazo, campo obrigatório):
        # a mensagem é dele e é a que ajuda o aluno.
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:
        codigo = registrar_falha(f"envio de tarefa (user={session.user_id})", exc)
        raise HTTPException(
            status_code=502, detail=mensagem_amigavel(codigo, "enviar a tarefa ao Moodle")
        ) from exc

    observability.logger.info(
        "Envio salvo como rascunho: user=%s tarefa=%s arquivos=%d",
        session.user_id, form.get("cmid"), len(conteudos),
    )
    return SubmissionResult(
        saved=True,
        status=[StatusLinha(**linha) for linha in status],
        moodle_url=url,
    )


@app.post("/api/sync-calendar", response_model=SyncCalendarResponse)
async def sync_calendar(
    request: SyncCalendarRequest,
    session: app_session.PortalSession = Depends(require_session),
):
    """
    Recebe a lista de eventos e o token OAuth2 do Google e cria os eventos
    no Google Calendar do usuário.

    Grava o ID de cada evento criado no banco — é o que faz o frontend lembrar
    que o evento já foi sincronizado depois de um reload.

    Fora do ar na v1 pública: o frontend não expõe o botão enquanto a tela de
    consentimento OAuth não passar pela verificação do Google. O endpoint fica
    de pé para o dia em que passar.
    """
    try:
        sync_service = CalendarSyncService(oauth_token=request.google_token)
        results = await sync_service.sync_events(request.events)

        if results:
            with repo.get_session() as db:
                for r in results:
                    repo.set_google_event_id(
                        db, session.user_id, r["stable_key"], r["google_event_id"]
                    )
                db.commit()

        return SyncCalendarResponse(
            synced_event_ids=[r["google_event_id"] for r in results],
            calendar_links=[r["link"] for r in results],
        )
    except Exception as exc:
        codigo = registrar_falha("sincronização com o Google Calendar", exc)
        raise HTTPException(
            status_code=502,
            detail=mensagem_amigavel(codigo, "sincronizar com o Google Calendar"),
        ) from exc


# ---------------------------------------------------------------------------
# Frontend compilado
#
# Registrado por último de propósito: o mount em "/" captura qualquer caminho,
# e as rotas acima precisam ser resolvidas primeiro.
# ---------------------------------------------------------------------------

class SPAStaticFiles(StaticFiles):
    """
    Arquivos estáticos com fallback para o `index.html`.

    Desde que a atividade ganhou endereço próprio (`/atividade/<chave>`), a
    interface tem rotas de verdade. Abrir esse link direto — de um favorito ou
    de um link mandado por um colega — chega ao servidor como um caminho que
    não existe em disco, e o `StaticFiles` puro devolveria 404. Quem resolve a
    rota é o JavaScript, então o servidor entrega o `index.html` e deixa o
    navegador decidir.

    `/api/...` fica de fora: ali um caminho desconhecido é erro de chamada, e
    devolver HTML no lugar de um 404 esconderia o problema de quem chamou.
    """

    async def get_response(self, path: str, scope):
        try:
            return await super().get_response(path, scope)
        except StarletteHTTPException as exc:
            if exc.status_code != 404 or path.startswith("api/"):
                raise
            return await super().get_response("index.html", scope)


_dist = Path(os.getenv("FRONTEND_DIST", Path(__file__).resolve().parent.parent.parent / "frontend" / "dist"))
if (_dist / "index.html").exists():
    app.mount("/", SPAStaticFiles(directory=str(_dist), html=True), name="frontend")
else:
    observability.logger.warning("Frontend não encontrado em %s — servindo só a API.", _dist)
