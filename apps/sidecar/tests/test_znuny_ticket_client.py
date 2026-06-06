# apps/sidecar/tests/test_znuny_ticket_client.py
from __future__ import annotations

import pytest

from gerti_sidecar.integrations import znuny_ticket


@pytest.mark.asyncio
async def test_create_ticket_maps_fields(monkeypatch):
    captured = {}

    async def fake_post(route, body):
        captured["route"] = route
        captured["body"] = body
        return {"TicketID": 42, "TicketNumber": "2026010100001"}

    monkeypatch.setattr(znuny_ticket, "_post", fake_post)
    out = await znuny_ticket.create_ticket(
        customer_user="joe@acme.test",
        customer_id="ACME",
        title="t",
        body="b",
        service="Suporte N1",
        type_="Incidente",
        priority="3 normal",
        contract_id="c-uuid",
        attachments=[znuny_ticket.Attachment("a.txt", "text/plain", "Zm9v")],
    )
    assert out == znuny_ticket.TicketCreated(42, "2026010100001")
    assert captured["route"] == "/Ticket"
    b = captured["body"]
    assert b["CustomerUser"] == "joe@acme.test"
    assert b["ContractId"] == "c-uuid"
    assert b["Attachments"][0]["Filename"] == "a.txt"


@pytest.mark.asyncio
async def test_search_company_scope(monkeypatch):
    async def fake_post(route, body):
        assert route == "/Ticket/Search"
        assert body["Scope"] == "company"
        return {
            "Tickets": [
                {
                    "TicketID": 1,
                    "TicketNumber": "n1",
                    "Title": "x",
                    "State": "new",
                    "Created": "2026-01-01 00:00:00",
                    "ContractId": "c1",
                }
            ]
        }

    monkeypatch.setattr(znuny_ticket, "_post", fake_post)
    rows = await znuny_ticket.search_tickets(scope="company", customer_user="j", customer_id="ACME")
    assert rows[0].contract_id == "c1"
    assert rows[0].znuny_ticket_id == 1


@pytest.mark.asyncio
async def test_get_ticket_passes_customer_id(monkeypatch):
    async def fake_post(route, body):
        assert route == "/Ticket/Get"
        assert body["CustomerID"] == "ACME"
        return {
            "TicketID": 7,
            "TicketNumber": "n",
            "Title": "t",
            "State": "open",
            "Priority": "3 normal",
            "Created": "2026-01-01 00:00:00",
            "CustomerID": "ACME",
            "ContractId": "c1",
            "Articles": [],
        }

    monkeypatch.setattr(znuny_ticket, "_post", fake_post)
    d = await znuny_ticket.get_ticket(znuny_ticket_id=7, customer_id="ACME")
    assert d.customer_id == "ACME"
    assert d.articles == []
