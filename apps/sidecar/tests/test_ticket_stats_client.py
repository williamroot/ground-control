"""Cliente GI ticket_stats (#1O): mapeia o hash do GI /Ticket/Stats para a
dataclass TicketStats, escopado por CustomerID."""

from __future__ import annotations

import pytest

from gerti_sidecar.integrations import znuny_ticket


@pytest.mark.asyncio
async def test_ticket_stats_maps_payload(monkeypatch):
    captured = {}

    async def fake_post(route, body):
        captured["route"] = route
        captured["body"] = body
        return {
            "ByState": {"open": 3, "closed": 7},
            "ByPriority": {"3 normal": 8, "4 high": 2},
            "ByDay": [
                {"date": "2026-06-01", "count": 4},
                {"date": "2026-06-02", "count": 6},
            ],
            "SlaBreached": 2,
            "SlaAtRisk": 1,
            "Total": 10,
        }

    monkeypatch.setattr(znuny_ticket, "_post", fake_post)
    stats = await znuny_ticket.ticket_stats(
        customer_id="AURORA", since="2026-06-01 00:00:00", until="2026-06-09 00:00:00"
    )
    assert captured["route"] == "/Ticket/Stats"
    assert captured["body"]["CustomerCompany"] == "AURORA"
    assert captured["body"]["Since"] == "2026-06-01 00:00:00"
    assert captured["body"]["Until"] == "2026-06-09 00:00:00"
    assert stats.by_state == {"open": 3, "closed": 7}
    assert stats.by_priority == {"3 normal": 8, "4 high": 2}
    assert stats.by_day == [
        {"date": "2026-06-01", "count": 4},
        {"date": "2026-06-02", "count": 6},
    ]
    assert stats.sla_breached == 2
    assert stats.sla_at_risk == 1
    assert stats.total == 10


@pytest.mark.asyncio
async def test_ticket_stats_tolerates_missing_blocks(monkeypatch):
    async def fake_post(route, body):
        return {"ByState": {"open": 1}}

    monkeypatch.setattr(znuny_ticket, "_post", fake_post)
    stats = await znuny_ticket.ticket_stats(customer_id="AURORA", since="x", until="y")
    assert stats.by_state == {"open": 1}
    assert stats.by_priority == {}
    assert stats.by_day == []
    assert stats.sla_breached == 0
    assert stats.sla_at_risk == 0
    assert stats.total == 1
