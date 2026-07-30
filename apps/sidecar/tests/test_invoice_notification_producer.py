"""InvoiceService.create_from_cycle emite notification `invoice_issued` para os
admins do tenant (Spec #3 V3, produtor obrigatório). Best-effort: mesmo sem
nenhum admin mapeado, a fatura é criada normalmente (não derruba a operação).
"""

from __future__ import annotations

import datetime as dt
import uuid

import pytest
from sqlalchemy import select

from gerti_sidecar import db
from gerti_sidecar.domain.consumption_service import ConsumptionService, RecordConsumption
from gerti_sidecar.domain.contract_service import ContractService, NewContract
from gerti_sidecar.domain.cycle_service import CycleService
from gerti_sidecar.domain.invoice_service import InvoiceService
from gerti_sidecar.models import ContractCycle, Notification, PortalUserRole
from gerti_sidecar.models.enums import ContractType, CycleKind, PortalRole


async def _seed_closed_cycle(s, *, code):
    c = await ContractService(s).create(
        NewContract(
            code=code,
            type=ContractType.credit_brl,
            starts_on=dt.date(2026, 1, 1),
            ends_on=dt.date(2026, 12, 31),
            initial_amount_brl=20000,
            unit_price_brl=200,
            created_by="w",
        )
    )
    cyc = ContractCycle(
        contract_id=c.id,
        kind=CycleKind.closing,
        period_start=dt.date(2026, 1, 1),
        period_end=dt.date(2026, 1, 31),
    )
    s.add(cyc)
    await s.flush()
    await ConsumptionService(s).record(
        RecordConsumption(
            contract_id=c.id,
            occurred_at=dt.datetime(2026, 1, 10, tzinfo=dt.UTC),
            source_kind="ticket_work",
            source_ref=f"{code}:1",
            billable_minutes=60,
            billable_amount_brl=200,
            recorded_by="t",
            webhook_event_id=uuid.uuid4(),
        )
    )
    await CycleService(s).close(cyc.id)
    return c, cyc


@pytest.mark.asyncio
async def test_create_from_cycle_notifies_tenant_admins(
    session, app_session_factory, seed_two_tenants
):
    a_id, _ = seed_two_tenants
    async with db.tenant_session_scope(a_id, factory=app_session_factory) as s:
        s.add(PortalUserRole(tenant_id=a_id, customer_login="admin@aurora", role=PortalRole.admin))
        s.add(
            PortalUserRole(
                tenant_id=a_id, customer_login="helpdesk@aurora", role=PortalRole.helpdesk
            )
        )
        await s.flush()

        _c, cyc = await _seed_closed_cycle(s, code="CB1")
        inv = await InvoiceService(s).create_from_cycle(cyc.id)

        rows = (
            (await s.execute(select(Notification).where(Notification.kind == "invoice_issued")))
            .scalars()
            .all()
        )
        assert len(rows) == 1
        notif = rows[0]
        assert notif.recipient_login == "admin@aurora"
        assert notif.link_path == f"/faturas/{inv.number}"
        assert str(inv.number).zfill(4) in notif.title


@pytest.mark.asyncio
async def test_create_from_cycle_without_admins_does_not_fail(
    session, app_session_factory, seed_two_tenants
):
    a_id, _ = seed_two_tenants
    async with db.tenant_session_scope(a_id, factory=app_session_factory) as s:
        _c, cyc = await _seed_closed_cycle(s, code="CB2")
        # sem PortalUserRole nenhum: create_from_cycle não pode falhar por isso
        inv = await InvoiceService(s).create_from_cycle(cyc.id)
        assert inv.number == 1

        rows = (
            (await s.execute(select(Notification).where(Notification.kind == "invoice_issued")))
            .scalars()
            .all()
        )
        assert rows == []
