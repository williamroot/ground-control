"""Relatório executivo mensal por cliente (T-R18b.3, R18b do vídeo do Kleber).

> *"Tenho um report executivo mensal aqui… vou pegar maio, vou pegar a
> DataStone… isso aqui eu consigo fazer em PDF… para ele saber quanto gastou,
> quanto consumiu, quais foram os principais tipos de ticket. No final, a gente
> põe a listona de chamados."* — 11:36

É o entregável recorrente da Gerti: *"isso aqui, todo mês, a gente manda"*
(10:51). E vale registrar a avaliação dele sobre o original: *"acho um relatório
bem feinho da TIFLUX, mas são os indicadores que a gente mostra para o
cliente"* — paridade de conteúdo é obrigatória, a apresentação deve ser melhor.

## Três decisões que este módulo materializa

**1. Consumo sai na unidade do contrato, uma linha por contrato.** Um cliente
com banco de horas e crédito em reais tem DUAS linhas, nunca uma soma. Somar
horas com reais não é arredondamento, é número errado.

**2. "Principais tipos de chamado" é configurável (suposição S2).** O `Type` do
Znuny costuma ter dois valores; o que o operador chama de "tipo" provavelmente é
o catálogo de serviço. As três dimensões (`service`/`type`/`queue`) chegam
prontas do GI e a chave `REPORT_TOP_DIMENSION` escolhe qual aparece. Nenhuma
delas é constante no meio da regra.

**3. Znuny fora do ar: o JSON degrada, o PDF recusa (aceite A18b.6).** O JSON
alimenta a tela, onde o operador vê o aviso. O PDF é o artefato que sai da
empresa e vai para o cliente — um documento incompleto com cara de completo é
justamente o modo de falha que esta campanha vem combatendo. Regra travada em
teste, não deixada ao acaso.
"""

from __future__ import annotations

import calendar
import datetime as dt
import uuid
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql.elements import ColumnElement

from gerti_sidecar.domain.contract_read_service import not_written_off_predicate
from gerti_sidecar.models import ConsumptionEvent, Contract, Tenant, TenantBranding
from gerti_sidecar.models.enums import ContractStatus, ContractType


class InvalidMonth(ValueError):
    """Mês fora do formato YYYY-MM ou fora de faixa (-> 422)."""


class TenantNotFound(LookupError):
    """Cliente inexistente (-> 404)."""


class TicketDataUnavailable(RuntimeError):
    """O Znuny não respondeu e o documento seria incompleto (-> 503 no PDF)."""


# Rótulo da dimensão escolhida, para o relatório dizer o que está mostrando em
# vez de só cuspir uma tabela sem cabeçalho honesto.
DIMENSION_LABELS = {
    "service": "Serviço",
    "type": "Tipo de chamado",
    "queue": "Fila",
}

_UNIT_LABELS = {"hours": "horas", "brl": "reais", "services": "atendimentos", "n/a": "—"}


def month_range(month: str) -> tuple[dt.date, dt.date]:
    """'2026-05' -> (2026-05-01, 2026-05-31). Recusa qualquer outra coisa.

    Validar aqui, e não no router, faz a regra valer para todo chamador — e o
    `2026-13` do aceite A18b.5 morre antes de virar consulta.
    """
    if not isinstance(month, str) or len(month) != 7 or month[4] != "-":
        raise InvalidMonth(f"mês inválido: {month!r} (esperado YYYY-MM)")
    try:
        year = int(month[:4])
        mon = int(month[5:])
    except ValueError as exc:
        raise InvalidMonth(f"mês inválido: {month!r} (esperado YYYY-MM)") from exc
    if not (1 <= mon <= 12) or not (2000 <= year <= 2100):
        raise InvalidMonth(f"mês inválido: {month!r}")
    last = calendar.monthrange(year, mon)[1]
    return dt.date(year, mon, 1), dt.date(year, mon, last)


_MONTH_NAMES_PT = [
    "janeiro", "fevereiro", "março", "abril", "maio", "junho",
    "julho", "agosto", "setembro", "outubro", "novembro", "dezembro",
]  # fmt: skip


def month_label_pt(month: str) -> str:
    start, _ = month_range(month)
    return f"{_MONTH_NAMES_PT[start.month - 1]}/{start.year}"


@dataclass(slots=True)
class ContractConsumption:
    code: str
    type: str
    kind: str  # hours | brl | services | n/a
    value: float
    unit_label: str


@dataclass(slots=True)
class ReportTicket:
    znuny_ticket_id: int
    ticket_number: str
    title: str
    state: str
    service: str
    type: str
    created: str
    hours: float


@dataclass(slots=True)
class MonthlyReport:
    tenant_id: uuid.UUID
    tenant_name: str
    display_name: str
    month: str
    month_label: str
    period_start: dt.date
    period_end: dt.date
    consumption: list[ContractConsumption]
    dimension: str
    dimension_label: str
    top_items: list[tuple[str, int]]
    tickets: list[ReportTicket]
    ticket_total: int
    tickets_truncated: bool
    # `True` quando o Znuny não respondeu: o bloco de chamados está VAZIO por
    # falha, não por ausência de chamados. A tela mostra o aviso; o PDF recusa.
    degraded: bool = False
    branding: dict[str, Any] = field(default_factory=dict)


