# .ia/ — documentação viva do Ground Control

Índice da documentação que muda com frequência. Leia **antes** de mexer no repo.

## Ordem de leitura obrigatória (toda sessão)

1. `OVERVIEW.md` — problema, escopo, terminologia
2. `ARCHITECTURE.md` — containers, redes, fluxos, provisionamento
3. `OPS.md` — hosts, deploy, runbooks, troubleshooting

## Sob demanda

- `DEMO.md` — instância de **demonstração**: empresa fictícia, credenciais, inventário, roteiro de apresentação e como (re)semear/resetar
- `DECISIONS.md` — ADRs: por que cada decisão (PG18, base image, Redis, OpenSearch, gaps)
- `../docs/decisions/0001-stack.md` — ADR técnico canônico (inglês, gerado no build)

## Como atualizar

- Mudou container/rede/fluxo → `ARCHITECTURE.md`
- Mudou host/deploy/runbook → `OPS.md`
- Tomou decisão técnica não óbvia → `DECISIONS.md` (+ ADR numerado em `../docs/decisions/` se estrutural)
- Mudou escopo/terminologia → `OVERVIEW.md`

Mantenha conciso e factual. Documentação desatualizada é pior que ausente.
