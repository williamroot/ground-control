"""V-R8.1..8.6 — importação em lote por CSV (R8).

Contexto que dá o tamanho: a migração do TIFLUX são **60 clientes e 43
contratos**. Sem carga em lote, isso é um a um, à mão.

Os três comportamentos que os testes protegem, e por quê:

1. **Simular não pode gravar.** O teste conta as chamadas ao Znuny e exige
   zero. Importar 60 clientes e descobrir no 47º que a coluna estava trocada é
   o erro que a simulação existe para evitar — e uma simulação que grava não é
   simulação.
2. **Erro numa linha não derruba as outras.** É o que permite consertar a
   planilha em vez de recomeçar.
3. **Senha não trafega em planilha.** Coluna `password` no arquivo é recusa,
   com explicação — senha em CSV fica no disco de quem exportou, no anexo do
   e-mail e no histórico do navegador.
"""

from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from gerti_sidecar import db
from gerti_sidecar.auth.admin_session import encode_admin_session
from gerti_sidecar.config import get_settings
from gerti_sidecar.main import create_app
from gerti_sidecar.models import PortalUserRole, Tenant, ZnunyInstance
from tests.test_admin_tenants import _GISpy

_HOST = {"host": "gerti.was.dev.br"}

_HEADER = "legal_name,trade_name,document,subdomain,znuny_customer_id,address_city"
_THREE = "\n".join(
    [
        _HEADER,
        "Alfa LTDA,Alfa,1,alfa,ALFA,Belo Horizonte",
        "Beta LTDA,Beta,2,beta,BETA,São Paulo",
        "Gama LTDA,Gama,3,gama,GAMA,Curitiba",
    ]
)


def _settings(monkeypatch):
    monkeypatch.setenv("SESSION_SECRET", "test-secret-32-chars-minimum-xxxx")
    monkeypatch.setenv("ENVIRONMENT", "test")
    get_settings.cache_clear()
    return get_settings()


async def _seed_instance(session: AsyncSession) -> None:
    session.add(
        ZnunyInstance(
            name="main",
            base_url="http://znuny",
            db_dsn_secret_ref="x",
            webservice_token_secret_ref="x",
            webhook_signing_secret_ref="x",
            mode="pool",
        )
    )
    await session.commit()


def _client(app):
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://t")


async def _setup(engine, session, monkeypatch):
    settings = _settings(monkeypatch)
    await _seed_instance(session)
    factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    monkeypatch.setattr(db, "AdminSessionLocal", factory)
    monkeypatch.setattr(db, "SessionLocal", factory)
    spy = _GISpy()
    spy.install(monkeypatch)
    return settings, spy, create_app()


def _csv(content: str):
    return {"file": ("clientes.csv", content.encode("utf-8"), "text/csv")}


# ── simulação ───────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_validate_reports_without_writing_anything(engine, session, monkeypatch):
    """V-R8.1 — 3 linhas válidas, zero escrita. A asserção do 'zero' é o teste."""
    settings, spy, app = await _setup(engine, session, monkeypatch)
    async with _client(app) as c:
        c.cookies.set("gsid_adm", encode_admin_session("william", settings))
        r = await c.post("/v1/admin/import/tenants/validate", headers=_HOST, files=_csv(_THREE))
    assert r.status_code == 200, r.text
    body = r.json()
    assert (body["total"], body["valid"], body["invalid"]) == (3, 3, 0)
    assert body["dry_run"] is True
    assert spy.companies == [], "simulação NÃO pode escrever no Znuny"

    rows = (await session.execute(select(Tenant))).scalars().all()
    assert rows == [], "simulação NÃO pode escrever no Postgres"


