"""Fase 0 (#1G-a) smoke: routers admin registrados, sessão admin gateia, stubs 501.

Não toca o DB: os endpoints `/v1/admin/*` pulam a resolução de tenant
(TenantMiddleware) e `get_admin_session` lê só o cookie. Prova:
  • routers registrados e roteando no host admin `gerti.was.dev.br` (não 404);
  • 401 sem sessão admin / com cookie inválido / com um `gsid` de CLIENTE;
  • 501 (stub) quando a sessão admin é válida → dependency passou.
"""

from __future__ import annotations

import jwt
import pytest
from httpx import ASGITransport, AsyncClient

from gerti_sidecar.auth.admin_session import encode_admin_session
from gerti_sidecar.config import get_settings
from gerti_sidecar.main import create_app

_HOST = {"host": "gerti.was.dev.br"}  # casa <sub>.was.dev.br → exercita o bypass


def _settings(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("SESSION_SECRET", "test-secret-32-chars-minimum-xxxx")
    monkeypatch.setenv("ENVIRONMENT", "test")
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://u:p@localhost/db")
    get_settings.cache_clear()
    return get_settings()


@pytest.mark.asyncio
async def test_admin_endpoints_require_admin_session(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = _settings(monkeypatch)
    transport = ASGITransport(app=create_app())
    async with AsyncClient(transport=transport, base_url="http://t") as c:
        # sem sessão → 401 (não 404: o bypass do admin no TenantMiddleware vale)
        for method, path in [
            ("GET", "/v1/admin/tenants"),
            ("POST", "/v1/admin/tenants/abc/contracts"),
            ("GET", "/v1/admin/tenants/abc"),
        ]:
            r = await c.request(method, path, headers=_HOST, json={})
            assert r.status_code == 401, (method, path, r.status_code)

        # cookie inválido → 401 (cookie via header p/ evitar o cookies= deprecado)
        bad = await c.get("/v1/admin/tenants", headers={**_HOST, "cookie": "gsid_adm=garbage"})
        assert bad.status_code == 401

        # um JWT de CLIENTE (sem typ:admin) NÃO vale como sessão admin → 401
        customer_token = jwt.encode(
            {"tenant_id": "t", "customer_login": "x", "role": "admin", "exp": 9999999999},
            settings.session_secret,
            algorithm="HS256",
        )
        cross = await c.get(
            "/v1/admin/tenants", headers={**_HOST, "cookie": f"gsid_adm={customer_token}"}
        )
        assert cross.status_code == 401

        # sessão admin VÁLIDA → chega no stub (501), provando router + dependency
        token = encode_admin_session("william", settings)
        ok = await c.get("/v1/admin/tenants", headers={**_HOST, "cookie": f"gsid_adm={token}"})
        assert ok.status_code == 501


@pytest.mark.asyncio
async def test_admin_login_route_registered(monkeypatch: pytest.MonkeyPatch) -> None:
    _settings(monkeypatch)
    transport = ASGITransport(app=create_app())
    async with AsyncClient(transport=transport, base_url="http://t") as c:
        # login não exige sessão (é o ponto de entrada) → stub 501, não 404/401
        r = await c.post(
            "/v1/admin/auth/login", headers=_HOST, json={"login": "william", "password": "x"}
        )
        assert r.status_code == 501
