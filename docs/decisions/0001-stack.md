# 0001 — Ground Control Znuny stack: technology choices & PG18 outcome

- **Status:** Accepted
- **Date:** 2026-05-16
- **Context:** Infra/orchestration layer for the Gerti Service Desk
  (Znuny-based, replacing Tiflux). Sidecar/portal are out of scope here.

## Decisions

### Znuny 7.2.3 (built from official tarball)
Latest 7.2 patch on <https://download.znuny.org/releases/> at build
time. Image built **from the official tarball** (no community images),
base `debian:bookworm-slim`.

**Why `debian:bookworm-slim` and NOT `perl:5.40-bookworm`:**
Apache's `libapache2-mod-perl2` is linked against Debian's *system*
perl (`/usr/bin/perl`, 5.36). On a `perl:5.40` base there are **two
perls**: mod_perl uses the system one, while CLI / `cpanm` /
`otrs.CheckModules.pl` default to `/usr/local/bin/perl` (5.40). This
was verified to break the build: `otrs.CheckModules.pl` reported
required modules "Not installed" even though they were apt-installed,
because they live in the *system* perl's `@INC`, not 5.40's. Using one
perl (Debian's) for mod_perl, the daemon and every console call
eliminates the entire class of `@INC` mismatch bugs.

Perl deps: Debian `lib*-perl` packages for everything packaged; the
remainder (`Sisimai`, `Search::Elasticsearch`, `Redis`, `Net::Server`,
`Linux::Inotify2`) via `cpanm` into the same system perl.
`bin/otrs.CheckModules.pl` runs as a **hard build gate** — any
*required* module still missing fails `docker build`. Result: all
required present (only optional MySQL/Oracle DBDs absent — by design,
we use PostgreSQL).

### PostgreSQL 18 — COMPATIBLE (no fallback)
**Verdict: Znuny 7.2.3 installs and runs cleanly on `postgres:18`
(verified PostgreSQL 18.4).** Schema load
(`scripts/database/schema.postgresql.sql` +
`initial_insert.postgresql.sql` + `schema-post.postgresql.sql`),
`DBD::Pg` runtime, console commands, the daemon, and the web UI all
work. **No fallback to PG17 was necessary.**

One PG18-specific operational change was required (NOT an
incompatibility with Znuny): the `postgres:18` Docker image stores its
cluster under a major-version subdirectory and expects the data volume
mounted at `/var/lib/postgresql` (not `/var/lib/postgresql/data`).
Mounting at the old path makes the image refuse to start. Fixed in
`docker-compose.yml`.

### Redis 7 as Znuny cache backend
**Finding:** Znuny 7.2 *core* ships only
`Kernel::System::Cache::FileStorable`. There is **no Redis cache
backend in core** (it is part of paid/feature add-ons).
**Decision:** ship a small, faithful `Kernel::System::Cache::Redis`
implementing Znuny's exact cache backend contract
(`Set`/`Get`/`Delete`/`CleanUp`), placed in `Custom/` (first in
Znuny's `@INC`, upgrade-safe). It uses `Kernel::System::Storable`
serialization (identical to FileStorable), native Redis `SETEX` TTLs,
and a per-`Type` Redis SET index for precise `CleanUp`.
**Verified:** with `Cache::Module = Kernel::System::Cache::Redis`,
Znuny writes 150+ `znuny:*` keys to Redis (SysConfig, Loader, etc.) —
the filesystem cache is genuinely bypassed.

### OpenSearch 2.x — reachability proven; deep wiring is add-on-gated
**Finding:** Znuny 7.2 *core* has **no Elasticsearch/OpenSearch
support** — no `Maint::DocumentSearch::*`, no ES client wiring. The
full document-search feature is the separate installable
`Znuny-Elasticsearch` add-on package, which is **not** in the public
`download.znuny.org` release repo (it is distributed via Znuny's
add-on channel / requires the add-on repo, unreachable in this build
environment).
**Decision (per task's documented minimum):** run OpenSearch single-
node (security plugin disabled for dev), and at provision time
**prove the Znuny container can reach the OpenSearch cluster** and
gets `status: green`. The entrypoint also best-effort attempts
`Admin::Package::Install Znuny-Elasticsearch` (no-op when offline) and
records the endpoint in `Config.pm` (`GertiOpenSearchEndpoint`) so the
sidecar/add-on can consume it later. **Known gap:** end-to-end Znuny
document indexing into OpenSearch is NOT exercised because core 7.2
cannot do it without the add-on; this is expected and documented.

### cloudflared — token pending
Token-mode tunnel for `znuny-dev.was.dev.br`. Token read from
`CLOUDFLARE_TUNNEL_TOKEN` via gitignored `.env.prod`. With the
placeholder it logs **"Provided Tunnel token is not valid."** and
restarts — expected; no other service depends on it, so the stack is
unaffected. Drop the real connector token into `.env.prod` to activate.

### Networking
Three networks: `edge` (cloudflared ↔ znuny-web), `app` (znuny ↔
backing services), `data` (**internal: true** — postgres/redis/
opensearch not routable from outside the compose project).

## Consequences
- Stack is reproducible from scratch; provisioning is idempotent.
- Redis cache + OpenSearch reachability are real and tested.
- Full Znuny↔OpenSearch document search needs the `Znuny-Elasticsearch`
  add-on (future work, when the add-on repo is available).
