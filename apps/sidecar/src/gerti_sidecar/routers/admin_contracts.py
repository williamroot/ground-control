"""POST /v1/admin/tenants/{id}/contracts — cria contrato (6 tipos) p/ um tenant.

Spec #1G-a / ADR D19. Exige `get_admin_session`. O corpo (T1.D) abre
`tenant_session_scope(tenant_id)` (RLS-subject) e usa `ContractService.create`,
preservando TODAS as invariantes #1C. Contrato Pydantic CONGELADO na Fase 0.
"""

from __future__ import annotations

import datetime as dt
import uuid
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select

from gerti_sidecar import db
from gerti_sidecar.auth.admin_session import AdminSessionPayload, get_admin_session
from gerti_sidecar.db import tenant_session_scope
from gerti_sidecar.domain.contract_service import ContractService, NewContract
from gerti_sidecar.domain.errors import ContractValidationError
from gerti_sidecar.models import Tenant
from gerti_sidecar.models.enums import ContractType

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
    """Cria um contrato (1 dos 6 tipos) para `tenant_id` via ContractService.

    1. valida o UUID e a EXISTÊNCIA do tenant (lookup cross-tenant via
       AdminSessionLocal/BYPASSRLS) → 404 `tenant_not_found`;
    2. abre `tenant_session_scope` (papel RLS-subject) e delega ao
       ContractService — todas as invariantes #1C são preservadas;
    3. 400 em ContractValidationError; 201 + ContractOut no sucesso.
    """
    try:
        tenant_uuid = uuid.UUID(tenant_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail="tenant_not_found") from exc

    # Existência do tenant: lookup cross-tenant (BYPASSRLS) na sessão admin.
    if db.AdminSessionLocal is None:
        raise RuntimeError("AdminSessionLocal não inicializado — chame init_db()")
    async with db.AdminSessionLocal() as admin_session:
        found = await admin_session.execute(select(Tenant.id).where(Tenant.id == tenant_uuid))
        if found.first() is None:
            raise HTTPException(status_code=404, detail="tenant_not_found")

    new = NewContract(
        code=body.code,
        type=ContractType(body.type),
        starts_on=body.starts_on,
        ends_on=body.ends_on,
        created_by=admin["agent_login"],
        initial_amount_brl=body.initial_amount_brl,
        initial_hours=body.initial_hours,
        initial_service_count=body.initial_service_count,
        unit_price_brl=body.unit_price_brl,
        travel_franchise_count=body.travel_franchise_count,
        billing_period_months=body.billing_period_months,
        closing_period_months=body.closing_period_months,
        billing_in_advance=body.billing_in_advance,
        accumulate_balance_between_cycles=body.accumulate_balance_between_cycles,
    )

    # Escrita sob o papel RLS-subject, com app.current_tenant = tenant_uuid.
    async with tenant_session_scope(tenant_uuid) as session:
        try:
            contract = await ContractService(session).create(new)
        except ContractValidationError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return ContractOut(
            id=str(contract.id),
            code=contract.code,
            type=str(contract.type),
            status=str(contract.status),
            starts_on=contract.starts_on,
            ends_on=contract.ends_on,
        )
