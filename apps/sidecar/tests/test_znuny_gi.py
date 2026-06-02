"""znuny_gi.authenticate_customer: True/False/ZnunyUnavailable, mocked HTTP.

Inclui a resolução e-mail→CustomerUserLogin (login sempre por e-mail): um
e-mail é resolvido para o `login` real lendo public.customer_user READ-ONLY;
um valor sem "@" passa direto; um miss (ou erro de DB) cai no valor cru.
"""

from __future__ import annotations

import httpx
import pytest

from gerti_sidecar import db
from gerti_sidecar.integrations import znuny_gi


class _MockResp:
    def __init__(self, status_code: int, payload: dict) -> None:
        self.status_code = status_code
        self._payload = payload

    def json(self) -> dict:
        return self._payload


class _FakeResult:
    """Imita o Result de session.execute(...).first()."""

    def __init__(self, row: tuple | None) -> None:
        self._row = row

    def first(self) -> tuple | None:
        return self._row


class _FakeSession:
    def __init__(self, row: tuple | None) -> None:
        self._row = row
        self.executed: list[tuple] = []

    async def __aenter__(self) -> _FakeSession:
        return self

    async def __aexit__(self, *exc) -> None:
        return None

    async def execute(self, sql, params=None) -> _FakeResult:
        self.executed.append((str(sql), params))
        return _FakeResult(self._row)


def _factory_returning(row: tuple | None):
    """Devolve uma factory (SessionLocal-like) que yielda uma _FakeSession."""

    def factory() -> _FakeSession:
        return _FakeSession(row)

    return factory


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


@pytest.mark.asyncio
async def test_email_resolves_to_real_login(monkeypatch):
    """E-mail informado → resolve `login` real e o usa no SessionCreate."""
    captured: dict = {}

    async def ok_post(self, url, **kw):
        captured["json"] = kw.get("json")
        return _MockResp(200, {"SessionID": "abc"})

    monkeypatch.setattr(znuny_gi, "_resolve_endpoint", lambda: ("http://znuny/ws", "tok"))
    monkeypatch.setattr(httpx.AsyncClient, "post", ok_post)
    # customer_user: email=eduardo.salvi@auroramoveis.com.br → login=eduardo.salvi
    monkeypatch.setattr(db, "SessionLocal", _factory_returning(("eduardo.salvi",)))

    ok = await znuny_gi.authenticate_customer("eduardo.salvi@auroramoveis.com.br", "pw")
    assert ok is True
    assert captured["json"]["CustomerUserLogin"] == "eduardo.salvi"


@pytest.mark.asyncio
async def test_non_email_passes_through_without_db(monkeypatch):
    """Valor sem '@' não toca o DB e vai cru ao SessionCreate."""
    captured: dict = {}

    async def ok_post(self, url, **kw):
        captured["json"] = kw.get("json")
        return _MockResp(200, {"SessionID": "abc"})

    def explode_factory():  # pragma: no cover - não deve ser chamada
        raise AssertionError("DB não deve ser consultado p/ login sem '@'")

    monkeypatch.setattr(znuny_gi, "_resolve_endpoint", lambda: ("http://znuny/ws", "tok"))
    monkeypatch.setattr(httpx.AsyncClient, "post", ok_post)
    monkeypatch.setattr(db, "SessionLocal", explode_factory)

    assert await znuny_gi.authenticate_customer("eduardo.salvi", "pw") is True
    assert captured["json"]["CustomerUserLogin"] == "eduardo.salvi"


@pytest.mark.asyncio
async def test_email_miss_falls_back_to_raw(monkeypatch):
    """Sem linha casando (tenant cujo login JÁ é o e-mail), usa o e-mail cru."""
    captured: dict = {}

    async def ok_post(self, url, **kw):
        captured["json"] = kw.get("json")
        return _MockResp(200, {"SessionID": "abc"})

    monkeypatch.setattr(znuny_gi, "_resolve_endpoint", lambda: ("http://znuny/ws", "tok"))
    monkeypatch.setattr(httpx.AsyncClient, "post", ok_post)
    monkeypatch.setattr(db, "SessionLocal", _factory_returning(None))

    ok = await znuny_gi.authenticate_customer("admin.tech@technova.example", "pw")
    assert ok is True
    assert captured["json"]["CustomerUserLogin"] == "admin.tech@technova.example"


@pytest.mark.asyncio
async def test_db_error_during_resolution_is_failure_safe(monkeypatch):
    """Erro de DB na resolução NÃO derruba o login: cai no valor cru."""
    captured: dict = {}

    async def ok_post(self, url, **kw):
        captured["json"] = kw.get("json")
        return _MockResp(200, {"SessionID": "abc"})

    class _BoomSession:
        async def __aenter__(self):
            raise RuntimeError("db down")

        async def __aexit__(self, *exc):
            return None

    monkeypatch.setattr(znuny_gi, "_resolve_endpoint", lambda: ("http://znuny/ws", "tok"))
    monkeypatch.setattr(httpx.AsyncClient, "post", ok_post)
    monkeypatch.setattr(db, "SessionLocal", lambda: _BoomSession())

    ok = await znuny_gi.authenticate_customer("user@x.com", "pw")
    assert ok is True
    assert captured["json"]["CustomerUserLogin"] == "user@x.com"


@pytest.mark.asyncio
async def test_resolution_no_sessionlocal_falls_back(monkeypatch):
    """SessionLocal não inicializado → fallback p/ valor cru (não crasha)."""
    captured: dict = {}

    async def ok_post(self, url, **kw):
        captured["json"] = kw.get("json")
        return _MockResp(200, {"SessionID": "abc"})

    monkeypatch.setattr(znuny_gi, "_resolve_endpoint", lambda: ("http://znuny/ws", "tok"))
    monkeypatch.setattr(httpx.AsyncClient, "post", ok_post)
    monkeypatch.setattr(db, "SessionLocal", None)

    ok = await znuny_gi.authenticate_customer("user@x.com", "pw")
    assert ok is True
    assert captured["json"]["CustomerUserLogin"] == "user@x.com"
