"""Distribuição do agente de inventário (Spec #1R-b) — /v1/agent/install.sh + download.

Rotas PÚBLICAS (sem auth): só servem o script de instalação e os binários
cross-compilados. O segredo (enroll token) NUNCA vem por aqui — é passado por flag
pelo operador (`sh -s -- --enroll-token=…`). `/v1/agent` já está na allowlist do
TenantMiddleware (#1R-a), então estas rotas não exigem subdomínio de tenant.

- GET /v1/agent/install.sh?server=<url> → renderiza o template embutindo o server.
- GET /v1/agent/download/{os_arch}      → serve o binário de AGENT_DIST_DIR;
  os-arch inválido / path traversal / binário ausente → 404.
"""

from __future__ import annotations

import re
from pathlib import Path

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import FileResponse, PlainTextResponse

from gerti_sidecar.config import get_settings

router = APIRouter(prefix="/agent", tags=["agent"])

_TEMPLATE_PATH = Path(__file__).resolve().parent.parent / "templates" / "install.sh.tmpl"

# os-arch aceito: <os>-<arch> com os/arch alfanuméricos. Casado de forma ancorada
# para barrar path traversal e qualquer caractere fora do padrão.
_OS_ARCH_RE = re.compile(r"^[a-z0-9]+-[a-z0-9]+$")

# Mapa os-arch → nome do arquivo no diretório de dist (windows ganha .exe).
_BINARY_NAMES = {
    "linux-amd64": "linux-amd64",
    "windows-amd64": "windows-amd64.exe",
    "darwin-arm64": "darwin-arm64",
}

# Server aceito: http(s)://host[...]. Barra qualquer coisa que não seja URL http
# (evita injeção de shell no script renderizado).
_SERVER_RE = re.compile(r"^https?://[A-Za-z0-9._\-]+(:[0-9]+)?(/[A-Za-z0-9._~\-/]*)?$")


@router.get("/install.sh")
async def install_script(server: str | None = Query(default=None)) -> PlainTextResponse:
    settings = get_settings()
    chosen = server or settings.agent_server_url
    chosen = chosen.rstrip("/")
    if not _SERVER_RE.match(chosen):
        raise HTTPException(status_code=400, detail="invalid_server")

    template = _TEMPLATE_PATH.read_text(encoding="utf-8")
    rendered = template.replace("__GC_DEFAULT_SERVER__", chosen)
    return PlainTextResponse(
        rendered,
        media_type="text/x-shellscript",
        headers={"Cache-Control": "no-store"},
    )


@router.get("/download/{os_arch}")
async def download_binary(os_arch: str) -> FileResponse:
    if not _OS_ARCH_RE.match(os_arch) or os_arch not in _BINARY_NAMES:
        raise HTTPException(status_code=404, detail="unknown_os_arch")

    settings = get_settings()
    dist_dir = Path(settings.agent_dist_dir).resolve()
    target = (dist_dir / _BINARY_NAMES[os_arch]).resolve()

    # Defesa em profundidade: o alvo resolvido tem que ficar dentro do dist_dir.
    if dist_dir not in target.parents and target != dist_dir:
        raise HTTPException(status_code=404, detail="not_found")
    if not target.is_file():
        # Em dev, o diretório pode não ter o binário ainda → 404 com instrução.
        raise HTTPException(status_code=404, detail="binary_not_built")

    return FileResponse(
        path=str(target),
        media_type="application/octet-stream",
        filename=f"gc-agent-{os_arch}",
    )
