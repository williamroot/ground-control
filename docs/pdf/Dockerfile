# Renderizador de documentação em PDF.
#
# Usa WeasyPrint — a MESMA engine que gera as faturas do #1P — para não introduzir
# uma segunda tecnologia de PDF no projeto. É imagem própria (não a do sidecar)
# para que gerar documentação não dependa de ter a stack construída.
FROM python:3.12-slim

# Dependências nativas do WeasyPrint (cairo/pango/gdk-pixbuf) + fontes.
# fonts-dejavu cobre os símbolos usados nos runbooks (✓, setas, box-drawing);
# sem ele o PDF sai com tofu no lugar dos marcadores de "esperado".
RUN apt-get update && apt-get install -y --no-install-recommends \
        libpango-1.0-0 libpangoft2-1.0-0 libcairo2 libgdk-pixbuf-2.0-0 \
        libffi-dev shared-mime-info \
        fonts-dejavu-core fonts-liberation2 \
    && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir "weasyprint>=63,<70" "markdown>=3.6,<4" "pygments>=2.18,<3"

WORKDIR /w
ENTRYPOINT ["python", "/render/render.py"]
