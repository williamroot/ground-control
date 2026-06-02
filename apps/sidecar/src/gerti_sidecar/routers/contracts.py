"""GET /v1/contracts — autenticado, tenant da sessão, saldo via #1C."""

from __future__ import annotations

import datetime as dt
import uuid

from fastapi import APIRouter, Depends, HTTPException, Path, Query
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from gerti_sidecar.auth.session import SessionPayload, get_current_session
from gerti_sidecar.db import get_tenant_session
from gerti_sidecar.domain.consumption_service import ConsumptionService
from gerti_sidecar.domain.contract_read_service import consumed_percent_from
from gerti_sidecar.models import (
    ConsumptionEvent,
    Contract,
    ContractAdjustmentRule,
    ContractBillingParty,
    ContractCycle,
    ContractRenewalPolicy,
    Glosa,
)
from gerti_sidecar.models.enums import GlosaStatus

router = APIRouter(prefix="/contracts", tags=["portal"])


class Saldo(BaseModel):
    kind: str
    remaining: float | None


class ContractItem(BaseModel):
    code: str
    type: str
    status: str
    starts_on: dt.date
    ends_on: dt.date
    saldo: Saldo
    id: uuid.UUID
    consumed_percent: float | None


class CycleItem(BaseModel):
    id: uuid.UUID
    kind: str
    period_start: dt.date
    period_end: dt.date
    status: str
    closed_at: dt.datetime | None
    totals: dict[str, object] | None


class AdjustmentRuleOut(BaseModel):
    index_code: str
    cadence_months: int
    next_run_on: dt.date
    cap_percent: float | None
    last_applied_on: dt.date | None
    last_applied_percent: float | None


class RenewalPolicyOut(BaseModel):
    auto_renew: bool
    notice_days: int
    next_review_on: dt.date
    renewal_term_months: int | None


class BillingPartyOut(BaseModel):
    legal_name: str
    document: str
    fiscal_address: dict[str, object]
    payment_method: str | None


class ContractDetail(BaseModel):
    id: uuid.UUID
    code: str
    type: str
    status: str
    starts_on: dt.date
    ends_on: dt.date
    initial_amount_brl: float | None
    initial_hours: float | None
    initial_service_count: int | None
    unit_price_brl: float | None
    travel_franchise_count: int
    billing_period_months: int
    closing_period_months: int
    billing_in_advance: bool
    accumulate_balance_between_cycles: bool
    saldo: Saldo
    consumed_percent: float | None
    cycles: list[CycleItem]
    adjustment_rule: AdjustmentRuleOut | None
    renewal_policy: RenewalPolicyOut | None
    billing_parties: list[BillingPartyOut]


@router.get("", response_model=list[ContractItem])
async def list_contracts(
    _session_payload: SessionPayload = Depends(get_current_session),
    session: AsyncSession = Depends(get_tenant_session),
) -> list[ContractItem]:
    contracts = (await session.execute(select(Contract).order_by(Contract.code))).scalars().all()
    cons = ConsumptionService(session)
    out: list[ContractItem] = []
    for c in contracts:
        bal = await cons.balance(c.id)
        out.append(
            ContractItem(
                id=c.id,
                code=c.code,
                type=c.type.value,
                status=c.status.value,
                starts_on=c.starts_on,
                ends_on=c.ends_on,
                saldo=Saldo(kind=bal.kind, remaining=bal.remaining),
                consumed_percent=consumed_percent_from(c, bal),
            )
        )
    return out


