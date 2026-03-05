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


# URL principal do portal acadêmico UNOESC
PORTAL_URL = "https://acad.unoesc.edu.br/academico/portal/index.jspa"

# Tempo máximo de espera por seletores (em milissegundos)
TIMEOUT_MS = 15_000


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

        O portal UNOESC usa o Jive SBS; os campos de login ficam em um
        formulário padrão com os identificadores '#username' e '#password'.
        """
        await page.goto(PORTAL_URL, wait_until="domcontentloaded")

        # Aguarda o campo de usuário aparecer para garantir que a página carregou
        await page.wait_for_selector("#username", timeout=TIMEOUT_MS)

        # Preenche usuário e senha
        await page.fill("#username", username)
        await page.fill("#password", password)

        # Clica no botão de submissão do formulário de login
        await page.click("input[type='submit'], button[type='submit']")

        # Aguarda o redirecionamento para o painel após o login
        try:
            # O painel possui um elemento com a classe 'j-community-sidebar' ou similar
            await page.wait_for_selector(".j-main-content, #jive-main-content", timeout=TIMEOUT_MS)
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

        No portal UNOESC (Jive), as disciplinas aparecem como 'espaços' (spaces)
        na barra lateral ou no painel de comunidades do aluno.
        """
        subject_links = []

        try:
            # Aguarda o menu de disciplinas/comunidades carregar
            await page.wait_for_selector(
                ".jive-widget-content a, .j-browse-space-link, .jive-community-link",
                timeout=TIMEOUT_MS,
            )

            # Seleciona todos os links de disciplinas visíveis na página
            links = await page.query_selector_all(
                ".jive-widget-content a[href*='/community/'], "
                ".j-browse-space-link, "
                ".jive-community-link"
            )

            for link in links:
                href = await link.get_attribute("href")
                name = (await link.inner_text()).strip()
                if href and name:
                    # Normaliza URL relativa para absoluta
                    if href.startswith("/"):
                        base = "https://acad.unoesc.edu.br"
                        href = base + href
                    subject_links.append({"name": name, "url": href})
        except PlaywrightTimeoutError:
            # Nenhuma disciplina encontrada no seletor padrão; retorna lista vazia
            pass

        return subject_links

    async def _extract_subject_content(self, page: Page, url: str) -> str:
        """
        Navega para a página de uma disciplina e extrai todo o texto relevante.

        Busca conteúdo em:
          - Avisos/anúncios da disciplina
          - Posts de fórum
          - Descrições de atividades e tarefas
        """
        try:
            await page.goto(url, wait_until="domcontentloaded")

            # Aguarda o conteúdo principal da disciplina carregar
            await page.wait_for_selector(
                ".jive-rendered-content, .j-content-body, #jive-main-content",
                timeout=TIMEOUT_MS,
            )

            # Extrai o texto de todo o conteúdo principal da página da disciplina
            content_elements = await page.query_selector_all(
                ".jive-rendered-content, "   # Conteúdo HTML renderizado (avisos, posts)
                ".jive-subject, "             # Assunto/título de posts
                ".jive-body-main, "           # Corpo principal de mensagens
                ".jive-widget-content"        # Widgets com conteúdo do espaço
            )

            texts = []
            for el in content_elements:
                text = (await el.inner_text()).strip()
                if text:
                    texts.append(text)

            return "\n\n".join(texts)

        except PlaywrightTimeoutError:
            # Conteúdo não carregou no tempo esperado; retorna string vazia
            return ""
        except Exception:
            return ""
