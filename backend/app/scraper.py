"""
Módulo de scraping — UNOESC Agenda.

Utiliza Playwright (modo assíncrono) para:
  1. Abrir um navegador headless
  2. Fazer login no portal acadêmico da UNOESC
  3. Navegar por cada disciplina matriculada
  4. Extrair todo o conteúdo de texto relevante (avisos, fóruns, atividades)
  5. Retornar uma lista de disciplinas com o texto extraído
"""

import asyncio
import uuid
from typing import Optional

from playwright.async_api import async_playwright, Page, Browser, TimeoutError as PlaywrightTimeoutError


# URL base do portal acadêmico UNOESC
BASE_URL = "https://acad.unoesc.edu.br"

# URL principal do portal acadêmico UNOESC
PORTAL_URL = "https://acad.unoesc.edu.br/academico/portal/index.jspa"

# URL da página de disciplinas EAD
EAD_URL = "https://acad.unoesc.edu.br/academico/portal/modules/ead/aulaOnlineAcademico.jspa"

# Tempo máximo de espera por seletores (em milissegundos)
# O portal pode ser lento para carregar
TIMEOUT_MS = 30_000


class ScraperService:
    """Serviço responsável pelo login e extração de conteúdo do portal UNOESC."""

    async def run(self, username: str, password: str) -> list[dict]:
        """
        Ponto de entrada principal do scraper.

        Parâmetros:
            username: Matrícula ou CPF do aluno no portal UNOESC.
            password: Senha do portal.

        Retorna:
            Lista de dicionários com 'id', 'name' e 'content' de cada disciplina.

        Lança:
            PermissionError: Se as credenciais forem inválidas.
            RuntimeError: Para outros erros durante a extração.
        """
        async with async_playwright() as pw:
            # Inicia o navegador em modo headless (sem interface gráfica)
            browser: Browser = await pw.chromium.launch(headless=True)
            page: Page = await browser.new_page()

            try:
                subjects = await self._scrape(page, username, password)
            finally:
                # Garante que o navegador sempre será fechado
                await browser.close()

        return subjects

    # ------------------------------------------------------------------
    # Métodos privados
    # ------------------------------------------------------------------

    async def _scrape(self, page: Page, username: str, password: str) -> list[dict]:
        """Orquestra o fluxo completo de login e extração."""
        await self._login(page, username, password)
        subject_links = await self._get_subject_links(page)
        subjects = []

        for link_info in subject_links:
            content = await self._extract_subject_content(page, link_info["url"])
            subjects.append({
                "id": str(uuid.uuid4()),
                "name": link_info["name"],
                "content": content,
            })

        return subjects

    async def _login(self, page: Page, username: str, password: str) -> None:
        """
        Navega até o portal e preenche o formulário de login.

        O portal UNOESC é um sistema próprio; os campos de login ficam em um
        formulário padrão com os identificadores '#j_username' e '#j_password'.
        Após login bem-sucedido, o painel carrega uma navbar com classe
        '.navbar-inverse' e um 'div#content' com o painel principal.
        """
        await page.goto(PORTAL_URL, wait_until="domcontentloaded")

        # Aguarda o campo de usuário aparecer para garantir que a página carregou
        await page.wait_for_selector("#j_username", timeout=TIMEOUT_MS)

        # Preenche usuário e senha
        await page.fill("#j_username", username)
        await page.fill("#j_password", password)

        # Clica no botão de submissão do formulário de login
        await page.click("input[type='submit'], button[type='submit']")

        # Aguarda o redirecionamento para o painel após o login
        try:
            # O painel possui uma navbar com '.navbar-inverse' e um 'div#content'
            await page.wait_for_selector(".navbar-inverse, #content", timeout=TIMEOUT_MS)
            print("[Scraper] Login bem-sucedido, navegando para disciplinas...")
        except PlaywrightTimeoutError as exc:
            # Se não chegou ao painel, verifica se há mensagem de erro de login
            error_msg = await self._get_login_error(page)
            if error_msg:
                raise PermissionError(f"Credenciais inválidas: {error_msg}") from exc
            raise PermissionError("Falha no login: o portal não respondeu como esperado.") from exc

    async def _get_login_error(self, page: Page) -> Optional[str]:
        """Tenta capturar a mensagem de erro exibida pelo portal após falha no login."""
        try:
            # O portal exibe erros dentro de elementos com a classe 'jive-error-box' ou similar
            error_element = await page.query_selector(".jive-error-box, .error-message, .alert-error")
            if error_element:
                return await error_element.inner_text()
        except Exception:
            pass
        return None

    async def _get_subject_links(self, page: Page) -> list[dict]:
        """
        Extrai os links e nomes de todas as disciplinas matriculadas.

        No portal UNOESC, as disciplinas EAD ficam disponíveis na página
        '/academico/portal/modules/ead/aulaOnlineAcademico.jspa'. O método
        navega até essa página e procura por links de disciplinas/turmas.
        Se nenhum link específico for encontrado, retorna a própria página
        como uma única "disciplina" de fallback.
        """
        subject_links = []

        print("[Scraper] Navegando para a página de disciplinas EAD...")
        await page.goto(EAD_URL, wait_until="domcontentloaded")

        try:
            # Aguarda o conteúdo principal carregar
            await page.wait_for_selector("#content, body", timeout=TIMEOUT_MS)

            # Procura por links de disciplinas/turmas: padrões com /ead/ ou /community/
            links = await page.query_selector_all(
                "a[href*='/ead/'], a[href*='/community/']"
            )

            for link in links:
                href = await link.get_attribute("href")
                name = (await link.inner_text()).strip()
                if href and name:
                    # Normaliza URL relativa para absoluta usando BASE_URL
                    if href.startswith("/"):
                        href = BASE_URL + href
                    subject_links.append({"name": name, "url": href})

        except PlaywrightTimeoutError:
            # Página não carregou no tempo esperado
            pass

        if not subject_links:
            # Fallback: retorna a própria página EAD como uma única "disciplina"
            print("[Scraper] Nenhum link de disciplina encontrado; usando fallback para página EAD.")
            subject_links = [{"name": "Aula on-line EAD", "url": EAD_URL}]

        print(f"[Scraper] {len(subject_links)} disciplina(s) encontrada(s).")
        return subject_links

    async def _extract_subject_content(self, page: Page, url: str) -> str:
        """
        Navega para a página de uma disciplina e extrai todo o texto relevante.

        Busca conteúdo na área principal da página (#content), que no portal
        UNOESC contém avisos, atividades e materiais da disciplina.
        Como fallback, extrai o conteúdo do body inteiro.
        """
        try:
            await page.goto(url, wait_until="domcontentloaded")

            # Aguarda o conteúdo principal da disciplina carregar
            await page.wait_for_selector(
                "#content, #mainbar, body",
                timeout=TIMEOUT_MS,
            )

            # Extrai o texto da área principal da página da disciplina
            content_element = await page.query_selector("#content")

            if content_element:
                # Pega todo o conteúdo da área principal do portal
                text = (await content_element.inner_text()).strip()
            else:
                # Fallback: extrai o body inteiro se #content não existir
                body_element = await page.query_selector("body")
                text = (await body_element.inner_text()).strip() if body_element else ""

            return text

        except PlaywrightTimeoutError:
            # Conteúdo não carregou no tempo esperado; retorna string vazia
            return ""
        except Exception:
            return ""
