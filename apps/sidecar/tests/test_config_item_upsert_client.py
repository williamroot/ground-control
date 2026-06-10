"""Cliente GI config_item_upsert (Spec #1R-a, escrita no CMDB) — monta o payload
/ConfigItem/Upsert e retorna (config_item_id, action).

Segurança: o CustomerCompany vem do tenant (resolvido server-side no domínio); o
cliente só repassa. O update envia ConfigItemID; o create não.
"""

from __future__ import annotations

import pytest

from gerti_sidecar.integrations import znuny_ticket


@pytest.mark.asyncio
async def test_config_item_upsert_create(monkeypatch):
    captured = {}

    async def fake_post(route, body):
        captured["route"] = route
        captured["body"] = body
        return {"ConfigItemID": 42, "VersionID": 100, "Number": "10042", "Action": "created"}

    monkeypatch.setattr(znuny_ticket, "_post", fake_post)
    cid, action = await znuny_ticket.config_item_upsert(
        customer_id="AURORA",
        name="AUR-NB-009",
        fingerprint="FP-AB12",
        attributes={"OperatingSystem": "Windows 11", "CPU": "i7", "Memoria": "16 GB"},
    )
    assert cid == 42
    assert action == "created"
    assert captured["route"] == "/ConfigItem/Upsert"
    b = captured["body"]
    assert b["CustomerCompany"] == "AURORA"
    assert b["Name"] == "AUR-NB-009"
    assert b["Fingerprint"] == "FP-AB12"
    assert b["DeplState"] == "Production"
    assert b["InciState"] == "Operational"
    assert b["ConfigItemClass"] == "Computer"
    assert b["Attributes"]["CPU"] == "i7"
    assert "ConfigItemID" not in b  # create não envia id


@pytest.mark.asyncio
async def test_config_item_upsert_update_passes_id(monkeypatch):
    captured = {}

    async def fake_post(route, body):
        captured["body"] = body
        return {"ConfigItemID": 42, "VersionID": 101, "Number": "10042", "Action": "updated"}

    monkeypatch.setattr(znuny_ticket, "_post", fake_post)
    cid, action = await znuny_ticket.config_item_upsert(
        customer_id="AURORA",
        name="AUR-NB-009",
        fingerprint="FP-AB12",
        attributes={"CPU": "i9"},
        config_item_id=42,
    )
    assert cid == 42
    assert action == "updated"
    assert captured["body"]["ConfigItemID"] == 42


@pytest.mark.asyncio
async def test_config_item_upsert_custom_states(monkeypatch):
    captured = {}

    async def fake_post(route, body):
        captured["body"] = body
        return {"ConfigItemID": 1, "Action": "created"}

    monkeypatch.setattr(znuny_ticket, "_post", fake_post)
    await znuny_ticket.config_item_upsert(
        customer_id="TECHNOVA",
        name="TN-SRV-01",
        fingerprint="FP-X",
        attributes={},
        depl_state="Maintenance",
        inci_state="Incident",
    )
    assert captured["body"]["DeplState"] == "Maintenance"
    assert captured["body"]["InciState"] == "Incident"
