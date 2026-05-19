"""Cliente fino do Generic Interface do Znuny — só auth de customer.

Contrato CONGELADO no spike R1 (ADR D14):
  authenticate_customer(login, password) -> bool
  ZnunyUnavailable: só em falha de transporte/5xx (nunca em rejeição limpa).
Endpoint/token vêm da única linha gerti.znuny_instance.
"""

from __future__ import annotations

import os

import httpx


class ZnunyUnavailable(RuntimeError):
    """Falha de transporte ao falar com o Znuny (-> 503 no router)."""


def _resolve_endpoint() -> tuple[str, str]:
    """(url do webservice, token de acesso). base_url da gerti.znuny_instance;
    o token concreto é resolvido do secret-ref (vault) — em dev/test cai no
    env ZNUNY_WS_URL / ZNUNY_WS_TOKEN. Implementação exata definida em D14."""
    url = os.environ.get("ZNUNY_WS_URL", "")
    token = os.environ.get("ZNUNY_WS_TOKEN", "")
    return url, token


async def authenticate_customer(login: str, password: str) -> bool:
    url, token = _resolve_endpoint()
    body = {"CustomerUserLogin": login, "Password": password, "AccessToken": token}
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(url, json=body)
    except httpx.HTTPError as exc:
        raise ZnunyUnavailable(str(exc)) from exc
    if resp.status_code >= 500:
        raise ZnunyUnavailable(f"znuny http {resp.status_code}")
    try:
        data = resp.json()
    except ValueError as exc:
        raise ZnunyUnavailable("resposta não-JSON do Znuny") from exc
    return bool(data.get("SessionID")) and "Error" not in data
