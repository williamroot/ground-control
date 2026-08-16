"""R18b — o relatório executivo mensal que a Gerti manda para os clientes dela.

*"para ele saber quanto gastou, quanto consumiu, quais foram os principais
tipos de ticket. No final, a gente põe a listona de chamados."* (11:36)

O que estes testes protegem:
  • V-R18b.1  conteúdo: consumo, tipos mais frequentes e a lista de chamados
  • V-R18b.2  a unidade segue o CONTRATO — crédito sai em reais e o relatório
              não expõe minutos
  • S2        a suposição "principais tipos = catálogo de serviço" está atrás da
              chave `REPORT_TOP_DIMENSION`, e o teste roda nos TRÊS estados
  • A18b.5    mês malformado morre no domínio, antes de virar consulta
  • A18b.6    Znuny fora do ar marca `degraded` em vez de fingir mês vazio
"""

from __future__ import annotations

import datetime as dt

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from gerti_sidecar.db import tenant_session_scope
from gerti_sidecar.domain.report_service import (
    InvalidMonth,
    ReportService,
    TenantNotFound,
    month_label_pt,
    month_range,
)
from gerti_sidecar.integrations.znuny_ticket import TicketStats, ZnunyUnavailable
from gerti_sidecar.models import (
    ConsumptionEvent,
    Contract,
    Tenant,
    TenantBranding,
    ZnunyInstance,
)
from gerti_sidecar.models.enums import ContractType

_MONTH = "2026-05"


def _stats(**kw) -> TicketStats:
    base = {
        "by_state": {"open": 2, "closed successful": 1},
        "by_priority": {"3 normal": 3},
        "by_day": [],
        "sla_breached": 0,
        "sla_at_risk": 0,
        "total": 3,
        "by_type": {"Incidente": 2, "Solicitação": 1},
        "by_service": {"Suporte::Estação de trabalho": 2, "Suporte::Rede": 1},
        "by_queue": {"Suporte::N1": 3},
        "tickets": [
            {
                "znuny_ticket_id": 11,
                "ticket_number": "2026050100001",
                "title": "Outlook travando",
                "state": "closed successful",
                "priority": "3 normal",
                "type": "Incidente",
                "service": "Suporte::Estação de trabalho",
                "queue": "Suporte::N1",
                "created": "2026-05-03 09:00:00",
                "customer_user": "ana@acme.example",
                "accounted_time": 120.0,
            },
            {
                "znuny_ticket_id": 12,
                "ticket_number": "2026050100002",
                "title": "Impressora sem rede",
                "state": "open",
                "priority": "3 normal",
                "type": "Incidente",
                "service": "Suporte::Rede",
                "queue": "Suporte::N1",
                "created": "2026-05-01 08:00:00",
                "customer_user": "ana@acme.example",
                "accounted_time": 60.0,
            },
            {
                "znuny_ticket_id": 13,
                "ticket_number": "2026050100003",
                "title": "Acesso novo colaborador",
                "state": "open",
                "priority": "3 normal",
                "type": "Solicitação",
                "service": "Suporte::Estação de trabalho",
                "queue": "Suporte::N1",
                "created": "2026-05-20 14:00:00",
                "customer_user": "ana@acme.example",
                "accounted_time": 120.0,
            },
        ],
        "tickets_truncated": False,
    }
    base.update(kw)
    return TicketStats(**base)


class _GI:
    def __init__(self, stats: TicketStats | None = None, *, down: bool = False) -> None:
        self._stats = stats if stats is not None else _stats()
        self._down = down
        self.calls: list[dict] = []

    async def ticket_stats(self, *, customer_id, since, until, include_tickets=False):
        self.calls.append(
            {
                "customer_id": customer_id,
                "since": since,
                "until": until,
                "include_tickets": include_tickets,
            }
        )
        if self._down:
            raise ZnunyUnavailable("timeout")
        return self._stats


async def _seed(session: AsyncSession, *, contract_type: ContractType) -> Tenant:
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
        legal_name="Acme Indústria",
        trade_name="Acme",
        document="1",
        znuny_customer_id="ACME",
        znuny_instance_id=inst.id,
        subdomain="acme",
    )
    session.add(t)
    await session.flush()
    session.add(TenantBranding(tenant_id=t.id, display_name="Acme Suporte"))
    kwargs: dict = {}
    if contract_type == ContractType.hour_bank:
        kwargs["initial_hours"] = 100
    elif contract_type == ContractType.credit_brl:
        kwargs["initial_amount_brl"] = 10000
        kwargs["unit_price_brl"] = 200
    c = Contract(
        tenant_id=t.id,
        code="C-1",
        type=contract_type,
        starts_on=dt.date(2026, 1, 1),
        ends_on=dt.date(2026, 12, 31),
        created_by="seed",
        **kwargs,
    )
    session.add(c)
    await session.flush()
    # 5 h no mês de maio (300 min), mais 2 h em ABRIL que NÃO podem entrar.
    for minutes, amount, when in (
        (180.0, 600.0, dt.datetime(2026, 5, 3, 9, tzinfo=dt.UTC)),
        (120.0, 400.0, dt.datetime(2026, 5, 20, 14, tzinfo=dt.UTC)),
        (120.0, 400.0, dt.datetime(2026, 4, 15, 10, tzinfo=dt.UTC)),
    ):
        session.add(
            ConsumptionEvent(
                contract_id=c.id,
                occurred_at=when,
                source_kind="ticket_work",
                source_ref=f"znuny:ticket:{int(minutes)}",
                billable_minutes=minutes,
                billable_amount_brl=amount,
                recorded_by="seed",
            )
        )
    await session.commit()
    return t


