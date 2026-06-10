from __future__ import annotations

import pytest

from gerti_sidecar.domain.automation_actions import ACTION_HANDLERS, ActionContext, execute


class _FakeGi:
    def __init__(self) -> None:
        self.update_calls: list[dict] = []

    async def agent_ticket_update(self, **kwargs) -> None:
        self.update_calls.append(kwargs)


class _FailingGi(_FakeGi):
    async def agent_ticket_update(self, **kwargs) -> None:
        raise RuntimeError("znuny down")


class _FakeAi:
    def __init__(self, out: str = "resumo seguro") -> None:
        self.out = out
        self.calls: list[int] = []

    async def summarize(self, *, znuny_ticket_id: int, agent_login: str) -> str:
        self.calls.append(znuny_ticket_id)
        return self.out


def _ctx(gi=None, ai=None) -> ActionContext:
    return ActionContext(
        znuny_ticket_id=7,
        facts={"customer_id": "AURORA", "title": "x"},
        gi=gi or _FakeGi(),
        ai=ai,
        agent_login="automation",
    )


@pytest.mark.asyncio
async def test_set_priority_calls_update():
    gi = _FakeGi()
    res = await execute([{"type": "set_priority", "params": {"priority": "5 very high"}}], _ctx(gi))
    assert gi.update_calls == [{"ticket_id": 7, "priority": "5 very high"}]
    assert res[0]["ok"] is True
    assert res[0]["type"] == "set_priority"


@pytest.mark.asyncio
async def test_set_queue_state_note():
    gi = _FakeGi()
    await execute([{"type": "set_queue", "params": {"queue": "Suporte N2"}}], _ctx(gi))
    await execute([{"type": "set_state", "params": {"state": "open"}}], _ctx(gi))
    await execute([{"type": "add_note", "params": {"note": "auto"}}], _ctx(gi))
    assert gi.update_calls[0] == {"ticket_id": 7, "queue": "Suporte N2"}
    assert gi.update_calls[1] == {"ticket_id": 7, "state": "open"}
    assert gi.update_calls[2] == {"ticket_id": 7, "note": "auto"}


@pytest.mark.asyncio
async def test_unknown_action_ignored_with_record():
    res = await execute([{"type": "delete_ticket", "params": {}}], _ctx())
    assert res[0]["ok"] is False
    assert "unknown_action" in res[0]["error"]


@pytest.mark.asyncio
async def test_action_failure_isolated():
    gi = _FailingGi()
    res = await execute(
        [
            {"type": "set_priority", "params": {"priority": "5 very high"}},
            {"type": "add_note", "params": {"note": "still runs"}},
        ],
        _ctx(gi),
    )
    # ambas tentadas; ambas falham mas o loop não aborta
    assert len(res) == 2
    assert all(r["ok"] is False for r in res)
    assert "znuny down" in res[0]["error"]


@pytest.mark.asyncio
async def test_ai_summarize_note_posts_internal_note():
    gi = _FakeGi()
    ai = _FakeAi(out="RESUMO: cliente reporta queda")
    res = await execute([{"type": "ai_summarize_note", "params": {}}], _ctx(gi, ai))
    assert ai.calls == [7]
    # a saída do LLM vira nota INTERNA via agent_ticket_update(note=...)
    assert gi.update_calls[0]["ticket_id"] == 7
    assert "RESUMO" in gi.update_calls[0]["note"]
    assert res[0]["ok"] is True


@pytest.mark.asyncio
async def test_ai_summarize_without_ai_service_is_safe():
    # sem AiService configurado → ação registra erro, não explode
    res = await execute([{"type": "ai_summarize_note", "params": {}}], _ctx())
    assert res[0]["ok"] is False


def test_action_handlers_allowlist():
    assert set(ACTION_HANDLERS) == {
        "set_priority",
        "set_queue",
        "set_state",
        "add_note",
        "notify",
        "ai_summarize_note",
    }
    assert "delete_ticket" not in ACTION_HANDLERS
