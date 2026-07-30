"""/v1/admin/tenants/{id}/catalog/items — console (agente): CRUD do Catálogo de Serviços.

Spec #3 V2. Exige get_admin_session. Valida a existência do tenant via
AdminSessionLocal (BYPASSRLS) — `_resolve_tenant` copiado de
`routers/admin_invoices.py` — depois abre `tenant_session_scope` (RLS-subject)
e delega ao ServiceCatalogService. O console vê itens ativos e inativos.
"""

from __future__ import annotations

import datetime as dt
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import select

from gerti_sidecar import db
from gerti_sidecar.auth.admin_session import AdminSessionPayload, get_admin_session
from gerti_sidecar.db import tenant_session_scope
from gerti_sidecar.domain import audit_service
from gerti_sidecar.domain.errors import CatalogItemNotFound
from gerti_sidecar.domain.service_catalog_service import ServiceCatalogService
from gerti_sidecar.models import CatalogItem, Tenant
from gerti_sidecar.models.catalog_item import ALLOWED_ICONS

router = APIRouter(prefix="/admin/tenants", tags=["admin"])


class CatalogItemIn(BaseModel):
    name: str = Field(min_length=3, max_length=120)
    category: str = Field(min_length=2, max_length=60)
    description: str | None = Field(default=None, max_length=1000)
    sla_hours: int | None = Field(default=None, ge=1, le=720)
    icon: str = Field(default="ticket")
    znuny_queue: str | None = Field(default=None, max_length=200)
    znuny_service: str | None = Field(default=None, max_length=200)
    default_priority: str | None = Field(default=None, max_length=200)
    active: bool = True
    sort_order: int = Field(default=0, ge=0, le=999)

    @field_validator("icon")
    @classmethod
    def _icon_allowed(cls, v: str) -> str:
        if v not in ALLOWED_ICONS:
            raise ValueError(f"icon fora da allowlist: {v}")
        return v


class CatalogItemAdminOut(BaseModel):
    id: str
    name: str
    category: str
    description: str | None
    sla_hours: int | None
    icon: str
    znuny_queue: str | None
    znuny_service: str | None
    default_priority: str | None
    active: bool
    sort_order: int
    created_at: dt.datetime
    updated_at: dt.datetime


def _out(i: CatalogItem) -> CatalogItemAdminOut:
    return CatalogItemAdminOut(
        id=str(i.id),
        name=i.name,
        category=i.category,
        description=i.description,
        sla_hours=i.sla_hours,
        icon=i.icon,
        znuny_queue=i.znuny_queue,
        znuny_service=i.znuny_service,
        default_priority=i.default_priority,
        active=i.active,
        sort_order=i.sort_order,
        created_at=i.created_at,
        updated_at=i.updated_at,
    )


async def _resolve_tenant(tenant_id: str) -> uuid.UUID:
    """Valida UUID + existência (cross-tenant, BYPASSRLS) → 404 tenant_not_found."""
    try:
        tenant_uuid = uuid.UUID(tenant_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail="tenant_not_found") from exc
    if db.AdminSessionLocal is None:
        raise HTTPException(status_code=503, detail="admin_db_unavailable")
    async with db.AdminSessionLocal() as admin_session:
        found = await admin_session.execute(select(Tenant.id).where(Tenant.id == tenant_uuid))
        if found.first() is None:
            raise HTTPException(status_code=404, detail="tenant_not_found")
    return tenant_uuid


def _parse_item_id(item_id: str) -> uuid.UUID:
    try:
        return uuid.UUID(item_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail="catalog_item_not_found") from exc


@router.get("/{tenant_id}/catalog/items", response_model=list[CatalogItemAdminOut])
async def list_items(
    tenant_id: str,
    category: str | None = Query(default=None, max_length=60),
    active: bool | None = Query(default=None),
    _admin: AdminSessionPayload = Depends(get_admin_session),
) -> list[CatalogItemAdminOut]:
    tid = await _resolve_tenant(tenant_id)
    async with tenant_session_scope(tid) as session:
        rows = await ServiceCatalogService(session).list_admin(category=category, active=active)
        return [_out(r) for r in rows]