# ── mês ────────────────────────────────────────────────────────────────────


def test_month_range_and_label():
    assert month_range("2026-05") == (dt.date(2026, 5, 1), dt.date(2026, 5, 31))
    assert month_range("2026-02") == (dt.date(2026, 2, 1), dt.date(2026, 2, 28))
    assert month_label_pt("2026-05") == "maio/2026"


@pytest.mark.parametrize("bad", ["2026-13", "2026-00", "202605", "", "maio", "2026-5", None])
def test_month_range_rejects_garbage(bad):
    """A18b.5 — mês inválido morre aqui, antes de virar consulta."""
    with pytest.raises(InvalidMonth):
        month_range(bad)


# ── conteúdo ───────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_report_content_hour_bank(engine, app_session_factory, session):
    """V-R18b.1 — consumo em horas, tipos mais frequentes e a listona."""
    t = await _seed(session, contract_type=ContractType.hour_bank)
    gi = _GI()
    async with tenant_session_scope(t.id, factory=app_session_factory) as s:
        admin = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
        async with admin() as meta:
            r = await ReportService(s, gi, top_dimension="type").monthly(
                t.id, _MONTH, admin_session=meta
            )

    # Consumo: 180 + 120 minutos de MAIO = 5.0 h. Abril fica de fora.
    assert len(r.consumption) == 1
    assert r.consumption[0].kind == "hours"
    assert r.consumption[0].value == 5.0
    assert r.consumption[0].unit_label == "horas"

    # Principais tipos, na dimensão pedida.
    assert r.dimension == "type"
    assert r.top_items[0] == ("Incidente", 2)

    # A listona, ordenada por data de abertura.
    assert len(r.tickets) == 3
    assert [x.ticket_number for x in r.tickets] == [
        "2026050100002",
        "2026050100001",
        "2026050100003",
    ]
    assert r.tickets[0].hours == 1.0  # 60 min
    assert r.ticket_total == 3
    assert r.degraded is False
    assert r.month_label == "maio/2026"
    assert r.display_name == "Acme Suporte"

    # A janela mandada ao Znuny é o mês pedido, não "os últimos 30 dias".
    assert gi.calls[0]["since"].startswith("2026-05-01")
    assert gi.calls[0]["until"].startswith("2026-05-31")


@pytest.mark.asyncio
async def test_report_credit_contract_is_in_reais_and_hides_minutes(
    engine, app_session_factory, session
):
    """V-R18b.2 / aceite A18b.2 — a unidade é a do contrato, e minuto não vaza."""
    t = await _seed(session, contract_type=ContractType.credit_brl)
    async with tenant_session_scope(t.id, factory=app_session_factory) as s:
        admin = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
        async with admin() as meta:
            r = await ReportService(s, _GI()).monthly(t.id, _MONTH, admin_session=meta)

    assert r.consumption[0].kind == "brl"
    assert r.consumption[0].value == 1000.0  # 600 + 400 de maio
    assert r.consumption[0].unit_label == "reais"
    # O bloco de consumo NÃO carrega minuto nenhum para este cliente.
    assert not hasattr(r.consumption[0], "minutes")
    assert "minute" not in str(r.consumption[0]).lower()


@pytest.mark.asyncio
async def test_contract_without_balance_is_left_out(engine, app_session_factory, session):
    """Valor fechado / SaaS não têm consumo a medir — ficam fora, não viram 0."""
    t = await _seed(session, contract_type=ContractType.saas_product)
    async with tenant_session_scope(t.id, factory=app_session_factory) as s:
        admin = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
        async with admin() as meta:
            r = await ReportService(s, _GI()).monthly(t.id, _MONTH, admin_session=meta)
    assert r.consumption == []


# ── S2: a suposição está atrás de uma chave, e vale nos três estados ───────


