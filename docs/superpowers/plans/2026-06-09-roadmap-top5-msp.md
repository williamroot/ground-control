# Roadmap — Top 5 features MSP (Ground Control)

> **Para workers agênticos:** SUB-SKILL OBRIGATÓRIA — use `superpowers:subagent-driven-development` (recomendado) ou `superpowers:executing-plans` para executar **cada plano de feature** tarefa-a-tarefa. Este arquivo é o **mestre**: sequência, infraestrutura compartilhada e invariantes. Os 5 planos detalhados estão em arquivos irmãos (`2026-06-09-1m-…` … `1q-…`).

**Goal:** entregar as 5 features que mais nos separam de um PSA/ITSM de MSP maduro — CSAT, IA (sumarização + resposta sugerida), Dashboards, Faturas e Automação — com arquitetura limpa, ancoradas nas convenções reais do sidecar/Nuxt/Znuny.

**Architecture:** cada feature é um **subsistema independente** (próprio spec→plano→deploy), seguindo o padrão consolidado: router FastAPI sob `/v1` → domain service → model SQLAlchemy + migration Alembic (FORCE RLS quando tenant-scoped) → integração Znuny via Generic Interface → proxy Nuxt `server/api/**` → page/componente. Motor de LLM = **Ollama Cloud `gpt-oss:120b`** via cliente async dedicado.

**Tech Stack:** Python 3.12 / FastAPI / SQLAlchemy 2 async / Alembic / Postgres 18 (RLS) / httpx · Nuxt 3 (SSR, Nuxt UI v3, charts SVG próprios) · Znuny 7.2.3 GI (Perl, overlay `Custom/`) · Ollama Cloud · WeasyPrint (PDF) · OpenSearch (ad-hoc interno).

---

## Decisões de escopo (aprovadas pelo usuário, 2026-06-09)

| Feature | Decisão |
|--------|---------|
| **#1M CSAT** | CSAT **1–5 no portal ao fechar** o ticket (inline no detalhe; sem e-mail/token). |
| **#1N IA** | Motor **Ollama Cloud `gpt-oss:120b`**; **sumarização** + **resposta sugerida** no console do agente. |
| **#1O Dashboards** | **Híbrido**: charts próprios (SVG) no console + portal por-tenant; OpenSearch Dashboards só para exploração **ad-hoc interna** (não exposto ao cliente). |
| **#1P Faturas** | **Fatura interna** (PDF branded + status open/paid/overdue/void). Sem fiscal/contábil nesta fase. |
| **#1Q Automação** | **Motor de regras próprio no sidecar** (ingestão de eventos Znuny via webhook HMAC → DSL de condições → ações via GI), com UI no-code no console. |

## Sequência de entrega (impacto/esforço, com dependências de dados)

1. **#1M CSAT** (B) — quick win; gera a métrica de satisfação que o dashboard consome.
2. **#1N IA** (B/M) — introduz a infra compartilhada `integrations/ollama.py`; independente de dados.
3. **#1O Dashboards** (M) — consome CSAT (#1M), consumo (#1B) e timers (#1J); usa OpenSearch ad-hoc.
4. **#1P Faturas** (M) — consome ciclos/consumo (#1B); adiciona PDF branded.
5. **#1Q Automação** (M/A) — maior superfície; pode acionar IA (#1N) e CSAT (#1M); fecha o ciclo.

Cada feature é **mergeável e deployável sozinha** (gate `make test` + e2e em staging, padrão das anteriores).

## Numeração de migrations (a partir do HEAD `0014_agent_timer`)

| Revisão | Feature | Tabelas |
|--------|---------|---------|
| `0015_csat` | #1M | `csat_response` (RLS) |
| `0016_ai_generation_log` | #1N | `ai_generation_log` (operacional, sem RLS) |
| `0017_invoice` | #1P | `invoice` + `invoice_line` (RLS) |
| `0018_automation` | #1Q | `automation_rule` + `automation_run` (RLS) |

