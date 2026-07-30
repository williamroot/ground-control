"""KbService: slug único/colisão, filtros, incremento de views (Spec #3 V1)."""

from __future__ import annotations

import pytest

from gerti_sidecar.domain.errors import KbArticleNotFound
from gerti_sidecar.domain.kb_service import KbService, normalize_tags, slugify


def test_slugify_strips_accents_and_symbols():
    assert slugify("Configuração de VPN — Guia!") == "configuracao-de-vpn-guia"
    assert slugify("   ") == "artigo"
    assert slugify("Ação & Reação") == "acao-reacao"


def test_normalize_tags_dedupes_and_lowercases():
    assert normalize_tags(["VPN", "vpn", " Wifi ", "wifi"]) == ["vpn", "wifi"]


@pytest.mark.asyncio
async def test_create_generates_unique_slug_on_collision(session, seed_two_tenants):
    a, _b = seed_two_tenants
    svc = KbService(session)
    first = await svc.create(
        tenant_id=a,
        title="Como resetar a senha",
        summary=None,
        body_markdown="passo a passo",
        category="acessos",
        tags=[],
        visibility="public",
        status="published",
        author_login="agente1",
    )
    second = await svc.create(
        tenant_id=a,
        title="Como resetar a senha",
        summary=None,
        body_markdown="outro conteúdo",
        category="acessos",
        tags=[],
        visibility="public",
        status="published",
        author_login="agente1",
    )
    third = await svc.create(
        tenant_id=a,
        title="Como resetar a senha",
        summary=None,
        body_markdown="mais um",
        category="acessos",
        tags=[],
        visibility="public",
        status="published",
        author_login="agente1",
    )
    assert first.slug == "como-resetar-a-senha"
    assert second.slug == "como-resetar-a-senha-2"
    assert third.slug == "como-resetar-a-senha-3"


@pytest.mark.asyncio
async def test_update_does_not_change_slug(session, seed_two_tenants):
    a, _b = seed_two_tenants
    svc = KbService(session)
    article = await svc.create(
        tenant_id=a,
        title="Título original",
        summary=None,
        body_markdown="conteúdo",
        category="rede",
        tags=[],
        visibility="public",
        status="draft",
        author_login="agente1",
    )
    original_slug = article.slug
    updated = await svc.update(
        article.id,
        title="Título completamente diferente",
        summary="novo resumo",
        body_markdown="conteúdo novo",
        category="rede",
        tags=["a"],
        visibility="internal",
        status="published",
    )
    assert updated.slug == original_slug
    assert updated.title == "Título completamente diferente"
    assert updated.visibility == "internal"
    assert updated.status == "published"


@pytest.mark.asyncio
async def test_list_public_filters_by_visibility_and_status(session, seed_two_tenants):
    a, _b = seed_two_tenants
    svc = KbService(session)
    await svc.create(
        tenant_id=a,
        title="Publicado público",
        summary=None,
        body_markdown="x",
        category="rede",
        tags=[],
        visibility="public",
        status="published",
        author_login=None,
    )
    await svc.create(
        tenant_id=a,
        title="Rascunho público",
        summary=None,
        body_markdown="x",
        category="rede",
        tags=[],
        visibility="public",
        status="draft",
        author_login=None,
    )
    await svc.create(
        tenant_id=a,
        title="Interno publicado",
        summary=None,
        body_markdown="x",
        category="rede",
        tags=[],
        visibility="internal",
        status="published",
        author_login=None,
    )
    rows, total = await svc.list_public()
    assert total == 1
    assert [r.title for r in rows] == ["Publicado público"]


@pytest.mark.asyncio
async def test_list_public_filters_by_q_and_category(session, seed_two_tenants):
    a, _b = seed_two_tenants
    svc = KbService(session)
    await svc.create(
        tenant_id=a,
        title="Configurar VPN",
        summary="tutorial de vpn",
        body_markdown="x",
        category="rede",
        tags=[],
        visibility="public",
        status="published",
        author_login=None,
    )
    await svc.create(
        tenant_id=a,
        title="Trocar impressora",
        summary=None,
        body_markdown="x",
        category="hardware",
        tags=[],
        visibility="public",
        status="published",
        author_login=None,
    )
    rows, total = await svc.list_public(q="vpn")
    assert total == 1
    assert rows[0].title == "Configurar VPN"

    rows2, total2 = await svc.list_public(category="hardware")
    assert total2 == 1
    assert rows2[0].title == "Trocar impressora"


@pytest.mark.asyncio
async def test_get_public_by_slug_increments_views_and_hides_draft(session, seed_two_tenants):
    a, _b = seed_two_tenants
    svc = KbService(session)
    published = await svc.create(
        tenant_id=a,
        title="Artigo publicado",
        summary=None,
        body_markdown="x",
        category="rede",
        tags=[],
        visibility="public",
        status="published",
        author_login=None,
    )
    draft = await svc.create(
        tenant_id=a,
        title="Artigo rascunho",
        summary=None,
        body_markdown="x",
        category="rede",
        tags=[],
        visibility="public",
        status="draft",
        author_login=None,
    )
    assert published.views == 0
    fetched = await svc.get_public_by_slug(published.slug)
    assert fetched.views == 1
    fetched_again = await svc.get_public_by_slug(published.slug)
    assert fetched_again.views == 2

    with pytest.raises(KbArticleNotFound):
        await svc.get_public_by_slug(draft.slug)


@pytest.mark.asyncio
async def test_categories_public_counts_only_public_published(session, seed_two_tenants):
    a, _b = seed_two_tenants
    svc = KbService(session)
    for i in range(3):
        await svc.create(
            tenant_id=a,
            title=f"Rede {i}",
            summary=None,
            body_markdown="x",
            category="rede",
            tags=[],
            visibility="public",
            status="published",
            author_login=None,
        )
    await svc.create(
        tenant_id=a,
        title="Hardware 1",
        summary=None,
        body_markdown="x",
        category="hardware",
        tags=[],
        visibility="internal",
        status="published",
        author_login=None,
    )
    cats = await svc.categories_public()
    assert cats == [("rede", 3)]


@pytest.mark.asyncio
async def test_admin_get_and_delete(session, seed_two_tenants):
    a, _b = seed_two_tenants
    svc = KbService(session)
    article = await svc.create(
        tenant_id=a,
        title="Para excluir",
        summary=None,
        body_markdown="x",
        category="rede",
        tags=[],
        visibility="internal",
        status="draft",
        author_login=None,
    )
    fetched = await svc.get_admin(article.id)
    assert fetched.id == article.id
    await svc.delete(article.id)
    with pytest.raises(KbArticleNotFound):
        await svc.get_admin(article.id)
