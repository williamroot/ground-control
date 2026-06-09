"""#1N Task 2 — agent_get_thread mapeia o ticket do GI de agente para um
dataclass AgentTicket com os artigos (role/author/created/body) da thread.

O AgentTicketGet.pm já devolve Articles (From/SenderType/Subject/Body/CreateTime)
desde o #1J — aqui só testamos o mapeamento Python (mock do GI, sem rede).
"""

from __future__ import annotations

import pytest

from gerti_sidecar.integrations import znuny_ticket
from gerti_sidecar.integrations.znuny_ticket import AgentTicket, Article


@pytest.mark.asyncio
async def test_agent_get_thread_maps_articles(monkeypatch):
    async def fake_agent_get(*, znuny_ticket_id: int):
        assert znuny_ticket_id == 42
        return {
            "TicketID": 42,
            "TicketNumber": "2026060810000042",
            "Title": "Impressora não imprime",
            "State": "open",
            "CustomerID": "AURORA",
            "Articles": [
                {
                    "ArticleID": 1,
                    "From": "Cliente Aurora <cli@aurora.example>",
                    "SenderType": "customer",
                    "Subject": "Impressora não imprime",
                    "Body": "Bom dia, a impressora parou.",
                    "CreateTime": "2026-06-08 10:00:00",
                },
                {
                    "ArticleID": 2,
                    "From": "Agente <ag@gerti.example>",
                    "SenderType": "agent",
                    "Subject": "RE: Impressora",
                    "Body": "Já vou verificar.",
                    "CreateTime": "2026-06-08 10:05:00",
                },
            ],
        }

    monkeypatch.setattr(znuny_ticket, "agent_get", fake_agent_get)

    t = await znuny_ticket.agent_get_thread(znuny_ticket_id=42)
    assert isinstance(t, AgentTicket)
    assert t.znuny_ticket_id == 42
    assert t.title == "Impressora não imprime"
    assert t.customer_id == "AURORA"
    assert len(t.articles) == 2
    a0 = t.articles[0]
    assert isinstance(a0, Article)
    assert a0.role == "customer"
    assert a0.author == "Cliente Aurora <cli@aurora.example>"
    assert a0.created == "2026-06-08 10:00:00"
    assert "impressora parou" in a0.body.lower()
    assert t.articles[1].role == "agent"


@pytest.mark.asyncio
async def test_agent_get_thread_no_articles(monkeypatch):
    async def fake_agent_get(*, znuny_ticket_id: int):
        return {"TicketID": 7, "Title": "Vazio", "State": "new", "CustomerID": "X"}

    monkeypatch.setattr(znuny_ticket, "agent_get", fake_agent_get)
    t = await znuny_ticket.agent_get_thread(znuny_ticket_id=7)
    assert t.articles == []
    assert t.title == "Vazio"
