"""agent_enroll_token + device_agent — RLS por tenant, constraints (Spec #1R-a).

- UNIQUE(token_hash) em agent_enroll_token
- UNIQUE(tenant_id, fingerprint) em device_agent
- CHECK status pending|active|revoked
- specs JSONB roundtrip
- RLS: sessão RLS-subject só enxerga linhas do tenant do GUC (ambas tabelas)
"""

from __future__ import annotations

import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import DBAPIError, IntegrityError

from gerti_sidecar.models import AgentEnrollToken, DeviceAgent


@pytest.mark.asyncio
async def test_enroll_token_unique_hash(session, seed_two_tenants):
    a, b = seed_two_tenants
    session.add(AgentEnrollToken(tenant_id=a, token_hash="dup", label="t1"))
    await session.flush()
    session.add(AgentEnrollToken(tenant_id=b, token_hash="dup", label="t2"))
    with pytest.raises((IntegrityError, DBAPIError)):
        await session.flush()
    await session.rollback()


@pytest.mark.asyncio
async def test_device_unique_tenant_fingerprint(session, seed_two_tenants):
    a, _b = seed_two_tenants
    session.add(
        DeviceAgent(
            tenant_id=a,
            fingerprint="FP1",
            agent_secret_hash="h1",
            status="active",
            hostname="host1",
        )
    )
    await session.flush()
    session.add(
        DeviceAgent(
            tenant_id=a,
            fingerprint="FP1",
            agent_secret_hash="h2",
            status="active",
            hostname="host2",
        )
    )
    with pytest.raises((IntegrityError, DBAPIError)):
        await session.flush()
    await session.rollback()


@pytest.mark.asyncio
async def test_device_same_fingerprint_other_tenant_ok(session, seed_two_tenants):
    """A UNIQUE é POR tenant: o mesmo fingerprint pode existir em tenants distintos."""
    a, b = seed_two_tenants
    session.add(
        DeviceAgent(
            tenant_id=a, fingerprint="SHARED", agent_secret_hash="h1", status="active", hostname="x"
        )
    )
    session.add(
        DeviceAgent(
            tenant_id=b, fingerprint="SHARED", agent_secret_hash="h2", status="active", hostname="y"
        )
    )
    await session.flush()  # não deve falhar


@pytest.mark.asyncio
async def test_device_status_check_constraint(session, seed_two_tenants):
    a, _b = seed_two_tenants
    session.add(
        DeviceAgent(
            tenant_id=a,
            fingerprint="FPbad",
            agent_secret_hash="h",
            status="bogus",
            hostname="x",
        )
    )
    with pytest.raises((IntegrityError, DBAPIError)):
        await session.flush()
    await session.rollback()


@pytest.mark.asyncio
async def test_device_specs_jsonb_roundtrip(session, seed_two_tenants):
    a, _b = seed_two_tenants
    d = DeviceAgent(
        tenant_id=a,
        fingerprint="FPspecs",
        agent_secret_hash="h",
        status="active",
        hostname="host",
        os="Ubuntu 22.04",
        specs={"cpu": "i5", "memory": "16 GB"},
    )
    session.add(d)
    await session.flush()
    fetched = (
        await session.execute(select(DeviceAgent).where(DeviceAgent.id == d.id))
    ).scalar_one()
    assert fetched.specs["cpu"] == "i5"
    assert fetched.specs["memory"] == "16 GB"
    assert fetched.os == "Ubuntu 22.04"
    assert fetched.znuny_config_item_id is None


@pytest.mark.asyncio
async def test_enroll_token_defaults(session, seed_two_tenants):
    a, _b = seed_two_tenants
    tok = AgentEnrollToken(tenant_id=a, token_hash="h-defaults", label="t")
    session.add(tok)
    await session.flush()
    fetched = (
        await session.execute(select(AgentEnrollToken).where(AgentEnrollToken.id == tok.id))
    ).scalar_one()
    assert fetched.enabled is True
    assert fetched.registration_count == 0
    assert fetched.max_registrations is None
    assert fetched.expires_at is None


@pytest.mark.asyncio
async def test_agent_inventory_rls_isolation(engine, app_session_factory, seed_two_tenants):
    """Sessão RLS-subject só enxerga tokens/devices do tenant do GUC."""
    a, b = seed_two_tenants
    factory = app_session_factory
    async with factory() as s:
        async with s.begin():
            await s.execute(
                text("SELECT set_config('app.current_tenant', :t, true)"), {"t": str(a)}
            )
            s.add(AgentEnrollToken(tenant_id=a, token_hash="ta", label="A"))
            s.add(
                DeviceAgent(
                    tenant_id=a,
                    fingerprint="A-FP",
                    agent_secret_hash="ha",
                    status="active",
                    hostname="ha",
                )
            )
    async with factory() as s:
        async with s.begin():
            await s.execute(
                text("SELECT set_config('app.current_tenant', :t, true)"), {"t": str(b)}
            )
            s.add(AgentEnrollToken(tenant_id=b, token_hash="tb", label="B"))
            s.add(
                DeviceAgent(
                    tenant_id=b,
                    fingerprint="B-FP",
                    agent_secret_hash="hb",
                    status="active",
                    hostname="hb",
                )
            )
    async with factory() as s:
        async with s.begin():
            await s.execute(
                text("SELECT set_config('app.current_tenant', :t, true)"), {"t": str(a)}
            )
            labels = (await s.execute(select(AgentEnrollToken.label))).scalars().all()
            fps = (await s.execute(select(DeviceAgent.fingerprint))).scalars().all()
    assert labels == ["A"]
    assert fps == ["A-FP"]
