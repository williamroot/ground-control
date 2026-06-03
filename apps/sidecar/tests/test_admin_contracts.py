"""POST /v1/admin/tenants/{id}/contracts (T1.D): cria contrato p/ tenant via #1C.

Wiring (espelha test_contracts_router.py):
  • db.AdminSessionLocal -> engine admin (BYPASSRLS): lookup de existência;
  • db.SessionLocal -> app_session_factory (papel gerti_sidecar, RLS-subject):
    a escrita do contrato passa por tenant_session_scope sob RLS de verdade.
Sessão admin via cookie gsid_adm (encode_admin_session); host gerti.was.dev.br.
"""

from __future__ import annotations

import uuid

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from gerti_sidecar import db
from gerti_sidecar.auth.admin_session import encode_admin_session
from gerti_sidecar.config import get_settings
from gerti_sidecar.main import create_app
from gerti_sidecar.models import Tenant, ZnunyInstance

_HOST = {"host": "gerti.was.dev.br"}  # casa o bypass admin do TenantMiddleware


def _settings(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("SESSION_SECRET", "test-secret-32-chars-minimum-xxxx")
    monkeypatch.setenv("ENVIRONMENT", "test")
    get_settings.cache_clear()
    return get_settings()


async def _seed_tenant(session: AsyncSession, *, subdomain: str = "acme") -> uuid.UUID:
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
        document="1",
        znuny_customer_id="ACME",
        znuny_instance_id=inst.id,
        subdomain=subdomain,
    )
    session.add(t)
    await session.commit()
    return t.id


def _wire(monkeypatch: pytest.MonkeyPatch, engine, app_session_factory) -> None:
    monkeypatch.setattr(
        db,
        "AdminSessionLocal",
        async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession),
    )
    monkeypatch.setattr(db, "SessionLocal", app_session_factory)


def _base_body(code: str, ctype: str) -> dict:
    body = {
        "code": code,
        "type": ctype,
        "starts_on": "2026-01-01",
        "ends_on": "2026-12-31",
    }
    if ctype == "hour_bank":
        body["initial_hours"] = 100
    elif ctype == "service_count":
        body["initial_service_count"] = 50
    else:  # credit_brl, credit_shared, closed_value, saas_product
        body["initial_amount_brl"] = 10000
    return body


_ALL_TYPES = [
    "credit_brl",
    "credit_shared",
    "hour_bank",
    "service_count",
    "closed_value",
    "saas_product",
]


@pytest.mark.asyncio
@pytest.mark.parametrize("ctype", _ALL_TYPES)
async def test_create_contract_each_type(
    ctype, engine, app_session_factory, session, monkeypatch
) -> None:
    st = _settings(monkeypatch)
    tenant_id = await _seed_tenant(session, subdomain=f"t-{ctype}")
    _wire(monkeypatch, engine, app_session_factory)

    transport = ASGITransport(app=create_app())
    async with AsyncClient(transport=transport, base_url="http://t") as c:
        c.cookies.set("gsid_adm", encode_admin_session("william", st))
        r = await c.post(
            f"/v1/admin/tenants/{tenant_id}/contracts",
            headers=_HOST,
            json=_base_body(f"C-{ctype}", ctype),
        )
    assert r.status_code == 201, r.text
    out = r.json()
    assert out["code"] == f"C-{ctype}"
    assert out["type"] == ctype
    assert out["status"] == "active"  # invariante #1C: default 'active'
    assert uuid.UUID(out["id"])  # id válido gerado

    # Persistência sob o tenant correto (lê via app role + GUC do tenant).
    async with app_session_factory() as s:
        async with s.begin():
            await s.execute(
                text("SELECT set_config('app.current_tenant', :tid, true)"),
                {"tid": str(tenant_id)},
            )
            row = await s.execute(
                text("SELECT tenant_id, status FROM gerti.contract WHERE code = :code"),
                {"code": f"C-{ctype}"},
            )
            persisted = row.one()
    assert persisted[0] == tenant_id
    assert str(persisted[1]) == "active"


@pytest.mark.asyncio
async def test_missing_required_field_for_type_is_4xx(
    engine, app_session_factory, session, monkeypatch
) -> None:
    st = _settings(monkeypatch)
    tenant_id = await _seed_tenant(session, subdomain="missing")
    _wire(monkeypatch, engine, app_session_factory)

    # hour_bank sem initial_hours -> ContractService rejeita -> 400.
    body = {
        "code": "NO-HOURS",
        "type": "hour_bank",
        "starts_on": "2026-01-01",
        "ends_on": "2026-12-31",
    }
    transport = ASGITransport(app=create_app())
    async with AsyncClient(transport=transport, base_url="http://t") as c:
        c.cookies.set("gsid_adm", encode_admin_session("william", st))
        r = await c.post(f"/v1/admin/tenants/{tenant_id}/contracts", headers=_HOST, json=body)
    assert 400 <= r.status_code < 500, r.text


@pytest.mark.asyncio
async def test_nonexistent_tenant_is_404(engine, app_session_factory, session, monkeypatch) -> None:
    st = _settings(monkeypatch)
    await _seed_tenant(session, subdomain="exists")  # algum tenant existe, mas não o alvo
    _wire(monkeypatch, engine, app_session_factory)

    ghost = uuid.uuid4()
    transport = ASGITransport(app=create_app())
    async with AsyncClient(transport=transport, base_url="http://t") as c:
        c.cookies.set("gsid_adm", encode_admin_session("william", st))
        r = await c.post(
            f"/v1/admin/tenants/{ghost}/contracts",
            headers=_HOST,
            json=_base_body("X", "credit_brl"),
        )
    assert r.status_code == 404
    assert r.json()["detail"] == "tenant_not_found"


@pytest.mark.asyncio
async def test_requires_admin_session(engine, app_session_factory, session, monkeypatch) -> None:
    _settings(monkeypatch)
    tenant_id = await _seed_tenant(session, subdomain="auth")
    _wire(monkeypatch, engine, app_session_factory)

    transport = ASGITransport(app=create_app())
    async with AsyncClient(transport=transport, base_url="http://t") as c:
        # sem cookie gsid_adm -> 401 (não chega no corpo)
        r = await c.post(
            f"/v1/admin/tenants/{tenant_id}/contracts",
            headers=_HOST,
            json=_base_body("AUTH", "credit_brl"),
        )
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_duplicate_code_per_tenant_is_4xx(
    engine, app_session_factory, session, monkeypatch
) -> None:
    """Invariante #1C: code único por tenant — segundo idêntico é rejeitado."""
    st = _settings(monkeypatch)
    tenant_id = await _seed_tenant(session, subdomain="dup")
    _wire(monkeypatch, engine, app_session_factory)

    transport = ASGITransport(app=create_app())
    async with AsyncClient(transport=transport, base_url="http://t") as c:
        c.cookies.set("gsid_adm", encode_admin_session("william", st))
        first = await c.post(
            f"/v1/admin/tenants/{tenant_id}/contracts",
            headers=_HOST,
            json=_base_body("DUP-1", "credit_brl"),
        )
        assert first.status_code == 201, first.text
        second = await c.post(
            f"/v1/admin/tenants/{tenant_id}/contracts",
            headers=_HOST,
            json=_base_body("DUP-1", "credit_brl"),
        )
    assert 400 <= second.status_code < 500, second.text
