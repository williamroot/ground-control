# apps/sidecar/tests/test_tickets_router.py
from __future__ import annotations

import datetime as dt

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from gerti_sidecar import db
from gerti_sidecar.auth.session import encode_session
from gerti_sidecar.config import get_settings
from gerti_sidecar.integrations import znuny_ticket
from gerti_sidecar.main import create_app
from gerti_sidecar.models import Contract, Tenant, TenantBranding, TenantQueue, ZnunyInstance
from gerti_sidecar.models.enums import ContractType


async def _seed(session):
    inst = ZnunyInstance(
        name="i",
        base_url="http://z",
        db_dsn_secret_ref="x",
        webservice_token_secret_ref="x",
        webhook_signing_secret_ref="x",
        mode="pool",
    )
    session.add(inst)
    await session.flush()
    t = Tenant(
        legal_name="Acme",
        trade_name="Acme",
        document="1",
        znuny_customer_id="ACME",
        znuny_instance_id=inst.id,
        subdomain="acme",
    )
    session.add(t)
    await session.flush()
    session.add(TenantBranding(tenant_id=t.id, display_name="Acme"))
    contract = Contract(
        tenant_id=t.id,
        code="C-1",
        type=ContractType.hour_bank,
        starts_on=dt.date(2026, 1, 1),
        ends_on=dt.date(2026, 12, 31),
        initial_hours=100,
        created_by="seed",
    )
    session.add(contract)
    await session.commit()
    return t


@pytest.mark.asyncio
async def test_open_ticket_single_contract(engine, app_session_factory, session, monkeypatch):
    monkeypatch.setenv("SESSION_SECRET", "test-secret-32-chars-minimum-xxxx")
    monkeypatch.setenv("ENVIRONMENT", "test")
    get_settings.cache_clear()
    t = await _seed(session)

    async def fake_create(**kw):
        return znuny_ticket.TicketCreated(123, "2026010100001")

    monkeypatch.setattr(znuny_ticket, "create_ticket", fake_create)
    monkeypatch.setattr(
        db,
        "AdminSessionLocal",
        async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession),
    )
    monkeypatch.setattr(db, "SessionLocal", app_session_factory)
    app = create_app()
    st = get_settings()
    h = {"host": "acme.suporte.gerti.com.br"}
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        c.cookies.set("gsid", encode_session(str(t.id), "joe", "helpdesk", st))
        r = await c.post(
            "/v1/tickets", headers=h, data={"title": "t", "body": "b"}
        )  # sem contract_id -> auto
        assert r.status_code == 201
        assert r.json()["ticket_number"] == "2026010100001"


# --- T-R5.3: a fila do cliente vale na ROTA, não só no serviço ---------------
#
# A verificação ao vivo da Onda 1 pegou isto: o serviço validava a fila, mas a
# rota não recebia o campo do formulário, então a guarda nunca rodava e o 422
# de "fila não associada" era código morto. Teste de serviço passando não
# provava a rota.


@pytest.mark.asyncio
async def test_open_ticket_uses_tenant_default_queue(
    engine, app_session_factory, session, monkeypatch
):
    """Aceite A5.2 — sem fila informada, o chamado nasce na padrão do cliente."""
    monkeypatch.setenv("SESSION_SECRET", "test-secret-32-chars-minimum-xxxx")
    monkeypatch.setenv("ENVIRONMENT", "test")
    get_settings.cache_clear()
    t = await _seed(session)
    session.add(
        TenantQueue(
            tenant_id=t.id, znuny_queue_id=6, znuny_queue_name="Suporte::N1", is_default=True
        )
    )
    await session.commit()

    seen: dict = {}

    async def fake_create(**kw):
        seen.update(kw)
        return znuny_ticket.TicketCreated(123, "2026010100001")

    monkeypatch.setattr(znuny_ticket, "create_ticket", fake_create)
    monkeypatch.setattr(
        db,
        "AdminSessionLocal",
        async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession),
    )
    monkeypatch.setattr(db, "SessionLocal", app_session_factory)
    app = create_app()
    st = get_settings()
    h = {"host": "acme.suporte.gerti.com.br"}
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        c.cookies.set("gsid", encode_session(str(t.id), "joe", "helpdesk", st))
        r = await c.post("/v1/tickets", headers=h, data={"title": "t", "body": "b"})
        assert r.status_code == 201, r.text
    assert seen["queue"] == "Suporte::N1"