@pytest.mark.parametrize(
    ("dimension", "expected_top", "expected_label"),
    [
        ("service", ("Suporte::Estação de trabalho", 2), "Serviço"),
        ("type", ("Incidente", 2), "Tipo de chamado"),
        ("queue", ("Suporte::N1", 3), "Fila"),
    ],
)
@pytest.mark.asyncio
async def test_top_dimension_is_switchable(
    engine, app_session_factory, session, dimension, expected_top, expected_label
):
    """S2 — `REPORT_TOP_DIMENSION` troca a dimensão sem tocar em código.

    O `Type` do Znuny costuma ter dois valores e render um gráfico sem conteúdo;
    "tipo de chamado" na boca do operador provavelmente é o catálogo de serviço.
    Como não sabemos, as três dimensões chegam prontas do GI e a chave escolhe.
    """
    t = await _seed(session, contract_type=ContractType.hour_bank)
    async with tenant_session_scope(t.id, factory=app_session_factory) as s:
        admin = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
        async with admin() as meta:
            r = await ReportService(s, _GI(), top_dimension=dimension).monthly(
                t.id, _MONTH, admin_session=meta
            )
    assert r.dimension == dimension
    assert r.dimension_label == expected_label
    assert r.top_items[0] == expected_top


@pytest.mark.asyncio
async def test_unknown_dimension_falls_back_to_service(engine, app_session_factory, session):
    """Chave com valor errado no `.env` não pode derrubar o relatório."""
    t = await _seed(session, contract_type=ContractType.hour_bank)
    async with tenant_session_scope(t.id, factory=app_session_factory) as s:
        admin = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
        async with admin() as meta:
            r = await ReportService(s, _GI(), top_dimension="banana").monthly(
                t.id, _MONTH, admin_session=meta
            )
    assert r.dimension == "service"


# ── degradação e erros ─────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_znuny_down_marks_degraded_instead_of_faking_empty_month(
    engine, app_session_factory, session
):
    """A18b.6 — mês sem dados e mês sem Znuny NÃO podem parecer a mesma coisa.

    O consumo continua vindo (é do nosso banco); o bloco de chamados fica vazio
    **com a marca**. Quem decide o que fazer com isso é o chamador — a rota do
    PDF recusa, a do JSON mostra o aviso.
    """
    t = await _seed(session, contract_type=ContractType.hour_bank)
    async with tenant_session_scope(t.id, factory=app_session_factory) as s:
        admin = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
        async with admin() as meta:
            r = await ReportService(s, _GI(down=True)).monthly(t.id, _MONTH, admin_session=meta)
    assert r.degraded is True
    assert r.tickets == []
    assert r.top_items == []
    assert r.ticket_total == 0
    # O consumo sobrevive: ele não depende do Znuny.
    assert r.consumption[0].value == 5.0


@pytest.mark.asyncio
async def test_truncated_ticket_list_is_flagged(engine, app_session_factory, session):
    """Lista cortada pelo teto do GI é sinalizada; a contagem total segue exata."""
    t = await _seed(session, contract_type=ContractType.hour_bank)
    gi = _GI(_stats(tickets_truncated=True, total=1500))
    async with tenant_session_scope(t.id, factory=app_session_factory) as s:
        admin = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
        async with admin() as meta:
            r = await ReportService(s, gi).monthly(t.id, _MONTH, admin_session=meta)
    assert r.tickets_truncated is True
    assert r.ticket_total == 1500
    assert len(r.tickets) == 3


@pytest.mark.asyncio
async def test_unknown_tenant_raises(engine, app_session_factory, session):
    import uuid as _uuid

    t = await _seed(session, contract_type=ContractType.hour_bank)
    async with tenant_session_scope(t.id, factory=app_session_factory) as s:
        admin = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
        async with admin() as meta:
            with pytest.raises(TenantNotFound):
                await ReportService(s, _GI()).monthly(_uuid.uuid4(), _MONTH, admin_session=meta)


@pytest.mark.asyncio
async def test_invalid_month_never_reaches_the_gi(engine, app_session_factory, session):
    """Mês inválido não pode custar uma ida ao Znuny."""
    t = await _seed(session, contract_type=ContractType.hour_bank)
    gi = _GI()
    async with tenant_session_scope(t.id, factory=app_session_factory) as s:
        admin = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
        async with admin() as meta:
            with pytest.raises(InvalidMonth):
                await ReportService(s, gi).monthly(t.id, "2026-13", admin_session=meta)
    assert gi.calls == []


# ── a listona é opt-in: o painel de analytics não paga a conta do relatório ──


@pytest.mark.asyncio
async def test_report_asks_for_the_ticket_list_explicitly(engine, app_session_factory, session):
    """A mesma op GI alimenta o painel de analytics, que só quer contagens.

    Sem `IncludeTickets`, toda carga do painel passaria a arrastar até mil
    chamados e um `TicketAccountedTimeGet` por chamado. O relatório pede a
    lista de propósito; o painel não pede.
    """
    t = await _seed(session, contract_type=ContractType.hour_bank)

    seen: dict = {}

    class _Recorder:
        async def ticket_stats(self, *, customer_id, since, until, include_tickets=False):
            seen["include_tickets"] = include_tickets
            return _stats()

    async with tenant_session_scope(t.id, factory=app_session_factory) as s:
        admin = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
        async with admin() as meta:
            await ReportService(s, _Recorder()).monthly(t.id, _MONTH, admin_session=meta)

    assert seen["include_tickets"] is True
