# Spec #1 — Roadmap de planos de implementação (12 semanas, time expandido)

> Spec #1 cobre 5 subsistemas independentes. Cada um é entregue por um plano executável separado. Este documento é o índice e o plano de fases.

Spec base: [`../specs/2026-05-12-gerti-servicedesk-znuny-design.md`](../specs/2026-05-12-gerti-servicedesk-znuny-design.md)

## Compromisso de prazo

**MVP funcional em 12 semanas (3 meses)** — piloto operando para 1 cliente novo na nova plataforma. Time expandido para viabilizar paralelismo real.

## Time proposto

| Papel | Pessoas | Atuação |
|---|---|---|
| Tech Lead / Arquiteto | 1 | full-time atravessando todas as ondas; integra, revisa, desbloqueia |
| Backend Python (FastAPI/SQLAlchemy) | 2-3 | sidecar core, Auth Bridge, APIs, workers |
| Frontend Vue 3 (Nuxt 3 + Nuxt UI) | 2 | Portal Cliente SPA white-label |
| DevOps / Infra | 1 | Docker Compose, CI/CD, observabilidade, deploy, secrets |
| Perl OPM | 1 | GertiHooks.opm (pode ser dev Python aprendendo Perl com mentoria) |
| **Total** | **6-7** | |

## Distribuição em 6 sprints quinzenais

```
Semana   1   2   3   4   5   6   7   8   9   10  11  12
        ├───────┼───────┼───────┼───────┼───────┼───────┤
Sprint   S1      S2      S3      S4      S5      S6
        ├───────┼───────┼───────┼───────┼───────┼───────┤
1A      ████████                                            Foundation (time todo)
1B              ████████                                    GertiHooks.opm (Perl)
1C              ████████████                                Sidecar domain (2 Python)
1D              ████████                                    Auth Bridge (1 Python)
1E                      ████████████                        Sidecar APIs (2 Python)
1F                              ████████████████            Portal Nuxt (2 Vue/Nuxt)
1G                                      ████████            Onboarding (1 Python)
Hardening                                       ████████    integração + bug fixes
Piloto                                                  ████████ 1 cliente novo
```

### Sprint 1 (semanas 1-2) — Foundation
- **1A** executado pelo time todo: scaffolding monorepo, Docker Compose dev, Postgres+schemas+RLS, sidecar skeleton, CI básico.
- Saída: `make check` verde, `smoke-test.sh` passa, todos os devs com ambiente local rodando.
- **Status atual: 8/15 tasks concluídas** (Tasks 1-8). Faltam Tasks 9-15 (Alembic, FastAPI, middleware, RLS smoke, CI, e2e, README).

### Sprint 2 (semanas 3-4) — Componentes paralelos
- **1B GertiHooks.opm** (1 dev Perl): pacote com dynamic fields, queues template, event handlers que disparam webhooks HMAC.
- **1C Sidecar domain & repos** (2 devs Python): modelos contract/contract_cycle/consumption_event/glosa/service_catalog + repositórios + RLS policies.
- **1D Auth Bridge OIDC** (1 dev Python): provider OIDC validando contra Znuny, JWT RS256, endpoints `/oidc/.well-known/*`.
- **Portal scaffold** (2 devs Vue/Nuxt): projeto Nuxt 3 (SSR Universal), Nuxt UI v3, Tailwind, Pinia, design tokens, layout shell, integração com Auth Bridge stub.
- Saída: smoke tests por componente; integração via mock.

### Sprint 3 (semanas 5-6) — APIs públicas + UI components
- **1E Sidecar APIs públicas** (2 devs Python, depende de 1B+1C+1D): `/v1/contracts`, `/v1/tickets`, `/v1/catalog/services`, `/v1/dashboards`, `/v1/webhooks/znuny/*`.
- **Portal layout & components** (2 devs Vue/Nuxt): tela de login (PKCE flow real via composables `useOidc`), listagem de tickets, página de abertura via catálogo (form_schema renderer com componentes Nuxt UI).
- Saída: chamada real Portal → API → Znuny funciona ponta-a-ponta para um happy path.

