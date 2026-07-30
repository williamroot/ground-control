"""Portal /v1/me/preferences — Spec #3 V3.

GET cria com defaults na primeira leitura (upsert idempotente); PUT aceita
corpo parcial; theme fora do enum -> 422.
"""

from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from gerti_sidecar import db
from gerti_sidecar.auth.session import encode_session
from gerti_sidecar.config import get_settings
from gerti_sidecar.main import create_app
from gerti_sidecar.models import Tenant, ZnunyInstance

AURORA_HOST = {"host": "aurora.suporte.gerti.com.br"}


async def _seed_tenant(session):
    inst = ZnunyInstance(
        name="i",
        base_url="http://z",
        db_dsn_secret_ref="x",
        webservice_token_secret_ref="x",
        webhook_signing_secret_ref="x",
        mode="pool",
    )
    session.add(inst)
    await session.flush()
    a = Tenant(
        legal_name="Aurora",
        trade_name="Aurora",
        document="1",
        znuny_customer_id="AURORA",
        znuny_instance_id=inst.id,
        subdomain="aurora",
    )
    session.add(a)
    await session.commit()
    return a.id


@pytest.fixture
def _app(engine, app_session_factory, monkeypatch):
    monkeypatch.setenv("SESSION_SECRET", "test-secret-32-chars-minimum-xxxx")
    monkeypatch.setenv("ENVIRONMENT", "test")
    get_settings.cache_clear()
    monkeypatch.setattr(
        db,
        "AdminSessionLocal",
        async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession),
    )
    monkeypatch.setattr(db, "SessionLocal", app_session_factory)
    return create_app()


@pytest.mark.asyncio
async def test_no_cookie_401(_app, session):
    # tenant precisa existir p/ o TenantMiddleware resolver o subdomínio antes
    # da dependency de sessão (senão 404 de tenant desconhecido mascara o 401).
    await _seed_tenant(session)
    async with AsyncClient(transport=ASGITransport(app=_app), base_url="http://t") as c:
        assert (await c.get("/v1/me/preferences", headers=AURORA_HOST)).status_code == 401


@pytest.mark.asyncio
async def test_get_creates_defaults_then_put_updates_and_422_on_bad_theme(_app, session):
    a_id = await _seed_tenant(session)
    st = get_settings()

    async with AsyncClient(transport=ASGITransport(app=_app), base_url="http://t") as c:
        c.cookies.set("gsid", encode_session(str(a_id), "joe@aurora", "helpdesk", st))

        # GET cria com defaults
        resp = await c.get("/v1/me/preferences", headers=AURORA_HOST)
        assert resp.status_code == 200
        body = resp.json()
        assert body["theme"] == "system"
        assert body["email_notifications"] is True
        assert body["weekly_report"] is False

        # segunda leitura é idempotente (mesmos valores, não duplica)
        resp2 = await c.get("/v1/me/preferences", headers=AURORA_HOST)
        assert resp2.status_code == 200
        assert resp2.json() == body

        # PUT parcial
        resp3 = await c.put(
            "/v1/me/preferences",
            json={"theme": "dark", "weekly_report": True},
            headers=AURORA_HOST,
        )
        assert resp3.status_code == 200
        updated = resp3.json()
        assert updated["theme"] == "dark"
        assert updated["weekly_report"] is True
        assert updated["email_notifications"] is True  # não enviado, preserva

        # 422: theme fora do enum
        resp4 = await c.put("/v1/me/preferences", json={"theme": "rainbow"}, headers=AURORA_HOST)
        assert resp4.status_code == 422
