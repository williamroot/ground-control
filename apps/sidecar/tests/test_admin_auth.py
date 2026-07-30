"""T1.A — agent-auth via GI + admin session login/logout (gsid_adm).

Cobre:
  • authenticate_agent: True (SessionID), False (Error/AuthFail/4xx),
    raise ZnunyUnavailable (transporte / 5xx / não-JSON), e o guard de contrato
    (body usa `UserLogin`, nunca `CustomerUserLogin`, e SEM resolução e-mail);
  • router /v1/admin/auth/login: 200 + Set-Cookie gsid_adm (válido), 401
    (inválido), 503 (ZnunyUnavailable); /logout → 204 + cookie limpo;
  • isolamento: um JWT de CLIENTE em gsid_adm é rejeitado (401) e o gsid_adm
    emitido pelo login é aceito por decode_admin_session;
  • #2 — login universal (login OU e-mail): login direto nunca chama
    resolve_agent_login (agente sem e-mail continua entrando por login);
    login por e-mail resolve o canônico e a SESSÃO GUARDA O LOGIN, nunca o
    e-mail (bug perigoso — asserido explicitamente); e-mail ambíguo e e-mail
    inexistente devolvem o MESMO 401 de senha errada; ZnunyUnavailable da
    resolução (classe distinta da do auth direto) também vira 503.
"""

from __future__ import annotations

import httpx
import jwt
import pytest
from httpx import ASGITransport, AsyncClient

from gerti_sidecar.auth.admin_session import decode_admin_session
from gerti_sidecar.config import get_settings
from gerti_sidecar.integrations import znuny_agent_auth
from gerti_sidecar.main import create_app
from gerti_sidecar.routers import admin_auth as admin_auth_router

_HOST = {"host": "gerti.was.dev.br"}  # host admin → bypass do TenantMiddleware


class _MockResp:
    def __init__(self, status_code: int, payload: dict | None) -> None:
        self.status_code = status_code
        self._payload = payload

    def json(self) -> dict:
        if self._payload is None:
            raise ValueError("not json")
        return self._payload