### Sprint 4 (semanas 7-8) — Portal MVP + onboarding
- **1F Portal Cliente Nuxt MVP** (2 devs Vue/Nuxt, depende de 1D+1E): tela completa de abertura via catálogo, listagem com filtros, detalhe de ticket, aprovação para faturamento, dashboard executivo básico. Server middleware do Nitro injeta branding por tenant antes do paint.
- **1G Onboarding tenant** (1 dev Python, depende de 1E): API admin de criação de tenant + chamadas a Znuny (criar customer_company, queues, dynamic fields), interface admin mínima.
- Saída: admin Gerti cria um tenant novo via API; tenant tem subdomínio funcional com portal branded.

### Sprint 5 (semanas 9-10) — Integração + hardening
- Bug fixes do que apareceu na integração ponta-a-ponta.
- Testes de carga leves (~100 tickets, ~10 contratos).
- Observabilidade (logs estruturados + traces + dashboard Grafana inicial).
- Documentação de operação (runbook, on-call).
- Hardening: secrets via Vault, network policies, healthchecks ajustados.

### Sprint 6 (semanas 11-12) — Piloto + buffer
- Onboarding de **1 cliente novo real** (não migração — cliente que adoeceria no Tiflux ou cliente já novo).
- Acompanhamento diário durante a primeira semana de uso.
- Buffer para imprevistos: 1 semana garantida.
- Saída: cliente operando em produção; Tiflux desativado para este cliente.

## Sumário de planos

| # | Plano | Sprint | Estado | Donos sugeridos |
|---|---|---|---|---|
| **[1A — Foundation & Dev Stack](2026-05-12-spec-1a-foundation.md)** | S1 (sem 1-2) | em execução · 8/15 | time todo |
| 1B — GertiHooks.opm | S2 (sem 3-4) | a escrever | 1× Perl |
| 1C — Sidecar domain & repos | S2 (sem 3-4) | a escrever | 2× Python |
| 1D — Auth Bridge OIDC | S2 (sem 3-4) | a escrever | 1× Python |
| 1E — Sidecar APIs públicas | S3 (sem 5-6) | a escrever | 2× Python |
| 1F — Portal Cliente Nuxt MVP | S3-S4 (sem 5-8) | a escrever | 2× Vue/Nuxt |
| 1G — Onboarding tenant + admin | S4 (sem 7-8) | a escrever | 1× Python |
| **Integração + piloto** | S5-S6 (sem 9-12) | — | time todo |

## Riscos do prazo apertado

| Risco | Mitigação |
|---|---|
| Time não está completo no início | Começar 1A com quem está; ramp up de novos devs durante S1 (foundation tem boa documentação) |
| 1B (Perl) atrasa e bloqueia 1E | Mock dos webhooks em 1E enquanto 1B não está pronto; pareamento entre Perl dev e tech lead |
| 1F (Portal) é o caminho mais longo | Cortar escopo: portal MVP entrega apenas catálogo de serviços, listagem e abertura. Dashboards refinados ficam para Spec #2 |
| Integração revela acoplamento maior | Spike de integração já na semana 4 (1B+1C antes de 1E); não esperar S5 |
| Onboarding do piloto demora | Cliente piloto definido na semana 2; ambiente staging com os dados dele desde S4 |

## Como rodar este roadmap

1. **Plano 1A já em execução** (subagent-driven). Concluir Tasks 9-15 da Spec #1A é prioridade imediata para destravar todos os outros planos.
2. Ao final de S1, planos 1B/1C/1D são detalhados em paralelo (cada um por um sub-time).
3. Cada plano detalhado vira PR sequencial gerenciado pela skill `superpowers:subagent-driven-development` ou `executing-plans`.
4. Demo quinzenal ao final de cada sprint — stakeholders Gerti e WAS validam progresso.
