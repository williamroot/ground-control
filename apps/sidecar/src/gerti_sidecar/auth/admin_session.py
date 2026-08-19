"""Sessão do Console de Administração (Spec #1G-a) — JWT HS256 + dependency.

Diferente da sessão de cliente (`auth/session.py`):
  • cookie PRÓPRIO `gsid_adm` (NUNCA colide com o `gsid` do cliente);
  • payload `{agent_login, role:"gerti_staff", typ:"admin", exp}`;
  • NÃO é tenant-scoped — o admin (equipe Gerti) opera CROSS-TENANT.

`get_admin_session`: 401 se cookie ausente|inválido|expirado|claim errado.
O claim `typ:"admin"` + role `gerti_staff` isola a sessão admin da de cliente
mesmo que o `SESSION_SECRET` seja compartilhado: um `gsid` de cliente (sem
`typ:"admin"`) NUNCA é aceito em `/v1/admin/*`, e vice-versa.

Congelado no spike R1G (ADR D19). T1.A preenche/endurece (encode/decode/testes).
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Awaitable, Callable
from typing import TypedDict

import jwt
from fastapi import Depends, HTTPException, Request

from gerti_sidecar.config import Settings, get_settings

_ALG = "HS256"
_ADMIN_ROLE = "gerti_staff"
_ADMIN_TYP = "admin"


class AdminSessionPayload(TypedDict):
    agent_login: str
    role: str
    typ: str
    exp: int


def encode_admin_session(agent_login: str, settings: Settings) -> str:
    exp = int(
        (dt.datetime.now(dt.UTC) + dt.timedelta(seconds=settings.session_ttl_seconds)).timestamp()
    )
    payload: AdminSessionPayload = {
        "agent_login": agent_login,
        "role": _ADMIN_ROLE,
        "typ": _ADMIN_TYP,
        "exp": exp,
    }
    return jwt.encode(dict(payload), settings.session_secret, algorithm=_ALG)


def decode_admin_session(token: str, settings: Settings) -> AdminSessionPayload | None:
    try:
        data = jwt.decode(token, settings.session_secret, algorithms=[_ALG])
    except jwt.PyJWTError:
        return None
    # Fail-closed: precisa ser EXATAMENTE uma sessão admin (typ + role).
    if data.get("typ") != _ADMIN_TYP or data.get("role") != _ADMIN_ROLE:
        return None
    if not isinstance(data.get("agent_login"), str) or not data["agent_login"]:
        return None
    return AdminSessionPayload(
        agent_login=data["agent_login"],
        role=_ADMIN_ROLE,
        typ=_ADMIN_TYP,
        exp=int(data["exp"]),
    )


async def get_admin_session(
    request: Request,
    settings: Settings = Depends(get_settings),
) -> AdminSessionPayload:
    """Dependency dos endpoints `/v1/admin/*`: exige uma sessão admin válida.

    401 sem cookie `gsid_adm` / inválido / expirado / claim errado. Não lê
    request.state.tenant (admin é cross-tenant).
    """
    token = request.cookies.get(settings.admin_session_cookie_name)
    if not token:
        raise HTTPException(status_code=401, detail="no_admin_session")
    payload = decode_admin_session(token, settings)
    if payload is None:
        raise HTTPException(status_code=401, detail="invalid_admin_session")
    return payload


# --------------------------------------------------------------------------- #
# R16 — módulos por agente (o caso da Georgia)
# --------------------------------------------------------------------------- #
#
# *"A Georgia só usa tickets e não tem acesso remoto, então ela não vê o
# inventário"* (10:00).
#
# O aceite é explícito quanto a onde isso vale: **"nem pela URL direta"**.
# Esconder o item no menu não é controle de acesso — é decoração. Por isso o
# gate é uma dependência de rota, no servidor, e o console é só o reflexo.
#
# A leitura é na sessão do CONSOLE (BYPASSRLS): as tabelas de licença são
# `REVOKE ALL ... FROM gerti_app` e a conexão do portal do cliente nem
# consegue lê-las.


def require_module(module: str) -> Callable[..., Awaitable[AdminSessionPayload]]:
    """Dependência que exige um módulo licenciado do agente.

    Fora do padrão de fail-closed do resto do projeto, e de propósito: quando
    `LICENSE_ENFORCEMENT_ENABLED` está desligado (o padrão), **libera**. Ligar
    o gate num ambiente onde ninguém tem licença atribuída trancaria todos os
    agentes para fora do inventário no primeiro deploy. A Gerti atribui as
    licenças, confere o quadro, e só então liga a chave.

    Com a chave ligada, a falta de licença ou do módulo é **403**, e a
    mensagem diz qual módulo falta — um 403 mudo faria o agente abrir chamado
    achando que o sistema quebrou.
    """

    async def _dep(
        admin: AdminSessionPayload = Depends(get_admin_session),
    ) -> AdminSessionPayload:
        if not get_settings().license_enforcement_enabled:
            return admin
        # Import local: `license_service` importa modelos que importam config,
        # e o topo deste módulo é carregado cedo demais na subida do app.
        from gerti_sidecar import db
        from gerti_sidecar.domain.license_service import LicenseService

        factory = db.AdminSessionLocal
        if factory is None:  # pragma: no cover - app sem banco não serve rota
            raise HTTPException(status_code=503, detail="admin_db_unavailable")
        async with factory() as session:
            modules = await LicenseService(session).modules_of(admin["agent_login"])
        if module not in modules:
            raise HTTPException(
                status_code=403,
                detail=f"licença sem o módulo '{module}'",
            )
        return admin

    return _dep
