import datetime as dt

import pytest

from gerti_sidecar.models import (
    Contract,
    ContractScopeCi,
    ContractScopeService,
    ServiceCatalogItem,
    SharedCreditPool,
)
from gerti_sidecar.models.enums import ContractType, CycleKind


@pytest.mark.asyncio
async def test_catalog_pool_scope(session, seed_two_tenants):
    a_id, _ = seed_two_tenants
    svc = ServiceCatalogItem(
        tenant_id=a_id,
        code="M365",
        title="Microsoft 365",
        default_queue_name="Suporte::N1",
        unit_price_brl=120,
    )
    pool = SharedCreditPool(
        tenant_id=a_id,
        name="Pool Matriz",
        total_amount_brl=50000,
        cycle_kind=CycleKind.billing,
        cycle_period_months=1,
        current_cycle_start=dt.date(2026, 1, 1),
    )
    session.add_all([svc, pool])
    await session.flush()
    c = Contract(
        tenant_id=a_id,
        code="C1",
        type=ContractType.closed_value,
        starts_on=dt.date(2026, 1, 1),
        ends_on=dt.date(2026, 12, 31),
        created_by="s",
    )
    session.add(c)
    await session.flush()
    session.add(ContractScopeService(contract_id=c.id, service_id=svc.id))
    session.add(
        ContractScopeCi(
            contract_id=c.id,
            znuny_ci_id=4012,
            covered_from=dt.date(2026, 1, 1),
        )
    )
    await session.flush()
    assert svc.id and pool.id


@pytest.mark.asyncio
async def test_service_catalog_item_global_row_is_read_only_to_tenant(
    session, app_session_factory, seed_two_tenants
):
    """B1: a tenant session can READ a global (tenant_id IS NULL) catalog row
    but CANNOT update or delete it (split per-command RLS policies)."""
    from sqlalchemy import text

    from gerti_sidecar import db

    a_id, _ = seed_two_tenants
    # Seed a GLOBAL catalog row as admin (BYPASSRLS).
    session.add(
        ServiceCatalogItem(
            tenant_id=None,
            code="GLOBAL-VOIP",
            title="VoIP global",
            default_queue_name="Suporte::N1",
            unit_price_brl=99,
        )
    )
    await session.commit()

    async with db.tenant_session_scope(a_id, factory=app_session_factory) as s:
        # CAN read the global row.
        codes = (
            (
                await s.execute(
                    text(
                        "SELECT code FROM gerti.service_catalog_item " "WHERE code = 'GLOBAL-VOIP'"
                    )
                )
            )
            .scalars()
            .all()
        )
        assert codes == ["GLOBAL-VOIP"]
        # CANNOT update it: 0 rows affected, NO error (USING filters it out).
        res = await s.execute(
            text(
                "UPDATE gerti.service_catalog_item SET title = 'hijack' "
                "WHERE code = 'GLOBAL-VOIP'"
            )
        )
        assert res.rowcount == 0
        # CANNOT delete it: 0 rows affected, NO error.
        res = await s.execute(
            text("DELETE FROM gerti.service_catalog_item " "WHERE code = 'GLOBAL-VOIP'")
        )
        assert res.rowcount == 0

    # Global row is still intact (verified via admin session).
    title = (
        await session.execute(
            text("SELECT title FROM gerti.service_catalog_item " "WHERE code = 'GLOBAL-VOIP'")
        )
    ).scalar_one()
    assert title == "VoIP global"
