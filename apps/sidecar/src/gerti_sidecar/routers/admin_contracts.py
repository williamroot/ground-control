"""POST /v1/admin/tenants/{id}/contracts — cria contrato (6 tipos) p/ um tenant.

Spec #1G-a / ADR D19. Exige `get_admin_session`. O corpo (T1.D) abre
`tenant_session_scope(tenant_id)` (RLS-subject) e usa `ContractService.create`,
preservando TODAS as invariantes #1C. Contrato Pydantic CONGELADO na Fase 0.
"""

from __future__ import annotations

import datetime as dt
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from gerti_sidecar.auth.admin_session import AdminSessionPayload, get_admin_session

router = APIRouter(prefix="/admin/tenants", tags=["admin"])

ContractTypeIn = Literal[
    "credit_brl",
    "credit_shared",
    "hour_bank",
    "service_count",
    "closed_value",
    "saas_product",
]


class NewContractBody(BaseModel):
    code: str
    type: ContractTypeIn
    starts_on: dt.date
    ends_on: dt.date
    initial_amount_brl: float | None = None
    initial_hours: float | None = None
    initial_service_count: int | None = None
    unit_price_brl: float | None = None
    travel_franchise_count: int = 0
    billing_period_months: int = 1
    closing_period_months: int = 1
    billing_in_advance: bool = True
    accumulate_balance_between_cycles: bool = False


class ContractOut(BaseModel):
    id: str
    code: str
    type: str
    status: str
    starts_on: dt.date
    ends_on: dt.date


@router.post("/{tenant_id}/contracts", status_code=201)
async def create_contract(
    tenant_id: str,
    body: NewContractBody,
    admin: AdminSessionPayload = Depends(get_admin_session),
) -> ContractOut:
    raise HTTPException(status_code=501, detail="not_implemented")  # T1.D
