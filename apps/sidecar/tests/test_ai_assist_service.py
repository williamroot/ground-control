"""#1S Task 3 — AiService.assist_ticket (rate-limit + parse failure-safe + auditoria).

Cliente-facing: o título+corpo do cliente vão ao LLM com defesa anti-injeção
(prompts.build_assist_messages), chat PURO (sem tools), saída parseada
failure-safe e registrada em ai_generation_log (kind='assist', agent_login =
customer_login). Rate-limit por cliente (>=20/h → AiRateLimited).
"""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import select

from gerti_sidecar.domain.ai_service import ASSIST_RATE_LIMIT, AiService
from gerti_sidecar.domain.errors import AiRateLimited
from gerti_sidecar.integrations.ollama import OllamaDisabled, OllamaUnavailable
from gerti_sidecar.models import AiGenerationLog


class _FakeOllama:
    _model = "gpt-oss:120b"

    def __init__(self, reply: str = '{"title":"X","body":"Y"}', raises=None):
        self.reply = reply
        self.raises = raises
        self.calls: list[dict] = []

    async def chat(self, messages, *, reasoning_effort: str = "low"):
        self.calls.append({"messages": messages, "reasoning_effort": reasoning_effort})
        if self.raises is not None:
            raise self.raises
        return self.reply


TENANT = uuid.uuid4()


@pytest.mark.asyncio
async def test_assist_returns_parsed_json_and_logs(session):
    ollama = _FakeOllama(reply='{"title":"Impressora sem imprimir","body":"O problema é..."}')
    svc = AiService(session, ollama, gi=None)
    out = await svc.assist_ticket(
        tenant_id=TENANT, customer_login="cli@aurora.example", title="nao imprime", body="resolva"
    )
    assert out == {"title": "Impressora sem imprimir", "body": "O problema é..."}
    # sem tools no payload enviado
    assert "tools" not in ollama.calls[0]
    logs = (
        (await session.execute(select(AiGenerationLog).where(AiGenerationLog.kind == "assist")))
        .scalars()
        .all()
    )
    assert len(logs) == 1
    assert logs[0].agent_login == "cli@aurora.example"
    assert logs[0].ok is True
    assert logs[0].znuny_ticket_id == 0


@pytest.mark.asyncio
async def test_assist_failure_safe_on_non_json(session):
    ollama = _FakeOllama(reply="texto livre sem json")
    svc = AiService(session, ollama, gi=None)
    out = await svc.assist_ticket(
        tenant_id=TENANT, customer_login="cli", title="assunto orig", body="corpo orig"
    )
    # não-JSON → mantém o título original, usa a saída bruta como body
    assert out["title"] == "assunto orig"
    assert out["body"] == "texto livre sem json"
    logs = (
        (await session.execute(select(AiGenerationLog).where(AiGenerationLog.kind == "assist")))
        .scalars()
        .all()
    )
    assert len(logs) == 1
    assert logs[0].ok is True


@pytest.mark.asyncio
async def test_assist_rate_limit_after_threshold(session):
    # semeia ASSIST_RATE_LIMIT logs recentes do mesmo cliente → próxima estoura
    for _ in range(ASSIST_RATE_LIMIT):
        session.add(
            AiGenerationLog(
                agent_login="spammer",
                znuny_ticket_id=0,
                kind="assist",
                model="gpt-oss:120b",
                duration_ms=1,
                ok=True,
            )
        )
    await session.flush()
    svc = AiService(session, _FakeOllama(), gi=None)
    with pytest.raises(AiRateLimited):
        await svc.assist_ticket(tenant_id=TENANT, customer_login="spammer", title="t", body="b")


@pytest.mark.asyncio
async def test_assist_rate_limit_is_per_customer(session):
    for _ in range(ASSIST_RATE_LIMIT):
        session.add(
            AiGenerationLog(
                agent_login="spammer",
                znuny_ticket_id=0,
                kind="assist",
                model="gpt-oss:120b",
                duration_ms=1,
                ok=True,
            )
        )
    await session.flush()
    # outro cliente não é afetado
    svc = AiService(session, _FakeOllama(), gi=None)
    out = await svc.assist_ticket(tenant_id=TENANT, customer_login="alice", title="t", body="b")
    assert "title" in out and "body" in out


@pytest.mark.asyncio
async def test_assist_disabled_propagates_and_logs_failure(session):
    ollama = _FakeOllama(raises=OllamaDisabled("no key"))
    svc = AiService(session, ollama, gi=None)
    with pytest.raises(OllamaDisabled):
        await svc.assist_ticket(tenant_id=TENANT, customer_login="cli", title="t", body="b")
    logs = (
        (await session.execute(select(AiGenerationLog).where(AiGenerationLog.kind == "assist")))
        .scalars()
        .all()
    )
    assert len(logs) == 1
    assert logs[0].ok is False


@pytest.mark.asyncio
async def test_assist_unavailable_propagates_and_logs_failure(session):
    ollama = _FakeOllama(raises=OllamaUnavailable("503"))
    svc = AiService(session, ollama, gi=None)
    with pytest.raises(OllamaUnavailable):
        await svc.assist_ticket(tenant_id=TENANT, customer_login="cli", title="t", body="b")
    logs = (await session.execute(select(AiGenerationLog))).scalars().all()
    assert len(logs) == 1
    assert logs[0].ok is False
