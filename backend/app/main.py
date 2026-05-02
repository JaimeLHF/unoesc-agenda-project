"""
Ponto de entrada da aplicação FastAPI — UNOESC Agenda.

Configura o app, CORS e registra todos os endpoints REST da API.
"""

import asyncio
import os
from datetime import datetime
from typing import Optional

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from app import repository as repo
from app.calendar_sync import CalendarSyncService
from app.database import Subject as SubjectDB, init_db, stable_event_key
from app.parser import ParserService
from app.scraper import ScraperService

# ---------------------------------------------------------------------------
# Modelos de Requisição e Resposta (Pydantic)
# ---------------------------------------------------------------------------

class LoginCredentials(BaseModel):
    """Credenciais do portal UNOESC."""
    username: str
    password: str


class SubjectModel(BaseModel):
    """Representa uma disciplina com seu conteúdo extraído."""
    id: str
    name: str
    content: Optional[str] = None


class AcademicEvent(BaseModel):
    """Representa um evento acadêmico extraído pelo Gemini."""
    id: str
    title: str
    date: str                # ISO 8601 (ex: "2025-06-10")
    time: Optional[str] = None  # ex: "19:00"
    description: str
    subject: str
    type: str                # webconference | deadline | exam | other
    synced: Optional[bool] = False
    url: Optional[str] = None  # link direto pro evento no portal Moodle


class ScrapeResponse(BaseModel):
    """Resposta do endpoint /api/scrape."""
    subjects: list[SubjectModel]
    calendar_events: list[AcademicEvent] = []


class ParseEventsRequest(BaseModel):
    """Requisição para o endpoint /api/parse-events."""
    subjects: list[SubjectModel]
    # Eventos já extraídos do calendário Moodle (fonte estruturada).
    # Mesclados aos eventos identificados pelo Gemini, com dedup.
    calendar_events: list[AcademicEvent] = []


class ParseEventsResponse(BaseModel):
    """Resposta do endpoint /api/parse-events."""
    events: list[AcademicEvent]


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

app = FastAPI(
    title="UNOESC Agenda API",
    description="API para extração e sincronização de atividades acadêmicas da UNOESC.",
    version="1.0.0",
)


@app.on_event("startup")
def _startup() -> None:
    """Cria as tabelas SQLite na primeira vez que o app sobe."""
    init_db()

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
# Endpoints
# ---------------------------------------------------------------------------

@app.get("/api/health")
async def health_check():
    """
    Diagnóstico das dependências externas. Útil para identificar rapidamente
    o que está faltando configurar ao subir o app pela primeira vez.
    """
    checks = {
        "api": True,
        "gemini_api_key": bool(os.getenv("GEMINI_API_KEY")),
        "playwright_chromium": False,
        "database": False,
    }
    hints: list[str] = []

    # Playwright Chromium
    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as pw:
            checks["playwright_chromium"] = pw.chromium.executable_path is not None
    except Exception:
        checks["playwright_chromium"] = False

    # Banco
    try:
        from sqlalchemy import text
        with repo.get_session() as session:
            session.execute(text("SELECT 1"))
            checks["database"] = True
    except Exception:
        checks["database"] = False

    if not checks["gemini_api_key"]:
        hints.append(
            "GEMINI_API_KEY não configurada. Edite backend/.env. "
            "Veja README.md → 'Configurando o Gemini'."
        )
    if not checks["playwright_chromium"]:
        hints.append(
            "Chromium do Playwright não instalado. "
            "Rode: cd backend && playwright install chromium (com o venv ativo)."
        )

    return {
        "status": "ok" if all(checks.values()) else "warn",
        "checks": checks,
        "hints": hints,
    }


@app.post("/api/scrape", response_model=ScrapeResponse)
async def scrape_portal(credentials: LoginCredentials):
    """
    Faz login no portal UNOESC, extrai disciplinas + calendário do Moodle,
    e persiste tudo no banco local (cache).
    """
    try:
        scraper = ScraperService()
        # Playwright sync precisa rodar fora do event loop do FastAPI
        result = await asyncio.to_thread(
            scraper.run, credentials.username, credentials.password
        )

        # Persiste o cache: subjects + eventos do calendar
        with repo.get_session() as session:
            repo.upsert_subjects(session, result["subjects"])
            if result.get("calendar_events"):
                repo.upsert_events(session, result["calendar_events"])
            repo.set_meta(session, "last_scraped_at", datetime.utcnow().isoformat())
            session.commit()

        return ScrapeResponse(
            subjects=result["subjects"],
            calendar_events=result.get("calendar_events", []),
        )
    except PermissionError as exc:
        # Credenciais inválidas ou acesso negado
        raise HTTPException(status_code=401, detail=str(exc)) from exc
    except Exception as exc:
        msg = str(exc)
        # Erro típico quando o Chromium do Playwright não foi instalado
        if "Executable doesn't exist" in msg or "playwright install" in msg.lower():
            detail = (
                "Chromium do Playwright não está instalado. "
                "Ative o venv e rode: playwright install chromium. "
                "Veja README.md, seção 'Setup rápido'."
            )
            raise HTTPException(status_code=500, detail=detail) from exc
        raise HTTPException(status_code=500, detail=f"Erro ao extrair dados do portal: {exc}") from exc


