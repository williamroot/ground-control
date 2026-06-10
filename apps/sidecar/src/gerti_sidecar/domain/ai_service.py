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

import datetime as dt
import json
import time
import uuid
from typing import Any, Protocol

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from gerti_sidecar.domain import prompts
from gerti_sidecar.domain.errors import AiRateLimited
from gerti_sidecar.integrations.znuny_ticket import AgentTicket
from gerti_sidecar.models import AiGenerationLog

# Limite do assistente de escrita do portal (Spec #1S): N chamadas por cliente/hora.
ASSIST_RATE_LIMIT = 20
# Caps da saída do LLM aplicados ao rascunho devolvido ao cliente (anti-abuso).
_MAX_ASSIST_TITLE_OUT = 250
_MAX_ASSIST_BODY_OUT = 8000


class _Ollama(Protocol):
    async def chat(self, messages: list[Any], *, reasoning_effort: str = ...) -> str: ...


class _Gi(Protocol):
    async def agent_get_thread(self, *, znuny_ticket_id: int) -> AgentTicket: ...


class AiService:
    def __init__(self, admin_session: AsyncSession, ollama: _Ollama, gi: _Gi | None) -> None:
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

    def _require_gi(self) -> _Gi:
        # summarize/suggest_reply precisam do GI de agente; assist_ticket não.
        if self._gi is None:
            raise RuntimeError("AiService sem GI: operação de thread indisponível")
        return self._gi

    async def summarize(self, *, znuny_ticket_id: int, agent_login: str) -> str:
        ticket = await self._require_gi().agent_get_thread(znuny_ticket_id=znuny_ticket_id)
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
        ticket = await self._require_gi().agent_get_thread(znuny_ticket_id=znuny_ticket_id)
        messages = prompts.build_reply_messages(ticket, instruction)
        return await self._run(
            agent_login=agent_login,
            znuny_ticket_id=znuny_ticket_id,
            kind="reply",
            messages=messages,
        )

    async def _assist_count_last_hour(self, customer_login: str) -> int:
        """Conta linhas ai_generation_log kind='assist' do cliente na última hora."""
        since = dt.datetime.now(dt.UTC) - dt.timedelta(hours=1)
        stmt = (
            select(func.count())
            .select_from(AiGenerationLog)
            .where(
                AiGenerationLog.kind == "assist",
                AiGenerationLog.agent_login == customer_login,
                AiGenerationLog.created_at >= since,
            )
        )
        return int((await self._session.execute(stmt)).scalar_one())

    @staticmethod
    def _parse_assist_output(raw: str, *, fallback_title: str) -> dict[str, str]:
        """Parse failure-safe: JSON {title,body} → dict; senão usa o texto como body.

        A saída do LLM é NÃO-CONFIÁVEL (camada 5): só vira rascunho de texto, nunca ação.
        """
        text = raw.strip()
        # tolera cercas de código ```json ... ```
        if text.startswith("```"):
            text = text.strip("`")
            if text.lower().startswith("json"):
                text = text[4:]
            text = text.strip()
        try:
            data = json.loads(text)
        except (ValueError, TypeError):
            data = None
        if isinstance(data, dict) and ("title" in data or "body" in data):
            title = str(data.get("title") or fallback_title)
            body = str(data.get("body") or "")
        else:
            title = fallback_title
            body = raw.strip()
        return {
            "title": title.strip()[:_MAX_ASSIST_TITLE_OUT],
            "body": body.strip()[:_MAX_ASSIST_BODY_OUT],
        }

    async def assist_ticket(
        self, *, tenant_id: uuid.UUID, customer_login: str, title: str, body: str
    ) -> dict[str, str]:
        """Assistente de escrita do PORTAL (Spec #1S): reescreve o rascunho do cliente.

        Cliente-facing, rate-limited (>=ASSIST_RATE_LIMIT/h → AiRateLimited). Monta
        msgs com defesa anti-injeção (prompts.build_assist_messages), chat PURO (sem
        tools), parse failure-safe, loga (kind='assist', agent_login=customer_login).
        `tenant_id` é só para contexto/auditoria; a tabela é operacional sem RLS.
        """
        if await self._assist_count_last_hour(customer_login) >= ASSIST_RATE_LIMIT:
            raise AiRateLimited("assist_rate_limited")
        messages = prompts.build_assist_messages(title, body)
        start = time.monotonic()
        ok = False
        try:
            out = await self._ollama.chat(messages, reasoning_effort="low")
            ok = True
            return self._parse_assist_output(out, fallback_title=title)
        finally:
            duration_ms = int((time.monotonic() - start) * 1000)
            await self._log(
                agent_login=customer_login,
                znuny_ticket_id=0,  # sem ticket ainda (rascunho pré-abertura)
                kind="assist",
                duration_ms=duration_ms,
                ok=ok,
            )
