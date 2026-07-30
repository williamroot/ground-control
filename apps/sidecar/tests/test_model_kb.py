"""Model KbArticle: CheckConstraints + RLS de tenant (Spec #3 V1, agente B1)."""

from __future__ import annotations

import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import DBAPIError, IntegrityError

from gerti_sidecar.models import KbArticle


def _article(tenant_id, **overrides):
    defaults = dict(
        tenant_id=tenant_id,
        slug="artigo-teste",
        title="Artigo teste",
        summary="resumo",
        body_markdown="# oi",
        category="rede",
        tags=["vpn", "wifi"],
        visibility="public",
        status="published",
    )
    defaults.update(overrides)
    return KbArticle(**defaults)


@pytest.mark.asyncio
async def test_visibility_check_constraint(session, seed_two_tenants):
    a, _b = seed_two_tenants
    session.add(_article(a, visibility="not_a_real_visibility"))
    with pytest.raises((IntegrityError, DBAPIError)):
        await session.flush()
    await session.rollback()


@pytest.mark.asyncio
async def test_status_check_constraint(session, seed_two_tenants):
    a, _b = seed_two_tenants
    session.add(_article(a, status="not_a_real_status"))
    with pytest.raises((IntegrityError, DBAPIError)):
        await session.flush()
    await session.rollback()


@pytest.mark.asyncio
async def test_unique_tenant_slug(session, seed_two_tenants):
    a, b = seed_two_tenants
    session.add(_article(a, slug="mesmo-slug"))
    await session.flush()
    # mesmo slug, mesmo tenant -> colide
    session.add(_article(a, slug="mesmo-slug", title="outro"))
    with pytest.raises((IntegrityError, DBAPIError)):
        await session.flush()
    await session.rollback()
    # mesmo slug, tenant diferente -> OK (unique é por tenant)
    session.add(_article(b, slug="mesmo-slug", title="outro tenant"))
    await session.flush()


@pytest.mark.asyncio
async def test_default_values(session, seed_two_tenants):
    a, _b = seed_two_tenants
    article = _article(a, tags=[])
    session.add(article)
    await session.flush()
    await session.refresh(article)
    assert article.views == 0
    assert article.tags == []
    assert article.created_at is not None
    assert article.updated_at is not None


@pytest.mark.asyncio
async def test_rls_isolation(engine, app_session_factory, seed_two_tenants):
    """RLS-subject session só enxerga artigos do tenant do GUC — prova cross-tenant."""
    a, b = seed_two_tenants
    factory = app_session_factory
    async with factory() as s:
        async with s.begin():
            await s.execute(
                text("SELECT set_config('app.current_tenant', :t, true)"), {"t": str(a)}
            )
            s.add(_article(a, slug="artigo-a", title="Artigo A"))
    async with factory() as s:
        async with s.begin():
            await s.execute(
                text("SELECT set_config('app.current_tenant', :t, true)"), {"t": str(b)}
            )
            s.add(_article(b, slug="artigo-b", title="Artigo B"))

    # tenant A só vê o seu
    async with factory() as s:
        async with s.begin():
            await s.execute(
                text("SELECT set_config('app.current_tenant', :t, true)"), {"t": str(a)}
            )
            rows = (await s.execute(select(KbArticle.title))).scalars().all()
    assert rows == ["Artigo A"]

    # tenant B não enxerga a linha do tenant A mesmo tentando o id direto
    async with factory() as s:
        async with s.begin():
            await s.execute(
                text("SELECT set_config('app.current_tenant', :t, true)"), {"t": str(b)}
            )
            rows_b = (await s.execute(select(KbArticle.title))).scalars().all()
    assert rows_b == ["Artigo B"]
