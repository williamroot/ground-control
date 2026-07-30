"""Model CatalogItem: CheckConstraints + RLS de tenant (Spec #3 V2, agente B1).

Tabela `gerti.catalog_item` — nome escolhido para não colidir com
`gerti.service_catalog_item` já existente (Spec #0 §4, ver test_model_catalog.py).
"""

from __future__ import annotations

import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import DBAPIError, IntegrityError

from gerti_sidecar.models import CatalogItem


def _item(tenant_id, **overrides):
    defaults = dict(
        tenant_id=tenant_id,
        name="Reset de senha",
        category="acessos",
        description="Solicita redefinição de senha de rede",
        sla_hours=4,
        icon="lock",
    )
    defaults.update(overrides)
    return CatalogItem(**defaults)


@pytest.mark.asyncio
async def test_icon_check_constraint(session, seed_two_tenants):
    a, _b = seed_two_tenants
    session.add(_item(a, icon="not-an-allowed-icon"))
    with pytest.raises((IntegrityError, DBAPIError)):
        await session.flush()
    await session.rollback()


@pytest.mark.asyncio
async def test_sla_hours_check_constraint(session, seed_two_tenants):
    a, _b = seed_two_tenants
    session.add(_item(a, sla_hours=0))
    with pytest.raises((IntegrityError, DBAPIError)):
        await session.flush()
    await session.rollback()

    session.add(_item(a, sla_hours=721))
    with pytest.raises((IntegrityError, DBAPIError)):
        await session.flush()
    await session.rollback()

    # NULL é permitido (SLA opcional)
    session.add(_item(a, sla_hours=None))
    await session.flush()


@pytest.mark.asyncio
async def test_sort_order_check_constraint(session, seed_two_tenants):
    a, _b = seed_two_tenants
    session.add(_item(a, sort_order=1000))
    with pytest.raises((IntegrityError, DBAPIError)):
        await session.flush()
    await session.rollback()


@pytest.mark.asyncio
async def test_defaults(session, seed_two_tenants):
    a, _b = seed_two_tenants
    item = CatalogItem(tenant_id=a, name="Item X", category="rede")
    session.add(item)
    await session.flush()
    await session.refresh(item)
    assert item.icon == "ticket"
    assert item.active is True
    assert item.sort_order == 0


@pytest.mark.asyncio
async def test_rls_isolation(engine, app_session_factory, seed_two_tenants):
    """RLS-subject session só enxerga itens do tenant do GUC — prova cross-tenant."""
    a, b = seed_two_tenants
    factory = app_session_factory
    async with factory() as s:
        async with s.begin():
            await s.execute(
                text("SELECT set_config('app.current_tenant', :t, true)"), {"t": str(a)}
            )
            s.add(_item(a, name="Item A"))
    async with factory() as s:
        async with s.begin():
            await s.execute(
                text("SELECT set_config('app.current_tenant', :t, true)"), {"t": str(b)}
            )
            s.add(_item(b, name="Item B"))

    async with factory() as s:
        async with s.begin():
            await s.execute(
                text("SELECT set_config('app.current_tenant', :t, true)"), {"t": str(a)}
            )
            rows = (await s.execute(select(CatalogItem.name))).scalars().all()
    assert rows == ["Item A"]
