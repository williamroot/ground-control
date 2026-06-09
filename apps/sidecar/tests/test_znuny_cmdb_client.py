"""Spec #1K Fase 2 Task 3 — cliente GI CMDB (config_item_search / config_item_get).

Testa que as funções montam o body correto (CustomerCompany, ConfigItemID) e
mapeiam as chaves da resposta para os dataclasses AssetSummary / AssetDetail.
"""

from __future__ import annotations

import pytest

from gerti_sidecar.integrations import znuny_ticket


@pytest.mark.asyncio
async def test_config_item_search(monkeypatch):
    async def fake_post(route, body):
        assert route == "/ConfigItem/Search"
        assert body["CustomerCompany"] == "AURORA"
        return {
            "ConfigItems": [
                {
                    "Id": 5,
                    "Number": "10001",
                    "Class": "Computer",
                    "Name": "PC-001",
                    "DeplState": "Production",
                    "InciState": "Operational",
                }
            ]
        }

    monkeypatch.setattr(znuny_ticket, "_post", fake_post)
    rows = await znuny_ticket.config_item_search(customer_id="AURORA")
    assert len(rows) == 1
    assert rows[0].id == 5
    assert rows[0].class_ == "Computer"
    assert rows[0].name == "PC-001"
    assert rows[0].number == "10001"
    assert rows[0].deploy_state == "Production"
    assert rows[0].inci_state == "Operational"


@pytest.mark.asyncio
async def test_config_item_search_empty(monkeypatch):
    async def fake_post(route, body):
        return {"ConfigItems": []}

    monkeypatch.setattr(znuny_ticket, "_post", fake_post)
    rows = await znuny_ticket.config_item_search(customer_id="EMPTY")
    assert rows == []


@pytest.mark.asyncio
async def test_config_item_get_passes_customer(monkeypatch):
    async def fake_post(route, body):
        assert route == "/ConfigItem/Get"
        assert body["CustomerCompany"] == "AURORA"
        assert body["ConfigItemID"] == 5
        return {
            "Id": 5,
            "Number": "10001",
            "Class": "Computer",
            "Name": "PC-001",
            "DeplState": "Production",
            "InciState": "Operational",
            "Attributes": {"SerialNumber": "SN9"},
        }

    monkeypatch.setattr(znuny_ticket, "_post", fake_post)
    d = await znuny_ticket.config_item_get(config_item_id=5, customer_id="AURORA")
    assert d.number == "10001"
    assert d.customer_id == ""
    assert d.attributes.get("SerialNumber") == "SN9"


@pytest.mark.asyncio
async def test_config_item_get_no_attributes(monkeypatch):
    async def fake_post(route, body):
        return {
            "Id": 7,
            "Number": "10002",
            "Class": "Server",
            "Name": "SRV-002",
            "DeplState": "Production",
            "InciState": "Operational",
        }

    monkeypatch.setattr(znuny_ticket, "_post", fake_post)
    d = await znuny_ticket.config_item_get(config_item_id=7, customer_id="AURORA")
    assert d.attributes == {}


@pytest.mark.asyncio
async def test_create_ticket_includes_config_item_id(monkeypatch):
    captured: dict[str, object] = {}

    async def fake_post(route, body):
        captured.update(body)
        return {"TicketID": 42, "TicketNumber": "2024001"}

    monkeypatch.setattr(znuny_ticket, "_post", fake_post)
    await znuny_ticket.create_ticket(
        customer_user="joe",
        customer_id="AURORA",
        title="Test",
        body="body",
        service=None,
        type_=None,
        priority=None,
        contract_id="cid-123",
        config_item_id=5,
    )
    assert captured.get("ConfigItemID") == 5


@pytest.mark.asyncio
async def test_create_ticket_no_config_item_id(monkeypatch):
    captured: dict[str, object] = {}

    async def fake_post(route, body):
        captured.update(body)
        return {"TicketID": 43, "TicketNumber": "2024002"}

    monkeypatch.setattr(znuny_ticket, "_post", fake_post)
    await znuny_ticket.create_ticket(
        customer_user="joe",
        customer_id="AURORA",
        title="Test",
        body="body",
        service=None,
        type_=None,
        priority=None,
        contract_id="cid-123",
    )
    assert "ConfigItemID" not in captured
