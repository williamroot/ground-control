"""T-R15.5 — boleto e nota fiscal de uma fatura, pelo Asaas.

A decisão I-4 (15/08) fechou o emissor: o Asaas, que já é o meio de pagamento
do checkout, emite **os dois**. Não é preciso contratar emissor fiscal
separado. O que faltava era acionar a cobrança **a partir de `gerti.invoice`**,
e não só a partir do checkout.

A ordem é a recomendada no plano, e não é arbitrária:

1. **Boleto primeiro.** É caminho pronto — `create_payment(billing_type="BOLETO")`
   já existe e depende apenas da chave da conta.
2. **Nota depois.** Ela depende de configuração FISCAL da conta Asaas
   (inscrição municipal, certificado digital, regime tributário, serviço e
   alíquota do município). Sem isso o Asaas **aceita a cobrança e recusa a
   nota** — o erro só aparece na hora de emitir. Por isso a nota é uma ação
   separada, com erro visível, e nunca um efeito colateral silencioso da
   emissão do boleto.

**Fail-safe.** `ASAAS_ENABLED=false` (o padrão) faz a emissão recusar com
`ChargingDisabled` em vez de tentar e falhar torto. Mesma postura do checkout.

**Idempotência.** Uma fatura com `asaas_payment_id` já tem cobrança: pedir de
novo devolve a que existe, não cria a segunda. Boleto duplicado é dinheiro
cobrado duas vezes do cliente, e o índice único na coluna é a rede embaixo
disso.

**Quem paga.** Se o contrato tem `contract_billing_party` — o "faturar para
outro CNPJ" do #0 —, o boleto sai no nome e documento DELE. Sem isso, sai no
do próprio cliente. Emitir sempre no do cliente furaria o único motivo de
aquela tabela existir.
"""

from __future__ import annotations

import datetime as dt
import logging
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from gerti_sidecar.domain.errors import InvoiceError
from gerti_sidecar.integrations.asaas_client import AsaasClient
from gerti_sidecar.models import Contract, ContractBillingParty, Invoice, Tenant

logger = logging.getLogger(__name__)


class ChargingDisabled(InvoiceError):
    """Asaas desligado por configuração (-> 503)."""


class ChargingRefused(InvoiceError):
    """A fatura não pode ser cobrada no estado em que está (-> 422)."""


def _cents(value: int) -> int:
    return int(value)


