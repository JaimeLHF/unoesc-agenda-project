"""
Ponto de entrada da aplicação FastAPI — UNOESC Agenda.

Configura o app, CORS e registra todos os endpoints REST da API.
"""

import asyncio
import os
from contextlib import asynccontextmanager
from typing import Optional

from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from app import repository as repo
from app import session as app_session
from app.calendar_sync import CalendarSyncService
from app.database import Subject as SubjectDB, event_key, init_db, utc_now
from app.moodle import MoodleClient, clear_session_cache

# ---------------------------------------------------------------------------
# Modelos de Requisição e Resposta (Pydantic)
# ---------------------------------------------------------------------------

class LoginCredentials(BaseModel):
    """Credenciais do portal UNOESC. Enviadas uma única vez, em /api/login."""
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


# ---------------------------------------------------------------------------
# Inicialização do app FastAPI
# ---------------------------------------------------------------------------

@asynccontextmanager
async def lifespan(_app: FastAPI):
    """
    Ciclo de vida do app. Substitui `@app.on_event("startup")`, deprecado no
    FastAPI. O que vem antes do `yield` roda na subida; depois, no shutdown.
    """
    init_db()
    yield


app = FastAPI(
    title="UNOESC Agenda API",
    description="API para extração e sincronização de atividades acadêmicas da UNOESC.",
    version="1.0.0",
    lifespan=lifespan,
)

# Permite requisições do servidor de desenvolvimento Vite (porta padrão 5180,
# regex aceita qualquer 51xx caso o Vite caia para a próxima porta livre).
app.add_middleware(
    CORSMiddleware,
    allow_origin_regex=r"http://localhost:51\d{2}",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------------
# Autenticação
# ---------------------------------------------------------------------------

def require_session(
    authorization: Optional[str] = Header(default=None),
) -> app_session.PortalSession:
    """
    Resolve o token do header `Authorization: Bearer <token>`.

    Dependência dos endpoints que precisam falar com o portal em nome do aluno.
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
    Valida as credenciais no portal e devolve um token de sessão.

    É o único endpoint que recebe a senha. A partir daqui o frontend usa o
    token, e a senha não volta a trafegar nem fica guardada no navegador.
    """
    try:
        with MoodleClient() as moodle:
            await asyncio.to_thread(
                moodle.login, credentials.username, credentials.password
            )
    except PermissionError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=500, detail=f"Erro ao autenticar no Moodle: {exc}"
        ) from exc

    return LoginResponse(token=app_session.create(credentials.username, credentials.password))


@app.post("/api/logout", status_code=200)
async def logout(authorization: Optional[str] = Header(default=None)):
    """Encerra a sessão do token informado. Idempotente."""
    if authorization and authorization.lower().startswith("bearer "):
        app_session.revoke(authorization[len("bearer "):].strip())
    return {"status": "ok"}


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@app.get("/api/health")
async def health_check():
    """
    Diagnóstico das dependências externas. Útil para identificar rapidamente
    o que está faltando configurar ao subir o app pela primeira vez.
    """
    provider = os.getenv("AI_PROVIDER", "gemini").lower()
    ai_key = "ANTHROPIC_API_KEY" if provider == "claude" else "GEMINI_API_KEY"

    checks = {
        "api": True,
        # A chave de IA deixou de ser obrigatória: os eventos vêm estruturados
        # do calendário do Moodle, sem LLM. Ela só serve para o assistente.
        "ai_key_optional": bool(os.getenv(ai_key)),
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
            f"{ai_key} não configurada — a agenda funciona normalmente, "
            "só o assistente de IA fica indisponível."
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
    Extrai disciplinas + calendário do Moodle e persiste tudo no banco local.

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
            repo.upsert_subjects(db, result["subjects"])
            if events:
                # Preenche `stable_key` em cada evento — o frontend usa esse
                # valor para marcar concluído.
                repo.upsert_events(db, events)
            repo.set_meta(db, "last_scraped_at", utc_now().isoformat())
            synced_keys = set(repo.list_synced_keys(db))
            db.commit()

        for ev in events:
            ev["synced"] = ev.get("stable_key") in synced_keys

        return ScrapeResponse(subjects=result["subjects"], calendar_events=events)
    except PermissionError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=500, detail=f"Erro ao extrair dados do Moodle: {exc}"
        ) from exc


