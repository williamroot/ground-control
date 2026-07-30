"""GET /v1/search — busca federada do portal (Spec #3 V6).

- 200 com tickets/assets escopados pelo customer_id do tenant (via GI fake)
- q curto (<2) → 422
- cross-tenant vazio: KB de um tenant nunca aparece na busca do outro
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
