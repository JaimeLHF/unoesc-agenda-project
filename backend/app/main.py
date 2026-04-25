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
from app.database import init_db, stable_event_key
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

# Permite requisições do servidor de desenvolvimento Vite (5173/5174 — o Vite
# escolhe a próxima porta livre se 5173 estiver ocupada)
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
