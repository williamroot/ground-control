"""ServiceCatalogService: filtros, visibilidade ativo/inativo (Spec #3 V2)."""

from __future__ import annotations

import uuid

import pytest

from gerti_sidecar.domain.errors import CatalogItemNotFound
from gerti_sidecar.domain.service_catalog_service import ServiceCatalogService


@pytest.mark.asyncio
async def test_list_public_only_active(session, seed_two_tenants):
    a, _b = seed_two_tenants
    svc = ServiceCatalogService(session)
    active = await svc.create(
        tenant_id=a,
        name="Item ativo",
        category="rede",
        description=None,
        sla_hours=4,
        icon="ticket",
        znuny_queue=None,
        znuny_service=None,
        default_priority=None,
        active=True,
        sort_order=0,
    )
    await svc.create(
        tenant_id=a,
        name="Item inativo",
        category="rede",
        description=None,
        sla_hours=4,
        icon="ticket",
        znuny_queue=None,
        znuny_service=None,
        default_priority=None,
        active=False,
        sort_order=0,
    )
    rows = await svc.list_public()
    assert [r.id for r in rows] == [active.id]


@pytest.mark.asyncio
async def test_list_public_filters_category_and_orders_by_sort_order_name(
    session, seed_two_tenants
):
    a, _b = seed_two_tenants
    svc = ServiceCatalogService(session)
    await svc.create(
        tenant_id=a,
        name="Zebra",
        category="acessos",
        description=None,
        sla_hours=None,
        icon="lock",
        znuny_queue=None,
        znuny_service=None,
        default_priority=None,
        active=True,
        sort_order=1,
    )
    await svc.create(
        tenant_id=a,
        name="Abacate",
        category="acessos",
        description=None,
        sla_hours=None,
        icon="lock",
        znuny_queue=None,
        znuny_service=None,
        default_priority=None,
        active=True,
        sort_order=0,
    )
    await svc.create(
        tenant_id=a,
        name="Outra categoria",
        category="rede",
        description=None,
        sla_hours=None,
        icon="wifi",
        znuny_queue=None,
        znuny_service=None,
        default_priority=None,
        active=True,
        sort_order=0,
    )
    rows = await svc.list_public(category="acessos")
    assert [r.name for r in rows] == ["Abacate", "Zebra"]


@pytest.mark.asyncio
async def test_get_public_hides_inactive_and_unknown(session, seed_two_tenants):
    a, _b = seed_two_tenants
    svc = ServiceCatalogService(session)
    inactive = await svc.create(
        tenant_id=a,
        name="Inativo",
        category="rede",
        description=None,
        sla_hours=None,
        icon="ticket",
        znuny_queue=None,
        znuny_service=None,
        default_priority=None,
        active=False,
        sort_order=0,
    )
    with pytest.raises(CatalogItemNotFound):
        await svc.get_public(inactive.id)
    with pytest.raises(CatalogItemNotFound):
        await svc.get_public(uuid.uuid4())


@pytest.mark.asyncio
async def test_categories_public_counts_only_active(session, seed_two_tenants):
    a, _b = seed_two_tenants
    svc = ServiceCatalogService(session)
    for i in range(2):
        await svc.create(
            tenant_id=a,
            name=f"Rede {i}",
            category="rede",
            description=None,
            sla_hours=None,
            icon="wifi",
            znuny_queue=None,
            znuny_service=None,
            default_priority=None,
            active=True,
            sort_order=0,
        )
    await svc.create(
        tenant_id=a,
        name="Rede inativa",
        category="rede",
        description=None,
        sla_hours=None,
        icon="wifi",
        znuny_queue=None,
        znuny_service=None,
        default_priority=None,
        active=False,
        sort_order=0,
    )
    cats = await svc.categories_public()
    assert cats == [("rede", 2)]


@pytest.mark.asyncio
async def test_admin_sees_inactive_and_update_delete(session, seed_two_tenants):
    a, _b = seed_two_tenants
    svc = ServiceCatalogService(session)
    item = await svc.create(
        tenant_id=a,
        name="Original",
        category="rede",
        description=None,
        sla_hours=None,
        icon="ticket",
        znuny_queue=None,
        znuny_service=None,
        default_priority=None,
        active=False,
        sort_order=0,
    )
    admin_rows = await svc.list_admin()
    assert item.id in {r.id for r in admin_rows}

    updated = await svc.update(
        item.id,
        name="Atualizado",
        category="rede",
        description="desc",
        sla_hours=8,
        icon="server",
        znuny_queue="Suporte::N1",
        znuny_service="Rede",
        default_priority="3 normal",
        active=True,
        sort_order=5,
    )
    assert updated.name == "Atualizado"
    assert updated.active is True

    await svc.delete(item.id)
    with pytest.raises(CatalogItemNotFound):
        await svc.get_admin(item.id)
