"""Worker de consumo/fechamento (Spec #1B). Entrypoint do servico sidecar-worker.

Loop asyncio: reconcilia consumo a cada RECONCILE_INTERVAL_SECONDS; fecha ciclos
vencidos 1x/dia. Cada iteracao e isolada (try/except + log); nunca derruba o processo.
Idempotente - seguro reiniciar a qualquer momento.
"""

from __future__ import annotations

import asyncio
import dataclasses
import datetime as dt

import structlog

from gerti_sidecar import db
from gerti_sidecar.config import get_settings
from gerti_sidecar.domain.cycle_closer import CycleCloser
from gerti_sidecar.domain.invoice_overdue import InvoiceOverdueMarker
from gerti_sidecar.domain.reconciliation_service import ReconciliationService
from gerti_sidecar.integrations import znuny_ticket

log = structlog.get_logger()


@dataclasses.dataclass
class WorkerState:
    last_close_date: dt.date | None = None


async def tick(state: WorkerState, *, today: dt.date | None = None) -> None:
    """Uma iteracao: reconcilia sempre; fecha ciclos 1x/dia."""
    day = today or dt.datetime.now(dt.UTC).date()
    try:
        n = await ReconciliationService(gi=znuny_ticket).reconcile()
        if n:
            log.info("reconcile.done", events=n)
    except Exception as exc:
        log.warning("reconcile.error", error=str(exc))

    if state.last_close_date != day:
        try:
            closed = await CycleCloser().close_due_cycles()
            state.last_close_date = day
            if closed:
                log.info("cycles.closed", count=closed)
        except Exception as exc:
            log.warning("close_cycles.error", error=str(exc))

        # Faturas vencidas: open → overdue (cross-tenant, 1x/dia). Failure-soft.
        try:
            overdue = await InvoiceOverdueMarker().mark_overdue_due()
            if overdue:
                log.info("invoices.overdue", count=overdue)
        except Exception as exc:
            log.warning("mark_overdue.error", error=str(exc))


async def run() -> None:
    settings = get_settings()
    db.init_db(settings)
    state = WorkerState()
    log.info("worker.start", interval=settings.reconcile_interval_seconds)
    try:
        while True:
            await tick(state)
            await asyncio.sleep(settings.reconcile_interval_seconds)
    finally:
        await db.dispose_db()


def main() -> None:
    asyncio.run(run())


if __name__ == "__main__":
    main()
