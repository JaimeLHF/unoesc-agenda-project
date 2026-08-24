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

# A sessão não expira por inatividade.
#
# Eram 8 horas, depois 30 dias, e mesmo 30 dias derruba quem passa um recesso
# sem abrir o app — volta em fevereiro e cai no login, que é justamente o
# momento em que a agenda importa. Agora o token vale até alguém encerrar:
# "Sair" no perfil, `revoke_for_user` (o que a troca de senha usa), ou uma
# `SESSION_SECRET` nova, que faz a senha guardada deixar de decifrar e derruba
# todas de uma vez. O custo é que token copiado do aparelho vale até ser
# revogado — a janela curta nunca protegeu contra isso de verdade, já que cada
# uso a renovava. Voltar a expirar é trocar o None por um `timedelta`: as duas
# checagens abaixo já tratam os dois casos.
SESSION_IDLE_TTL: timedelta | None = None


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

        if (
            SESSION_IDLE_TTL is not None
            and utc_now() - _aware(row.last_used_at) > SESSION_IDLE_TTL
        ):
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

    Com `SESSION_IDLE_TTL` em None não há sessão parada demais: a linha por
    aluno é barata, e apagar aqui seria deslogar quem voltou do recesso.
    """
    if SESSION_IDLE_TTL is None:
        return 0

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
