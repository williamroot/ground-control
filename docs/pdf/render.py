"""Renderiza a documentação do Ground Control em PDF.

Markdown -> HTML (python-markdown) -> PDF (WeasyPrint, a MESMA engine das faturas
do #1P, para não termos duas tecnologias de PDF no projeto).

Roda só dentro do container `docs/pdf/Dockerfile` — nada é instalado no host.
Uso: `scripts/docs-pdf.sh` (ou veja o `argparse` abaixo).
"""

from __future__ import annotations

import argparse
import base64
import html
import re
from dataclasses import dataclass
from pathlib import Path

import markdown
from weasyprint import CSS, HTML

STYLE = Path("/render/style.css")

# Marcadores dos runbooks: "✅ **Esperado:**" é a linha que a pessoa procura ao
# voltar ao documento depois de executar um passo. O ✓ do DejaVu é confiável em
# PDF; o emoji nem sempre tem fonte no container e viraria tofu.
MARKER_REPLACEMENTS = {
    "✅": '<span class="ok">✓</span>',
    "⚠️": '<span class="ok">!</span>',
    "🔐": '<span class="ok">#</span>',
}


@dataclass(frozen=True)
class Doc:
    """Um documento a renderizar."""

    source: Path
    title: str
    subtitle: str


def _slug(text: str) -> str:
    s = re.sub(r"[^\w\s-]", "", text.lower()).strip()
    return re.sub(r"[\s_]+", "-", s)


def _apply_markers(rendered: str) -> str:
    for needle, replacement in MARKER_REPLACEMENTS.items():
        rendered = rendered.replace(needle, replacement)
    return rendered


def _build_toc(md: markdown.Markdown) -> str:
    """Sumário com número de página, resolvido pelo WeasyPrint (target-counter)."""
    items = getattr(md, "toc_tokens", [])
    if not items:
        return ""

    def render(tokens: list[dict], depth: int = 0) -> str:
        if not tokens or depth > 1:  # só H1/H2 — um sumário que cabe numa página
            return ""
        parts = ["<ul>"]
        for token in tokens:
            name = html.escape(token["name"])
            parts.append(f'<li><a href="#{token["id"]}">{name}</a>')
            parts.append(render(token.get("children", []), depth + 1))
            parts.append("</li>")
        parts.append("</ul>")
        return "".join(parts)

    return f'<nav class="toc"><h2>Sumário</h2>{render(items)}</nav>'


# Mark do Ground Control — o mesmo crosshair de `landing/assets/favicon.svg`, na cor
# de sinal da marca (#FF6B1A). Vai embutido como data URI porque o suporte nativo a
# SVG do WeasyPrint é parcial; como <img> ele renderiza igual em qualquer versão.
_BRANDMARK_SVG = (
    '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 40 40">'
    '<circle cx="20" cy="20" r="15" fill="none" stroke="#FF6B1A" stroke-width="2"/>'
    '<circle cx="20" cy="20" r="4" fill="#FF6B1A"/>'
    '<line x1="20" y1="2" x2="20" y2="9" stroke="#FF6B1A" stroke-width="2"/>'
    '<line x1="20" y1="31" x2="20" y2="38" stroke="#FF6B1A" stroke-width="2"/>'
    '<line x1="2" y1="20" x2="9" y2="20" stroke="#FF6B1A" stroke-width="2"/>'
    '<line x1="31" y1="20" x2="38" y2="20" stroke="#FF6B1A" stroke-width="2"/>'
    "</svg>"
)


def _brandmark() -> str:
    encoded = base64.b64encode(_BRANDMARK_SVG.encode("utf-8")).decode("ascii")
    return f'<img class="cover__logo" src="data:image/svg+xml;base64,{encoded}" alt="">'


def _cover(doc: Doc, generated_at: str, commit: str) -> str:
    return f"""
    <section class="cover">
      <div class="cover__brand">
        {_brandmark()}
        <div class="cover__lockup">
          <span class="cover__wordmark">Ground Control</span>
          <span class="cover__tagline">Service Desk Platform &middot; White-label &middot; MSP-first</span>
        </div>
      </div>
      <div class="cover__mark">Documentação</div>
      <h1 class="cover__title">{html.escape(doc.title)}</h1>
      <p class="cover__subtitle">{html.escape(doc.subtitle)}</p>
      <div class="cover__meta">
        <strong>Gerado em</strong> {html.escape(generated_at)}
        &nbsp;&middot;&nbsp; <strong>Revisão</strong> {html.escape(commit)}
        <br>Plataforma de Service Desk para MSP &mdash; núcleo Znuny, white-label por cliente.
        <div class="cover__was">Engineered by <strong>WAS Soluções em Tecnologia</strong></div>
      </div>
    </section>
    """


