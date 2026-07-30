"""NotificationService: emit idempotente, list_for, mark_read, mark_all_read
(Spec #3 V3). emit é idempotente por
(tenant_id, recipient_login, kind, link_path, dia).
"""

from __future__ import annotations

import datetime as dt

import pytest

from gerti_sidecar import db
from gerti_sidecar.domain.errors import NotificationNotFound
from gerti_sidecar.domain.notification_service import NotificationService


@pytest.mark.asyncio
async def test_emit_idempotent_same_day(session, app_session_factory, seed_two_tenants):
    a_id, _ = seed_two_tenants
    async with db.tenant_session_scope(a_id, factory=app_session_factory) as s:
        svc = NotificationService(s)
        n1 = await svc.emit(
            recipient_login="joe@aurora",
            kind="invoice_issued",
            title="Fatura #0001 emitida",
            link_path="/faturas/1",
            at=dt.datetime(2026, 3, 1, 9, 0, tzinfo=dt.UTC),
        )
        n2 = await svc.emit(
            recipient_login="joe@aurora",
            kind="invoice_issued",
            title="Fatura #0001 emitida (repetida)",
            link_path="/faturas/1",
            at=dt.datetime(2026, 3, 1, 18, 0, tzinfo=dt.UTC),
        )
        assert n1.id == n2.id
        page = await svc.list_for("joe@aurora")
        assert page.total == 1


@pytest.mark.asyncio
async def test_emit_different_day_not_idempotent(session, app_session_factory, seed_two_tenants):
    a_id, _ = seed_two_tenants
    async with db.tenant_session_scope(a_id, factory=app_session_factory) as s:
        svc = NotificationService(s)
        n1 = await svc.emit(
            recipient_login="joe@aurora",
            kind="invoice_issued",
            title="Fatura #0001",
            link_path="/faturas/1",
            at=dt.datetime(2026, 3, 1, tzinfo=dt.UTC),
        )
        n2 = await svc.emit(
            recipient_login="joe@aurora",
            kind="invoice_issued",
            title="Fatura #0002",
            link_path="/faturas/2",
            at=dt.datetime(2026, 3, 2, tzinfo=dt.UTC),
        )
        assert n1.id != n2.id
        page = await svc.list_for("joe@aurora")
        assert page.total == 2


@pytest.mark.asyncio
async def test_list_for_status_filters_and_unread_count(
    session, app_session_factory, seed_two_tenants
):
    a_id, _ = seed_two_tenants
    async with db.tenant_session_scope(a_id, factory=app_session_factory) as s:
        svc = NotificationService(s)
        n1 = await svc.emit(
            recipient_login="joe@aurora",
            kind="system",
            title="A",
            link_path="/a",
            at=dt.datetime(2026, 3, 1, tzinfo=dt.UTC),
        )
        await svc.emit(
            recipient_login="joe@aurora",
            kind="system",
            title="B",
            link_path="/b",
            at=dt.datetime(2026, 3, 2, tzinfo=dt.UTC),
        )
        await svc.mark_read(n1.id, "joe@aurora")

        all_page = await svc.list_for("joe@aurora", status="all")
        assert all_page.total == 2
        assert all_page.unread == 1

        unread_page = await svc.list_for("joe@aurora", status="unread")
        assert unread_page.total == 1
        assert unread_page.items[0].title == "B"

        read_page = await svc.list_for("joe@aurora", status="read")
        assert read_page.total == 1
        assert read_page.items[0].title == "A"

        # não vaza notificação de outro destinatário do mesmo tenant
        other = await svc.list_for("mary@aurora")
        assert other.total == 0


@pytest.mark.asyncio
async def test_mark_read_rejects_other_recipient(session, app_session_factory, seed_two_tenants):
    a_id, _ = seed_two_tenants
    async with db.tenant_session_scope(a_id, factory=app_session_factory) as s:
        svc = NotificationService(s)
        n = await svc.emit(recipient_login="joe@aurora", kind="system", title="A")
        with pytest.raises(NotificationNotFound):
            await svc.mark_read(n.id, "mary@aurora")


@pytest.mark.asyncio
async def test_mark_all_read(session, app_session_factory, seed_two_tenants):
    a_id, _ = seed_two_tenants
    async with db.tenant_session_scope(a_id, factory=app_session_factory) as s:
        svc = NotificationService(s)
        await svc.emit(
            recipient_login="joe@aurora",
            kind="system",
            title="A",
            link_path="/a",
            at=dt.datetime(2026, 3, 1, tzinfo=dt.UTC),
        )
        await svc.emit(
            recipient_login="joe@aurora",
            kind="system",
            title="B",
            link_path="/b",
            at=dt.datetime(2026, 3, 2, tzinfo=dt.UTC),
        )
        # notificação de outro destinatário não deve ser tocada
        await svc.emit(recipient_login="mary@aurora", kind="system", title="C")

        updated = await svc.mark_all_read("joe@aurora")
        assert updated == 2

        page = await svc.list_for("joe@aurora")
        assert page.unread == 0

        mary_page = await svc.list_for("mary@aurora")
        assert mary_page.unread == 1