def _settings(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("SESSION_SECRET", "test-secret-32-chars-minimum-xxxx")
    monkeypatch.setenv("ENVIRONMENT", "test")
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://u:p@localhost/db")
    get_settings.cache_clear()
    return get_settings()


# ---------------------------------------------------------------------------
# authenticate_agent (GI)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_authenticate_agent_success(monkeypatch):
    """HTTP 2xx + SessionID → True; body usa UserLogin (não CustomerUserLogin)."""
    monkeypatch.setenv("ZNUNY_WS_URL", "http://znuny/ws")
    monkeypatch.setenv("ZNUNY_WS_TOKEN", "tok")
    captured: dict = {}

    async def ok_post(self, url, **kw):
        captured["url"] = url
        captured["json"] = kw.get("json")
        return _MockResp(200, {"SessionID": "sess-123"})

    monkeypatch.setattr(httpx.AsyncClient, "post", ok_post)
    assert await znuny_agent_auth.authenticate_agent("william", "pw") is True

    body = captured["json"]
    # D19 regression guard: agent-auth usa UserLogin, NUNCA CustomerUserLogin,
    # e SEM resolução e-mail→login (login vai cru).
    assert body["UserLogin"] == "william"
    assert "Password" in body
    assert body["AccessToken"] == "tok"
    assert "CustomerUserLogin" not in body
    assert captured["url"] == "http://znuny/ws"


@pytest.mark.asyncio
async def test_authenticate_agent_no_email_resolution(monkeypatch):
    """Um e-mail é enviado CRU (sem resolução): UserLogin == valor informado."""
    monkeypatch.setenv("ZNUNY_WS_URL", "http://znuny/ws")
    monkeypatch.setenv("ZNUNY_WS_TOKEN", "tok")
    captured: dict = {}

    async def ok_post(self, url, **kw):
        captured["json"] = kw.get("json")
        return _MockResp(200, {"SessionID": "sess-123"})

    monkeypatch.setattr(httpx.AsyncClient, "post", ok_post)
    assert await znuny_agent_auth.authenticate_agent("agent@gerti.com", "pw") is True
    assert captured["json"]["UserLogin"] == "agent@gerti.com"


@pytest.mark.asyncio
async def test_authenticate_agent_authfail_is_false(monkeypatch):
    """body com Error/AuthFail → False (rejeição limpa, não derruba)."""
    monkeypatch.setenv("ZNUNY_WS_URL", "http://znuny/ws")
    monkeypatch.setenv("ZNUNY_WS_TOKEN", "tok")

    async def reject_post(self, url, **kw):
        return _MockResp(200, {"Error": {"ErrorCode": "SessionCreate.AuthFail"}})

    monkeypatch.setattr(httpx.AsyncClient, "post", reject_post)
    assert await znuny_agent_auth.authenticate_agent("william", "bad") is False


@pytest.mark.asyncio
async def test_authenticate_agent_http_4xx_is_false(monkeypatch):
    """HTTP 4xx (sem SessionID) → False."""
    monkeypatch.setenv("ZNUNY_WS_URL", "http://znuny/ws")
    monkeypatch.setenv("ZNUNY_WS_TOKEN", "tok")

    async def four_oh_one(self, url, **kw):
        return _MockResp(401, {"Error": "denied"})

    monkeypatch.setattr(httpx.AsyncClient, "post", four_oh_one)
    assert await znuny_agent_auth.authenticate_agent("william", "bad") is False


@pytest.mark.asyncio
async def test_authenticate_agent_transport_error_raises(monkeypatch):
    """Erro de transporte → ZnunyUnavailable."""
    monkeypatch.setenv("ZNUNY_WS_URL", "http://znuny/ws")
    monkeypatch.setenv("ZNUNY_WS_TOKEN", "tok")

    async def boom_post(self, url, **kw):
        raise httpx.ConnectError("down")

    monkeypatch.setattr(httpx.AsyncClient, "post", boom_post)
    with pytest.raises(znuny_agent_auth.ZnunyUnavailable):
        await znuny_agent_auth.authenticate_agent("william", "pw")


@pytest.mark.asyncio
async def test_authenticate_agent_http_5xx_raises(monkeypatch):
    """HTTP ≥500 → ZnunyUnavailable."""
    monkeypatch.setenv("ZNUNY_WS_URL", "http://znuny/ws")
    monkeypatch.setenv("ZNUNY_WS_TOKEN", "tok")

    async def five_hundred(self, url, **kw):
        return _MockResp(503, None)

    monkeypatch.setattr(httpx.AsyncClient, "post", five_hundred)
    with pytest.raises(znuny_agent_auth.ZnunyUnavailable):
        await znuny_agent_auth.authenticate_agent("william", "pw")


@pytest.mark.asyncio
async def test_authenticate_agent_non_json_raises(monkeypatch):
    """HTTP 2xx mas corpo não-JSON → ZnunyUnavailable."""
    monkeypatch.setenv("ZNUNY_WS_URL", "http://znuny/ws")
    monkeypatch.setenv("ZNUNY_WS_TOKEN", "tok")

    async def garbage(self, url, **kw):
        return _MockResp(200, None)

    monkeypatch.setattr(httpx.AsyncClient, "post", garbage)
    with pytest.raises(znuny_agent_auth.ZnunyUnavailable):
        await znuny_agent_auth.authenticate_agent("william", "pw")


# ---------------------------------------------------------------------------
# router /v1/admin/auth/login|logout
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_admin_login_success_emits_gsid_adm(monkeypatch):
    """Agente válido → 200 + Set-Cookie gsid_adm, aceito por decode_admin_session."""
    settings = _settings(monkeypatch)

    async def good(login, password):
        return True

    monkeypatch.setattr(admin_auth_router, "authenticate_agent", good)
    transport = ASGITransport(app=create_app())
    async with AsyncClient(transport=transport, base_url="http://t") as c:
        r = await c.post(
            "/v1/admin/auth/login",
            headers=_HOST,
            json={"login": "william", "password": "pw"},
        )
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}
    assert "gsid_adm" in r.cookies
    # O gsid_adm emitido é uma sessão admin VÁLIDA (typ:admin + role gerti_staff).
    payload = decode_admin_session(r.cookies["gsid_adm"], settings)
    assert payload is not None
    assert payload["agent_login"] == "william"
    assert payload["typ"] == "admin"
    assert payload["role"] == "gerti_staff"


@pytest.mark.asyncio
async def test_admin_login_invalid_credentials_401(monkeypatch):
    """Agente inválido → 401, sem cookie."""
    _settings(monkeypatch)

    async def bad(login, password):
        return False

    monkeypatch.setattr(admin_auth_router, "authenticate_agent", bad)
    transport = ASGITransport(app=create_app())
    async with AsyncClient(transport=transport, base_url="http://t") as c:
        r = await c.post(
            "/v1/admin/auth/login",
            headers=_HOST,
            json={"login": "william", "password": "bad"},
        )
    assert r.status_code == 401
    assert "gsid_adm" not in r.cookies


