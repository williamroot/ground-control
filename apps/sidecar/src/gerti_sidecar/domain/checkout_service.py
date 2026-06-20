"""Contratação self-service (Spec #2) — orquestra o checkout via Asaas.

Modelo pré-cadastro → paga → webhook provisiona: aqui criamos a checkout_session
(SEM tocar Znuny/tenant), o customer + a cobrança no Asaas (assinatura p/ planos
recorrentes; avulsa p/ pré-pago) e devolvemos os meios de pagamento (QR PIX /
boleto / link Asaas). O provisionamento acontece no webhook (provisioning_service).
"""

from __future__ import annotations

import dataclasses
import datetime as dt
import secrets
import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from gerti_sidecar import db
from gerti_sidecar.config import Settings, get_asaas_client
from gerti_sidecar.domain.errors import CheckoutConflict, CheckoutDisabled, CheckoutError
from gerti_sidecar.integrations.asaas_client import AsaasClient
from gerti_sidecar.models.contratacao import CheckoutSession, Payment, Plan
from gerti_sidecar.models.tenant import Tenant


@dataclasses.dataclass(slots=True)
class CheckoutInput:
    plan_slug: str
    billing_type: str  # PIX | BOLETO | CREDIT_CARD
    # company{legal_name,trade_name,document}, subdomain, znuny_customer_id,
    # branding{}, admin{email,first_name,last_name,password}
    applicant: dict[str, Any]
    target_tenant_id: uuid.UUID | None = None
    credit_card: dict[str, Any] | None = (
        None  # holderName,number,expiryMonth,expiryYear,ccv (+holderInfo)
    )
    remote_ip: str | None = None


