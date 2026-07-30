"""NotificationService — central de notificações do cliente (Spec #3 V3).

`emit` é o único produtor: idempotente por
`(tenant_id, recipient_login, kind, link_path, dia)` — evita spammar o
mesmo destinatário com o mesmo alerta no mesmo dia (ex.: fatura emitida
duas vezes por engano no mesmo ciclo de processamento).

Escopo por destinatário: `recipient_login` NÃO é o tenant — dentro do
mesmo tenant, dois usuários nunca compartilham notificação. A policy RLS
só isola por tenant_id; o filtro por `recipient_login` é responsabilidade
desta camada (ver `_owned` / `list_for` / `mark_read`).
"""

from __future__ import annotations

import dataclasses
import datetime as dt
import uuid
from typing import Any, cast

from sqlalchemy import CursorResult, func, select, text, update
from sqlalchemy.ext.asyncio import AsyncSession

from gerti_sidecar.domain.errors import NotificationNotFound
from gerti_sidecar.models import Notification


@dataclasses.dataclass(slots=True)
class NotificationPage:
    items: list[Notification]
    total: int
    unread: int


def _norm(login: str) -> str:
    return login.strip().lower()


class NotificationService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def emit(
        self,
        *,
        recipient_login: str,
        kind: str,
        title: str,
        body: str | None = None,
        link_path: str | None = None,
        at: dt.datetime | None = None,
    ) -> Notification:
        """Cria a notificação, ou devolve a existente do mesmo dia (idempotente)."""
        now = at or dt.datetime.now(dt.UTC)
        day_start = dt.datetime.combine(now.date(), dt.time.min, tzinfo=dt.UTC)
        day_end = day_start + dt.timedelta(days=1)

        conditions = [
            func.lower(Notification.recipient_login) == _norm(recipient_login),
            Notification.kind == kind,
            Notification.created_at >= day_start,
            Notification.created_at < day_end,
        ]
        if link_path is None:
            conditions.append(Notification.link_path.is_(None))
        else:
            conditions.append(Notification.link_path == link_path)

        existing = (
            await self.session.execute(select(Notification).where(*conditions))
        ).scalar_one_or_none()
        if existing is not None:
            return existing

        notif = Notification(
            tenant_id=await self._current_tenant_id(),
            recipient_login=recipient_login,
            kind=kind,
            title=title,
            body=body,
            link_path=link_path,
            created_at=now,
        )
        self.session.add(notif)
        await self.session.flush()
        return notif

    async def list_for(
        self,
        recipient_login: str,
        *,
        status: str = "all",
        limit: int = 20,
        offset: int = 0,
    ) -> NotificationPage:
        login = _norm(recipient_login)
        base = select(Notification).where(func.lower(Notification.recipient_login) == login)
        if status == "unread":
            base = base.where(Notification.read_at.is_(None))
        elif status == "read":
            base = base.where(Notification.read_at.is_not(None))

        total = int(
            await self.session.scalar(select(func.count()).select_from(base.subquery())) or 0
        )
        unread = int(
            await self.session.scalar(
                select(func.count()).select_from(
                    select(Notification)
                    .where(
                        func.lower(Notification.recipient_login) == login,
                        Notification.read_at.is_(None),
                    )
                    .subquery()
                )
            )
            or 0
        )
        rows = (
            (
                await self.session.execute(
                    base.order_by(Notification.created_at.desc()).limit(limit).offset(offset)
                )
            )
            .scalars()
            .all()
        )
        return NotificationPage(items=list(rows), total=total, unread=unread)

    async def mark_read(self, notification_id: uuid.UUID, recipient_login: str) -> Notification:
        notif = await self._owned(notification_id, recipient_login)
        if notif.read_at is None:
            notif.read_at = dt.datetime.now(dt.UTC)
            await self.session.flush()
        return notif

    async def mark_all_read(self, recipient_login: str) -> int:
        login = _norm(recipient_login)
        result = await self.session.execute(
            update(Notification)
            .where(
                func.lower(Notification.recipient_login) == login,
                Notification.read_at.is_(None),
            )
            .values(read_at=dt.datetime.now(dt.UTC))
        )
        await self.session.flush()
        return int(cast("CursorResult[Any]", result).rowcount or 0)

    async def _owned(self, notification_id: uuid.UUID, recipient_login: str) -> Notification:
        notif = await self.session.get(Notification, notification_id)
        # RLS já escondeu cross-tenant (get -> None); aqui garantimos também
        # que a notificação é do destinatário da sessão -> 404, nunca 403 (H3).
        if notif is None or _norm(notif.recipient_login) != _norm(recipient_login):
            raise NotificationNotFound("notificação inexistente para este destinatário")
        return notif

    async def _current_tenant_id(self) -> uuid.UUID:
        res = await self.session.execute(text("SELECT current_setting('app.current_tenant', true)"))
        val = res.scalar_one()
        if not val:
            raise RuntimeError("sessão sem tenant (GUC ausente)")
        return uuid.UUID(val)
