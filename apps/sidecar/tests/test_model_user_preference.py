"""UserPreference: model, defaults, UNIQUE (tenant_id, user_login), CHECK de
theme, RLS (Spec #3 V3). Espelha o padrão de test_model_invoice.py.
"""

from __future__ import annotations

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from gerti_sidecar import db
from gerti_sidecar.models import UserPreference


@pytest.mark.asyncio
async def test_user_preference_defaults(session, seed_two_tenants):
    a_id, _ = seed_two_tenants
    p = UserPreference(tenant_id=a_id, user_login="joe@aurora")
    session.add(p)
    await session.flush()
    assert p.theme == "system"
    assert p.email_notifications is True
    assert p.sla_alerts is True
    assert p.ticket_updates is True
    assert p.contract_alerts is True
    assert p.invoice_alerts is True
    assert p.weekly_report is False


@pytest.mark.asyncio
async def test_user_preference_theme_check_constraint(session, seed_two_tenants):
    a_id, _ = seed_two_tenants
    bad = UserPreference(tenant_id=a_id, user_login="joe@aurora", theme="purple")
    sp = await session.begin_nested()
    session.add(bad)
    with pytest.raises(IntegrityError):
        await session.flush()
    await sp.rollback()


@pytest.mark.asyncio
async def test_user_preference_unique_tenant_login(session, seed_two_tenants):
    a_id, _ = seed_two_tenants
    session.add(UserPreference(tenant_id=a_id, user_login="joe@aurora"))
    await session.flush()

    dup = UserPreference(tenant_id=a_id, user_login="joe@aurora")
    sp = await session.begin_nested()
    session.add(dup)
    with pytest.raises(IntegrityError):
        await session.flush()
    await sp.rollback()


@pytest.mark.asyncio
async def test_user_preference_rls_isolation(session, app_session_factory, seed_two_tenants):
    a_id, b_id = seed_two_tenants
    session.add_all(
        [
            UserPreference(tenant_id=a_id, user_login="joe@aurora", theme="dark"),
            UserPreference(tenant_id=b_id, user_login="joe@beta", theme="light"),
        ]
    )
    await session.commit()

    async with db.tenant_session_scope(a_id, factory=app_session_factory) as s:
        rows = (
            (await s.execute(text("SELECT user_login FROM gerti.user_preference"))).scalars().all()
        )
    assert rows == ["joe@aurora"]

    async with db.tenant_session_scope(b_id, factory=app_session_factory) as s:
        rows = (
            (await s.execute(text("SELECT user_login FROM gerti.user_preference"))).scalars().all()
        )
    assert rows == ["joe@beta"]

    async with app_session_factory() as s:
        assert (
            await s.execute(text("SELECT count(*) FROM gerti.user_preference"))
        ).scalar_one() == 0
