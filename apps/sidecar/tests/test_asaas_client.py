"""AsaasClient — unit com httpx.MockTransport (sem rede real)."""

from __future__ import annotations

import httpx
import pytest

from gerti_sidecar.integrations.asaas_client import (
    AsaasClient,
    AsaasDisabled,
    AsaasError,
    AsaasUnavailable,
)


def _client(handler: httpx.MockTransport, *, key: str = "k") -> AsaasClient:
    return AsaasClient(base_url="https://api-sandbox.asaas.com/v3", api_key=key, transport=handler)


@pytest.mark.asyncio
async def test_create_payment_ok_and_value_in_reais() -> None:
    seen: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        import json as _json

        seen.update(_json.loads(request.content))
        seen["_auth"] = request.headers.get("access_token")
        return httpx.Response(200, json={"id": "pay_1", "invoiceUrl": "https://x/y"})

    c = _client(httpx.MockTransport(handler))
    out = await c.create_payment(
        customer_id="cus_1",
        value_cents=14990,
        due_date="2026-07-01",
        billing_type="PIX",
        description="t",
        external_reference="checkout:1",
    )
    assert out["id"] == "pay_1"
    assert seen["value"] == "149.90"  # centavos → reais
    assert seen["_auth"] == "k"  # header access_token


@pytest.mark.asyncio
async def test_4xx_maps_to_asaas_error_with_descriptions() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(400, json={"errors": [{"description": "CPF inválido"}]})

    c = _client(httpx.MockTransport(handler))
    with pytest.raises(AsaasError) as ei:
        await c.create_customer(name="x", cpf_cnpj="0", email="a@b.c", external_reference="r")
    assert ei.value.status == 422
    assert "CPF inválido" in ei.value.messages


@pytest.mark.asyncio
async def test_5xx_maps_to_unavailable() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503, json={})

    c = _client(httpx.MockTransport(handler))
    with pytest.raises(AsaasUnavailable):
        await c.get_payment("pay_1")


@pytest.mark.asyncio
async def test_no_key_disabled() -> None:
    c = _client(httpx.MockTransport(lambda r: httpx.Response(200, json={})), key="")
    with pytest.raises(AsaasDisabled):
        await c.get_payment("pay_1")
