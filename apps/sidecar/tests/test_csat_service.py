"""Spec #1M Task 2 — CsatService: guarda de posse + estado fechado.

A assinatura REAL do GI é get_ticket(*, znuny_ticket_id, customer_id) — não há
customer_user/login no GI (o escopo de posse é o customer_id do tenant; o GI
levanta ZnunyWriteError p/ não-encontrado/posse). O service recebe customer_id
p/ o lookup e customer_login só p/ gravar.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest

from gerti_sidecar.db import tenant_session_scope
from gerti_sidecar.domain.csat_service import (
    CsatAlreadyExists,
    CsatError,
    CsatService,
    TicketNotClosed,
)
from gerti_sidecar.integrations.znuny_ticket import ZnunyWriteError


def _fake_gi(*, state: str = "closed successful", customer_id: str = "AURORA"):
    async def get_ticket(*, znuny_ticket_id: int, customer_id: str) -> Any:
        if state == "__notfound__":
            raise ZnunyWriteError("not found")
        return SimpleNamespace(
            znuny_ticket_id=znuny_ticket_id,
            state=state,
            customer_id=customer_id,
        )

    return SimpleNamespace(get_ticket=get_ticket)


@pytest.mark.asyncio
async def test_submit_closed_ok_then_duplicate(session, app_session_factory, seed_two_tenants):
    tenant_id, _ = seed_two_tenants
    gi = _fake_gi(state="closed successful")
    async with tenant_session_scope(tenant_id, factory=app_session_factory) as s:
        svc = CsatService(s, gi)
        r = await svc.submit(
            tenant_id=tenant_id,
            znuny_ticket_id=10,
            customer_login="u@a",
            customer_id="AURORA",
            score=5,
            comment="ótimo",
        )
        assert r.score == 5
        assert r.znuny_ticket_id == 10
    # segunda resposta no mesmo ticket → CsatAlreadyExists (UNIQUE)
    async with tenant_session_scope(tenant_id, factory=app_session_factory) as s:
        svc = CsatService(s, gi)
        with pytest.raises(CsatAlreadyExists):
            await svc.submit(
                tenant_id=tenant_id,
                znuny_ticket_id=10,
                customer_login="u@a",
                customer_id="AURORA",
                score=4,
                comment=None,
            )


@pytest.mark.asyncio
async def test_submit_open_ticket_rejected(session, app_session_factory, seed_two_tenants):
    tenant_id, _ = seed_two_tenants
    gi = _fake_gi(state="open")
    async with tenant_session_scope(tenant_id, factory=app_session_factory) as s:
        svc = CsatService(s, gi)
        with pytest.raises(TicketNotClosed):
            await svc.submit(
                tenant_id=tenant_id,
                znuny_ticket_id=11,
                customer_login="u@a",
                customer_id="AURORA",
                score=5,
                comment=None,
            )


@pytest.mark.asyncio
async def test_submit_not_owned_is_not_found(session, app_session_factory, seed_two_tenants):
    tenant_id, _ = seed_two_tenants
    gi = _fake_gi(state="__notfound__")
    async with tenant_session_scope(tenant_id, factory=app_session_factory) as s:
        svc = CsatService(s, gi)
        with pytest.raises(CsatError):
            await svc.submit(
                tenant_id=tenant_id,
                znuny_ticket_id=99,
                customer_login="u@a",
                customer_id="AURORA",
                score=5,
                comment=None,
            )


@pytest.mark.asyncio
async def test_submit_invalid_score(session, app_session_factory, seed_two_tenants):
    tenant_id, _ = seed_two_tenants
    gi = _fake_gi(state="closed successful")
    async with tenant_session_scope(tenant_id, factory=app_session_factory) as s:
        svc = CsatService(s, gi)
        with pytest.raises(CsatError):
            await svc.submit(
                tenant_id=tenant_id,
                znuny_ticket_id=12,
                customer_login="u@a",
                customer_id="AURORA",
                score=6,
                comment=None,
            )


@pytest.mark.asyncio
async def test_comment_truncated(session, app_session_factory, seed_two_tenants):
    tenant_id, _ = seed_two_tenants
    gi = _fake_gi(state="closed successful")
    long_comment = "x" * 5000
    async with tenant_session_scope(tenant_id, factory=app_session_factory) as s:
        svc = CsatService(s, gi)
        r = await svc.submit(
            tenant_id=tenant_id,
            znuny_ticket_id=13,
            customer_login="u@a",
            customer_id="AURORA",
            score=3,
            comment=long_comment,
        )
        assert r.comment is not None
        assert len(r.comment) <= 2000


@pytest.mark.asyncio
async def test_find_returns_state(session, app_session_factory, seed_two_tenants):
    """find() retorna a resposta gravada (usado pelo GET /tickets/{id})."""
    tenant_id, _ = seed_two_tenants
    gi = _fake_gi(state="closed successful")
    async with tenant_session_scope(tenant_id, factory=app_session_factory) as s:
        svc = CsatService(s, gi)
        assert await svc.find(tenant_id=tenant_id, znuny_ticket_id=14) is None
        await svc.submit(
            tenant_id=tenant_id,
            znuny_ticket_id=14,
            customer_login="u@a",
            customer_id="AURORA",
            score=2,
            comment=None,
        )
    async with tenant_session_scope(tenant_id, factory=app_session_factory) as s:
        svc = CsatService(s, gi)
        found = await svc.find(tenant_id=tenant_id, znuny_ticket_id=14)
        assert found is not None
        assert found.score == 2
