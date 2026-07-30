"""POST /v1/admin/auth/login|logout — auth de agente Znuny, emite gsid_adm.

Spec #1G-a / ADR D19. Contrato Pydantic CONGELADO na Fase 0; T1.A preenche o
corpo (valida no GI via `authenticate_agent`, emite o cookie `gsid_adm`).

#2 — login universal (login OU e-mail): tenta `authenticate_agent(identifier,
password)` PRIMEIRO — cobre o login normal E o caso comum de um agente cujo
`UserLogin` já É um e-mail, sem chamada extra ao GI. Só se essa tentativa
falhar E o identifier digitado contiver `@`, resolve o login canônico via
`AdminAgentResolveLogin` (GI, GertiAdmin — `Custom/.../AdminAgentResolveLogin.pm`)
e tenta autenticar de novo com o login resolvido.

PONTO CRÍTICO: a sessão (`gsid_adm`) sempre guarda o LOGIN que efetivamente
autenticou — nunca o e-mail digitado. `agent_login` vira `AgentLogin` em toda
operação GI subsequente do console; se a sessão guardasse o e-mail, o
operador entraria e toda tela quebraria depois (o Znuny não conhece agente
por e-mail).

Não vaza enumeração: e-mail inexistente, e-mail ambíguo (`resolve_agent_login`
devolve `None` para os dois) e senha errada devolvem exatamente o mesmo 401
`invalid_credentials` — a resolução por e-mail nunca aparece no response nem
na mensagem de erro.

`ZnunyUnavailable` (de qualquer uma das duas chamadas GI) → 503.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel

from gerti_sidecar.auth.admin_session import encode_admin_session
from gerti_sidecar.config import Settings, get_settings
from gerti_sidecar.integrations.znuny_admin_people import (
    ZnunyUnavailable as ResolveUnavailable,
)
from gerti_sidecar.integrations.znuny_admin_people import (
    resolve_agent_login,
)
from gerti_sidecar.integrations.znuny_agent_auth import (
    ZnunyUnavailable,
    authenticate_agent,
)

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
    # `resolved_login` começa como o identifier digitado; só muda se a
    # tentativa direta falhar e a resolução por e-mail achar um agente.
    resolved_login = body.login
    try:
        ok = await authenticate_agent(resolved_login, body.password)
        if not ok and "@" in body.login:
            canonical = await resolve_agent_login(body.login)
            if canonical is not None:
                resolved_login = canonical
                ok = await authenticate_agent(resolved_login, body.password)
    except (ZnunyUnavailable, ResolveUnavailable) as exc:
        raise HTTPException(status_code=503, detail="znuny_unavailable") from exc
    if not ok:
        raise HTTPException(status_code=401, detail="invalid_credentials")
    # Guarda o LOGIN CANÔNICO que efetivamente autenticou — nunca o e-mail
    # digitado (ver nota "PONTO CRÍTICO" no docstring do módulo).
    token = encode_admin_session(resolved_login, settings)
    response.set_cookie(
        key=settings.admin_session_cookie_name,
        value=token,
        max_age=settings.session_ttl_seconds,
        httponly=True,
        secure=settings.session_cookie_secure,
        samesite="lax",
        path="/",
    )
    return {"status": "ok"}


@router.post("/logout", status_code=204)
async def admin_logout(
    response: Response,
    settings: Settings = Depends(get_settings),
) -> Response:
    response.delete_cookie(
        key=settings.admin_session_cookie_name,
        httponly=True,
        secure=settings.session_cookie_secure,
        samesite="lax",
        path="/",
    )
    response.status_code = 204
    return response
