"""KbService — Base de Conhecimento (Spec #3 V1).

Slug derivado do título (minúsculas, sem acento, `[a-z0-9-]`), único por
tenant — em colisão sufixa `-2`, `-3`… Gerado uma única vez na criação; o
update NUNCA recalcula (preserva links). `views` incrementa via
`UPDATE ... SET views = views + 1` (sem race), nunca no console.

Colisão de UNIQUE(tenant_id, slug) não encerra a operação: usa
`session.begin_nested()` (savepoint) para tentar o próximo sufixo sem
derrubar a transação externa (que carrega o GUC `app.current_tenant`).
"""

from __future__ import annotations

import re
import unicodedata
import uuid
from collections.abc import Sequence

from sqlalchemy import Select, func, or_, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from gerti_sidecar.domain.errors import KbArticleNotFound, KbSlugExhausted
from gerti_sidecar.models import KbArticle

MAX_SLUG_ATTEMPTS = 200
DEFAULT_LIMIT = 20


def slugify(value: str) -> str:
    """minúsculas, sem acento, `[a-z0-9-]`; nunca vazio (fallback "artigo")."""
    normalized = unicodedata.normalize("NFKD", value)
    without_accents = "".join(c for c in normalized if not unicodedata.combining(c))
    lowered = without_accents.lower()
    slug = re.sub(r"[^a-z0-9]+", "-", lowered).strip("-")
    return slug or "artigo"


def normalize_tags(tags: Sequence[str]) -> list[str]:
    """minúsculas, sem duplicatas, preserva ordem de primeira aparição."""
    out: list[str] = []
    seen: set[str] = set()
    for raw in tags:
        tag = raw.strip().lower()
        if not tag or tag in seen:
            continue
        seen.add(tag)
        out.append(tag)
    return out


class KbService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    # --- portal cliente (só public+published) ---

    async def list_public(
        self,
        *,
        q: str | None = None,
        category: str | None = None,
        limit: int = DEFAULT_LIMIT,
        offset: int = 0,
    ) -> tuple[list[KbArticle], int]:
        stmt = select(KbArticle).where(
            KbArticle.visibility == "public", KbArticle.status == "published"
        )
        stmt = _apply_filters(stmt, q=q, category=category)
        total = await self.session.scalar(select(func.count()).select_from(stmt.subquery()))
        rows = (
            (
                await self.session.execute(
                    stmt.order_by(KbArticle.updated_at.desc()).limit(limit).offset(offset)
                )
            )
            .scalars()
            .all()
        )
        return list(rows), int(total or 0)

    async def get_public_by_slug(self, slug: str) -> KbArticle:
        row = (
            await self.session.execute(
                select(KbArticle).where(
                    KbArticle.slug == slug,
                    KbArticle.visibility == "public",
                    KbArticle.status == "published",
                )
            )
        ).scalar_one_or_none()
        if row is None:
            raise KbArticleNotFound("artigo inexistente ou não publicado")
        await self.session.execute(
            update(KbArticle).where(KbArticle.id == row.id).values(views=KbArticle.views + 1)
        )
        await self.session.flush()
        await self.session.refresh(row)
        return row

    async def categories_public(self) -> list[tuple[str, int]]:
        rows = (
            await self.session.execute(
                select(KbArticle.category, func.count())
                .where(KbArticle.visibility == "public", KbArticle.status == "published")
                .group_by(KbArticle.category)
                .order_by(func.count().desc(), KbArticle.category.asc())
            )
        ).all()
        return [(r[0], int(r[1])) for r in rows]

    # --- console (cross-status/visibility) ---

    async def list_admin(
        self,
        *,
        q: str | None = None,
        category: str | None = None,
        status: str | None = None,
        limit: int = DEFAULT_LIMIT,
        offset: int = 0,
    ) -> tuple[list[KbArticle], int]:
        stmt = select(KbArticle)
        stmt = _apply_filters(stmt, q=q, category=category)
        if status:
            stmt = stmt.where(KbArticle.status == status)
        total = await self.session.scalar(select(func.count()).select_from(stmt.subquery()))
        rows = (
            (
                await self.session.execute(
                    stmt.order_by(KbArticle.updated_at.desc()).limit(limit).offset(offset)
                )
            )
            .scalars()
            .all()
        )
        return list(rows), int(total or 0)

    async def get_admin(self, article_id: uuid.UUID) -> KbArticle:
        row = await self.session.get(KbArticle, article_id)
        if row is None:
            raise KbArticleNotFound("artigo inexistente neste tenant")
        return row

    async def create(
        self,
        *,
        tenant_id: uuid.UUID,
        title: str,
        summary: str | None,
        body_markdown: str,
        category: str,
        tags: list[str],
        visibility: str,
        status: str,
        author_login: str | None,
    ) -> KbArticle:
        base_slug = slugify(title)
        for attempt in range(MAX_SLUG_ATTEMPTS):
            candidate = base_slug if attempt == 0 else f"{base_slug}-{attempt + 1}"
            article = KbArticle(
                tenant_id=tenant_id,
                slug=candidate,
                title=title,
                summary=summary,
                body_markdown=body_markdown,
                category=category,
                tags=tags,
                visibility=visibility,
                status=status,
                author_login=author_login,
            )
            # Savepoint aberto antes do add: colisão de UNIQUE(tenant_id, slug)
            # é desfeita sem derrubar a transação externa (GUC app.current_tenant).
            sp = await self.session.begin_nested()
            try:
                self.session.add(article)
                await self.session.flush()
            except IntegrityError:
                await sp.rollback()
                continue
            return article
        raise KbSlugExhausted("não foi possível gerar um slug único para este título")

    async def update(
        self,
        article_id: uuid.UUID,
        *,
        title: str,
        summary: str | None,
        body_markdown: str,
        category: str,
        tags: list[str],
        visibility: str,
        status: str,
    ) -> KbArticle:
        article = await self.get_admin(article_id)
        # slug NÃO muda no update (preserva links externos).
        article.title = title
        article.summary = summary
        article.body_markdown = body_markdown
        article.category = category
        article.tags = tags
        article.visibility = visibility
        article.status = status
        await self.session.flush()
        # `updated_at` (onupdate=func.now()) fica expirado após o UPDATE; sem o
        # refresh, o acesso síncrono no router (Pydantic model_dump) dispara um
        # lazy-load fora do greenlet do AsyncSession -> MissingGreenlet.
        await self.session.refresh(article)
        return article

    async def delete(self, article_id: uuid.UUID) -> None:
        article = await self.get_admin(article_id)
        await self.session.delete(article)
        await self.session.flush()


def _apply_filters(
    stmt: Select[tuple[KbArticle]], *, q: str | None, category: str | None
) -> Select[tuple[KbArticle]]:
    if category:
        stmt = stmt.where(KbArticle.category == category)
    if q:
        like = f"%{q.lower()}%"
        stmt = stmt.where(
            or_(
                func.lower(KbArticle.title).like(like),
                func.lower(KbArticle.summary).like(like),
                func.lower(KbArticle.body_markdown).like(like),
            )
        )
    return stmt
