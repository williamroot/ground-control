"""/v1/admin/tenants/{id}/billing-config — R6, e /approvals — R7 (Onda 5).

**R6:** *"aqui eu configuro se manda e-mail, se manda SMS, para quem vai a
cobrança"* (05:20). Defaults seguros: tudo desligado. Ligar aviso automático é
decisão do cliente, não estado herdado de um default nosso — e no SMS isso tem
custo por mensagem.

**R7:** a fila de aprovação e a chave que a liga por cliente.

`tenant_id` explícito em toda consulta: a sessão do console é BYPASSRLS e a
policy não se aplica. Lição da Onda 3.
"""

from __future__ import annotations

import re
import uuid

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select

from gerti_sidecar import db
from gerti_sidecar.auth.admin_session import AdminSessionPayload, get_admin_session
from gerti_sidecar.domain import audit_service
from gerti_sidecar.models import Tenant, TenantBillingConfig, TicketApproval

router = APIRouter(prefix="/admin/tenants", tags=["admin"])

_EMAIL_RE = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")


class BillingConfigIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    email_enabled: bool = False
    sms_enabled: bool = False
    billing_email: str | None = Field(default=None, max_length=255)
    billing_phone: str | None = Field(default=None, max_length=32)
    # Teto em 28 de propósito: 29-31 não existem em todo mês, e "dia 31"
    # viraria a mesma armadilha que a agenda recorrente teve que tratar.
    billing_day: int | None = Field(default=None, ge=1, le=28)
    notes: str | None = Field(default=None, max_length=2000)
    approval_required: bool = False


class BillingConfigOut(BaseModel):
    email_enabled: bool
    sms_enabled: bool
    billing_email: str | None
    billing_phone: str | None
    billing_day: int | None
    notes: str | None
    approval_required: bool
    # `true` quando o SMS está ligado mas o provedor real ainda não existe. A
    # tela DIZ isso: "modo simulado" precisa estar na cara, senão alguém confia
    # num aviso que nunca sai.
    sms_simulated: bool


class ApprovalOut(BaseModel):
    znuny_ticket_id: int
    status: str
    requested_by: str
    approver_login: str | None
    reason: str | None
    created_at: str


def _tid(tenant_id: str) -> uuid.UUID:
    try:
        return uuid.UUID(tenant_id)
    except (ValueError, AttributeError):
        raise HTTPException(status_code=404, detail="tenant_not_found") from None


def _require_db() -> None:
    if db.AdminSessionLocal is None:
        raise HTTPException(status_code=503, detail="admin_db_unavailable")


def _sms_simulated() -> bool:
    import os

    return os.environ.get("SMS_PROVIDER", "console").strip().lower() == "console"


@router.get("/{tenant_id}/billing-config")
async def get_billing_config(
    tenant_id: str,
    admin: AdminSessionPayload = Depends(get_admin_session),
) -> BillingConfigOut:
    _require_db()
    assert db.AdminSessionLocal is not None
    tid = _tid(tenant_id)
    async with db.AdminSessionLocal() as s:
        tenant = await s.get(Tenant, tid)
        if tenant is None:
            raise HTTPException(status_code=404, detail="tenant_not_found")
        cfg = await s.get(TenantBillingConfig, tid)
    return BillingConfigOut(
        email_enabled=bool(cfg.email_enabled) if cfg else False,
        sms_enabled=bool(cfg.sms_enabled) if cfg else False,
        billing_email=cfg.billing_email if cfg else None,
        billing_phone=cfg.billing_phone if cfg else None,
        billing_day=cfg.billing_day if cfg else None,
        notes=cfg.notes if cfg else None,
        approval_required=tenant.approval_required,
        sms_simulated=_sms_simulated(),
    )


@router.put("/{tenant_id}/billing-config")
async def put_billing_config(
    tenant_id: str,
    body: BillingConfigIn,
    request: Request,
    admin: AdminSessionPayload = Depends(get_admin_session),
) -> BillingConfigOut:
    _require_db()
    assert db.AdminSessionLocal is not None
    tid = _tid(tenant_id)

    email = (body.billing_email or "").strip()
    if email and not _EMAIL_RE.match(email):
        raise HTTPException(status_code=422, detail="e-mail de cobrança inválido")
    # Ligar o aviso sem ter para onde mandar é configuração que parece feita e
    # não é. Recusamos em vez de deixar a fatura sair sem aviso, em silêncio.
    if body.email_enabled and not email:
        raise HTTPException(
            status_code=422, detail="informe o e-mail de cobrança para ativar o aviso por e-mail"
        )
    phone = (body.billing_phone or "").strip()
    if body.sms_enabled and not phone:
        raise HTTPException(
            status_code=422, detail="informe o telefone para ativar o aviso por SMS"
        )

    async with db.AdminSessionLocal() as s:
        async with s.begin():
            tenant = await s.get(Tenant, tid)
            if tenant is None:
                raise HTTPException(status_code=404, detail="tenant_not_found")
            cfg = await s.get(TenantBillingConfig, tid)
            if cfg is None:
                cfg = TenantBillingConfig(tenant_id=tid)
                s.add(cfg)
            cfg.email_enabled = body.email_enabled
            cfg.sms_enabled = body.sms_enabled
            cfg.billing_email = email or None
            cfg.billing_phone = phone or None
            cfg.billing_day = body.billing_day
            cfg.notes = body.notes
            cfg.updated_by = admin["agent_login"]
            tenant.approval_required = body.approval_required

    await audit_service.record(
        actor_type="agent",
        actor_login=admin["agent_login"],
        tenant_id=tid,
        action="update",
        entity="tenant_billing_config",
        entity_id=str(tid),
        description="configuração de faturamento alterada",
        ip=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
        metadata={
            "email_enabled": body.email_enabled,
            "sms_enabled": body.sms_enabled,
            "billing_day": body.billing_day,
            "approval_required": body.approval_required,
        },
    )
    return await get_billing_config(tenant_id, admin)


@router.get("/{tenant_id}/approvals")
async def list_approvals(
    tenant_id: str,
    status: str | None = None,
    admin: AdminSessionPayload = Depends(get_admin_session),
) -> list[ApprovalOut]:
    """Chamados esperando decisão, para o console acompanhar (R7)."""
    _require_db()
    assert db.AdminSessionLocal is not None
    tid = _tid(tenant_id)
    async with db.AdminSessionLocal() as s:
        if await s.get(Tenant, tid) is None:
            raise HTTPException(status_code=404, detail="tenant_not_found")
        stmt = select(TicketApproval).where(TicketApproval.tenant_id == tid)
        if status:
            stmt = stmt.where(TicketApproval.status == status)
        rows = (await s.execute(stmt.order_by(TicketApproval.created_at.desc()))).scalars().all()
    return [
        ApprovalOut(
            znuny_ticket_id=r.znuny_ticket_id,
            status=r.status,
            requested_by=r.requested_by,
            approver_login=r.approver_login,
            reason=r.reason,
            created_at=r.created_at.isoformat(),
        )
        for r in rows
    ]
