"""Contratação self-service (Spec #2) — rotas PÚBLICAS (sem login, sem tenant).

`/v1/checkout/*` está na allowlist do TenantMiddleware (público; o tenant pode
nem existir ainda — modelo pré-cadastro → paga → webhook provisiona). Asaas off
(ASAAS_ENABLED=false / sem key) → 404 (fail-safe).
"""

from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from gerti_sidecar.config import Settings, get_settings
from gerti_sidecar.domain.checkout_service import CheckoutInput, CheckoutService
from gerti_sidecar.domain.errors import CheckoutConflict, CheckoutDisabled, CheckoutError
from gerti_sidecar.integrations.asaas_client import AsaasError, AsaasUnavailable

router = APIRouter(prefix="/checkout", tags=["checkout"])


class CompanyIn(BaseModel):
    legal_name: str
    trade_name: str
    document: str


class BrandingIn(BaseModel):
    display_name: str | None = None
    primary_color: str | None = None
    accent_color: str | None = None
    support_email: str | None = None
    logo_url: str | None = None


class AdminIn(BaseModel):
    email: str
    first_name: str
    last_name: str
    password: str


class CardIn(BaseModel):
    holderName: str
    number: str
    expiryMonth: str
    expiryYear: str
    ccv: str
    holderInfo: dict[str, Any] | None = None


class StartCheckoutBody(BaseModel):
    plan_slug: str
    billing_type: str  # PIX | BOLETO | CREDIT_CARD
    company: CompanyIn
    subdomain: str
    znuny_customer_id: str
    admin: AdminIn
    branding: BrandingIn | None = None
    credit_card: CardIn | None = None


def _svc(settings: Settings) -> CheckoutService:
    return CheckoutService(settings)


@router.get("/plans")
async def list_plans(
    audience: str | None = None, settings: Settings = Depends(get_settings)
) -> list[dict[str, Any]]:
    if not settings.asaas_enabled or not settings.asaas_api_key:
        raise HTTPException(status_code=404, detail="checkout_disabled")
    plans = await _svc(settings).list_public_plans(audience)
    return [
        {
            "slug": p.slug,
            "name": p.name,
            "description": p.description,
            "audience": p.audience,
            "billing_mode": p.billing_mode,
            "price_cents": p.price_cents,
            "cycle": p.cycle,
        }
        for p in plans
    ]


@router.post("/sessions", status_code=201)
async def start_session(
    body: StartCheckoutBody, request: Request, settings: Settings = Depends(get_settings)
) -> dict[str, Any]:
    applicant: dict[str, Any] = {
        "company": body.company.model_dump(),
        "subdomain": body.subdomain.strip().lower(),
        "znuny_customer_id": body.znuny_customer_id.strip(),
        "branding": body.branding.model_dump() if body.branding else {},
        "admin": body.admin.model_dump(),
    }
    data = CheckoutInput(
        plan_slug=body.plan_slug,
        billing_type=body.billing_type,
        applicant=applicant,
        credit_card=body.credit_card.model_dump() if body.credit_card else None,
        remote_ip=request.client.host if request.client else None,
    )
    try:
        return await _svc(settings).start(data)
    except CheckoutDisabled as exc:
        raise HTTPException(status_code=404, detail="checkout_disabled") from exc
    except CheckoutConflict as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except AsaasError as exc:
        raise HTTPException(status_code=exc.status, detail=exc.messages) from exc
    except AsaasUnavailable as exc:
        raise HTTPException(status_code=503, detail="payment_provider_unavailable") from exc
    except CheckoutError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/sessions/{session_id}")
async def session_status(
    session_id: uuid.UUID, token: str, settings: Settings = Depends(get_settings)
) -> dict[str, Any]:
    if not settings.asaas_enabled:
        raise HTTPException(status_code=404, detail="checkout_disabled")
    try:
        return await _svc(settings).get_status(session_id, token)
    except CheckoutConflict as exc:
        raise HTTPException(status_code=404, detail="not_found") from exc
