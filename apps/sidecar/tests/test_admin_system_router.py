"""GET /v1/admin/system/health — saúde do sistema com falha isolada (Spec #3 V6).

- sem gsid_adm → 401
- 200 mesmo com a sonda do Znuny GI falhando (sem endpoint configurado)
- nenhum segredo (token/senha) vaza na resposta
"""

from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from gerti_sidecar import db
from gerti_sidecar.auth.admin_session import encode_admin_session
from gerti_sidecar.config import get_settings
from gerti_sidecar.main import create_app

_HOST = {"host": "gerti.was.dev.br"}


def _settings(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("SESSION_SECRET", "test-secret-32-chars-minimum-xxxx")
    monkeypatch.setenv("ENVIRONMENT", "test")
    # Segredo "sensível" que NUNCA pode aparecer na resposta.
    monkeypatch.setenv("ZNUNY_WS_TOKEN", "top-secret-token-xyz")
    monkeypatch.delenv("ZNUNY_ADMIN_WS_URL", raising=False)
    monkeypatch.delenv("ZNUNY_TICKET_WS_URL", raising=False)
    get_settings.cache_clear()
    return get_settings()


def _wire(monkeypatch, engine, app_session_factory) -> None:
    monkeypatch.setattr(
        db,
        "AdminSessionLocal",
        async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession),
    )
    monkeypatch.setattr(db, "SessionLocal", app_session_factory)


@pytest.mark.asyncio
async def test_health_requires_admin(engine, app_session_factory, monkeypatch):
    _settings(monkeypatch)
    _wire(monkeypatch, engine, app_session_factory)
    transport = ASGITransport(app=create_app())
    async with AsyncClient(transport=transport, base_url="http://t") as c:
        r = await c.get("/v1/admin/system/health", headers=_HOST)
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_health_200_with_isolated_probe_failure_and_no_secret_leak(
    engine, app_session_factory, monkeypatch
):
    st = _settings(monkeypatch)
    _wire(monkeypatch, engine, app_session_factory)
    transport = ASGITransport(app=create_app())
    async with AsyncClient(transport=transport, base_url="http://t") as c:
        c.cookies.set("gsid_adm", encode_admin_session("william", st))
        r = await c.get("/v1/admin/system/health", headers=_HOST)
    assert r.status_code == 200
    body = r.json()

    # db (via AdminSessionLocal wired ao testcontainer) deve responder ok.
    assert body["db"]["ok"] is True
    assert "latency_ms" in body["db"]

    # znuny_gi sem endpoint configurado -> sonda vermelha, mas HTTP 200.
    assert body["znuny_gi"]["ok"] is False

    # ai/asaas desligados por padrão nos testes -> só enabled=False.
    assert body["ai"] == {"enabled": False}
    assert body["asaas"] == {"enabled": False}

    assert body["version"]

    # nenhum segredo (token/senha) aparece na resposta.
    raw = r.text
    assert "top-secret-token-xyz" not in raw
    assert "AccessToken" not in raw
    assert "password" not in raw.lower()
