from __future__ import annotations

import pytest

from gerti_sidecar.integrations import znuny_ticket


@pytest.mark.asyncio
async def test_time_accounting_add(monkeypatch):
    captured = {}

    async def fake_post(route, body):
        captured["route"] = route
        captured["body"] = body
        return {"OK": 1, "UserID": 7}

    monkeypatch.setattr(znuny_ticket, "_post_agent", fake_post)
    await znuny_ticket.time_accounting_add(
        znuny_ticket_id=19, agent_login="william", time_unit=24.0, note="ok"
    )
    assert captured["route"] == "/TimeAccounting/Add"
    assert captured["body"]["TicketID"] == 19
    assert captured["body"]["AgentLogin"] == "william"
    assert captured["body"]["TimeUnit"] == 24.0


@pytest.mark.asyncio
async def test_agent_search(monkeypatch):
    async def fake_post(route, body):
        assert route == "/Agent/Ticket/Search"
        return {
            "Tickets": [
                {
                    "TicketID": 19,
                    "TicketNumber": "n",
                    "Title": "t",
                    "State": "open",
                    "CustomerID": "AURORA",
                    "Owner": "william",
                    "Created": "2026-06-09 10:00:00",
                }
            ]
        }

    monkeypatch.setattr(znuny_ticket, "_post_agent", fake_post)
    rows = await znuny_ticket.agent_search(query="impr", customer_id=None)
    assert rows[0].znuny_ticket_id == 19
    assert rows[0].customer_id == "AURORA"
