"""GET /v1/admin/analytics?tenant_id= (Spec #1O) — console (agente), cross-tenant.

Sob get_admin_session (gsid_adm). Resolve o tenant + customer_id via
AdminSessionLocal (BYPASSRLS, D16), depois abre tenant_session_scope(tenant_id,
factory=AdminSessionLocal): o agente é cross-tenant (BYPASSRLS), mas passamos o
GUC app.current_tenant para reusar a MESMA agregação tenant-scoped do portal sem
vazamento cross-tenant. tenant_id inválido/desconhecido -> 404.
"""

from __future__ import annotations

import datetime as dt
import uuid
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select

from gerti_sidecar import db
from gerti_sidecar.auth.admin_session import AdminSessionPayload, get_admin_session
from gerti_sidecar.config import get_settings
from gerti_sidecar.domain.contract_read_service import ContractReadService
from gerti_sidecar.domain.metrics_service import MetricsService
from gerti_sidecar.integrations import znuny_ticket
from gerti_sidecar.models import Contract, Tenant
from gerti_sidecar.models.enums import ContractStatus

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


# ── R18a — consumo por cliente no console (T-R18a.2) ────────────────────────
#
# *"Se eu quero saber qual o consumo de cada cliente, eu venho aqui e pego esse
# cara e vejo nos últimos três meses qual foi o ciclo de utilização dele."*
# (11:00)
#
# A série já existia — mas no PORTAL, sob o cookie do CLIENTE, contrato a
# contrato, e cobrindo a vida inteira. O Kleber é agente da Gerti: para ver o
# consumo de um cliente ele teria que entrar no portal daquele cliente. Esta
# rota é a mesma leitura, na superfície certa e com a janela certa.


class SeriesPointOut(BaseModel):
    bucket: dt.date
    value: float


class ContractSeriesOut(BaseModel):
    contract_id: str
    code: str
    type: str
    # hours | brl | services — a UNIDADE, que nunca pode ser misturada entre
    # contratos no mesmo gráfico (aceite A18a.2).
    kind: str
    points: list[SeriesPointOut]


class ConsumptionSeriesOut(BaseModel):
    tenant_id: str
    window: str  # cycles | months
    count: int
    series: list[ContractSeriesOut]


@router.get("/tenants/{tenant_id}/consumption-series")
async def get_tenant_consumption_series(
    tenant_id: str,
    window: Literal["cycles", "months"] | None = None,
    count: int | None = None,
    admin: AdminSessionPayload = Depends(get_admin_session),
) -> ConsumptionSeriesOut:
    """Uma série por contrato ativo, cada uma na unidade do seu contrato.

    `window`/`count` são de propósito parâmetros de requisição, e não só
    configuração: "últimos três meses" pode ser mês-calendário ou ciclo de
    faturamento (suposição S3), e deixar o operador escolher na tela é melhor
    do que acertar por sorte. O default vem de `CONSUMPTION_WINDOW_MODE`.
    """
    if db.AdminSessionLocal is None:
        raise HTTPException(status_code=503, detail="admin_db_unavailable")
    try:
        tid = uuid.UUID(tenant_id)
    except (ValueError, AttributeError):
        raise HTTPException(status_code=404, detail="tenant_not_found") from None

    settings = get_settings()
    mode = window or settings.consumption_window_mode
    n = count or settings.consumption_window_count

    async with db.AdminSessionLocal() as s:
        if await s.get(Tenant, tid) is None:
            raise HTTPException(status_code=404, detail="tenant_not_found")

    out: list[ContractSeriesOut] = []
    async with db.tenant_session_scope(tid, factory=db.AdminSessionLocal) as scoped:
        svc = ContractReadService(scoped)
        contracts = (
            (
                await scoped.execute(
                    select(Contract)
                    .where(Contract.status == ContractStatus.active)
                    .order_by(Contract.code)
                )
            )
            .scalars()
            .all()
        )
        for c in contracts:
            series = await svc.series(c, window=mode, count=n)
            if series.kind == "n/a":
                # Contrato sem saldo não vira gráfico vazio enganoso (A18a.4).
                continue
            out.append(
                ContractSeriesOut(
                    contract_id=str(c.id),
                    code=c.code,
                    type=c.type.value,
                    kind=series.kind,
                    points=[SeriesPointOut(bucket=p.bucket, value=p.value) for p in series.points],
                )
            )

    return ConsumptionSeriesOut(tenant_id=str(tid), window=mode, count=n, series=out)
