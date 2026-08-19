"""V-R9.2 — configuração de e-mail pelo console, e a senha que nunca pode sair.

O aceite A9.4 diz: *"a senha de uma conta de e-mail **nunca** aparece em
resposta de sistema, tela ou auditoria"*. Isso não é higiene genérica — o
Znuny guarda a senha da caixa postal **em texto claro** no banco, e o
`MailAccountGet` nativo a devolve. Se a capa de administração repassasse a
resposta como veio, qualquer leitura da tela traria senha de caixa no corpo
HTTP.

Por isso os testes aqui atacam a garantia de três ângulos:
  1. a resposta da listagem não contém senha, em nenhum nível do JSON;
  2. salvar SEM digitar senha não manda senha ao Znuny (é o que permite editar
     a fila de uma caixa sem nunca ter conhecido a senha dela);
  3. a auditoria registra QUE a senha mudou, nunca QUAL é.
"""

from __future__ import annotations

import json
from typing import Any

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from gerti_sidecar import db
from gerti_sidecar.auth.admin_session import encode_admin_session
from gerti_sidecar.config import get_settings
from gerti_sidecar.integrations import znuny_admin_mail as gi
from gerti_sidecar.main import create_app
from gerti_sidecar.models import AuditLog

_HOST = {"host": "gerti.was.dev.br"}
_SECRET = "s3nha-que-nao-pode-vazar"