@pytest.mark.asyncio
async def test_open_ticket_rejects_queue_not_associated(
    engine, app_session_factory, session, monkeypatch
):
    """A rota precisa RECEBER a fila para a guarda existir — 422, sem criar nada."""
    monkeypatch.setenv("SESSION_SECRET", "test-secret-32-chars-minimum-xxxx")
    monkeypatch.setenv("ENVIRONMENT", "test")
    get_settings.cache_clear()
    t = await _seed(session)
    session.add(
        TenantQueue(
            tenant_id=t.id, znuny_queue_id=6, znuny_queue_name="Suporte::N1", is_default=True
        )
    )
    await session.commit()

    async def must_not_create(**kw):
        raise AssertionError("nenhum chamado pode nascer com fila recusada")

    monkeypatch.setattr(znuny_ticket, "create_ticket", must_not_create)
    monkeypatch.setattr(
        db,
        "AdminSessionLocal",
        async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession),
    )
    monkeypatch.setattr(db, "SessionLocal", app_session_factory)
    app = create_app()
    st = get_settings()
    h = {"host": "acme.suporte.gerti.com.br"}
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        c.cookies.set("gsid", encode_session(str(t.id), "joe", "helpdesk", st))
        r = await c.post(
            "/v1/tickets", headers=h, data={"title": "t", "body": "b", "queue": "Financeiro"}
        )
    assert r.status_code == 422, r.text
    assert r.json()["detail"] == "queue_not_allowed"


# --- V-R2.4: o detalhe tem que espelhar o escopo que a lista já usa ----------
# Mundo do Znuny fake: TicketID -> (CustomerID da empresa, CustomerUserID dono).
_WORLD = {
    501: ("ACME", "ana@acme"),  # chamado da Ana — MESMA empresa do bob
    502: ("ACME", "dora@acme"),  # chamado da Dora — idem (usado pelo admin)
    999: ("OUTRA", "zoe@outra"),  # chamado de outra empresa (cross-tenant)
}


async def _fake_get_ticket(*, znuny_ticket_id, customer_id, customer_user=None):
    """Espelha o contrato do GertiTicket::TicketGet (Perl) — não é complacente.

    CustomerID sempre confere. CustomerUserID é OPCIONAL: ausente/vazio => escopo
    de empresa (como antes); presente => o dono do chamado também precisa bater.
    Qualquer divergência devolve o MESMO 'ticket not found' (nunca 403, nunca
    erro distinto — não vaza a existência do chamado).
    """
    owner = _WORLD.get(znuny_ticket_id)
    if owner is None or owner[0] != customer_id:
        raise znuny_ticket.ZnunyWriteError("ticket not found")
    if customer_user and owner[1] != customer_user:
        raise znuny_ticket.ZnunyWriteError("ticket not found")
    return znuny_ticket.TicketDetail(
        znuny_ticket_id=znuny_ticket_id,
        ticket_number=f"20260101000{znuny_ticket_id}",
        title="chamado",
        state="open",
        priority="3 normal",
        created="2026-01-01 10:00:00",
        contract_id=None,
        customer_id=owner[0],
        articles=[],
    )


