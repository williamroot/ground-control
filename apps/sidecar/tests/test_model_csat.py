"""Spec #1M Task 1 — modelo CsatResponse + RLS + UNIQUE por ticket.

Prova isolamento RLS por tenant (FORCE) e a UNIQUE (tenant_id, znuny_ticket_id)
sob a sessão de cliente (gerti_sidecar, RLS-subject) via tenant_session_scope.
"""

from __future__ import annotations

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from gerti_sidecar.db import tenant_session_scope
from gerti_sidecar.models.csat import CsatResponse


@pytest.mark.asyncio
async def test_csat_rls_isolation(session, app_session_factory, seed_two_tenants):
    a, b = seed_two_tenants
    async with tenant_session_scope(a, factory=app_session_factory) as s:
        s.add(CsatResponse(tenant_id=a, znuny_ticket_id=10, customer_login="u@a", score=5))
    # tenant b não enxerga o CSAT de a (RLS FORCE)
    async with tenant_session_scope(b, factory=app_session_factory) as s:
        rows = (await s.execute(select(CsatResponse))).scalars().all()
        assert rows == []
    # tenant a enxerga o próprio
    async with tenant_session_scope(a, factory=app_session_factory) as s:
        rows = (await s.execute(select(CsatResponse))).scalars().all()
        assert len(rows) == 1
        assert rows[0].score == 5


@pytest.mark.asyncio
async def test_csat_unique_per_ticket(session, app_session_factory, seed_two_tenants):
    a, _b = seed_two_tenants
    async with tenant_session_scope(a, factory=app_session_factory) as s:
        s.add(CsatResponse(tenant_id=a, znuny_ticket_id=20, customer_login="u@a", score=5))
    with pytest.raises(IntegrityError):
        async with tenant_session_scope(a, factory=app_session_factory) as s:
            s.add(CsatResponse(tenant_id=a, znuny_ticket_id=20, customer_login="u@a", score=3))
            await s.flush()
