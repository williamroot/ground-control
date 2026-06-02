"""E2E (#1F-b): rich read endpoints over the Aurora+TechNova seeds, cross-tenant 404.

Aurora AUR-HORAS-2026 seed: events [90,120,150] min, pending glosa on event #0.
Pending glosa STILL counts -> consumed = (90+120+150)/60 = 6.0h; initial 40h ->
remaining 34.0h. counts_toward_balance is True for the pending-glosa event.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from gerti_sidecar import db
from gerti_sidecar.auth.session import encode_session
from gerti_sidecar.config import get_settings
from gerti_sidecar.main import create_app

_SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

import seed_demo_branding  # noqa: E402
import seed_demo_contracts  # noqa: E402


@pytest.mark.asyncio
async def test_rich_endpoints_two_tenants(engine, app_session_factory, session, monkeypatch):
    monkeypatch.setenv("SESSION_SECRET", "test-secret-32-chars-minimum-xxxx")
    monkeypatch.setenv("ENVIRONMENT", "test")
    get_settings.cache_clear()
    await seed_demo_contracts.seed(session)
    await session.commit()
    aurora_id, technova_id = await seed_demo_branding.seed(session)
    await session.commit()
    monkeypatch.setattr(
        db,
        "AdminSessionLocal",
        async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession),
    )
    monkeypatch.setattr(db, "SessionLocal", app_session_factory)
    app = create_app()
    st = get_settings()
    ha = {"host": "aurora.suporte.gerti.com.br"}
    ht = {"host": "technova.suporte.gerti.com.br"}
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://t") as cl:
        cl.cookies.set("gsid", encode_session(str(aurora_id), "eduardo.salvi", st))
        lst = (await cl.get("/v1/contracts", headers=ha)).json()
        assert len(lst) == 6
        assert all("id" in c and "consumed_percent" in c for c in lst)
        horas = next(c for c in lst if c["code"] == "AUR-HORAS-2026")
        assert horas["saldo"]["kind"] == "hours"
        assert horas["saldo"]["remaining"] == pytest.approx(34.0)  # pending glosa counts
        cid = horas["id"]

        det = (await cl.get(f"/v1/contracts/{cid}", headers=ha)).json()
        assert det["initial_hours"] == 40.0
        assert len(det["cycles"]) >= 1

        cons = (await cl.get(f"/v1/contracts/{cid}/consumption", headers=ha)).json()
        assert cons["total"] == 3
        # the pending-glosa event STILL counts
        pend = [it for it in cons["items"] if it["glosa"] and it["glosa"]["status"] == "pending"]
        assert pend and pend[0]["counts_toward_balance"] is True

        ser = (await cl.get(f"/v1/contracts/{cid}/series?today=2026-12-31", headers=ha)).json()
        assert ser["kind"] == "hours" and len(ser["points"]) >= 1

        dash = (await cl.get("/v1/dashboard", headers=ha)).json()
        assert dash["contract_count"] == 6
        types = {b["type"] for b in dash["balances_by_type"]}
        assert {
            "hour_bank",
            "credit_brl",
            "credit_shared",
            "service_count",
            "closed_value",
            "saas_product",
        } <= types

        # cross-tenant: TechNova session asking Aurora's contract -> 404
        cl.cookies.clear()
        cl.cookies.set("gsid", encode_session(str(technova_id), "admin.tech@technova.example", st))
        assert (await cl.get(f"/v1/contracts/{cid}", headers=ht)).status_code == 404