def _dedupe_events(
    calendar_events: list[AcademicEvent],
    gemini_events: list[dict],
) -> list[dict]:
    """
    Mescla eventos do calendário Moodle (fonte primária, estruturada) com os
    extraídos pelo Gemini (texto livre). Em caso de conflito, mantém o do
    calendário — datas/horários são exatos lá.

    Heurística de dedup: mesma disciplina + mesma data → mesmo evento.
    Evita duplicar uma "Atividade Avaliativa 1 - 22/03" extraída por LLM com
    a "ENTREGA 1" do calendário Moodle (mesmo prazo).
    """
    seen_keys: set[tuple[str, str]] = set()
    merged: list[dict] = []

    # Calendário primeiro — tem prioridade
    for ev in calendar_events:
        key = (ev.subject.strip().lower(), ev.date)
        seen_keys.add(key)
        merged.append(ev.model_dump())

    # Gemini só entra se a chave (disciplina+data) não existir
    for ev in gemini_events:
        key = (ev.get("subject", "").strip().lower(), ev.get("date", ""))
        if key in seen_keys:
            continue
        seen_keys.add(key)
        merged.append(ev)

    # Ordena cronologicamente
    merged.sort(key=lambda e: (e.get("date", ""), e.get("time") or ""))
    return merged


@app.post("/api/parse-events", response_model=ParseEventsResponse)
async def parse_events(request: ParseEventsRequest):
    """
    Mescla eventos do calendário Moodle (fonte estruturada) com eventos
    extraídos pelo Gemini do conteúdo de cada disciplina (captura
    webconferências e outros eventos não publicados como prazo no Moodle).
    """
    try:
        parser = ParserService()
        gemini_events = await parser.extract_events(request.subjects)
        merged = _dedupe_events(request.calendar_events, gemini_events)

        # Persiste eventos consolidados no cache local
        if merged:
            with repo.get_session() as session:
                repo.upsert_events(session, merged)
                session.commit()

        return ParseEventsResponse(events=merged)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Erro ao interpretar eventos: {exc}") from exc


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
                title=e.title,
                date=e.date,
                time=e.time,
                description=e.description or "",
                subject=e.subject,
                type=e.type,
                synced=False,
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
    """
    with repo.get_session() as session:
        repo.clear_cache(session)
        session.commit()
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
    username: str
    password: str
    subject_name: str
    activity_url: str


@app.post("/api/activity-content")
async def get_activity_content(request: ActivityContentRequest):
    """
    Faz login no Moodle via SSO e extrai o conteúdo completo da página
    da atividade (enunciado, instruções, critérios de avaliação).
    """
    with repo.get_session() as session:
        subject = session.get(SubjectDB, request.subject_name)
        if not subject or not subject.dof:
            raise HTTPException(
                status_code=404,
                detail="Disciplina não encontrada ou sem código de acesso.",
            )
        dof = subject.dof

    try:
        scraper = ScraperService()
        content = await asyncio.to_thread(
            scraper.fetch_activity_content,
            request.username, request.password, dof, request.activity_url,
        )
        if not content:
            raise HTTPException(
                status_code=502,
                detail="Não foi possível extrair o conteúdo da atividade.",
            )
        return {"content": content}
    except PermissionError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Erro ao extrair conteúdo: {exc}") from exc


class OpenCourseRequest(BaseModel):
    """Requisição para gerar link SSO pro Moodle."""
    username: str
    password: str
    subject_name: str
    target_url: Optional[str] = None  # URL da atividade específica (mod/quiz, mod/assign, etc.)


@app.post("/api/open-course")
async def open_course(request: OpenCourseRequest):
    """
    Faz login rápido no portal e gera um link SSO fresco para o Moodle
    da disciplina solicitada. Retorna o SSO url + target url para o frontend
    fazer o redirect em sequência (SSO cria sessão → redirect pra atividade).
    """
    # Busca o dof da disciplina no banco
    with repo.get_session() as session:
        subject = session.get(SubjectDB, request.subject_name)
        if not subject or not subject.dof:
            raise HTTPException(
                status_code=404,
                detail="Disciplina não encontrada ou sem código de acesso (dof). Tente atualizar os dados.",
            )
        dof = subject.dof

    try:
        scraper = ScraperService()
        sso_url = await asyncio.to_thread(
            scraper.generate_sso_link, request.username, request.password, dof
        )
        if not sso_url:
            raise HTTPException(
                status_code=502,
                detail="Não foi possível gerar o link de acesso ao Moodle.",
            )
        return {"sso_url": sso_url, "target_url": request.target_url}
    except PermissionError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Erro ao gerar link: {exc}") from exc


@app.post("/api/sync-calendar", response_model=SyncCalendarResponse)
async def sync_calendar(request: SyncCalendarRequest):
    """
    Recebe a lista de eventos e o token OAuth2 do Google e cria os eventos
    no Google Calendar do usuário.
    """
    try:
        sync_service = CalendarSyncService(oauth_token=request.google_token)
        synced_ids, links = await sync_service.sync_events(request.events)
        return SyncCalendarResponse(synced_event_ids=synced_ids, calendar_links=links)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Erro ao sincronizar com o Google Calendar: {exc}") from exc
