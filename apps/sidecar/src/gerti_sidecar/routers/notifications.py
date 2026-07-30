"""GET/POST /v1/notifications — central de notificações do cliente (Spec #3 V3).

Escopo por destinatário: cada sessão só enxerga (e só pode marcar como
lida) as notificações cujo `recipient_login` é o `customer_login` da
própria sessão. Mesmo dentro do mesmo tenant, um usuário nunca lê/marca a
notificação de outro — o serviço responde 404 (nunca 403), anti-IDOR (H3).
"""

from __future__ import annotations

import datetime as dt
import uuid
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Path, Query, Response
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from gerti_sidecar.auth.session import SessionPayload, get_current_session
from gerti_sidecar.db import get_tenant_session
from gerti_sidecar.domain.errors import NotificationNotFound
from gerti_sidecar.domain.notification_service import NotificationService
from gerti_sidecar.models import Notification

router = APIRouter(prefix="/notifications", tags=["portal"])


class NotificationItem(BaseModel):
    id: uuid.UUID
    kind: str
    title: str
    body: str | None
    link_path: str | None
    read_at: dt.datetime | None
    created_at: dt.datetime


class NotificationPageOut(BaseModel):
    items: list[NotificationItem]
    total: int
    unread: int
    limit: int
    offset: int


class ReadAllOut(BaseModel):
    updated: int


def _item(n: Notification) -> NotificationItem:
    return NotificationItem(
        id=n.id,
        kind=n.kind,
        title=n.title,
        body=n.body,
        link_path=n.link_path,
        read_at=n.read_at,
        created_at=n.created_at,
    )


@router.get("", response_model=NotificationPageOut)
async def list_notifications(
    status: Literal["all", "unread", "read"] = "all",
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    session_payload: SessionPayload = Depends(get_current_session),
    session: AsyncSession = Depends(get_tenant_session),
) -> NotificationPageOut:
    page = await NotificationService(session).list_for(
        session_payload["customer_login"], status=status, limit=limit, offset=offset
    )
    return NotificationPageOut(
        items=[_item(n) for n in page.items],
        total=page.total,
        unread=page.unread,
        limit=limit,
        offset=offset,
    )


@router.post("/{notification_id}/read", status_code=204)
async def mark_read(
    notification_id: uuid.UUID = Path(...),
    session_payload: SessionPayload = Depends(get_current_session),
    session: AsyncSession = Depends(get_tenant_session),
) -> Response:
    try:
        await NotificationService(session).mark_read(
            notification_id, session_payload["customer_login"]
        )
    except NotificationNotFound as exc:
        raise HTTPException(status_code=404, detail="notification_not_found") from exc
    return Response(status_code=204)


@router.post("/read-all", response_model=ReadAllOut)
async def mark_all_read(
    session_payload: SessionPayload = Depends(get_current_session),
    session: AsyncSession = Depends(get_tenant_session),
) -> ReadAllOut:
    updated = await NotificationService(session).mark_all_read(session_payload["customer_login"])
    return ReadAllOut(updated=updated)
