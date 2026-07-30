#!/usr/bin/env bash
# Gera a documentação do Ground Control em PDF.
#
# Tudo em Docker — nada é instalado no host. A engine é WeasyPrint, a mesma que
# gera as faturas do #1P, para não termos duas tecnologias de PDF no projeto.
#
# Uso:  ./scripts/docs-pdf.sh
# Saída: docs/pdf/out/*.pdf  (gitignored — PDF é artefato, não fonte)
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

IMAGE="ground-control/docs-pdf:dev"
GENERATED_AT="$(date '+%d/%m/%Y')"
COMMIT="$(git rev-parse --short HEAD 2>/dev/null || echo 'sem git')"

echo "==> Construindo o renderizador (WeasyPrint em container)"
docker build -q -t "$IMAGE" docs/pdf >/dev/null

echo "==> Renderizando"
docker run --rm \
  -v "$ROOT:/w" \
  -v "$ROOT/docs/pdf:/render:ro" \
  -w /w \
  "$IMAGE" \
  --out docs/pdf/out \
  --generated-at "$GENERATED_AT" \
  --commit "$COMMIT"

echo "==> Pronto: docs/pdf/out/"
