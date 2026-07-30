"""GET /v1/catalog/* — portal (cliente): vitrine de serviços, detalhe, categorias.

Spec #3 V2. tenant-scoped via get_tenant_session (RLS). O cliente vê
**apenas** itens `active=true`; usado por `/catalogo` (vitrine) e por
`/tickets/novo?servico=<id>` (pré-preenchimento). 404 cross-tenant/RLS/
inativo — nunca 403 (anti-IDOR).
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from gerti_sidecar.auth.session import SessionPayload, get_current_session
from gerti_sidecar.db import get_tenant_session
from gerti_sidecar.domain.errors import CatalogItemNotFound
from gerti_sidecar.domain.service_catalog_service import ServiceCatalogService
from gerti_sidecar.models import CatalogItem

router = APIRouter(prefix="/catalog", tags=["portal"])


class CatalogItemPublic(BaseModel):
    id: str
    name: str
    category: str
    description: str | None
    sla_hours: int | None
    icon: str


class CatalogItemDetail(CatalogItemPublic):
    znuny_queue: str | None
    znuny_service: str | None
    default_priority: str | None


class CatalogCategoryOut(BaseModel):
    category: str
    count: int


def _item(i: CatalogItem) -> CatalogItemPublic:
    return CatalogItemPublic(
        id=str(i.id),
        name=i.name,
        category=i.category,
        description=i.description,
        sla_hours=i.sla_hours,
        icon=i.icon,
    )


@router.get("/items", response_model=list[CatalogItemPublic])
async def list_items(
    category: str | None = Query(default=None, max_length=60),
    _session_payload: SessionPayload = Depends(get_current_session),
    session: AsyncSession = Depends(get_tenant_session),
) -> list[CatalogItemPublic]:
    rows = await ServiceCatalogService(session).list_public(category=category)
    return [_item(r) for r in rows]


def _parse_uuid(item_id: str) -> uuid.UUID:
    try:
        return uuid.UUID(item_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail="catalog_item_not_found") from exc


@router.get("/items/{item_id}", response_model=CatalogItemDetail)
async def get_item(
    item_id: str,
    _session_payload: SessionPayload = Depends(get_current_session),
    session: AsyncSession = Depends(get_tenant_session),
) -> CatalogItemDetail:
    uid = _parse_uuid(item_id)
    try:
        item = await ServiceCatalogService(session).get_public(uid)
    except CatalogItemNotFound as exc:
        raise HTTPException(status_code=404, detail="catalog_item_not_found") from exc
    return CatalogItemDetail(
        **_item(item).model_dump(),
        znuny_queue=item.znuny_queue,
        znuny_service=item.znuny_service,
        default_priority=item.default_priority,
    )


@router.get("/categories", response_model=list[CatalogCategoryOut])
async def list_categories(
    _session_payload: SessionPayload = Depends(get_current_session),
    session: AsyncSession = Depends(get_tenant_session),
) -> list[CatalogCategoryOut]:
    rows = await ServiceCatalogService(session).categories_public()
    return [CatalogCategoryOut(category=c, count=n) for c, n in rows]