@router.post("/{tenant_id}/catalog/items", status_code=201, response_model=CatalogItemAdminOut)
async def create_item(
    tenant_id: str,
    body: CatalogItemIn,
    request: Request,
    admin: AdminSessionPayload = Depends(get_admin_session),
) -> CatalogItemAdminOut:
    tid = await _resolve_tenant(tenant_id)
    async with tenant_session_scope(tid) as session:
        item = await ServiceCatalogService(session).create(
            tenant_id=tid,
            name=body.name,
            category=body.category,
            description=body.description,
            sla_hours=body.sla_hours,
            icon=body.icon,
            znuny_queue=body.znuny_queue,
            znuny_service=body.znuny_service,
            default_priority=body.default_priority,
            active=body.active,
            sort_order=body.sort_order,
        )
        out = _out(item)

    await audit_service.record(
        actor_type="agent",
        actor_login=admin["agent_login"],
        tenant_id=tid,
        action="create",
        entity="service_catalog_item",
        entity_id=out.id,
        description=f'Criou item de catálogo "{body.name}"',
        ip=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
        metadata={"name": body.name, "category": body.category},
    )
    return out


@router.get("/{tenant_id}/catalog/items/{item_id}", response_model=CatalogItemAdminOut)
async def get_item(
    tenant_id: str,
    item_id: str,
    _admin: AdminSessionPayload = Depends(get_admin_session),
) -> CatalogItemAdminOut:
    tid = await _resolve_tenant(tenant_id)
    iid = _parse_item_id(item_id)
    async with tenant_session_scope(tid) as session:
        try:
            item = await ServiceCatalogService(session).get_admin(iid)
        except CatalogItemNotFound as exc:
            raise HTTPException(status_code=404, detail="catalog_item_not_found") from exc
        return _out(item)


@router.put("/{tenant_id}/catalog/items/{item_id}", response_model=CatalogItemAdminOut)
async def update_item(
    tenant_id: str,
    item_id: str,
    body: CatalogItemIn,
    request: Request,
    admin: AdminSessionPayload = Depends(get_admin_session),
) -> CatalogItemAdminOut:
    tid = await _resolve_tenant(tenant_id)
    iid = _parse_item_id(item_id)
    async with tenant_session_scope(tid) as session:
        try:
            item = await ServiceCatalogService(session).update(
                iid,
                name=body.name,
                category=body.category,
                description=body.description,
                sla_hours=body.sla_hours,
                icon=body.icon,
                znuny_queue=body.znuny_queue,
                znuny_service=body.znuny_service,
                default_priority=body.default_priority,
                active=body.active,
                sort_order=body.sort_order,
            )
        except CatalogItemNotFound as exc:
            raise HTTPException(status_code=404, detail="catalog_item_not_found") from exc
        out = _out(item)

    await audit_service.record(
        actor_type="agent",
        actor_login=admin["agent_login"],
        tenant_id=tid,
        action="update",
        entity="service_catalog_item",
        entity_id=out.id,
        description=f'Editou item de catálogo "{body.name}"',
        ip=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
        metadata={"name": body.name, "category": body.category},
    )
    return out


@router.delete("/{tenant_id}/catalog/items/{item_id}", status_code=204)
async def delete_item(
    tenant_id: str,
    item_id: str,
    request: Request,
    admin: AdminSessionPayload = Depends(get_admin_session),
) -> Response:
    tid = await _resolve_tenant(tenant_id)
    iid = _parse_item_id(item_id)
    async with tenant_session_scope(tid) as session:
        try:
            service = ServiceCatalogService(session)
            item = await service.get_admin(iid)
            name = item.name
            await service.delete(iid)
        except CatalogItemNotFound as exc:
            raise HTTPException(status_code=404, detail="catalog_item_not_found") from exc

    await audit_service.record(
        actor_type="agent",
        actor_login=admin["agent_login"],
        tenant_id=tid,
        action="delete",
        entity="service_catalog_item",
        entity_id=str(iid),
        description=f'Excluiu item de catálogo "{name}"',
        ip=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
        metadata={"name": name},
    )
    return Response(status_code=204)
