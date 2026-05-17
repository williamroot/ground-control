# Deploy — Ground Control

## Hosts

| Alvo | Host | Acesso |
|---|---|---|
| Produção (stack Znuny) | `100.99.49.110` | `ssh ubuntu@100.99.49.110` (chaves ok, git ok) |
| Landing comercial | mesmo host ou VPS de landing | nginx + cloudflared (`landing/`) |

## 1. Stack Znuny (znuny-dev.was.dev.br)

### Primeiro deploy

```bash
ssh ubuntu@100.99.49.110
git clone git@github.com:williamroot/ground-control.git
cd ground-control
make init
nano .env.prod          # colar CLOUDFLARE_TUNNEL_TOKEN real (tunnel znuny-dev)
make build
make up
make test               # exigir FAIL=0 antes de considerar no ar
docker compose logs -f cloudflared   # esperar "Registered tunnel connection"
```

### Cloudflare (uma vez, no dashboard Zero Trust)
- Tunnel `znuny-dev` → Public Hostname: `znuny-dev.was.dev.br` → Type `HTTP` → `znuny-web:80`
- Copiar o connector token para `.env.prod`
- DNS CNAME `znuny-dev` → `<tunnel-id>.cfargotunnel.com` **proxied** (se o token de API não tiver `Zone:DNS:Edit`, criar manual no dashboard)

### Atualizar conteúdo já implantado

```bash
ssh ubuntu@100.99.49.110
cd ground-control && git pull
docker compose up -d --build      # se mudou imagem/compose
# (ou só `up -d` se nada de imagem mudou)
make test                          # revalidar
```

## 2. Landing (groundcontrol.was.dev.br)

```bash
cd ground-control/landing
cp .env.prod.example .env.prod
nano .env.prod          # token do tunnel "ground-control" (id 4f515441-...)
docker compose -f docker-compose-prod.yml --env-file .env.prod up -d
```

- Ingress do tunnel `ground-control` já configurado via API (`groundcontrol.was.dev.br` → `http://web:80`).
- **Pendente:** DNS CNAME `groundcontrol` → `4f515441-d21e-4992-9389-f59b4c35e0d2.cfargotunnel.com` **proxied** (bloqueado: token Cloudflare sem `Zone:DNS:Edit` — criar manual ou fornecer token com escopo).

## Rollback

- Stack: `git checkout <sha-anterior> && docker compose up -d --build`
- Volumes preservam dados; `make reset` só em recriação consciente (destrói DB).

## Checklist pós-deploy (zero tolerância)

- [ ] `docker compose ps`: postgres/redis/opensearch/znuny-web/znuny-daemon `healthy`
- [ ] `make test` → `FAIL=0`
- [ ] `curl -fsS https://znuny-dev.was.dev.br/znuny/index.pl` → 200 + form de login
- [ ] cloudflared logando `Registered tunnel connection`
- [ ] (landing) `https://groundcontrol.was.dev.br` responde após DNS
