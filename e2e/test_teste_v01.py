"""Regressões do teste do cliente "TESTE_Znuny-V01" (03/09/2026) — NÃO-destrutivo.

Cada teste trava um NOK do relatório (docs/RESPOSTA-TESTE-ZNUNY-V01.md):
- E1: o calendário dava 500 na carga direta (TDZ em `calendarName`) — e nenhum
  teste abria a página. `test_toda_pagina_renderiza` fecha a CLASSE: toda página
  do menu e toda aba do cliente, por carga direta, sem 500 e sem erro de JS;
- A3: a página do cliente rolava na horizontal e não havia botão "Filas";
- D3: a busca do console só olhava o título — número do chamado não achava nada;
- C2: login do portal com senha errada dizia "ou serviço indisponível".
"""
import re

import pytest

from config import ADMIN_BASE, ADMIN_PASS, ADMIN_USER, AURORA_TENANT_ID, TENANTS
from helpers import admin_login, is_login_page

# Chamado do roteiro D (checklist "Onboarding de estação" aplicado).
CHECKLIST_TICKET_ID = "84"
CHECKLIST_TICKET_TITLE = "Liberar acesso ao ERP para a nova analista"

CLIENT_TABS = [
    "usuarios", "filas", "chamados", "atividades", "consumo", "agentes", "faturas",
    "faturamento", "conhecimento", "catalogo", "identidade", "editar", "contratos/novo",
]


@pytest.fixture
def logged_admin(page):
    admin_login(page, ADMIN_BASE, ADMIN_USER, ADMIN_PASS)
    return page


def _menu_paths(pg) -> list[str]:
    """Links internos do menu do console (inclui o submenu Znuny)."""
    pg.goto(f"{ADMIN_BASE}/", wait_until="networkidle")
    paths = set(pg.eval_on_selector_all(
        "header a[href^='/']", "els => els.map(e => e.getAttribute('href'))"))
    znuny = pg.get_by_role("button", name=re.compile("Znuny"))
    if znuny.count():
        znuny.first.click()
        pg.wait_for_timeout(500)
        paths |= set(pg.eval_on_selector_all(
            "a[href^='/znuny']", "els => els.map(e => e.getAttribute('href'))"))
    paths.add("/znuny/calendario")  # o caso do E1, garantido mesmo se o menu mudar
    return sorted(p for p in paths if p and p != "/login")


def test_toda_pagina_renderiza(logged_admin):
    """Carga DIRETA (SSR) de cada página: status < 500, sem tela de erro, sem pageerror."""
    pg = logged_admin
    erros: list[str] = []
    pg.on("pageerror", lambda e: erros.append(str(e)))
    paths = _menu_paths(pg) + [f"/clientes/{AURORA_TENANT_ID}"] + [
        f"/clientes/{AURORA_TENANT_ID}/{t}" for t in CLIENT_TABS]
    falhas = []
    for path in paths:
        erros.clear()
        resp = pg.goto(f"{ADMIN_BASE}{path}", wait_until="networkidle")
        body = pg.inner_text("body")
        if resp is None or resp.status >= 500 or "before initialization" in body or erros:
            falhas.append(f"{path}: status={resp and resp.status} erros={erros[:1]}")
        assert not is_login_page(pg), f"{path}: caiu no login (sessão SSR perdida)"
    assert not falhas, "páginas quebradas:\n" + "\n".join(falhas)


@pytest.mark.parametrize("width", [1280, 1480])
def test_cliente_sem_rolagem_horizontal_e_com_filas(logged_admin, width):
    pg = logged_admin
    pg.set_viewport_size({"width": width, "height": 900})
    pg.goto(f"{ADMIN_BASE}/clientes/{AURORA_TENANT_ID}", wait_until="networkidle")
    scroll, inner = pg.evaluate("[document.documentElement.scrollWidth, innerWidth]")
    assert scroll <= inner, f"rolagem horizontal: conteúdo {scroll}px em janela {inner}px"
    filas = pg.get_by_role("link", name="Filas", exact=True)
    assert filas.count() == 1 and filas.is_visible(), "botão 'Filas' ausente ou fora da tela"
    filas.click()
    pg.wait_for_url(re.compile(r"/filas$"))


def test_calendario_carga_direta_e_nomes_no_seletor(logged_admin):
    pg = logged_admin
    resp = pg.goto(f"{ADMIN_BASE}/znuny/calendario", wait_until="networkidle")
    assert resp is not None and resp.status == 200
    assert "before initialization" not in pg.inner_text("body")
    pg.get_by_role("combobox").first.click()
    opcoes = pg.get_by_role("option").all_inner_texts()
    assert "Padrão" in opcoes[0]
    assert any(o.startswith("Calendário 3") for o in opcoes)
    # o texto da opção não pode vir truncado com reticências pelo CSS
    truncado = pg.eval_on_selector_all(
        "[role=option] span", "els => els.some(e => e.scrollWidth > e.clientWidth + 1)")
    assert not truncado, "rótulos do seletor de calendário cortados"


@pytest.mark.parametrize("termo", ["#84", "84", "ERP para a nova analista"])
def test_busca_de_chamado_por_id_e_titulo(logged_admin, termo):
    pg = logged_admin
    pg.goto(f"{ADMIN_BASE}/atendimento", wait_until="networkidle")
    pg.get_by_placeholder(re.compile("Buscar|busca", re.I)).first.fill(termo)
    pg.get_by_text(CHECKLIST_TICKET_TITLE).first.wait_for(timeout=15000)


def test_busca_de_chamado_pelo_numero_da_tela(logged_admin):
    """O número que a lista MOSTRA (#2026…) tem que achar o próprio chamado."""
    pg = logged_admin
    pg.goto(f"{ADMIN_BASE}/atendimento/{CHECKLIST_TICKET_ID}", wait_until="networkidle")
    numero = re.search(r"#?(\d{10,})", pg.inner_text("body"))
    assert numero, "detalhe do chamado não mostra o número"
    pg.goto(f"{ADMIN_BASE}/atendimento", wait_until="networkidle")
    pg.get_by_placeholder(re.compile("Buscar|busca", re.I)).first.fill(numero.group(1))
    pg.get_by_text(CHECKLIST_TICKET_TITLE).first.wait_for(timeout=15000)


def test_portal_senha_errada_diz_que_e_senha(page):
    t = TENANTS["aurora"]
    page.goto(f"{t['base']}/login", wait_until="networkidle")
    page.fill('input[autocomplete="username"]', "eduardo.salvi")
    page.fill('input[autocomplete="current-password"]', "senha-errada-de-proposito")
    page.get_by_role("button", name="Entrar").click()
    page.get_by_text(re.compile("incorret", re.I)).first.wait_for(timeout=15000)
    assert "indisponível" not in page.inner_text("body")
