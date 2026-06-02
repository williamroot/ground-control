"""POST /v1/admin/auth/login|logout — auth de agente Znuny, emite gsid_adm.

Spec #1G-a / ADR D19. Contrato Pydantic CONGELADO na Fase 0; T1.A preenche o
corpo (valida no GI via `authenticate_agent`, emite o cookie `gsid_adm`).
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel

from gerti_sidecar.config import Settings, get_settings

router = APIRouter(prefix="/admin/auth", tags=["admin"])


class AdminLoginBody(BaseModel):
    login: str
    password: str


@router.post("/login")
async def admin_login(
    body: AdminLoginBody,
    response: Response,
    settings: Settings = Depends(get_settings),
) -> dict[str, str]:
    raise HTTPException(status_code=501, detail="not_implemented")  # T1.A


@router.post("/logout", status_code=204)
async def admin_logout(
    response: Response,
    settings: Settings = Depends(get_settings),
) -> Response:
    raise HTTPException(status_code=501, detail="not_implemented")  # T1.A
