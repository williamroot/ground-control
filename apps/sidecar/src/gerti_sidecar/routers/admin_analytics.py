"""GET /v1/admin/analytics?tenant_id= (Spec #1O) — console (agente), cross-tenant.

Sob get_admin_session (gsid_adm). Resolve o tenant + customer_id via
AdminSessionLocal (BYPASSRLS, D16), depois abre tenant_session_scope(tenant_id,
factory=AdminSessionLocal): o agente é cross-tenant (BYPASSRLS), mas passamos o
GUC app.current_tenant para reusar a MESMA agregação tenant-scoped do portal sem
vazamento cross-tenant. tenant_id inválido/desconhecido -> 404.
"""

from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException

from gerti_sidecar import db
from gerti_sidecar.auth.admin_session import AdminSessionPayload, get_admin_session
from gerti_sidecar.domain.metrics_service import MetricsService
from gerti_sidecar.integrations import znuny_ticket
from gerti_sidecar.models import Tenant

router = APIRouter(prefix="/admin", tags=["admin"])


def _period_days(period: str) -> int:
    table = {"30d": 30, "90d": 90}
    return table.get(period, 30)


@router.get("/analytics")
async def get_admin_analytics(
    tenant_id: str,
    period: str = "30d",
    admin: AdminSessionPayload = Depends(get_admin_session),
) -> dict[str, Any]:
    if db.AdminSessionLocal is None:
        raise HTTPException(status_code=503, detail="admin_db_unavailable")
    try:
        tid = uuid.UUID(tenant_id)
    except (ValueError, AttributeError):
        raise HTTPException(status_code=404, detail="tenant_not_found") from None

    async with db.AdminSessionLocal() as s:
        tenant = await s.get(Tenant, tid)
        if tenant is None:
            raise HTTPException(status_code=404, detail="tenant_not_found")
        customer_id = tenant.znuny_customer_id

    async with db.tenant_session_scope(tid, factory=db.AdminSessionLocal) as scoped:
        svc = MetricsService(scoped, znuny_ticket)
        return await svc.tenant_metrics(
            tenant_id=tid,
            customer_id=customer_id,
            period_days=_period_days(period),
        )