@pytest.mark.asyncio
async def test_validate_points_at_the_line_with_the_problem(engine, session, monkeypatch):
    settings, _spy, app = await _setup(engine, session, monkeypatch)
    bad = "\n".join(
        [
            _HEADER,
            "Alfa LTDA,Alfa,1,alfa,ALFA,BH",
            "Beta LTDA,Beta,2,,BETA,SP",  # subdomínio vazio
            "Gama LTDA,Gama,3,GAMA-MAIUSCULO,GAMA,CWB",  # subdomínio inválido
        ]
    )
    async with _client(app) as c:
        c.cookies.set("gsid_adm", encode_admin_session("william", settings))
        r = await c.post("/v1/admin/import/tenants/validate", headers=_HOST, files=_csv(bad))
    body = r.json()
    assert body["valid"] == 1
    assert body["invalid"] == 2
    problems = {row["line"]: row["message"] for row in body["rows"] if row["status"] == "failed"}
    # O número da LINHA é o que o operador usa para consertar a planilha.
    assert 3 in problems and "subdomain" in problems[3]
    assert 4 in problems and "minúsculo" in problems[4]


@pytest.mark.asyncio
async def test_duplicate_inside_the_file_is_caught_before_writing(engine, session, monkeypatch):
    settings, _spy, app = await _setup(engine, session, monkeypatch)
    dup = "\n".join(
        [
            _HEADER,
            "Alfa LTDA,Alfa,1,alfa,ALFA,BH",
            "Alfa de novo,Alfa2,9,alfa,ALFA2,SP",
        ]
    )
    async with _client(app) as c:
        c.cookies.set("gsid_adm", encode_admin_session("william", settings))
        r = await c.post("/v1/admin/import/tenants/validate", headers=_HOST, files=_csv(dup))
    body = r.json()
    assert body["invalid"] == 1
    assert "repetida no próprio arquivo" in body["rows"][1]["message"]


# ── arquivo recusado por inteiro ────────────────────────────────────────────


@pytest.mark.asyncio
async def test_wrong_header_is_refused_with_the_expected_columns(engine, session, monkeypatch):
    settings, _spy, app = await _setup(engine, session, monkeypatch)
    async with _client(app) as c:
        c.cookies.set("gsid_adm", encode_admin_session("william", settings))
        r = await c.post(
            "/v1/admin/import/tenants/validate",
            headers=_HOST,
            files=_csv("nome,cnpj\nAlfa,1"),
        )
    assert r.status_code == 422
    detail = r.json()["detail"]
    assert "faltam as colunas obrigatórias" in detail
    # A mensagem precisa DIZER quais colunas — senão o operador adivinha.
    assert "legal_name" in detail and "subdomain" in detail


@pytest.mark.asyncio
async def test_a_password_column_is_refused(engine, session, monkeypatch):
    """V-R8.3 — senha não trafega em planilha, e a recusa explica por quê."""
    settings, _spy, app = await _setup(engine, session, monkeypatch)
    async with _client(app) as c:
        c.cookies.set("gsid_adm", encode_admin_session("william", settings))
        r = await c.post(
            "/v1/admin/import/tenant_users/validate",
            headers=_HOST,
            files=_csv("email,first_name,last_name,password\na@b.com,A,B,segredo"),
        )
    assert r.status_code == 422
    assert "senha não trafega em planilha" in r.json()["detail"]


@pytest.mark.asyncio
async def test_unknown_kind_is_404(engine, session, monkeypatch):
    settings, _spy, app = await _setup(engine, session, monkeypatch)
    async with _client(app) as c:
        c.cookies.set("gsid_adm", encode_admin_session("william", settings))
        for path in ("/v1/admin/import/contracts/validate", "/v1/admin/import/contracts"):
            r = await c.post(path, headers=_HOST, files=_csv(_THREE))
            assert r.status_code == 404, path


# ── execução ────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_import_creates_and_is_idempotent(engine, session, monkeypatch):
    """V-R8.2 — reexecutar o mesmo arquivo não duplica nada."""
    settings, _spy, app = await _setup(engine, session, monkeypatch)
    async with _client(app) as c:
        c.cookies.set("gsid_adm", encode_admin_session("william", settings))
        first = await c.post("/v1/admin/import/tenants", headers=_HOST, files=_csv(_THREE))
        assert first.status_code == 200, first.text
        assert first.json()["created"] == 3

        again = await c.post("/v1/admin/import/tenants", headers=_HOST, files=_csv(_THREE))
        assert again.json() == {**again.json(), "created": 0, "skipped": 3}

    rows = (await session.execute(select(Tenant))).scalars().all()
    assert len(rows) == 3
    # O endereço da planilha chegou ao cadastro.
    alfa = next(t for t in rows if t.znuny_customer_id == "ALFA")
    assert alfa.address_city == "Belo Horizonte"


