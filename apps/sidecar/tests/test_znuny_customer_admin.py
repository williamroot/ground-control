"""znuny_customer_admin: write-client do webservice GertiAdmin (ADR D19).

Mock de httpx. Para cada função (create_customer_company / create_customer_user
/ set_password):
  • happy path → retorna o id esperado / None, e o POST bate a URL (base+Route),
    o AccessToken e as chaves de corpo do contrato congelado.
  • rejeição limpa (HTTP 4xx OU corpo com `Error`) → ZnunyWriteError.
  • transporte / HTTP 5xx → ZnunyUnavailable.
"""

from __future__ import annotations

import httpx
import pytest

from gerti_sidecar.integrations import znuny_customer_admin as zca

_BASE = "http://znuny/otrs/nph-genericinterface.pl/Webservice/GertiAdmin"
_TOKEN = "tok-admin"


@pytest.fixture(autouse=True)
def _env(monkeypatch):
    monkeypatch.setenv("ZNUNY_ADMIN_WS_URL", _BASE)
    monkeypatch.setenv("ZNUNY_WS_TOKEN", _TOKEN)


class _MockResp:
    def __init__(self, status_code: int, payload):
        self.status_code = status_code
        self._payload = payload

    def json(self):
        if isinstance(self._payload, ValueError):
            raise self._payload
        return self._payload


def _capturing_post(status_code: int, payload):
    captured: dict = {}

    async def post(self, url, **kw):
        captured["url"] = url
        captured["json"] = kw.get("json")
        return _MockResp(status_code, payload)

    return post, captured


# --------------------------------------------------------------------------- #
# create_customer_company
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_create_company_happy(monkeypatch):
    post, captured = _capturing_post(200, {"CustomerID": "acme"})
    monkeypatch.setattr(httpx.AsyncClient, "post", post)

    out = await zca.create_customer_company("acme", "ACME Ltda")

    assert out == "acme"
    assert captured["url"] == _BASE + "/CustomerCompany"
    body = captured["json"]
    assert body["AccessToken"] == _TOKEN
    assert body["CustomerID"] == "acme"
    assert body["CustomerCompanyName"] == "ACME Ltda"
    assert body["ValidID"] == 1


@pytest.mark.asyncio
async def test_create_company_invalid_validid(monkeypatch):
    post, captured = _capturing_post(200, {})
    monkeypatch.setattr(httpx.AsyncClient, "post", post)

    out = await zca.create_customer_company("acme", "ACME", valid=False)

    # GI não ecoou CustomerID → cai no valor de entrada.
    assert out == "acme"
    assert captured["json"]["ValidID"] == 2


@pytest.mark.asyncio
async def test_create_company_error_body_raises_write_error(monkeypatch):
    post, _ = _capturing_post(200, {"Error": {"ErrorMessage": "duplicate"}})
    monkeypatch.setattr(httpx.AsyncClient, "post", post)

    with pytest.raises(zca.ZnunyWriteError, match="duplicate"):
        await zca.create_customer_company("acme", "ACME")


@pytest.mark.asyncio
async def test_create_company_4xx_raises_write_error(monkeypatch):
    post, _ = _capturing_post(400, {"Error": {"ErrorCode": "Validation"}})
    monkeypatch.setattr(httpx.AsyncClient, "post", post)

    with pytest.raises(zca.ZnunyWriteError):
        await zca.create_customer_company("acme", "ACME")


@pytest.mark.asyncio
async def test_create_company_5xx_raises_unavailable(monkeypatch):
    post, _ = _capturing_post(503, {})
    monkeypatch.setattr(httpx.AsyncClient, "post", post)

    with pytest.raises(zca.ZnunyUnavailable):
        await zca.create_customer_company("acme", "ACME")


@pytest.mark.asyncio
async def test_create_company_transport_error_raises_unavailable(monkeypatch):
    async def boom(self, url, **kw):
        raise httpx.ConnectError("down")

    monkeypatch.setattr(httpx.AsyncClient, "post", boom)

    with pytest.raises(zca.ZnunyUnavailable):
        await zca.create_customer_company("acme", "ACME")


