"""Cliente Ollama Cloud (#1N) — API nativa /api/chat, failure-safe.

Espelha o padrão dos clientes Znuny (`_post`): exceções traduzíveis para status
HTTP (OllamaDisabled -> feature ausente/desligada; OllamaUnavailable -> 503),
`transport` injetável para testes (httpx.MockTransport, sem rede real).

Confirmado ao vivo: `POST https://ollama.com/api/chat` com
`Authorization: Bearer <key>` e `gpt-oss:120b` retorna
`{"message": {"content": "...", "thinking": "..."}}` — lemos `message.content`
e ignoramos `thinking`. Chamadas são `chat` PURO: nenhuma tool/function-calling
exposta (camada de defesa contra prompt injection — roadmap §E).
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from typing import Any

import httpx


class OllamaError(RuntimeError):
    """Base de erros do cliente Ollama."""


class OllamaDisabled(OllamaError):
    """Sem api_key/feature off — a IA está desabilitada (fail-soft)."""


class OllamaUnavailable(OllamaError):
    """Transporte/timeout/5xx/resposta inválida — indisponibilidade -> 503."""


Message = dict[str, str]


class OllamaClient:
    def __init__(
        self,
        *,
        base_url: str,
        api_key: str,
        model: str,
        timeout: float = 120.0,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._base = base_url.rstrip("/")
        self._key = api_key
        self._model = model
        self._timeout = timeout
        self._transport = transport

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self._key}",
            "Content-Type": "application/json",
        }

    async def chat(self, messages: list[Message], *, reasoning_effort: str = "low") -> str:
        """Chat puro (stream=False). Retorna message.content; ignora thinking.

        SEM tools/function-calling (defesa contra prompt injection). 5xx/4xx/timeout
        -> OllamaUnavailable; sem api_key -> OllamaDisabled.
        """
        if not self._key:
            raise OllamaDisabled("OLLAMA_API_KEY ausente")
        payload: dict[str, Any] = {
            "model": self._model,
            "messages": messages,
            "stream": False,
            "reasoning_effort": reasoning_effort,  # gpt-oss: low|medium|high
        }
        try:
            async with httpx.AsyncClient(
                timeout=self._timeout, transport=self._transport
            ) as client:
                resp = await client.post(
                    f"{self._base}/api/chat", headers=self._headers(), json=payload
                )
        except httpx.HTTPError as exc:
            raise OllamaUnavailable(str(exc)) from exc
        if resp.status_code >= 500:
            raise OllamaUnavailable(f"ollama http {resp.status_code}")
        if resp.status_code >= 400:
            raise OllamaUnavailable(f"ollama http {resp.status_code}: {resp.text[:200]}")
        try:
            data = resp.json()
        except ValueError as exc:
            raise OllamaUnavailable("resposta não-JSON do Ollama") from exc
        content = (data.get("message") or {}).get("content")
        if not content:
            raise OllamaUnavailable("resposta sem message.content")
        return str(content)

    async def chat_stream(
        self, messages: list[Message], *, reasoning_effort: str = "low"
    ) -> AsyncIterator[str]:
        """NDJSON: cada linha é um JSON; token incremental em message.content; fim em done.

        Reservado para melhoria futura (streaming SSE); o MVP usa `chat`.
        """
        if not self._key:
            raise OllamaDisabled("OLLAMA_API_KEY ausente")
        payload = {
            "model": self._model,
            "messages": messages,
            "stream": True,
            "reasoning_effort": reasoning_effort,
        }
        async with httpx.AsyncClient(
            timeout=None,  # noqa: S113 — stream NDJSON sem comprimento fixo
            transport=self._transport,
        ) as client:
            async with client.stream(
                "POST", f"{self._base}/api/chat", headers=self._headers(), json=payload
            ) as resp:
                if resp.status_code >= 400:
                    raise OllamaUnavailable(f"ollama http {resp.status_code}")
                async for line in resp.aiter_lines():
                    if not line:
                        continue
                    chunk = json.loads(line)
                    piece = (chunk.get("message") or {}).get("content") or ""
                    if piece:
                        yield piece
                    if chunk.get("done"):
                        break