@router.get("/{contract_id}", response_model=ContractDetail)
async def get_contract(
    contract_id: uuid.UUID = Path(...),
    _session_payload: SessionPayload = Depends(get_current_session),
    session: AsyncSession = Depends(get_tenant_session),
) -> ContractDetail:
    c = await session.get(Contract, contract_id)
    if c is None:  # RLS hid a cross-tenant row -> 404, never 403/500 (H2)
        raise HTTPException(status_code=404, detail="contract_not_found")
    bal = await ConsumptionService(session).balance(c.id)
    cycles = (
        (
            await session.execute(
                select(ContractCycle)
                .where(ContractCycle.contract_id == c.id)
                .order_by(ContractCycle.period_start.asc())
            )
        )
        .scalars()
        .all()
    )
    rule = await session.get(ContractAdjustmentRule, c.id)
    policy = await session.get(ContractRenewalPolicy, c.id)
    parties = (
        (
            await session.execute(
                select(ContractBillingParty).where(ContractBillingParty.contract_id == c.id)
            )
        )
        .scalars()
        .all()
    )
    return ContractDetail(
        id=c.id,
        code=c.code,
        type=c.type.value,
        status=c.status.value,
        starts_on=c.starts_on,
        ends_on=c.ends_on,
        initial_amount_brl=(
            float(c.initial_amount_brl) if c.initial_amount_brl is not None else None
        ),
        initial_hours=float(c.initial_hours) if c.initial_hours is not None else None,
        initial_service_count=c.initial_service_count,
        unit_price_brl=float(c.unit_price_brl) if c.unit_price_brl is not None else None,
        travel_franchise_count=c.travel_franchise_count,
        billing_period_months=c.billing_period_months,
        closing_period_months=c.closing_period_months,
        billing_in_advance=c.billing_in_advance,
        accumulate_balance_between_cycles=c.accumulate_balance_between_cycles,
        saldo=Saldo(kind=bal.kind, remaining=bal.remaining),
        consumed_percent=consumed_percent_from(c, bal),
        cycles=[
            CycleItem(
                id=cy.id,
                kind=cy.kind.value,
                period_start=cy.period_start,
                period_end=cy.period_end,
                status=cy.status.value,
                closed_at=cy.closed_at,
                totals=cy.totals,
            )
            for cy in cycles
        ],
        adjustment_rule=(
            AdjustmentRuleOut(
                index_code=rule.index_code,
                cadence_months=rule.cadence_months,
                next_run_on=rule.next_run_on,
                cap_percent=float(rule.cap_percent) if rule.cap_percent is not None else None,
                last_applied_on=rule.last_applied_on,
                last_applied_percent=(
                    float(rule.last_applied_percent)
                    if rule.last_applied_percent is not None
                    else None
                ),
            )
            if rule is not None
            else None
        ),
        renewal_policy=(
            RenewalPolicyOut(
                auto_renew=policy.auto_renew,
                notice_days=policy.notice_days,
                next_review_on=policy.next_review_on,
                renewal_term_months=policy.renewal_term_months,
            )
            if policy is not None
            else None
        ),
        billing_parties=[
            BillingPartyOut(
                legal_name=p.legal_name,
                document=p.document,
                fiscal_address=p.fiscal_address,
                payment_method=p.payment_method,
            )
            for p in parties
        ],
    )


class GlosaOut(BaseModel):
    status: str


class ConsumptionItem(BaseModel):
    id: int
    occurred_at: dt.datetime
    source_kind: str
    source_ref: str
    billable_minutes: float
    billable_amount_brl: float
    glosa: GlosaOut | None
    counts_toward_balance: bool


class ConsumptionPage(BaseModel):
    page: int
    page_size: int
    total: int
    items: list[ConsumptionItem]


@router.get("/{contract_id}/consumption", response_model=ConsumptionPage)
async def get_consumption(
    contract_id: uuid.UUID = Path(...),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1),  # over-max clamped to 200 in-body (H4), not 422
    _session_payload: SessionPayload = Depends(get_current_session),
    session: AsyncSession = Depends(get_tenant_session),
) -> ConsumptionPage:
    c = await session.get(Contract, contract_id)
    if c is None:  # RLS hid cross-tenant -> 404 (H2)
        raise HTTPException(status_code=404, detail="contract_not_found")
    page = max(1, page)
    page_size = min(max(1, page_size), 200)  # clamp (H4)
    total = (
        await session.scalar(
            select(func.count())
            .select_from(ConsumptionEvent)
            .where(ConsumptionEvent.contract_id == c.id)
        )
        or 0
    )
    # LEFT OUTER JOIN Glosa (glosa_id has no FK — H13); status read-only.
    rows = (
        await session.execute(
            select(ConsumptionEvent, Glosa.status)
            .outerjoin(Glosa, Glosa.id == ConsumptionEvent.glosa_id)
            .where(ConsumptionEvent.contract_id == c.id)
            .order_by(ConsumptionEvent.occurred_at.desc(), ConsumptionEvent.id.desc())
            .limit(page_size)
            .offset((page - 1) * page_size)
        )
    ).all()
    items: list[ConsumptionItem] = []
    for ev, glosa_status in rows:
        counts = glosa_status is None or glosa_status != GlosaStatus.approved
        items.append(
            ConsumptionItem(
                id=ev.id,
                occurred_at=ev.occurred_at,
                source_kind=ev.source_kind,
                source_ref=ev.source_ref,
                billable_minutes=float(ev.billable_minutes),
                billable_amount_brl=float(ev.billable_amount_brl),
                glosa=GlosaOut(status=glosa_status.value) if glosa_status is not None else None,
                counts_toward_balance=counts,
            )
        )
    return ConsumptionPage(page=page, page_size=page_size, total=int(total), items=items)