@app.get("/api/cache", response_model=CacheResponse)
async def get_cache():
    """
    Retorna disciplinas + eventos persistidos do último scraping bem-sucedido,
    junto com a lista de eventos marcados como concluídos. Usado pelo frontend
    para abrir a app sem precisar logar novamente.
    """
    with repo.get_session() as session:
        subjects = [
            SubjectModel(id=s.name, name=s.name, content=s.content)
            for s in repo.list_subjects(session)
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
            for e in repo.list_events(session)
        ]
        done_keys = repo.list_done_keys(session)
        last_scraped_at = repo.get_meta(session, "last_scraped_at")

    return CacheResponse(
        subjects=subjects,
        events=events,
        done_keys=done_keys,
        last_scraped_at=last_scraped_at,
    )


@app.get("/api/done-events", response_model=DoneEventsResponse)
async def list_done_events():
    """Lista as `stable_keys` de todos os eventos marcados como concluídos."""
    with repo.get_session() as session:
        return DoneEventsResponse(done_keys=repo.list_done_keys(session))


@app.post("/api/done-events", response_model=DoneEventsResponse, status_code=200)
async def mark_event_done(request: DoneEventRequest):
    """Marca um evento como concluído (idempotente)."""
    with repo.get_session() as session:
        repo.mark_done(session, request.stable_key)
        session.commit()
        return DoneEventsResponse(done_keys=repo.list_done_keys(session))


@app.delete("/api/done-events", response_model=DoneEventsResponse)
async def unmark_event_done(request: DoneEventRequest):
    """Desmarca um evento como concluído."""
    with repo.get_session() as session:
        repo.unmark_done(session, request.stable_key)
        session.commit()
        return DoneEventsResponse(done_keys=repo.list_done_keys(session))


@app.delete("/api/cache")
async def clear_cache():
    """
    Apaga o cache local (subjects, events, meta). Mantém done_events para
    não perder o progresso do aluno ao limpar.

    Descarta também as sessões guardadas em memória (tokens emitidos e cookies
    do portal) — limpar o cache deve significar recomeçar do zero, inclusive o
    login.
    """
    with repo.get_session() as session:
        repo.clear_cache(session)
        session.commit()
    clear_session_cache()
    app_session.revoke_all()
    return {"status": "ok", "message": "Cache limpo. Faça login para recarregar os dados."}


class AiHelpMessage(BaseModel):
    role: str  # "user" | "assistant"
    content: str


class AiHelpRequest(BaseModel):
    """Requisição para pedir ajuda da IA sobre uma atividade."""
    activity_content: str
    activity_title: str
    subject_name: str
    messages: list[AiHelpMessage]  # histórico da conversa


def _build_system_prompt(request: AiHelpRequest) -> str:
    return f"""Você é um assistente acadêmico direto e eficiente. Seu papel é ajudar o aluno a resolver a atividade da forma mais completa e objetiva possível.

Atividade: "{request.activity_title}"
Disciplina: "{request.subject_name}"

Conteúdo completo da atividade (extraído do Moodle):
\"\"\"
{request.activity_content[:50000]}
\"\"\"

REGRAS:
- Forneça as respostas de forma clara e direta
- Se for um quiz com alternativas, indique a resposta correta e explique brevemente o porquê
- Se for uma atividade dissertativa, escreva a resposta completa que o aluno pode usar como base
- Sempre justifique brevemente a resposta para que o aluno entenda o raciocínio
- Use linguagem clara em português brasileiro
- Formate com markdown quando útil (listas, negrito, código)
- Se não tiver informação suficiente para responder, peça mais detalhes ao aluno
"""


def _call_gemini(system_prompt: str, messages: list[AiHelpMessage]) -> str:
    from google import genai
    from google.genai import types as genai_types

    client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))
    model = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")

    contents = []
    for msg in messages:
        role = "user" if msg.role == "user" else "model"
        contents.append(genai_types.Content(
            role=role,
            parts=[genai_types.Part(text=msg.content)],
        ))

    response = client.models.generate_content(
        model=model,
        contents=contents,
        config=genai_types.GenerateContentConfig(
            system_instruction=system_prompt,
        ),
    )
    return (response.text or "").strip()


