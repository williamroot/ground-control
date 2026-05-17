"""Middleware deve resolver tenant por subdomínio e setar app.current_tenant."""

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from gerti_sidecar import db
from gerti_sidecar.config import get_settings
from gerti_sidecar.main import create_app
from gerti_sidecar.models import Tenant, ZnunyInstance


@pytest.fixture
async def acme_tenant(session, monkeypatch):
    inst = ZnunyInstance(
        name="main",
        base_url="http://znuny:80",
        db_dsn_secret_ref="x",
        webservice_token_secret_ref="x",
        webhook_signing_secret_ref="x",
        mode="pool",
    )
    session.add(inst)
    await session.flush()
    t = Tenant(
        legal_name="Acme",
        trade_name="Acme",
        document="00",
        znuny_customer_id="acme",
        znuny_instance_id=inst.id,
        subdomain="acme",
    )
    session.add(t)
    await session.commit()
    return t


@pytest.mark.asyncio
async def test_request_with_subdomain_sets_tenant(
    monkeypatch: pytest.MonkeyPatch, db_url: str, engine, acme_tenant: Tenant
) -> None:
    monkeypatch.setenv("DATABASE_URL", db_url)
    monkeypatch.setenv("ENVIRONMENT", "test")
    get_settings.cache_clear()
    # lifespan não roda sob ASGITransport: liga SessionLocal à engine de teste
    monkeypatch.setattr(
        db, "SessionLocal", async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    )
    app = create_app()

    @app.get("/v1/_probe")
    async def _probe() -> dict[str, bool]:
        return {"ok": True}

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://acme.suporte.gerti.com.br") as ac:
        response = await ac.get("/v1/_probe")
    assert response.status_code == 200
    # tenant_id deve aparecer em header de debug
    assert response.headers.get("x-gerti-tenant") == str(acme_tenant.id)


@pytest.mark.asyncio
async def test_request_without_subdomain_has_no_tenant(
    monkeypatch: pytest.MonkeyPatch, db_url: str
) -> None:
    monkeypatch.setenv("DATABASE_URL", db_url)
    monkeypatch.setenv("ENVIRONMENT", "test")
    get_settings.cache_clear()
    app = create_app()

    @app.get("/v1/_probe")
    async def _probe() -> dict[str, bool]:
        return {"ok": True}

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://api.gerti.com.br") as ac:
        response = await ac.get("/v1/_probe")
    # sem subdomínio o request segue sem tenant
    assert response.status_code == 200
    assert response.headers.get("x-gerti-tenant") is None


@pytest.mark.asyncio
async def test_request_with_unknown_subdomain_returns_404(
    monkeypatch: pytest.MonkeyPatch, db_url: str, engine
) -> None:
    monkeypatch.setenv("DATABASE_URL", db_url)
    monkeypatch.setenv("ENVIRONMENT", "test")
    get_settings.cache_clear()
    monkeypatch.setattr(
        db, "SessionLocal", async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    )
    app = create_app()

    @app.get("/v1/_probe")
    async def _probe() -> dict[str, bool]:
        return {"ok": True}

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://ghost.suporte.gerti.com.br") as ac:
        response = await ac.get("/v1/_probe")
    assert response.status_code == 404
    body = response.json()
    assert body["detail"]["code"] == "tenant_not_found"
