"""GET /v1/contracts: auth required, tenant-scoped, balances via #1C."""

from __future__ import annotations

import datetime as dt

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from gerti_sidecar import db
from gerti_sidecar.auth.session import encode_session
from gerti_sidecar.config import get_settings
from gerti_sidecar.main import create_app
from gerti_sidecar.models import Contract, Tenant, TenantBranding, ZnunyInstance
from gerti_sidecar.models.enums import ContractType


@pytest.mark.asyncio
async def test_contracts_scoped_and_authed(engine, app_session_factory, session, monkeypatch):
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
        legal_name="Aurora",
        trade_name="Aurora",
        document="1",
        znuny_customer_id="AURORA",
        znuny_instance_id=inst.id,
        subdomain="aurora",
    )
    session.add(t)
    await session.flush()
    session.add(TenantBranding(tenant_id=t.id, display_name="Aurora Móveis"))
    contract = Contract(
        tenant_id=t.id,
        code="AUR-1",
        type=ContractType.credit_brl,
        starts_on=dt.date(2026, 1, 1),
        ends_on=dt.date(2026, 12, 31),
        initial_amount_brl=10000,
        created_by="seed",
    )
    session.add(contract)
    await session.commit()
    # Resolution path = admin engine (BYPASSRLS, mirrors
    # test_tenant_middleware.py). Data path: db.SessionLocal =
    # app_session_factory (RLS-subject). get_tenant_session ->
    # tenant_session_scope(tenant.id) (no factory=) uses module
    # db.SessionLocal, so /v1/contracts data is GENUINELY served by the
    # RLS-subject gerti_sidecar role under the app.current_tenant GUC —
    # RLS is really exercised on the contracts read (not bypassed).
    monkeypatch.setattr(
        db,
        "AdminSessionLocal",
        async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession),
    )
    monkeypatch.setattr(db, "SessionLocal", app_session_factory)
    app = create_app()
    st = get_settings()
    h = {"host": "aurora.suporte.gerti.com.br"}
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://t") as c:
        assert (await c.get("/v1/contracts", headers=h)).status_code == 401
        c.cookies.set("gsid", encode_session(str(t.id), "joe", st))
        r = await c.get("/v1/contracts", headers=h)
        assert r.status_code == 200
        rows = r.json()
        assert len(rows) == 1
        assert rows[0]["code"] == "AUR-1"
        assert rows[0]["saldo"]["kind"] == "brl"
        assert rows[0]["saldo"]["remaining"] == 10000.0
        assert rows[0]["id"] == str(contract.id)
        # credit_brl with full balance (no consumption) -> 0% consumed
        assert rows[0]["consumed_percent"] == 0.0