class InvoiceChargeService:
    def __init__(self, session: AsyncSession, asaas: AsaasClient | None, *, enabled: bool) -> None:
        self.session = session
        self._asaas = asaas
        self._enabled = enabled

    def _client(self) -> AsaasClient:
        if not self._enabled or self._asaas is None:
            raise ChargingDisabled(
                "cobrança pelo Asaas está desligada (ASAAS_ENABLED/ASAAS_API_KEY)"
            )
        return self._asaas

    async def _payer(self, invoice: Invoice) -> tuple[str, str, str]:
        """Nome, documento e e-mail de quem recebe a cobrança."""
        party = await self.session.get(ContractBillingParty, invoice.contract_id)
        tenant = await self.session.get(Tenant, invoice.tenant_id)
        if tenant is None:  # pragma: no cover - FK garante
            raise ChargingRefused("cliente da fatura inexistente")
        email = tenant.contact_email or ""
        if party is not None:
            return party.legal_name, party.document, email
        return tenant.legal_name, tenant.document, email

    async def issue_bank_slip(self, invoice_id: uuid.UUID) -> Invoice:
        """Emite (ou devolve) o boleto da fatura."""
        invoice = await self.session.get(Invoice, invoice_id)
        if invoice is None:
            raise InvoiceError("fatura inexistente neste tenant")
        if invoice.asaas_payment_id:
            return invoice  # idempotente: nunca um segundo boleto
        if invoice.total_cents <= 0:
            raise ChargingRefused("fatura sem valor — não há o que cobrar")
        if invoice.status.value in ("paid", "void"):
            raise ChargingRefused(f"fatura {invoice.status} não aceita cobrança nova")

        client = self._client()
        name, document, email = await self._payer(invoice)
        if not document:
            raise ChargingRefused(
                "o cliente não tem CNPJ/CPF cadastrado — o Asaas recusa a cobrança sem ele"
            )
        contract = await self.session.get(Contract, invoice.contract_id)
        code = contract.code if contract else "—"

        customer = await client.find_or_create_customer(
            name=name,
            cpf_cnpj=document,
            email=email,
            external_reference=f"tenant:{invoice.tenant_id}",
        )
        payment = await client.create_payment(
            customer_id=str(customer["id"]),
            value_cents=_cents(invoice.total_cents),
            due_date=invoice.due_at.date().isoformat(),
            billing_type="BOLETO",
            description=(
                f"Fatura #{invoice.number:04d} — {code} — "
                f"{invoice.period_start:%d/%m/%Y} a {invoice.period_end:%d/%m/%Y}"
            ),
            # É por esta referência que o webhook reencontra a fatura.
            external_reference=f"invoice:{invoice.id}",
        )
        invoice.asaas_payment_id = str(payment.get("id") or "")
        invoice.asaas_charge_status = str(payment.get("status") or "")
        invoice.asaas_bank_slip_url = payment.get("bankSlipUrl") or None
        invoice.asaas_invoice_url = payment.get("invoiceUrl") or None
        await self.session.flush()
        return invoice

    async def issue_nfe(
        self,
        invoice_id: uuid.UUID,
        *,
        service_description: str | None = None,
        municipal_service_code: str | None = None,
        municipal_service_name: str | None = None,
    ) -> Invoice:
        """Agenda a NFS-e da fatura. Exige o boleto já emitido.

        A nota do Asaas pendura numa cobrança (`payment`), então não há como
        emitir nota de uma fatura que nunca virou cobrança. A recusa é
        explícita — a alternativa seria emitir um boleto por baixo, e ninguém
        deve descobrir que cobrou o cliente porque pediu uma nota.
        """
        invoice = await self.session.get(Invoice, invoice_id)
        if invoice is None:
            raise InvoiceError("fatura inexistente neste tenant")
        if not invoice.asaas_payment_id:
            raise ChargingRefused("emita a cobrança antes — a nota fiscal é emitida sobre ela")
        if invoice.nfe_id:
            return invoice  # idempotente: uma nota por fatura

        client = self._client()
        contract = await self.session.get(Contract, invoice.contract_id)
        code = contract.code if contract else "—"
        result = await client.schedule_invoice(
            payment_id=invoice.asaas_payment_id,
            service_description=(
                service_description
                or f"Serviços de TI — contrato {code} — "
                f"{invoice.period_start:%d/%m/%Y} a {invoice.period_end:%d/%m/%Y}"
            ),
            value_cents=_cents(invoice.total_cents),
            effective_date=dt.datetime.now(dt.UTC).date().isoformat(),
            municipal_service_code=municipal_service_code,
            municipal_service_name=municipal_service_name,
        )
        invoice.nfe_id = str(result.get("id") or "")
        invoice.nfe_status = str(result.get("status") or "")
        invoice.nfe_pdf_url = result.get("pdfUrl") or None
        await self.session.flush()
        return invoice

    async def refresh(self, invoice_id: uuid.UUID) -> Invoice:
        """Relê no Asaas o estado da cobrança e da nota.

        Existe porque webhook se perde: sem uma leitura sob demanda, uma fatura
        paga fora do webhook ficaria `open` para sempre e alguém cobraria o
        cliente de novo.
        """
        invoice = await self.session.get(Invoice, invoice_id)
        if invoice is None:
            raise InvoiceError("fatura inexistente neste tenant")
        if not invoice.asaas_payment_id:
            return invoice
        client = self._client()
        payment = await client.get_payment(invoice.asaas_payment_id)
        invoice.asaas_charge_status = str(payment.get("status") or "")
        invoice.asaas_bank_slip_url = payment.get("bankSlipUrl") or invoice.asaas_bank_slip_url
        if invoice.nfe_id:
            nfe = await client.get_invoice(invoice.nfe_id)
            invoice.nfe_status = str(nfe.get("status") or "")
            invoice.nfe_pdf_url = nfe.get("pdfUrl") or invoice.nfe_pdf_url
        await self.session.flush()
        return invoice


async def find_invoice_by_payment(session: AsyncSession, payment_id: str) -> Invoice | None:
    """Fatura de uma cobrança do Asaas (usada pelo webhook)."""
    return (
        await session.execute(select(Invoice).where(Invoice.asaas_payment_id == payment_id))
    ).scalar_one_or_none()
