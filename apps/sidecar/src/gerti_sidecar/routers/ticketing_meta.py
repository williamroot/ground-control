# apps/sidecar/src/gerti_sidecar/routers/ticketing_meta.py
"""Catálogo para o formulário de abertura (Spec #1E) — NÃO-admin.

/v1/ticketing/contracts: contratos ATIVOS selecionáveis (qualquer papel logado).
Diferente de /v1/contracts (#1F-b, require_admin): aqui devolve só o necessário
ao dropdown, sob RLS por tenant. /v1/ticketing/form-meta: serviços/prioridades/
tipos do Znuny via GI.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from gerti_sidecar.auth.session import SessionPayload, get_current_session
from gerti_sidecar.db import get_tenant_session
from gerti_sidecar.domain.consumption_service import ConsumptionService
from gerti_sidecar.integrations import znuny_ticket
from gerti_sidecar.integrations.znuny_customer_admin import ZnunyUnavailable, ZnunyWriteError
from gerti_sidecar.models import Contract
from gerti_sidecar.models.enums import ContractStatus

router = APIRouter(prefix="/ticketing", tags=["ticketing"])


class SelectableContract(BaseModel):
    id: uuid.UUID
    code: str
    type: str
    saldo_label: str | None


@router.get("/contracts", response_model=list[SelectableContract])
async def selectable_contracts(
    _session: SessionPayload = Depends(get_current_session),
    session: AsyncSession = Depends(get_tenant_session),
) -> list[SelectableContract]:
    rows = await session.execute(
        select(Contract).where(Contract.status == ContractStatus.active).order_by(Contract.code)
    )
    cons = ConsumptionService(session)
    out: list[SelectableContract] = []
    for contract in rows.scalars().all():
        bal = await cons.balance(contract.id)
        label = None if bal.remaining is None else f"{bal.kind} {bal.remaining:g}"
        out.append(
            SelectableContract(
                id=contract.id,
                code=contract.code,
                type=str(contract.type.value),
                saldo_label=label,
            )
        )
    return out


class FormMeta(BaseModel):
    services: list[dict[str, object]]
    priorities: list[dict[str, object]]
    types: list[dict[str, object]]


@router.get("/form-meta", response_model=FormMeta)
async def form_meta(
    session_payload: SessionPayload = Depends(get_current_session),
) -> FormMeta:
    try:
        meta = await znuny_ticket.form_meta(customer_user=session_payload["customer_login"])
    except ZnunyUnavailable as exc:
        raise HTTPException(status_code=503, detail="znuny_unavailable") from exc
    except ZnunyWriteError as exc:
        raise HTTPException(status_code=502, detail="znuny_form_meta_error") from exc
    return FormMeta(
        services=meta["services"],
        priorities=meta["priorities"],
        types=meta["types"],
    )