class CheckoutService:
    def __init__(self, settings: Settings, *, asaas: AsaasClient | None = None) -> None:
        self._settings = settings
        self._asaas = asaas or get_asaas_client(settings)

    def _factory(self) -> async_sessionmaker[AsyncSession]:
        f = db.AdminSessionLocal or db.SessionLocal
        if f is None:
            raise CheckoutError("db_unavailable")
        return f

    def _ensure_enabled(self) -> None:
        if not self._settings.asaas_enabled or not self._settings.asaas_api_key:
            raise CheckoutDisabled("contratação desabilitada")

    async def list_public_plans(self, audience: str | None = None) -> list[Plan]:
        async with self._factory()() as s:
            stmt = select(Plan).where(Plan.active.is_(True), Plan.public.is_(True))
            if audience:
                stmt = stmt.where(Plan.audience == audience)
            return list((await s.execute(stmt)).scalars().all())

    async def start(self, data: CheckoutInput, *, now: dt.datetime | None = None) -> dict[str, Any]:
        self._ensure_enabled()
        now = now or dt.datetime.now(dt.UTC)
        async with self._factory()() as s:
            plan = (
                await s.execute(
                    select(Plan).where(Plan.slug == data.plan_slug, Plan.active.is_(True))
                )
            ).scalar_one_or_none()
            if plan is None:
                raise CheckoutConflict(f"plano {data.plan_slug!r} inexistente ou inativo")
            # Conflitos de cadastro ANTES de cobrar (mesmas invariantes do onboarding).
            if data.target_tenant_id is None:
                sub = str(data.applicant.get("subdomain") or "")
                cid = str(data.applicant.get("znuny_customer_id") or "")
                if not sub or not cid or not (data.applicant.get("company") or {}).get("document"):
                    raise CheckoutError("dados de cadastro incompletos")
                clash = (
                    await s.execute(
                        select(Tenant.id).where(
                            (Tenant.subdomain == sub) | (Tenant.znuny_customer_id == cid)
                        )
                    )
                ).first()
                if clash is not None:
                    raise CheckoutConflict("subdomínio ou identificador já em uso")
            plan_id = plan.id
            plan_name: str = plan.name
            plan_billing_mode: str = plan.billing_mode
            plan_price_cents: int = plan.price_cents
            plan_cycle: str = plan.cycle or "MONTHLY"

        # Customer no Asaas
        company = data.applicant.get("company") or {}
        admin = data.applicant.get("admin") or {}
        customer = await self._asaas.find_or_create_customer(
            name=str(
                company.get("trade_name")
                or company.get("legal_name")
                or admin.get("email")
                or "Cliente"
            ),
            cpf_cnpj=str(company.get("document") or ""),
            email=str(admin.get("email") or ""),
            external_reference=f"checkout:{data.plan_slug}",
        )
        customer_id = str(customer["id"])

        # Token de cartão (nunca persistimos o PAN)
        card_token: str | None = None
        if data.billing_type == "CREDIT_CARD" and data.credit_card:
            tok = await self._asaas.tokenize_credit_card(data.credit_card)
            card_token = str(tok.get("creditCardToken") or "")

        due = (now.date() + dt.timedelta(days=3)).isoformat()
        description = f"Contratação {plan_name}"
        session_id = uuid.uuid4()
        ext_ref = f"checkout:{session_id}"

        if plan_billing_mode == "subscription":
            created = await self._asaas.create_subscription(
                customer_id=customer_id,
                value_cents=plan_price_cents,
                next_due_date=due,
                billing_type=data.billing_type,
                cycle=plan_cycle,
                description=description,
                external_reference=ext_ref,
                credit_card_token=card_token,
            )
            asaas_subscription_id = str(created.get("id") or "")
            asaas_payment_id = None
        else:
            created = await self._asaas.create_payment(
                customer_id=customer_id,
                value_cents=plan_price_cents,
                due_date=due,
                billing_type=data.billing_type,
                description=description,
                external_reference=ext_ref,
                credit_card_token=card_token,
                remote_ip=data.remote_ip,
            )
            asaas_subscription_id = None
            asaas_payment_id = str(created.get("id") or "")

        invoice_url = created.get("invoiceUrl")
        guest_token = secrets.token_urlsafe(24)

        # Persiste sessão + pagamento (BYPASSRLS; tenant ainda não existe)
        async with self._factory()() as s:
            async with s.begin():
                cs = CheckoutSession(
                    id=session_id,
                    plan_id=plan_id,
                    status="awaiting_payment",
                    target_tenant_id=data.target_tenant_id,
                    applicant=data.applicant,
                    billing_type=data.billing_type,
                    asaas_customer_id=customer_id,
                    asaas_subscription_id=asaas_subscription_id,
                    asaas_payment_id=asaas_payment_id,
                    guest_token=guest_token,
                    expires_at=now + dt.timedelta(hours=24),
                )
                s.add(cs)
                if asaas_payment_id:
                    s.add(
                        Payment(
                            checkout_session_id=session_id,
                            billing_type=data.billing_type,
                            status="pending",
                            value_cents=plan_price_cents,
                            asaas_payment_id=asaas_payment_id,
                            asaas_subscription_id=asaas_subscription_id,
                            external_reference=ext_ref,
                        )
                    )

        out: dict[str, Any] = {
            "session_id": str(session_id),
            "guest_token": guest_token,
            "status": "awaiting_payment",
            "billing_type": data.billing_type,
            "value_cents": plan_price_cents,
            "invoice_url": invoice_url,
        }
        # Meios de pagamento inline (best-effort; falha não derruba o checkout)
        if asaas_payment_id:
            out.update(await self._payment_details(asaas_payment_id, data.billing_type))
        return out

    async def _payment_details(self, payment_id: str, billing_type: str) -> dict[str, Any]:
        try:
            if billing_type == "PIX":
                q = await self._asaas.get_pix_qrcode(payment_id)
                return {
                    "pix": {
                        "qrcode_base64": q.get("encodedImage"),
                        "copy_paste": q.get("payload"),
                        "expiration": q.get("expirationDate"),
                    }
                }
            if billing_type == "BOLETO":
                b = await self._asaas.get_billing_info(payment_id)
                slip = b.get("bankSlip") or {}
                return {
                    "boleto": {
                        "url": slip.get("bankSlipUrl"),
                        "linha_digitavel": slip.get("identificationField"),
                        "barcode": slip.get("barCode"),
                    }
                }
        except Exception:
            return {}
        return {}

    async def get_status(self, session_id: uuid.UUID, guest_token: str) -> dict[str, Any]:
        async with self._factory()() as s:
            cs = await s.get(CheckoutSession, session_id)
        if cs is None or not secrets.compare_digest(cs.guest_token, guest_token):
            raise CheckoutConflict("sessão não encontrada")
        out: dict[str, Any] = {"session_id": str(session_id), "status": cs.status}
        if cs.status == "provisioned" and cs.provisioned_tenant_id is not None:
            sub = str((cs.applicant or {}).get("subdomain") or "")
            out["subdomain"] = sub
            out["portal_url"] = f"https://{sub}.was.dev.br/" if sub else None
        return out
