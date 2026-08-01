"""
Módulo de scraping — UNOESC Agenda.

Fluxo:
  1. Login no portal acadêmico (acad.unoesc.edu.br)
  2. Acessa a página EAD e extrai cards de disciplina do semestre vigente
  3. Para cada disciplina, gera URL de SSO via moodleRooms.jspa e navega
     para o Moodle (on.unoesc.edu.br) — onde estão as atividades reais
  4. Extrai:
     a) Texto da página de cada curso (alimenta o Gemini para webconferências)
     b) Eventos estruturados do calendário consolidado do Moodle
        (/calendar/view.php?view=upcoming) — prazos exatos sem LLM

Implementado com a API síncrona do Playwright para evitar incompatibilidades
do asyncio com o uvicorn no Windows. O endpoint FastAPI deve invocar
`ScraperService.run` via `asyncio.to_thread(...)`.

Os cookies do portal são reaproveitados entre chamadas (ver `_authenticated`),
então só o primeiro request de uma sessão paga o custo do login.
"""

import hashlib
import re
import threading
import uuid
from contextlib import contextmanager
from datetime import date, datetime, timedelta, timezone
from typing import Iterator, Optional
from urllib.parse import urlparse

from playwright.sync_api import sync_playwright, Page, Browser, BrowserContext

# URLs base
BASE_URL = "https://acad.unoesc.edu.br"
PORTAL_URL = f"{BASE_URL}/academico/portal/index.jspa"
EAD_URL = f"{BASE_URL}/academico/portal/modules/ead/aulaOnlineAcademico.jspa"
MOODLE_LINK_URL = f"{BASE_URL}/academico/portal/modules/portal/moodleRooms.jspa"
PORTAL_LOGIN_URL = f"{BASE_URL}/academico/login.jsp"

TIMEOUT_MS = 30_000

# Lookahead em dias para o calendário Moodle (180 = ~6 meses, cobre o semestre)
CALENDAR_LOOKAHEAD_DAYS = 180

# Mapeia o componente do Moodle para o tipo de evento da nossa aplicação
COMPONENT_TYPE_MAP = {
    "mod_assign": "deadline",
    "mod_quiz": "exam",
    "mod_forum": "deadline",
    "mod_hsuforum": "deadline",
    "mod_workshop": "deadline",
    "mod_lesson": "deadline",
    "mod_choice": "other",
    "mod_feedback": "other",
}

# Brasil não tem horário de verão desde 2019; UTC-3 é estável.
TZ_BR = timezone(timedelta(hours=-3))


def current_semester(today: Optional[date] = None) -> str:
    """Retorna o semestre vigente no formato 'AAAA/N' (ex: '2026/1')."""
    today = today or date.today()
    return f"{today.year}/{1 if today.month <= 6 else 2}"


# ---------------------------------------------------------------------------
# Cache de sessão do portal
# ---------------------------------------------------------------------------
#
# Cada chamada ao scraper abria um Chromium novo e refazia o login do zero.
# Abrir uma atividade no assistente de IA custava um login inteiro; abrir três,
# três logins. Guardamos os cookies do portal (`storage_state` do Playwright)
# entre as chamadas e só relogamos quando a sessão realmente morreu.
#
# Fica só em memória de propósito — cookies de sessão não vão para o disco.
# Reiniciar o backend descarta tudo e o próximo request faz login normalmente.

# Tempo máximo que uma sessão fica no cache antes de ser descartada por idade.
# É só um limite superior: a validade real é testada a cada uso.
SESSION_MAX_AGE = timedelta(minutes=30)

_session_cache: dict[str, dict] = {}
_session_lock = threading.Lock()


def _session_cache_key(username: str, password: str) -> str:
    """
    Identifica a sessão por usuário + hash da senha.

    Incluir a senha (como hash, nunca em claro) garante que trocar de
    credenciais force um login de verdade, em vez de reaproveitar a sessão
    antiga e dar a impressão de que a senha nova foi aceita.
    """
    digest = hashlib.sha256(password.encode("utf-8")).hexdigest()
    return f"{username}:{digest}"


def _load_session(key: str) -> Optional[dict]:
    """Devolve o `storage_state` guardado, se ainda estiver dentro da validade."""
    with _session_lock:
        entry = _session_cache.get(key)
        if not entry:
            return None
        if datetime.now(timezone.utc) - entry["saved_at"] > SESSION_MAX_AGE:
            del _session_cache[key]
            return None
        return entry["state"]


def _save_session(key: str, state: dict) -> None:
    with _session_lock:
        _session_cache[key] = {"state": state, "saved_at": datetime.now(timezone.utc)}


