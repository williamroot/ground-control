"""Notification: model, CHECK de kind, RLS (Spec #3 V3).

Espelha o padrão de test_model_invoice.py. `notification` é tenant-scoped
(FORCE RLS + policy direta por tenant_id).
"""

from __future__ import annotations

import datetime as dt

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from gerti_sidecar import db
from gerti_sidecar.models import Notification


@pytest.mark.asyncio
async def test_notification_kind_check_constraint(session, seed_two_tenants):
    a_id, _ = seed_two_tenants
    bad = Notification(
        tenant_id=a_id,
        recipient_login="joe@aurora",
        kind="not_a_real_kind",
        title="x",
    )
    sp = await session.begin_nested()
    session.add(bad)
    with pytest.raises(IntegrityError):
        await session.flush()
    await sp.rollback()


@pytest.mark.asyncio
async def test_notification_defaults(session, seed_two_tenants):
    a_id, _ = seed_two_tenants
    n = Notification(
        tenant_id=a_id,
        recipient_login="joe@aurora",
        kind="invoice_issued",
        title="Fatura #0001 emitida",
    )
    session.add(n)
    await session.flush()
    assert n.read_at is None
    assert n.created_at is not None
    assert n.body is None
    assert n.link_path is None


@pytest.mark.asyncio
async def test_notification_rls_isolation(session, app_session_factory, seed_two_tenants):
    """Tenant A só vê suas notificações; B vê só as dele; GUC ausente → 0 linhas."""
    a_id, b_id = seed_two_tenants

    session.add_all(
        [
            Notification(
                tenant_id=a_id,
                recipient_login="joe@aurora",
                kind="invoice_issued",
                title="A",
                created_at=dt.datetime(2026, 1, 1, tzinfo=dt.UTC),
            ),
            Notification(
                tenant_id=b_id,
                recipient_login="joe@beta",
                kind="invoice_issued",
                title="B",
                created_at=dt.datetime(2026, 1, 1, tzinfo=dt.UTC),
            ),
        ]
    )
    await session.commit()

    async with db.tenant_session_scope(a_id, factory=app_session_factory) as s:
        titles = (await s.execute(text("SELECT title FROM gerti.notification"))).scalars().all()
    assert titles == ["A"]

    async with db.tenant_session_scope(b_id, factory=app_session_factory) as s:
        titles = (await s.execute(text("SELECT title FROM gerti.notification"))).scalars().all()
    assert titles == ["B"]

    # GUC ausente → fail-closed
    async with app_session_factory() as s:
        assert (await s.execute(text("SELECT count(*) FROM gerti.notification"))).scalar_one() == 0