@pytest.mark.asyncio
async def test_get_ticket_ownership(engine, app_session_factory, session, monkeypatch):
    monkeypatch.setenv("SESSION_SECRET", "test-secret-32-chars-minimum-xxxx")
    monkeypatch.setenv("ENVIRONMENT", "test")
    get_settings.cache_clear()
    t = await _seed(session)

    monkeypatch.setattr(znuny_ticket, "get_ticket", _fake_get_ticket)
    monkeypatch.setattr(
        db,
        "AdminSessionLocal",
        async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession),
    )
    monkeypatch.setattr(db, "SessionLocal", app_session_factory)
    app = create_app()
    st = get_settings()
    h = {"host": "acme.suporte.gerti.com.br"}

    def _login(c, login: str, role: str) -> None:
        c.cookies.clear()
        c.cookies.set("gsid", encode_session(str(t.id), login, role, st))

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        # sem sessão => 401 (nem chega no GI)
        assert (await c.get("/v1/tickets/501", headers=h)).status_code == 401

        # ASSERT central: helpdesk da MESMA empresa não abre chamado de colega.
        _login(c, "bob@acme", "helpdesk")
        assert (await c.get("/v1/tickets/501", headers=h)).status_code == 404

        # ...mas o próprio chamado continua acessível ao dono.
        _login(c, "ana@acme", "helpdesk")
        r = await c.get("/v1/tickets/501", headers=h)
        assert r.status_code == 200
        assert r.json()["znuny_ticket_id"] == 501

        # admin do portal mantém o escopo de empresa (privilégio legítimo).
        _login(c, "chefe@acme", "admin")
        r = await c.get("/v1/tickets/501", headers=h)
        assert r.status_code == 200
        assert r.json()["znuny_ticket_id"] == 501

        # chamado de outra empresa: 404 para todo mundo, inclusive o admin.
        assert (await c.get("/v1/tickets/999", headers=h)).status_code == 404
        _login(c, "bob@acme", "helpdesk")
        assert (await c.get("/v1/tickets/999", headers=h)).status_code == 404


# --- Mesma classe de falha do V-R2.4, agora nas rotas de ESCRITA -------------
# Fake no _post do cliente GI (não no reply_ticket/get_ticket): assim o teste
# atravessa o cliente de verdade e pode afirmar o PAYLOAD que vai ao Znuny.


def _install_fake_gi_post(monkeypatch) -> list[dict]:
    """Espelha o contrato dos módulos Perl TicketGet/TicketReply.

    CustomerID (empresa) sempre confere. CustomerUserID é OPCIONAL e é guarda
    ADICIONAL: presente => o dono do chamado também precisa bater. Qualquer
    divergência devolve o MESMO 'ticket not found' (nunca 403, nunca erro
    distinto). Devolve a lista dos corpos enviados, para asserção de payload.
    """
    captured: list[dict] = []

    async def fake_post(route, body):
        captured.append({"route": route, **body})
        owner = _WORLD.get(int(body["TicketID"]))
        not_found = owner is None or owner[0] != body.get("CustomerID")
        if not not_found and body.get("CustomerUserID"):
            not_found = owner[1] != body["CustomerUserID"]
        if not_found:
            raise znuny_ticket.ZnunyWriteError("ticket not found")
        if route == "/Ticket/Reply":
            return {"ArticleID": 1}
        if route == "/Ticket/Get":
            return {
                "TicketID": body["TicketID"],
                "TicketNumber": "N1",
                "Title": "chamado",
                "State": "closed successful",
                "Priority": "3 normal",
                "Created": "2026-01-01 10:00:00",
                "CustomerID": owner[0],
                "ContractId": None,
                "Articles": [],
            }
        raise AssertionError(f"rota GI inesperada: {route}")

    monkeypatch.setattr(znuny_ticket, "_post", fake_post)
    return captured


def _wire_db(monkeypatch, engine, app_session_factory) -> None:
    monkeypatch.setattr(
        db,
        "AdminSessionLocal",
        async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession),
    )
    monkeypatch.setattr(db, "SessionLocal", app_session_factory)


