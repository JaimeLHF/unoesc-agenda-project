"""
Cliente HTTP do Moodle — UNOESC Agenda.

Substitui o `scraper.py` (Playwright + portal JSP). O portal acadêmico
(`acad.unoesc.edu.br`) era HTML sob medida da UNOESC, diferente por curso, e
por isso só funcionava para alguns alunos. O Moodle (`on.unoesc.edu.br`) é
software padrão: aceita login HTTP direto e expõe a mesma API JSON que a
própria interface web consome.

Fluxo:
  1. `GET /login/index.php` para pegar o `logintoken` do form
  2. `POST /login/index.php` com usuário/senha → cookies `MoodleSession`
  3. `sesskey` sai do `M.cfg` embutido no HTML de qualquer página logada
  4. `POST /lib/ajax/service.php?sesskey=…&info=<fn>` devolve JSON

Sem browser, sem Chromium, sem SSO, sem parsing de DOM.

As decisões abaixo vieram de medição contra contas reais; os scripts que as
produziram estão em `backend/scripts/probes/` e o README de lá tem o mapa
completo da API.
"""

import base64
import json
import logging
import re
import threading
import unicodedata
import uuid
from datetime import datetime, timedelta, timezone
from html import unescape
from typing import Any, Optional
from urllib.parse import unquote

import httpx

logger = logging.getLogger("agenda.moodle")

# ---------------------------------------------------------------------------
# Constantes
# ---------------------------------------------------------------------------

MOODLE_BASE = "https://on.unoesc.edu.br"

TIMEOUT = httpx.Timeout(30.0, connect=15.0)
USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/131.0 Safari/537.36"
)

# Brasil não tem horário de verão desde 2019; UTC-3 é estável.
TZ_BR = timezone(timedelta(hours=-3))

# Janela padrão do calendário. Meses para trás importam: prazo já vencido só
# aparece varrendo o passado, e o aluno ainda quer vê-lo marcado como perdido.
MONTHS_BACK = 2
MONTHS_AHEAD = 6

# `modulename` do Moodle → tipo de evento da aplicação
# (os tipos aceitos são: webconference | deadline | exam | other)
MODULE_TYPE_MAP = {
    "assign": "deadline",
    "quiz": "exam",
    "forum": "deadline",
    "hsuforum": "deadline",
    "workshop": "deadline",
    "lesson": "deadline",
    "choice": "other",
    "feedback": "other",
    # Plugins de webconferência — nenhum apareceu nas contas medidas até agora,
    # mas o mapeamento é barato e evita cair em "other" se algum curso usar.
    "bigbluebuttonbn": "webconference",
    "zoom": "webconference",
    "collaborate": "webconference",
    "teams": "webconference",
    "webconf": "webconference",
}

# Módulos que são material de leitura. O palpite por título nunca se aplica a
# eles — só ao que pode de fato ser um compromisso.
MATERIAL_MODULES = {"resource", "folder", "book", "imscp", "glossary", "wiki"}


# ---------------------------------------------------------------------------
# Cache de sessão
# ---------------------------------------------------------------------------
#
# Mesma motivação do cache antigo do scraper: sem ele, cada chamada refazia o
# login. Agora guardamos os cookies do Moodle (e o sesskey) em vez do
# `storage_state` do Playwright.
#
# Só em memória, de propósito: cookies de sessão não vão para o disco.
# Reiniciar o backend descarta tudo e o próximo request faz login normalmente.

SESSION_MAX_AGE = timedelta(minutes=30)

_session_cache: dict[str, dict] = {}
_session_lock = threading.Lock()


def _cache_key(username: str, password: str) -> str:
    """
    Identifica a sessão por usuário + hash da senha.

    A senha entra como hash (nunca em claro) para que trocar de credenciais
    force um login de verdade, em vez de reaproveitar a sessão antiga e dar a
    impressão de que a senha nova foi aceita.
    """
    import hashlib

    digest = hashlib.sha256(password.encode("utf-8")).hexdigest()
    return f"{username}:{digest}"


def _load_session(key: str) -> Optional[dict]:
    with _session_lock:
        entry = _session_cache.get(key)
        if not entry:
            return None
        if datetime.now(timezone.utc) - entry["saved_at"] > SESSION_MAX_AGE:
            del _session_cache[key]
            return None
        return entry["data"]


def _save_session(key: str, data: dict) -> None:
    with _session_lock:
        _session_cache[key] = {"data": data, "saved_at": datetime.now(timezone.utc)}


def _drop_session(key: str) -> None:
    with _session_lock:
        _session_cache.pop(key, None)


def clear_session_cache() -> None:
    """Descarta todas as sessões guardadas. Usado ao limpar o cache local."""
    with _session_lock:
        _session_cache.clear()


# ---------------------------------------------------------------------------
# Helpers de texto
# ---------------------------------------------------------------------------

def _epoch_iso(valor: Any) -> Optional[str]:
    """
    Epoch do Moodle → ISO no fuso de Brasília. Zero significa "nunca acessou",
    não 1970.
    """
    try:
        segundos = int(valor or 0)
    except (TypeError, ValueError):
        return None
    if segundos <= 0:
        return None
    return datetime.fromtimestamp(segundos, TZ_BR).isoformat()


_TAG_RE = re.compile(r"(?is)<(script|style|svg|noscript)[^>]*>.*?</\1>")
_BLOCK_RE = re.compile(r"(?i)</(p|div|li|tr|h[1-6]|section|article)>")


