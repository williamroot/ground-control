"""Cliente Ollama Cloud (#1N Task 1) — chat puro via /api/chat, failure-safe.

Sem rede real: httpx.MockTransport. Verifica path, header Bearer, body, e
mapeamento de erros (5xx/timeout -> OllamaUnavailable; sem key -> OllamaDisabled).
"""

from __future__ import annotations

import httpx
import pytest

from gerti_sidecar.integrations.ollama import (
    OllamaClient,
    OllamaDisabled,
    OllamaUnavailable,
)


@pytest.mark.asyncio
async def test_chat_happy():
    def handler(req: httpx.Request) -> httpx.Response:
        assert req.url.path == "/api/chat"
        assert req.headers["authorization"] == "Bearer KEY"
        body = req.content
        assert b'"model"' in body
        assert b'"gpt-oss:120b"' in body
        assert b'"stream":false' in body or b'"stream": false' in body
        return httpx.Response(200, json={"message": {"content": "RESUMO"}, "done": True})

    client = OllamaClient(
        base_url="https://ollama.com",
        api_key="KEY",
        model="gpt-oss:120b",
        transport=httpx.MockTransport(handler),
    )
    out = await client.chat([{"role": "user", "content": "oi"}])
    assert out == "RESUMO"


@pytest.mark.asyncio
async def test_chat_ignores_thinking_reads_content():
    def handler(req: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={"message": {"content": "RESPOSTA", "thinking": "raciocinio interno"}},
        )

    client = OllamaClient(
        base_url="https://ollama.com",
        api_key="KEY",
        model="gpt-oss:120b",
        transport=httpx.MockTransport(handler),
    )
    out = await client.chat([{"role": "user", "content": "oi"}])
    assert out == "RESPOSTA"


@pytest.mark.asyncio
async def test_chat_disabled_without_key():
    client = OllamaClient(base_url="https://ollama.com", api_key="", model="gpt-oss:120b")
    with pytest.raises(OllamaDisabled):
        await client.chat([{"role": "user", "content": "oi"}])


@pytest.mark.asyncio
async def test_chat_5xx_is_unavailable():
    def handler(req: httpx.Request) -> httpx.Response:
        return httpx.Response(502, text="bad gateway")

    client = OllamaClient(
        base_url="https://ollama.com",
        api_key="KEY",
        model="gpt-oss:120b",
        transport=httpx.MockTransport(handler),
    )
    with pytest.raises(OllamaUnavailable):
        await client.chat([{"role": "user", "content": "oi"}])


@pytest.mark.asyncio
async def test_chat_transport_error_is_unavailable():
    def handler(req: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("boom")

    client = OllamaClient(
        base_url="https://ollama.com",
        api_key="KEY",
        model="gpt-oss:120b",
        transport=httpx.MockTransport(handler),
    )
    with pytest.raises(OllamaUnavailable):
        await client.chat([{"role": "user", "content": "oi"}])


@pytest.mark.asyncio
async def test_chat_empty_content_is_unavailable():
    def handler(req: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"message": {"content": ""}})

    client = OllamaClient(
        base_url="https://ollama.com",
        api_key="KEY",
        model="gpt-oss:120b",
        transport=httpx.MockTransport(handler),
    )
    with pytest.raises(OllamaUnavailable):
        await client.chat([{"role": "user", "content": "oi"}])
