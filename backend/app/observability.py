"""
Registro do que acontece no servidor — e o que o aluno vê quando quebra.

Duas coisas, porque são o mesmo problema visto dos dois lados:

1. **Log de verdade.** Antes o único registro era `print()`, sem hora, sem
   nível, sem stack trace. Num app rodando na máquina do dono isso passa; num
   app público, uma quebra do lado da UNOESC vira "erro 500" sem nenhum rastro
   de por quê.

2. **Mensagem limpa para o aluno.** `detail=f"Erro: {exc}"` mandava o texto da
   exceção direto para a tela — caminho de arquivo, nome de biblioteca, às
   vezes trecho de URL com parâmetro. Quem lê não entende e não deveria ver.

A ligação entre os dois é o `codigo`: um identificador curto que aparece na
tela do aluno e na linha de log. Ele manda um print no WhatsApp com o código,
e `fly logs | grep <codigo>` acha o traceback exato daquela falha.
"""

import logging
import os
import secrets
import time

from fastapi import Request
from fastapi.responses import JSONResponse

logger = logging.getLogger("agenda")


def setup_logging() -> None:
    """
    Configura o logging raiz. Chamado uma vez, na subida do app.

    `force=True` porque o uvicorn já instala handlers próprios ao iniciar; sem
    isso o `basicConfig` seria ignorado e as mensagens sairiam sem formato.
    """
    nivel = os.getenv("LOG_LEVEL", "INFO").upper()
    logging.basicConfig(
        level=getattr(logging, nivel, logging.INFO),
        format="%(asctime)s %(levelname)-7s [%(name)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        force=True,
    )
    # O access log do uvicorn repete o que o nosso middleware já registra, com
    # menos informação (não tem duração).
    logging.getLogger("uvicorn.access").disabled = True

    # O httpx loga uma linha por requisição ao Moodle, com a URL completa —
    # ruído a cada scrape, e URL de aluno no log sem necessidade. Só o que der
    # errado interessa.
    for ruidoso in ("httpx", "httpcore"):
        logging.getLogger(ruidoso).setLevel(logging.WARNING)


def novo_codigo() -> str:
    """Identificador curto de uma falha. Aparece na tela e no log."""
    return secrets.token_hex(3)


def registrar_falha(contexto: str, exc: BaseException) -> str:
    """
    Loga a exceção com stack trace e devolve o código para mostrar ao aluno.

    Use no `except` de qualquer coisa que fale com o mundo externo (Moodle,
    Google, provedor de IA): é o único lugar onde o motivo real fica gravado.
    """
    codigo = novo_codigo()
    logger.error("[%s] %s: %s", codigo, contexto, exc, exc_info=exc)
    return codigo


def mensagem_amigavel(codigo: str, acao: str) -> str:
    """
    Texto que vai para a tela. Diz o que falhou em português, sem detalhe
    interno, e carrega o código para o dono conseguir investigar depois.
    """
    return (
        f"Não foi possível {acao} agora. Tente de novo em alguns minutos — "
        f"se continuar, informe o código {codigo}."
    )


async def log_requests(request: Request, call_next):
    """
    Middleware: uma linha por requisição, com duração.

    Registra quem chamou, o que respondeu e quanto demorou. É o que responde
    "o app está lento?" e "alguém está usando?" sem precisar instrumentar nada
    além disso.
    """
    inicio = time.perf_counter()
    try:
        response = await call_next(request)
    except Exception as exc:
        # Exceção que escapou de todos os endpoints. Sem este handler, o
        # uvicorn devolveria um 500 com o traceback no corpo da resposta.
        duracao = (time.perf_counter() - inicio) * 1000
        codigo = registrar_falha(f"{request.method} {request.url.path}", exc)
        logger.info(
            "%s %s → 500 em %.0fms", request.method, request.url.path, duracao
        )
        return JSONResponse(
            status_code=500,
            content={"detail": mensagem_amigavel(codigo, "concluir esta ação")},
        )

    duracao = (time.perf_counter() - inicio) * 1000
    # Erro do servidor sobe para WARNING: é o que se procura ao investigar.
    nivel = logging.WARNING if response.status_code >= 500 else logging.INFO
    logger.log(
        nivel,
        "%s %s → %d em %.0fms",
        request.method,
        request.url.path,
        response.status_code,
        duracao,
    )
    return response
