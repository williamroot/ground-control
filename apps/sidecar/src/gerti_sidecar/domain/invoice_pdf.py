"""Render de fatura interna branded para PDF (Spec #1P).

Primário: WeasyPrint (HTML/CSS via template Jinja2 com logo/cores do tenant).
Fallback: ReportLab (mesma assinatura `render_invoice_pdf`), caso a imagem não
suporte as libs nativas do WeasyPrint (cairo/pango/gdk-pixbuf). A escolha é
isolada aqui: o resto do código só conhece `render_invoice_pdf(...) -> bytes`.

Valores chegam em centavos (int) e são formatados como BRL pt-BR.
"""

from __future__ import annotations

import dataclasses
import datetime as dt
from pathlib import Path
from typing import Any, Protocol

from jinja2 import Environment, FileSystemLoader, select_autoescape

_TEMPLATES_DIR = Path(__file__).resolve().parent.parent / "templates"

_INVOICE_STATUS_LABELS = {
    "draft": "Rascunho",
    "open": "Em aberto",
    "paid": "Paga",
    "overdue": "Vencida",
    "void": "Cancelada",
}


@dataclasses.dataclass(slots=True)
class InvoiceBranding:
    """Branding mínimo p/ o cabeçalho da fatura (subset de TenantBranding)."""

    display_name: str
    logo_url: str | None
    primary_color: str


class _InvoiceLike(Protocol):
    number: int
    status: Any
    issued_at: dt.datetime
    due_at: dt.datetime
    period_start: dt.date
    period_end: dt.date
    currency: str
    subtotal_cents: int
    total_cents: int


class _LineLike(Protocol):
    description: str
    quantity: Any
    unit: str
    unit_price_cents: int
    amount_cents: int
    position: int


def _money_brl(cents: int) -> str:
    """Formata centavos como 'R$ 1.234,56' (pt-BR)."""
    reais = cents / 100
    s = f"{reais:,.2f}"  # 1,234.56 (locale C)
    s = s.replace(",", "_").replace(".", ",").replace("_", ".")
    return f"R$ {s}"


def _fmt_date(value: dt.date | dt.datetime) -> str:
    return value.strftime("%d/%m/%Y")


def _status_value(status: Any) -> str:
    return getattr(status, "value", str(status))


def _render_html(invoice: _InvoiceLike, lines: list[_LineLike], branding: InvoiceBranding) -> str:
    env = Environment(
        loader=FileSystemLoader(str(_TEMPLATES_DIR)),
        autoescape=select_autoescape(["html", "xml"]),
    )
    template = env.get_template("invoice.html")
    status = _status_value(invoice.status)
    return template.render(
        invoice=invoice,
        lines=sorted(lines, key=lambda x: x.position),
        display_name=branding.display_name,
        logo_url=branding.logo_url,
        primary_color=branding.primary_color or "#334155",
        status_label=_INVOICE_STATUS_LABELS.get(status, status),
        issued=_fmt_date(invoice.issued_at),
        due=_fmt_date(invoice.due_at),
        period_start=_fmt_date(invoice.period_start),
        period_end=_fmt_date(invoice.period_end),
        money=_money_brl,
    )


def _render_weasyprint(html: str) -> bytes:
    from weasyprint import HTML  # import tardio: lib nativa só carrega se usada

    return HTML(string=html).write_pdf()  # type: ignore[no-any-return]


def _render_reportlab(
    invoice: _InvoiceLike, lines: list[_LineLike], branding: InvoiceBranding
) -> bytes:
    """Fallback simples (sem HTML/CSS) quando WeasyPrint não está disponível.

    Layout enxuto: cabeçalho com nome do tenant + número, tabela de linhas, total.
    A cor de marca é usada no título. Mantém o mesmo contrato de bytes %PDF-.
    """
    import io

    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import mm
    from reportlab.pdfgen import canvas

    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    width, height = A4
    y = height - 25 * mm

    primary = colors.HexColor(branding.primary_color or "#334155")
    c.setFillColor(primary)
    c.setFont("Helvetica-Bold", 18)
    c.drawString(16 * mm, y, branding.display_name)
    c.setFont("Helvetica-Bold", 13)
    c.drawRightString(width - 16 * mm, y, f"Fatura #{invoice.number:04d}")
    y -= 8 * mm
    c.setFillColor(colors.black)
    c.setFont("Helvetica", 9)
    c.drawString(16 * mm, y, f"Emissão: {_fmt_date(invoice.issued_at)}")
    c.drawString(70 * mm, y, f"Vencimento: {_fmt_date(invoice.due_at)}")
    status = _status_value(invoice.status)
    status_label = _INVOICE_STATUS_LABELS.get(status, status)
    c.drawString(120 * mm, y, f"Status: {status_label}")
    y -= 6 * mm
    c.drawString(
        16 * mm,
        y,
        f"Período: {_fmt_date(invoice.period_start)} a {_fmt_date(invoice.period_end)}",
    )
    y -= 12 * mm

    c.setFillColor(primary)
    c.rect(16 * mm, y - 2 * mm, width - 32 * mm, 7 * mm, fill=1, stroke=0)
    c.setFillColor(colors.white)
    c.setFont("Helvetica-Bold", 9)
    c.drawString(18 * mm, y, "Descrição")
    c.drawRightString(width - 18 * mm, y, "Total")
    y -= 9 * mm

    c.setFillColor(colors.black)
    c.setFont("Helvetica", 9)
    for line in sorted(lines, key=lambda x: x.position):
        c.drawString(18 * mm, y, str(line.description))
        c.drawRightString(width - 18 * mm, y, _money_brl(line.amount_cents))
        y -= 6 * mm

    y -= 4 * mm
    c.setFont("Helvetica-Bold", 11)
    c.setFillColor(primary)
    c.drawRightString(width - 18 * mm, y, f"Total: {_money_brl(invoice.total_cents)}")

    c.setFillColor(colors.grey)
    c.setFont("Helvetica", 8)
    c.drawCentredString(width / 2, 14 * mm, "Documento interno — não é nota fiscal")
    c.showPage()
    c.save()
    return buf.getvalue()


def render_invoice_pdf(
    invoice: _InvoiceLike, lines: list[_LineLike], branding: InvoiceBranding
) -> bytes:
    """Renderiza a fatura para PDF (WeasyPrint primário; ReportLab no fallback)."""
    html = _render_html(invoice, lines, branding)
    try:
        return _render_weasyprint(html)
    except Exception:
        # Qualquer falha de import/lib nativa do WeasyPrint cai p/ o ReportLab.
        return _render_reportlab(invoice, lines, branding)
