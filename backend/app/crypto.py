"""
Cifragem simétrica das senhas do Moodle guardadas em sessão.

## Por que a senha é guardada

O `MoodleClient` refaz o login sozinho quando a sessão do Moodle expira no meio
do uso (o cookie do Moodle vale bem menos que a sessão do app). Guardar
só o cookie obrigaria o aluno a redigitar a senha no meio da navegação, várias
vezes por dia.

## O que isso protege — e o que não protege

Protege contra vazamento **do banco**: um dump do SQLite (backup mal guardado,
volume copiado) não entrega senha nenhuma sem a `SESSION_SECRET`, que vive fora
do arquivo, nas variáveis de ambiente.

Não protege contra comprometimento do **servidor rodando**: quem tiver o
processo tem a chave e o banco juntos, e consegue decifrar. Esse risco é
inerente a guardar credencial de terceiro e não tem solução criptográfica — a
solução real é o Moodle emitir um token de web service por aluno, aí a senha
sai do fluxo inteiro. Está registrado como o item de maior impacto no
`docs/PLANO_PUBLICO.md`.
"""

import base64
import hashlib
import logging
import os

from cryptography.fernet import Fernet, InvalidToken

logger = logging.getLogger("agenda.crypto")


class SecretMissingError(RuntimeError):
    """`SESSION_SECRET` ausente num ambiente que exige a chave."""


def _derive_key(secret: str) -> bytes:
    """
    Converte um segredo de texto livre na chave de 32 bytes que o Fernet exige.

    SHA-256 direto, sem KDF de alongamento: a entrada não é senha de usuário, é
    um segredo de infraestrutura que deve ser gerado aleatoriamente (veja
    `.env.example`). Alongar não acrescenta nada contra quem já tem a chave, e
    a proteção aqui é o segredo ser longo e aleatório.
    """
    return base64.urlsafe_b64encode(hashlib.sha256(secret.encode("utf-8")).digest())


def _load_fernet() -> Fernet:
    secret = os.getenv("SESSION_SECRET", "").strip()

    if not secret:
        if os.getenv("APP_ENV", "development").lower() == "production":
            raise SecretMissingError(
                "SESSION_SECRET não configurada. Em produção ela é obrigatória: "
                "sem ela, cada reinício invalidaria todas as sessões ativas."
            )
        # Desenvolvimento: chave efêmera. Reiniciar o backend derruba as
        # sessões, que é o comportamento que o app já tinha antes.
        secret = Fernet.generate_key().decode()
        logger.warning(
            "SESSION_SECRET não definida — usando chave efêmera de "
            "desenvolvimento. As sessões não sobrevivem a um restart."
        )

    return Fernet(_derive_key(secret))


_fernet: Fernet | None = None


def _fernet_instance() -> Fernet:
    """Carrega a chave uma vez, no primeiro uso (não no import)."""
    global _fernet
    if _fernet is None:
        _fernet = _load_fernet()
    return _fernet


def encrypt(plaintext: str) -> str:
    return _fernet_instance().encrypt(plaintext.encode("utf-8")).decode("ascii")


def decrypt(ciphertext: str) -> str | None:
    """
    Decifra. Devolve `None` quando o texto não bate com a chave atual — o caso
    normal disso é a `SESSION_SECRET` ter mudado, e a resposta certa é tratar a
    sessão como expirada e pedir login de novo.
    """
    try:
        return _fernet_instance().decrypt(ciphertext.encode("ascii")).decode("utf-8")
    except (InvalidToken, ValueError):
        return None
