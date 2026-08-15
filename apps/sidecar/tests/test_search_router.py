"""GET /v1/search — busca federada do portal (Spec #3 V6).

- 200 com tickets/assets escopados pelo customer_id do tenant (via GI fake)
- q curto (<2) → 422
- cross-tenant vazio: KB de um tenant nunca aparece na busca do outro
- escopo por papel (#1H): helpdesk não acha chamado de colega da mesma
  empresa (ele levaria 404 ao clicar — a busca vazava o conteúdo E quebrava a
  navegação); admin do portal continua vendo a empresa inteira
"""

from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from gerti_sidecar import db
from gerti_sidecar.auth.session import encode_session
from gerti_sidecar.config import get_settings
from gerti_sidecar.integrations import znuny_ticket
from gerti_sidecar.main import create_app
from gerti_sidecar.models import KbArticle, Tenant, TenantBranding, ZnunyInstance


async def _seed_tenant(session, inst_id, *, subdomain: str, customer_id: str):
    t = Tenant(
        legal_name=subdomain,
        trade_name=subdomain,
        document=subdomain,
        znuny_customer_id=customer_id,
        znuny_instance_id=inst_id,
        subdomain=subdomain,
    )
    session.add(t)
    await session.flush()
    session.add(TenantBranding(tenant_id=t.id, display_name=subdomain))
    return t


@pytest.mark.asyncio
async def test_search_scoped_by_tenant_and_short_q_422(
    engine, app_session_factory, session, monkeypatch
):
    monkeypatch.setenv("SESSION_SECRET", "test-secret-32-chars-minimum-xxxx")
    monkeypatch.setenv("ENVIRONMENT", "test")
    get_settings.cache_clear()

    inst = ZnunyInstance(
        name="i",
        base_url="http://z",
        db_dsn_secret_ref="x",
        webservice_token_secret_ref="x",
        webhook_signing_secret_ref="x",
        mode="pool",
    )
    session.add(inst)
    await session.flush()
    aurora = await _seed_tenant(session, inst.id, subdomain="aurora-s", customer_id="AURORA")
    beta = await _seed_tenant(session, inst.id, subdomain="beta-s", customer_id="BETA")
    await session.flush()
    # KB só do tenant aurora — nunca deve vazar p/ a busca de beta.
    session.add(
        KbArticle(
            tenant_id=aurora.id,
            slug="reset-vpn",
            title="Como resetar a VPN",
            summary="Passo a passo",
            body_markdown="...",
            category="Rede",
            tags=[],
            visibility="public",
            status="published",
        )
    )
    await session.commit()

    async def fake_search_tickets(*, scope, customer_user, customer_id):
        assert customer_id in ("AURORA", "BETA")
        rows = {
            "AURORA": [
                znuny_ticket.TicketSummary(
                    znuny_ticket_id=1,
                    ticket_number="1001",
                    title="VPN não conecta",
                    state="open",
                    created="2026-01-01",
                    contract_id=None,
                )
            ],
            "BETA": [],
        }
        return rows[customer_id]

    async def fake_config_item_search(*, customer_id):
        return []

    monkeypatch.setattr(znuny_ticket, "search_tickets", fake_search_tickets)
    monkeypatch.setattr(znuny_ticket, "config_item_search", fake_config_item_search)
    monkeypatch.setattr(
        db,
        "AdminSessionLocal",
        async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession),
    )
    monkeypatch.setattr(db, "SessionLocal", app_session_factory)

    app = create_app()
    st = get_settings()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        h_aurora = {"host": "aurora-s.suporte.gerti.com.br"}
        h_beta = {"host": "beta-s.suporte.gerti.com.br"}

        # q curto -> 422
        c.cookies.set("gsid", encode_session(str(aurora.id), "joe", "admin", st))
        short = await c.get("/v1/search", headers=h_aurora, params={"q": "v"})
        assert short.status_code == 422

        # busca em aurora encontra o ticket e o artigo de KB dela.
        ok = await c.get("/v1/search", headers=h_aurora, params={"q": "vpn"})
        assert ok.status_code == 200
        body = ok.json()
        assert len(body["tickets"]) == 1
        assert body["tickets"][0]["path"] == "/tickets/1"
        assert len(body["kb"]) == 1
        assert body["kb"][0]["path"] == "/base-conhecimento/reset-vpn"

        # busca em beta (mesma query) não traz NADA do tenant aurora.
        c.cookies.set("gsid", encode_session(str(beta.id), "joe", "admin", st))
        cross = await c.get("/v1/search", headers=h_beta, params={"q": "vpn"})
        assert cross.status_code == 200
        cross_body = cross.json()
        assert cross_body["tickets"] == []
        assert cross_body["kb"] == []


