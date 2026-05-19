"""tenant_branding: 1:1 with tenant, RLS fail-closed, scoped by subdomain GUC."""

from __future__ import annotations

import pytest
from sqlalchemy import text

from gerti_sidecar import db
from gerti_sidecar.models import Tenant, TenantBranding, ZnunyInstance


@pytest.mark.asyncio
async def test_tenant_branding_rls_fail_closed_and_scoped(session, app_session_factory):
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
    a = Tenant(
        legal_name="A SA",
        trade_name="A",
        document="1",
        znuny_customer_id="a",
        znuny_instance_id=inst.id,
        subdomain="a",
    )
    b = Tenant(
        legal_name="B SA",
        trade_name="B",
        document="2",
        znuny_customer_id="b",
        znuny_instance_id=inst.id,
        subdomain="b",
    )
    session.add_all([a, b])
    await session.flush()
    session.add_all(
        [
            TenantBranding(tenant_id=a.id, display_name="Brand A"),
            TenantBranding(tenant_id=b.id, display_name="Brand B"),
        ]
    )
    await session.commit()

    async with db.tenant_session_scope(a.id, factory=app_session_factory) as s:
        names = (
            (await s.execute(text("SELECT display_name FROM gerti.tenant_branding")))
            .scalars()
            .all()
        )
    assert names == ["Brand A"]

    async with app_session_factory() as s:
        rows = (
            (await s.execute(text("SELECT display_name FROM gerti.tenant_branding")))
            .scalars()
            .all()
        )
    assert rows == []
