"""Render do relatório executivo mensal para PDF (T-R18b.3, R18b).

Mesmo pipeline da fatura (`invoice_pdf.py`): Jinja2 + WeasyPrint, com o
ReportLab como rede de segurança quando a imagem não tem as libs nativas
(cairo/pango). A escolha fica isolada aqui — o resto do código só conhece
`render_report_pdf(report) -> bytes`.

**Diferença deliberada em relação à fatura:** o fallback ReportLab da fatura não
pagina, e a Onda 0 registrou isso como dívida aceitável porque uma fatura tem 2
a 4 linhas. Um relatório executivo tem a "listona de chamados" e pode ter
centenas — então o fallback daqui **pagina de verdade** e nunca deixa conteúdo
cair fora da página em silêncio.

Marca: o relatório sai com a identidade do **cliente**, igual à fatura. É
suposição de baixo risco (o levantamento registra a dúvida: quem envia é a
Gerti, então poderia ser a marca dela) — trocar é passar outro branding para
`render_report_pdf`, sem tocar no template.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader, select_autoescape

_TEMPLATES_DIR = Path(__file__).resolve().parent.parent / "templates"

_CONTRACT_TYPE_LABELS = {
    "hour_bank": "Banco de horas",
    "credit_brl": "Crédito em reais",
    "credit_shared": "Crédito compartilhado",
    "service_count": "Pacote de atendimentos",
    "closed_value": "Valor fechado",
    "saas_product": "Produto SaaS",
    "free": "Livre",
}

ReportLike = Any


def _money_brl(value: float) -> str:
    s = f"{value:,.2f}"
    s = s.replace(",", "_").replace(".", ",").replace("_", ".")
    return f"R$ {s}"


def _fmt_value(consumption: Any) -> str:
    """O número já com a unidade certa — é o aceite A18b.2 virando texto."""
    if consumption.kind == "brl":
        return _money_brl(consumption.value)
    if consumption.kind == "hours":
        return f"{consumption.value:.2f} h".replace(".", ",")
    if consumption.kind == "services":
        return f"{int(consumption.value)}"
    return "—"


def _type_label(value: str) -> str:
    return _CONTRACT_TYPE_LABELS.get(value, value)


def render_report_html(report: ReportLike) -> str:
    env = Environment(
        loader=FileSystemLoader(str(_TEMPLATES_DIR)),
        autoescape=select_autoescape(["html", "xml"]),
    )
    template = env.get_template("executive_report.html")
    return template.render(
        display_name=report.display_name,
        logo_url=report.branding.get("logo_url"),
        primary_color=report.branding.get("primary_color") or "#334155",
        month_label=report.month_label,
        period_start=report.period_start.strftime("%d/%m/%Y"),
        period_end=report.period_end.strftime("%d/%m/%Y"),
        consumption=report.consumption,
        dimension_label=report.dimension_label,
        top_items=report.top_items,
        tickets=report.tickets,
        ticket_total=report.ticket_total,
        tickets_truncated=report.tickets_truncated,
        fmt_value=_fmt_value,
        type_label=_type_label,
    )


def _render_weasyprint(html: str) -> bytes:
    # import tardio: lib nativa (cairo/pango) só carrega se usada.
    from weasyprint import HTML  # type: ignore[import-untyped]

    return HTML(string=html).write_pdf()  # type: ignore[no-any-return]


def _render_reportlab(report: ReportLike) -> bytes:
    """Fallback sem HTML/CSS. Pagina de verdade — ver o cabeçalho do módulo."""
    import io

    # import tardio; reportlab não publica py.typed, daí os ignores (idem
    # WeasyPrint) — mesmo tratamento de `invoice_pdf.py`.
    from reportlab.lib import colors  # type: ignore[import-untyped]
    from reportlab.lib.pagesizes import A4  # type: ignore[import-untyped]
    from reportlab.lib.styles import (  # type: ignore[import-untyped]
        ParagraphStyle,
        getSampleStyleSheet,
    )
    from reportlab.lib.units import mm  # type: ignore[import-untyped]
    from reportlab.platypus import (  # type: ignore[import-untyped]
        PageBreak,
        Paragraph,
        SimpleDocTemplate,
        Spacer,
        Table,
        TableStyle,
    )

    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=A4,
        leftMargin=16 * mm,
        rightMargin=16 * mm,
        topMargin=18 * mm,
        bottomMargin=18 * mm,
        title=f"Relatório executivo — {report.display_name} — {report.month_label}",
    )
    styles = getSampleStyleSheet()
    brand = colors.HexColor(report.branding.get("primary_color") or "#334155")
    h1 = ParagraphStyle("h1", parent=styles["Title"], textColor=brand, fontSize=18, spaceAfter=2)
    h2 = ParagraphStyle("h2", parent=styles["Heading2"], textColor=colors.HexColor("#64748b"))
    small = ParagraphStyle("small", parent=styles["Normal"], fontSize=8,
                           textColor=colors.HexColor("#94a3b8"))  # fmt: skip

    flow: list[Any] = [
        Paragraph(report.display_name, h1),
        Paragraph(f"Relatório executivo — {report.month_label}", styles["Normal"]),
        Paragraph(
            f"{report.period_start.strftime('%d/%m/%Y')} a "
            f"{report.period_end.strftime('%d/%m/%Y')}",
            small,
        ),
        Spacer(1, 10),
        Paragraph("Consumo do período", h2),
    ]

    if report.consumption:
        rows = [["Contrato", "Tipo", "Consumo"]]
        rows += [[c.code, _type_label(c.type), _fmt_value(c)] for c in report.consumption]
        table = Table(rows, hAlign="LEFT", colWidths=[55 * mm, 55 * mm, 45 * mm])
        table.setStyle(
            TableStyle(
                [
                    ("TEXTCOLOR", (0, 0), (-1, 0), colors.HexColor("#64748b")),
                    ("FONTSIZE", (0, 0), (-1, -1), 8),
                    ("LINEBELOW", (0, 0), (-1, 0), 0.5, colors.HexColor("#cbd5e1")),
                    ("ALIGN", (2, 1), (2, -1), "RIGHT"),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
                ]
            )
        )
        flow.append(table)
        if len(report.consumption) > 1:
            flow.append(Spacer(1, 4))
            flow.append(
                Paragraph("Contratos de tipos diferentes — os valores não se somam.", small)
            )
    else:
        flow.append(Paragraph("Nenhum contrato com consumo mensurável no período.", small))

    flow += [
        Spacer(1, 12),
        Paragraph(f"Principais chamados por {report.dimension_label.lower()}", h2),
    ]
    if report.top_items:
        rows = [[report.dimension_label, "Chamados"]]
        rows += [[label, str(count)] for label, count in report.top_items]
        table = Table(rows, hAlign="LEFT", colWidths=[110 * mm, 45 * mm])
        table.setStyle(
            TableStyle(
                [
                    ("TEXTCOLOR", (0, 0), (-1, 0), colors.HexColor("#64748b")),
                    ("FONTSIZE", (0, 0), (-1, -1), 8),
                    ("LINEBELOW", (0, 0), (-1, 0), 0.5, colors.HexColor("#cbd5e1")),
                    ("ALIGN", (1, 1), (1, -1), "RIGHT"),
                ]
            )
        )
        flow.append(table)
    else:
        flow.append(Paragraph("Nenhum chamado registrado no período.", small))

    flow += [PageBreak(), Paragraph(f"Chamados do período ({report.ticket_total})", h2)]
    if report.tickets:
        # SimpleDocTemplate quebra a Table em páginas sozinho — é justamente por
        # isso que este fallback pode carregar a listona inteira sem sumir com
        # nada, ao contrário do fallback da fatura.
        rows = [["Número", "Assunto", "Aberto em", "Estado", "Horas"]]
        for t in report.tickets:
            title = t.title if len(t.title) <= 58 else t.title[:57] + "…"
            rows.append([t.ticket_number, title, t.created[:10], t.state, f"{t.hours:.2f}"])
        table = Table(
            rows,
            hAlign="LEFT",
            colWidths=[30 * mm, 70 * mm, 22 * mm, 28 * mm, 16 * mm],
            repeatRows=1,
        )
        table.setStyle(
            TableStyle(
                [
                    ("TEXTCOLOR", (0, 0), (-1, 0), colors.HexColor("#64748b")),
                    ("FONTSIZE", (0, 0), (-1, -1), 7),
                    ("LINEBELOW", (0, 0), (-1, 0), 0.5, colors.HexColor("#cbd5e1")),
                    ("ALIGN", (4, 1), (4, -1), "RIGHT"),
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ]
            )
        )
        flow.append(table)
        if report.tickets_truncated:
            flow.append(Spacer(1, 4))
            flow.append(
                Paragraph(
                    f"Lista limitada aos primeiros {len(report.tickets)} chamados; "
                    f"a contagem total ({report.ticket_total}) continua correta.",
                    small,
                )
            )
    else:
        flow.append(Paragraph("Nenhum chamado no período.", small))

    doc.build(flow)
    return buf.getvalue()


def render_report_pdf(report: ReportLike) -> bytes:
    """Relatório executivo em PDF (WeasyPrint primário; ReportLab no fallback)."""
    try:
        return _render_weasyprint(render_report_html(report))
    except Exception:
        return _render_reportlab(report)