class ReportService:
    def __init__(self, session: AsyncSession, gi: Any, *, top_dimension: str = "service") -> None:
        self.session = session
        self._gi = gi
        self._dimension = top_dimension if top_dimension in DIMENSION_LABELS else "service"

    async def monthly(
        self, tenant_id: uuid.UUID, month: str, *, admin_session: AsyncSession | None = None
    ) -> MonthlyReport:
        """Monta o relatório do mês. `session` já é RLS-scoped no tenant.

        `admin_session` (BYPASSRLS) é usada só para ler o cadastro do cliente,
        que vive fora do escopo de RLS do caminho do console.
        """
        start, end = month_range(month)
        meta_session = admin_session or self.session
        tenant = await meta_session.get(Tenant, tenant_id)
        if tenant is None:
            raise TenantNotFound(str(tenant_id))
        branding = await meta_session.get(TenantBranding, tenant_id)

        consumption = await self._consumption(tenant_id, start, end)
        stats, degraded = await self._ticket_stats(tenant.znuny_customer_id, start, end)

        raw_dim: dict[str, int] = {
            "service": stats.by_service if stats else {},
            "type": stats.by_type if stats else {},
            "queue": stats.by_queue if stats else {},
        }[self._dimension]
        top_items = sorted(raw_dim.items(), key=lambda kv: (-kv[1], kv[0]))[:10]

        tickets = [
            ReportTicket(
                znuny_ticket_id=int(t.get("znuny_ticket_id") or 0),
                ticket_number=str(t.get("ticket_number") or ""),
                title=str(t.get("title") or ""),
                state=str(t.get("state") or ""),
                service=str(t.get("service") or ""),
                type=str(t.get("type") or ""),
                created=str(t.get("created") or ""),
                hours=round(float(t.get("accounted_time") or 0) / 60.0, 2),
            )
            for t in (stats.tickets if stats else [])
        ]
        tickets.sort(key=lambda t: t.created)

        return MonthlyReport(
            tenant_id=tenant_id,
            tenant_name=tenant.trade_name,
            display_name=(branding.display_name if branding else tenant.trade_name),
            month=month,
            month_label=month_label_pt(month),
            period_start=start,
            period_end=end,
            consumption=consumption,
            dimension=self._dimension,
            dimension_label=DIMENSION_LABELS[self._dimension],
            top_items=top_items,
            tickets=tickets,
            ticket_total=(stats.total if stats else 0),
            tickets_truncated=bool(stats.tickets_truncated) if stats else False,
            degraded=degraded,
            branding={
                "logo_url": branding.logo_url if branding else None,
                "primary_color": (branding.primary_color if branding else None) or "#334155",
            },
        )

    async def _consumption(
        self, tenant_id: uuid.UUID, start: dt.date, end: dt.date
    ) -> list[ContractConsumption]:
        """Uma linha por contrato ativo, cada uma na SUA unidade.

        Nunca soma tipos diferentes: um cliente com banco de horas e crédito em
        reais recebe duas linhas. A glosa aprovada é excluída (regra S3
        centralizada) — o relatório mostra o que foi cobrado, não o que foi
        lançado.
        """
        contracts = (
            (
                await self.session.execute(
                    # `tenant_id` EXPLÍCITO: o console abre a sessão por
                    # AdminSessionLocal (BYPASSRLS), onde a policy de RLS não
                    # se aplica. Sem isto, o relatório de um cliente listaria os
                    # contratos de outro — e sairia em PDF para o cliente errado.
                    select(Contract)
                    .where(
                        Contract.tenant_id == tenant_id,
                        Contract.status == ContractStatus.active,
                    )
                    .order_by(Contract.code)
                )
            )
            .scalars()
            .all()
        )
        lo = dt.datetime.combine(start, dt.time.min, dt.UTC)
        hi = dt.datetime.combine(end + dt.timedelta(days=1), dt.time.min, dt.UTC)

        out: list[ContractConsumption] = []
        for c in contracts:
            if c.type == ContractType.hour_bank:
                kind = "hours"
            elif c.type in (ContractType.credit_brl, ContractType.credit_shared):
                kind = "brl"
            elif c.type == ContractType.service_count:
                kind = "services"
            else:
                # closed_value / saas_product: não há consumo a medir. Fica fora
                # do bloco em vez de aparecer como 0, que se lê como "não usou".
                continue

            # Agrega no BANCO, não na memória: um mês movimentado pode ter
            # milhares de eventos, e trazê-los todos para somar em Python é
            # pagar rede e RAM por um número só.
            extra: list[ColumnElement[bool]] = []
            value_expr: ColumnElement[Any]
            if kind == "hours":
                value_expr = func.coalesce(func.sum(ConsumptionEvent.billable_minutes), 0) / 60.0
            elif kind == "brl":
                value_expr = func.coalesce(func.sum(ConsumptionEvent.billable_amount_brl), 0)
            else:
                value_expr = func.count()
                extra = [ConsumptionEvent.source_kind == "service_item"]

            raw = await self.session.scalar(
                select(value_expr).where(
                    ConsumptionEvent.contract_id == c.id,
                    ConsumptionEvent.occurred_at >= lo,
                    ConsumptionEvent.occurred_at < hi,
                    not_written_off_predicate(),
                    *extra,
                )
            )
            value = round(float(raw or 0.0), 2)

            out.append(
                ContractConsumption(
                    code=c.code,
                    type=c.type.value,
                    kind=kind,
                    value=value,
                    unit_label=_UNIT_LABELS[kind],
                )
            )
        return out

    async def _ticket_stats(
        self, customer_id: str, start: dt.date, end: dt.date
    ) -> tuple[Any | None, bool]:
        since = f"{start.isoformat()} 00:00:00"
        until = f"{end.isoformat()} 23:59:59"
        try:
            stats = await self._gi.ticket_stats(
                customer_id=customer_id,
                since=since,
                until=until,
                # Opt-in explícito: o painel de analytics usa a MESMA op e não
                # pode passar a arrastar a listona a cada carga.
                include_tickets=True,
            )
        except Exception:
            # Failure-soft aqui, por desenho: quem decide o que fazer com a
            # degradação é o chamador — o JSON mostra o aviso, o PDF recusa.
            return None, True
        return stats, False