@pytest.mark.asyncio
async def test_admin_login_znuny_unavailable_503(monkeypatch):
    """authenticate_agent levanta ZnunyUnavailable → 503."""
    _settings(monkeypatch)

    async def down(login, password):
        raise admin_auth_router.ZnunyUnavailable("down")

    monkeypatch.setattr(admin_auth_router, "authenticate_agent", down)
    transport = ASGITransport(app=create_app())
    async with AsyncClient(transport=transport, base_url="http://t") as c:
        r = await c.post(
            "/v1/admin/auth/login",
            headers=_HOST,
            json={"login": "william", "password": "pw"},
        )
    assert r.status_code == 503
    assert r.json()["detail"] == "znuny_unavailable"


# ---------------------------------------------------------------------------
# #2 — login universal (login OU e-mail)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_admin_login_direct_success_never_calls_resolve(monkeypatch):
    """Sucesso já na primeira tentativa (login normal — inclusive um login que
    por acaso CONTÉM '@', como o agente sem e-mail nenhum 'root@localhost' do
    instalador) NUNCA chama `resolve_agent_login`. Cobre ao mesmo tempo:
    'nenhuma chamada extra ao GI quando o login direto já funciona' e 'agente
    sem e-mail continua entrando por login'."""
    settings = _settings(monkeypatch)

    async def auth(login, password):
        return True

    async def resolve_should_not_run(identifier):
        raise AssertionError(
            "resolve_agent_login não deveria ser chamado — login direto já funcionou"
        )

    monkeypatch.setattr(admin_auth_router, "authenticate_agent", auth)
    monkeypatch.setattr(admin_auth_router, "resolve_agent_login", resolve_should_not_run)
    transport = ASGITransport(app=create_app())
    async with AsyncClient(transport=transport, base_url="http://t") as c:
        r = await c.post(
            "/v1/admin/auth/login",
            headers=_HOST,
            json={"login": "root@localhost", "password": "pw"},
        )
    assert r.status_code == 200
    payload = decode_admin_session(r.cookies["gsid_adm"], settings)
    assert payload is not None
    assert payload["agent_login"] == "root@localhost"


@pytest.mark.asyncio
async def test_admin_login_by_email_success_session_stores_canonical_login(monkeypatch):
    """Login por e-mail: `authenticate_agent` falha com o e-mail cru primeiro,
    `resolve_agent_login` acha o login canônico, `authenticate_agent` tenta de
    novo com ele — e a SESSÃO GUARDA O LOGIN CANÔNICO, nunca o e-mail digitado.
    Este é o bug perigoso da spec: se a sessão guardasse o e-mail, o operador
    entraria e toda operação GI subsequente (que usa `agent_login` como
    `AgentLogin`) quebraria."""
    settings = _settings(monkeypatch)
    attempted_logins: list[str] = []

    async def auth(login, password):
        attempted_logins.append(login)
        return login == "william"  # só autentica com o LOGIN canônico, nunca o e-mail

    async def resolve(identifier):
        assert identifier == "william@gerti.com"
        return "william"

    monkeypatch.setattr(admin_auth_router, "authenticate_agent", auth)
    monkeypatch.setattr(admin_auth_router, "resolve_agent_login", resolve)
    transport = ASGITransport(app=create_app())
    async with AsyncClient(transport=transport, base_url="http://t") as c:
        r = await c.post(
            "/v1/admin/auth/login",
            headers=_HOST,
            json={"login": "william@gerti.com", "password": "pw"},
        )
    assert r.status_code == 200
    assert attempted_logins == ["william@gerti.com", "william"]
    payload = decode_admin_session(r.cookies["gsid_adm"], settings)
    assert payload is not None
    # Guarda checada explicitamente: o claim tem que ser o LOGIN, nunca o e-mail.
    assert payload["agent_login"] == "william"
    assert payload["agent_login"] != "william@gerti.com"


@pytest.mark.asyncio
async def test_admin_login_ambiguous_email_401_identical_to_bad_password(monkeypatch):
    """E-mail que casa mais de um agente válido: `resolve_agent_login` devolve
    `None` (mesmo contrato de 'não encontrado') → 401 `invalid_credentials`,
    idêntico ao de senha errada. Nada de vazar que o e-mail é ambíguo."""
    _settings(monkeypatch)

    async def auth(login, password):
        return False

    async def resolve(identifier):
        return None

    monkeypatch.setattr(admin_auth_router, "authenticate_agent", auth)
    monkeypatch.setattr(admin_auth_router, "resolve_agent_login", resolve)
    transport = ASGITransport(app=create_app())
    async with AsyncClient(transport=transport, base_url="http://t") as c:
        r = await c.post(
            "/v1/admin/auth/login",
            headers=_HOST,
            json={"login": "duplicado@gerti.com", "password": "pw"},
        )
    assert r.status_code == 401
    assert r.json()["detail"] == "invalid_credentials"
    assert "gsid_adm" not in r.cookies


