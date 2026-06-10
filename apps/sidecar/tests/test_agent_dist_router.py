"""Distribuição do agente de inventário (Spec #1R-b) — /v1/agent/install.sh + download.

Rotas PÚBLICAS (sem auth; só servem o script e o binário — o token vem por flag):
- GET /v1/agent/install.sh?server=<url> → shell script com `--server=<url>` embutido.
- GET /v1/agent/download/{os_arch}     → serve o binário do diretório de dist;
  os-arch inválido (path traversal / desconhecido / binário ausente) → 404.

Não dependem de DB (router estático/template) — usam só o ASGI client + monkeypatch
do diretório de dist.
"""

from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

from gerti_sidecar.config import get_settings
from gerti_sidecar.main import create_app


def _client(app):
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver")


@pytest.mark.asyncio
async def test_install_script_embeds_server(monkeypatch):
    monkeypatch.setenv("ENVIRONMENT", "test")
    get_settings.cache_clear()
    app = create_app()
    async with _client(app) as ac:
        r = await ac.get("/v1/agent/install.sh", params={"server": "https://x.example.com"})
    assert r.status_code == 200
    body = r.text
    assert body.startswith("#!/bin/sh")
    # O server escolhido aparece como flag default no script renderizado.
    assert "--server=https://x.example.com" in body
    # Content-Type shell-ish.
    assert (
        "text/x-shellscript" in r.headers["content-type"]
        or "text/plain" in r.headers["content-type"]
    )


@pytest.mark.asyncio
async def test_install_script_default_server_from_settings(monkeypatch):
    monkeypatch.setenv("ENVIRONMENT", "test")
    monkeypatch.setenv("AGENT_SERVER_URL", "https://api-default.example.com")
    get_settings.cache_clear()
    app = create_app()
    async with _client(app) as ac:
        r = await ac.get("/v1/agent/install.sh")
    assert r.status_code == 200
    assert "--server=https://api-default.example.com" in r.text


@pytest.mark.asyncio
async def test_install_script_rejects_bad_server(monkeypatch):
    monkeypatch.setenv("ENVIRONMENT", "test")
    get_settings.cache_clear()
    app = create_app()
    async with _client(app) as ac:
        r = await ac.get("/v1/agent/install.sh", params={"server": "not a url; rm -rf /"})
    # Server inválido (não-http) → 400, nunca injeta no script.
    assert r.status_code == 400


@pytest.mark.asyncio
async def test_download_invalid_os_arch_404(monkeypatch):
    monkeypatch.setenv("ENVIRONMENT", "test")
    get_settings.cache_clear()
    app = create_app()
    async with _client(app) as ac:
        r = await ac.get("/v1/agent/download/bad")
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_download_path_traversal_404(monkeypatch):
    monkeypatch.setenv("ENVIRONMENT", "test")
    get_settings.cache_clear()
    app = create_app()
    async with _client(app) as ac:
        # Mesmo URL-encoded, o os_arch só aceita o padrão <os>-<arch>.
        r = await ac.get("/v1/agent/download/..%2f..%2fetc%2fpasswd")
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_download_missing_binary_404(monkeypatch, tmp_path):
    monkeypatch.setenv("ENVIRONMENT", "test")
    # Diretório de dist existe mas não tem o binário pedido → 404 (em dev).
    monkeypatch.setenv("AGENT_DIST_DIR", str(tmp_path))
    get_settings.cache_clear()
    app = create_app()
    async with _client(app) as ac:
        r = await ac.get("/v1/agent/download/linux-amd64")
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_download_serves_binary(monkeypatch, tmp_path):
    monkeypatch.setenv("ENVIRONMENT", "test")
    monkeypatch.setenv("AGENT_DIST_DIR", str(tmp_path))
    (tmp_path / "linux-amd64").write_bytes(b"\x7fELF-fake-binary")
    get_settings.cache_clear()
    app = create_app()
    async with _client(app) as ac:
        r = await ac.get("/v1/agent/download/linux-amd64")
    assert r.status_code == 200
    assert r.content == b"\x7fELF-fake-binary"
    assert r.headers["content-type"] == "application/octet-stream"


@pytest.mark.asyncio
async def test_download_windows_exe(monkeypatch, tmp_path):
    monkeypatch.setenv("ENVIRONMENT", "test")
    monkeypatch.setenv("AGENT_DIST_DIR", str(tmp_path))
    (tmp_path / "windows-amd64.exe").write_bytes(b"MZ-fake")
    get_settings.cache_clear()
    app = create_app()
    async with _client(app) as ac:
        r = await ac.get("/v1/agent/download/windows-amd64")
    assert r.status_code == 200
    assert r.content == b"MZ-fake"