@pytest.mark.asyncio
async def test_reply_ownership_scope(engine, app_session_factory, session, monkeypatch):
    """helpdesk não responde chamado de colega; admin do portal continua podendo."""
    monkeypatch.setenv("SESSION_SECRET", "test-secret-32-chars-minimum-xxxx")
    monkeypatch.setenv("ENVIRONMENT", "test")
    get_settings.cache_clear()
    t = await _seed(session)
    captured = _install_fake_gi_post(monkeypatch)
    _wire_db(monkeypatch, engine, app_session_factory)
    app = create_app()
    st = get_settings()
    h = {"host": "acme.suporte.gerti.com.br"}

    def _login(c, login: str, role: str) -> None:
        c.cookies.clear()
        c.cookies.set("gsid", encode_session(str(t.id), login, role, st))

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        # ASSERT central: helpdesk da MESMA empresa não escreve no chamado do colega.
        _login(c, "bob@acme", "helpdesk")
        r = await c.post("/v1/tickets/501/reply", headers=h, json={"body": "oi"})
        assert r.status_code == 404
        # ...e o escopo `own` foi de fato ao GI (senão o 404 seria por acaso).
        assert captured[-1]["route"] == "/Ticket/Reply"
        assert captured[-1]["CustomerUserID"] == "bob@acme"

        # o dono responde o PRÓPRIO chamado normalmente.
        _login(c, "ana@acme", "helpdesk")
        r = await c.post("/v1/tickets/501/reply", headers=h, json={"body": "oi"})
        assert r.status_code == 201
        assert r.json() == {"ok": True}
        assert captured[-1]["CustomerUser"] == "ana@acme"  # autor
        assert captured[-1]["CustomerUserID"] == "ana@acme"  # guarda

        # REGRESSÃO: admin do portal responde chamado da empresa (de outra pessoa)
        # — e o payload NÃO carrega a guarda por usuário.
        _login(c, "chefe@acme", "admin")
        r = await c.post("/v1/tickets/502/reply", headers=h, json={"body": "oi"})
        assert r.status_code == 201
        assert captured[-1]["CustomerUser"] == "chefe@acme"  # autor != dono, legítimo
        assert "CustomerUserID" not in captured[-1]

        # chamado de outra empresa: 404 até para o admin.
        assert (
            await c.post("/v1/tickets/999/reply", headers=h, json={"body": "oi"})
        ).status_code == 404


@pytest.mark.asyncio
async def test_csat_ownership_scope(engine, app_session_factory, session, monkeypatch):
    """helpdesk não avalia chamado de colega; admin do portal continua podendo."""
    monkeypatch.setenv("SESSION_SECRET", "test-secret-32-chars-minimum-xxxx")
    monkeypatch.setenv("ENVIRONMENT", "test")
    get_settings.cache_clear()
    t = await _seed(session)
    captured = _install_fake_gi_post(monkeypatch)
    _wire_db(monkeypatch, engine, app_session_factory)
    app = create_app()
    st = get_settings()
    h = {"host": "acme.suporte.gerti.com.br"}

    def _login(c, login: str, role: str) -> None:
        c.cookies.clear()
        c.cookies.set("gsid", encode_session(str(t.id), login, role, st))

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        # ASSERT central: helpdesk da MESMA empresa não avalia o chamado do colega.
        _login(c, "bob@acme", "helpdesk")
        r = await c.post("/v1/tickets/501/csat", headers=h, json={"score": 1})
        assert r.status_code == 404
        assert captured[-1]["route"] == "/Ticket/Get"
        assert captured[-1]["CustomerUserID"] == "bob@acme"

        # o dono avalia o PRÓPRIO chamado normalmente.
        _login(c, "ana@acme", "helpdesk")
        r = await c.post("/v1/tickets/501/csat", headers=h, json={"score": 5})
        assert r.status_code == 201
        assert r.json()["score"] == 5

        # REGRESSÃO: admin do portal avalia chamado da empresa, sem guarda por usuário.
        _login(c, "chefe@acme", "admin")
        r = await c.post("/v1/tickets/502/csat", headers=h, json={"score": 4})
        assert r.status_code == 201
        assert "CustomerUserID" not in captured[-1]

        # chamado de outra empresa: 404 até para o admin.
        assert (
            await c.post("/v1/tickets/999/csat", headers=h, json={"score": 5})
        ).status_code == 404


