"""GET/PUT /v1/me/preferences — preferências do usuário no Portal (Spec #3 V3).

`get_or_create` idempotente: a primeira leitura já cria a linha com os
defaults da tabela. `PUT` aceita corpo parcial — campos omitidos/`null`
não são alterados; `theme` fora do enum -> 422 (Pydantic Literal).
"""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from gerti_sidecar.auth.session import SessionPayload, get_current_session
from gerti_sidecar.db import get_tenant_session
from gerti_sidecar.domain.preference_service import PreferenceService
from gerti_sidecar.models import UserPreference

router = APIRouter(prefix="/me/preferences", tags=["portal"])


class PreferenceOut(BaseModel):
    theme: str
    email_notifications: bool
    sla_alerts: bool
    ticket_updates: bool
    contract_alerts: bool
    invoice_alerts: bool
    weekly_report: bool


class PreferenceUpdate(BaseModel):
    theme: Literal["light", "dark", "system"] | None = None
    email_notifications: bool | None = None
    sla_alerts: bool | None = None
    ticket_updates: bool | None = None
    contract_alerts: bool | None = None
    invoice_alerts: bool | None = None
    weekly_report: bool | None = None


def _out(p: UserPreference) -> PreferenceOut:
    return PreferenceOut(
        theme=p.theme,
        email_notifications=p.email_notifications,
        sla_alerts=p.sla_alerts,
        ticket_updates=p.ticket_updates,
        contract_alerts=p.contract_alerts,
        invoice_alerts=p.invoice_alerts,
        weekly_report=p.weekly_report,
    )


@router.get("", response_model=PreferenceOut)
async def get_preferences(
    session_payload: SessionPayload = Depends(get_current_session),
    session: AsyncSession = Depends(get_tenant_session),
) -> PreferenceOut:
    pref = await PreferenceService(session).get_or_create(session_payload["customer_login"])
    return _out(pref)


@router.put("", response_model=PreferenceOut)
async def update_preferences(
    body: PreferenceUpdate,
    session_payload: SessionPayload = Depends(get_current_session),
    session: AsyncSession = Depends(get_tenant_session),
) -> PreferenceOut:
    pref = await PreferenceService(session).update(
        session_payload["customer_login"],
        **body.model_dump(exclude_unset=True),
    )
    return _out(pref)
