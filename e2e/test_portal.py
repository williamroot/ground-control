"""Portal do cliente (white-label) — regressões de browser.

Cobre, de forma NÃO-destrutiva:
- login + branding por tenant;
- sessão SSR sobrevive a carga direta/refresh (regressão do bug onde /tickets,
  /ativos, /faturas, / redirecionavam p/ /login — host do tenant não repassado);
- isolamento cross-tenant (gsid de um tenant é 401 no outro);
- #1S "Melhorar com IA" (assist devolve rascunho estruturado);
- CSAT guards (422 em chamado aberto; 409 em chamado já avaliado).
"""
import pytest

from config import AURORA_CLOSED_TICKET, AURORA_TICKET_ID, TENANTS
from helpers import is_login_page, portal_login

TENANT_KEYS = list(TENANTS)
PROTECTED_PATHS = ["/", "/tickets", "/ativos", "/faturas"]


@pytest.mark.parametrize("tkey", TENANT_KEYS)
def test_login_e_branding(page, tkey):
    t = TENANTS[tkey]
    portal_login(page, t["base"], t["user"], t["password"])
    body = page.inner_text("body")
    assert t["name"] in body
    assert "Seus contratos" in body


@pytest.mark.parametrize("tkey", TENANT_KEYS)
@pytest.mark.parametrize("path", PROTECTED_PATHS)
def test_pagina_protegida_sobrevive_a_carga_direta(page, tkey, path):
    """Regressão: carga SSR direta de página autenticada NÃO pode cair no login."""
    t = TENANTS[tkey]
    portal_login(page, t["base"], t["user"], t["password"])
    page.goto(f"{t['base']}{path}", wait_until="networkidle")
    page.wait_for_timeout(800)
    assert not is_login_page(page), f"{path} redirecionou p/ /login (sessão SSR perdida)"


def test_isolamento_cross_tenant(browser):
    """gsid do Aurora deve ser rejeitado (401) em endpoint do TechNova."""
    a, tn = TENANTS["aurora"], TENANTS["technova"]
    ctx = browser.new_context()
    try:
        pg = ctx.new_page()
        pg.set_default_timeout(30000)
        portal_login(pg, a["base"], a["user"], a["password"])
        gsid = next((c["value"] for c in ctx.cookies() if c["name"] == "gsid"), None)
        assert gsid, "gsid não setado após login"
        # gsid é tenant-scoped: enviado a OUTRO tenant → 403 (autenticado, mas
        # sem direito àquele tenant). Sem cookie nenhum seria 401.
        r = ctx.request.get(f"{tn['base']}/api/portal/me", headers={"cookie": f"gsid={gsid}"})
        assert r.status == 403, f"cross-tenant deveria ser 403, veio {r.status}"
    finally:
        ctx.close()


def test_1s_melhorar_com_ia(context):
    """#1S: assist devolve título + corpo estruturado (read-only)."""
    a = TENANTS["aurora"]
    pg = context.new_page()
    portal_login(pg, a["base"], a["user"], a["password"])
    r = context.request.post(
        f"{a['base']}/api/portal/ticketing/assist",
        data={"title": "", "body": "o sistema ta lento de manha e nao abre, ja reiniciei e nao adiantou"},
    )
    assert r.status == 200, f"assist veio {r.status}"
    d = r.json()
    assert d.get("title", "").strip(), "assist não devolveu título"
    assert len(d.get("body", "")) > 20, "assist não devolveu corpo"


def test_csat_guard_chamado_aberto(context):
    """CSAT em chamado ABERTO → 422 ticket_not_closed."""
    a = TENANTS["aurora"]
    pg = context.new_page()
    portal_login(pg, a["base"], a["user"], a["password"])
    r = context.request.post(
        f"{a['base']}/api/portal/tickets/{AURORA_TICKET_ID}/csat",
        data={"score": 5, "comment": None},
    )
    assert r.status == 422, f"esperava 422 (aberto), veio {r.status}"


def test_csat_guard_ja_avaliado(context):
    """CSAT em chamado fechado JÁ avaliado → 409 csat_already_submitted."""
    a = TENANTS["aurora"]
    pg = context.new_page()
    portal_login(pg, a["base"], a["user"], a["password"])
    r = context.request.post(
        f"{a['base']}/api/portal/tickets/{AURORA_CLOSED_TICKET}/csat",
        data={"score": 4, "comment": None},
    )
    assert r.status == 409, f"esperava 409 (já avaliado), veio {r.status}"
