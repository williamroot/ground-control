"""GET /v1/health retorna 200 com status ok e env."""

import pytest
from httpx import ASGITransport, AsyncClient

from gerti_sidecar.main import create_app


@pytest.mark.asyncio
async def test_health_returns_200(monkeypatch: pytest.MonkeyPatch, db_url: str) -> None:
    monkeypatch.setenv("DATABASE_URL", db_url)
    monkeypatch.setenv("ENVIRONMENT", "test")
    from gerti_sidecar.config import get_settings

    get_settings.cache_clear()
    app = create_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        response = await ac.get("/v1/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["environment"] == "test"
    assert "version" in body
