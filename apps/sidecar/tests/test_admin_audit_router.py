"""GET /v1/admin/audit-logs — consulta a trilha de auditoria (Spec #3 V5).

- sem gsid_adm → 401
- criar um contrato grava uma linha de audit_log (instrumentação real)
- filtro por action / tenant_id / q (texto)
- limit > 200 → 422
"""

from __future__ import annotations

import uuid

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from gerti_sidecar import db
from gerti_sidecar.auth.admin_session import encode_admin_session
from gerti_sidecar.config import get_settings
from gerti_sidecar.domain import audit_service
from gerti_sidecar.main import create_app
from gerti_sidecar.models import Tenant, ZnunyInstance

_HOST = {"host": "gerti.was.dev.br"}


def _settings(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("SESSION_SECRET", "test-secret-32-chars-minimum-xxxx")
    monkeypatch.setenv("ENVIRONMENT", "test")
    get_settings.cache_clear()
    return get_settings()


async def _seed_tenant(session, *, subdomain: str = "acme") -> uuid.UUID:
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
    t = Tenant(
        legal_name="Acme SA",
        trade_name="Acme",
        document=subdomain,
        znuny_customer_id=subdomain.upper(),
        znuny_instance_id=inst.id,
        subdomain=subdomain,
    )
    session.add(t)
    await session.commit()
    return t.id


def _wire(monkeypatch, engine, app_session_factory) -> None:
    monkeypatch.setattr(
        db,
        "AdminSessionLocal",
        async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession),
    )
    monkeypatch.setattr(db, "SessionLocal", app_session_factory)


@pytest.mark.asyncio
async def test_list_audit_logs_requires_admin(engine, app_session_factory, session, monkeypatch):
    _settings(monkeypatch)
    _wire(monkeypatch, engine, app_session_factory)
    transport = ASGITransport(app=create_app())
    async with AsyncClient(transport=transport, base_url="http://t") as c:
        r = await c.get("/v1/admin/audit-logs", headers=_HOST)
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_creating_contract_writes_audit_row_and_filters_work(
    engine, app_session_factory, session, monkeypatch
):
    st = _settings(monkeypatch)
    tenant_id = await _seed_tenant(session, subdomain="acme-audit")
    other_tenant_id = await _seed_tenant(session, subdomain="other-audit")
    _wire(monkeypatch, engine, app_session_factory)

    transport = ASGITransport(app=create_app())
    async with AsyncClient(transport=transport, base_url="http://t") as c:
        c.cookies.set("gsid_adm", encode_admin_session("william", st))

        created = await c.post(
            f"/v1/admin/tenants/{tenant_id}/contracts",
            headers=_HOST,
            json={
                "code": "AUD-1",
                "type": "credit_brl",
                "starts_on": "2026-01-01",
                "ends_on": "2026-12-31",
                "initial_amount_brl": 1000,
            },
        )
        assert created.status_code == 201, created.text

        # grava um evento adicional de outro tenant/ação p/ testar filtros.
        await audit_service.record(
            actor_type="system",
            actor_login=None,
            tenant_id=other_tenant_id,
            action="login",
            entity="session",
            description="login de teste",
        )

        lst = await c.get("/v1/admin/audit-logs", headers=_HOST)
        assert lst.status_code == 200
        body = lst.json()
        assert body["total"] >= 2
        descriptions = [i["description"] for i in body["items"]]
        assert any("AUD-1" in d for d in descriptions)

        # filtro por action=create
        by_action = await c.get("/v1/admin/audit-logs", headers=_HOST, params={"action": "create"})
        assert by_action.status_code == 200
        assert all(i["action"] == "create" for i in by_action.json()["items"])

        # filtro por tenant_id
        by_tenant = await c.get(
            "/v1/admin/audit-logs", headers=_HOST, params={"tenant_id": str(tenant_id)}
        )
        assert by_tenant.status_code == 200
        assert all(i["tenant_id"] == str(tenant_id) for i in by_tenant.json()["items"])
        assert len(by_tenant.json()["items"]) >= 1

        # filtro por q (texto no description)
        by_q = await c.get("/v1/admin/audit-logs", headers=_HOST, params={"q": "aud-1"})
        assert by_q.status_code == 200
        assert len(by_q.json()["items"]) >= 1

        # limit > 200 -> 422
        too_big = await c.get("/v1/admin/audit-logs", headers=_HOST, params={"limit": 201})
        assert too_big.status_code == 422
