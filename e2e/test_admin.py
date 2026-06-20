"""Console de Administração — regressões de browser (NÃO-destrutivo).

Cobre:
- login de agente + lista de clientes;
- detalhe de ticket no /atendimento RENDERIZA (regressão: vinha em branco e o
  timer "Iniciar" quebrava por casing capitalizado vs snake_case);
- sub-rotas de cliente (Faturas #1P, Agentes #1R, Novo Contrato) RENDERIZAM
  suas próprias páginas (regressão: rota aninhada sem <NuxtPage/> mostrava o
  detalhe do cliente).
"""
import pytest

from config import ADMIN_BASE, ADMIN_PASS, ADMIN_USER, AURORA_TENANT_ID, AURORA_TICKET_ID
from helpers import admin_login, is_login_page


@pytest.fixture
def logged_admin(page):
    admin_login(page, ADMIN_BASE, ADMIN_USER, ADMIN_PASS)
    return page


def test_login_e_lista_de_clientes(logged_admin):
    assert "Aurora" in logged_admin.inner_text("body")


def test_atendimento_detalhe_renderiza(logged_admin):
    """Regressão (casing): detalhe do ticket mostra título + thread; timer iniciável."""
    pg = logged_admin
    pg.goto(f"{ADMIN_BASE}/atendimento/{AURORA_TICKET_ID}", wait_until="networkidle")
    pg.wait_for_timeout(1000)
    assert not is_login_page(pg)
    assert pg.locator("h1").first.inner_text().strip(), "título do ticket veio vazio"
    body = pg.inner_text("body")
    assert "Histórico" in body
    # timer idle só aparece com znuny_ticket_id válido (quebrava no bug do casing)
    assert pg.get_by_role("button", name="Iniciar").count() > 0


SUBROUTES = [("faturas", "Faturas"), ("agentes", "Agentes de inventário"), ("contratos/novo", "Novo contrato")]


@pytest.mark.parametrize("path,expected_h1", SUBROUTES)
def test_subrotas_de_cliente_renderizam(logged_admin, path, expected_h1):
    """Regressão (rota aninhada): cada sub-página renderiza a SI MESMA, não o detalhe."""
    pg = logged_admin
    pg.goto(f"{ADMIN_BASE}/clientes/{AURORA_TENANT_ID}/{path}", wait_until="networkidle")
    pg.wait_for_timeout(1000)
    h1 = pg.locator("h1").first.inner_text()
    assert expected_h1 in h1, f"{path}: h1='{h1}' (esperava '{expected_h1}')"
    # não pode ser o detalhe do cliente (que tem 'Dados cadastrais')
    assert "Dados cadastrais" not in pg.inner_text("body")
