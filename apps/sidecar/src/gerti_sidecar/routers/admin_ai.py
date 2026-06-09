"""Router /v1/admin/ai/* (Spec #1N) — sumarização + resposta sugerida (agente).

Opt-in: se settings.ai_features_enabled for False, os endpoints respondem 404
(feature oculta). Sessão de AGENTE (get_admin_session, cross-tenant); usa
AdminSessionLocal (BYPASSRLS) p/ gravar ai_generation_log. O conteúdo do ticket
é puxado via GI de agente e enviado ao LLM com defesa contra prompt injection
(AiService/prompts). A saída é texto (rascunho/resumo) — NUNCA auto-enviada ao
cliente nem usada como ação.

Mapeamento de erros: OllamaDisabled/OllamaUnavailable/ZnunyUnavailable -> 503;
ZnunyWriteError (ticket não encontrado) -> 404.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from gerti_sidecar import db
from gerti_sidecar.auth.admin_session import AdminSessionPayload, get_admin_session
from gerti_sidecar.config import Settings, get_ollama_client, get_settings
from gerti_sidecar.domain.ai_service import AiService
from gerti_sidecar.integrations import znuny_ticket
from gerti_sidecar.integrations.ollama import OllamaDisabled, OllamaUnavailable
from gerti_sidecar.integrations.znuny_customer_admin import ZnunyUnavailable, ZnunyWriteError

router = APIRouter(prefix="/admin/ai", tags=["admin", "ai"])


class SummarizeBody(BaseModel):
    ticket_id: int


class SuggestReplyBody(BaseModel):
    ticket_id: int
    instruction: str | None = None


class AiTextOut(BaseModel):
    text: str


class AiEnabledOut(BaseModel):
    enabled: bool


def _require_enabled(settings: Settings) -> None:
    # Kill-switch global: feature oculta (404) quando desligada.
    if not settings.ai_features_enabled:
        raise HTTPException(status_code=404, detail="ai_features_disabled")


def _admin_factory() -> async_sessionmaker[AsyncSession]:
    if db.AdminSessionLocal is None:
        raise HTTPException(status_code=503, detail="admin_db_unavailable")
    return db.AdminSessionLocal


@router.get("/enabled", response_model=AiEnabledOut)
async def ai_enabled(
    admin: AdminSessionPayload = Depends(get_admin_session),
    settings: Settings = Depends(get_settings),
) -> AiEnabledOut:
    """Flag p/ o console esconder/exibir o painel de IA (não 404: sempre responde)."""
    return AiEnabledOut(enabled=bool(settings.ai_features_enabled))


@router.post("/summarize", response_model=AiTextOut)
async def summarize(
    body: SummarizeBody,
    admin: AdminSessionPayload = Depends(get_admin_session),
    settings: Settings = Depends(get_settings),
) -> AiTextOut:
    _require_enabled(settings)
    factory = _admin_factory()
    async with factory() as s:
        svc = AiService(s, get_ollama_client(settings), znuny_ticket)
        try:
            text = await svc.summarize(
                znuny_ticket_id=body.ticket_id, agent_login=admin["agent_login"]
            )
        except (OllamaDisabled, OllamaUnavailable, ZnunyUnavailable) as exc:
            await s.commit()  # persiste o log ok=False
            raise HTTPException(status_code=503, detail="ai_unavailable") from exc
        except ZnunyWriteError as exc:
            await s.commit()
            raise HTTPException(status_code=404, detail="ticket_not_found") from exc
        await s.commit()
        return AiTextOut(text=text)


@router.post("/suggest-reply", response_model=AiTextOut)
async def suggest_reply(
    body: SuggestReplyBody,
    admin: AdminSessionPayload = Depends(get_admin_session),
    settings: Settings = Depends(get_settings),
) -> AiTextOut:
    _require_enabled(settings)
    factory = _admin_factory()
    async with factory() as s:
        svc = AiService(s, get_ollama_client(settings), znuny_ticket)
        try:
            text = await svc.suggest_reply(
                znuny_ticket_id=body.ticket_id,
                agent_login=admin["agent_login"],
                instruction=body.instruction,
            )
        except (OllamaDisabled, OllamaUnavailable, ZnunyUnavailable) as exc:
            await s.commit()
            raise HTTPException(status_code=503, detail="ai_unavailable") from exc
        except ZnunyWriteError as exc:
            await s.commit()
            raise HTTPException(status_code=404, detail="ticket_not_found") from exc
        await s.commit()
        return AiTextOut(text=text)