def _call_claude(system_prompt: str, messages: list[AiHelpMessage]) -> str:
    import anthropic

    client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
    model = os.getenv("CLAUDE_MODEL", "claude-haiku-4-5-20251001")

    api_messages = []
    for msg in messages:
        api_messages.append({"role": msg.role, "content": msg.content})

    response = client.messages.create(
        model=model,
        max_tokens=4096,
        system=system_prompt,
        messages=api_messages,
    )
    return response.content[0].text


@app.post("/api/ai-help")
async def ai_help(request: AiHelpRequest):
    """
    Envia o conteúdo da atividade + histórico de conversa para a IA configurada
    (Gemini ou Claude). Retorna a resposta.
    """
    provider = os.getenv("AI_PROVIDER", "gemini").lower()

    if provider == "claude":
        if not os.getenv("ANTHROPIC_API_KEY"):
            raise HTTPException(
                status_code=503,
                detail="ANTHROPIC_API_KEY não configurada. Adicione em backend/.env.",
            )
    else:
        if not os.getenv("GEMINI_API_KEY"):
            raise HTTPException(
                status_code=503,
                detail="GEMINI_API_KEY não configurada. Adicione em backend/.env.",
            )

    system_prompt = _build_system_prompt(request)

    try:
        if provider == "claude":
            answer = _call_claude(system_prompt, request.messages)
        else:
            answer = _call_gemini(system_prompt, request.messages)

        if not answer:
            answer = "Desculpe, não consegui gerar uma resposta. Tente reformular sua pergunta."
        return {"response": answer}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Erro ao consultar IA: {exc}") from exc


class ActivityContentRequest(BaseModel):
    """Requisição para extrair conteúdo de uma atividade do Moodle."""
    subject_name: str
    activity_url: str


@app.post("/api/activity-content")
async def get_activity_content(
    request: ActivityContentRequest,
    session: app_session.PortalSession = Depends(require_session),
):
    """
    Extrai o conteúdo da página da atividade (enunciado, instruções, critérios).

    O `subject_name` não é mais necessário para chegar lá — a sessão do Moodle
    dá acesso a qualquer atividade em que o aluno esteja matriculado. Continua
    aceito para não quebrar o frontend antigo.
    """
    try:
        with MoodleClient() as moodle:
            content = await asyncio.to_thread(
                moodle.fetch_activity_content,
                session.username, session.password, request.activity_url,
            )
        if not content:
            raise HTTPException(
                status_code=502,
                detail="Não foi possível extrair o conteúdo da atividade.",
            )
        return {"content": content}
    except PermissionError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Erro ao extrair conteúdo: {exc}") from exc


class OpenCourseRequest(BaseModel):
    """Requisição para obter o link de uma atividade/disciplina no Moodle."""
    subject_name: str
    target_url: Optional[str] = None  # URL da atividade específica (mod/quiz, mod/assign, etc.)


@app.post("/api/open-course")
async def open_course(request: OpenCourseRequest):
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
        subject = db.get(SubjectDB, request.subject_name)
        if not subject or not subject.course_url:
            raise HTTPException(
                status_code=404,
                detail="Disciplina não encontrada. Tente atualizar os dados.",
            )
        return {"url": subject.course_url}


@app.post("/api/sync-calendar", response_model=SyncCalendarResponse)
async def sync_calendar(request: SyncCalendarRequest):
    """
    Recebe a lista de eventos e o token OAuth2 do Google e cria os eventos
    no Google Calendar do usuário.

    Grava o ID de cada evento criado no banco — é o que faz o frontend lembrar
    que o evento já foi sincronizado depois de um reload.
    """
    try:
        sync_service = CalendarSyncService(oauth_token=request.google_token)
        results = await sync_service.sync_events(request.events)

        if results:
            with repo.get_session() as session:
                for r in results:
                    repo.set_google_event_id(session, r["stable_key"], r["google_event_id"])
                session.commit()

        return SyncCalendarResponse(
            synced_event_ids=[r["google_event_id"] for r in results],
            calendar_links=[r["link"] for r in results],
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Erro ao sincronizar com o Google Calendar: {exc}") from exc
