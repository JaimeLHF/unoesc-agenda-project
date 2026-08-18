"""
Prazos garimpados do PDF da disciplina.

Medido em 18/08/2026 numa conta de Medicina Veterinária: existe curso em que
nenhuma atividade é cadastrada no Moodle. As quatro disciplinas do aluno
somavam 58 `resource` e um fórum de tira-dúvidas — zero eventos de calendário.
Os prazos existem, mas dentro do PDF de apresentação da disciplina:

    A1/1 Avaliação teórica - Prof. Andressa 10/09/2026 - Peso: 4
    A1/3 Confecção de bulário 28/07/2026 á 25/11/2026 - Peso 0,2

É o mesmo caso das webconferências (`extract_webconferences` em `moodle.py`):
compromisso que o Moodle não conhece como objeto e só existe como texto solto.
A diferença é que aqui o texto está dentro de um arquivo, não na página.

Plano B, nunca plano A: `MoodleClient.run` só varre PDF de disciplina que não
produziu nenhum evento de calendário. Para quem cursa EAD, onde tudo é
`assign`/`quiz`, isto custa zero requisição.
"""
from __future__ import annotations

import io
import logging
import re
import unicodedata
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

logger = logging.getLogger(__name__)

TZ_BR = timezone(timedelta(hours=-3))

# Quantos PDFs abrir por disciplina. O aluno da medida tinha 58 arquivos em 4
# disciplinas; baixar todo semestre inteiro a cada scrape custaria minutos de
# espera para achar uma lâmina. Os candidatos são escolhidos pelo nome.
MAX_PDFS_POR_DISCIPLINA = 6

# Arquivo maior que isto é videoaula ou atlas de imagem, não cronograma.
MAX_BYTES = 8_000_000

# Páginas lidas por arquivo. O cronograma vive nas primeiras lâminas; passar
# disso é pagar CPU para ler bibliografia.
MAX_PAGINAS = 40

# Teto de eventos por arquivo. Um cronograma de aulas semanais tem 40 datas, e
# despejar tudo isso na agenda afogaria as entregas que importam. Quando corta,
# registra no log — silêncio aqui viraria "o PDF não tinha mais nada".
MAX_EVENTOS_POR_PDF = 30

# Janela de sanidade das datas. Bibliografia é cheia de ano solto ("ROCA,
# 2002"), mas ano sozinho não casa com o padrão; o que esta janela pega é erro
# de digitação do professor — "10/09/2062" — e data de edição do documento.
MESES_PASSADO = 12
MESES_FUTURO = 24

# Nome de arquivo que costuma carregar cronograma. Comparado sem acento e sem
# pontuação (ver `_normalizar`), porque "apresentação"/"apresentacao" e
# "plano-de-ensino"/"plano de ensino" aparecem nas duas grafias.
_PISTAS_NOME = (
    "apresentacao", "plano de ensino", "plano de aula", "plano da disciplina",
    "cronograma", "avaliacoes", "avaliacao", "calendario", "datas",
    "programa", "aula 1", "aula 01", "roteiro", "syllabus",
)

_DATA = re.compile(r"\b(\d{1,2})/(\d{1,2})/(\d{2,4})\b")

# Marcadores de lâmina do PowerPoint e traços soltos que sobram na ponta do
# título depois que a data sai.
_LIXO_BORDA = " \t -–—•▪·*>»"

# Conectores que ficam pendurados quando o título vinha antes de um intervalo:
# "Confecção de bulário 28/07 á 25/11" corta na primeira data e sobra o "á".
_CONECTOR_FINAL = re.compile(r"\s*\b(?:a|á|as|às|ate|até|e|de|entre|em|no|na)\b\s*$", re.I)

_PESO = re.compile(r"\s*[-–—]?\s*peso:?\s*[\d.,]+\s*$", re.I)


def _normalizar(s: str) -> str:
    """Minúsculas, sem acento e sem pontuação separadora."""
    sem_acento = "".join(
        c for c in unicodedata.normalize("NFKD", (s or "").lower())
        if not unicodedata.combining(c)
    )
    return re.sub(r"\s+", " ", re.sub(r"[-_./]+", " ", sem_acento)).strip()


def looks_like_schedule(nome: str) -> bool:
    """O nome do arquivo sugere um documento com datas do semestre?"""
    texto = _normalizar(nome)
    return any(p in texto for p in _PISTAS_NOME)


