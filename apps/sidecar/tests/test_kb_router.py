"""Router /v1/kb/* — portal cliente (Spec #3 V1).

- sem gsid → 401
- lista/detalhe/categorias só `public`+`published`; detalhe incrementa views
- cross-tenant → 404 (nunca 403)
- draft/internal → 404 (mesmo tenant)
- 422 de validação (limit fora do range)
"""

from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from gerti_sidecar import db
from gerti_sidecar.auth.session import encode_session
from gerti_sidecar.config import get_settings
from gerti_sidecar.main import create_app
from gerti_sidecar.models import KbArticle, Tenant, TenantBranding, ZnunyInstance


async def _seed_tenant(session, *, subdomain: str, name: str) -> Tenant:
    inst = ZnunyInstance(
        name=f"inst-{subdomain}",
        base_url="http://znuny",
        db_dsn_secret_ref="x",
        webservice_token_secret_ref="x",
        webhook_signing_secret_ref="x",
        mode="pool",
    )
    session.add(inst)
    await session.flush()
    t = Tenant(
        legal_name=name,
        trade_name=name,
        document=subdomain,
        znuny_customer_id=subdomain.upper(),
        znuny_instance_id=inst.id,
        subdomain=subdomain,
    )
    session.add(t)
    await session.flush()
    session.add(TenantBranding(tenant_id=t.id, display_name=name))
    await session.commit()
    return t


@pytest.mark.asyncio
async def test_kb_client_flow(engine, app_session_factory, session, monkeypatch):
    monkeypatch.setenv("SESSION_SECRET", "test-secret-32-chars-minimum-xxxx")
    monkeypatch.setenv("ENVIRONMENT", "test")
    get_settings.cache_clear()

    tenant_a = await _seed_tenant(session, subdomain="aurora", name="Aurora")
    tenant_b = await _seed_tenant(session, subdomain="beta", name="Beta")

    published_public = KbArticle(
        tenant_id=tenant_a.id,
        slug="como-resetar-senha",
        title="Como resetar senha",
        summary="Passo a passo",
        body_markdown="# Passo a passo\n\n1. faça x",
        category="acessos",
        tags=["senha", "acesso"],
        visibility="public",
        status="published",
    )
    draft_public = KbArticle(
        tenant_id=tenant_a.id,
        slug="rascunho-nao-publicado",
        title="Rascunho não publicado",
        body_markdown="rascunho",
        category="acessos",
        tags=[],
        visibility="public",
        status="draft",
    )
    published_internal = KbArticle(
        tenant_id=tenant_a.id,
        slug="artigo-interno",
        title="Artigo interno",
        body_markdown="uso interno da equipe",
        category="processos",
        tags=[],
        visibility="internal",
        status="published",
    )
    other_tenant_article = KbArticle(
        tenant_id=tenant_b.id,
        slug="artigo-do-tenant-b",
        title="Artigo do tenant B",
        body_markdown="x",
        category="rede",
        tags=[],
        visibility="public",
        status="published",
    )
    session.add_all([published_public, draft_public, published_internal, other_tenant_article])
    await session.commit()

    monkeypatch.setattr(
        db,
        "AdminSessionLocal",
        async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession),
    )
    monkeypatch.setattr(db, "SessionLocal", app_session_factory)
    app = create_app()
    st = get_settings()
    h = {"host": "aurora.suporte.gerti.com.br"}

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        # sem sessão -> 401
        assert (await c.get("/v1/kb/articles", headers=h)).status_code == 401

        c.cookies.set("gsid", encode_session(str(tenant_a.id), "joe", "helpdesk", st))

        # lista só vê o artigo público publicado do próprio tenant
        lst = await c.get("/v1/kb/articles", headers=h)
        assert lst.status_code == 200
        body = lst.json()
        assert body["total"] == 1
        assert body["items"][0]["slug"] == "como-resetar-senha"
        assert body["items"][0]["views"] == 0

        # categorias
        cats = await c.get("/v1/kb/categories", headers=h)
        assert cats.status_code == 200
        assert cats.json() == [{"category": "acessos", "count": 1}]

        # detalhe incrementa views
        detail1 = await c.get("/v1/kb/articles/como-resetar-senha", headers=h)
        assert detail1.status_code == 200
        assert detail1.json()["views"] == 1
        assert "body_markdown" in detail1.json()
        detail2 = await c.get("/v1/kb/articles/como-resetar-senha", headers=h)
        assert detail2.json()["views"] == 2

        # draft -> 404 (mesmo tenant, mesmo dono)
        assert (await c.get("/v1/kb/articles/rascunho-nao-publicado", headers=h)).status_code == 404

        # internal -> 404
        assert (await c.get("/v1/kb/articles/artigo-interno", headers=h)).status_code == 404

        # cross-tenant -> 404, nunca 403
        assert (await c.get("/v1/kb/articles/artigo-do-tenant-b", headers=h)).status_code == 404

        # 422 de validação: limit fora do range
        bad = await c.get("/v1/kb/articles", params={"limit": 0}, headers=h)
        assert bad.status_code == 422
