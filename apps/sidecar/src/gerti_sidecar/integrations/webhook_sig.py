"""Verificação de assinatura HMAC dos webhooks Znuny→sidecar (Spec #1Q, Task 4).

HMAC-SHA256 sobre o corpo HTTP **bruto** (bytes exatos). Header:
`X-Gerti-Signature: sha256=<hexdigest>`. A comparação é constant-time
(`hmac.compare_digest`) para evitar timing attacks. O MESMO segredo compartilhado
é renderizado no Config.pm do Znuny (Event module GertiAutomation) e resolvido no
sidecar via `ZnunyInstance.webhook_signing_secret_ref`.
"""

from __future__ import annotations

import hashlib
import hmac

_PREFIX = "sha256="


def sign(secret: str, body: bytes) -> str:
    """Gera o header de assinatura (`sha256=<hex>`) para um corpo. Usado em testes."""
    digest = hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()
    return f"{_PREFIX}{digest}"


def verify(secret: str, body: bytes, header_sig: str | None) -> bool:
    """True se `header_sig` casa o HMAC-SHA256 do corpo com o segredo.

    Aceita tanto `sha256=<hex>` quanto o hex puro. Constant-time. Segredo vazio,
    header ausente ou malformado → False (fail-closed).
    """
    if not secret or not header_sig:
        return False
    provided = header_sig[len(_PREFIX) :] if header_sig.startswith(_PREFIX) else header_sig
    provided = provided.strip()
    if not provided:
        return False
    expected = hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(provided, expected)
