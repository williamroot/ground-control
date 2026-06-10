"""AutomationEngine — orquestra evento → regras → ações (Spec #1Q, Task 4).

`handle(tenant, event, facts, znuny_ticket_id)`:
- abre `tenant_session_scope(tenant.id)` (RLS-subject) e carrega as `automation_rule`
  `enabled` com `trigger_event == event`, ordenadas por `position`;
- avalia `conditions` com o avaliador puro (`automation_eval.evaluate`);
- se casa, executa `actions` (allowlist) via `automation_actions.execute`;
- grava um `automation_run` por regra avaliada (matched true/false, resultado, erro).

Garantias:
- **Sem cross-tenant:** as regras vêm da sessão RLS do tenant do evento; uma regra
  do tenant A nunca é vista processando um evento do tenant B.
- **Erros isolados por regra:** uma regra ruim (ação que explode) não derruba as
  outras nem a transação; o erro vai para o `automation_run.error`.
- A ação `ai_summarize_note` recebe um AiService (via `ai_factory`) sob a sessão
  admin; a saída do LLM é tratada como nota interna não-confiável (defesa #1N).
"""

from __future__ import annotations

import logging
from typing import Any, Protocol

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from gerti_sidecar.db import tenant_session_scope
from gerti_sidecar.domain.automation_actions import ActionContext, execute
from gerti_sidecar.domain.automation_eval import evaluate
from gerti_sidecar.models import AutomationRule, AutomationRun

logger = logging.getLogger("gerti_sidecar.automation")


class _Tenant(Protocol):
    @property
    def id(self) -> Any: ...


class _AiFactory(Protocol):
    def __call__(self, admin_session: AsyncSession) -> Any: ...


class AutomationEngine:
    def __init__(self, *, gi: Any, ai_factory: _AiFactory | None = None) -> None:
        self._gi = gi
        self._ai_factory = ai_factory

    async def handle(
        self,
        tenant: _Tenant,
        event: str,
        facts: dict[str, Any],
        *,
        znuny_ticket_id: int,
    ) -> list[AutomationRun]:
        runs: list[AutomationRun] = []
        async with tenant_session_scope(tenant.id) as session:
            rules = (
                (
                    await session.execute(
                        select(AutomationRule)
                        .where(
                            AutomationRule.trigger_event == event,
                            AutomationRule.enabled.is_(True),
                        )
                        .order_by(AutomationRule.position, AutomationRule.created_at)
                    )
                )
                .scalars()
                .all()
            )
            for rule in rules:
                matched = False
                actions_result: list[dict[str, Any]] | None = None
                error: str | None = None
                try:
                    matched = evaluate(rule.conditions, facts)
                    if matched:
                        ctx = ActionContext(
                            znuny_ticket_id=znuny_ticket_id,
                            facts=facts,
                            gi=self._gi,
                            ai=(self._ai_factory(session) if self._ai_factory else None),
                        )
                        actions_result = await execute(rule.actions, ctx)
                except Exception as exc:  # isolamento por regra
                    error = str(exc)
                    logger.warning(
                        "automation rule %s failed on ticket %s: %s",
                        rule.id,
                        znuny_ticket_id,
                        exc,
                    )
                run = AutomationRun(
                    tenant_id=rule.tenant_id,
                    rule_id=rule.id,
                    znuny_ticket_id=znuny_ticket_id,
                    event=event,
                    matched=matched,
                    actions_result=actions_result,
                    error=error,
                )
                session.add(run)
                runs.append(run)
        return runs
