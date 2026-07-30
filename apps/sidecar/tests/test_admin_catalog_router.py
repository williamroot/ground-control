"""Router /v1/admin/tenants/{id}/catalog/items — console CRUD (Spec #3 V2).

- sem gsid_adm → 401
- tenant inválido/inexistente → 404 tenant_not_found
- criar (201), listar, editar (PUT), icon fora da allowlist → 422
- deletar (204) + 404 no item já deletado
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
async def test_admin_catalog_crud(engine, app_session_factory, monkeypatch):
    monkeypatch.setenv("SESSION_SECRET", "test-secret-32-chars-minimum-xxxx")
    monkeypatch.setenv("ENVIRONMENT", "test")
    get_settings.cache_clear()
    admin_factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    monkeypatch.setattr(db, "AdminSessionLocal", admin_factory)
    monkeypatch.setattr(db, "SessionLocal", app_session_factory)

    tid = await _seed_tenant(engine)
    app = create_app()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        base = f"/v1/admin/tenants/{tid}/catalog/items"

        # sem sessão -> 401
        assert (await c.get(base)).status_code == 401

        c.cookies.set("gsid_adm", encode_admin_session("william", get_settings()))

        # tenant inexistente -> 404
        ghost = f"/v1/admin/tenants/{uuid.uuid4()}/catalog/items"
        assert (await c.get(ghost)).status_code == 404

        # icon fora da allowlist -> 422
        bad_icon = await c.post(
            base,
            json={
                "name": "Reset de senha",
                "category": "acessos",
                "icon": "not-an-icon",
            },
        )
        assert bad_icon.status_code == 422

        # sla_hours fora do range -> 422
        bad_sla = await c.post(
            base,
            json={
                "name": "Reset de senha",
                "category": "acessos",
                "sla_hours": 0,
            },
        )
        assert bad_sla.status_code == 422

        # nome curto demais -> 422
        bad_name = await c.post(base, json={"name": "ab", "category": "acessos"})
        assert bad_name.status_code == 422

        # criar válido -> 201
        created = await c.post(
            base,
            json={
                "name": "Reset de senha",
                "category": "acessos",
                "description": "Solicita redefinição",
                "sla_hours": 4,
                "icon": "lock",
                "znuny_queue": "Suporte::N1",
                "znuny_service": "Acessos",
                "default_priority": "3 normal",
                "active": True,
                "sort_order": 0,
            },
        )
        assert created.status_code == 201
        item = created.json()
        assert item["icon"] == "lock"
        item_id = item["id"]

        # listar
        lst = await c.get(base)
        assert lst.status_code == 200
        assert len(lst.json()) == 1

        # GET detalhe
        detail = await c.get(f"{base}/{item_id}")
        assert detail.status_code == 200
        assert detail.json()["znuny_queue"] == "Suporte::N1"

        # editar (PUT) — desativa e muda nome
        upd = await c.put(
            f"{base}/{item_id}",
            json={
                "name": "Reset de senha (revisado)",
                "category": "acessos",
                "icon": "lock",
                "active": False,
                "sort_order": 3,
            },
        )
        assert upd.status_code == 200
        assert upd.json()["active"] is False
        assert upd.json()["name"] == "Reset de senha (revisado)"

        # editar item inexistente -> 404
        assert (
            await c.put(
                f"{base}/{uuid.uuid4()}",
                json={"name": "Qualquer coisa", "category": "acessos"},
            )
        ).status_code == 404

        # deletar
        dele = await c.delete(f"{base}/{item_id}")
        assert dele.status_code == 204
        assert (await c.get(f"{base}/{item_id}")).status_code == 404

        # deletar de novo -> 404
        assert (await c.delete(f"{base}/{item_id}")).status_code == 404
