from __future__ import annotations

import pytest
from sqlalchemy.exc import IntegrityError

from gerti_sidecar.models import AgentTimer


@pytest.mark.asyncio
async def test_one_active_timer_per_agent_ticket(session):
    session.add(AgentTimer(agent_login="william", znuny_ticket_id=19, status="running"))
    await session.flush()
    # segundo ativo p/ o mesmo (agente,ticket) → viola o índice parcial único
    session.add(AgentTimer(agent_login="william", znuny_ticket_id=19, status="paused"))
    with pytest.raises(IntegrityError):
        await session.flush()
    await session.rollback()
    # mas dois tickets diferentes podem coexistir
    session.add(AgentTimer(agent_login="william", znuny_ticket_id=19, status="running"))
    session.add(AgentTimer(agent_login="william", znuny_ticket_id=20, status="running"))
    await session.flush()
