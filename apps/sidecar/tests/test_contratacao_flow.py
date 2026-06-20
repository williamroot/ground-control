"""Fluxo de contratação ponta-a-ponta (Spec #2) com testcontainer.

Asaas fake (sem rede), onboarding GI mockado. Cobre: start() cria checkout_session
+ payment e devolve PIX; webhook PAYMENT_RECEIVED provisiona (tenant + contrato);
idempotência (reentrega = duplicate, não reprovisiona).
"""

from __future__ import annotations

from typing import Any

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from gerti_sidecar import db
from gerti_sidecar.config import get_settings
from gerti_sidecar.domain.asaas_webhook_service import AsaasWebhookService
from gerti_sidecar.domain.checkout_service import CheckoutInput, CheckoutService
from gerti_sidecar.integrations import znuny_customer_admin as gi
from gerti_sidecar.models.contract import Contract
from gerti_sidecar.models.contratacao import CheckoutSession, Payment, Plan
from gerti_sidecar.models.tenant import Tenant
from gerti_sidecar.models.znuny_instance import ZnunyInstance


class FakeAsaas:
    """Implementa só o que o CheckoutService usa; sem rede."""

    async def find_or_create_customer(self, **kw: Any) -> dict[str, Any]:
        return {"id": "cus_fake"}

    async def tokenize_credit_card(self, data: dict[str, Any]) -> dict[str, Any]:
        return {"creditCardToken": "tok_fake"}

    async def create_payment(self, **kw: Any) -> dict[str, Any]:
        return {"id": "pay_fake", "invoiceUrl": "https://asaas/i/pay_fake"}

    async def create_subscription(self, **kw: Any) -> dict[str, Any]:
        return {"id": "sub_fake", "invoiceUrl": "https://asaas/i/sub_fake"}

    async def get_pix_qrcode(self, payment_id: str) -> dict[str, Any]:
        return {
            "encodedImage": "b64png",
            "payload": "00020126...pix",
            "expirationDate": "2026-07-01",
        }

    async def get_billing_info(self, payment_id: str) -> dict[str, Any]:
        return {"bankSlip": {"bankSlipUrl": "https://b/slip", "identificationField": "0001"}}


async def _seed(factory: async_sessionmaker[AsyncSession]) -> None:
    async with factory() as s:
        async with s.begin():
            s.add(
                ZnunyInstance(
                    name="t",
                    base_url="https://znuny.test",
                    db_dsn_secret_ref="",
                    webservice_token_secret_ref="",
                    webhook_signing_secret_ref="",
                    mode="pool",
                    status="active",
                )
            )
            s.add(
                Plan(
                    slug="horas-40",
                    name="Pacote 40h",
                    audience="end_client",
                    contract_type="hour_bank",
                    billing_mode="one_off",
                    price_cents=200000,
                    initial_hours=40,
                    public=True,
                    active=True,
                )
            )


def _applicant() -> dict[str, Any]:
    return {
        "company": {
            "legal_name": "ACME Ltda",
            "trade_name": "ACME",
            "document": "12.345.678/0001-90",
        },
        "subdomain": "acme",
        "znuny_customer_id": "ACME",
        "branding": {"display_name": "ACME", "primary_color": "#111", "accent_color": "#222"},
        "admin": {
            "email": "admin@acme.com",
            "first_name": "Ana",
            "last_name": "Adm",
            "password": "S3nha@2026",
        },
    }


@pytest.mark.asyncio
async def test_checkout_then_webhook_provisions(engine, monkeypatch) -> None:
    monkeypatch.setenv("ASAAS_ENABLED", "true")
    monkeypatch.setenv("ASAAS_API_KEY", "test-key")
    monkeypatch.setenv("ENVIRONMENT", "test")
    get_settings.cache_clear()

    factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    monkeypatch.setattr(db, "AdminSessionLocal", factory)
    monkeypatch.setattr(db, "SessionLocal", factory)

    # onboarding GI: no-ops (sem Znuny real)
    async def _noop(*a: Any, **k: Any) -> None:
        return None

    monkeypatch.setattr(gi, "create_customer_company", _noop)
    monkeypatch.setattr(gi, "create_customer_user", _noop)
    monkeypatch.setattr(gi, "set_password", _noop)

    await _seed(factory)

    # 1) start checkout (PIX one_off)
    svc = CheckoutService(get_settings(), asaas=FakeAsaas())
    out = await svc.start(
        CheckoutInput(plan_slug="horas-40", billing_type="PIX", applicant=_applicant())
    )
    assert out["status"] == "awaiting_payment"
    assert out["value_cents"] == 200000
    assert out["pix"]["copy_paste"].startswith("0002")  # QR PIX inline
    session_id = out["session_id"]

    async with factory() as s:
        pay = (
            await s.execute(select(Payment).where(Payment.asaas_payment_id == "pay_fake"))
        ).scalar_one()
        assert str(pay.checkout_session_id) == session_id
        assert pay.status == "pending"

    # 2) webhook PAYMENT_RECEIVED → provisiona
    event = {
        "id": "evt_1",
        "event": "PAYMENT_RECEIVED",
        "payment": {"id": "pay_fake", "billingType": "PIX"},
    }
    result = await AsaasWebhookService().handle(event)
    assert result["status"] == "provisioned"

    async with factory() as s:
        tenant = (await s.execute(select(Tenant).where(Tenant.subdomain == "acme"))).scalar_one()
        assert tenant.znuny_customer_id == "ACME"
        contracts = (
            (await s.execute(select(Contract).where(Contract.tenant_id == tenant.id)))
            .scalars()
            .all()
        )
        assert len(contracts) == 1
        assert contracts[0].type == "hour_bank"
        cs = await s.get(CheckoutSession, pay.checkout_session_id)
        assert cs is not None and cs.status == "provisioned"
        # senha do admin removida do applicant (at-rest) após provisionar
        assert "password" not in (cs.applicant.get("admin") or {})
        pay2 = (
            await s.execute(select(Payment).where(Payment.asaas_payment_id == "pay_fake"))
        ).scalar_one()
        assert pay2.status == "received" and pay2.tenant_id == tenant.id

    # 3) idempotência: reentrega do MESMO evento não reprovisiona
    again = await AsaasWebhookService().handle(event)
    assert again["status"] == "duplicate"
    async with factory() as s:
        tenants = (
            (await s.execute(select(Tenant).where(Tenant.subdomain == "acme"))).scalars().all()
        )
        assert len(tenants) == 1  # não duplicou


@pytest.mark.asyncio
async def test_pix_confirmed_does_not_provision(engine, monkeypatch) -> None:
    """PIX: PAYMENT_CONFIRMED é intermediário — só RECEIVED provisiona."""
    monkeypatch.setenv("ASAAS_ENABLED", "true")
    monkeypatch.setenv("ASAAS_API_KEY", "test-key")
    monkeypatch.setenv("ENVIRONMENT", "test")
    get_settings.cache_clear()
    factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    monkeypatch.setattr(db, "AdminSessionLocal", factory)
    monkeypatch.setattr(db, "SessionLocal", factory)
    event = {
        "id": "evt_confirmed",
        "event": "PAYMENT_CONFIRMED",
        "payment": {"id": "pay_x", "billingType": "PIX"},
    }
    result = await AsaasWebhookService().handle(event)
    assert result["status"] in ("ok", "ignored")  # não provisiona
