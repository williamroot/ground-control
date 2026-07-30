"""/v1/admin/tenants/{id}/kb/articles — console (agente): CRUD da Base de Conhecimento.

Spec #3 V1. Exige get_admin_session. Valida a existência do tenant via
AdminSessionLocal (BYPASSRLS) — `_resolve_tenant` copiado de
`routers/admin_invoices.py` — depois abre `tenant_session_scope` (RLS-subject)
e delega ao KbService. O console vê artigos em qualquer status/visibility
(inclusive draft/internal) e NUNCA incrementa `views`.
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
from gerti_sidecar.domain.errors import KbArticleNotFound, KbSlugExhausted
from gerti_sidecar.domain.kb_service import KbService, normalize_tags
from gerti_sidecar.models import KbArticle, Tenant

router = APIRouter(prefix="/admin/tenants", tags=["admin"])

_VISIBILITIES = ("public", "internal")
_STATUSES = ("draft", "published", "archived")


class KbArticleIn(BaseModel):
    title: str = Field(min_length=3, max_length=200)
    summary: str | None = Field(default=None, max_length=500)
    body_markdown: str = Field(min_length=1, max_length=50000)
    category: str = Field(min_length=2, max_length=60)
    tags: list[str] = Field(default_factory=list)
    visibility: str
    status: str

    @field_validator("visibility")
    @classmethod
    def _visibility_allowed(cls, v: str) -> str:
        if v not in _VISIBILITIES:
            raise ValueError(f"visibility inválida: {v}")
        return v

    @field_validator("status")
    @classmethod
    def _status_allowed(cls, v: str) -> str:
        if v not in _STATUSES:
            raise ValueError(f"status inválido: {v}")
        return v

    @field_validator("tags")
    @classmethod
    def _tags_valid(cls, v: list[str]) -> list[str]:
        if len(v) > 10:
            raise ValueError("no máximo 10 tags")
        for tag in v:
            if len(tag.strip()) > 30:
                raise ValueError("tag com mais de 30 caracteres")
        return normalize_tags(v)


class KbArticleAdminItem(BaseModel):
    id: str
    slug: str
    title: str
    summary: str | None
    category: str
    tags: list[str]
    visibility: str
    status: str
    views: int
    updated_at: dt.datetime


class KbArticleAdminDetail(KbArticleAdminItem):
    body_markdown: str
    author_login: str | None
    created_at: dt.datetime


class KbArticleAdminListOut(BaseModel):
    items: list[KbArticleAdminItem]
    total: int
    limit: int
    offset: int


def _item(a: KbArticle) -> KbArticleAdminItem:
    return KbArticleAdminItem(
        id=str(a.id),
        slug=a.slug,
        title=a.title,
        summary=a.summary,
        category=a.category,
        tags=list(a.tags or []),
        visibility=a.visibility,
        status=a.status,
        views=a.views,
        updated_at=a.updated_at,
    )


def _detail(a: KbArticle) -> KbArticleAdminDetail:
    return KbArticleAdminDetail(
        **_item(a).model_dump(),
        body_markdown=a.body_markdown,
        author_login=a.author_login,
        created_at=a.created_at,
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


def _parse_article_id(article_id: str) -> uuid.UUID:
    try:
        return uuid.UUID(article_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail="kb_article_not_found") from exc


@router.get("/{tenant_id}/kb/articles", response_model=KbArticleAdminListOut)
async def list_articles(
    tenant_id: str,
    q: str | None = Query(default=None, max_length=200),
    category: str | None = Query(default=None, max_length=60),
    status: str | None = Query(default=None, max_length=20),
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    _admin: AdminSessionPayload = Depends(get_admin_session),
) -> KbArticleAdminListOut:
    tid = await _resolve_tenant(tenant_id)
    async with tenant_session_scope(tid) as session:
        rows, total = await KbService(session).list_admin(
            q=q, category=category, status=status, limit=limit, offset=offset
        )
        return KbArticleAdminListOut(
            items=[_item(r) for r in rows], total=total, limit=limit, offset=offset
        )


@router.post("/{tenant_id}/kb/articles", status_code=201, response_model=KbArticleAdminDetail)
async def create_article(
    tenant_id: str,
    body: KbArticleIn,
    request: Request,
    admin: AdminSessionPayload = Depends(get_admin_session),
) -> KbArticleAdminDetail:
    tid = await _resolve_tenant(tenant_id)
    async with tenant_session_scope(tid) as session:
        try:
            article = await KbService(session).create(
                tenant_id=tid,
                title=body.title,
                summary=body.summary,
                body_markdown=body.body_markdown,
                category=body.category,
                tags=body.tags,
                visibility=body.visibility,
                status=body.status,
                author_login=admin["agent_login"],
            )
        except KbSlugExhausted as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        out = _detail(article)

    await audit_service.record(
        actor_type="agent",
        actor_login=admin["agent_login"],
        tenant_id=tid,
        action="create",
        entity="kb_article",
        entity_id=out.id,
        description=f'Criou artigo "{body.title}"',
        ip=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
        metadata={"title": body.title, "category": body.category},
    )
    return out


@router.get("/{tenant_id}/kb/articles/{article_id}", response_model=KbArticleAdminDetail)
async def get_article(
    tenant_id: str,
    article_id: str,
    _admin: AdminSessionPayload = Depends(get_admin_session),
) -> KbArticleAdminDetail:
    tid = await _resolve_tenant(tenant_id)
    aid = _parse_article_id(article_id)
    async with tenant_session_scope(tid) as session:
        try:
            article = await KbService(session).get_admin(aid)
        except KbArticleNotFound as exc:
            raise HTTPException(status_code=404, detail="kb_article_not_found") from exc
        return _detail(article)


@router.put("/{tenant_id}/kb/articles/{article_id}", response_model=KbArticleAdminDetail)
async def update_article(
    tenant_id: str,
    article_id: str,
    body: KbArticleIn,
    request: Request,
    admin: AdminSessionPayload = Depends(get_admin_session),
) -> KbArticleAdminDetail:
    tid = await _resolve_tenant(tenant_id)
    aid = _parse_article_id(article_id)
    async with tenant_session_scope(tid) as session:
        try:
            article = await KbService(session).update(
                aid,
                title=body.title,
                summary=body.summary,
                body_markdown=body.body_markdown,
                category=body.category,
                tags=body.tags,
                visibility=body.visibility,
                status=body.status,
            )
        except KbArticleNotFound as exc:
            raise HTTPException(status_code=404, detail="kb_article_not_found") from exc
        out = _detail(article)

    await audit_service.record(
        actor_type="agent",
        actor_login=admin["agent_login"],
        tenant_id=tid,
        action="update",
        entity="kb_article",
        entity_id=out.id,
        description=f'Editou artigo "{body.title}"',
        ip=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
        metadata={"title": body.title, "category": body.category},
    )
    return out


@router.delete("/{tenant_id}/kb/articles/{article_id}", status_code=204)
async def delete_article(
    tenant_id: str,
    article_id: str,
    request: Request,
    admin: AdminSessionPayload = Depends(get_admin_session),
) -> Response:
    tid = await _resolve_tenant(tenant_id)
    aid = _parse_article_id(article_id)
    async with tenant_session_scope(tid) as session:
        try:
            service = KbService(session)
            article = await service.get_admin(aid)
            title = article.title
            await service.delete(aid)
        except KbArticleNotFound as exc:
            raise HTTPException(status_code=404, detail="kb_article_not_found") from exc

    await audit_service.record(
        actor_type="agent",
        actor_login=admin["agent_login"],
        tenant_id=tid,
        action="delete",
        entity="kb_article",
        entity_id=str(aid),
        description=f'Excluiu artigo "{title}"',
        ip=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
        metadata={"title": title},
    )
    return Response(status_code=204)
