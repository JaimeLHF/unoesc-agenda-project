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
from collections import Counter, deque
from datetime import datetime, timezone

from fastapi import Request
from fastapi.responses import JSONResponse

logger = logging.getLogger("agenda")


# ---------------------------------------------------------------------------
# Métricas em memória
# ---------------------------------------------------------------------------
#
# O painel do dono precisa responder "como o servidor está se comportando"
# sem que ninguém abra um terminal. O log do Fly responde isso, mas só para
# quem tem o flyctl na mão e só enquanto o buffer dura algumas horas.
#
# Isto aqui é o mínimo que responde a pergunta de dentro do processo: quantas
# requisições, por rota, quanto demoraram, e o que deu errado. Fica em
# memória de propósito — gravar métrica em banco custaria uma tabela e uma
# escrita por requisição, para um dado que não é do aluno e que ninguém vai
# consultar sobre o mês passado. O preço é que **todo deploy zera**, e o
# painel diz desde quando está contando para essa leitura não enganar.

INICIO = datetime.now(timezone.utc)

# Duração de cada requisição, em ms. Limitado porque memória de máquina
# pequena é o recurso escasso aqui — 2000 amostras dão p50/p95 honestos e
# ocupam alguns KB.
_duracoes: deque[float] = deque(maxlen=2000)
_por_rota: Counter[str] = Counter()
_por_status: Counter[int] = Counter()
_lentas: deque[tuple[str, float, str]] = deque(maxlen=10)
_falhas: deque[dict] = deque(maxlen=25)


def _registrar_metrica(metodo: str, rota: str, status: int, ms: float) -> None:
    """
    Uma amostra. `rota` já vem sem identificador variável — ver `_rotulo`.
    """
    _duracoes.append(ms)
    _por_rota[f"{metodo} {rota}"] += 1
    _por_status[status] += 1
    # Só o que passou de 1s: abaixo disso a lista viraria ruído e esconderia
    # justamente a requisição que travou a tela de alguém.
    if ms >= 1000:
        _lentas.appendleft((f"{metodo} {rota}", ms, agora_iso()))


def agora_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _percentil(valores: list[float], p: float) -> float | None:
    if not valores:
        return None
    return valores[min(int(len(valores) * p), len(valores) - 1)]


def metricas() -> dict:
    """Resumo do que o processo viu desde que subiu. Consumido pelo painel."""
    ordenadas = sorted(_duracoes)
    return {
        "desde": INICIO.isoformat(timespec="seconds"),
        "uptime_s": int((datetime.now(timezone.utc) - INICIO).total_seconds()),
        "requisicoes": sum(_por_rota.values()),
        "amostras": len(ordenadas),
        "p50_ms": _percentil(ordenadas, 0.50),
        "p95_ms": _percentil(ordenadas, 0.95),
        "max_ms": ordenadas[-1] if ordenadas else None,
        "por_rota": _por_rota.most_common(12),
        "por_status": sorted(_por_status.items()),
        "lentas": [
            {"rota": r, "ms": round(ms), "quando": q} for r, ms, q in _lentas
        ],
        "falhas": list(_falhas),
    }


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
    _falhas.appendleft(
        {
            "codigo": codigo,
            "contexto": contexto,
            "erro": f"{type(exc).__name__}: {exc}"[:300],
            "quando": agora_iso(),
        }
    )
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


def _rotulo(path: str) -> str:
    """
    Caminho sem a parte variável: `/calendario/<chave>.ics` conta como uma
    rota só. Sem isso o painel listaria uma linha por token e o ranking de
    rotas mais chamadas não diria nada — e o token do .ics, que é credencial,
    ficaria guardado na memória do processo.
    """
    partes = []
    for parte in path.split("/"):
        if len(parte) > 24 or (parte.endswith(".ics") and len(parte) > 8):
            partes.append("<id>")
        else:
            partes.append(parte)
    return "/".join(partes)[:120]


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
        _registrar_metrica(request.method, _rotulo(request.url.path), 500, duracao)
        logger.info(
            "%s %s → 500 em %.0fms", request.method, request.url.path, duracao
        )
        return JSONResponse(
            status_code=500,
            content={"detail": mensagem_amigavel(codigo, "concluir esta ação")},
        )

    duracao = (time.perf_counter() - inicio) * 1000
    _registrar_metrica(
        request.method, _rotulo(request.url.path), response.status_code, duracao
    )
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
