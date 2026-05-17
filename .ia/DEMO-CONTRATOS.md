# Ground Control — DEMO do Motor de Contratos (#1C)

> Complementa [`DEMO.md`](DEMO.md) (Service Desk Znuny / Móveis Aurora). É o
> **mesmo cliente fictício** — o tenant de contratos é a própria Aurora
> Móveis (`znuny_customer_id = AURORA`), então as duas demos contam uma
> história só: a operação no Znuny + os contratos que a faturam.

> ⚠️ Dados fictícios, semeados **idempotentemente** por
> `apps/sidecar/scripts/seed_demo_contracts.py`. Em prod desde 2026-05-17.

## O que o motor #1C entrega (estado: **deployado e verificado em prod**)

Núcleo real de contratos (Spec #1C): modelo de dados + regras + **RLS
multi-tenant** (isolamento por `app.current_tenant`, fail-closed). **Ainda
NÃO há UI/API HTTP** — isso é a Spec #1E. A demonstração é via o motor
rodando de verdade (scripts de domínio + psql), provando as regras.

### As 6 modalidades de contrato (os "planos")

| Código (demo) | Modalidade | Conteúdo | Saldo inicial |
|---|---|---|---|
| `AUR-HORAS-2026` | **Banco de horas** (`hour_bank`) | 40h/ciclo, excedente R$180/h | 40 h |
| `AUR-CREDITO-2026` | **Crédito em R$** (`credit_brl`) | saldo R$20.000, +reajuste IPCA (teto 8%) + auto-renovação | R$ 20.000 |
| `AUR-POOL-2026` | **Crédito compartilhado** (`credit_shared`) | pool R$50.000 rateável | R$ 50.000 |
| `AUR-PACOTE-2026` | **Pacote por nº de serviços** (`service_count`) | 50 atendimentos/ciclo | 50 serviços |
| `AUR-FECHADO-2026` | **Valor fechado** (`closed_value`) | mensalidade R$9.000, sem saldo corrente | — |
| `AUR-SAAS-2026` | **Assinatura SaaS** (`saas_product`) | produto por assinatura R$1.490 | — |

\+ regras provadas no E2E: ciclos **faturamento ≠ fechamento**, **glosa**
(só glosa *aprovada* abate saldo — a pendente não), **reajuste por índice
com teto**, **renovação automática**, ledger **append-only**, **RLS** por
tenant.

## Prova E2E em produção (rodada real, role sem privilégio `gerti_sidecar`)

```
[PASS] tenant vê os 6 contratos AUR-*
[PASS] saldo AUR-HORAS-2026 == 34.0h  (glosa pendente NÃO reduz; 40 - 6h consumidas)
[PASS] ciclo fev fechado: consumed_minutes=120, status=closed, evento liquidado
[PASS] reajuste AUR-CREDITO-2026 respeita cap 8%  (200 → 216,00)
[PASS] fail-closed: sem GUC, Tenant e Contract retornam 0/0  (RLS)
E2E RESULT: ALL PASS
```

Tenant Aurora (prod): `5effe6fd-005e-43e4-9b1a-81107eb7f1a9`.

## Roteiro de apresentação — bloco "Contratos / Faturamento"

Encaixa após o passo 4 do roteiro do Service Desk (`DEMO.md` §4), quando se
fala de SLA + horas apontadas:

1. **Falar:** "Cada hora apontada no chamado alimenta o contrato do cliente.
   A Aurora tem 6 modalidades possíveis — banco de horas, crédito em R$,
   pool compartilhado entre filiais, pacote de serviços, valor fechado,
   assinatura." → mostrar a tabela acima (slide).
2. **Mostrar o motor vivo** (terminal, opcional/avançado): rodar o resumo
   idempotente — imprime os 6 contratos + saldos atuais:
   ```bash
   ssh gc 'cd ~/ground-control && set -a && . ./.env && . ./.env.prod && set +a
     docker run --rm --network ground-control_data \
       -e DATABASE_URL="postgresql+asyncpg://gerti_admin_user:$GERTI_ADMIN_DB_PASSWORD@postgres:5432/$POSTGRES_DB" \
       -v ~/ground-control/apps/sidecar/scripts:/app/scripts:ro \
       ground-control/sidecar:1c uv run python /app/scripts/seed_demo_contracts.py --summary'
   ```
3. **Falar a regra forte (diferencial vs Tiflux):** "Banco de horas: 40h,
   consumiu 6h → restam 34h. Pediu glosa de um atendimento? Enquanto não for
   **aprovada**, o valor continua devido — nada some do saldo por engano.
   Reajuste anual com **teto** contratual. E cada cliente só enxerga os
   próprios contratos — isolamento no banco (RLS), não na aplicação."
4. **Fechar:** "Mesmo motor de contratos do Tiflux, em base própria,
   multi-tenant, auditável (ledger append-only)."

## Operação

- **Re-semear / ver estado** (idempotente): `seed_demo_contracts.py`
  (default = semeia; `--summary` = só imprime; `--reset` = apaga só os dados
  Aurora — exige role table-owner/superusuário se houver ledger).
- **Re-rodar o E2E**: `e2e_prod_check.py` com `DATABASE_URL` de
  `gerti_sidecar` + `DEMO_TENANT_ID=5effe6fd-005e-43e4-9b1a-81107eb7f1a9`.
- Ambos rodam via `docker run` na rede `ground-control_data` (a imagem
  `ground-control/sidecar:1c`; **não** via `docker compose run` — o
  `environment:` do serviço fixa o role e venceria o `-e`).
- Gate local equivalente: `apps/sidecar/tests/test_demo_seed_e2e.py`
  (testcontainers) — roda no CI/`make check`.

## Os 4 ativos de apresentação (resumo)

| Ativo | URL/Como | Estado |
|---|---|---|
| Service Desk vivo (Znuny/Aurora) | `znuny-dev.was.dev.br/znuny/index.pl` · `william`/`Gerti@Demo2026` | ✅ pronto, clicável (`DEMO.md`) |
| Motor de contratos #1C | scripts acima (sem UI — Spec #1E futura) | ✅ deployado, dados+E2E verdes |
| 6 modalidades + regras (slides) | tabela/§ deste doc | ✅ conteúdo pronto |
| Deck interativo do plano | `plano-gerti.was.dev.br` | ✅ publicado |
