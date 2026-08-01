"""
Sessões de aplicação — troca a senha do portal por um token opaco.

Antes, usuário e senha viajavam no corpo de `/api/scrape`,
`/api/activity-content` e `/api/open-course`, e ficavam guardados em state do
React durante toda a sessão. Agora as credenciais são enviadas uma única vez
em `/api/login`; o backend devolve um token que os demais endpoints exigem no
header `Authorization: Bearer <token>`.

As credenciais continuam na memória do processo, e não só os cookies, porque o
scraper precisa delas para relogar sozinho quando a sessão do portal expira
(ver `ScraperService._authenticated`). Guardar apenas os cookies obrigaria o
aluno a digitar a senha de novo no meio do uso.

Nada disso vai para o disco: reiniciar o backend derruba todas as sessões.
"""

import secrets
import threading
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from app.database import utc_now

# Tempo de inatividade após o qual a sessão é descartada. Cada uso renova.
SESSION_IDLE_TTL = timedelta(hours=8)


@dataclass
class PortalSession:
    """Credenciais do portal associadas a um token emitido pelo backend."""

    username: str
    password: str
    created_at: datetime = field(default_factory=utc_now)
    last_used_at: datetime = field(default_factory=utc_now)


_sessions: dict[str, PortalSession] = {}
_lock = threading.Lock()


def create(username: str, password: str) -> str:
    """Emite um token novo para as credenciais informadas."""
    token = secrets.token_urlsafe(32)
    with _lock:
        _sessions[token] = PortalSession(username=username, password=password)
    return token


def get(token: str) -> PortalSession | None:
    """
    Devolve a sessão do token, renovando a janela de inatividade.

    Retorna None se o token não existe ou se a sessão ficou parada além do TTL.
    """
    if not token:
        return None
    with _lock:
        session = _sessions.get(token)
        if session is None:
            return None
        if utc_now() - session.last_used_at > SESSION_IDLE_TTL:
            del _sessions[token]
            return None
        session.last_used_at = utc_now()
        return session


def revoke(token: str) -> None:
    """Encerra uma sessão. Idempotente."""
    with _lock:
        _sessions.pop(token, None)


def revoke_all() -> None:
    """Encerra todas as sessões."""
    with _lock:
        _sessions.clear()
