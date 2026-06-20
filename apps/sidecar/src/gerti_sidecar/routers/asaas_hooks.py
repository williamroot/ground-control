"""Webhook do Asaas (Spec #2) — POST /v1/hooks/asaas/payment.

Auth por token (header `asaas-access-token` == ASAAS_WEBHOOK_TOKEN), padrão do
Asaas (compare_digest, constant-time). `/v1/hooks` já está na allowlist do
TenantMiddleware. SEMPRE responde 200 (mesmo evento ignorado); idempotência e
processamento ficam no AsaasWebhookService. Token inválido → 401.
"""

from __future__ import annotations

import hmac
from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException, Request, Response

from gerti_sidecar.config import Settings, get_settings
from gerti_sidecar.domain.asaas_webhook_service import AsaasWebhookService

router = APIRouter(prefix="/hooks", tags=["hooks"])


@router.post("/asaas/payment")
async def asaas_payment(
    request: Request,
    response: Response,
    asaas_access_token: str | None = Header(default=None, alias="asaas-access-token"),
    settings: Settings = Depends(get_settings),
) -> dict[str, Any]:
    expected = settings.asaas_webhook_token
    if (
        not expected
        or not asaas_access_token
        or not hmac.compare_digest(asaas_access_token, expected)
    ):
        raise HTTPException(status_code=401, detail="invalid_token")
    try:
        event = await request.json()
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="invalid_payload") from exc
    if not isinstance(event, dict):
        raise HTTPException(status_code=400, detail="invalid_payload")
    try:
        result = await AsaasWebhookService().handle(event)
    except Exception:
        response.status_code = 200
        return {"status": "error_logged"}
    return result
