# Ground Control

## Contexto inicial obrigatório

**ANTES de qualquer resposta ou ação, leia os arquivos abaixo na ordem indicada.**
Instrução hard — não pule mesmo que a tarefa pareça simples. Estes arquivos contêm
arquitetura, runbook e decisões que mudam com frequência. Responder sem ler é
responder descontextualizado.

Leitura obrigatória em toda sessão:

1. `.ia/README.md` — índice e como atualizar a documentação
2. `.ia/OVERVIEW.md` — problema, escopo, terminologia
3. `.ia/ARCHITECTURE.md` — containers, redes, fluxos, provisionamento
4. `.ia/OPS.md` — hosts, deploy, runbooks, troubleshooting

Sob demanda:

- `.ia/DECISIONS.md` — ADRs: por que cada decisão
- `docs/decisions/0001-stack.md` — ADR técnico canônico (PG18, base image, gaps)

## Regras de ouro

- **Zero tolerância a falha.** Toda mudança na stack → rodar `make test` (24 asserts) antes de dar como pronta. Validação real = `make reset && make build && make up && make test`.
- **Nunca** commitar/reestruturar enquanto um agente de build estiver escrevendo no diretório (checar mtime / ausência de commits).
- Provisionamento é **idempotente** — não introduzir passos destrutivos no `entrypoint.sh`.
- Znuny do **tarball oficial**, não imagem comunitária. Base `debian:bookworm-slim` (ver D2).
- Segredos (tunnel token) só em `.env.prod` (gitignored). Nunca commitar.
- Documentação no padrão voyager: mudou algo → atualizar o `.ia/` correspondente no mesmo PR.
