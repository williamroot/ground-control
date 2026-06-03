"""E2E (#1G-a): onboarding pelo Console de Administração → o novo admin
loga no PORTAL e enxerga o contrato criado, com isolamento admin x cliente.

Caminho exercido (Znuny mockado — a prova viva contra o Znuny real é a
verificação de deploy da Fase 2):
  1. agente loga no admin (gsid_adm via /v1/admin/auth/login);
  2. onboarding de "Acme": POST /v1/admin/tenants cria CustomerCompany/User
     (GI mockado) + gerti.tenant + tenant_branding + portal_user_role(admin);
  3. POST /v1/admin/tenants/{id}/contracts cria 1 contrato hour_bank;
  4. o novo admin loga no PORTAL (gsid) no subdomínio do tenant e
     GET /v1/contracts mostra o contrato criado;
  5. isolamento BIDIRECIONAL: gsid_adm NÃO acessa /v1/contracts; um gsid de
     cliente NÃO acessa /v1/admin/* (claim typ:admin ausente).
"""

from __future__ import annotations

import datetime as dt

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from gerti_sidecar import db
from gerti_sidecar.config import get_settings
from gerti_sidecar.integrations import znuny_customer_admin
from gerti_sidecar.main import create_app
from gerti_sidecar.models import ZnunyInstance
from gerti_sidecar.routers import admin_auth as admin_auth_router
from gerti_sidecar.routers import auth as auth_router


@pytest.mark.asyncio
async def test_admin_onboarding_to_portal_contract_visibility(
    engine, app_session_factory, session, monkeypatch
):
    monkeypatch.setenv("SESSION_SECRET", "test-secret-32-chars-minimum-xxxx")
    monkeypatch.setenv("ENVIRONMENT", "test")
    get_settings.cache_clear()

    # §2.1: exatamente 1 Znuny. Onboarding resolve a única instância.
    inst = ZnunyInstance(
        name="main",
        base_url="http://znuny",
        db_dsn_secret_ref="x",
        webservice_token_secret_ref="x",
        webhook_signing_secret_ref="x",
        mode="pool",
    )
    session.add(inst)
    await session.commit()

    # Resolução subdomínio->tenant + escrita de onboarding = BYPASSRLS (D16);
    # dado de tenant = RLS-subject (gerti_sidecar).
    monkeypatch.setattr(
        db,
        "AdminSessionLocal",
        async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession),
    )
    monkeypatch.setattr(db, "SessionLocal", app_session_factory)

    # Znuny mockado: agent-auth e o write-client GI (CustomerCompany/User/senha).
    async def agent_ok(login: str, password: str) -> bool:
        return True

    async def customer_ok(login: str, password: str) -> bool:
        return True

    async def co_add(customer_id: str, company_name: str, *, valid: bool = True) -> str:
        return customer_id

    async def user_add(*, login, email, first_name, last_name, customer_id, valid=True) -> str:
        return login

    async def set_pw(login: str, password: str) -> None:
        return None

    monkeypatch.setattr(admin_auth_router, "authenticate_agent", agent_ok)
    monkeypatch.setattr(auth_router, "authenticate_customer", customer_ok)
    monkeypatch.setattr(znuny_customer_admin, "create_customer_company", co_add)
    monkeypatch.setattr(znuny_customer_admin, "create_customer_user", user_add)
    monkeypatch.setattr(znuny_customer_admin, "set_password", set_pw)

    app = create_app()
    h_adm = {"host": "gerti.was.dev.br"}  # console (cross-tenant, sem subdomínio)
    h_acme = {"host": "acme.suporte.gerti.com.br"}  # portal do tenant Acme

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://t") as c:
        # (1) agente loga no admin → gsid_adm.
        la = await c.post(
            "/v1/admin/auth/login", headers=h_adm, json={"login": "william", "password": "x"}
        )
        assert la.status_code == 200, la.text
        assert c.cookies.get("gsid_adm") is not None

        # (2) onboarding de "Acme".
        body = {
            "legal_name": "Acme Indústria S.A.",
            "trade_name": "Acme",
            "document": "12.345.678/0001-99",
            "subdomain": "acme",
            "znuny_customer_id": "ACME",
            "branding": {"display_name": "Acme", "primary_color": "#16A34A"},
            "users": [
                {
                    "email": "admin@acme.example",
                    "first_name": "Ana",
                    "last_name": "Admin",
                    "password": "Acme@Demo2026",
                    "role": "admin",
                }
            ],
        }
        ob = await c.post("/v1/admin/tenants", headers=h_adm, json=body)
        assert ob.status_code == 201, ob.text
        tenant_id = ob.json()["tenant"]["id"]
        assert ob.json()["subdomain_to_register"] == "acme"
        assert "admin@acme.example" in ob.json()["created_users"]

        # (3) cria 1 contrato hour_bank para o tenant Acme.
        contract = {
            "code": "ACME-HORAS-2026",
            "type": "hour_bank",
            "starts_on": str(dt.date(2026, 1, 1)),
            "ends_on": str(dt.date(2026, 12, 31)),
            "initial_hours": 100,
        }
        cr = await c.post(f"/v1/admin/tenants/{tenant_id}/contracts", headers=h_adm, json=contract)
        assert cr.status_code == 201, cr.text
        assert cr.json()["code"] == "ACME-HORAS-2026"

        # (4-iso) gsid_adm NÃO é sessão de cliente: /v1/contracts → 401.
        leak = await c.get("/v1/contracts", headers=h_acme)
        assert leak.status_code == 401

        gsid_adm_value = c.cookies.get("gsid_adm")

        # (5) o NOVO admin loga no PORTAL do tenant Acme → gsid.
        c.cookies.clear()
        lp = await c.post(
            "/v1/auth/login",
            headers=h_acme,
            json={"username": "admin@acme.example", "password": "pw"},
        )
        assert lp.status_code == 200, lp.text
        gsid_value = c.cookies.get("gsid")
        assert gsid_value is not None

        # (6) o admin do cliente ENXERGA o contrato criado pelo console.
        cs = await c.get("/v1/contracts", headers=h_acme)
        assert cs.status_code == 200, cs.text
        codes = [x["code"] for x in cs.json()]
        assert "ACME-HORAS-2026" in codes
        assert len(cs.json()) == 1

        # (7) isolamento reverso: um gsid de CLIENTE não vale em /v1/admin/*.
        c.cookies.clear()
        c.cookies.set("gsid_adm", gsid_value)  # cookie de cliente no slot admin
        adm_leak = await c.get("/v1/admin/tenants", headers=h_adm)
        assert adm_leak.status_code == 401

        # ...e o gsid_adm do console não é aceito como gsid de cliente.
        c.cookies.clear()
        c.cookies.set("gsid", gsid_adm_value)
        cli_leak = await c.get("/v1/contracts", headers=h_acme)
        assert cli_leak.status_code == 401
