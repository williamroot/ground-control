"""#1N Task 3 — ai_generation_log: tabela operacional SEM RLS (como agent_timer).

Insere via a sessão admin (BYPASSRLS, cross-tenant) e lê de volta. Verifica o
CHECK de kind (summary|reply).
"""

from __future__ import annotations

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from gerti_sidecar.models import AiGenerationLog


@pytest.mark.asyncio
async def test_insert_and_read_back(session):
    log = AiGenerationLog(
        agent_login="william",
        znuny_ticket_id=42,
        kind="summary",
        model="gpt-oss:120b",
        duration_ms=1234,
        ok=True,
    )
    session.add(log)
    await session.flush()
    stmt = select(AiGenerationLog).where(AiGenerationLog.znuny_ticket_id == 42)
    rows = (await session.execute(stmt)).scalars().all()
    assert len(rows) == 1
    assert rows[0].kind == "summary"
    assert rows[0].ok is True
    assert rows[0].model == "gpt-oss:120b"
    assert rows[0].created_at is not None


@pytest.mark.asyncio
async def test_kind_check_constraint(session):
    session.add(
        AiGenerationLog(
            agent_login="william",
            znuny_ticket_id=1,
            kind="bogus",
            model="gpt-oss:120b",
            duration_ms=1,
            ok=False,
        )
    )
    with pytest.raises(IntegrityError):
        await session.flush()
    await session.rollback()


@pytest.mark.asyncio
async def test_reply_kind_and_failure(session):
    session.add(
        AiGenerationLog(
            agent_login="bruno",
            znuny_ticket_id=99,
            kind="reply",
            model="gpt-oss:120b",
            duration_ms=50,
            ok=False,
        )
    )
    await session.flush()
    row = (
        await session.execute(select(AiGenerationLog).where(AiGenerationLog.znuny_ticket_id == 99))
    ).scalar_one()
    assert row.kind == "reply"
    assert row.ok is False
