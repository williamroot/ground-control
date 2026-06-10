# apps/sidecar/src/gerti_sidecar/routers/ticketing_meta.py
"""Catálogo para o formulário de abertura (Spec #1E) — NÃO-admin.

/v1/ticketing/contracts: contratos ATIVOS selecionáveis (qualquer papel logado).
Diferente de /v1/contracts (#1F-b, require_admin): aqui devolve só o necessário
ao dropdown, sob RLS por tenant. /v1/ticketing/form-meta: serviços/prioridades/
tipos do Znuny via GI.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from gerti_sidecar import db
from gerti_sidecar.auth.session import SessionPayload, get_current_session
from gerti_sidecar.config import Settings, get_ollama_client, get_settings
from gerti_sidecar.db import get_tenant_session
from gerti_sidecar.domain.ai_service import AiService
from gerti_sidecar.domain.consumption_service import ConsumptionService
from gerti_sidecar.domain.errors import AiRateLimited
from gerti_sidecar.integrations import znuny_ticket
from gerti_sidecar.integrations.ollama import OllamaDisabled, OllamaUnavailable
from gerti_sidecar.integrations.znuny_customer_admin import ZnunyUnavailable, ZnunyWriteError
from gerti_sidecar.models import Contract
from gerti_sidecar.models.enums import ContractStatus

router = APIRouter(prefix="/ticketing", tags=["ticketing"])


class SelectableContract(BaseModel):
    id: uuid.UUID
    code: str
    type: str
    saldo_label: str | None


@router.get("/contracts", response_model=list[SelectableContract])
async def selectable_contracts(
    _session: SessionPayload = Depends(get_current_session),
    session: AsyncSession = Depends(get_tenant_session),
) -> list[SelectableContract]:
    rows = await session.execute(
        select(Contract).where(Contract.status == ContractStatus.active).order_by(Contract.code)
    )
    cons = ConsumptionService(session)
    out: list[SelectableContract] = []
    for contract in rows.scalars().all():
        bal = await cons.balance(contract.id)
        label = None if bal.remaining is None else f"{bal.kind} {bal.remaining:g}"
        out.append(
            SelectableContract(
                id=contract.id,
                code=contract.code,
                type=str(contract.type.value),
                saldo_label=label,
            )
        )
    return out


class FormMeta(BaseModel):
    services: list[dict[str, object]]
    priorities: list[dict[str, object]]
    types: list[dict[str, object]]
    # #1S: a UI usa esta flag p/ mostrar/ocultar o botão "Melhorar com IA".
    ai_assist_enabled: bool = False


@router.get("/form-meta", response_model=FormMeta)
async def form_meta(
    session_payload: SessionPayload = Depends(get_current_session),
    settings: Settings = Depends(get_settings),
) -> FormMeta:
    try:
        meta = await znuny_ticket.form_meta(customer_user=session_payload["znuny_login"])
    except ZnunyUnavailable as exc:
        raise HTTPException(status_code=503, detail="znuny_unavailable") from exc
    except ZnunyWriteError as exc:
        raise HTTPException(status_code=502, detail="znuny_form_meta_error") from exc
    return FormMeta(
        services=meta["services"],
        priorities=meta["priorities"],
        types=meta["types"],
        ai_assist_enabled=bool(settings.ai_features_enabled),
    )


class AssistBody(BaseModel):
    title: str | None = None
    body: str


class AssistOut(BaseModel):
    title: str
    body: str


def _admin_factory() -> async_sessionmaker[AsyncSession]:
    if db.AdminSessionLocal is None:
        raise HTTPException(status_code=503, detail="admin_db_unavailable")
    return db.AdminSessionLocal


@router.post("/assist", response_model=AssistOut)
async def assist(
    payload: AssistBody,
    session: SessionPayload = Depends(get_current_session),
    settings: Settings = Depends(get_settings),
) -> AssistOut:
    """#1S — assistente de escrita do portal (opt-in, cliente-facing, rate-limited).

    A saída é um RASCUNHO (título+corpo) que o cliente edita e envia manualmente —
    nunca auto-submete. Defesa anti-injeção no AiService/prompts; sem tools.
    """
    # Kill-switch global: feature oculta (404) quando desligada.
    if not settings.ai_features_enabled:
        raise HTTPException(status_code=404, detail="ai_features_disabled")
    title = (payload.title or "").strip()
    body = payload.body.strip()
    if not body:
        raise HTTPException(status_code=400, detail="empty_body")
    factory = _admin_factory()
    async with factory() as s:
        svc = AiService(s, get_ollama_client(settings), gi=None)
        try:
            result = await svc.assist_ticket(
                tenant_id=uuid.UUID(session["tenant_id"]),
                customer_login=session["znuny_login"],
                title=title,
                body=body,
            )
        except AiRateLimited as exc:
            await s.commit()  # persiste o log se houver
            raise HTTPException(status_code=429, detail="rate_limited") from exc
        except (OllamaDisabled, OllamaUnavailable) as exc:
            await s.commit()  # persiste o log ok=False
            raise HTTPException(status_code=503, detail="ai_unavailable") from exc
        await s.commit()
        return AssistOut(title=result["title"], body=result["body"])
