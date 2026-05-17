# Ground Control — OPS / Runbook

## Hosts

| Host | Uso | Acesso |
|---|---|---|
| `100.99.49.110` / LAN `192.168.1.40` | **VPS de produção do ground-control** (Znuny + sidecar #1C) | **`ssh gc`** (jump via node `postgres`→LAN) — ver nota abaixo |
| `100.96.54.61` | node `postgres` (mesma LAN; jump host saudável) | `ssh ubuntu@100.96.54.61` (key) |
| local | dev | docker compose |

> Não confundir com a VPS `gerti` (host `gerti`), que serve a apresentação `plano-gerti.was.dev.br`. São máquinas distintas.

> **Acesso SSH ao ground-control — path Tailscale direto é assimétrico (CGNAT do uplink):** `tailscale status` mostra `direct 189.1.162.120:41641, tx≫rx`; `tailscale ping` responde mas SSH/TCP direto p/ `100.99.49.110` dá *"timed out (banner exchange)"*, intermitente. **Não é MTU** (mesmo assim `tailscale0` foi p/ 1240 via drop-in `tailscaled.service.d/mtu.conf` — higiene, persistente) **nem firewall do host** (ufw off, DERP sao 9.7ms). Causa: retorno UDP do WireGuard descartado pelo NAT/roteador do uplink — **fix permanente é no roteador/ISP** (port-forward 41641 / UPnP / tirar do CGNAT). **Acesso confiável:** alias `~/.ssh/config` `Host gc` → `ProxyJump ubuntu@100.96.54.61` → `192.168.1.40` (key-based; node `postgres` tem path Tailscale simétrico). Tráfego público (Cloudflare Tunnel) não usa Tailscale e nunca foi afetado.

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

### Seed de demonstração (apresentação)
`scripts/seed-demo.sh` — semeia, **de forma idempotente**, a operação MSP
fictícia "Aurora Móveis" (5 agentes, 5 customer users, 5 filas, 11 serviços,
3 SLAs, 17 tickets com artigos e horas). Roda na VPS dentro de `~/ground-control`
com a stack de pé. Detalhes, credenciais e roteiro em [`DEMO.md`](DEMO.md).
- `./scripts/seed-demo.sh` — semeia / re-semeia (seguro reexecutar)
- `./scripts/seed-demo.sh --verify` — só verificação e2e
- `./scripts/seed-demo.sh --reset` — apaga só os dados de demo (pede `SIM`)
O motor é `scripts/seed-demo.pl` (API nativa Znuny, executado como `otrs`
dentro de `znuny-web`); `scripts/seed-authcheck.pl` valida credenciais.

### Deploy do sidecar de contratos (Spec #1C — profile `gerti`)

Plano canônico: [`../docs/superpowers/plans/2026-05-17-spec-1c-deploy.md`](../docs/superpowers/plans/2026-05-17-spec-1c-deploy.md).
**Aditivo e gated por profile**: nenhum serviço `gerti` sobe sem
`--profile gerti`; um `make up` da stack Znuny fica intocado (Postgres
não reinicia, nada do Znuny é reconstruído). Single-cluster: schema
`gerti` no MESMO `postgres:18` do Znuny (Spec #0). Verificado local:
`docker compose config --services` SEM profile lista só os 6 serviços
Znuny (o footgun `${VAR:?}` que quebraria isso foi eliminado — segredos
têm default vazio no `environment:` e são exigidos em runtime no shell
do container, não no parse do compose).

**Pré-requisito (humano, one-time):** em `~/ground-control/.env.prod`
na VPS (gitignored — NUNCA commitar), adicionar as duas linhas
`GERTI_SIDECAR_DB_PASSWORD=…` e `GERTI_ADMIN_DB_PASSWORD=…` (valores
fortes; ver `.env.prod.example`). O agente gera os segredos e os
entrega out-of-band (Human-needed #2 do plano).

```bash
ssh ubuntu@100.99.49.110
cd ground-control && git pull                       # traz compose + gerti-init + sidecar
# 1) garantir GERTI_SIDECAR_DB_PASSWORD / GERTI_ADMIN_DB_PASSWORD em .env.prod
DC="docker compose --env-file .env --env-file .env.prod --profile gerti"

# 2) D1 — schema gerti + roles + RLS no cluster VIVO (idempotente)
$DC run --rm gerti-db-init       # verá o SELECT listando gerti_* roles + schemas

# 3) D2 — build + migrate (Alembic como gerti_admin_user) + app
$DC build sidecar
$DC up -d sidecar                # sidecar-migrate roda e sai 0; sidecar sobe healthy
$DC ps                           # sidecar healthy; sidecar-migrate Exit 0

# 4) prova de schema + RLS real em prod (zero-tolerância)
docker compose exec -T postgres psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" \
  -c "select count(*) from gerti.contract;"      # 0 linhas, tabela existe
docker compose exec -T postgres psql -U gerti_sidecar -d "$POSTGRES_DB" \
  -c "select * from gerti.tenant;"               # 0 linhas (GUC ausente → fail-closed)
docker compose exec -T postgres psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c \
  "select relname,relrowsecurity,relforcerowsecurity from pg_class c \
   join pg_namespace n on n.oid=relnamespace where nspname='gerti' and relkind='r';"
#  → relrowsecurity AND relforcerowsecurity = t p/ TODA tabela gerti.*

# 5) Znuny/landing intactos
curl -fsS https://znuny-dev.was.dev.br/znuny/index.pl | grep -qi login && echo ZNUNY_OK
curl -fsS https://groundcontrol.was.dev.br >/dev/null && echo LANDING_OK
```

**D3 — expor `api-dev.was.dev.br`** (ingress no MESMO tunnel `znuny-dev`,
token-mode multi-hostname): usar o script **read-modify-write** do plano
de deploy §D3 (GET config → splice da regra `api-dev` ANTES do catch-all
`http_status:404` → guard aborta se `znuny-dev` sumir → PUT do objeto
inteiro → re-GET assert ambos hostnames). DNS `CNAME api-dev →
<tunnel_id>.cfargotunnel.com` proxied. **Nunca** PUT de config
hand-written (substitui o array inteiro e derruba `znuny-dev` + demo
Aurora). Verificar: `curl -fsS https://api-dev.was.dev.br/v1/health`.

**Rollback (sidecar só, Znuny intocado):**
`$DC stop sidecar` → `git checkout <sha-anterior> -- apps/sidecar docker-compose.yml`
→ `$DC up -d sidecar`. Migration ruim: `$DC run --rm sidecar-migrate uv run alembic downgrade -1`.
**NUNCA** `make reset` (destrói o DB Znuny compartilhado).

> **Status (2026-05-17):** artefatos de deploy prontos, commitados e
> no `origin/main` (compose profile `gerti`, `postgres/gerti-init/`,
> `.env.prod.example`). A execução na VPS ficou **pendente: SSH p/
> `100.99.49.110` inacessível** (porta 22 timeout / ICMP 100% loss,
> embora o node apareça no tailnet) no momento do deploy autônomo —
> bloqueio externo do lado da VPS. Assim que o SSH voltar, o deploy é
> um `git pull` + os passos 1–5 + D3 acima (nenhuma mudança de código
> pendente).

## Backup (a definir em prod)

- Postgres: `pg_dump` agendado → storage externo (não implementado nesta fase)
- `znuny-var` (anexos): snapshot de volume
- Ação futura: pgBackRest + retenção, documentar aqui quando implementado.

## Observabilidade (a definir)

Logs via `docker compose logs` por enquanto. Stack de observabilidade (OTEL/Grafana) é fase posterior — documentar aqui quando entrar.
