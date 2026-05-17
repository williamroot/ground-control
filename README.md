# Ground Control — Znuny dev stack

Production-grade, fully-coupled Docker Compose stack for **Znuny 7.2.3**
— the ticketing/ITSM core of the **Gerti Service Desk** platform
(replacing Tiflux). This repo is the **infra/orchestration layer only**;
the Python sidecar and Nuxt portal live elsewhere and are out of scope.

100% automated provisioning — **no web installer, ever**.

---

## Architecture

```
                       Internet
                          │
                 ┌────────▼────────┐   edge network
                 │   cloudflared   │   (znuny-dev.was.dev.br)
                 └────────┬────────┘
                          │
                 ┌────────▼────────┐
                 │   znuny-web     │  Apache2 + mod_perl2  (:8080→80)
                 │  (Znuny 7.2.3)  │
                 └────────┬────────┘
        app network       │           ┌──────────────┐
                 ┌────────┼───────────┤ znuny-daemon │ bin/otrs.Daemon.pl
                 │        │           └──────────────┘ (foreground/supervised)
   ┌─────────────▼──┐ ┌───▼────┐ ┌────▼─────────┐
   │  postgres:18   │ │redis:7 │ │ opensearch:2 │   data network
   │ schema: znuny  │ │ cache  │ │  single-node │   (internal: true)
   └────────────────┘ └────────┘ └──────────────┘
```

| Service        | Image                            | Role |
|----------------|----------------------------------|------|
| `postgres`     | `postgres:18`                    | DB (Znuny schema in `public`; `gerti` schema added later by sidecar) |
| `redis`        | `redis:7-alpine`                 | Znuny cache backend (custom `Cache::Redis`) |
| `opensearch`   | `opensearchproject/opensearch:2` | Search cluster (single-node, dev security off) |
| `znuny-web`    | built from official tarball      | Apache2 + mod_perl2, serves `/znuny/index.pl` |
| `znuny-daemon` | same image                       | `bin/otrs.Daemon.pl` supervised in foreground |
| `cloudflared`  | `cloudflare/cloudflared:latest`  | Tunnel for `znuny-dev.was.dev.br` (token pending) |

Networks: **edge** (cloudflared↔web), **app** (web/daemon↔services),
**data** (`internal: true` — DB/Redis/OpenSearch unreachable from
outside the project).

Named volumes: `postgres-data`, `znuny-var` (article storage /
`/opt/otrs/var`), `opensearch-data`.

---

## Quickstart

```bash
make init      # create .env and .env.prod from the committed examples
make build     # build the Znuny image (~1–2 min on a warm cache)
make up        # start the whole stack
make test      # full end-to-end smoke test (24 assertions)
```

Then open <http://localhost:8080/znuny/index.pl>.

Default seeded super-agent (set in `.env`):

- user: `root@localhost`
- password: `Admin-Change-Me-123`  ← change `ZNUNY_ADMIN_PASSWORD`

Useful targets: `make logs svc=znuny-web`, `make shell`, `make psql`,
`make redis-keys`, `make es-health`, `make reset` (destroys volumes).

---

## How the Cloudflare Tunnel token is supplied

The tunnel hostname is `znuny-dev.was.dev.br`. The connector token is
**not committed**. `make init` copies `.env.prod.example` →
`.env.prod` (gitignored). When you provision the tunnel in the
Cloudflare dashboard, paste the connector token:

```bash
# .env.prod
CLOUDFLARE_TUNNEL_TOKEN=<real-connector-token-from-cloudflare>
```

then `docker compose up -d cloudflared`.

**Until then** cloudflared logs `Provided Tunnel token is not valid.`
and restarts. **This is expected and harmless** — no other service
depends on cloudflared, so the rest of the stack is fully functional.

---

## PG18 verdict

**Znuny 7.2.3 is COMPATIBLE with PostgreSQL 18 (verified 18.4). No
fallback to PG17 was needed.** Schema load, `DBD::Pg`, console
commands, the daemon and the web UI all work on `postgres:18`.

The only PG18-specific change (an *image* change, not a Znuny
incompatibility): `postgres:18` expects the data volume at
`/var/lib/postgresql` (major-version subdir), not
`/var/lib/postgresql/data`. Handled in `docker-compose.yml`. Details:
[`docs/decisions/0001-stack.md`](docs/decisions/0001-stack.md).

---

## Provisioning (automated, idempotent)

`znuny/entrypoint.sh`:

1. Renders `Kernel/Config.pm` from `Config.pm.tmpl` using env
   (DB DSN, Redis, OpenSearch endpoint, `SystemID`, FQDN).
2. Waits for PostgreSQL to be ready.
3. **Idempotent DB init** — loads schema + initial data + post-schema
   **only if** the `valid` table is absent; otherwise logs
   `schema already present — skipping`.
4. Rebuilds SysConfig, ensures/creates the admin user, sets its
   password deterministically, verifies it in the `users` table.
5. Proves Znuny→OpenSearch reachability.
6. `web` role → exec Apache2 (foreground). `daemon` role → waits for
   web's provisioning marker, then runs `bin/otrs.Daemon.pl`
   supervised in the foreground (auto-restarts if it stops).

---

## Known gaps / notes

- **Redis cache:** core Znuny 7.2 ships only `FileStorable`. We add a
  faithful `Kernel::System::Cache::Redis` (in `Custom/`, upgrade-safe)
  implementing Znuny's exact backend contract. Verified: 150+
  `znuny:*` keys land in Redis; filesystem cache is bypassed.
- **OpenSearch:** core Znuny 7.2 has **no** ES/OpenSearch support —
  it is the separate `Znuny-Elasticsearch` add-on (not in the public
  release repo). We guarantee: OpenSearch healthy, Znuny configured
  with the endpoint, and **Znuny→OpenSearch connectivity proven**
  (`status: green`). Full document-search indexing requires the add-on
  (future work). See the decision note.
- **cloudflared:** pending real token (see above).

## Troubleshooting

| Symptom | Cause / fix |
|---|---|
| `postgres` unhealthy, logs about `/var/lib/postgresql/data (unused mount)` | PG18 volume path — must be `/var/lib/postgresql` (already fixed here) |
| `znuny-web` restart loop, Apache `Can't locate /opt/znuny/...` | Znuny defaults to `/opt/znuny`; we install to `/opt/otrs` and symlink `/opt/znuny→/opt/otrs` (already handled) |
| `Cache::Redis could not be loaded` | The custom backend is in `Custom/Kernel/System/Cache/Redis.pm`; rebuild the image |
| cloudflared `token is not valid` | Expected until you set a real `CLOUDFLARE_TUNNEL_TOKEN` in `.env.prod` |
| Want a clean slate | `make reset` (destroys all volumes incl. DB) |

## Layout

```
docker-compose.yml            stack (networks, healthchecks, depends_on)
docker-compose.override.yml   dev: exposes 5432/9200, loads .env.prod
znuny/Dockerfile              Znuny image from official 7.2.3 tarball
znuny/entrypoint.sh           automated, idempotent provisioning
znuny/Config.pm.tmpl          Kernel/Config.pm rendered from env
znuny/Cache/Redis.pm          custom Znuny Redis cache backend
scripts/smoke-test.sh         24-assertion end-to-end test
docs/decisions/0001-stack.md  stack choices + PG18 outcome
Makefile  .env.example  .env.prod.example
```