@pytest.mark.asyncio
async def test_admin_login_unknown_email_401_identical_to_bad_password(monkeypatch):
    """E-mail que não casa nenhum agente: mesmo 401 `invalid_credentials` do
    caso de senha errada — sem enumeração de e-mails cadastrados."""
    _settings(monkeypatch)

    async def auth(login, password):
        return False

    async def resolve(identifier):
        return None

    monkeypatch.setattr(admin_auth_router, "authenticate_agent", auth)
    monkeypatch.setattr(admin_auth_router, "resolve_agent_login", resolve)
    transport = ASGITransport(app=create_app())
    async with AsyncClient(transport=transport, base_url="http://t") as c:
        r = await c.post(
            "/v1/admin/auth/login",
            headers=_HOST,
            json={"login": "fantasma@gerti.com", "password": "pw"},
        )
    assert r.status_code == 401
    assert r.json()["detail"] == "invalid_credentials"
    assert "gsid_adm" not in r.cookies


@pytest.mark.asyncio
async def test_admin_login_wrong_password_still_401_same_shape(monkeypatch):
    """Senha errada (login por username, sem e-mail envolvido) — mesmo 401,
    completando a matriz: os três motivos de falha (senha errada, e-mail
    ambíguo, e-mail inexistente) são indistinguíveis no response."""
    _settings(monkeypatch)

    async def auth(login, password):
        return False

    monkeypatch.setattr(admin_auth_router, "authenticate_agent", auth)
    transport = ASGITransport(app=create_app())
    async with AsyncClient(transport=transport, base_url="http://t") as c:
        r = await c.post(
            "/v1/admin/auth/login",
            headers=_HOST,
            json={"login": "william", "password": "bad"},
        )
    assert r.status_code == 401
    assert r.json()["detail"] == "invalid_credentials"


@pytest.mark.asyncio
async def test_admin_login_resolve_znuny_unavailable_503(monkeypatch):
    """`ZnunyUnavailable` levantado pela RESOLUÇÃO por e-mail (não só pelo
    `authenticate_agent` direto) também vira 503 — mesmo contrato
    failure-safe, e ela é uma classe de exceção DIFERENTE da usada pelo
    auth direto (módulos diferentes), então o router precisa capturar as
    duas."""
    _settings(monkeypatch)

    async def auth(login, password):
        return False

    async def resolve_down(identifier):
        raise admin_auth_router.ResolveUnavailable("down")

    monkeypatch.setattr(admin_auth_router, "authenticate_agent", auth)
    monkeypatch.setattr(admin_auth_router, "resolve_agent_login", resolve_down)
    transport = ASGITransport(app=create_app())
    async with AsyncClient(transport=transport, base_url="http://t") as c:
        r = await c.post(
            "/v1/admin/auth/login",
            headers=_HOST,
            json={"login": "william@gerti.com", "password": "pw"},
        )
    assert r.status_code == 503
    assert r.json()["detail"] == "znuny_unavailable"


@pytest.mark.asyncio
async def test_admin_logout_clears_cookie(monkeypatch):
    """logout → 204 + Set-Cookie que expira o gsid_adm."""
    _settings(monkeypatch)
    transport = ASGITransport(app=create_app())
    async with AsyncClient(transport=transport, base_url="http://t") as c:
        r = await c.post("/v1/admin/auth/logout", headers=_HOST)
    assert r.status_code == 204
    set_cookie = r.headers.get("set-cookie", "")
    assert "gsid_adm=" in set_cookie


# ---------------------------------------------------------------------------
# isolamento cliente ↔ admin
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_customer_jwt_rejected_as_admin_session(monkeypatch):
    """Um gsid de CLIENTE (sem typ:admin) em gsid_adm → 401 em rota admin."""
    settings = _settings(monkeypatch)
    customer_token = jwt.encode(
        {"tenant_id": "t", "customer_login": "x", "role": "admin", "exp": 9999999999},
        settings.session_secret,
        algorithm="HS256",
    )
    # decode_admin_session deve recusar (fail-closed por typ/role).
    assert decode_admin_session(customer_token, settings) is None

    transport = ASGITransport(app=create_app())
    async with AsyncClient(transport=transport, base_url="http://t") as c:
        r = await c.get(
            "/v1/admin/tenants",
            headers={**_HOST, "cookie": f"gsid_adm={customer_token}"},
        )
    assert r.status_code == 401