def pdf_to_text(dados: bytes, max_paginas: int = MAX_PAGINAS) -> str:
    """
    Texto de um PDF. Devolve "" para arquivo ilegível ou só de imagem.

    O `pypdf` não faz OCR: lâmina escaneada devolve vazio, e é assim que fica —
    OCR exigiria dependência binária na imagem do Fly e ainda erraria data.
    """
    try:
        from pypdf import PdfReader
    except ImportError:  # pragma: no cover - dependência declarada
        logger.warning("pypdf ausente: prazos em PDF não serão lidos")
        return ""

    try:
        leitor = PdfReader(io.BytesIO(dados))
        paginas = leitor.pages[:max_paginas]
        return "\n".join((p.extract_text() or "") for p in paginas)
    except Exception as exc:
        logger.info("PDF ilegível (%s)", exc)
        return ""


def _tipo(titulo: str) -> str:
    texto = _normalizar(titulo)
    if any(p in texto for p in ("prova", "avaliacao", "exame", "teste")):
        return "exam"
    return "deadline"


def _slug(texto: str) -> str:
    """Pedaço estável do título, para a chave do evento não depender da data."""
    return re.sub(r"[^a-z0-9]+", "-", _normalizar(texto))[:48].strip("-")


def _titulo_da_linha(linha: str, inicio_data: int, fim_ultima_data: int) -> str:
    """
    O que a linha diz, sem as datas.

    Corta na primeira data em vez de apagar as datas do meio: o que vem depois
    delas é quase sempre peso e período ("– Peso: 4"), e apagar deixaria o
    título costurado com o resto. Quando a linha *começa* pela data
    ("10/09/2026 - Prova 1"), o título é o que vem depois da última.
    """
    antes = linha[:inicio_data].strip(_LIXO_BORDA)
    antes = _CONECTOR_FINAL.sub("", antes).strip(_LIXO_BORDA)
    if len(antes) >= 4:
        return _PESO.sub("", antes).strip(_LIXO_BORDA)

    depois = linha[fim_ultima_data:].strip(_LIXO_BORDA)
    depois = _PESO.sub("", depois).strip(_LIXO_BORDA)
    return depois if len(depois) >= 4 else ""


def extract_schedule(
    texto: str,
    subject: str,
    course_url: str,
    course_id: Any = None,
    origem: str = "",
    hoje: Optional[datetime] = None,
) -> list[dict]:
    """
    Eventos garimpados do texto de um PDF da disciplina.

    Uma linha com data vira um compromisso. Intervalo ("28/07/2026 a
    25/11/2026") vira um evento só, na data final — é o prazo; o começo fica na
    descrição, que a tela mostra inteira.
    """
    agora = hoje or datetime.now(TZ_BR)
    limite_min = agora - timedelta(days=30 * MESES_PASSADO)
    limite_max = agora + timedelta(days=30 * MESES_FUTURO)

    eventos: list[dict] = []
    vistos: set[str] = set()

    for linha_bruta in (texto or "").splitlines():
        linha = " ".join(linha_bruta.split())
        achados = list(_DATA.finditer(linha))
        if not achados:
            continue

        datas: list[datetime] = []
        for m in achados:
            dia, mes, ano = int(m.group(1)), int(m.group(2)), int(m.group(3))
            if ano < 100:                       # "25/11/26" → 2026
                ano += 2000
            try:
                data = datetime(ano, mes, dia, tzinfo=TZ_BR)
            except ValueError:                  # 31/02: erro de digitação
                continue
            if limite_min <= data <= limite_max:
                datas.append(data)

        if not datas:
            continue

        titulo = _titulo_da_linha(linha, achados[0].start(), achados[-1].end())
        if not titulo:
            continue

        prazo = max(datas)                      # intervalo: vale a data final
        chave = f"pdf-{course_id}-{_slug(titulo)}"
        if chave in vistos:                     # mesma linha em dois arquivos
            continue
        vistos.add(chave)

        eventos.append({
            "id": str(uuid.uuid4()),
            "title": titulo,
            "date": prazo.strftime("%Y-%m-%d"),
            # Sem hora: o PDF diz o dia, e inventar "23:59" seria dar ao aluno
            # uma precisão que o documento não tem.
            "time": None,
            "description": (f"{linha}\n\nLido do arquivo “{origem}” da disciplina."
                            if origem else linha),
            "subject": subject,
            "type": _tipo(titulo),
            "synced": False,
            "source": "pdf_curso",
            "url": course_url,
            # Não existe evento no Moodle para apontar. Curso + título é o que
            # há de estável: se o professor corrigir a data no PDF, o evento é
            # atualizado em vez de duplicar.
            "moodle_event_id": chave,
            "event_type": None,
            "module": "pdf",
            "course_id": course_id,
        })

        if len(eventos) >= MAX_EVENTOS_POR_PDF:
            logger.info(
                "%s: teto de %d eventos atingido em “%s”; o resto do arquivo "
                "não foi lido", subject, MAX_EVENTOS_POR_PDF, origem,
            )
            break

    return eventos
