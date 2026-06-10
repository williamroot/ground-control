"""Executor de ações do motor de automação (Spec #1Q, Task 3).

`execute(actions, ctx)` roda cada `{type, params}` da regra que casou:
- `ACTION_HANDLERS` é a **allowlist** (fonte única reusada pela validação do CRUD
  e pelos metadados da UI). Tipo fora dela → ação ignorada com `error` registrado
  (NUNCA deleta ticket/cliente — fora da allowlist por design).
- Cada ação é isolada: a falha de uma NÃO aborta as demais (coleta resultados).
- `ai_summarize_note`: chama o AiService (#1N), trata a saída como NÃO-CONFIÁVEL
  (defesa anti-injeção: vira **nota interna**, nunca enviada ao cliente).

As escritas no Znuny vão por `gi.agent_ticket_update(...)` (token de agente).
`notify` posta uma nota (MVP); um canal de e-mail dedicado é melhoria futura.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol


class _Gi(Protocol):
    async def agent_ticket_update(
        self,
        *,
        ticket_id: int,
        queue: str | None = ...,
        state: str | None = ...,
        priority: str | None = ...,
        owner: str | None = ...,
        note: str | None = ...,
    ) -> None: ...


class _Ai(Protocol):
    async def summarize(self, *, znuny_ticket_id: int, agent_login: str) -> str: ...


@dataclass
class ActionContext:
    znuny_ticket_id: int
    facts: dict[str, Any]
    gi: _Gi
    ai: _Ai | None = None
    agent_login: str = "automation"


async def _set_priority(ctx: ActionContext, params: dict[str, Any]) -> None:
    await ctx.gi.agent_ticket_update(
        ticket_id=ctx.znuny_ticket_id, priority=str(params["priority"])
    )


async def _set_queue(ctx: ActionContext, params: dict[str, Any]) -> None:
    await ctx.gi.agent_ticket_update(ticket_id=ctx.znuny_ticket_id, queue=str(params["queue"]))


async def _set_state(ctx: ActionContext, params: dict[str, Any]) -> None:
    await ctx.gi.agent_ticket_update(ticket_id=ctx.znuny_ticket_id, state=str(params["state"]))


async def _add_note(ctx: ActionContext, params: dict[str, Any]) -> None:
    await ctx.gi.agent_ticket_update(ticket_id=ctx.znuny_ticket_id, note=str(params["note"]))


async def _notify(ctx: ActionContext, params: dict[str, Any]) -> None:
    # MVP: a notificação é registrada como nota no ticket (prefixo claro).
    # Um canal de e-mail dedicado fica para uma melhoria futura.
    message = str(params.get("message") or params.get("note") or "Notificação automática")
    await ctx.gi.agent_ticket_update(ticket_id=ctx.znuny_ticket_id, note=f"[notify] {message}")


async def _ai_summarize_note(ctx: ActionContext, params: dict[str, Any]) -> None:
    if ctx.ai is None:
        raise RuntimeError("ai_service_unavailable")
    # A saída do LLM é NÃO-CONFIÁVEL → nota INTERNA, nunca ao cliente (#1N camada 5).
    summary = await ctx.ai.summarize(
        znuny_ticket_id=ctx.znuny_ticket_id, agent_login=ctx.agent_login
    )
    await ctx.gi.agent_ticket_update(
        ticket_id=ctx.znuny_ticket_id, note=f"[IA — resumo automático]\n{summary}"
    )


# Allowlist de ações. Qualquer tipo fora daqui é ignorado (sem deletar nada).
ACTION_HANDLERS = {
    "set_priority": _set_priority,
    "set_queue": _set_queue,
    "set_state": _set_state,
    "add_note": _add_note,
    "notify": _notify,
    "ai_summarize_note": _ai_summarize_note,
}


async def execute(actions: Any, ctx: ActionContext) -> list[dict[str, Any]]:
    """Roda cada ação isoladamente; retorna lista de resultados (auditoria)."""
    results: list[dict[str, Any]] = []
    if not isinstance(actions, (list | tuple)):
        return results
    for action in actions:
        atype = action.get("type") if isinstance(action, dict) else None
        params = action.get("params") if isinstance(action, dict) else None
        if not isinstance(params, dict):
            params = {}
        handler = ACTION_HANDLERS.get(atype) if atype is not None else None
        if handler is None:
            results.append({"type": atype, "ok": False, "error": f"unknown_action:{atype}"})
            continue
        try:
            await handler(ctx, params)
            results.append({"type": atype, "ok": True})
        except Exception as exc:  # isolamento por ação: nunca aborta as demais
            results.append({"type": atype, "ok": False, "error": str(exc)})
    return results
