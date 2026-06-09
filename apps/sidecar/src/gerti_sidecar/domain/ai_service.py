"""AiService — sumarização + resposta sugerida via Ollama Cloud (Spec #1N).

Puxa a thread do ticket via GI de agente (agent_get_thread), monta o prompt com
DEFESA CONTRA PROMPT INJECTION (prompts.py: spotlighting/sanitização/limites),
chama o LLM em modo `chat` PURO (SEM tools — camada 2) e registra a geração em
ai_generation_log (auditoria/custo). A saída é tratada como NÃO-CONFIÁVEL: o
service apenas RETORNA texto ao router — nunca deriva ação, muda estado de
ticket ou envia algo ao cliente (camada 5).

Opera sob a sessão admin (AdminSessionLocal, BYPASSRLS — o agente é cross-tenant,
como timer_service). Em erro, grava log com ok=False antes de re-levantar.
"""

from __future__ import annotations

import time
from typing import Any, Protocol

from sqlalchemy.ext.asyncio import AsyncSession

from gerti_sidecar.domain import prompts
from gerti_sidecar.integrations.znuny_ticket import AgentTicket
from gerti_sidecar.models import AiGenerationLog


class _Ollama(Protocol):
    async def chat(self, messages: list[Any], *, reasoning_effort: str = ...) -> str: ...


class _Gi(Protocol):
    async def agent_get_thread(self, *, znuny_ticket_id: int) -> AgentTicket: ...


class AiService:
    def __init__(self, admin_session: AsyncSession, ollama: _Ollama, gi: _Gi) -> None:
        self._session = admin_session
        self._ollama = ollama
        self._gi = gi

    @property
    def _model(self) -> str:
        # nome do modelo p/ auditoria (atributo privado do cliente, fallback genérico)
        return getattr(self._ollama, "_model", "")

    async def _log(
        self, *, agent_login: str, znuny_ticket_id: int, kind: str, duration_ms: int, ok: bool
    ) -> None:
        self._session.add(
            AiGenerationLog(
                agent_login=agent_login,
                znuny_ticket_id=znuny_ticket_id,
                kind=kind,
                model=self._model or "unknown",
                duration_ms=duration_ms,
                ok=ok,
            )
        )
        await self._session.flush()

    async def _run(
        self,
        *,
        agent_login: str,
        znuny_ticket_id: int,
        kind: str,
        messages: list[dict[str, str]],
    ) -> str:
        start = time.monotonic()
        ok = False
        try:
            # chat PURO, sem tools (camada 2). reasoning_effort baixo (custo).
            out = await self._ollama.chat(messages, reasoning_effort="low")
            ok = True
            return out
        finally:
            duration_ms = int((time.monotonic() - start) * 1000)
            await self._log(
                agent_login=agent_login,
                znuny_ticket_id=znuny_ticket_id,
                kind=kind,
                duration_ms=duration_ms,
                ok=ok,
            )

    async def summarize(self, *, znuny_ticket_id: int, agent_login: str) -> str:
        ticket = await self._gi.agent_get_thread(znuny_ticket_id=znuny_ticket_id)
        messages = prompts.build_summary_messages(ticket)
        return await self._run(
            agent_login=agent_login,
            znuny_ticket_id=znuny_ticket_id,
            kind="summary",
            messages=messages,
        )

    async def suggest_reply(
        self, *, znuny_ticket_id: int, agent_login: str, instruction: str | None
    ) -> str:
        ticket = await self._gi.agent_get_thread(znuny_ticket_id=znuny_ticket_id)
        messages = prompts.build_reply_messages(ticket, instruction)
        return await self._run(
            agent_login=agent_login,
            znuny_ticket_id=znuny_ticket_id,
            kind="reply",
            messages=messages,
        )
