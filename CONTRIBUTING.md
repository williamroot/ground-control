# Contribuindo

## Setup local

```bash
git clone git@github.com:williamroot/ground-control.git
cd ground-control
make init      # .env e .env.prod a partir dos exemplos
make build
make up
make test      # 24 asserts — deve dar FAIL=0
```

Abra <http://localhost:8080/znuny/index.pl>.

## Estilo

- Shell/YAML/Perl: simples, comentado onde não é óbvio, sem zelo dogmático.
- Compose: healthcheck real em todo serviço, `depends_on: condition: service_healthy`, redes segregadas, volumes nomeados.
- `entrypoint.sh`: idempotente sempre. Toda etapa nova precisa ser segura em `down && up` repetido.
- Imagem: módulo Perl novo → adicionar como dep e garantir que `otrs.CheckModules.pl` continua passando (gate de build).

## Mudou a stack?

Rodar **validação real** antes de abrir PR:

```bash
make reset && make build && make up && make test
```

`make test` deve terminar com `FAIL=0`. Sem isso, não está pronto (zero tolerância a falha).

## Documentação

Mudança que toca arquitetura/host/decisão → atualizar o `.ia/` correspondente **no mesmo commit**:

- container/rede/fluxo → `.ia/ARCHITECTURE.md`
- host/deploy/runbook → `.ia/OPS.md`
- decisão não óbvia → `.ia/DECISIONS.md` (+ ADR numerado em `docs/decisions/` se estrutural)
- escopo/terminologia → `.ia/OVERVIEW.md`

## Segredos

Token do Cloudflare Tunnel e similares só em `.env.prod` (gitignored). Nunca em commit, log ou exemplo. `.env*.example` carregam apenas placeholders.

## Commits

Conventional commits (`feat:`, `fix:`, `chore:`, `docs:`, `test:`). Mensagem explica o **porquê**, não só o quê.
