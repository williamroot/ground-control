"""Login helpers compartilhados pelos testes."""
from playwright.sync_api import Page


def _await_logged_in(page: Page, base: str) -> None:
    """Espera a transição pós-login (SPA) terminar.

    O wait_for_url resolve assim que a URL vira "/", mas o form de login pode
    coexistir por um instante durante a troca de página. Esperamos o campo de
    senha SUMIR do DOM — sinal de que o dashboard substituiu o login. (Se um
    login realmente falhar, o campo nunca some e isto estoura, falhando claro.)
    """
    page.wait_for_url(f"{base}/", timeout=15000)
    page.wait_for_selector('input[autocomplete="current-password"]', state="detached", timeout=15000)
    page.wait_for_load_state("networkidle")


def portal_login(page: Page, base: str, user: str, password: str) -> None:
    """Login no portal do cliente (campo é E-MAIL)."""
    page.goto(f"{base}/login", wait_until="networkidle")
    page.fill('input[autocomplete="email"]', user)
    page.fill('input[autocomplete="current-password"]', password)
    page.get_by_role("button", name="Entrar").click()
    _await_logged_in(page, base)


def admin_login(page: Page, base: str, user: str, password: str) -> None:
    """Login no Console (agente Znuny, login curto)."""
    page.goto(f"{base}/login", wait_until="networkidle")
    page.fill('input[autocomplete="username"]', user)
    page.fill('input[autocomplete="current-password"]', password)
    page.get_by_role("button", name="Entrar").click()
    _await_logged_in(page, base)


def is_login_page(page: Page) -> bool:
    """True se a página atual é a tela de login (campo de senha presente)."""
    return page.locator('input[autocomplete="current-password"]').count() > 0
