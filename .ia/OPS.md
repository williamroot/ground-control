# Ground Control — OPS / Runbook

## Hosts

| Host | Uso | Acesso |
|---|---|---|
| `100.99.49.110` | **VPS de produção do ground-control** (Znuny) | `ssh ubuntu@100.99.49.110` (chaves configuradas, git ok) |
| local | dev | docker compose |

> Não confundir com a VPS `gerti` (host `gerti`), que serve a apresentação `plano-gerti.was.dev.br`. São máquinas distintas.

## Domínios / Cloudflare Tunnel

| Domínio | Tunnel | Serviço | Estado |
|---|---|---|---|
| `znuny-dev.was.dev.br` | (token-mode, em `.env.prod`) | znuny-web:80 | aguardando token do connector |
| `groundcontrol.was.dev.br` | `ground-control` (id `4f515441-d21e-4992-9389-f59b4c35e0d2`) | landing web:80 | ingress configurado via API; falta DNS CNAME |

DNS pendente (token Cloudflare atual sem `Zone:DNS:Edit`): criar CNAME **proxied**
`groundcontrol` → `4f515441-d21e-4992-9389-f59b4c35e0d2.cfargotunnel.com`.

## Deploy (resumo — completo em `../DEPLOY.md`)

```bash
ssh ubuntu@100.99.49.110
git clone git@github.com:williamroot/ground-control.git   # 1ª vez
cd ground-control && git pull
make init
# editar .env.prod com CLOUDFLARE_TUNNEL_TOKEN real
make build && make up
make test          # validar 24/24 antes de considerar no ar
```

Atualização de conteúdo já implantado: `git pull` + `docker compose up -d --build` (ou só `up -d` se nada de imagem mudou).

## Runbooks

### Stack não sobe / container unhealthy
1. `docker compose ps` — qual serviço
2. `make logs svc=<serviço>`
3. Postgres unhealthy + log `/var/lib/postgresql/data (unused mount)` → volume PG18 deve ser `/var/lib/postgresql` (já corrigido no compose; se editaram, reverter)
4. znuny-web loop + `Can't locate /opt/znuny/...` → simlink `/opt/znuny→/opt/otrs` ausente; rebuild da imagem

### cloudflared `token is not valid`
Esperado até `.env.prod` ter token real. Não afeta o resto da stack (nada depende do cloudflared). Após colar token: `docker compose up -d cloudflared`.

### Cache não vai pro Redis
`make redis-keys` deve listar `znuny:*`. Se vazio: `Cache::Redis` não carregou → conferir `Custom/Kernel/System/Cache/Redis.pm` na imagem e `Cache::Module` no Config.pm; rebuild.

### Reset total (destrói dados)
`make reset` — apaga todos os volumes (DB incluso). Só em dev / recriação consciente.

### Smoke-test
`make test` — 24 asserts e2e a partir do estado atual. Para validação real pós-deploy, rodar do zero: `make reset && make build && make up && make test`.

## Backup (a definir em prod)

- Postgres: `pg_dump` agendado → storage externo (não implementado nesta fase)
- `znuny-var` (anexos): snapshot de volume
- Ação futura: pgBackRest + retenção, documentar aqui quando implementado.

## Observabilidade (a definir)

Logs via `docker compose logs` por enquanto. Stack de observabilidade (OTEL/Grafana) é fase posterior — documentar aqui quando entrar.
