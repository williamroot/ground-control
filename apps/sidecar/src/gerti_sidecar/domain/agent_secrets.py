"""Helpers de token/secret do agente (Spec #1R-a) — alta entropia, sha256, hmac.

Modelo de segurança: NENHUM segredo é persistido em plaintext. O servidor guarda
apenas o sha256 hex; o plaintext é mostrado UMA única vez (na criação do token de
enrollment e no enroll do agente) e nunca mais é recuperável. A verificação usa
`hmac.compare_digest` (constant-time) para evitar timing oracles.

- `new_enroll_token()` → `('gcat_<rand>', hash)` — token de instalação por tenant.
- `new_agent_secret()` → `('gca_<rand>', hash)` — credencial por-agente (heartbeat).
- `hash_token(t)` → sha256 hex determinístico.
- `verify(presented, stored_hash)` → True só se sha256(presented) casa stored_hash
  (constant-time); False se qualquer um for vazio (fail-closed).
"""

from __future__ import annotations

import hashlib
import hmac
import secrets

_ENROLL_PREFIX = "gcat_"
_AGENT_PREFIX = "gca_"
_ENTROPY_BYTES = 32


def hash_token(token: str) -> str:
    """sha256 hex determinístico do token (o que vai persistido no banco)."""
    return hashlib.sha256(token.encode()).hexdigest()


def new_enroll_token() -> tuple[str, str]:
    """Gera um token de enrollment de alta entropia → (plaintext, sha256hex)."""
    plain = _ENROLL_PREFIX + secrets.token_urlsafe(_ENTROPY_BYTES)
    return plain, hash_token(plain)


def new_agent_secret() -> tuple[str, str]:
    """Gera a credencial por-agente de alta entropia → (plaintext, sha256hex)."""
    plain = _AGENT_PREFIX + secrets.token_urlsafe(_ENTROPY_BYTES)
    return plain, hash_token(plain)


def verify(presented: str, stored_hash: str) -> bool:
    """Compara o segredo apresentado com o hash guardado (constant-time).

    Fail-closed: qualquer entrada vazia → False (nunca autentica sem credencial).
    """
    if not presented or not stored_hash:
        return False
    return hmac.compare_digest(hash_token(presented), stored_hash)
