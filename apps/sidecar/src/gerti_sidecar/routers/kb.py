"""GET /v1/kb/* — portal (cliente): lista, detalhe por slug, categorias.

Spec #3 V1. tenant-scoped via get_tenant_session (RLS). Qualquer papel logado
(helpdesk ou admin) enxerga a Base de Conhecimento — não é dado financeiro.
O cliente vê **apenas** artigos `visibility='public' AND status='published'`;
o detalhe incrementa `views` (nunca o console). 404 cross-tenant/RLS/estado
errado — nunca 403 (anti-IDOR).
"""

from __future__ import annotations

import datetime as dt

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from gerti_sidecar.auth.session import SessionPayload, get_current_session
from gerti_sidecar.db import get_tenant_session
from gerti_sidecar.domain.errors import KbArticleNotFound
from gerti_sidecar.domain.kb_service import KbService
from gerti_sidecar.models import KbArticle

router = APIRouter(prefix="/kb", tags=["portal"])


class KbArticleItem(BaseModel):
    id: str
    slug: str
    title: str
    summary: str | None
    category: str
    tags: list[str]
    views: int
    updated_at: dt.datetime


class KbArticleDetail(KbArticleItem):
    body_markdown: str


class KbArticleListOut(BaseModel):
    items: list[KbArticleItem]
    total: int
    limit: int
    offset: int


class KbCategoryOut(BaseModel):
    category: str
    count: int


def _item(a: KbArticle) -> KbArticleItem:
    return KbArticleItem(
        id=str(a.id),
        slug=a.slug,
        title=a.title,
        summary=a.summary,
        category=a.category,
        tags=list(a.tags or []),
        views=a.views,
        updated_at=a.updated_at,
    )


@router.get("/articles", response_model=KbArticleListOut)
async def list_articles(
    q: str | None = Query(default=None, max_length=200),
    category: str | None = Query(default=None, max_length=60),
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    _session_payload: SessionPayload = Depends(get_current_session),
    session: AsyncSession = Depends(get_tenant_session),
) -> KbArticleListOut:
    rows, total = await KbService(session).list_public(
        q=q, category=category, limit=limit, offset=offset
    )
    return KbArticleListOut(items=[_item(r) for r in rows], total=total, limit=limit, offset=offset)


@router.get("/articles/{slug}", response_model=KbArticleDetail)
async def get_article(
    slug: str,
    _session_payload: SessionPayload = Depends(get_current_session),
    session: AsyncSession = Depends(get_tenant_session),
) -> KbArticleDetail:
    try:
        article = await KbService(session).get_public_by_slug(slug)
    except KbArticleNotFound as exc:
        raise HTTPException(status_code=404, detail="kb_article_not_found") from exc
    return KbArticleDetail(**_item(article).model_dump(), body_markdown=article.body_markdown)


@router.get("/categories", response_model=list[KbCategoryOut])
async def list_categories(
    _session_payload: SessionPayload = Depends(get_current_session),
    session: AsyncSession = Depends(get_tenant_session),
) -> list[KbCategoryOut]:
    rows = await KbService(session).categories_public()
    return [KbCategoryOut(category=c, count=n) for c, n in rows]
