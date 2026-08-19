"""Passo do worker que materializa a agenda de todos os clientes (T-R11.3).

Cross-tenant por fora, RLS-scoped por dentro: lê a lista de clientes com
`AdminSessionLocal` (BYPASSRLS) e abre um `tenant_session_scope` por cliente
para a escrita. É o mesmo desenho do `cycle_closer` — o worker é global, o dado
nunca é.

Roda **uma vez por dia**, junto do fechamento de ciclos. Uma agenda não precisa
de granularidade de minuto: a tarefa é "verificação de backup de segunda", não
"às 08:00:03". O horário do cadastro (`at_time`) aparece no título e na tela;
ele é informação para o técnico, não gatilho de precisão.
"""

from __future__ import annotations

import datetime as dt
import logging

from sqlalchemy import select

from gerti_sidecar import db
from gerti_sidecar.domain.recurring_task_service import RecurringTaskService
from gerti_sidecar.integrations import znuny_ticket
from gerti_sidecar.models import Tenant

logger = logging.getLogger(__name__)


async def materialize_due_tasks(*, today: dt.date | None = None) -> int:
    """Abre os chamados vencidos de todos os clientes. Devolve quantos criou."""
    if db.AdminSessionLocal is None:
        raise RuntimeError("AdminSessionLocal não inicializado — chame init_db()")
    day = today or dt.datetime.now(dt.UTC).date()

    async with db.AdminSessionLocal() as admin:
        tenants = (await admin.execute(select(Tenant.id, Tenant.znuny_customer_id))).all()

    total = 0
    for tenant_id, customer_id in tenants:
        try:
            async with db.tenant_session_scope(tenant_id) as s:
                result = await RecurringTaskService(s, znuny_ticket).materialize(
                    tenant_id=tenant_id, customer_id=customer_id, today=day
                )
            total += result.created
            if result.failed:
                logger.warning(
                    "agenda: %s falha(s) ao abrir chamado do cliente %s",
                    result.failed,
                    customer_id,
                )
        except Exception as exc:
            # Um cliente com problema não pode travar a agenda dos outros.
            logger.warning("agenda do cliente %s falhou: %s", customer_id, exc)
    return total
