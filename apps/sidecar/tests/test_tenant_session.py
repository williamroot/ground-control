"""tenant_session_scope sets app.current_tenant and RLS isolates tenant rows."""

from __future__ import annotations

import pytest
from sqlalchemy import text

from gerti_sidecar import db


@pytest.mark.asyncio
async def test_tenant_session_scope_sets_guc_and_isolates(app_session_factory, seed_two_tenants):
    a_id, b_id = seed_two_tenants
    async with db.tenant_session_scope(a_id, factory=app_session_factory) as s:
        rows = (await s.execute(text("SELECT id FROM gerti.tenant"))).scalars().all()
        guc = (
            await s.execute(text("SELECT current_setting('app.current_tenant', true)"))
        ).scalar_one()
    assert {str(r) for r in rows} == {str(a_id)}
    assert guc == str(a_id)


@pytest.mark.asyncio
async def test_unset_guc_sees_zero_tenant_rows(app_session_factory, seed_two_tenants):
    a_id, b_id = seed_two_tenants
    factory = app_session_factory
    async with factory() as s:  # no tenant_session_scope → GUC unset
        rows = (await s.execute(text("SELECT id FROM gerti.tenant"))).scalars().all()
    assert rows == []
