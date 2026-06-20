"""Configuração da suíte e2e (browser, contra a stack viva).

Tudo via env com defaults de DEMO (credenciais públicas/descartáveis, ver
.ia/DEMO.md). Para apontar a outro ambiente, sobrescreva as GC_* no shell.
"""
import os


def _env(key: str, default: str) -> str:
    return os.environ.get(key, default)


# Hosts públicos (Cloudflare). Ambiente único: "staging"=="prod".
ADMIN_BASE = _env("GC_ADMIN_BASE", "https://gerti.was.dev.br")
API_BASE = _env("GC_API_BASE", "https://api-dev.was.dev.br")

# Tenants white-label de teste (#1F-a). Login do portal é por E-MAIL.
TENANTS = {
    "aurora": {
        "base": _env("GC_AURORA_BASE", "https://aurora.was.dev.br"),
        "user": _env("GC_AURORA_USER", "eduardo.salvi@auroramoveis.com.br"),
        "password": _env("GC_AURORA_PASS", "Aurora@Demo2026"),
        "name": "Aurora",
    },
    "technova": {
        "base": _env("GC_TECHNOVA_BASE", "https://technova.was.dev.br"),
        "user": _env("GC_TECHNOVA_USER", "admin.tech@technova.example"),
        "password": _env("GC_TECHNOVA_PASS", "TechNova@Demo2026"),
        "name": "TechNova",
    },
}

# Agente do Console (#1G-a).
ADMIN_USER = _env("GC_ADMIN_USER", "william")
ADMIN_PASS = _env("GC_ADMIN_PASS", "Gerti@Demo2026")

# IDs/fixtures conhecidos do seed de demo.
AURORA_TENANT_ID = _env("GC_AURORA_TID", "5effe6fd-005e-43e4-9b1a-81107eb7f1a9")
AURORA_TICKET_ID = _env("GC_AURORA_TICKET", "39")  # "Lentidão na VPN" (open, c/ thread)
AURORA_CLOSED_TICKET = _env("GC_AURORA_CLOSED_TICKET", "36")  # fechado, já avaliado (CSAT)

# Playwright não tem download pré-built no ubuntu26.04 → usa o Chromium do host.
# Em CI normal, faça `playwright install chromium` e exporte GC_CHROMIUM_PATH="".
CHROMIUM_PATH = _env("GC_CHROMIUM_PATH", "/usr/bin/chromium-browser")
