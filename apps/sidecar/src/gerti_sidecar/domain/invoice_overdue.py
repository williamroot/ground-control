"""Marca faturas vencidas como overdue, por tenant (Spec #1P).

Leitura cross-tenant (admin/BYPASSRLS) dos tenants com fatura `open` vencida;
o UPDATE roda sob tenant_session_scope (RLS-subject) via InvoiceService.mark_overdue_due
(reuso da regra de transição). Idempotente: uma fatura já `overdue`/`paid`/`void`
não é re-selecionada. Failure-soft é responsabilidade do chamador (worker.tick).
"""

from __future__ import annotations

import datetime as dt

from sqlalchemy import select

from gerti_sidecar import db
from gerti_sidecar.domain.invoice_service import InvoiceService
from gerti_sidecar.models import Invoice
from gerti_sidecar.models.enums import InvoiceStatus


class InvoiceOverdueMarker:
    async def mark_overdue_due(self, *, today: dt.date | None = None) -> int:
        if db.AdminSessionLocal is None:
            raise RuntimeError("AdminSessionLocal não inicializado — chame init_db()")
        day = today or dt.datetime.now(dt.UTC).date()
        cutoff = dt.datetime.combine(day, dt.time.min, tzinfo=dt.UTC)

        # Tenants com ao menos uma fatura open vencida (cross-tenant, BYPASSRLS).
        async with db.AdminSessionLocal() as admin:
            tenant_ids = (
                (
                    await admin.execute(
                        select(Invoice.tenant_id)
                        .where(
                            Invoice.status == InvoiceStatus.open,
                            Invoice.due_at < cutoff,
                        )
                        .distinct()
                    )
                )
                .scalars()
                .all()
            )

        marked = 0
        for tenant_id in tenant_ids:
            async with db.tenant_session_scope(tenant_id) as s:
                marked += await InvoiceService(s).mark_overdue_due(today=day)
        return marked