@pytest.mark.asyncio
async def test_a_bad_line_does_not_abort_the_others(engine, session, monkeypatch):
    """V-R8.3 — falha isolada: as linhas boas entram mesmo assim."""
    settings, _spy, app = await _setup(engine, session, monkeypatch)
    mixed = "\n".join(
        [
            _HEADER,
            "Alfa LTDA,Alfa,1,alfa,ALFA,BH",
            "Beta LTDA,Beta,2,,BETA,SP",  # ruim
            "Gama LTDA,Gama,3,gama,GAMA,CWB",
        ]
    )
    async with _client(app) as c:
        c.cookies.set("gsid_adm", encode_admin_session("william", settings))
        r = await c.post("/v1/admin/import/tenants", headers=_HOST, files=_csv(mixed))
    body = r.json()
    assert body["created"] == 2
    assert body["failed"] == 1
    assert [row["line"] for row in body["rows"] if row["status"] == "failed"] == [3]
    rows = (await session.execute(select(Tenant))).scalars().all()
    assert sorted(t.znuny_customer_id for t in rows) == ["ALFA", "GAMA"]


@pytest.mark.asyncio
async def test_user_import_generates_a_password_shown_once(engine, session, monkeypatch):
    settings, spy, app = await _setup(engine, session, monkeypatch)
    async with _client(app) as c:
        c.cookies.set("gsid_adm", encode_admin_session("william", settings))
        await c.post("/v1/admin/import/tenants", headers=_HOST, files=_csv(_THREE))
        tenants = await c.get("/v1/admin/tenants", headers=_HOST)
        tid = next(t["id"] for t in tenants.json() if t["subdomain"] == "alfa")

        users = "email,first_name,last_name,role,extension\nana@alfa.com,Ana,Souza,admin,204"
        r = await c.post(
            f"/v1/admin/import/tenant_users?tenant_id={tid}", headers=_HOST, files=_csv(users)
        )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["created"] == 1
    generated = body["rows"][0]["generated_password"]
    assert generated and len(generated) >= 12
    # E ela chegou ao Znuny como senha de verdade.
    assert any(pw == generated for _login, pw in spy.passwords)

    role = (await session.execute(select(PortalUserRole))).scalars().one()
    assert role.extension == "204"


@pytest.mark.asyncio
async def test_user_import_requires_a_tenant(engine, session, monkeypatch):
    settings, _spy, app = await _setup(engine, session, monkeypatch)
    async with _client(app) as c:
        c.cookies.set("gsid_adm", encode_admin_session("william", settings))
        users = "email,first_name,last_name\nana@alfa.com,Ana,Souza"
        r = await c.post("/v1/admin/import/tenant_users", headers=_HOST, files=_csv(users))
    assert r.status_code == 422


@pytest.mark.asyncio
async def test_template_is_downloadable_and_matches_the_parser(engine, session, monkeypatch):
    """O modelo baixado tem que ser aceito pelo próprio importador."""
    settings, _spy, app = await _setup(engine, session, monkeypatch)
    async with _client(app) as c:
        c.cookies.set("gsid_adm", encode_admin_session("william", settings))
        tpl = await c.get("/v1/admin/import/tenants/template", headers=_HOST)
        assert tpl.status_code == 200
        assert "legal_name" in tpl.text
        # Round-trip: o modelo passa na validação.
        r = await c.post("/v1/admin/import/tenants/validate", headers=_HOST, files=_csv(tpl.text))
    assert r.status_code == 200
    assert r.json()["invalid"] == 0


@pytest.mark.asyncio
async def test_import_routes_require_an_agent_session(engine, session, monkeypatch):
    settings, _spy, app = await _setup(engine, session, monkeypatch)
    async with _client(app) as c:
        for path in (
            "/v1/admin/import/tenants/validate",
            "/v1/admin/import/tenants",
        ):
            assert (await c.post(path, headers=_HOST, files=_csv(_THREE))).status_code == 401
        assert (await c.get("/v1/admin/import/tenants/template", headers=_HOST)).status_code == 401
    assert settings is not None
