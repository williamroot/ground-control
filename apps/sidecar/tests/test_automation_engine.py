"""AutomationEngine — orquestra evento → regras → ações, grava automation_run.

Usa testcontainer (engine/app_session_factory). GI/AI mockados.
"""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import select, text

from gerti_sidecar import db
from gerti_sidecar.domain.automation_service import AutomationEngine
from gerti_sidecar.models import AutomationRule, AutomationRun


class _FakeGi:
    def __init__(self) -> None:
        self.calls: list[dict] = []

    async def agent_ticket_update(self, **kw) -> None:
        self.calls.append(kw)


class _Tenant:
    def __init__(self, tid: uuid.UUID) -> None:
        self.id = tid


async def _seed_rules(factory, tenant_id, rules):
    async with factory() as s:
        async with s.begin():
            await s.execute(
                text("SELECT set_config('app.current_tenant', :t, true)"),
                {"t": str(tenant_id)},
            )
            for r in rules:
                s.add(AutomationRule(tenant_id=tenant_id, **r))


@pytest.mark.asyncio
async def test_engine_matches_only_matching_rule(
    engine, app_session_factory, seed_two_tenants, monkeypatch
):
    a, _b = seed_two_tenants
    monkeypatch.setattr(db, "SessionLocal", app_session_factory)
    await _seed_rules(
        app_session_factory,
        a,
        [
            {
                "name": "urgente",
                "trigger_event": "article_create",
                "conditions": [{"field": "title", "op": "contains", "value": "urgente"}],
                "actions": [{"type": "set_priority", "params": {"priority": "5 very high"}}],
                "position": 0,
            },
            {
                "name": "nao casa",
                "trigger_event": "article_create",
                "conditions": [{"field": "state", "op": "eq", "value": "closed"}],
                "actions": [{"type": "add_note", "params": {"note": "x"}}],
                "position": 1,
            },
        ],
    )
    gi = _FakeGi()
    eng = AutomationEngine(gi=gi, ai_factory=None)
    facts = {"title": "Servidor urgente fora do ar", "state": "open", "customer_id": "a"}
    await eng.handle(_Tenant(a), "article_create", facts, znuny_ticket_id=99)

    # só a regra que casou executou ação
    assert gi.calls == [{"ticket_id": 99, "priority": "5 very high"}]

    # dois automation_run gravados: 1 matched=True (com ação), 1 matched=False
    async with app_session_factory() as s:
        async with s.begin():
            await s.execute(
                text("SELECT set_config('app.current_tenant', :t, true)"), {"t": str(a)}
            )
            runs = (await s.execute(select(AutomationRun))).scalars().all()
    matched = sorted(r.matched for r in runs)
    assert matched == [False, True]


@pytest.mark.asyncio
async def test_engine_filters_by_event_and_enabled(
    engine, app_session_factory, seed_two_tenants, monkeypatch
):
    a, _b = seed_two_tenants
    monkeypatch.setattr(db, "SessionLocal", app_session_factory)
    await _seed_rules(
        app_session_factory,
        a,
        [
            {
                "name": "outro evento",
                "trigger_event": "ticket_create",
                "conditions": [],
                "actions": [{"type": "add_note", "params": {"note": "no"}}],
                "position": 0,
            },
            {
                "name": "desabilitada",
                "trigger_event": "article_create",
                "enabled": False,
                "conditions": [],
                "actions": [{"type": "add_note", "params": {"note": "no"}}],
                "position": 1,
            },
        ],
    )
    gi = _FakeGi()
    eng = AutomationEngine(gi=gi, ai_factory=None)
    await eng.handle(_Tenant(a), "article_create", {"title": "x"}, znuny_ticket_id=5)
    # nenhuma regra de article_create habilitada → nenhuma ação
    assert gi.calls == []


@pytest.mark.asyncio
async def test_engine_no_cross_tenant(engine, app_session_factory, seed_two_tenants, monkeypatch):
    a, b = seed_two_tenants
    monkeypatch.setattr(db, "SessionLocal", app_session_factory)
    # regra no tenant A
    await _seed_rules(
        app_session_factory,
        a,
        [
            {
                "name": "A only",
                "trigger_event": "ticket_create",
                "conditions": [],
                "actions": [{"type": "add_note", "params": {"note": "a"}}],
                "position": 0,
            }
        ],
    )
    gi = _FakeGi()
    eng = AutomationEngine(gi=gi, ai_factory=None)
    # processa evento como tenant B → a regra de A NÃO dispara
    await eng.handle(_Tenant(b), "ticket_create", {"title": "x"}, znuny_ticket_id=7)
    assert gi.calls == []


@pytest.mark.asyncio
async def test_engine_isolates_bad_rule(engine, app_session_factory, seed_two_tenants, monkeypatch):
    a, _b = seed_two_tenants
    monkeypatch.setattr(db, "SessionLocal", app_session_factory)
    await _seed_rules(
        app_session_factory,
        a,
        [
            {
                "name": "boa",
                "trigger_event": "ticket_create",
                "conditions": [],
                "actions": [{"type": "add_note", "params": {"note": "ok"}}],
                "position": 0,
            }
        ],
    )

    class _BoomGi(_FakeGi):
        async def agent_ticket_update(self, **kw):
            raise RuntimeError("boom")

    eng = AutomationEngine(gi=_BoomGi(), ai_factory=None)
    # não deve levantar — erro isolado, run gravado
    await eng.handle(_Tenant(a), "ticket_create", {"title": "x"}, znuny_ticket_id=8)
    async with app_session_factory() as s:
        async with s.begin():
            await s.execute(
                text("SELECT set_config('app.current_tenant', :t, true)"), {"t": str(a)}
            )
            runs = (await s.execute(select(AutomationRun))).scalars().all()
    assert len(runs) == 1
    assert runs[0].matched is True
    # a ação falhou → registrada no actions_result
    assert runs[0].actions_result[0]["ok"] is False
