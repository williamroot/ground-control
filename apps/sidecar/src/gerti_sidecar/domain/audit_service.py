"""audit_service.record — grava a trilha de auditoria (Spec #3 V5).

`record(...)` é fire-and-forget: abre sua PRÓPRIA sessão `AdminSessionLocal`
(BYPASSRLS — `audit_log` é operacional, sem RLS, nunca via `gerti_app`) e
comita isolada da transação do chamador. Qualquer falha (DB indisponível,
etc.) é só logada — **a gravação de auditoria nunca derruba a operação
principal** (contrato V5).

NUNCA passe segredo, senha, token ou corpo de ticket em `description`/
`metadata` — só metadados de auditoria (ids, nomes, tipos).
"""

from __future__ import annotations

import logging
import uuid
from typing import Any, Literal

from gerti_sidecar import db
from gerti_sidecar.models.audit_log import AuditLog

logger = logging.getLogger(__name__)

ActorType = Literal["agent", "customer", "system"]
Action = Literal["create", "update", "delete", "login", "export"]


async def record(
    *,
    actor_type: ActorType,
    actor_login: str | None,
    tenant_id: uuid.UUID | None,
    action: Action,
    entity: str,
    description: str,
    entity_id: str | None = None,
    ip: str | None = None,
    user_agent: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> None:
    """Grava um evento de auditoria. Nunca levanta — falha é só logada."""
    if db.AdminSessionLocal is None:
        logger.warning(
            "audit_log: AdminSessionLocal indisponível — evento descartado (%s/%s)",
            action,
            entity,
        )
        return
    try:
        async with db.AdminSessionLocal() as session:
            session.add(
                AuditLog(
                    actor_type=actor_type,
                    actor_login=actor_login,
                    tenant_id=tenant_id,
                    action=action,
                    entity=entity,
                    entity_id=entity_id,
                    description=description,
                    ip=ip,
                    user_agent=user_agent,
                    metadata_json=metadata or {},
                )
            )
            await session.commit()
    except Exception:  # nunca derruba a operação principal (contrato V5)
        logger.exception(
            "audit_log: falha ao gravar evento (%s/%s) — operação principal segue",
            action,
            entity,
        )
