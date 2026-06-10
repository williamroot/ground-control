"""Router /v1/admin/.../automation-rules — CRUD com validação server-side.

- sem gsid_adm → 401
- tenant inválido/inexistente → 404
- criar com field/op/type fora das allowlists → 422
- criar/listar/editar/toggle/deletar OK
- GET /v1/admin/automation/meta serve os dropdowns
"""

from __future__ import annotations

import uuid

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from gerti_sidecar import db
from gerti_sidecar.auth.admin_session import encode_admin_session
from gerti_sidecar.config import get_settings
from gerti_sidecar.main import create_app
from gerti_sidecar.models import Tenant, ZnunyInstance


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


@pytest.mark.asyncio
async def test_automation_crud(engine, app_session_factory, monkeypatch):
    monkeypatch.setenv("SESSION_SECRET", "test-secret-32-chars-minimum-xxxx")
    monkeypatch.setenv("ENVIRONMENT", "test")
    get_settings.cache_clear()
    admin_factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    monkeypatch.setattr(db, "AdminSessionLocal", admin_factory)
    monkeypatch.setattr(db, "SessionLocal", app_session_factory)

    tid = await _seed_tenant(engine)
    app = create_app()
    st = get_settings()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        base = f"/v1/admin/tenants/{tid}/automation-rules"

        # sem sessão → 401
        assert (await c.get(base)).status_code == 401

        c.cookies.set("gsid_adm", encode_admin_session("william", st))

        # meta serve os dropdowns
        meta = await c.get("/v1/admin/automation/meta")
        assert meta.status_code == 200
        m = meta.json()
        assert "priority" in m["fields"]
        assert "contains" in m["ops"]
        assert "set_priority" in m["actions"]
        assert set(m["trigger_events"]) == {
            "ticket_create",
            "article_create",
            "state_update",
            "escalation",
        }

        # tenant inexistente → 404
        ghost = f"/v1/admin/tenants/{uuid.uuid4()}/automation-rules"
        assert (await c.get(ghost)).status_code == 404

        # criar com trigger inválido → 422
        bad_trigger = await c.post(
            base, json={"name": "x", "trigger_event": "nope", "conditions": [], "actions": []}
        )
        assert bad_trigger.status_code == 422

        # criar com field fora da allowlist → 422
        bad_field = await c.post(
            base,
            json={
                "name": "x",
                "trigger_event": "article_create",
                "conditions": [{"field": "__danger__", "op": "eq", "value": "y"}],
                "actions": [],
            },
        )
        assert bad_field.status_code == 422

        # criar com action fora da allowlist → 422
        bad_action = await c.post(
            base,
            json={
                "name": "x",
                "trigger_event": "article_create",
                "conditions": [],
                "actions": [{"type": "delete_ticket", "params": {}}],
            },
        )
        assert bad_action.status_code == 422

        # criar válida → 201
        created = await c.post(
            base,
            json={
                "name": "urgente",
                "trigger_event": "article_create",
                "conditions": [{"field": "title", "op": "contains", "value": "urgente"}],
                "actions": [{"type": "set_priority", "params": {"priority": "5 very high"}}],
                "position": 0,
            },
        )
        assert created.status_code == 201
        rule_id = created.json()["id"]

        # listar
        lst = await c.get(base)
        assert lst.status_code == 200
        assert len(lst.json()) == 1
        assert lst.json()[0]["name"] == "urgente"

        # editar (PUT)
        upd = await c.put(
            f"{base}/{rule_id}",
            json={
                "name": "urgente-v2",
                "trigger_event": "article_create",
                "conditions": [{"field": "priority", "op": "eq", "value": "3 normal"}],
                "actions": [{"type": "add_note", "params": {"note": "oi"}}],
                "position": 2,
                "enabled": False,
            },
        )
        assert upd.status_code == 200
        assert upd.json()["name"] == "urgente-v2"
        assert upd.json()["enabled"] is False
        assert upd.json()["position"] == 2

        # deletar
        dele = await c.delete(f"{base}/{rule_id}")
        assert dele.status_code == 204
        assert len((await c.get(base)).json()) == 0
