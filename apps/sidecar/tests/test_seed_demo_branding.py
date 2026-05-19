"""seed_demo_branding: idempotente; Aurora (só branding) + TechNova
(tenant + branding + contratos), cross-tenant visivelmente distinto."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
from sqlalchemy import select

from gerti_sidecar.models import Contract, Tenant, TenantBranding

_SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

import seed_demo_branding  # noqa: E402
import seed_demo_contracts  # noqa: E402


@pytest.mark.asyncio
async def test_branding_seed_two_tenants_idempotent(session):
    # #1C seed creates the Aurora tenant + the single znuny_instance + 6 contracts.
    await seed_demo_contracts.seed(session)
    await session.commit()
    r1 = await seed_demo_branding.seed(session)
    await session.commit()
    r2 = await seed_demo_branding.seed(session)
    await session.commit()
    assert r1 == r2  # (aurora_id, technova_id) stable across re-runs

    aurora_id, technova_id = r1
    assert aurora_id != technova_id

    ba = (
        await session.execute(select(TenantBranding).where(TenantBranding.tenant_id == aurora_id))
    ).scalar_one()
    bt = (
        await session.execute(select(TenantBranding).where(TenantBranding.tenant_id == technova_id))
    ).scalar_one()
    assert ba.display_name == "Aurora Móveis"
    assert bt.display_name == "TechNova"
    # White-label difference must be visually obvious.
    assert ba.primary_color != bt.primary_color
    assert ba.display_name != bt.display_name

    ta = (await session.execute(select(Tenant).where(Tenant.id == aurora_id))).scalar_one()
    tt = (await session.execute(select(Tenant).where(Tenant.id == technova_id))).scalar_one()
    assert ta.znuny_customer_id == "AURORA"
    assert tt.znuny_customer_id == "TECHNOVA"
    assert tt.subdomain == "technova"
    # Constraint §2.1: both tenants point at the SAME single znuny_instance.
    assert ta.znuny_instance_id == tt.znuny_instance_id

    # Aurora keeps its 6 #1C contracts; TechNova has its own small set,
    # demonstrably DIFFERENT (count + codes) from Aurora's.
    ca = (
        (await session.execute(select(Contract).where(Contract.tenant_id == aurora_id)))
        .scalars()
        .all()
    )
    ct = (
        (await session.execute(select(Contract).where(Contract.tenant_id == technova_id)))
        .scalars()
        .all()
    )
    assert len(ca) == 6
    assert len(ct) == 2
    assert {c.code for c in ca}.isdisjoint({c.code for c in ct})
