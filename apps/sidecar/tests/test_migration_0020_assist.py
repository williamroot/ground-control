"""#1S Task 1 — migration 0020: ai_generation_log.kind aceita 'assist'.

A coluna agent_login guarda o customer_login nas linhas de assist (reuso; é
tabela operacional sem RLS). Insere via a sessão admin (BYPASSRLS, cross-tenant).
"""

from __future__ import annotations

import pytest
from sqlalchemy import select

from gerti_sidecar.models import AiGenerationLog


@pytest.mark.asyncio
async def test_assist_kind_is_accepted(session):
    log = AiGenerationLog(
        agent_login="cliente@aurora.example",
        znuny_ticket_id=0,
        kind="assist",
        model="gpt-oss:120b",
        duration_ms=321,
        ok=True,
    )
    session.add(log)
    await session.flush()
    row = (
        await session.execute(select(AiGenerationLog).where(AiGenerationLog.kind == "assist"))
    ).scalar_one()
    assert row.kind == "assist"
    assert row.agent_login == "cliente@aurora.example"
    assert row.ok is True


@pytest.mark.asyncio
async def test_summary_and_reply_still_accepted(session):
    for kind in ("summary", "reply"):
        session.add(
            AiGenerationLog(
                agent_login="william",
                znuny_ticket_id=7,
                kind=kind,
                model="gpt-oss:120b",
                duration_ms=1,
                ok=True,
            )
        )
    await session.flush()
