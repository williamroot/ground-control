"""V-R18b.3 — o relatório executivo vira um PDF de verdade.

Molde de `test_invoice_pdf.py`. Dois caminhos exercitados de propósito:
WeasyPrint (o primário, que depende de libs nativas) e o fallback ReportLab —
a Onda 0 mostrou que fallback nunca exercitado é código morto disfarçado.
"""

from __future__ import annotations

import datetime as dt

from gerti_sidecar.domain.report_pdf import (
    _render_reportlab,
    render_report_html,
    render_report_pdf,
)
from gerti_sidecar.domain.report_service import (
    ContractConsumption,
    MonthlyReport,
    ReportTicket,
)


def _report(*, tickets: int = 3, truncated: bool = False) -> MonthlyReport:
    import uuid

    return MonthlyReport(
        tenant_id=uuid.uuid4(),
        tenant_name="Aurora Móveis",
        display_name="Aurora Suporte",
        month="2026-05",
        month_label="maio/2026",
        period_start=dt.date(2026, 5, 1),
        period_end=dt.date(2026, 5, 31),
        consumption=[
            ContractConsumption(
                code="AUR-HORAS-2026",
                type="hour_bank",
                kind="hours",
                value=5.0,
                unit_label="horas",
            ),
            ContractConsumption(
                code="AUR-CREDITO-2026",
                type="credit_brl",
                kind="brl",
                value=1234.56,
                unit_label="reais",
            ),
        ],
        dimension="service",
        dimension_label="Serviço",
        top_items=[("Suporte::Estação de trabalho", 2), ("Suporte::Rede", 1)],
        tickets=[
            ReportTicket(
                znuny_ticket_id=100 + i,
                ticket_number=f"20260501000{i:02d}",
                title=f"Chamado de teste {i}",
                state="closed successful",
                service="Suporte::Rede",
                type="Incidente",
                created=f"2026-05-{(i % 28) + 1:02d} 09:00:00",
                hours=1.5,
            )
            for i in range(tickets)
        ],
        ticket_total=tickets if not truncated else 1500,
        tickets_truncated=truncated,
        degraded=False,
        branding={"logo_url": None, "primary_color": "#16A34A"},
    )


def test_html_carries_the_client_name_and_every_ticket_number():
    """O HTML intermediário precisa citar o cliente e cada chamado da listona."""
    r = _report()
    html = render_report_html(r)
    assert "Aurora Suporte" in html
    assert "maio/2026" in html
    for t in r.tickets:
        assert t.ticket_number in html
    # A unidade aparece formatada, não crua.
    assert "5,00 h" in html
    assert "R$ 1.234,56" in html
    # O aviso de que tipos diferentes não se somam aparece com 2 contratos.
    assert "não se somam" in html


def test_pdf_is_a_real_pdf():
    pdf = render_report_pdf(_report())
    assert pdf.startswith(b"%PDF-")
    assert len(pdf) > 1024


def test_reportlab_fallback_is_a_real_pdf_too():
    """O fallback é exercitado de propósito — fallback nunca rodado é ficção."""
    pdf = _render_reportlab(_report())
    assert pdf.startswith(b"%PDF-")
    assert len(pdf) > 1024


def test_reportlab_fallback_paginates_a_long_ticket_list():
    """A diferença deliberada em relação à fatura: aqui a listona pagina.

    O fallback da fatura não pagina (dívida registrada na Onda 0, aceitável com
    2 a 4 linhas). Um relatório com 400 chamados não pode perder conteúdo em
    silêncio — o PDF precisa crescer de verdade.
    """
    small = _render_reportlab(_report(tickets=3))
    big = _render_reportlab(_report(tickets=400))
    assert big.startswith(b"%PDF-")
    assert len(big) > len(small) * 3, "a listona longa não chegou ao PDF"


def test_truncation_is_stated_in_the_document():
    html = render_report_html(_report(tickets=3, truncated=True))
    assert "limitada" in html
    assert "1500" in html


def test_empty_month_says_so_instead_of_showing_an_empty_table():
    import uuid

    r = MonthlyReport(
        tenant_id=uuid.uuid4(),
        tenant_name="Acme",
        display_name="Acme",
        month="2026-05",
        month_label="maio/2026",
        period_start=dt.date(2026, 5, 1),
        period_end=dt.date(2026, 5, 31),
        consumption=[],
        dimension="service",
        dimension_label="Serviço",
        top_items=[],
        tickets=[],
        ticket_total=0,
        tickets_truncated=False,
        branding={"logo_url": None, "primary_color": "#334155"},
    )
    html = render_report_html(r)
    assert "Nenhum chamado no período" in html
    assert "Nenhum contrato com consumo mensurável" in html
    assert _render_reportlab(r).startswith(b"%PDF-")
