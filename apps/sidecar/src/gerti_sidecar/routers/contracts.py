"""GET /v1/contracts — autenticado, tenant da sessão, saldo via #1C."""

from __future__ import annotations

import datetime as dt
import uuid

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from gerti_sidecar.auth.session import SessionPayload, get_current_session
from gerti_sidecar.db import get_tenant_session
from gerti_sidecar.domain.consumption_service import ConsumptionService
from gerti_sidecar.domain.contract_read_service import consumed_percent_from
from gerti_sidecar.models import Contract

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
