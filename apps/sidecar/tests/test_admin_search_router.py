"""GET /v1/admin/search — busca federada cross-tenant do console (Spec #3 V6).

- sem gsid_adm → 401
- q curto (<2) → 422
- encontra tenant por nome/subdomínio
"""

from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from gerti_sidecar import db
from gerti_sidecar.auth.admin_session import encode_admin_session
from gerti_sidecar.config import get_settings
from gerti_sidecar.integrations import znuny_ticket
from gerti_sidecar.main import create_app
from gerti_sidecar.models import Tenant, ZnunyInstance

_HOST = {"host": "gerti.was.dev.br"}


@pytest.mark.asyncio
async def test_admin_search(engine, app_session_factory, session, monkeypatch):
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
    t = Tenant(
        legal_name="Aurora Móveis SA",
        trade_name="Aurora",
        document="1",
        znuny_customer_id="AURORA",
        znuny_instance_id=inst.id,
        subdomain="aurora-adm-search",
    )
    session.add(t)
    await session.commit()

    async def fake_agent_search(*, query, customer_id):
        return []

    monkeypatch.setattr(znuny_ticket, "agent_search", fake_agent_search)
    monkeypatch.setattr(
        db,
        "AdminSessionLocal",
        async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession),
    )
    monkeypatch.setattr(db, "SessionLocal", app_session_factory)

    app = create_app()
    st = get_settings()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        # sem sessão -> 401
        no_session = await c.get("/v1/admin/search", headers=_HOST, params={"q": "aurora"})
        assert no_session.status_code == 401

        c.cookies.set("gsid_adm", encode_admin_session("william", st))

        # q curto -> 422
        short = await c.get("/v1/admin/search", headers=_HOST, params={"q": "a"})
        assert short.status_code == 422

        ok = await c.get("/v1/admin/search", headers=_HOST, params={"q": "aurora"})
        assert ok.status_code == 200
        body = ok.json()
        assert len(body["tenants"]) == 1
        assert body["tenants"][0]["path"] == f"/clientes/{t.id}"
        assert body["tickets"] == []


@pytest.mark.asyncio
async def test_admin_search_tickets_stay_cross_tenant(
    engine, app_session_factory, session, monkeypatch
):
    """Regressão: o console é do agente da Gerti (gsid_adm) — cross-tenant por design.

    Diferente de `/v1/search` (portal), a busca do console NÃO ganha escopo de
    usuário/empresa: usa `agent_search` sem `CustomerID` e devolve chamados de
    todos os tenants.
    """
    monkeypatch.setenv("SESSION_SECRET", "test-secret-32-chars-minimum-xxxx")
    monkeypatch.setenv("ENVIRONMENT", "test")
    get_settings.cache_clear()

    calls: list[str | None] = []

    async def fake_agent_search(*, query, customer_id):
        calls.append(customer_id)
        return [
            znuny_ticket.AgentTicketSummary(
                znuny_ticket_id=1,
                ticket_number="1001",
                title="Impressora da Ana travou",
                state="open",
                customer_id="ACME",
                owner="agente",
                created="2026-01-01",
            ),
            znuny_ticket.AgentTicketSummary(
                znuny_ticket_id=3,
                ticket_number="1003",
                title="Impressora da Globex",
                state="open",
                customer_id="GLOBEX",
                owner="agente",
                created="2026-01-01",
            ),
        ]

    monkeypatch.setattr(znuny_ticket, "agent_search", fake_agent_search)
    monkeypatch.setattr(
        db,
        "AdminSessionLocal",
        async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession),
    )
    monkeypatch.setattr(db, "SessionLocal", app_session_factory)

    app = create_app()
    st = get_settings()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        c.cookies.set("gsid_adm", encode_admin_session("william", st))
        ok = await c.get("/v1/admin/search", headers=_HOST, params={"q": "impressora"})
        assert ok.status_code == 200
        tickets = ok.json()["tickets"]
        assert sorted(t["id"] for t in tickets) == ["1", "3"]
        assert [t["path"] for t in tickets] == ["/atendimento/1", "/atendimento/3"]
        assert calls == [None], "console não deve filtrar por CustomerID"
