"""audit_log: tabela OPERACIONAL sem RLS (como ai_generation_log/agent_timer).

Insere via a sessão admin (BYPASSRLS, cross-tenant) e lê de volta. Verifica os
CHECKs de actor_type e action.
"""

from __future__ import annotations

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from gerti_sidecar.models import AuditLog


@pytest.mark.asyncio
async def test_insert_and_read_back(session):
    log = AuditLog(
        actor_type="agent",
        actor_login="william",
        tenant_id=None,
        action="create",
        entity="tenant",
        entity_id="abc",
        description="onboarding do tenant Acme",
        ip="127.0.0.1",
        user_agent="pytest",
        metadata_json={"subdomain": "acme"},
    )
    session.add(log)
    await session.flush()
    rows = (
        (await session.execute(select(AuditLog).where(AuditLog.entity_id == "abc"))).scalars().all()
    )
    assert len(rows) == 1
    assert rows[0].action == "create"
    assert rows[0].actor_type == "agent"
    assert rows[0].metadata_json == {"subdomain": "acme"}
    assert rows[0].at is not None


@pytest.mark.asyncio
async def test_actor_type_check_constraint(session):
    session.add(
        AuditLog(
            actor_type="bogus",
            action="create",
            entity="tenant",
            description="x",
        )
    )
    with pytest.raises(IntegrityError):
        await session.flush()
    await session.rollback()


@pytest.mark.asyncio
async def test_action_check_constraint(session):
    session.add(
        AuditLog(
            actor_type="agent",
            action="bogus",
            entity="tenant",
            description="x",
        )
    )
    with pytest.raises(IntegrityError):
        await session.flush()
    await session.rollback()


@pytest.mark.asyncio
async def test_default_theme_accepts_system(session):
    """0024 alarga ck_tenant_branding_theme p/ incluir 'system' (Spec #3 V4)."""
    from gerti_sidecar.models import Tenant, TenantBranding, ZnunyInstance

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
        legal_name="A SA",
        trade_name="A",
        document="1",
        znuny_customer_id="a",
        znuny_instance_id=inst.id,
        subdomain="a-theme",
    )
    session.add(t)
    await session.flush()
    session.add(TenantBranding(tenant_id=t.id, display_name="A", default_theme="system"))
    await session.flush()
