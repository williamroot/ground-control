# e2e — suíte de browser (Playwright)

Testes end-to-end que dirigem o **navegador** contra a stack **viva** (portal
white-label + Console de Administração), via Cloudflare. Existem porque os e2e
dos specs sempre rodaram pela API do sidecar — nunca pelo browser — e uma classe
inteira de bugs de SSR/render/roteamento passou batido (ver
`.ia/` e o histórico de fixes de 2026-06-20). Esta suíte **trava essas regressões**.

## O que cobre (não-destrutivo, seguro p/ CI)

`test_portal.py` (Aurora + TechNova):
- login + branding por tenant;
- **sessão SSR sobrevive a carga direta/refresh** de `/`, `/tickets`, `/ativos`,
  `/faturas` (regressão crítica: redirecionavam p/ `/login`);
- isolamento cross-tenant (gsid de um tenant → **401** no outro);
- **#1S** "Melhorar com IA" (assist devolve rascunho);
- **CSAT** guards (422 aberto / 409 já avaliado).

`test_admin.py` (agente):
- login + lista de clientes;
- **detalhe de ticket no `/atendimento` renderiza** (regressão de casing: vinha
  em branco + timer quebrado);
- **Faturas (#1P), Agentes (#1R) e Novo Contrato renderizam** suas páginas
  (regressão de rota aninhada sem `<NuxtPage/>`).

## Como rodar

Pré-requisito: um Chromium executável. Neste host (ubuntu26.04, sem build
pré-built do Playwright) usamos o do sistema via `GC_CHROMIUM_PATH`
(default `/usr/bin/chromium-browser`).

```bash
cd e2e
uv venv && uv pip install -e .            # ou: pip install playwright pytest
# Em CI com browser baixado: playwright install chromium && export GC_CHROMIUM_PATH=""
uv run pytest -v
```

Config 100% por env (defaults de DEMO — credenciais públicas, ver `.ia/DEMO.md`):
`GC_ADMIN_BASE`, `GC_AURORA_BASE/USER/PASS`, `GC_TECHNOVA_BASE/USER/PASS`,
`GC_ADMIN_USER/PASS`, `GC_AURORA_TID`, `GC_AURORA_TICKET`, `GC_CHROMIUM_PATH`.

## Fluxos destrutivos (manuais — fora da suíte automática)

Estes **mutam produção** e exigem limpeza; rodar à mão com tenant/ticket
throwaway + remoção depois (padrão dos runbooks em `.ia/OPS.md`):

- Portal: abrir chamado (`POST /api/portal/tickets`) + responder + CSAT 201.
- Console: onboarding (`POST /api/admin/tenants`) + criar contrato + regra de
  automação (criar/editar/excluir) + token de agente (gerar/revogar) + gerar fatura.

Validados ao vivo em 2026-06-20 (todos 201/200, throwaways limpos). Não entram
no CI para não sujar/derrubar dados reais.
