# apps/sidecar/tests/test_ticketing_meta_router.py
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
async def test_selectable_contracts_visible_to_helpdesk(
    engine, app_session_factory, session, monkeypatch
):
    monkeypatch.setenv("SESSION_SECRET", "test-secret-32-chars-minimum-xxxx")
    monkeypatch.setenv("ENVIRONMENT", "test")
    get_settings.cache_clear()
    inst = ZnunyInstance(
        name="i", base_url="http://z", db_dsn_secret_ref="x",
        webservice_token_secret_ref="x", webhook_signing_secret_ref="x", mode="pool",
    )
    session.add(inst)
    await session.flush()
    t = Tenant(legal_name="Acme", trade_name="Acme", document="1",
               znuny_customer_id="ACME", znuny_instance_id=inst.id, subdomain="acme")
    session.add(t)
    await session.flush()
    session.add(TenantBranding(tenant_id=t.id, display_name="Acme"))
    session.add(Contract(tenant_id=t.id, code="C-1", type=ContractType.hour_bank,
                         starts_on=dt.date(2026, 1, 1), ends_on=dt.date(2026, 12, 31),
                         initial_hours=100, created_by="seed"))
    await session.commit()
    monkeypatch.setattr(db, "AdminSessionLocal",
                        async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession))
    monkeypatch.setattr(db, "SessionLocal", app_session_factory)
    app = create_app()
    st = get_settings()
    h = {"host": "acme.suporte.gerti.com.br"}
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        assert (await c.get("/v1/ticketing/contracts", headers=h)).status_code == 401
        # papel helpdesk (NÃO admin) deve enxergar — diferente de /v1/contracts
        c.cookies.set("gsid", encode_session(str(t.id), "joe", "helpdesk", st))
        r = await c.get("/v1/ticketing/contracts", headers=h)
        assert r.status_code == 200
        rows = r.json()
        assert rows[0]["code"] == "C-1"
        assert "id" in rows[0]
