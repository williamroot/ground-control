"""Router /v1/admin/tenants/{id}/agent-tokens + /devices — console (Spec #1R-a).

- sem gsid_adm → 401
- tenant inexistente → 404
- POST agent-tokens → 201 com token EM CLARO uma vez (+ install_command)
- GET agent-tokens lista (sem plaintext)
- DELETE/disable token
- GET devices lista
- POST devices/{id}/approve (pending→active + CMDB)
- POST devices/{id}/revoke
"""

from __future__ import annotations

import uuid

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from gerti_sidecar import db
from gerti_sidecar.auth.admin_session import encode_admin_session
from gerti_sidecar.config import get_settings
from gerti_sidecar.domain.agent_secrets import hash_token, new_agent_secret
from gerti_sidecar.main import create_app
from gerti_sidecar.models import AgentEnrollToken, DeviceAgent, Tenant, ZnunyInstance


class FakeGI:
    def __init__(self) -> None:
        self.calls: list[dict] = []
        self._n = 300

    async def config_item_upsert(
        self, *, customer_id, name, fingerprint, attributes, config_item_id=None, **kw
    ):
        self.calls.append({"customer_id": customer_id, "config_item_id": config_item_id})
        if config_item_id is not None:
            return config_item_id, "updated"
        self._n += 1
        return self._n, "created"


async def _seed_tenant(engine) -> uuid.UUID:
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
        return t.id


def _wire(monkeypatch, engine, app_session_factory, gi):
    monkeypatch.setenv("SESSION_SECRET", "test-secret-32-chars-minimum-xxxx")
    monkeypatch.setenv("ENVIRONMENT", "test")
    get_settings.cache_clear()
    admin_factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    monkeypatch.setattr(db, "AdminSessionLocal", admin_factory)
    monkeypatch.setattr(db, "SessionLocal", app_session_factory)
    import gerti_sidecar.routers.admin_agents as admin_agents

    monkeypatch.setattr(admin_agents, "gi", gi)


@pytest.mark.asyncio
async def test_token_and_device_crud(engine, app_session_factory, monkeypatch):
    gi = FakeGI()
    _wire(monkeypatch, engine, app_session_factory, gi)
    tid = await _seed_tenant(engine)
    app = create_app()
    st = get_settings()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        tokens = f"/v1/admin/tenants/{tid}/agent-tokens"
        devices = f"/v1/admin/tenants/{tid}/devices"

        # sem sessão → 401
        assert (await c.get(tokens)).status_code == 401

        c.cookies.set("gsid_adm", encode_admin_session("william", st))

        # tenant inexistente → 404
        ghost = f"/v1/admin/tenants/{uuid.uuid4()}/agent-tokens"
        assert (await c.get(ghost)).status_code == 404

        # criar token → 201 com plaintext UMA vez + comando de instalação
        created = await c.post(tokens, json={"label": "matriz", "max_registrations": 5})
        assert created.status_code == 201
        cbody = created.json()
        assert cbody["token"].startswith("gcat_")
        assert "install_command" in cbody and cbody["token"] in cbody["install_command"]
        token_id = cbody["id"]

        # listar tokens — sem plaintext, sem hash
        lst = await c.get(tokens)
        assert lst.status_code == 200
        rows = lst.json()
        assert len(rows) == 1
        assert "token" not in rows[0]
        assert "token_hash" not in rows[0]
        assert rows[0]["label"] == "matriz"
        assert rows[0]["max_registrations"] == 5
        assert rows[0]["enabled"] is True

        # desabilitar token (rotação = criar novo + desabilitar antigo)
        dele = await c.delete(f"{tokens}/{token_id}")
        assert dele.status_code in (200, 204)
        rows = (await c.get(tokens)).json()
        assert rows[0]["enabled"] is False

        # nenhum device ainda
        assert (await c.get(devices)).json() == []


@pytest.mark.asyncio
async def test_device_approve_and_revoke(engine, app_session_factory, monkeypatch):
    gi = FakeGI()
    _wire(monkeypatch, engine, app_session_factory, gi)
    tid = await _seed_tenant(engine)

    # seed um device pending direto na DB (RLS-subject)
    from gerti_sidecar.db import tenant_session_scope

    secret_plain, secret_hash = new_agent_secret()
    async with tenant_session_scope(tid, factory=app_session_factory) as s:
        d = DeviceAgent(
            tenant_id=tid,
            fingerprint="FP-pending",
            agent_secret_hash=secret_hash,
            status="pending",
            hostname="aur-nb-pending",
            os="Ubuntu",
            specs={"cpu": "i5"},
        )
        s.add(d)
        await s.flush()
        device_id = d.id

    app = create_app()
    st = get_settings()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        c.cookies.set("gsid_adm", encode_admin_session("william", st))
        devices = f"/v1/admin/tenants/{tid}/devices"

        lst = await c.get(devices)
        assert lst.status_code == 200
        assert len(lst.json()) == 1
        assert lst.json()[0]["status"] == "pending"
        assert "agent_secret_hash" not in lst.json()[0]

        # aprovar → active + CMDB escrito com customer do tenant
        appr = await c.post(f"{devices}/{device_id}/approve")
        assert appr.status_code == 200
        assert appr.json()["status"] == "active"
        assert appr.json()["znuny_config_item_id"] is not None
    assert gi.calls and gi.calls[0]["customer_id"] == "AURORA"

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        c.cookies.set("gsid_adm", encode_admin_session("william", st))
        devices = f"/v1/admin/tenants/{tid}/devices"
        # revogar
        rev = await c.post(f"{devices}/{device_id}/revoke")
        assert rev.status_code == 200
        assert rev.json()["status"] == "revoked"

    # confirma na DB
    async with tenant_session_scope(tid, factory=app_session_factory) as s:
        dev = (await s.execute(select(DeviceAgent))).scalar_one()
        assert dev.status == "revoked"


@pytest.mark.asyncio
async def test_token_hash_never_exposed(engine, app_session_factory, monkeypatch):
    """Defesa: o plaintext do token criado bate com o hash persistido (e nada mais)."""
    gi = FakeGI()
    _wire(monkeypatch, engine, app_session_factory, gi)
    tid = await _seed_tenant(engine)
    app = create_app()
    st = get_settings()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        c.cookies.set("gsid_adm", encode_admin_session("william", st))
        created = await c.post(f"/v1/admin/tenants/{tid}/agent-tokens", json={"label": "x"})
        plain = created.json()["token"]

    from gerti_sidecar.db import tenant_session_scope

    async with tenant_session_scope(tid, factory=app_session_factory) as s:
        tok = (await s.execute(select(AgentEnrollToken))).scalar_one()
        assert tok.token_hash == hash_token(plain)
        assert tok.token_hash != plain
