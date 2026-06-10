"""Router público /v1/agent/* (Spec #1R-a) — Bearer token/secret, fora do middleware.

- POST /v1/agent/enroll Bearer token válido → 201 {agent_id, agent_secret, status:active}
- sobre o limite → 202 status pending (sem CMDB)
- token ruim → 401
- POST /v1/agent/heartbeat Bearer agent_secret → 200; revogado → 401
- resolve sem subdomínio (allowlist do TenantMiddleware) — base_url sem tenant.
"""

from __future__ import annotations

import uuid

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from gerti_sidecar import db
from gerti_sidecar.config import get_settings
from gerti_sidecar.domain.agent_secrets import hash_token
from gerti_sidecar.main import create_app
from gerti_sidecar.models import AgentEnrollToken, Tenant, ZnunyInstance


class FakeGI:
    def __init__(self) -> None:
        self.calls: list[dict] = []
        self._n = 200

    async def config_item_upsert(
        self, *, customer_id, name, fingerprint, attributes, config_item_id=None, **kw
    ):
        self.calls.append({"customer_id": customer_id, "config_item_id": config_item_id})
        if config_item_id is not None:
            return config_item_id, "updated"
        self._n += 1
        return self._n, "created"


async def _seed_tenant_token(
    engine, app_session_factory, *, plain="gcat_x", max_registrations=None
) -> tuple[uuid.UUID, str]:
    admin = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    async with admin() as s:
        inst = ZnunyInstance(
            name="main",
            base_url="http://znuny",
            db_dsn_secret_ref="x",
            webservice_token_secret_ref="x",
            webhook_signing_secret_ref="x",
            mode="pool",
        )
        s.add(inst)
        await s.flush()
        t = Tenant(
            legal_name="Aurora SA",
            trade_name="Aurora",
            document="1",
            znuny_customer_id="AURORA",
            znuny_instance_id=inst.id,
            subdomain="aurora",
        )
        s.add(t)
        await s.commit()
        tid = t.id
    async with app_session_factory() as s:
        async with s.begin():
            await s.execute(
                text("SELECT set_config('app.current_tenant', :t, true)"), {"t": str(tid)}
            )
            s.add(
                AgentEnrollToken(
                    tenant_id=tid,
                    token_hash=hash_token(plain),
                    label="install",
                    max_registrations=max_registrations,
                )
            )
    return tid, plain


def _wire(monkeypatch, engine, app_session_factory, gi) -> None:
    monkeypatch.setenv("SESSION_SECRET", "test-secret-32-chars-minimum-xxxx")
    monkeypatch.setenv("ENVIRONMENT", "test")
    get_settings.cache_clear()
    admin_factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    monkeypatch.setattr(db, "AdminSessionLocal", admin_factory)
    monkeypatch.setattr(db, "SessionLocal", app_session_factory)
    # injeta o GI fake no módulo do router
    import gerti_sidecar.routers.agent as agent_router

    monkeypatch.setattr(agent_router, "gi", gi)


@pytest.mark.asyncio
async def test_enroll_then_heartbeat(engine, app_session_factory, monkeypatch):
    gi = FakeGI()
    _wire(monkeypatch, engine, app_session_factory, gi)
    tid, plain = await _seed_tenant_token(engine, app_session_factory)
    app = create_app()
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://api-dev.was.dev.br"
    ) as c:
        # token ruim → 401
        bad = await c.post(
            "/v1/agent/enroll",
            headers={"Authorization": "Bearer gcat_nope"},
            json={"fingerprint": "FP1", "hostname": "h", "os": "x", "specs": {}},
        )
        assert bad.status_code == 401

        # enroll válido → 201 active
        r = await c.post(
            "/v1/agent/enroll",
            headers={"Authorization": f"Bearer {plain}"},
            json={
                "fingerprint": "FP1",
                "hostname": "aur-nb",
                "os": "Ubuntu",
                "specs": {"cpu": "i5"},
            },
        )
        assert r.status_code == 201
        body = r.json()
        assert body["status"] == "active"
        assert body["agent_secret"].startswith("gca_")
        assert body["agent_id"]
        secret = body["agent_secret"]
    assert gi.calls and gi.calls[0]["customer_id"] == "AURORA"

    # heartbeat 200
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://api-dev.was.dev.br"
    ) as c:
        hb = await c.post(
            "/v1/agent/heartbeat",
            headers={"Authorization": f"Bearer {secret}"},
            json={"specs": {"cpu": "i9"}},
        )
        assert hb.status_code == 200
        assert hb.json()["status"] == "active"

        # secret desconhecido → 401
        bad_hb = await c.post(
            "/v1/agent/heartbeat",
            headers={"Authorization": "Bearer gca_nope"},
            json={"specs": {}},
        )
        assert bad_hb.status_code == 401


@pytest.mark.asyncio
async def test_enroll_over_limit_pending_202(engine, app_session_factory, monkeypatch):
    gi = FakeGI()
    _wire(monkeypatch, engine, app_session_factory, gi)
    tid, plain = await _seed_tenant_token(engine, app_session_factory, max_registrations=0)
    app = create_app()
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://api-dev.was.dev.br"
    ) as c:
        r = await c.post(
            "/v1/agent/enroll",
            headers={"Authorization": f"Bearer {plain}"},
            json={"fingerprint": "FP1", "hostname": "h", "os": "x", "specs": {}},
        )
        assert r.status_code == 202
        assert r.json()["status"] == "pending"
    assert gi.calls == []  # pending não escreve no CMDB


@pytest.mark.asyncio
async def test_heartbeat_revoked_401(engine, app_session_factory, monkeypatch):
    gi = FakeGI()
    _wire(monkeypatch, engine, app_session_factory, gi)
    tid, plain = await _seed_tenant_token(engine, app_session_factory)
    app = create_app()
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://api-dev.was.dev.br"
    ) as c:
        r = await c.post(
            "/v1/agent/enroll",
            headers={"Authorization": f"Bearer {plain}"},
            json={"fingerprint": "FP1", "hostname": "h", "os": "x", "specs": {}},
        )
        secret = r.json()["agent_secret"]
    # revoga direto na DB
    from gerti_sidecar.db import tenant_session_scope
    from gerti_sidecar.models import DeviceAgent

    async with tenant_session_scope(tid, factory=app_session_factory) as s:
        dev = (await s.execute(select(DeviceAgent))).scalar_one()
        dev.status = "revoked"
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://api-dev.was.dev.br"
    ) as c:
        hb = await c.post(
            "/v1/agent/heartbeat",
            headers={"Authorization": f"Bearer {secret}"},
            json={"specs": {}},
        )
        assert hb.status_code == 401


@pytest.mark.asyncio
async def test_enroll_missing_bearer_401(engine, app_session_factory, monkeypatch):
    gi = FakeGI()
    _wire(monkeypatch, engine, app_session_factory, gi)
    await _seed_tenant_token(engine, app_session_factory)
    app = create_app()
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://api-dev.was.dev.br"
    ) as c:
        r = await c.post(
            "/v1/agent/enroll",
            json={"fingerprint": "FP1", "hostname": "h", "os": "x", "specs": {}},
        )
        assert r.status_code == 401