# --------------------------------------------------------------------------- #
# create_customer_user
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_create_user_happy(monkeypatch):
    post, captured = _capturing_post(201, {"UserLogin": "joe@acme.com"})
    monkeypatch.setattr(httpx.AsyncClient, "post", post)

    out = await zca.create_customer_user(
        login="joe@acme.com",
        email="joe@acme.com",
        first_name="Joe",
        last_name="Doe",
        customer_id="acme",
    )

    assert out == "joe@acme.com"
    assert captured["url"] == _BASE + "/CustomerUser"
    body = captured["json"]
    assert body["AccessToken"] == _TOKEN
    assert body["UserLogin"] == "joe@acme.com"
    assert body["UserEmail"] == "joe@acme.com"
    assert body["UserFirstname"] == "Joe"
    assert body["UserLastname"] == "Doe"
    assert body["UserCustomerID"] == "acme"
    assert body["ValidID"] == 1


@pytest.mark.asyncio
async def test_create_user_no_echo_falls_back_to_input(monkeypatch):
    post, _ = _capturing_post(200, {})
    monkeypatch.setattr(httpx.AsyncClient, "post", post)

    out = await zca.create_customer_user(
        login="jane@acme.com",
        email="jane@acme.com",
        first_name="Jane",
        last_name="Roe",
        customer_id="acme",
    )

    assert out == "jane@acme.com"


@pytest.mark.asyncio
async def test_create_user_duplicate_raises_write_error(monkeypatch):
    post, _ = _capturing_post(200, {"Error": "login already exists"})
    monkeypatch.setattr(httpx.AsyncClient, "post", post)

    with pytest.raises(zca.ZnunyWriteError, match="already exists"):
        await zca.create_customer_user(
            login="joe@acme.com",
            email="joe@acme.com",
            first_name="Joe",
            last_name="Doe",
            customer_id="acme",
        )


@pytest.mark.asyncio
async def test_create_user_non_json_raises_unavailable(monkeypatch):
    post, _ = _capturing_post(200, ValueError("not json"))
    monkeypatch.setattr(httpx.AsyncClient, "post", post)

    with pytest.raises(zca.ZnunyUnavailable):
        await zca.create_customer_user(
            login="joe@acme.com",
            email="joe@acme.com",
            first_name="Joe",
            last_name="Doe",
            customer_id="acme",
        )


@pytest.mark.asyncio
async def test_create_user_5xx_raises_unavailable(monkeypatch):
    post, _ = _capturing_post(500, {})
    monkeypatch.setattr(httpx.AsyncClient, "post", post)

    with pytest.raises(zca.ZnunyUnavailable):
        await zca.create_customer_user(
            login="joe@acme.com",
            email="joe@acme.com",
            first_name="Joe",
            last_name="Doe",
            customer_id="acme",
        )


# --------------------------------------------------------------------------- #
# set_password
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_set_password_happy(monkeypatch):
    post, captured = _capturing_post(200, {"Success": 1})
    monkeypatch.setattr(httpx.AsyncClient, "post", post)

    out = await zca.set_password("joe@acme.com", "s3cret")

    assert out is None
    assert captured["url"] == _BASE + "/CustomerUser/Password"
    body = captured["json"]
    assert body["AccessToken"] == _TOKEN
    assert body["UserLogin"] == "joe@acme.com"
    assert body["Password"] == "s3cret"


@pytest.mark.asyncio
async def test_set_password_error_raises_write_error(monkeypatch):
    post, _ = _capturing_post(200, {"Error": {"ErrorMessage": "unknown user"}})
    monkeypatch.setattr(httpx.AsyncClient, "post", post)

    with pytest.raises(zca.ZnunyWriteError, match="unknown user"):
        await zca.set_password("ghost@acme.com", "s3cret")


@pytest.mark.asyncio
async def test_set_password_4xx_raises_write_error(monkeypatch):
    post, _ = _capturing_post(422, {})
    monkeypatch.setattr(httpx.AsyncClient, "post", post)

    with pytest.raises(zca.ZnunyWriteError):
        await zca.set_password("joe@acme.com", "bad")


@pytest.mark.asyncio
async def test_set_password_transport_error_raises_unavailable(monkeypatch):
    async def boom(self, url, **kw):
        raise httpx.ReadTimeout("timeout")

    monkeypatch.setattr(httpx.AsyncClient, "post", boom)

    with pytest.raises(zca.ZnunyUnavailable):
        await zca.set_password("joe@acme.com", "s3cret")


@pytest.mark.asyncio
async def test_url_built_with_rstrip(monkeypatch):
    """Base com barra final não gera barra dupla na URL final."""
    monkeypatch.setenv("ZNUNY_ADMIN_WS_URL", _BASE + "/")
    post, captured = _capturing_post(200, {"CustomerID": "acme"})
    monkeypatch.setattr(httpx.AsyncClient, "post", post)

    await zca.create_customer_company("acme", "ACME")

    assert captured["url"] == _BASE + "/CustomerCompany"
