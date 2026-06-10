#!/bin/sh
# build.sh — cross-compila o gc-agent (#1R-b) para os 3 alvos e deposita os
# binários no diretório de saída (default: ../sidecar/agent-dist), onde a imagem
# do sidecar os bakeia para servir em GET /v1/agent/download/{os_arch}.
#
# Uso:
#   apps/agent/build.sh [OUT_DIR]
#
# Binários estáticos (CGO_ENABLED=0), nomes <os>-<arch> (windows ganha .exe) —
# exatamente os nomes esperados pelo endpoint de download.

set -eu

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
OUT_DIR="${1:-${SCRIPT_DIR}/../sidecar/agent-dist}"

mkdir -p "$OUT_DIR"
OUT_DIR="$(cd "$OUT_DIR" && pwd)"

export CGO_ENABLED=0
LDFLAGS="-s -w"

# alvos: "os arch nome-do-arquivo"
build_one() {
  os="$1"; arch="$2"; out="$3"
  echo "build ${os}/${arch} -> ${OUT_DIR}/${out}"
  ( cd "$SCRIPT_DIR" && GOOS="$os" GOARCH="$arch" go build -ldflags "$LDFLAGS" -o "${OUT_DIR}/${out}" . )
}

build_one linux   amd64 linux-amd64
build_one windows amd64 windows-amd64.exe
build_one darwin  arm64 darwin-arm64

echo "binários em ${OUT_DIR}:"
ls -la "$OUT_DIR"
