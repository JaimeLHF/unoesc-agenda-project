"""
Sessões de aplicação — troca a senha do Moodle por um token opaco.

As credenciais são enviadas uma única vez em `/api/login`; o backend devolve um
token que os demais endpoints exigem no header `Authorization: Bearer <token>`.

O que mudou ao virar app hospedado: a sessão agora vive no banco, não num
`dict` de processo. Antes, todo deploy deslogava todo mundo e uma segunda
instância não reconhecia os tokens da primeira. O token é gravado **hasheado**
(SHA-256) — ler o banco não permite se passar por ninguém — e a senha vai
cifrada, ver `crypto.py`.
"""

import hashlib
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from sqlalchemy import delete, select

from app import crypto
from app.database import AppSession, SessionLocal, User, utc_now
from app.repository import get_or_create_user

# Tempo de inatividade após o qual a sessão é descartada. Cada uso renova.
SESSION_IDLE_TTL = timedelta(hours=8)


@dataclass
class PortalSession:
    """Dados do aluno associados a um token emitido pelo backend."""

    user_id: str
    username: str
    password: str


def _hash(token: str) -> str:
    """
    SHA-256 puro, sem salt. O token já é 256 bits de aleatoriedade vinda do
    `secrets` — não há o que um ataque de dicionário faça contra ele, que é o
    problema que salt+KDF resolvem para senhas escolhidas por gente.
    """
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def create(username: str, password: str) -> str:
    """
    Emite um token novo, criando o usuário se for o primeiro login dele.
    """
    token = secrets.token_urlsafe(32)

    with SessionLocal() as db:
        user = get_or_create_user(db, username)
        db.add(
            AppSession(
                token_hash=_hash(token),
                user_id=user.id,
                password_enc=crypto.encrypt(password),
            )
        )
        db.commit()

    return token


def get(token: str) -> PortalSession | None:
    """
    Devolve a sessão do token, renovando a janela de inatividade.

    Retorna None se o token não existe, se a sessão ficou parada além do TTL,
    ou se a senha não pôde ser decifrada (a `SESSION_SECRET` mudou) — nos três
    casos o certo é o frontend mandar o aluno logar de novo.
    """
    if not token:
        return None

    token_hash = _hash(token)

    with SessionLocal() as db:
        row = db.get(AppSession, token_hash)
        if row is None:
            return None

        if utc_now() - _aware(row.last_used_at) > SESSION_IDLE_TTL:
            db.delete(row)
            db.commit()
            return None

        password = crypto.decrypt(row.password_enc)
        if password is None:
            db.delete(row)
            db.commit()
            return None

        user = db.get(User, row.user_id)
        if user is None:
            db.delete(row)
            db.commit()
            return None

        row.last_used_at = utc_now()
        db.commit()

        return PortalSession(
            user_id=user.id,
            username=user.moodle_username,
            password=password,
        )


def revoke(token: str) -> None:
    """Encerra uma sessão. Idempotente."""
    if not token:
        return
    with SessionLocal() as db:
        row = db.get(AppSession, _hash(token))
        if row is not None:
            db.delete(row)
            db.commit()


def revoke_for_user(user_id: str) -> None:
    """Encerra todas as sessões de um aluno."""
    with SessionLocal() as db:
        db.execute(delete(AppSession).where(AppSession.user_id == user_id))
        db.commit()


def purge_expired() -> int:
    """
    Remove sessões paradas além do TTL. Chamado no startup; sem isso a tabela
    só cresce, já que uma sessão abandonada nunca passa por `get()` de novo.
    """
    cutoff = utc_now() - SESSION_IDLE_TTL
    with SessionLocal() as db:
        rows = db.execute(
            select(AppSession).where(AppSession.last_used_at < cutoff)
        ).scalars().all()
        for row in rows:
            db.delete(row)
        db.commit()
        return len(rows)


def _aware(value: datetime) -> datetime:
    """
    O SQLite devolve datetime sem timezone; comparar com `utc_now()` (aware)
    levantaria TypeError. Os valores gravados já são hora de parede em UTC.
    """
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
