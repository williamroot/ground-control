from __future__ import annotations

import uuid

import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import DBAPIError, IntegrityError

from gerti_sidecar.models import AutomationRule, AutomationRun


@pytest.mark.asyncio
async def test_rule_trigger_event_check_constraint(session, seed_two_tenants):
    a, _b = seed_two_tenants
    session.add(
        AutomationRule(
            tenant_id=a,
            name="bad trigger",
            trigger_event="not_a_real_event",
            conditions=[],
            actions=[],
            position=0,
        )
    )
    with pytest.raises((IntegrityError, DBAPIError)):
        await session.flush()
    await session.rollback()


@pytest.mark.asyncio
async def test_rule_jsonb_roundtrip(session, seed_two_tenants):
    a, _b = seed_two_tenants
    rule = AutomationRule(
        tenant_id=a,
        name="urgente",
        trigger_event="article_create",
        conditions=[{"field": "title", "op": "contains", "value": "urgente"}],
        actions=[{"type": "set_priority", "params": {"priority": "5 very high"}}],
        position=3,
    )
    session.add(rule)
    await session.flush()
    fetched = (
        await session.execute(select(AutomationRule).where(AutomationRule.id == rule.id))
    ).scalar_one()
    assert fetched.enabled is True
    assert fetched.conditions[0]["op"] == "contains"
    assert fetched.actions[0]["params"]["priority"] == "5 very high"
    assert fetched.position == 3


@pytest.mark.asyncio
async def test_run_fk_to_rule(session, seed_two_tenants):
    a, _b = seed_two_tenants
    rule = AutomationRule(
        tenant_id=a,
        name="r",
        trigger_event="ticket_create",
        conditions=[],
        actions=[],
        position=0,
    )
    session.add(rule)
    await session.flush()
    run = AutomationRun(
        tenant_id=a,
        rule_id=rule.id,
        znuny_ticket_id=42,
        event="ticket_create",
        matched=True,
        actions_result=[{"type": "set_priority", "ok": True}],
    )
    session.add(run)
    await session.flush()
    # FK violation: run pointing at a non-existent rule
    session.add(
        AutomationRun(
            tenant_id=a,
            rule_id=uuid.uuid4(),
            znuny_ticket_id=1,
            event="ticket_create",
            matched=False,
        )
    )
    with pytest.raises((IntegrityError, DBAPIError)):
        await session.flush()
    await session.rollback()


@pytest.mark.asyncio
async def test_rule_rls_isolation(engine, app_session_factory, seed_two_tenants):
    """A RLS-subject session só enxerga regras do tenant do GUC."""
    a, b = seed_two_tenants
    # seed via admin/superuser session (engine), uma regra por tenant
    factory = app_session_factory
    async with factory() as s:
        async with s.begin():
            await s.execute(
                text("SELECT set_config('app.current_tenant', :t, true)"), {"t": str(a)}
            )
            s.add(
                AutomationRule(
                    tenant_id=a,
                    name="A rule",
                    trigger_event="ticket_create",
                    conditions=[],
                    actions=[],
                    position=0,
                )
            )
    async with factory() as s:
        async with s.begin():
            await s.execute(
                text("SELECT set_config('app.current_tenant', :t, true)"), {"t": str(b)}
            )
            s.add(
                AutomationRule(
                    tenant_id=b,
                    name="B rule",
                    trigger_event="ticket_create",
                    conditions=[],
                    actions=[],
                    position=0,
                )
            )
    # tenant A só vê a sua
    async with factory() as s:
        async with s.begin():
            await s.execute(
                text("SELECT set_config('app.current_tenant', :t, true)"), {"t": str(a)}
            )
            rows = (await s.execute(select(AutomationRule.name))).scalars().all()
    assert rows == ["A rule"]
