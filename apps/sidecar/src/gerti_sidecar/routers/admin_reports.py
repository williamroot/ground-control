"""/v1/admin/tenants/{id}/reports/* — relatório executivo mensal (T-R18b.4, R18b).

*"Tenho um report executivo mensal aqui… vou pegar maio, vou pegar a
DataStone… isso aqui eu consigo fazer em PDF."* (11:36)

Duas superfícies para o mesmo relatório, e a diferença entre elas é a decisão
do aceite A18b.6:

  • `GET .../reports/monthly?month=YYYY-MM` → JSON, **degrada** quando o Znuny
    está fora: devolve 200 com `degraded: true` e o bloco de chamados vazio. É
    o que alimenta a tela, onde o operador vê o aviso na cara.
  • `GET .../reports/monthly.pdf?month=YYYY-MM` → PDF, **recusa** (503) no mesmo
    cenário. Este é o artefato que sai da empresa e vai para o cliente; um
    documento incompleto com cara de completo é exatamente o modo de falha que
    esta campanha vem combatendo desde a Onda 0.

Ambos sob `get_admin_session` (401 sem sessão de agente). Padrão D16: valida o
tenant com `AdminSessionLocal` (BYPASSRLS) e depois abre
`tenant_session_scope(...)` para que a leitura de consumo passe pelo mesmo
caminho RLS-scoped do portal — o agente é cross-tenant, mas a consulta não.
"""

from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Response

from gerti_sidecar import db
from gerti_sidecar.auth.admin_session import AdminSessionPayload, get_admin_session
from gerti_sidecar.config import get_settings
from gerti_sidecar.domain.report_pdf import render_report_pdf
from gerti_sidecar.domain.report_service import (
    InvalidMonth,
    MonthlyReport,
    ReportService,
    TenantNotFound,
)
from gerti_sidecar.integrations import znuny_ticket
from gerti_sidecar.models import Tenant

router = APIRouter(prefix="/admin/tenants", tags=["admin"])


def _tenant_uuid(tenant_id: str) -> uuid.UUID:
    try:
        return uuid.UUID(tenant_id)
    except (ValueError, AttributeError):
        raise HTTPException(status_code=404, detail="tenant_not_found") from None


async def _build(tenant_id: str, month: str) -> MonthlyReport:
    if db.AdminSessionLocal is None:
        raise HTTPException(status_code=503, detail="admin_db_unavailable")
    tid = _tenant_uuid(tenant_id)

    async with db.AdminSessionLocal() as admin_s:
        if await admin_s.get(Tenant, tid) is None:
            raise HTTPException(status_code=404, detail="tenant_not_found")

    settings = get_settings()
    async with db.AdminSessionLocal() as meta_s:
        async with db.tenant_session_scope(tid, factory=db.AdminSessionLocal) as scoped:
            svc = ReportService(scoped, znuny_ticket, top_dimension=settings.report_top_dimension)
            try:
                return await svc.monthly(tid, month, admin_session=meta_s)
            except InvalidMonth as exc:
                raise HTTPException(status_code=422, detail=str(exc)) from exc
            except TenantNotFound as exc:
                raise HTTPException(status_code=404, detail="tenant_not_found") from exc


def _as_dict(r: MonthlyReport) -> dict[str, Any]:
    return {
        "tenant_id": str(r.tenant_id),
        "tenant_name": r.tenant_name,
        "display_name": r.display_name,
        "month": r.month,
        "month_label": r.month_label,
        "period_start": r.period_start.isoformat(),
        "period_end": r.period_end.isoformat(),
        "consumption": [
            {
                "code": c.code,
                "type": c.type,
                "kind": c.kind,
                "value": c.value,
                "unit_label": c.unit_label,
            }
            for c in r.consumption
        ],
        "dimension": r.dimension,
        "dimension_label": r.dimension_label,
        "top_items": [{"label": label, "count": count} for label, count in r.top_items],
        "tickets": [
            {
                "znuny_ticket_id": t.znuny_ticket_id,
                "ticket_number": t.ticket_number,
                "title": t.title,
                "state": t.state,
                "service": t.service,
                "type": t.type,
                "created": t.created,
                "hours": t.hours,
            }
            for t in r.tickets
        ],
        "ticket_total": r.ticket_total,
        "tickets_truncated": r.tickets_truncated,
        "degraded": r.degraded,
    }


@router.get("/{tenant_id}/reports/monthly")
async def monthly_report(
    tenant_id: str,
    month: str,
    admin: AdminSessionPayload = Depends(get_admin_session),
) -> dict[str, Any]:
    """Relatório do mês em JSON. Degrada com aviso se o Znuny estiver fora."""
    return _as_dict(await _build(tenant_id, month))


@router.get(
    "/{tenant_id}/reports/monthly.pdf",
    responses={200: {"content": {"application/pdf": {}}}},
)
async def monthly_report_pdf(
    tenant_id: str,
    month: str,
    admin: AdminSessionPayload = Depends(get_admin_session),
) -> Response:
    """O mesmo relatório em PDF. **Recusa** documento incompleto (A18b.6)."""
    report = await _build(tenant_id, month)
    if report.degraded:
        raise HTTPException(
            status_code=503,
            detail=(
                "não foi possível ler os chamados no Znuny; o PDF não é gerado "
                "incompleto — tente novamente em instantes"
            ),
        )
    pdf = render_report_pdf(report)
    filename = f"relatorio-{report.month}-{report.tenant_name}.pdf".replace(" ", "-")
    return Response(
        content=pdf,
        media_type="application/pdf",
        headers={"content-disposition": f'inline; filename="{filename}"'},
    )