def html_to_text(html: str, max_chars: int = 20_000) -> str:
    """Converte HTML em texto legível, preservando quebras de bloco."""
    html = _TAG_RE.sub(" ", html)
    html = _BLOCK_RE.sub("\n", html)
    html = re.sub(r"(?i)<br\s*/?>", "\n", html)
    text = unescape(re.sub(r"<[^>]+>", " ", html))
    text = re.sub(r"[ \t ]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return "\n".join(line.strip() for line in text.splitlines()).strip()[:max_chars]


def main_region(html: str) -> str:
    """
    Recorta a área principal do Moodle, se der; senão devolve a página toda.

    Para no início do rodapé: sem esse corte, a captura ia do `region-main` até
    o fim do documento e engolia navegação e rodapé até estourar o teto de
    caracteres — as disciplinas saíam todas com o mesmo tamanho, o do limite.
    """
    m = re.search(r'(?is)<(?:div|section)[^>]+id="region-main"[^>]*>(.*)', html)
    trecho = m.group(1) if m else html
    corte = re.search(r'(?is)<footer|id="page-footer"|class="[^"]*footer', trecho)
    return trecho[:corte.start()] if corte else trecho


# O Moodle monta o nome do evento grudando uma frase de contexto no nome da
# atividade ("Entrega 1 está marcado(a) para esta data"). Na tela do calendário
# dele isso faz sentido; numa lista de compromissos, é ruído em todo item.
_SUFIXOS_EVENTO = re.compile(
    r"\s*(está marcado\(a\) para esta data"
    r"|deve ser entregue nesta data"
    r"|is due|should be completed)\s*$",
    re.IGNORECASE,
)


def clean_event_title(name: str) -> str:
    """Tira a frase de contexto que o Moodle acrescenta ao nome da atividade."""
    return _SUFIXOS_EVENTO.sub("", (name or "").strip()).strip() or "Evento"


def clean_course_name(fullname: str) -> str:
    """
    Extrai o nome legível da disciplina.

    O Moodle devolve algo como `10275 - ENGENHARIA DE SOFTWARE - EAD54-12`:
    código do componente, nome, e código da turma. O aluno só quer o do meio,
    que também é o formato que o portal antigo entregava — manter igual evita
    duplicar disciplina no banco entre a versão velha e a nova.
    """
    nome = (fullname or "").strip()
    nome = re.sub(r"^\s*\d+\s*-\s*", "", nome)                  # código na frente
    nome = re.sub(r"\s*\(\s*DOF[_-]?\d+\s*\)\s*", " ", nome, flags=re.I)  # dof no meio
    nome = re.sub(r"\s*-\s*[A-Z]{2,}\d+[-\w]*\s*$", "", nome)   # turma no fim
    return nome.strip(" -") or (fullname or "").strip() or "Disciplina"


def dof_from_shortname(shortname: str) -> Optional[str]:
    """
    O `dof` vinha do HTML do portal (`a.link-moodle[data-dof]`). Descobrimos que
    ele já vem embutido no shortname do curso no Moodle — por exemplo
    `28743 - EAD54-12 (DOF_1414949)` — então o portal deixou de ser necessário.
    """
    m = re.search(r"DOF[_-]?(\d+)", shortname or "", re.IGNORECASE)
    return m.group(1) if m else None


def _normalizar(s: str) -> str:
    """
    Minúsculas, sem acento e sem pontuação separadora.

    A UNOESC escreve "Aula On-line" com hífen (é o nome oficial do módulo EAD),
    então casar "aula online" sem colapsar o hífen não encontra nada.
    """
    sem_acento = "".join(
        c for c in unicodedata.normalize("NFKD", s.lower()) if not unicodedata.combining(c)
    )
    texto = re.sub(r"\s+", " ", re.sub(r"[-_./]+", " ", sem_acento)).strip()
    # "on-line" vira "on line" ao colapsar o hífen; junta de volta para que um
    # único padrão ("online") case com as duas grafias.
    return re.sub(r"\bon line\b", "online", texto)


def guess_type(modulename: str, name: str) -> str:
    """
    Tipo do evento a partir do módulo, com o texto como desempate.

    O módulo é a fonte confiável; o nome só é consultado quando o módulo não
    diz nada (`other`), para não perder uma webconferência anunciada como
    atividade genérica.
    """
    modulename = (modulename or "").lower()
    tipo = MODULE_TYPE_MAP.get(modulename, "other")
    if tipo != "other":
        return tipo
    # Material não vira compromisso por causa do título: um arquivo chamado
    # "Aula On-line 3 - slides" é leitura, não encontro ao vivo.
    if modulename in MATERIAL_MODULES:
        return "other"
    texto = _normalizar(name or "")
    if any(p in texto for p in ("webconf", "web conf", "videoconf", "video conf",
                                "conferencia", "encontro online", "aula online",
                                "aula ao vivo", "meet", "zoom", "teams")):
        return "webconference"
    if any(p in texto for p in ("prova", "exame", "avaliacao objetiva")):
        return "exam"
    return tipo


# ---------------------------------------------------------------------------
# Webconferências
# ---------------------------------------------------------------------------
#
# Webconferência não é atividade do Moodle: não tem `assign` nem `quiz`, logo
# não gera evento de calendário. O professor anuncia no texto da página do
# curso, sempre no mesmo modelo institucional da UNOESC:
#
#     WEBCONFERÊNCIA 1
#     Data: 05/05/2026
#     Horário: 19h - 21h
#
# Ancorar em "WEBCONFERÊNCIA <n>" + "Data:" é o que separa o anúncio real do
# texto-modelo que fala de webconferência sem marcar nenhuma ("Lembre-se! É de
# suma importância que você participe…"), que aparece 3x mais vezes.

_WEBCONF_ANCORA = re.compile(
    r"WEBCONFER[ÊE]NCIA\s*(\d+)?.{0,80}?Data:\s*(\d{1,2})/(\d{1,2})/(\d{2,4})",
    re.IGNORECASE | re.DOTALL,
)
# "19h - 21h", "19h até 21h", "19h às 21h.", "19:30"
_WEBCONF_HORA = re.compile(r"Hor[áa]rio:\s*(\d{1,2})\s*(?:h|:)\s*(\d{2})?", re.IGNORECASE)


def extract_webconferences(texto: str, subject: str, course_url: str,
                           course_id: Any = None) -> list[dict]:
    """Eventos de webconferência garimpados do texto da página do curso."""
    eventos = []
    for m in _WEBCONF_ANCORA.finditer(texto or ""):
        numero, dia, mes, ano = m.group(1), m.group(2), m.group(3), m.group(4)
        ano_int = int(ano)
        if ano_int < 100:                      # "10/03/26" → 2026
            ano_int += 2000
        try:
            data = datetime(ano_int, int(mes), int(dia), tzinfo=TZ_BR)
        except ValueError:                     # data impossível: ignora
            continue

        # O horário vem logo depois da data; olha uma janela curta à frente.
        janela = texto[m.end():m.end() + 120]
        hora_m = _WEBCONF_HORA.search(janela)
        hora = f"{int(hora_m.group(1)):02d}:{hora_m.group(2) or '00'}" if hora_m else "19:00"

        titulo = f"Webconferência {numero}" if numero else "Webconferência"
        eventos.append({
            "id": str(uuid.uuid4()),
            "title": titulo,
            "date": data.strftime("%Y-%m-%d"),
            "time": hora,
            "description": " ".join(m.group(0).split())[:500],
            "subject": subject,
            "type": "webconference",
            "synced": False,
            "source": "moodle_course_text",
            "url": course_url,
            # Não há id de evento no Moodle — a webconferência não existe como
            # objeto lá. Curso + número é o que temos de estável.
            "moodle_event_id": f"webconf-{course_id}-{numero or data.strftime('%Y%m%d')}",
            "event_type": None,
            "module": "webconf",
            "course_id": course_id,
        })
    return eventos


# ---------------------------------------------------------------------------
# Cliente
# ---------------------------------------------------------------------------

class MoodleClient:
    """
    Cliente autenticado do Moodle. Síncrono de propósito: os endpoints do
    FastAPI o invocam via `asyncio.to_thread(...)`, como já faziam com o
    scraper, então a forma de chamada não muda.
    """

    def __init__(self, base_url: str = MOODLE_BASE) -> None:
        self.base = base_url.rstrip("/")
        self._client = httpx.Client(
            timeout=TIMEOUT,
            follow_redirects=True,
            headers={"User-Agent": USER_AGENT},
        )
        self.sesskey: Optional[str] = None
        # Id numérico do aluno no Moodle. Sai do `M.cfg` junto com o sesskey e
        # é o que `core_user_get_users_by_field` pede para devolver o perfil.
        self.userid: Optional[int] = None
        self._credentials: Optional[tuple[str, str]] = None

    # -- ciclo de vida ---------------------------------------------------

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> "MoodleClient":
        return self

    def __exit__(self, *exc: Any) -> None:
        self.close()

    # -- autenticação ----------------------------------------------------

    def login(self, username: str, password: str) -> None:
        """
        Autentica no Moodle, reaproveitando a sessão em cache quando possível.

        Lança PermissionError se as credenciais forem recusadas — é o que o
        FastAPI converte em 401.
        """
        self._credentials = (username, password)
        key = _cache_key(username, password)

        cached = _load_session(key)
        if cached:
            self._client.cookies.update(cached["cookies"])
            self.sesskey = cached["sesskey"]
            self.userid = cached.get("userid")
            if self._session_alive():
                return
            # Sessão morreu antes do TTL — descarta e faz login de verdade.
            _drop_session(key)
            self._client.cookies.clear()
            self.sesskey = None
            self.userid = None

        self._do_login(username, password)
        _save_session(key, {
            "cookies": dict(self._client.cookies),
            "sesskey": self.sesskey,
            "userid": self.userid,
        })

    def _do_login(self, username: str, password: str) -> None:
        page = self._client.get(f"{self.base}/login/index.php")
        token = re.search(r'name="logintoken"\s+value="([^"]+)"', page.text)

        resp = self._client.post(f"{self.base}/login/index.php", data={
            "username": username,
            "password": password,
            "logintoken": token.group(1) if token else "",
            "anchor": "",
        })

        # Continuar vendo o form de login significa credencial recusada.
        if re.search(r'name="logintoken"', resp.text):
            motivo = self._login_error_message(resp.text)
            raise PermissionError(
                (f"{motivo} " if motivo else "")
                + "Login recusado pelo Moodle. Use a matrícula no formato "
                "294833@unoesc.edu.br com a senha do portal."
            )

        self.sesskey = self._extract_sesskey(resp.text)
        self.userid = self._extract_userid(resp.text)
        if not self.sesskey or not self.userid:
            painel = self._client.get(f"{self.base}/my/").text
            self.sesskey = self.sesskey or self._extract_sesskey(painel)
            self.userid = self.userid or self._extract_userid(painel)
        if not self.sesskey:
            raise RuntimeError(
                "Login aceito mas não foi possível ler o sesskey — o Moodle pode "
                "ter mudado o layout da página."
            )

    @staticmethod
    def _login_error_message(html: str) -> str:
        """
        Lê o aviso que o Moodle desenha acima do form (`alert-danger`).

        Sem isso todo login recusado vira a mesma frase, e senha errada fica
        indistinguível de conta bloqueada por excesso de tentativas.
        """
        m = re.search(r'alert-danger[^>]*>(.*?)</div>', html, re.S)
        if not m:
            return ""
        return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", m.group(1))).strip()[:300]

    @staticmethod
    def _extract_sesskey(html: str) -> Optional[str]:
        m = re.search(r'"sesskey":"([^"]+)"', html)
        return m.group(1) if m else None

    @staticmethod
    def _extract_userid(html: str) -> Optional[int]:
        """
        Lê o `userId` do `M.cfg` — falta dele não é erro fatal, só desliga o
        perfil: a agenda inteira funciona sem ele.
        """
        m = re.search(r'"userId":\s*(\d+)', html) or re.search(r'"userid":\s*(\d+)', html)
        return int(m.group(1)) if m else None

    def _session_alive(self) -> bool:
        """Confere se os cookies em cache ainda valem, sem custo de login."""
        try:
            self._ajax("core_calendar_get_action_events_by_timesort",
                       {"limitnum": 1, "timesortfrom": 0})
            return True
        except Exception:
            return False

    # -- transporte ------------------------------------------------------

    def _ajax(self, methodname: str, args: dict) -> Any:
        """
        Chama a API interna que o próprio front-end do Moodle usa.

        Relogar automaticamente quando a sessão expira é o que permite manter o
        cache agressivo acima sem o aluno tomar erro no meio do uso.
        """
        try:
            return self._ajax_once(methodname, args)
        except PermissionError:
            if not self._credentials:
                raise
            self._do_login(*self._credentials)
            _save_session(_cache_key(*self._credentials), {
                "cookies": dict(self._client.cookies),
                "sesskey": self.sesskey,
            })
            return self._ajax_once(methodname, args)

    def _ajax_once(self, methodname: str, args: dict) -> Any:
        url = f"{self.base}/lib/ajax/service.php"
        resp = self._client.post(
            url,
            params={"sesskey": self.sesskey or "", "info": methodname},
            json=[{"index": 0, "methodname": methodname, "args": args}],
        )
        resp.raise_for_status()
        payload = resp.json()
        item = payload[0] if isinstance(payload, list) and payload else {}

        if item.get("error"):
            exc = item.get("exception") or {}
            code = exc.get("errorcode", "")
            msg = exc.get("message") or str(exc)
            if code in ("servicerequireslogin", "requireloginerror", "invalidsesskey"):
                raise PermissionError(f"Sessão do Moodle expirada ({code}).")
            raise RuntimeError(f"{methodname}: {code}: {msg}")

        data = item.get("data")
        # `core_courseformat_get_state` devolve o estado como STRING JSON.
        # Sem esse parse, a resposta boa é descartada silenciosamente.
        if isinstance(data, str):
            try:
                return json.loads(data)
            except json.JSONDecodeError:
                return data
        return data

    # -- consultas -------------------------------------------------------

    def profile(self) -> dict:
        """
        Dados cadastrais do próprio aluno, para a tela de perfil.

        `core_user_get_users_by_field` é a única função de usuário que esta
        instância deixa ligada no AJAX — `core_webservice_get_site_info` e as de
        nota respondem `servicenotavailable` (medido em 15/08/2026, veja
        `scripts/probes/probe_profile.py`). Ela devolve mais que a página de
        perfil pública: nome separado em primeiro/último, e-mail, departamento e
        os dois acessos como epoch, sem precisar raspar HTML traduzido.

        Só o próprio `userid` é consultado. O Moodle recusaria outro id, mas o
        ponto aqui é que nem existe caminho para pedir outro: o id sai da sessão
        do aluno, não de parâmetro de requisição.
        """
        if not self.userid:
            self.userid = self._extract_userid(self._client.get(f"{self.base}/my/").text)
        if not self.userid:
            raise RuntimeError(
                "Não foi possível identificar sua conta no Moodle — o layout da "
                "página pode ter mudado."
            )

        data = self._ajax("core_user_get_users_by_field",
                          {"field": "id", "values": [self.userid]})
        bruto = (data or [{}])[0] if isinstance(data, list) and data else {}

        nome = (bruto.get("fullname") or "").strip()
        return {
            "moodle_id": bruto.get("id") or self.userid,
            "fullname": nome,
            "firstname": (bruto.get("firstname") or "").strip(),
            "lastname": (bruto.get("lastname") or "").strip(),
            # `username` vem só a matrícula ("294833"); o e-mail é que traz o
            # endereço completo que o aluno usa para entrar.
            "username": (bruto.get("username") or "").strip(),
            "email": (bruto.get("email") or "").strip(),
            "department": (bruto.get("department") or "").strip(),
            "institution": (bruto.get("institution") or "").strip(),
            "city": (bruto.get("city") or "").strip(),
            "country": (bruto.get("country") or "").strip(),
            "timezone": (bruto.get("timezone") or "").strip(),
            "first_access": _epoch_iso(bruto.get("firstaccess")),
            "last_access": _epoch_iso(bruto.get("lastaccess")),
            "avatar": self._avatar_data_uri(bruto.get("profileimageurl")),
        }

    def _avatar_data_uri(self, url: Optional[str]) -> Optional[str]:
        """
        Baixa a foto de perfil e devolve como `data:` embutido.

        A URL do Moodle exige a sessão de lá, que o navegador do aluno não tem —
        o mesmo motivo pelo qual login automático é impossível. O servidor já
        está logado, então busca a imagem e manda os bytes junto do JSON.

        O Moodle sempre responde alguma coisa: sem foto enviada, cai no avatar
        cinza do tema (`/theme/image.php/.../u/f1`). Esse não vale a viagem —
        a tela desenha as iniciais, que dizem mais do que uma silhueta genérica.
        """
        if not url or "pluginfile.php" not in url:
            return None
        try:
            resp = self._client.get(url)
            resp.raise_for_status()
            tipo = resp.headers.get("content-type", "image/jpeg").split(";")[0]
            if not tipo.startswith("image/") or len(resp.content) > 300_000:
                return None
            return f"data:{tipo};base64," + base64.b64encode(resp.content).decode("ascii")
        except Exception as exc:  # foto é enfeite: nunca derruba o perfil
            logger.info("Foto de perfil não veio: %s", exc)
            return None

    def list_courses(self) -> list[dict]:
        """Disciplinas em que o aluno está matriculado."""
        data = self._ajax(
            "core_course_get_enrolled_courses_by_timeline_classification",
            {"offset": 0, "limit": 0, "classification": "all", "sort": "fullname",
             "customfieldname": "", "customfieldvalue": ""},
        )
        cursos = []
        for c in (data or {}).get("courses", []):
            shortname = c.get("shortname") or ""
            cursos.append({
                "course_id": c.get("id"),
                "name": clean_course_name(c.get("fullname") or shortname),
                "fullname": c.get("fullname") or "",
                "shortname": shortname,
                "dof": dof_from_shortname(shortname),
                "url": c.get("viewurl") or f"{self.base}/course/view.php?id={c.get('id')}",
                # Epoch em segundos, ou 0 quando o curso não tem data marcada.
                # É o que separa o semestre corrente das disciplinas encerradas:
                # o Moodle mantém a matrícula viva depois do fim do componente,
                # então sem isso a lista mistura 2026/1 com 2026/2.
                "start_date": c.get("startdate") or None,
                "end_date": c.get("enddate") or None,
            })
        return cursos

    def course_grades(self, cursos: list[dict]) -> dict[int, float]:
        """
        Nota final de cada disciplina, por `course_id`.

        Vem do relatório geral (`/grade/report/overview`), que entrega todos os
        cursos numa requisição só — o relatório por curso exigiria uma volta ao
        servidor por disciplina. É HTML e não AJAX porque as funções de nota do
        `service.php` respondem `servicenotavailable` nesta instância.

        A linha é casada pelo id no link e, se ele não vier, pelo nome completo
        do curso: o Moodle mudou o destino desse link entre versões (ora a
        disciplina, ora o relatório do usuário) e a primeira tentativa, que
        exigia `course/view.php`, não casou nada.

        Disciplina sem nota lançada aparece com `-` e fica fora do dicionário:
        ausência é informação (o semestre está em andamento), zero não seria.
        """
        try:
            resp = self._client.get(f"{self.base}/grade/report/overview/index.php")
            resp.raise_for_status()
        except Exception as exc:  # nota é enfeite: nunca derruba a agenda
            logger.warning("Relatório de notas não veio: %s", exc)
            return {}

        por_nome = {
            _normalizar(c.get("fullname") or ""): c["course_id"]
            for c in cursos
            if c.get("fullname")
        }

        notas: dict[int, float] = {}
        for linha in re.findall(r"(?is)<tr[^>]*>(.*?)</tr>", resp.text):
            celulas = [
                html_to_text(c).strip()
                for c in re.findall(r"(?is)<t[dh][^>]*>(.*?)</t[dh]>", linha)
            ]
            if len(celulas) < 2:
                continue

            m = re.search(r"(?i)href=\"[^\"]*(?:course/view|grade/report)[^\"]*[?&]id=(\d+)", linha)
            course_id = int(m.group(1)) if m else por_nome.get(_normalizar(celulas[0]))
            if not course_id:
                continue

            # A nota é a última célula numérica da linha; o Moodle escreve em
            # pt-BR ("95,00"), então a vírgula precisa virar ponto.
            for texto in reversed(celulas):
                valor = texto.replace(".", "").replace(",", ".")
                if re.fullmatch(r"\d+(?:\.\d+)?", valor):
                    notas[course_id] = float(valor)
                    break
        return notas

    def raw_calendar_events(
        self,
        months_back: int = MONTHS_BACK,
        months_ahead: int = MONTHS_AHEAD,
        today: Optional[datetime] = None,
    ) -> list[dict]:
        """
        Eventos do calendário, mês a mês, deduplicados por id.

        Usa `monthly_view` e não `action_events_by_timesort`: medindo as duas,
        o `action_events` só devolve o que tem ação pendente e perde os eventos
        de abertura (`open`) de questionário — numa conta real deu 8 eventos
        contra 10 do mensal, e numa disciplina sem pendência deu zero.
        """
        hoje = today or datetime.now(TZ_BR)
        vistos: set = set()
        eventos: list[dict] = []

        for i in range(-months_back, months_ahead + 1):
            ano = hoje.year + (hoje.month - 1 + i) // 12
            mes = (hoje.month - 1 + i) % 12 + 1
            data = self._ajax("core_calendar_get_calendar_monthly_view", {
                "year": ano, "month": mes, "courseid": 1, "categoryid": 0,
                "includenavigation": False, "mini": False,
            })
            for semana in (data or {}).get("weeks", []):
                for dia in semana.get("days", []):
                    for ev in dia.get("events", []):
                        if ev.get("id") in vistos:
                            continue
                        vistos.add(ev.get("id"))
                        eventos.append(ev)
        return eventos

    def calendar_events(self, **kwargs: Any) -> list[dict]:
        """Eventos já no formato canônico da aplicação."""
        return self.normalize_events(self.raw_calendar_events(**kwargs))

    @staticmethod
    def normalize_events(raw: list[dict]) -> list[dict]:
        """
        Converte eventos do Moodle para o formato que o banco espera.

        Use `timestart` e não `formattedtime`: este último vem como HTML pronto
        para renderizar (`<span class="dimmed_text">07:00 AM</span>`).
        """
        normalizados: list[dict] = []
        for ev in raw:
            ts = ev.get("timestart") or ev.get("timesort")
            if not ts:
                continue
            dt = datetime.fromtimestamp(int(ts), tz=TZ_BR)
            curso = ev.get("course") or {}
            modulename = ev.get("modulename") or ""

            normalizados.append({
                "id": str(uuid.uuid4()),
                "title": clean_event_title(ev.get("name") or ""),
                "date": dt.strftime("%Y-%m-%d"),
                "time": dt.strftime("%H:%M"),
                # 500 caracteres cortavam o enunciado no meio de uma palavra —
                # justamente onde costuma estar o que a atividade pede. O que o
                # Moodle manda no calendário já é o resumo dele; guardamos
                # inteiro e deixamos a tela decidir quanto mostrar.
                "description": html_to_text(ev.get("description") or "", 8_000),
                "subject": clean_course_name(curso.get("fullname") or curso.get("shortname") or ""),
                "type": guess_type(modulename, ev.get("name") or ""),
                "synced": False,
                "source": "moodle_calendar",
                "url": ev.get("url") or ev.get("viewurl") or "",
                # Identidade do evento no Moodle. É o que dá uma chave estável
                # de verdade: não muda se o professor renomear a atividade ou
                # mexer na data, ao contrário de um hash de título.
                "moodle_event_id": ev.get("id"),
                # Extras — úteis no frontend, ignorados pelo upsert.
                "event_type": ev.get("eventtype"),      # due | open | close
                "module": modulename,
                "course_id": curso.get("id"),
            })

        normalizados.sort(key=lambda e: (e["date"], e["time"] or ""))
        return normalizados

    def course_activities(self, course_id: int) -> list[dict]:
        """
        Atividades de uma disciplina.

        `core_course_get_contents` está desabilitado nesta instância; o estado
        do formato de curso entrega a mesma informação.
        """
        estado = self._ajax("core_courseformat_get_state", {"courseid": course_id})
        atividades = []
        for cm in (estado or {}).get("cm", []):
            url = cm.get("url") or ""
            m = re.search(r"/mod/([a-z0-9_]+)/", url)
            atividades.append({
                "cmid": cm.get("id"),
                "name": cm.get("name") or "",
                # `module` vem com o nome TRADUZIDO ("Tarefa", "Questionário"),
                # então o slug tem que sair da URL — filtrar por `module` nunca casa.
                "modname": m.group(1) if m else (cm.get("plugin") or "?"),
                "url": url,
            })
        return atividades

    def course_text(self, course_id: int) -> str:
        """Texto da página da disciplina (alimenta a tela de detalhe)."""
        resp = self._client.get(f"{self.base}/course/view.php", params={"id": course_id})
        return html_to_text(main_region(resp.text))

    def activity_content(self, url: str, title: str = "") -> dict:
        """
        Página de uma atividade, lida com a sessão que o backend já mantém.

        Este método já existiu e foi apagado quando o app virou público, porque
        alimentava o assistente que resolvia provas. Voltou em 14/08/2026 com
        um destino só: a tela de detalhe que o aluno abre. O conteúdo daqui
        **não entra no contexto do assistente** — ele continua montando o
        prompt a partir de data, disciplina e título, e só (`assistant.py`).

        O aluno já vê exatamente isto no Moodle dele; o que muda é não precisar
        logar de novo para ler.
        """
        if not url.startswith(self.base):
            raise PermissionError("Endereço fora do Moodle da UNOESC.")

        resp = self._client.get(url, follow_redirects=True)

        # Sessão caída: o Moodle responde 200 com a página de login em vez de
        # um 401, então o redirecionamento é o único sinal confiável.
        if "/login/index.php" in str(resp.url):
            raise PermissionError("A sessão do Moodle expirou.")

        resp.raise_for_status()
        regiao = main_region(resp.text)

        return {
            "intro": self._extract_intro(regiao, title),
            "status": self._extract_status(regiao),
            "files": self._extract_files(regiao),
            "url": str(resp.url),
        }

    # -- envio de tarefa -------------------------------------------------
    #
    # O envio no Moodle tem duas etapas, e é importante saber onde cada uma
    # para:
    #
    #   1. o arquivo sobe para a **área de rascunho** do aluno, que é a gaveta
    #      do seletor de arquivos e não pertence a tarefa nenhuma;
    #   2. `savesubmission` amarra esse rascunho à tarefa — daí em diante o
    #      professor já vê o arquivo, com o status "rascunho (não enviado)".
    #
    # Existe uma terceira, `action=submit`, que é o "enviar para avaliação" e
    # na maioria das tarefas o aluno não consegue desfazer. **Ela não está
    # aqui de propósito.** O app salva o rascunho, que é reversível, e deixa o
    # clique irreversível para o aluno dar no Moodle, sabendo o que faz.

    _HIDDEN_RE = re.compile(r"(?is)<input[^>]*type=[\"']hidden[\"'][^>]*>")

    @staticmethod
    def _hidden_fields(html: str) -> dict:
        campos = {}
        for tag in MoodleClient._HIDDEN_RE.findall(html):
            n = re.search(r"name=[\"']([^\"']+)[\"']", tag)
            v = re.search(r"value=[\"']([^\"']*)[\"']", tag)
            if n:
                campos[n.group(1)] = v.group(1) if v else ""
        return campos

    @staticmethod
    def _cmid_from_url(url: str) -> Optional[str]:
        m = re.search(r"/mod/assign/view\.php\?(?:[^#]*&)?id=(\d+)", url)
        return m.group(1) if m else None

    def submission_form(self, url: str) -> dict:
        """
        Lê o formulário de envio de uma tarefa e devolve o que a tela precisa
        mostrar e o que o POST vai precisar mandar.

        Nada aqui altera a tarefa: é um GET na mesma página que o aluno abriria.
        O `itemid` do rascunho é gerado **a cada abertura do formulário**, então
        ele não pode ser guardado: quem sobe o arquivo e quem salva o envio têm
        que usar o mesmo, na mesma sequência.
        """
        cmid = self._cmid_from_url(url)
        if not cmid:
            return {"can_submit": False,
                    "reason": "Esta atividade não é uma tarefa com envio."}

        resp = self._client.get(
            f"{self.base}/mod/assign/view.php",
            params={"id": cmid, "action": "editsubmission"},
            follow_redirects=True,
        )
        if "/login/index.php" in str(resp.url):
            raise PermissionError("A sessão do Moodle expirou.")

        # Medido em 15/08/2026 numa tarefa já entregue: o Moodle responde
        # **404** ao `editsubmission` em vez de uma página com aviso. Não é
        # erro nosso nem tarefa inexistente — é a forma dele de dizer "não há
        # formulário aqui", e a tela precisa disso, não de uma exceção.
        if resp.status_code == 404:
            return {"can_submit": False,
                    "reason": "O Moodle não abre o formulário desta tarefa — ela já foi "
                              "entregue, ou o prazo de envio terminou."}
        resp.raise_for_status()
        pagina = resp.text

        ocultos = self._hidden_fields(pagina)
        itemid_arquivos = ocultos.get("files_filemanager")
        itemid_texto = ocultos.get("onlinetext_editor[itemid]")

        # Sem formulário de envio o Moodle devolve a página normal da tarefa —
        # prazo encerrado, envio já entregue e travado, ou tarefa sem envio.
        if not (itemid_arquivos or itemid_texto):
            return {"can_submit": False,
                    "reason": "O Moodle não está aceitando envio nesta tarefa agora. "
                              "O prazo pode ter encerrado, ou o envio já foi entregue."}

        ctx = (re.search(r'"contextid"\s*:\s*(\d+)', pagina)
               or re.search(r'"context"\s*:\s*\{\s*"id"\s*:\s*(\d+)', pagina)
               or re.search(r"contextid=(\d+)", pagina))

        repo_id = None
        for m_up in re.finditer(r'"type"\s*:\s*"upload"', pagina):
            ids = re.findall(r'"id"\s*:\s*"?(\d+)"?', pagina[max(0, m_up.start() - 400):m_up.start()])
            if ids:
                repo_id = ids[-1]
                break

        limite = re.search(r"(?i)tamanho máximo para arquivos:\s*([\d.,]+)\s*([kmg])b", pagina)
        max_arquivos = re.search(r"(?i)número máximo de anexos:\s*(\d+)", pagina)

        return {
            "can_submit": True,
            "reason": None,
            "cmid": cmid,
            # O rascunho vem pré-carregado com o que já está no envio. Salvar
            # manda tudo o que estiver lá, não só o que o app subiu — então
            # esta lista precisa chegar à tela, ou o aluno acha que trocou o
            # arquivo quando na verdade somou mais um.
            "existing_files": self._draft_files(itemid_arquivos) if itemid_arquivos else [],
            "accepts_files": bool(itemid_arquivos),
            "accepts_text": bool(itemid_texto),
            "itemid_files": itemid_arquivos,
            "itemid_text": itemid_texto,
            "ctx_id": ctx.group(1) if ctx else None,
            "repo_id": repo_id,
            "max_files": int(max_arquivos.group(1)) if max_arquivos else None,
            "moodle_max_label": limite.group(0) if limite else None,
            "hidden": ocultos,
        }

    @staticmethod
    def submission_state(status: list[dict]) -> dict:
        """
        Lê a tabela de status e diz se a tarefa já foi entregue.

        O Moodle distingue três situações que a tela precisa tratar diferente:
        nada enviado, rascunho salvo (dá para mexer) e enviado para avaliação
        (acabou). A frase vem traduzida, então casamos o texto em português e
        deixamos o inglês como reserva — o tema da UNOESC já apareceu nos dois.
        """
        estado = {"submitted": False, "draft": False, "label": None, "modified": None}
        for linha in status or []:
            rotulo = _normalizar(linha.get("label", ""))
            valor = linha.get("value", "")
            valor_norm = _normalizar(valor)

            if "status de envio" in rotulo or "submission status" in rotulo:
                estado["label"] = valor
                if "enviado para avaliacao" in valor_norm or "submitted for grading" in valor_norm:
                    estado["submitted"] = True
                elif "rascunho" in valor_norm or "draft" in valor_norm:
                    estado["draft"] = True
            elif "ultima modificacao" in rotulo or "last modified" in rotulo:
                if valor and valor != "-":
                    estado["modified"] = valor
        return estado

    def _draft_files(self, itemid: str) -> list[dict]:
        """
        O que já está na área de rascunho desta tarefa.

        O Moodle pré-carrega aqui os arquivos do envio atual, então esta é a
        lista que o aluno veria ao abrir o seletor de arquivos lá — e é a que
        vai junto no `savesubmission`. Falha aqui não impede o envio: a lista é
        informação, não permissão.
        """
        try:
            resp = self._client.post(
                f"{self.base}/repository/draftfiles_ajax.php",
                params={"action": "list"},
                data={
                    "sesskey": self.sesskey or "",
                    "client_id": "agenda",
                    "itemid": itemid,
                    "filepath": "/",
                    "draftpath": "/",
                },
            )
            resp.raise_for_status()
            dados = resp.json()
        except Exception as exc:
            logger.info("Rascunho não pôde ser listado: %s", exc)
            return []

        arquivos = []
        for f in (dados or {}).get("list", []):
            nome = f.get("filename") or ""
            # O Moodle usa "." para representar a própria pasta.
            if nome and nome != ".":
                arquivos.append({"name": nome, "size": int(f.get("size") or 0)})
        return arquivos

    def upload_to_draft(self, form: dict, filename: str, content: bytes) -> dict:
        """
        Põe um arquivo na área de rascunho do aluno.

        Ainda não é envio: enquanto `save_submission` não rodar, a tarefa
        continua exatamente como estava.
        """
        if not (form.get("ctx_id") and form.get("repo_id") and form.get("itemid_files")):
            raise RuntimeError(
                "Não consegui preparar o envio de arquivo nesta tarefa — o Moodle "
                "não entregou o seletor de arquivos."
            )

        resp = self._client.post(
            f"{self.base}/repository/repository_ajax.php",
            params={"action": "upload"},
            data={
                "sesskey": self.sesskey or "",
                "repo_id": form["repo_id"],
                "itemid": form["itemid_files"],
                "ctx_id": form["ctx_id"],
                "savepath": "/",
                "title": filename,
                "author": "",
                "license": "unknown",
                "overwrite": "1",
            },
            files={"repo_upload_file": (filename, content, "application/octet-stream")},
        )
        resp.raise_for_status()
        try:
            dados = resp.json()
        except ValueError as exc:
            raise RuntimeError("O Moodle respondeu o upload num formato inesperado.") from exc

        if isinstance(dados, dict) and dados.get("error"):
            raise RuntimeError(str(dados["error"])[:300])
        return dados if isinstance(dados, dict) else {"resposta": dados}

    def save_submission(self, form: dict, online_text: str = "") -> list[dict]:
        """
        Amarra o rascunho à tarefa — o "salvar mudanças" do Moodle.

        Devolve a tabela de status relida da página **depois** do POST. É o
        único jeito honesto de dizer ao aluno que deu certo: nós não decidimos
        que foi salvo, o Moodle é que diz.
        """
        dados = dict(form.get("hidden") or {})
        dados["sesskey"] = self.sesskey or ""
        dados["action"] = "savesubmission"
        dados["submitbutton"] = "Salvar mudanças"
        if form.get("accepts_text"):
            # O editor do Moodle guarda HTML; um texto simples vira parágrafo.
            corpo = unescape(online_text or "").strip()
            dados["onlinetext_editor[text]"] = (
                "<p>" + corpo.replace("\n", "<br>") + "</p>" if corpo else ""
            )
            dados.setdefault("onlinetext_editor[format]", "1")

        resp = self._client.post(
            f"{self.base}/mod/assign/view.php",
            params={"id": form["cmid"]},
            data=dados,
            follow_redirects=True,
        )
        if "/login/index.php" in str(resp.url):
            raise PermissionError("A sessão do Moodle expirou no meio do envio.")
        resp.raise_for_status()

        # Continuar no formulário significa que o Moodle recusou (arquivo fora
        # do tipo aceito, prazo fechado, campo obrigatório vazio).
        if "editsubmission" in str(resp.url) or "_qf__mod_assign_submission_form" in resp.text:
            erro = re.search(r'(?is)class="[^"]*(?:alert-danger|error)[^"]*"[^>]*>(.*?)</div>',
                             resp.text)
            raise RuntimeError(
                html_to_text(erro.group(1), 300) if erro
                else "O Moodle não aceitou o envio e não disse o motivo."
            )

        return self._extract_status(main_region(resp.text))

    # A página de uma tarefa tem duas partes com naturezas diferentes: o
    # enunciado, que é texto corrido, e a tabela de status do envio, que é um
    # conjunto de pares rótulo/valor. Achatar as duas no mesmo bloco de texto
    # produzia aquela parede em que "Status de envio" aparecia duas vezes e
    # "Adicionar envio" — que no Moodle é um botão — virava um parágrafo.

    _TABELA_RE = re.compile(r'(?is)<table[^>]*class="[^"]*generaltable[^"]*"[^>]*>(.*?)</table>')
    _LINHA_RE = re.compile(r"(?is)<tr[^>]*>(.*?)</tr>")
    _CELULA_RE = re.compile(r"(?is)<t([hd])[^>]*>(.*?)</t\1>")

    # Linhas que só fazem sentido dentro do Moodle: rótulo de botão, cabeçalho
    # de seção repetido, e as datas de abertura/vencimento — que esta tela já
    # mostra no topo, com o dia da semana por extenso.
    _RUIDO_RE = re.compile(
        r"^(condições de conclusão|adicionar envio|editar envio|status de envio"
        r"|aberto:.*|vencimento:.*|-)$",
        re.IGNORECASE,
    )

    @classmethod
    def _extract_status(cls, html: str) -> list[dict]:
        """A tabela de status do envio como pares rótulo/valor."""
        m = cls._TABELA_RE.search(html)
        if not m:
            return []

        linhas: list[dict] = []
        for linha in cls._LINHA_RE.finditer(m.group(1)):
            celulas = [
                html_to_text(c.group(2), 400) for c in cls._CELULA_RE.finditer(linha.group(1))
            ]
            if len(celulas) != 2:
                continue
            rotulo, valor = celulas[0].strip(), celulas[1].strip()
            # Linha sem valor não informa nada; "-" é o vazio do próprio Moodle.
            if rotulo and valor and valor != "-":
                linhas.append({"label": rotulo, "value": valor})
        return linhas

    @classmethod
    def _extract_intro(cls, html: str, title: str = "") -> str:
        """
        Só o enunciado: corta a partir da tabela de status, que vem depois dele
        na página e é devolvida separada por `_extract_status`.
        """
        m = cls._TABELA_RE.search(html)
        texto = html_to_text(html[: m.start()] if m else html, 20_000)

        alvo = _normalizar(title)
        linhas = [
            linha
            for linha in texto.splitlines()
            if not cls._RUIDO_RE.match(linha.strip())
            # O título da atividade encabeça a página do Moodle, e esta tela já
            # o mostra em destaque — repetido, viraria a primeira linha do
            # enunciado.
            and not (alvo and _normalizar(linha) == alvo)
        ]
        return "\n".join(linhas).strip()

    @staticmethod
    def _extract_files(html: str) -> list[dict]:
        """
        Anexos da atividade — o enunciado costuma estar num PDF, não no texto.

        Os links de arquivo do Moodle passam todos por `/pluginfile.php/`; é o
        que separa um anexo de um link qualquer dentro da descrição.
        """
        vistos: set[str] = set()
        arquivos: list[dict] = []

        for m in re.finditer(
            r'(?is)<a[^>]+href="([^"]*/pluginfile\.php/[^"]+)"[^>]*>(.*?)</a>', html
        ):
            href = unescape(m.group(1))
            if href in vistos:
                continue
            vistos.add(href)

            nome = html_to_text(m.group(2), 200) or href.rsplit("/", 1)[-1]
            arquivos.append({"name": unquote(nome), "url": href})

        return arquivos

    # -- fluxo completo --------------------------------------------------

    def run(self, username: str, password: str, with_content: bool = False) -> dict:
        """
        Login → disciplinas → calendário. Substitui `ScraperService.run`.

        A página de cada curso continua sendo buscada, mas só para extrair as
        webconferências — que não existem como atividade no Moodle e por isso
        nunca aparecem no calendário. O texto em si é descartado:
        `with_content` fica desligado porque esse campo existia para o
        `parser.py` garimpar eventos com o Gemini, e o frontend declara
        `content` sem nunca renderizar.

        Retorna:
            {
              "subjects": [{id, name, content, dof, course_id, course_url}, ...],
              "calendar_events": [{title, date, time, description, subject, type, ...}, ...],
            }
        """
        self.login(username, password)

        cursos = self.list_courses()
        logger.info("%d disciplina(s) encontradas", len(cursos))

        subjects = []
        webconfs: list[dict] = []
        for i, c in enumerate(cursos, start=1):
            conteudo = ""
            try:
                texto = self.course_text(c["course_id"])
                webconfs.extend(
                    extract_webconferences(texto, c["name"], c["url"], c["course_id"])
                )
                if with_content:
                    conteudo = texto
            except Exception as exc:  # acessório: não derruba a busca da agenda
                logger.warning(
                    "[%d/%d] %s: sem texto (%s)", i, len(cursos), c["name"], exc
                )

            subjects.append({
                "id": str(uuid.uuid4()),
                "name": c["name"],
                "content": conteudo,
                "dof": c["dof"],
                "course_id": c["course_id"],
                "course_url": c["url"],
                "start_date": c.get("start_date"),
                "end_date": c.get("end_date"),
            })

        # Uma requisição para todas as disciplinas — feita depois do laço para
        # não repetir por curso.
        notas = self.course_grades(cursos)
        for sub in subjects:
            nota = notas.get(sub["course_id"])
            if nota is not None:
                sub["final_grade"] = nota

        eventos = self.calendar_events()
        logger.info(
            "%d evento(s) no calendário + %d webconferência(s) no texto",
            len(eventos),
            len(webconfs),
        )

        eventos.extend(webconfs)
        eventos.sort(key=lambda e: (e["date"], e["time"] or ""))
        return {"subjects": subjects, "calendar_events": eventos}


# ---------------------------------------------------------------------------
# Autoteste manual
# ---------------------------------------------------------------------------
#
#   cd backend && python -m app.moodle
#
# Roda o fluxo inteiro contra a conta informada e imprime um resumo. Serve como
# critério de aceite da migração: os números têm que bater com os que os
# scripts de sondagem já mediram.

if __name__ == "__main__":  # pragma: no cover
    import getpass
    from collections import Counter

    usuario = input("Usuário do Moodle: ").strip()
    senha = getpass.getpass("Senha: ")

    with MoodleClient() as cliente:
        resultado = cliente.run(usuario, senha)

        print("\n--- disciplinas ---")
        for s in resultado["subjects"]:
            print(f"  [{s['course_id']}] {s['name']}  dof={s['dof']}  "
                  f"({len(s['content'])} chars)")

        eventos = resultado["calendar_events"]
        print(f"\n--- {len(eventos)} eventos ---")
        for e in eventos:
            print(f"  {e['date']} {e['time']}  {e['type']:14} {e['event_type'] or '':6} "
                  f"{e['title'][:46]:48} {e['subject'][:28]}")

        print("\n--- por tipo ---")
        for tipo, n in Counter(e["type"] for e in eventos).most_common():
            print(f"  {n:3}x {tipo}")
        print("--- por módulo ---")
        for mod, n in Counter(e["module"] for e in eventos).most_common():
            print(f"  {n:3}x {mod}")

        print("\n--- cache de sessão (2º login deve ser instantâneo) ---")
        inicio = datetime.now()
        cliente.login(usuario, senha)
        print(f"  relogin em {(datetime.now() - inicio).total_seconds():.2f}s")
