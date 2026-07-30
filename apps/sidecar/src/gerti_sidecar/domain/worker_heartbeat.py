"""Heartbeat do worker de consumo (Spec #3) — prova de vida separada do cursor.

`gerti.worker_heartbeat` é gravada a CADA tick de `jobs/worker.py`, com
trabalho ou sem, sucesso ou falha — diferente de `consumption_sync_cursor`,
que só avança quando há algo a reconciliar. É essa gravação incondicional que
permite à sonda de saúde (`domain/system_health_service.py`) distinguir um
worker vivo e ocioso de um worker travado.

Cross-tenant/operacional: só `AdminSessionLocal` (BYPASSRLS) toca esta tabela.
Failure-soft é responsabilidade do chamador (worker.tick) — esta função deixa
a exceção subir para que o chamador logue e siga o loop.
"""

from __future__ import annotations

import datetime as dt

from gerti_sidecar import db
from gerti_sidecar.models.worker_heartbeat import WorkerHeartbeat

WORKER_CONSUMPTION = "consumption"


async def record_heartbeat(worker: str, *, error: str | None) -> None:
    """Upsert do heartbeat de `worker`: ticks incrementa sempre, last_tick_at
    reflete o tick atual, last_success_at só avança quando `error` é None, e
    last_error é substituído (limpo quando o tick voltou a passar)."""
    if db.AdminSessionLocal is None:
        raise RuntimeError("AdminSessionLocal não inicializado — chame init_db()")
    now = dt.datetime.now(dt.UTC)
    async with db.AdminSessionLocal() as admin:
        hb = await admin.get(WorkerHeartbeat, worker)
        if hb is None:
            admin.add(
                WorkerHeartbeat(
                    worker=worker,
                    last_tick_at=now,
                    last_success_at=None if error else now,
                    ticks=1,
                    last_error=error,
                )
            )
        else:
            hb.last_tick_at = now
            hb.ticks += 1
            hb.last_error = error
            if error is None:
                hb.last_success_at = now
        await admin.commit()