def render(doc: Doc, out_dir: Path, generated_at: str, commit: str) -> Path:
    md = markdown.Markdown(
        extensions=["tables", "fenced_code", "toc", "sane_lists", "attr_list"],
        extension_configs={"toc": {"slugify": lambda value, sep: _slug(value)}},
    )
    body = md.convert(doc.source.read_text(encoding="utf-8"))
    body = _apply_markers(body)

    # O H1 do markdown vira o título corrente do cabeçalho (string-set no CSS);
    # a capa já mostra o título, então o do corpo é redundante — removido.
    body = re.sub(r"<h1[^>]*>.*?</h1>", "", body, count=1, flags=re.DOTALL)

    document = f"""<!doctype html>
<html lang="pt-BR"><head><meta charset="utf-8"><title>{html.escape(doc.title)}</title></head>
<body>{_cover(doc, generated_at, commit)}{_build_toc(md)}
<main><h1>{html.escape(doc.title)}</h1>{body}</main></body></html>"""

    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{doc.source.stem}.pdf"
    HTML(string=document, base_url=str(doc.source.parent)).write_pdf(
        out_path, stylesheets=[CSS(filename=str(STYLE))]
    )
    return out_path


def main() -> None:
    parser = argparse.ArgumentParser(description="Gera a documentação em PDF.")
    parser.add_argument("--out", default="docs/pdf/out", help="diretório de saída")
    parser.add_argument("--generated-at", required=True, help="data legível da geração")
    parser.add_argument("--commit", required=True, help="revisão curta do git")
    args = parser.parse_args()

    docs = [
        Doc(
            Path("docs/REQUISITOS-RECURSOS-ADMINISTRATIVOS.md"),
            "Recursos administrativos",
            "O vídeo do Kleber convertido em 18 requisitos numerados, com o estado de "
            "cada um no código, as tarefas, os termos de aceite e os testes que os "
            "provam — mais a transcrição integral com marcação de tempo.",
        ),
        Doc(
            Path("docs/ENTREGA-RECURSOS-ADMINISTRATIVOS.md"),
            "Entrega — recursos administrativos",
            "O fechamento da campanha aberta a partir do vídeo: o que mudou em "
            "cada requisito, as decisões que assumimos no lugar dele (com o "
            "custo de mudar de ideia) e o roteiro para conferir com as próprias "
            "mãos no ambiente de homologação.",
        ),
        Doc(
            Path("docs/SUPOSICOES-A-VALIDAR.md"),
            "Suposições a validar",
            "As seis leituras do vídeo do Kleber que assumimos sem confirmação — cada "
            "uma com a chave que a controla, o custo de mudar de ideia e as perguntas "
            "prontas para levar a ele.",
        ),
        Doc(
            Path("docs/ENTREGA-E-ROADMAP.md"),
            "Entrega e roadmap",
            "O que foi entregue nesta rodada, os acessos do ambiente de "
            "demonstração e o que vem a seguir — documento de apresentação.",
        ),
        Doc(
            Path("docs/COMO-TESTAR-PARIDADE-INTERFACE.md"),
            "Como testar a paridade de interface",
            "Base de conhecimento, catálogo de serviços, notificações, identidade "
            "visual, auditoria e saúde do sistema — roteiro passo a passo, com a "
            "prova de isolamento entre clientes.",
        ),
        Doc(
            Path("docs/COMO-TESTAR-ADMIN-ZNUNY.md"),
            "Como testar a administração do Znuny",
            "Filas, SLAs, serviços, classificação, classes de CI, agentes e "
            "calendário — administrados pelo console, ao vivo, sem duplicar dado.",
        ),
        Doc(
            Path("docs/COMO-TESTAR-AGENTE-INVENTARIO.md"),
            "Como testar o agente de inventário",
            "Auto-registro de equipamentos no CMDB do cliente por token de "
            "enrollment, com aprovação, revogação e prova de isolamento.",
        ),
        Doc(
            Path(".ia/DEMO.md"),
            "Instância de demonstração",
            "A operação fictícia usada em apresentação e teste: empresa, agentes, "
            "clientes, credenciais e como (re)semear.",
        ),
        Doc(
            Path(".ia/OVERVIEW.md"),
            "Visão geral da plataforma",
            "O problema que o Ground Control resolve, o escopo e a terminologia.",
        ),
        Doc(
            Path(".ia/ARCHITECTURE.md"),
            "Arquitetura",
            "Containers, redes, fluxos, provisionamento e os subsistemas de produto.",
        ),
        Doc(
            Path(".ia/OPS.md"),
            "Operação e runbooks",
            "Hosts, deploy, verificação, rollback e troubleshooting.",
        ),
        Doc(
            Path(".ia/DECISIONS.md"),
            "Decisões de arquitetura",
            "Os ADRs: por que cada decisão foi tomada — e, quando foi o caso, "
            "por que foi corrigida.",
        ),
    ]

    out_dir = Path(args.out)
    for doc in docs:
        if not doc.source.exists():
            print(f"  ignorado (não existe): {doc.source}")
            continue
        path = render(doc, out_dir, args.generated_at, args.commit)
        size_kb = path.stat().st_size / 1024
        print(f"  {path}  ({size_kb:.0f} KB)")


if __name__ == "__main__":
    main()
