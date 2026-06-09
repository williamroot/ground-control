"""Router /v1/admin/timer/* — ciclo completo e guard de autenticação.

Monkeypatch GI (znuny_ticket.time_accounting_add) para não precisar de Znuny real.
Usa testcontainer Postgres via fixtures `engine`/`app_session_factory` do conftest.
"""

from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from gerti_sidecar import db
from gerti_sidecar.auth.admin_session import encode_admin_session
from gerti_sidecar.config import get_settings
from gerti_sidecar.integrations import znuny_ticket
from gerti_sidecar.main import create_app


@pytest.mark.asyncio
async def test_timer_lifecycle_requires_admin(engine, app_session_factory, monkeypatch):
    monkeypatch.setenv("SESSION_SECRET", "test-secret-32-chars-minimum-xxxx")
    monkeypatch.setenv("ENVIRONMENT", "test")
    get_settings.cache_clear()

    async def fake_add(**kw):
        return None

    monkeypatch.setattr(znuny_ticket, "time_accounting_add", fake_add)
    admin_factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    monkeypatch.setattr(db, "AdminSessionLocal", admin_factory)
    monkeypatch.setattr(db, "SessionLocal", app_session_factory)
    app = create_app()
    st = get_settings()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        # sem gsid_adm → 401
        assert (
            await c.post("/v1/admin/timer/start", json={"znuny_ticket_id": 19})
        ).status_code == 401
        c.cookies.set("gsid_adm", encode_admin_session("william", st))
        r = await c.post("/v1/admin/timer/start", json={"znuny_ticket_id": 19})
        assert r.status_code == 201
        tid = r.json()["id"]
        assert (await c.post("/v1/admin/timer/pause", json={"timer_id": tid})).status_code == 200
        assert (await c.post("/v1/admin/timer/resume", json={"timer_id": tid})).status_code == 200
        s = await c.post("/v1/admin/timer/stop", json={"timer_id": tid, "adjust_minutes": 10})
        assert s.status_code == 200
        assert s.json()["status"] == "stopped"
        # active list
        a = await c.get("/v1/admin/timer/active")
        assert a.status_code == 200
