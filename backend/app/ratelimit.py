"""
Limitador de tentativas de login.

Sem isso, o `/api/login` público vira um proxy de força bruta contra o Moodle
da UNOESC: qualquer pessoa poderia varrer senhas de matrículas usando o nosso
servidor, e quem levaria o bloqueio de IP (e a ligação da TI) seria a gente.

Janela deslizante simples, em memória. Se um dia o app rodar em mais de uma
instância, cada uma terá a própria contagem e o limite efetivo multiplica pelo
número de instâncias — a hora de trocar por Redis é essa, não antes.
"""

import os
import threading
from collections import defaultdict
from datetime import timedelta

from app.database import utc_now

MAX_ATTEMPTS = int(os.getenv("LOGIN_MAX_ATTEMPTS", "5"))
WINDOW = timedelta(minutes=int(os.getenv("LOGIN_WINDOW_MINUTES", "15")))

_failures: dict[str, list] = defaultdict(list)
_lock = threading.Lock()


def _prune(key: str) -> list:
    """Descarta as tentativas que já saíram da janela. Chame com o lock."""
    cutoff = utc_now() - WINDOW
    kept = [ts for ts in _failures[key] if ts > cutoff]
    if kept:
        _failures[key] = kept
    else:
        _failures.pop(key, None)
    return kept


def seconds_until_allowed(key: str) -> int:
    """
    Quantos segundos faltam até a próxima tentativa ser aceita. Zero quando o
    login pode seguir agora.
    """
    with _lock:
        attempts = _prune(key)
        if len(attempts) < MAX_ATTEMPTS:
            return 0
        libera_em = min(attempts) + WINDOW
        return max(1, int((libera_em - utc_now()).total_seconds()))


def register_failure(key: str) -> None:
    """Contabiliza uma tentativa de login recusada pelo Moodle."""
    with _lock:
        _prune(key)
        _failures[key].append(utc_now())


def reset(key: str) -> None:
    """Zera o histórico após um login bem-sucedido."""
    with _lock:
        _failures.pop(key, None)