Dashboards (#1O) **não cria tabela** — agrega o que já existe + uma GI op `TicketStats`. Encadear `down_revision` na ordem de merge real; se duas features forem para `main` fora de ordem, ajustar `down_revision` no rebase (cada plano assume seu predecessor imediato).

## Infraestrutura compartilhada

### A. Cliente Ollama Cloud — `integrations/ollama.py` (entregue em #1N, reutilizável)
Cliente async failure-safe espelhando o padrão `integrations/znuny_*` (`_post`, exceções → status). Usa a **API nativa `/api/chat`** (NDJSON), que é o caminho **confirmado** para o cloud; o `/v1/chat/completions` OpenAI-compat fica como otimização futura **a verificar** ao vivo. Detalhe completo (código) no plano #1N — as demais features que precisarem de LLM importam daqui.

**Env vars novas** (em `config.py` `Settings`):
```python
ollama_api_key: str = ""                       # OLLAMA_API_KEY (vazio = IA desabilitada, fail-soft)
ollama_base_url: str = "https://ollama.com"    # OLLAMA_BASE_URL
ollama_model: str = "gpt-oss:120b"             # OLLAMA_MODEL
ollama_timeout_seconds: int = 120              # OLLAMA_TIMEOUT_SECONDS
ai_features_enabled: bool = False              # AI_FEATURES_ENABLED (kill-switch global)
```
Secret só em `.env.prod` (gitignored) — **nunca commitar** o `OLLAMA_API_KEY` (mesma regra do tunnel token).

### B. Egress de dados para o LLM (decisão de segurança, cross-cutting)
Sumarização/resposta sugerida **enviam conteúdo de ticket para um serviço externo** (Ollama Cloud). Invariante: (1) feature é **opt-in** por env (`AI_FEATURES_ENABLED`) e some da UI quando off; (2) só o **agente** (sessão `gsid_adm`) aciona; (3) resposta sugerida **nunca** é enviada automaticamente — sempre popula um rascunho que o agente edita; (4) documentar o egress no `.ia/SECURITY`/`OPS`. Registrar cada geração em `ai_generation_log` (auditoria + consciência de custo GPU-time).

### C. Ingestão de eventos Znuny → sidecar (entregue em #1Q)
Um **webservice GI tipo Invoker** no Znuny dispara em eventos de ticket (`TicketCreate`, `ArticleCreate`, close, escalation) e faz `POST` assinado (HMAC, segredo já modelado em `ZnunyInstance.webhook_signing_secret_ref`) para `/v1/hooks/znuny/ticket-event`. Reutilizável por automação (#1Q) e, no futuro, por dashboards em tempo real. Detalhe no plano #1Q.

### D. Charts SVG próprios — `apps/portal/components/charts/` e `apps/admin/components/charts/`
Já existem `AreaChart.vue`, `ProgressBar.vue`, `Sparkline.vue` (SVG puro, `var(--brand-primary)`, SSR-safe via `useId()`). #1O adiciona `BarChart.vue` e `DonutChart.vue` no mesmo padrão (zero deps externas). Regra **H8**: cor da marca só para identidade; estados (SLA breach, CSAT baixo) usam cores **semânticas**.

## Invariantes herdados (valem para as 5)

- **Núcleo Znuny imutável** — só overlay `Custom/` e webservices versionados em `znuny/webservices/`.
- **Multi-tenant**: tabelas de negócio são `tenant_id` + `FORCE ROW LEVEL SECURITY` com policy `tenant_id = current_setting('app.current_tenant')::uuid`; acesso via `tenant_session_scope`. Tabelas **operacionais** (logs cross-tenant, como `ai_generation_log`) ficam sem RLS e são lidas via `AdminSessionLocal` (BYPASSRLS).
- **Auth**: rota de cliente → `Depends(get_current_session)` (+ `require_admin` quando for admin do tenant); rota de agente → `Depends(get_admin_session)`.
- **GI failure-safe**: `ZnunyUnavailable` → 503, `ZnunyWriteError` → 400/422. Novo: `OllamaUnavailable` → 503.
- **TDD + commits frequentes**: cada tarefa = teste falhando → impl mínima → verde → commit. Gate final `make test` + e2e staging.
- **Docs voyager**: mudou algo → atualizar `.ia/` correspondente no **mesmo PR** (ARCHITECTURE/INTEGRATION/OPS/DECISIONS).

## Pontos a verificar antes de codar (de pesquisa)

1. **Ollama cloud OpenAI-compat** (`https://ollama.com/v1/chat/completions`): não confirmado na doc oficial — usar `/api/chat` nativo (confirmado) e só tentar `/v1` como otimização com smoke test `GET /v1/models`.
2. **Limites do tier Ollama** (free/pro, GPU-time, 1 modelo concorrente no free): confirmar em `ollama.com/pricing` antes de dimensionar concorrência. `gpt-oss:120b` = contexto **128K**.
3. **WeasyPrint deps nativas** (cairo/pango/gdk-pixbuf) no Dockerfile do sidecar — validar imagem ou cair para ReportLab (trade-off no #1P).
4. **Eventos Znuny** para o Invoker (#1Q): confirmar nomes exatos na 7.2.3 (`TicketCreate`, `ArticleCreate`, `TicketStateUpdate`, `Escalation<Type>TimeStart`).

## Handoff de execução

Plano completo. Recomendação: **subagent-driven**, um subagente fresco por tarefa com revisão entre tarefas (padrão usado em #1J/#1K/#1L). Execute os planos **na ordem da sequência** (1M→1N→1O→1P→1Q); cada um termina com merge + deploy staging + e2e antes do próximo.