@pytest.mark.asyncio
async def test_search_tickets_respect_role_scope(engine, app_session_factory, session, monkeypatch):
    """Busca usa o MESMO escopo por papel da lista/detalhe (domain.ticket_scope).

    helpdesk => 'own' (não acha chamado de colega da mesma empresa: antes a
    busca devolvia título/número/estado e o clique dava 404); admin do portal
    => 'company'. Cross-empresa é impossível em qualquer papel.
    """
    monkeypatch.setenv("SESSION_SECRET", "test-secret-32-chars-minimum-xxxx")
    monkeypatch.setenv("ENVIRONMENT", "test")
    get_settings.cache_clear()

    inst = ZnunyInstance(
        name="i",
        base_url="http://z",
        db_dsn_secret_ref="x",
        webservice_token_secret_ref="x",
        webhook_signing_secret_ref="x",
        mode="pool",
    )
    session.add(inst)
    await session.flush()
    acme = await _seed_tenant(session, inst.id, subdomain="acme-scope", customer_id="ACME")
    globex = await _seed_tenant(session, inst.id, subdomain="globex-scope", customer_id="GLOBEX")
    await session.commit()

    def _summary(tid: int, title: str) -> znuny_ticket.TicketSummary:
        return znuny_ticket.TicketSummary(
            znuny_ticket_id=tid,
            ticket_number=f"100{tid}",
            title=title,
            state="open",
            created="2026-01-01",
            contract_id=None,
        )

    # Fake do GI: replica o Znuny — Scope='own' filtra por CustomerUser.
    _rows = {
        "ACME": [
            (_summary(1, "Impressora da Ana travou"), "ana@acme"),
            (_summary(2, "Impressora do Bob sem tinta"), "bob@acme"),
        ],
        "GLOBEX": [(_summary(3, "Impressora da Globex"), "carol@globex")],
    }
    calls: list[tuple[str, str, str]] = []

    async def fake_search_tickets(*, scope, customer_user, customer_id):
        calls.append((scope, customer_user, customer_id))
        rows = _rows.get(customer_id, [])
        if scope == "own":
            rows = [r for r in rows if r[1] == customer_user]
        return [r[0] for r in rows]

    async def fake_config_item_search(*, customer_id):
        return []

    monkeypatch.setattr(znuny_ticket, "search_tickets", fake_search_tickets)
    monkeypatch.setattr(znuny_ticket, "config_item_search", fake_config_item_search)
    monkeypatch.setattr(
        db,
        "AdminSessionLocal",
        async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession),
    )
    monkeypatch.setattr(db, "SessionLocal", app_session_factory)

    app = create_app()
    st = get_settings()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        h_acme = {"host": "acme-scope.suporte.gerti.com.br"}
        h_globex = {"host": "globex-scope.suporte.gerti.com.br"}

        # 1) helpdesk NÃO acha o chamado do colega da mesma empresa.
        c.cookies.set(
            "gsid",
            encode_session(str(acme.id), "bob@acme", "helpdesk", st, znuny_login="bob@acme"),
        )
        r = await c.get("/v1/search", headers=h_acme, params={"q": "impressora"})
        assert r.status_code == 200
        ids = [t["id"] for t in r.json()["tickets"]]
        assert ids == ["2"], "helpdesk viu chamado de colega na busca (IDOR)"
        assert calls[-1][0] == "own"

        # ...nem buscando pelo termo que só casa o chamado da colega.
        only_ana = await c.get("/v1/search", headers=h_acme, params={"q": "ana"})
        assert only_ana.status_code == 200
        assert only_ana.json()["tickets"] == []

        # 2) helpdesk acha o PRÓPRIO chamado.
        mine = await c.get("/v1/search", headers=h_acme, params={"q": "bob"})
        assert mine.status_code == 200
        assert [t["path"] for t in mine.json()["tickets"]] == ["/tickets/2"]

        # 3) admin do portal continua vendo a empresa inteira (regressão).
        c.cookies.set(
            "gsid",
            encode_session(str(acme.id), "dana@acme", "admin", st, znuny_login="dana@acme"),
        )
        adm = await c.get("/v1/search", headers=h_acme, params={"q": "impressora"})
        assert adm.status_code == 200
        assert calls[-1][0] == "company"
        assert sorted(t["id"] for t in adm.json()["tickets"]) == ["1", "2"]

        # 4) cross-empresa: nenhum papel enxerga chamado da outra empresa.
        assert all(t["id"] != "3" for t in adm.json()["tickets"])
        c.cookies.set(
            "gsid",
            encode_session(str(globex.id), "carol@globex", "admin", st, znuny_login="carol@globex"),
        )
        other = await c.get("/v1/search", headers=h_globex, params={"q": "impressora"})
        assert other.status_code == 200
        assert [t["id"] for t in other.json()["tickets"]] == ["3"]
