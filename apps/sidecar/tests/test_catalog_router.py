"""Router /v1/catalog/* — portal cliente (Spec #3 V2).

- sem gsid → 401
- lista/detalhe/categorias só `active=true`
- cross-tenant → 404 (nunca 403)
- item inativo → 404
- 422 de validação (query `category` acima do limite de tamanho)
"""

from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from gerti_sidecar import db
from gerti_sidecar.auth.session import encode_session
from gerti_sidecar.config import get_settings
from gerti_sidecar.main import create_app
from gerti_sidecar.models import CatalogItem, Tenant, TenantBranding, ZnunyInstance


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
async def test_catalog_client_flow(engine, app_session_factory, session, monkeypatch):
    monkeypatch.setenv("SESSION_SECRET", "test-secret-32-chars-minimum-xxxx")
    monkeypatch.setenv("ENVIRONMENT", "test")
    get_settings.cache_clear()

    tenant_a = await _seed_tenant(session, subdomain="aurora", name="Aurora")
    tenant_b = await _seed_tenant(session, subdomain="beta", name="Beta")

    active_item = CatalogItem(
        tenant_id=tenant_a.id,
        name="Reset de senha",
        category="acessos",
        description="Solicita redefinição de senha",
        sla_hours=4,
        icon="lock",
        znuny_queue="Suporte::N1",
        znuny_service="Acessos",
        default_priority="3 normal",
        active=True,
        sort_order=0,
    )
    inactive_item = CatalogItem(
        tenant_id=tenant_a.id,
        name="Serviço desativado",
        category="acessos",
        icon="ticket",
        active=False,
        sort_order=1,
    )
    other_tenant_item = CatalogItem(
        tenant_id=tenant_b.id,
        name="Item do tenant B",
        category="rede",
        icon="wifi",
        active=True,
        sort_order=0,
    )
    session.add_all([active_item, inactive_item, other_tenant_item])
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
        assert (await c.get("/v1/catalog/items", headers=h)).status_code == 401

        c.cookies.set("gsid", encode_session(str(tenant_a.id), "joe", "helpdesk", st))

        # lista só o item ativo
        lst = await c.get("/v1/catalog/items", headers=h)
        assert lst.status_code == 200
        items = lst.json()
        assert len(items) == 1
        assert items[0]["name"] == "Reset de senha"
        assert "znuny_queue" not in items[0]  # forma resumida (sem campos internos)

        # categorias só contam ativos
        cats = await c.get("/v1/catalog/categories", headers=h)
        assert cats.status_code == 200
        assert cats.json() == [{"category": "acessos", "count": 1}]

        # detalhe completo do item ativo
        detail = await c.get(f"/v1/catalog/items/{active_item.id}", headers=h)
        assert detail.status_code == 200
        d = detail.json()
        assert d["znuny_queue"] == "Suporte::N1"
        assert d["default_priority"] == "3 normal"

        # item inativo -> 404
        assert (await c.get(f"/v1/catalog/items/{inactive_item.id}", headers=h)).status_code == 404

        # cross-tenant -> 404, nunca 403
        assert (
            await c.get(f"/v1/catalog/items/{other_tenant_item.id}", headers=h)
        ).status_code == 404

        # id malformado -> 404 (guard, nunca 400/500)
        assert (await c.get("/v1/catalog/items/not-a-uuid", headers=h)).status_code == 404

        # 422 de validação: category acima do limite de tamanho (60)
        bad = await c.get("/v1/catalog/items", params={"category": "x" * 61}, headers=h)
        assert bad.status_code == 422
