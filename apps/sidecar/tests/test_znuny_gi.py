"""znuny_gi.authenticate_customer: True/False/ZnunyUnavailable, mocked HTTP."""

from __future__ import annotations

import httpx
import pytest

from gerti_sidecar.integrations import znuny_gi


class _MockResp:
    def __init__(self, status_code: int, payload: dict) -> None:
        self.status_code = status_code
        self._payload = payload

    def json(self) -> dict:
        return self._payload


@pytest.mark.asyncio
async def test_authenticate_customer_paths(monkeypatch):
    captured: dict = {}

    async def ok_post(self, url, **kw):
        captured["json"] = kw.get("json")
        return _MockResp(200, {"SessionID": "abc"})

    async def reject_post(self, url, **kw):
        return _MockResp(200, {"Error": {"ErrorCode": "AuthFail"}})

    async def boom_post(self, url, **kw):
        raise httpx.ConnectError("down")

    monkeypatch.setattr(znuny_gi, "_resolve_endpoint", lambda: ("http://znuny/ws", "tok"))

    monkeypatch.setattr(httpx.AsyncClient, "post", ok_post)
    assert await znuny_gi.authenticate_customer("joe", "pw") is True

    # D14 regression guard: the customer-login body MUST use CustomerUserLogin
    # (Kernel::System::CustomerAuth) — never UserLogin (agent auth).
    body = captured["json"]
    assert body["CustomerUserLogin"] == "joe"
    assert "Password" in body
    assert "UserLogin" not in body

    monkeypatch.setattr(httpx.AsyncClient, "post", reject_post)
    assert await znuny_gi.authenticate_customer("joe", "bad") is False

    monkeypatch.setattr(httpx.AsyncClient, "post", boom_post)
    with pytest.raises(znuny_gi.ZnunyUnavailable):
        await znuny_gi.authenticate_customer("joe", "pw")