@pytest.mark.asyncio
async def test_reply_happy_path(engine, app_session_factory, session, monkeypatch):
    monkeypatch.setenv("SESSION_SECRET", "test-secret-32-chars-minimum-xxxx")
    monkeypatch.setenv("ENVIRONMENT", "test")
    get_settings.cache_clear()
    t = await _seed(session)

    async def fake_reply(**kw):
        return None

    monkeypatch.setattr(znuny_ticket, "reply_ticket", fake_reply)
    monkeypatch.setattr(
        db,
        "AdminSessionLocal",
        async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession),
    )
    monkeypatch.setattr(db, "SessionLocal", app_session_factory)
    app = create_app()
    st = get_settings()
    h = {"host": "acme.suporte.gerti.com.br"}
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        c.cookies.set("gsid", encode_session(str(t.id), "joe", "helpdesk", st))
        r = await c.post("/v1/tickets/5/reply", headers=h, json={"body": "oi"})
        assert r.status_code == 201
        assert r.json() == {"ok": True}


@pytest.mark.asyncio
async def test_reply_ownership_404(engine, app_session_factory, session, monkeypatch):
    monkeypatch.setenv("SESSION_SECRET", "test-secret-32-chars-minimum-xxxx")
    monkeypatch.setenv("ENVIRONMENT", "test")
    get_settings.cache_clear()
    t = await _seed(session)

    from gerti_sidecar.integrations.znuny_ticket import ZnunyWriteError

    async def fake_reply(**kw):
        raise ZnunyWriteError("not found")

    monkeypatch.setattr(znuny_ticket, "reply_ticket", fake_reply)
    monkeypatch.setattr(
        db,
        "AdminSessionLocal",
        async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession),
    )
    monkeypatch.setattr(db, "SessionLocal", app_session_factory)
    app = create_app()
    st = get_settings()
    h = {"host": "acme.suporte.gerti.com.br"}
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        c.cookies.set("gsid", encode_session(str(t.id), "joe", "helpdesk", st))
        r = await c.post("/v1/tickets/5/reply", headers=h, json={"body": "oi"})
        assert r.status_code == 404


@pytest.mark.asyncio
async def test_video_attachment_allowed(engine, app_session_factory, session, monkeypatch):
    monkeypatch.setenv("SESSION_SECRET", "test-secret-32-chars-minimum-xxxx")
    monkeypatch.setenv("ENVIRONMENT", "test")
    get_settings.cache_clear()
    t = await _seed(session)

    async def fake_create(**kw):
        assert kw["attachments"] and kw["attachments"][0].filename.endswith(".mp4")
        return znuny_ticket.TicketCreated(7, "N7")

    monkeypatch.setattr(znuny_ticket, "create_ticket", fake_create)
    monkeypatch.setattr(
        db,
        "AdminSessionLocal",
        async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession),
    )
    monkeypatch.setattr(db, "SessionLocal", app_session_factory)
    app = create_app()
    st = get_settings()
    h = {"host": "acme.suporte.gerti.com.br"}
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        c.cookies.set("gsid", encode_session(str(t.id), "joe", "helpdesk", st))
        r = await c.post(
            "/v1/tickets",
            headers=h,
            data={"title": "t", "body": "b"},
            files={"files": ("clip.mp4", b"\x00\x00\x00\x18ftypmp42", "video/mp4")},
        )
        assert r.status_code == 201


@pytest.mark.asyncio
async def test_list_helpdesk_scope_own(engine, app_session_factory, session, monkeypatch):
    monkeypatch.setenv("SESSION_SECRET", "test-secret-32-chars-minimum-xxxx")
    monkeypatch.setenv("ENVIRONMENT", "test")
    get_settings.cache_clear()
    t = await _seed(session)

    async def fake_search(*, scope, customer_user, customer_id):
        assert scope == "own"
        return []

    monkeypatch.setattr(znuny_ticket, "search_tickets", fake_search)
    monkeypatch.setattr(
        db,
        "AdminSessionLocal",
        async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession),
    )
    monkeypatch.setattr(db, "SessionLocal", app_session_factory)
    app = create_app()
    st = get_settings()
    h = {"host": "acme.suporte.gerti.com.br"}
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        c.cookies.set("gsid", encode_session(str(t.id), "joe", "helpdesk", st))
        r = await c.get("/v1/tickets", headers=h)
        assert r.status_code == 200
        assert r.json() == []
