"""render_invoice_pdf: gera um PDF branded a partir de invoice + lines + branding.

Testa pelo header %PDF- + tamanho (lição #1M/#1N/#1O). Não monta página Nuxt nem
extrai texto; valida o contrato do renderizador (bytes válidos, não-triviais).
"""

from __future__ import annotations

import datetime as dt
import uuid

from gerti_sidecar.domain.invoice_pdf import InvoiceBranding, render_invoice_pdf


class _Inv:
    def __init__(self):
        self.id = uuid.uuid4()
        self.number = 42
        self.status = "open"
        self.issued_at = dt.datetime(2026, 2, 1, tzinfo=dt.UTC)
        self.due_at = dt.datetime(2026, 2, 16, tzinfo=dt.UTC)
        self.period_start = dt.date(2026, 1, 1)
        self.period_end = dt.date(2026, 1, 31)
        self.currency = "BRL"
        self.subtotal_cents = 35000
        self.total_cents = 35000


class _Line:
    def __init__(self, desc, qty, unit, unit_price_cents, amount_cents, position):
        self.description = desc
        self.quantity = qty
        self.unit = unit
        self.unit_price_cents = unit_price_cents
        self.amount_cents = amount_cents
        self.position = position


def test_render_invoice_pdf_returns_pdf_bytes():
    branding = InvoiceBranding(
        display_name="Aurora Móveis",
        logo_url=None,
        primary_color="#e67e22",
    )
    inv = _Inv()
    lines = [
        _Line("Atendimento (horas)", 1.5, "h", 20000, 30000, 0),
        _Line("Deslocamento", 1, "serviço", 5000, 5000, 1),
    ]
    pdf = render_invoice_pdf(inv, lines, branding)
    assert isinstance(pdf, bytes)
    assert pdf[:5] == b"%PDF-"
    assert len(pdf) > 1024
