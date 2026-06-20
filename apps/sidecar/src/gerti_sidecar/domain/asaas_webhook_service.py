"""Processamento de webhooks do Asaas (Spec #2).

Idempotente por `event_id` (gerti.asaas_webhook_event, UNIQUE). Mapeia os eventos
de pagamento para o estado local e, quando o pagamento de uma checkout_session é
recebido, dispara o ProvisioningService (pré-cadastro → paga → provisiona).

Gotcha herdado do projeto de referência: para PIX, `PAYMENT_CONFIRMED` é
intermediário — agimos só no `PAYMENT_RECEIVED`. Para cartão/boleto, ambos valem.
"""

from __future__ import annotations

import datetime as dt
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from gerti_sidecar import db
from gerti_sidecar.domain.provisioning_service import ProvisioningService
from gerti_sidecar.models.contratacao import AsaasWebhookEvent, Payment

# Eventos que processamos (os demais são ack 200 e ignorados).
_PAID_EVENTS = {"PAYMENT_RECEIVED", "PAYMENT_CONFIRMED"}
_PROCESSABLE = _PAID_EVENTS | {"PAYMENT_OVERDUE", "PAYMENT_REFUNDED", "PAYMENT_CREATED"}


def _factory() -> async_sessionmaker[AsyncSession]:
    f = db.AdminSessionLocal or db.SessionLocal
    if f is None:
        raise RuntimeError("db_unavailable")
    return f


class AsaasWebhookService:
    def __init__(self, *, provisioner: ProvisioningService | None = None) -> None:
        self._provisioner = provisioner or ProvisioningService()

    async def handle(
        self, event: dict[str, Any], *, now: dt.datetime | None = None
    ) -> dict[str, Any]:
        now = now or dt.datetime.now(dt.UTC)
        event_id = str(event.get("id") or "")
        event_type = str(event.get("event") or "")
        if not event_id:
            return {"status": "ignored", "reason": "no_event_id"}

        # Idempotência: registra o evento; se já PROCESSED, sai.
        async with _factory()() as s:
            existing = (
                await s.execute(
                    select(AsaasWebhookEvent).where(AsaasWebhookEvent.event_id == event_id)
                )
            ).scalar_one_or_none()
            if existing is not None and existing.status == "processed":
                return {"status": "duplicate"}
            if existing is None:
                # o SELECT acima já abriu a transação; add+commit (sem s.begin()).
                s.add(
                    AsaasWebhookEvent(
                        event_id=event_id,
                        event_type=event_type,
                        payload=event,
                        status="received",
                    )
                )
                await s.commit()

        if event_type not in _PROCESSABLE:
            await self._mark(event_id, "processed", now)
            return {"status": "ignored", "reason": "not_processable"}

        try:
            result = await self._dispatch(event, event_type, now=now)
        except Exception as exc:
            await self._mark(event_id, "failed", now, error=str(exc)[:500])
            raise
        await self._mark(event_id, "processed", now)
        return result

    async def _dispatch(
        self, event: dict[str, Any], event_type: str, *, now: dt.datetime
    ) -> dict[str, Any]:
        payment = event.get("payment") or {}
        asaas_payment_id = str(payment.get("id") or "")
        if not asaas_payment_id:
            return {"status": "ignored", "reason": "no_payment"}

        # PIX: só RECEIVED confirma (CONFIRMED é intermediário).
        billing_type = str(payment.get("billingType") or "")
        is_paid_event = event_type in _PAID_EVENTS and not (
            billing_type == "PIX" and event_type == "PAYMENT_CONFIRMED"
        )

        async with _factory()() as s:
            async with s.begin():
                pay = (
                    await s.execute(
                        select(Payment).where(Payment.asaas_payment_id == asaas_payment_id)
                    )
                ).scalar_one_or_none()
                if pay is not None:
                    if event_type == "PAYMENT_OVERDUE":
                        pay.status = "overdue"
                    elif event_type == "PAYMENT_REFUNDED":
                        pay.status = "refunded"
                    elif is_paid_event:
                        pay.status = "received"
                        pay.paid_at = now
                checkout_session_id = pay.checkout_session_id if pay is not None else None

        # Provisiona quando uma contratação foi paga.
        if is_paid_event and checkout_session_id is not None:
            tenant_id = await self._provisioner.provision(checkout_session_id, now=now)
            return {"status": "provisioned", "tenant_id": str(tenant_id)}

        # Pagamento recorrente vinculado a fatura/contrato (#1P) — fase 2.
        return {"status": "ok", "event": event_type}

    async def _mark(
        self, event_id: str, status: str, now: dt.datetime, *, error: str | None = None
    ) -> None:
        async with _factory()() as s:
            async with s.begin():
                row = (
                    await s.execute(
                        select(AsaasWebhookEvent).where(AsaasWebhookEvent.event_id == event_id)
                    )
                ).scalar_one_or_none()
                if row is not None:
                    row.status = status
                    row.error = error
                    if status in ("processed", "failed"):
                        row.processed_at = now
