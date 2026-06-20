"""Cliente Asaas (Spec #2) — gateway de pagamento (PIX/Boleto/Cartão + assinatura).

Mesmo molde do `ollama.py`: client tipado, `transport` injetável (httpx.MockTransport
nos testes — sem rede real), exceções traduzíveis para status HTTP. Auth por header
`access_token` (padrão Asaas; ver projeto de referência ~/projetos/billing). Sem SDK.

Erros:
- AsaasDisabled  → sem api_key (feature off / conta mal configurada).
- AsaasError     → 4xx do Asaas (mapeia errors[].description) → vira 400/422.
- AsaasUnavailable → timeout/transporte/5xx → 503.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

import httpx


class AsaasError(RuntimeError):
    """Erro de negócio do Asaas (4xx) — `messages` traz as descrições."""

    def __init__(
        self, message: str, *, status: int = 400, messages: list[str] | None = None
    ) -> None:
        super().__init__(message)
        self.status = status
        self.messages = messages or [message]


class AsaasDisabled(AsaasError):
    """Sem api_key / conta inativa — pagamento desabilitado."""


class AsaasUnavailable(AsaasError):
    """Transporte/timeout/5xx — indisponibilidade → 503."""


def _cents_to_str(cents: int) -> str:
    """Asaas espera valor decimal em reais (ex.: 14.90), não centavos."""
    return str((Decimal(cents) / Decimal(100)).quantize(Decimal("0.01")))


class AsaasClient:
    def __init__(
        self,
        *,
        base_url: str,
        api_key: str,
        timeout: float = 30.0,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._base = base_url.rstrip("/")
        self._key = api_key
        self._timeout = timeout
        self._transport = transport

    def _headers(self) -> dict[str, str]:
        return {
            "access_token": self._key,
            "Content-Type": "application/json",
            "accept": "application/json",
            "User-Agent": "GroundControl",
        }

    async def _request(
        self, method: str, path: str, *, json: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        if not self._key:
            raise AsaasDisabled("ASAAS api_key ausente")
        url = f"{self._base}{path}"
        try:
            async with httpx.AsyncClient(
                timeout=self._timeout, transport=self._transport
            ) as client:
                resp = await client.request(method, url, headers=self._headers(), json=json)
        except httpx.HTTPError as exc:
            raise AsaasUnavailable(str(exc)) from exc
        if resp.status_code >= 500:
            raise AsaasUnavailable(f"asaas http {resp.status_code}")
        try:
            data = resp.json()
        except ValueError as exc:
            raise AsaasUnavailable("resposta não-JSON do Asaas") from exc
        if resp.status_code >= 400:
            descs = [e.get("description", "") for e in (data.get("errors") or [])]
            msg = "; ".join(d for d in descs if d) or f"asaas http {resp.status_code}"
            raise AsaasError(
                msg,
                status=422 if resp.status_code == 400 else resp.status_code,
                messages=descs or [msg],
            )
        if not isinstance(data, dict):
            raise AsaasUnavailable("resposta inesperada do Asaas")
        return data

    # --- Customers ---------------------------------------------------------
    async def find_customer_by_document(self, cpf_cnpj: str) -> dict[str, Any] | None:
        data = await self._request("GET", f"/customers?cpfCnpj={cpf_cnpj}")
        items = data.get("data") or []
        return items[0] if items else None

    async def create_customer(
        self,
        *,
        name: str,
        cpf_cnpj: str,
        email: str,
        external_reference: str,
        phone: str | None = None,
    ) -> dict[str, Any]:
        body: dict[str, Any] = {
            "name": name,
            "cpfCnpj": cpf_cnpj,
            "email": email,
            "externalReference": external_reference,
        }
        if phone:
            body["phone"] = phone
        return await self._request("POST", "/customers", json=body)

    async def find_or_create_customer(
        self, *, name: str, cpf_cnpj: str, email: str, external_reference: str
    ) -> dict[str, Any]:
        found = await self.find_customer_by_document(cpf_cnpj)
        if found:
            return found
        return await self.create_customer(
            name=name, cpf_cnpj=cpf_cnpj, email=email, external_reference=external_reference
        )

    # --- Cartão ------------------------------------------------------------
    async def tokenize_credit_card(self, data: dict[str, Any]) -> dict[str, Any]:
        """POST /creditCard/tokenize → {creditCardToken, ...}. NUNCA persistir o PAN."""
        return await self._request("POST", "/creditCard/tokenize", json=data)

    # --- Cobrança avulsa ---------------------------------------------------
    async def create_payment(
        self,
        *,
        customer_id: str,
        value_cents: int,
        due_date: str,
        billing_type: str,
        description: str,
        external_reference: str,
        credit_card_token: str | None = None,
        remote_ip: str | None = None,
    ) -> dict[str, Any]:
        body: dict[str, Any] = {
            "customer": customer_id,
            "billingType": billing_type,
            "value": _cents_to_str(value_cents),
            "dueDate": due_date,
            "description": description,
            "externalReference": external_reference,
        }
        if billing_type == "CREDIT_CARD" and credit_card_token:
            body["creditCardToken"] = credit_card_token
            if remote_ip:
                body["remoteIp"] = remote_ip
        return await self._request("POST", "/payments", json=body)

    # --- Assinatura recorrente (inclui PIX recorrente) --------------------
    async def create_subscription(
        self,
        *,
        customer_id: str,
        value_cents: int,
        next_due_date: str,
        billing_type: str,
        cycle: str,
        description: str,
        external_reference: str,
        credit_card_token: str | None = None,
    ) -> dict[str, Any]:
        body: dict[str, Any] = {
            "customer": customer_id,
            "billingType": billing_type,
            "value": _cents_to_str(value_cents),
            "nextDueDate": next_due_date,
            "cycle": cycle,
            "description": description,
            "externalReference": external_reference,
        }
        if billing_type == "CREDIT_CARD" and credit_card_token:
            body["creditCardToken"] = credit_card_token
        return await self._request("POST", "/subscriptions", json=body)

    async def cancel_subscription(self, subscription_id: str) -> dict[str, Any]:
        return await self._request("DELETE", f"/subscriptions/{subscription_id}")

    # --- Detalhes de cobrança ---------------------------------------------
    async def get_payment(self, payment_id: str) -> dict[str, Any]:
        return await self._request("GET", f"/payments/{payment_id}")

    async def get_pix_qrcode(self, payment_id: str) -> dict[str, Any]:
        """→ {encodedImage(base64 PNG), payload(copia-e-cola), expirationDate}."""
        return await self._request("GET", f"/payments/{payment_id}/pixQrCode")

    async def get_billing_info(self, payment_id: str) -> dict[str, Any]:
        """→ {bankSlip:{bankSlipUrl, barCode, identificationField}, ...} (boleto)."""
        return await self._request("GET", f"/payments/{payment_id}/billingInfo")
