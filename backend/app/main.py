"""
Ponto de entrada da aplicação FastAPI — UNOESC Agenda.

Configura o app, CORS e registra todos os endpoints REST da API.
"""

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional
import os

from app.scraper import ScraperService
from app.parser import ParserService
from app.calendar_sync import CalendarSyncService

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


class ScrapeResponse(BaseModel):
    """Resposta do endpoint /api/scrape."""
    subjects: list[SubjectModel]


class ParseEventsRequest(BaseModel):
    """Requisição para o endpoint /api/parse-events."""
    subjects: list[SubjectModel]


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


# ---------------------------------------------------------------------------
# Inicialização do app FastAPI
# ---------------------------------------------------------------------------

app = FastAPI(
    title="UNOESC Agenda API",
    description="API para extração e sincronização de atividades acadêmicas da UNOESC.",
    version="1.0.0",
)

# Permite requisições do servidor de desenvolvimento Vite (porta 5173)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@app.get("/api/health")
async def health_check():
    """Verifica se a API está no ar."""
    return {"status": "ok", "message": "UNOESC Agenda API está funcionando."}


@app.post("/api/scrape", response_model=ScrapeResponse)
async def scrape_portal(credentials: LoginCredentials):
    """
    Recebe as credenciais do aluno, faz login no portal UNOESC com Playwright
    e retorna as disciplinas com o conteúdo extraído de cada página.
    """
    try:
        scraper = ScraperService()
        subjects = await scraper.run(credentials.username, credentials.password)
        return ScrapeResponse(subjects=subjects)
    except PermissionError as exc:
        # Credenciais inválidas ou acesso negado
        raise HTTPException(status_code=401, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Erro ao extrair dados do portal: {exc}") from exc


@app.post("/api/parse-events", response_model=ParseEventsResponse)
async def parse_events(request: ParseEventsRequest):
    """
    Recebe a lista de disciplinas com conteúdo e usa o Gemini para identificar
    e estruturar eventos acadêmicos (webconferências, entregas, provas, etc.).
    """
    try:
        parser = ParserService()
        events = await parser.extract_events(request.subjects)
        return ParseEventsResponse(events=events)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Erro ao interpretar eventos: {exc}") from exc


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
