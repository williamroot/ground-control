from __future__ import annotations

import pytest

from gerti_sidecar.integrations import znuny_ticket


@pytest.mark.asyncio
async def test_time_accounting_since_maps(monkeypatch):
    async def fake_post(route, body):
        assert route == "/TimeAccounting/Since"
        assert body["SinceId"] == 10
        assert body["Limit"] == 500
        return {
            "Entries": [
                {
                    "Id": 11, "TicketId": 19, "ArticleId": 50,
                    "TimeUnit": "30", "Created": "2026-06-08 10:00:00",
                },
                {
                    "Id": 12, "TicketId": 19, "ArticleId": 51,
                    "TimeUnit": "15", "Created": "2026-06-08 11:00:00",
                },
            ],
            "MaxId": 12,
        }

    monkeypatch.setattr(znuny_ticket, "_post", fake_post)
    page = await znuny_ticket.time_accounting_since(since_id=10, limit=500)
    assert page.max_id == 12
    assert len(page.entries) == 2
    assert page.entries[0].id == 11
    assert page.entries[0].ticket_id == 19
    assert page.entries[0].time_unit == 30.0
    assert page.entries[1].article_id == 51