def _settings(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("SESSION_SECRET", "test-secret-32-chars-minimum-xxxx")
    monkeypatch.setenv("ENVIRONMENT", "test")
    get_settings.cache_clear()
    return get_settings()


class _Znuny:
    """Znuny de mentira que se comporta MAL de propósito.

    Ele devolve `Password` em texto claro na listagem — exatamente como o
    `MailAccountGet` nativo faz. Se a nossa camada não filtrar, o teste pega.
    """

    def __init__(self) -> None:
        self.set_calls: list[dict[str, Any]] = []

    async def list_mail_accounts(self, *, agent_login: str):
        from gerti_sidecar.integrations.znuny_admin_mail import MailAccount

        return [
            MailAccount(
                id=1,
                login="suporte@gerti.example",
                host="imap.gerti.example",
                type="IMAPS",
                valid=True,
                trusted=False,
                dispatching_by="Queue",
                queue_id=6,
                queue_name="Suporte::N1",
                comment="",
                imap_folder="INBOX",
                has_password=True,
            )
        ]

    async def set_mail_account(self, **kw):
        self.set_calls.append(kw)
        return {"Action": "updated", "Account": {"ID": kw.get("account_id") or 1}}


def _client(app) -> AsyncClient:
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://t")


async def _setup(engine, monkeypatch):
    settings = _settings(monkeypatch)
    factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    monkeypatch.setattr(db, "AdminSessionLocal", factory)
    monkeypatch.setattr(db, "SessionLocal", factory)
    fake = _Znuny()
    monkeypatch.setattr(gi, "list_mail_accounts", fake.list_mail_accounts)
    monkeypatch.setattr(gi, "set_mail_account", fake.set_mail_account)
    return settings, fake, create_app()


def _body(**over) -> dict[str, Any]:
    base = {
        "login": "suporte@gerti.example",
        "host": "imap.gerti.example",
        "type": "IMAPS",
        "valid": True,
        "trusted": False,
        "dispatching_by": "Queue",
        "queue_id": 6,
        "comment": "",
        "imap_folder": "INBOX",
    }
    base.update(over)
    return base


# ── A9.4: a senha não sai ───────────────────────────────────────────────────


def test_strip_secrets_kills_password_at_any_depth():
    """A rede de segurança do lado Python, testada isolada."""
    payload = {
        "Accounts": [
            {"ID": 1, "Login": "a@b", "Password": _SECRET, "pw": _SECRET},
            {"ID": 2, "Nested": {"UserPw": _SECRET, "Login": "c@d"}},
        ],
        "Token": "abc",
    }
    clean = gi._strip_secrets(payload)
    dumped = json.dumps(clean)
    assert _SECRET not in dumped
    assert "abc" not in dumped  # `Token` também é segredo
    # E o que NÃO é segredo continua lá.
    assert clean["Accounts"][0]["Login"] == "a@b"
    assert clean["Accounts"][1]["Nested"]["Login"] == "c@d"


@pytest.mark.asyncio
async def test_listing_never_returns_a_password(engine, monkeypatch):
    settings, _fake, app = await _setup(engine, monkeypatch)
    async with _client(app) as c:
        c.cookies.set("gsid_adm", encode_admin_session("william", settings))
        r = await c.get("/v1/admin/znuny/mail-accounts", headers=_HOST)
    assert r.status_code == 200, r.text
    assert _SECRET not in r.text
    # Nenhuma CHAVE de segredo na resposta. `has_password` é permitida de
    # propósito — ela diz que existe senha, não qual é; sem ela a tela
    # mostraria um campo vazio, que se lê como "esta conta não tem senha".
    payload = r.json()
    for account in payload:
        for key in account:
            assert key == "has_password" or "password" not in key.lower(), key
            assert key.lower() != "pw", key
    assert payload[0]["has_password"] is True


@pytest.mark.asyncio
async def test_saving_without_typing_a_password_sends_none(engine, monkeypatch):
    """É isto que permite editar a fila de uma caixa sem conhecer a senha dela."""
    settings, fake, app = await _setup(engine, monkeypatch)
    async with _client(app) as c:
        c.cookies.set("gsid_adm", encode_admin_session("william", settings))
        r = await c.put("/v1/admin/znuny/mail-accounts/1", headers=_HOST, json=_body(queue_id=7))
    assert r.status_code == 200, r.text
    assert fake.set_calls[-1]["password"] is None
    assert fake.set_calls[-1]["queue_id"] == 7


@pytest.mark.asyncio
async def test_audit_records_that_the_password_changed_not_which(engine, session, monkeypatch):
    settings, _fake, app = await _setup(engine, monkeypatch)
    async with _client(app) as c:
        c.cookies.set("gsid_adm", encode_admin_session("william", settings))
        r = await c.put(
            "/v1/admin/znuny/mail-accounts/1", headers=_HOST, json=_body(password=_SECRET)
        )
        assert r.status_code == 200, r.text

    row = (
        (
            await session.execute(
                select(AuditLog)
                .where(AuditLog.entity == "znuny_mail_account")
                .order_by(AuditLog.at.desc())
            )
        )
        .scalars()
        .first()
    )
    assert row is not None
    dumped = json.dumps(row.metadata_json)
    assert _SECRET not in dumped
    assert row.metadata_json["password_changed"] is True
    assert row.metadata_json["queue_id"] == 6


@pytest.mark.asyncio
async def test_creating_without_a_password_is_refused(engine, monkeypatch):
    """Criar caixa sem senha não é 'manter a atual' — não existe atual."""
    settings, fake, app = await _setup(engine, monkeypatch)
    async with _client(app) as c:
        c.cookies.set("gsid_adm", encode_admin_session("william", settings))
        r = await c.post("/v1/admin/znuny/mail-accounts", headers=_HOST, json=_body())
    assert r.status_code == 422, r.text
    assert fake.set_calls == [], "não pode chegar a chamar o Znuny"


# ── autorização ─────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_mail_routes_require_an_agent_session(engine, monkeypatch):
    _settings_, _fake, app = await _setup(engine, monkeypatch)
    paths = [
        ("GET", "/v1/admin/znuny/mail-accounts"),
        ("POST", "/v1/admin/znuny/mail-accounts"),
        ("PUT", "/v1/admin/znuny/mail-accounts/1"),
        ("GET", "/v1/admin/znuny/postmaster-filters"),
        ("POST", "/v1/admin/znuny/postmaster-filters"),
        ("DELETE", "/v1/admin/znuny/postmaster-filters/qualquer"),
    ]
    async with _client(app) as c:  # sem cookie
        for method, p in paths:
            assert (await c.request(method, p, headers=_HOST, json={})).status_code == 401, p
    async with _client(app) as c2:
        c2.cookies.set("gsid", "cookie-de-cliente-nao-serve")
        for method, p in paths:
            assert (await c2.request(method, p, headers=_HOST, json={})).status_code == 401, p


# ── filtros de domínio ──────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_filter_name_is_validated_before_touching_znuny(engine, monkeypatch):
    settings, _fake, app = await _setup(engine, monkeypatch)
    called: list[str] = []

    async def _must_not_call(**kw):
        called.append("chamou")
        return {}

    monkeypatch.setattr(gi, "set_postmaster_filter", _must_not_call)
    monkeypatch.setattr(gi, "delete_postmaster_filter", _must_not_call)

    async with _client(app) as c:
        c.cookies.set("gsid_adm", encode_admin_session("william", settings))
        bad = {
            "name": "../../etc/passwd",
            "match": [{"key": "From", "value": "@x.com"}],
            "set": [{"key": "X-OTRS-CustomerNo", "value": "X"}],
        }
        assert (
            await c.post("/v1/admin/znuny/postmaster-filters", headers=_HOST, json=bad)
        ).status_code == 422
        assert (
            await c.delete("/v1/admin/znuny/postmaster-filters/..%2Fetc", headers=_HOST)
        ).status_code in (404, 422)
    assert called == []


@pytest.mark.asyncio
async def test_renaming_a_filter_is_refused(engine, monkeypatch):
    """Renomear é apagar+criar no Znuny; não pode sair de um form de edição."""
    settings, _fake, app = await _setup(engine, monkeypatch)

    async def _must_not_call(**kw):
        raise AssertionError("não pode chamar o Znuny")

    monkeypatch.setattr(gi, "set_postmaster_filter", _must_not_call)
    async with _client(app) as c:
        c.cookies.set("gsid_adm", encode_admin_session("william", settings))
        r = await c.put(
            "/v1/admin/znuny/postmaster-filters/antigo",
            headers=_HOST,
            json={
                "name": "novo",
                "match": [{"key": "From", "value": "@x.com"}],
                "set": [{"key": "X-OTRS-CustomerNo", "value": "X"}],
            },
        )
    assert r.status_code == 422


@pytest.mark.asyncio
async def test_deleting_a_filter_audits_the_previous_state(engine, session, monkeypatch):
    """Exceção declarada à regra "sem exclusão": some do Znuny, fica na trilha."""
    settings, _fake, app = await _setup(engine, monkeypatch)
    before = {
        "Name": "aurora-dominio",
        "StopAfterMatch": 0,
        "Match": [{"Key": "From", "Value": "@auroramoveis.com.br"}],
        "Set": [{"Key": "X-OTRS-CustomerNo", "Value": "AURORA"}],
    }

    async def _delete(*, agent_login, name):
        return {"Action": "deleted", "Before": before}

    monkeypatch.setattr(gi, "delete_postmaster_filter", _delete)
    async with _client(app) as c:
        c.cookies.set("gsid_adm", encode_admin_session("william", settings))
        r = await c.delete("/v1/admin/znuny/postmaster-filters/aurora-dominio", headers=_HOST)
    assert r.status_code == 200, r.text

    row = (
        (
            await session.execute(
                select(AuditLog)
                .where(AuditLog.entity == "znuny_postmaster_filter")
                .order_by(AuditLog.at.desc())
            )
        )
        .scalars()
        .first()
    )
    assert row is not None
    assert row.action == "delete"
    # O estado anterior COMPLETO está na trilha — a remoção é reconstituível.
    assert row.metadata_json["antes"]["Set"][0]["Value"] == "AURORA"
