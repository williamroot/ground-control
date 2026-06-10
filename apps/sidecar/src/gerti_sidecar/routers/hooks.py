"""Webhooks Znuny→sidecar (Spec #1Q, Task 4).

POST /v1/hooks/znuny/ticket-event: o Event module GertiAutomation do Znuny posta
aqui em cada evento de ticket, assinado HMAC-SHA256 (header X-Gerti-Signature)
com o segredo compartilhado.

Fluxo:
1. Lê o **raw body** (bytes exatos que o Znuny assinou).
2. Resolve o segredo de assinatura via `ZnunyInstance.webhook_signing_secret_ref`
   (lookup BYPASSRLS — é diretório, não dado de tenant) e verifica o HMAC
   constant-time. Inválido/ausente → **401**.
3. Resolve o tenant por `customer_id` (== `Tenant.znuny_customer_id`). Não
   resolvido → **202** (aceita e ignora; não vaza qual customer existe).
4. Monta os facts e chama `AutomationEngine.handle(...)`. **200** ao final.

Não exige tenant por subdomínio: `/v1/hooks` está na allowlist do TenantMiddleware
(o tenant vem do `customer_id` assinado). Processamento síncrono no MVP.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from fastapi import APIRouter, HTTPException, Request, Response
from sqlalchemy import select

from gerti_sidecar import db
from gerti_sidecar.domain.automation_service import AutomationEngine
from gerti_sidecar.integrations import znuny_ticket
from gerti_sidecar.integrations.webhook_sig import verify
from gerti_sidecar.models import Tenant, ZnunyInstance

logger = logging.getLogger("gerti_sidecar.hooks")

router = APIRouter(prefix="/hooks", tags=["hooks"])

# Mapa nome-de-evento-Znuny → trigger do sidecar (defesa: só estes são aceitos).
_EVENT_ALIASES = {
    "TicketCreate": "ticket_create",
    "ArticleCreate": "article_create",
    "TicketStateUpdate": "state_update",
    "ticket_create": "ticket_create",
    "article_create": "article_create",
    "state_update": "state_update",
    "escalation": "escalation",
}

# Campos de facts que o engine/avaliador conhecem (espelha ALLOWED_FIELDS).
_FACT_KEYS = (
    "priority",
    "queue",
    "state",
    "type",
    "service",
    "customer_id",
    "title",
    "age_minutes",
    "sla_state",
)


async def _resolve_secret() -> str | None:
    """Segredo de assinatura do ZnunyInstance (lookup BYPASSRLS, diretório)."""
    factory = db.AdminSessionLocal or db.SessionLocal
    if factory is None:
        return None
    async with factory() as s:
        inst = (
            await s.execute(select(ZnunyInstance).order_by(ZnunyInstance.created_at).limit(1))
        ).scalar_one_or_none()
        return inst.webhook_signing_secret_ref if inst else None


async def _resolve_tenant(customer_id: str) -> Tenant | None:
    factory = db.AdminSessionLocal or db.SessionLocal
    if factory is None:
        return None
    async with factory() as s:
        return (
            await s.execute(
                select(Tenant).where(
                    Tenant.znuny_customer_id == customer_id,
                    Tenant.status == "active",
                )
            )
        ).scalar_one_or_none()


@router.post("/znuny/ticket-event")
async def ticket_event(request: Request, response: Response) -> dict[str, Any]:
    raw = await request.body()
    header_sig = request.headers.get("x-gerti-signature")

    secret = await _resolve_secret()
    if not verify(secret or "", raw, header_sig):
        raise HTTPException(status_code=401, detail="invalid_signature")

    try:
        payload = json.loads(raw.decode("utf-8"))
    except (ValueError, UnicodeDecodeError) as exc:
        raise HTTPException(status_code=400, detail="invalid_payload") from exc
    if not isinstance(payload, dict):
        raise HTTPException(status_code=400, detail="invalid_payload")

    raw_event = str(payload.get("event") or "")
    event = _EVENT_ALIASES.get(raw_event)
    customer_id = str(payload.get("customer_id") or "")
    ticket_id_raw = payload.get("ticket_id")

    if event is None or not customer_id or ticket_id_raw is None:
        # payload incompleto: aceita e ignora (não é erro do remetente assinado)
        response.status_code = 202
        return {"status": "ignored", "reason": "incomplete"}

    tenant = await _resolve_tenant(customer_id)
    if tenant is None:
        # tenant desconhecido → 202, sem vazar
        response.status_code = 202
        return {"status": "ignored", "reason": "unknown_tenant"}

    try:
        znuny_ticket_id = int(ticket_id_raw)
    except (TypeError, ValueError):
        response.status_code = 202
        return {"status": "ignored", "reason": "bad_ticket_id"}

    facts = {k: payload[k] for k in _FACT_KEYS if k in payload}
    facts["customer_id"] = customer_id

    engine = AutomationEngine(gi=znuny_ticket, ai_factory=None)
    runs = await engine.handle(tenant, event, facts, znuny_ticket_id=znuny_ticket_id)
    matched = sum(1 for r in runs if r.matched)
    return {"status": "ok", "rules_evaluated": len(runs), "rules_matched": matched}