def clear_session_cache() -> None:
    """Descarta todas as sessões guardadas. Usado ao limpar o cache local."""
    with _session_lock:
        _session_cache.clear()


class ScraperService:
    """Serviço responsável pelo login e extração de conteúdo do portal UNOESC."""

    def __init__(self, semester: Optional[str] = None) -> None:
        self.semester = semester or current_semester()

    # ------------------------------------------------------------------
    # Sessão autenticada (reaproveitada entre chamadas)
    # ------------------------------------------------------------------

    @contextmanager
    def _authenticated(
        self, username: str, password: str
    ) -> Iterator[tuple[BrowserContext, Page]]:
        """
        Abre um Chromium e entrega um contexto já autenticado no portal.

        Reaproveita os cookies da última sessão do mesmo usuário quando eles
        ainda valem — evita refazer o login a cada request. Se a sessão tiver
        morrido, faz o login normalmente e guarda os cookies novos.

        Lança PermissionError se as credenciais forem inválidas.
        """
        cache_key = _session_cache_key(username, password)

        with sync_playwright() as pw:
            browser: Browser = pw.chromium.launch(headless=True)
            try:
                state = _load_session(cache_key)
                context, page = self._new_context(browser, state)

                if state and self._is_logged_in(page):
                    print("[Scraper] Sessão reaproveitada — login pulado")
                else:
                    if state:
                        # Cookies velhos: joga fora o contexto e começa limpo
                        print("[Scraper] Sessão expirada — refazendo login")
                        context.close()
                        context, page = self._new_context(browser, None)

                    self._login(page, username, password)
                    _save_session(cache_key, context.storage_state())

                yield context, page
            finally:
                browser.close()

    @staticmethod
    def _new_context(
        browser: Browser, state: Optional[dict]
    ) -> tuple[BrowserContext, Page]:
        """Cria um contexto (opcionalmente com cookies restaurados) e sua página."""
        context: BrowserContext = (
            browser.new_context(storage_state=state) if state else browser.new_context()
        )
        page: Page = context.new_page()
        # Aceita silenciosamente qualquer dialog que apareça (alerts JS)
        page.on("dialog", lambda d: d.accept())
        return context, page

    @staticmethod
    def _is_logged_in(page: Page) -> bool:
        """
        Testa se os cookies restaurados ainda valem: o portal devolve o form de
        login (com `#j_username`) quando a sessão caiu.
        """
        try:
            page.goto(PORTAL_URL, wait_until="domcontentloaded", timeout=TIMEOUT_MS)
            return page.query_selector("#j_username") is None
        except Exception as exc:
            print(f"[Scraper] Falha ao validar sessão em cache: {exc}")
            return False

    def _create_sso_url(self, context: BrowserContext, dof: str) -> Optional[str]:
        """
        Reproduz o JS `MoodleRoomsAccessID.criarLink` (POST em moodleRooms.jspa)
        e devolve a URL de SSO para o Moodle da disciplina.
        """
        response = context.request.post(
            MOODLE_LINK_URL,
            form={"action": "criarLinkMoodleRooms", "dof": dof},
            headers={
                "X-Requested-With": "XMLHttpRequest",
                "Referer": EAD_URL,
            },
        )
        if response.status != 200:
            return None
        data = response.json()
        return (data or {}).get("url")

    def login(self, username: str, password: str) -> None:
        """
        Valida as credenciais no portal e deixa a sessão aquecida no cache.

        Usado por `/api/login`: o custo do login é pago uma vez aqui e as
        chamadas seguintes reaproveitam os cookies.

        Lança PermissionError se as credenciais forem inválidas.
        """
        with self._authenticated(username, password):
            pass

    def run(self, username: str, password: str) -> dict:
        """
        Executa o fluxo completo: login → disciplinas → conteúdo + calendário.

        Função síncrona — chame via `asyncio.to_thread(scraper.run, ...)` em
        contextos async (FastAPI).

        Retorna:
            {
              "subjects": [{id, name, content}, ...],
              "calendar_events": [{title, date, time, description, subject, type, source_url}, ...],
            }

        Lança PermissionError em caso de credenciais inválidas.
        """
        with self._authenticated(username, password) as (context, page):
            print("[Scraper] 1/3 Sessão do portal pronta")

            print("[Scraper] 2/3 Extraindo cards de disciplina...")
            cards = self._extract_subject_cards(page)
            print(f"[Scraper]      {len(cards)} disciplina(s) encontradas")

            course_id_to_subject: dict[str, str] = {}
            subjects: list[dict] = []
            moodle_base: Optional[str] = None

            for i, card in enumerate(cards, start=1):
                print(f"[Scraper]      [{i}/{len(cards)}] {card['name']}...")
                content, base, course_id = self._fetch_moodle_course_text(
                    context, card["dof"]
                )
                print(f"[Scraper]            -> {len(content)} chars, course_id={course_id}, base={base}")
                if base and not moodle_base:
                    moodle_base = base
                if course_id:
                    course_id_to_subject[course_id] = card["name"]
                subjects.append({
                    "id": str(uuid.uuid4()),
                    "name": card["name"],
                    "content": content,
                    "dof": card["dof"],
                })

            calendar_events: list[dict] = []
            if moodle_base:
                print(f"[Scraper] 3/3 Lendo calendário consolidado em {moodle_base}...")
                calendar_events = self._fetch_calendar_events(
                    context, moodle_base, course_id_to_subject
                )
                print(f"[Scraper]      {len(calendar_events)} evento(s) capturado(s)")
                # Anexa a URL do curso aos subjects (consumido pelo parser
                # para enriquecer eventos do Gemini com link direto)
                for subj in subjects:
                    course_id = next(
                        (cid for cid, name in course_id_to_subject.items() if name == subj["name"]),
                        None,
                    )
                    if course_id:
                        subj["course_url"] = PORTAL_LOGIN_URL
            else:
                print("[Scraper] 3/3 Sem moodle_base detectada — pulando calendário")

        return {"subjects": subjects, "calendar_events": calendar_events}

    def fetch_activity_content(self, username: str, password: str, dof: str, activity_url: str) -> str:
        """
        Faz login no portal, entra no Moodle via SSO e navega até a URL
        da atividade para extrair o conteúdo completo (enunciado, instruções, critérios).
        Para quizzes com múltiplas páginas, percorre todas automaticamente.
        """
        with self._authenticated(username, password) as (context, _page):
            sso_url = self._create_sso_url(context, dof)
            if not sso_url:
                return ""

            # Autentica no Moodle
            moodle_page = context.new_page()
            moodle_page.goto(sso_url, wait_until="domcontentloaded", timeout=60_000)
            moodle_page.wait_for_timeout(2000)

            # Navega pra atividade específica
            moodle_page.goto(activity_url, wait_until="domcontentloaded", timeout=60_000)
            try:
                moodle_page.wait_for_selector("#region-main, main", timeout=45_000)
            except Exception:
                pass
            moodle_page.wait_for_timeout(1000)

            # Se é um quiz com páginas, percorre todas
            all_text_parts: list[str] = []

            if "mod/quiz/attempt" in activity_url:
                # Extrai a página atual
                all_text_parts.append(self._extract_page_text(moodle_page))

                # Descobre quantas páginas existem e percorre cada uma
                page_links = moodle_page.evaluate("""() => {
                    const nav = document.querySelector('.qn_buttons, .othernav');
                    if (!nav) return [];
                    const links = nav.querySelectorAll('a[href*="page="]');
                    const pages = new Set();
                    for (const a of links) {
                        const m = a.getAttribute('href').match(/page=(\\d+)/);
                        if (m) pages.add(parseInt(m[1]));
                    }
                    return [...pages].sort((a, b) => a - b);
                }""")

                # Pega a página atual da URL
                current_page_match = re.search(r"page=(\d+)", activity_url)
                current_page = int(current_page_match.group(1)) if current_page_match else 0

                for pg in page_links:
                    if pg == current_page:
                        continue  # Já extraímos
                    pg_url = re.sub(r"page=\d+", f"page={pg}", activity_url)
                    if "page=" not in activity_url:
                        pg_url = activity_url + f"&page={pg}"
                    try:
                        moodle_page.goto(pg_url, wait_until="domcontentloaded", timeout=60_000)
                        moodle_page.wait_for_timeout(1500)
                        all_text_parts.append(self._extract_page_text(moodle_page))
                    except Exception as exc:
                        print(f"[Scraper] Falha ao carregar página {pg} do quiz: {exc}")
            else:
                all_text_parts.append(self._extract_page_text(moodle_page))

            moodle_page.close()
            return "\n\n---\n\n".join(all_text_parts).strip()

    @staticmethod
    def _extract_page_text(page: Page) -> str:
        """Extrai o texto da área principal de uma página do Moodle."""
        return page.evaluate("""() => {
            const main = document.querySelector('#region-main') || document.querySelector('main');
            if (!main) return document.body.innerText || '';
            return main.innerText || '';
        }""") or ""

    def generate_sso_link(self, username: str, password: str, dof: str) -> Optional[str]:
        """
        Faz login rápido no portal e gera um link SSO fresco para o Moodle.
        Retorna a URL que, ao ser aberta no navegador do usuário, o loga
        diretamente no curso sem precisar digitar credenciais.
        """
        with self._authenticated(username, password) as (context, _page):
            return self._create_sso_url(context, dof)

    # ------------------------------------------------------------------
    # Login
    # ------------------------------------------------------------------

    def _login(self, page: Page, username: str, password: str) -> None:
        page.goto(PORTAL_URL, wait_until="domcontentloaded")
        page.wait_for_selector("#j_username", timeout=TIMEOUT_MS)
        page.fill("#j_username", username)
        page.fill("#j_password", password)
        with page.expect_navigation(wait_until="domcontentloaded", timeout=TIMEOUT_MS):
            page.click("input[type='submit']")
        page.wait_for_timeout(1500)

        # Se ainda existir campo de senha, login falhou
        if page.query_selector("input[type='password']"):
            raise PermissionError("Credenciais inválidas para o portal UNOESC.")

    # ------------------------------------------------------------------
    # Extração das disciplinas (cards)
    # ------------------------------------------------------------------

    def _extract_subject_cards(self, page: Page) -> list[dict]:
        """
        Navega para a página EAD, ativa a aba do semestre vigente e extrai
        os cards de disciplina visíveis.
        """
        page.goto(EAD_URL, wait_until="domcontentloaded")
        page.wait_for_timeout(1500)

        # Clica na aba do semestre desejado (se existir)
        page.evaluate(
            """
            (semestre) => {
                const buttons = document.querySelectorAll(".tablinks");
                for (const b of buttons) {
                    if (b.textContent.trim() === semestre) { b.click(); return; }
                }
            }
            """,
            self.semester,
        )
        page.wait_for_timeout(600)

        cards = page.evaluate(
            """
            (semestre) => {
                const result = [];
                // Procura o painel da aba ativa do semestre solicitado
                const panel = document.querySelector(`[id$="${semestre}"].tabcontent`)
                           || document.querySelector(".tabcontent[style*='block']")
                           || document.querySelector(".tabcontent");
                if (!panel) return result;
                for (const card of panel.querySelectorAll(".card")) {
                    const titleEl = card.querySelector("h2 b");
                    const moodleLink = card.querySelector("a.link-moodle");
                    if (!titleEl || !moodleLink) continue;
                    const dof = moodleLink.getAttribute("data-dof");
                    if (!dof) continue;
                    result.push({ name: titleEl.textContent.trim(), dof });
                }
                return result;
            }
            """,
            self.semester,
        )
        return cards

    # ------------------------------------------------------------------
    # Acesso ao Moodle via SSO e extração do conteúdo do curso
    # ------------------------------------------------------------------

    def _fetch_moodle_course_text(
        self, context: BrowserContext, dof: str
    ) -> tuple[str, Optional[str], Optional[str]]:
        """
        Gera a URL SSO da disciplina, navega no Moodle e extrai o texto
        + identificadores.

        Retorna:
            (texto_da_area_principal, moodle_base_url, course_id_do_moodle)
        """
        try:
            sso_url = self._create_sso_url(context, dof)
            if not sso_url:
                return "", None, None

            moodle_page = context.new_page()
            try:
                moodle_page.goto(sso_url, wait_until="domcontentloaded", timeout=45_000)
                try:
                    moodle_page.wait_for_selector("#region-main, main", timeout=TIMEOUT_MS)
                except Exception:
                    pass
                moodle_page.wait_for_timeout(1500)

                final_url = moodle_page.url
                parsed = urlparse(final_url)
                base = f"{parsed.scheme}://{parsed.netloc}"
                course_id_match = re.search(r"course/view\.php\?id=(\d+)", final_url)
                course_id = course_id_match.group(1) if course_id_match else None

                text = self._extract_moodle_text(moodle_page)
                return text, base, course_id
            finally:
                moodle_page.close()
        except Exception as exc:
            print(f"[Scraper] Falha ao buscar Moodle (dof={dof}): {exc}")
            return "", None, None

    # ------------------------------------------------------------------
    # Calendário consolidado do Moodle (todos os prazos em um só lugar)
    # ------------------------------------------------------------------

    def _fetch_calendar_events(
        self,
        context: BrowserContext,
        moodle_base: str,
        course_id_to_subject: dict[str, str],
    ) -> list[dict]:
        """
        Lê o calendário consolidado do Moodle (próximos eventos) e devolve uma
        lista de eventos já estruturados, prontos para sincronização — sem LLM.
        """
        url = f"{moodle_base}/calendar/view.php?view=upcoming&lookahead={CALENDAR_LOOKAHEAD_DAYS}"
        page = context.new_page()
        try:
            page.goto(url, wait_until="domcontentloaded", timeout=45_000)
            try:
                page.wait_for_selector(".calendarwrapper", timeout=TIMEOUT_MS)
            except Exception:
                pass
            page.wait_for_timeout(1000)

            raw_events = page.evaluate(
                """() => {
                    const events = [];
                    for (const node of document.querySelectorAll(".calendarwrapper .event")) {
                        const courseId = node.getAttribute("data-course-id") || "";
                        const eventId = node.getAttribute("data-event-id") || "";
                        const component = node.getAttribute("data-event-component") || "";
                        const eventtype = node.getAttribute("data-event-eventtype") || "";
                        const title = (node.querySelector("h3.name")?.textContent || "").trim();
                        // O link "time=TIMESTAMP" carrega o instante do evento (Unix seconds)
                        const timeLink = node.querySelector('a[href*="time="]');
                        let timestamp = null;
                        if (timeLink) {
                            const m = timeLink.getAttribute("href").match(/time=(\\d+)/);
                            if (m) timestamp = parseInt(m[1], 10);
                        }
                        const courseLink = node.querySelector('a[href*="/course/view.php"]');
                        const courseName = courseLink ? courseLink.textContent.trim() : "";
                        const description = (node.querySelector(".description-content")?.innerText || "").trim();
                        const actionLink = node.querySelector(".card-footer a.card-link")?.getAttribute("href") || "";
                        events.push({
                            courseId, eventId, component, eventtype,
                            title, timestamp, courseName, description, actionLink,
                        });
                    }
                    return events;
                }"""
            )
        finally:
            page.close()

        return self._normalize_calendar_events(raw_events, course_id_to_subject, moodle_base)

    @staticmethod
    def _normalize_calendar_events(
        raw_events: list[dict],
        course_id_to_subject: dict[str, str],
        moodle_base: str,
    ) -> list[dict]:
        """
        Converte eventos brutos do calendário Moodle para o formato canônico.
        Filtra eventos sem timestamp e mapeia component → tipo.
        """
        normalized: list[dict] = []
        for ev in raw_events:
            ts = ev.get("timestamp")
            if not ts:
                continue
            dt_local = datetime.fromtimestamp(int(ts), tz=TZ_BR)
            event_type = COMPONENT_TYPE_MAP.get(ev.get("component", ""), "other")

            # Prefere o nome de disciplina mapeado via SSO; fallback no rótulo do calendário
            course_id = str(ev.get("courseId", ""))
            subject_name = course_id_to_subject.get(course_id) or ev.get("courseName") or "Disciplina"

            description = (ev.get("description") or "").strip()

            # URL: link direto da atividade no Moodle (mod/assign, mod/quiz, etc.)
            # Salva o actionLink original — o endpoint /api/open-course cuida do login.
            action = ev.get("actionLink") or ""
            if action and not action.startswith("http"):
                action = f"{moodle_base}/{action.lstrip('/')}"
            url = action or f"{moodle_base}/course/view.php?id={course_id}" if course_id else PORTAL_LOGIN_URL

            normalized.append({
                "id": str(uuid.uuid4()),
                "title": ev.get("title") or "Evento",
                "date": dt_local.strftime("%Y-%m-%d"),
                "time": dt_local.strftime("%H:%M"),
                "description": description[:500],
                "subject": subject_name,
                "type": event_type,
                "synced": False,
                "source": "moodle_calendar",
                "url": url,
            })

        # Ordena por data/hora crescente
        normalized.sort(key=lambda e: (e["date"], e["time"] or ""))
        return normalized

    @staticmethod
    def _extract_moodle_text(page: Page) -> str:
        """
        Extrai texto relevante da página do curso no Moodle.
        Foca em #region-main (área principal). Inclui a URL e título do curso
        como cabeçalho, para o LLM ter contexto.
        """
        title = page.title()
        url = page.url

        main_text = page.evaluate(
            """
            () => {
                const main = document.querySelector("#region-main") || document.querySelector("main") || document.body;
                return main.innerText || "";
            }
            """
        )
        # Compacta espaços em branco múltiplos
        main_text = re.sub(r"\n{3,}", "\n\n", main_text).strip()
        header = f"# {title}\nURL: {url}\n\n"
        return header + main_text
