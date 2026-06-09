"""Router de ativos CMDB (Spec #1K Fase 2).

/v1/assets     GET  — lista Config Items do tenant logado (escopo server-trusted).
/v1/assets/{id} GET  — detalhe de um CI; ZnunyWriteError → 404 (anti-IDOR),
                       ZnunyUnavailable → 503.

Auth: get_current_session (qualquer papel logado, helpdesk ou admin).
O customer_id vem de request.state.tenant.znuny_customer_id — nunca do cliente.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request

from gerti_sidecar.auth.session import SessionPayload, get_current_session
from gerti_sidecar.integrations import znuny_ticket
from gerti_sidecar.integrations.znuny_customer_admin import ZnunyUnavailable, ZnunyWriteError
from gerti_sidecar.models import Tenant

router = APIRouter(prefix="/assets", tags=["assets"])


def _customer_id(request: Request) -> str:
    tenant: Tenant = request.state.tenant
    return tenant.znuny_customer_id


@router.get("")
async def list_assets(
    request: Request,
    _session: SessionPayload = Depends(get_current_session),
) -> list[dict[str, object]]:
    customer_id = _customer_id(request)
    try:
        rows = await znuny_ticket.config_item_search(customer_id=customer_id)
    except ZnunyUnavailable as exc:
        raise HTTPException(status_code=503, detail="znuny_unavailable") from exc
    return [
        {
            "znuny_config_item_id": r.id,
            "number": r.number,
            "class_": r.class_,
            "name": r.name,
            "deploy_state": r.deploy_state,
            "inci_state": r.inci_state,
        }
        for r in rows
    ]


@router.get("/{config_item_id}")
async def get_asset(
    config_item_id: int,
    request: Request,
    _session: SessionPayload = Depends(get_current_session),
) -> dict[str, object]:
    customer_id = _customer_id(request)
    try:
        d = await znuny_ticket.config_item_get(
            config_item_id=config_item_id, customer_id=customer_id
        )
    except ZnunyWriteError as exc:
        raise HTTPException(status_code=404, detail="asset_not_found") from exc
    except ZnunyUnavailable as exc:
        raise HTTPException(status_code=503, detail="znuny_unavailable") from exc
    return {
        "znuny_config_item_id": d.id,
        "number": d.number,
        "class_": d.class_,
        "name": d.name,
        "deploy_state": d.deploy_state,
        "inci_state": d.inci_state,
        "customer_id": d.customer_id,
        "created": d.created,
        "attributes": d.attributes,
    }
