# Ground Control — Decisões (ADRs)

Resumo das decisões não óbvias. ADR técnico canônico (gerado no build, inglês):
[`../docs/decisions/0001-stack.md`](../docs/decisions/0001-stack.md).

## D1 — Znuny do tarball oficial, não imagem comunitária
Zero tolerância a falha. Imagens comunitárias de Znuny são desatualizadas/opacas.
Build próprio do tarball oficial 7.2.3 = versão pinada, reprodutível, auditável.

## D2 — Base `debian:bookworm-slim`, NÃO `perl:5.40`
`libapache2-mod-perl2` linka contra o perl **do sistema** (5.36). Em base `perl:5.40`
há dois perls: mod_perl usa o do sistema; CLI/`cpanm`/`otrs.CheckModules.pl` usam o 5.40.
Verificado quebrando o build (`CheckModules.pl` reportava módulos apt-instalados como
ausentes — `@INC` mismatch). Um perl só elimina a classe inteira de bug.

## D3 — PostgreSQL 18: COMPATÍVEL, sem fallback
**Veredito: Znuny 7.2.3 instala e roda limpo no `postgres:18` (verificado 18.4).**
Schema load, `DBD::Pg`, console, daemon e web — tudo funciona. Sem fallback p/ PG17.
Único ajuste (de *imagem*, não incompatibilidade do Znuny): `postgres:18` espera o
volume em `/var/lib/postgresql` (subdir de major-version), não `/var/lib/postgresql/data`.

## D4 — Backend de cache Redis custom
Core Znuny 7.2 só tem `Cache::FileStorable` (Redis é add-on pago/feature). Decisão:
shipar `Kernel::System::Cache::Redis` fiel ao contrato (`Set/Get/Delete/CleanUp`),
em `Custom/` (upgrade-safe), `Storable` + `SETEX` + índice SET por `Type`.
Verificado: 150+ chaves `znuny:*` no Redis, FS bypassed.

## D5 — OpenSearch: alcance provado, indexação é add-on-gated
Core Znuny 7.2 **não** tem suporte ES/OpenSearch (é o add-on `Znuny-Elasticsearch`,
fora do repo público de releases). Decisão (mínimo acordado): OpenSearch healthy,
endpoint em `Config.pm` (`GertiOpenSearchEndpoint`), e **alcance Znuny→OpenSearch
provado** (`status: green`). **Gap conhecido:** indexação completa de documentos
exige o add-on (trabalho futuro).

## D6 — Provisionamento automatizado e idempotente
Sem instalador web, nunca. `entrypoint.sh` renderiza Config.pm de env, init de DB
só se schema ausente, admin/SystemID via Console.pl. `down && up` repetido não
duplica nem reinicializa destrutivamente.

## D7 — Redes segregadas
`edge` (cloudflared↔web), `app` (znuny↔serviços), `data` (`internal: true` —
postgres/redis/opensearch não roteáveis de fora).

## D8 — cloudflared token-mode via `.env.prod`
Token não commitado. Placeholder → cloudflared loga "token is not valid" e reinicia;
esperado e inócuo (nada depende dele). Token real ativa o tunnel.

## D9 — Monorepo de deploy + landing consolidada
Repo `ground-control` é o monorepo de deploy. Landing comercial consolidada em
`landing/` (era repo standalone `ground-control-landing`). Sidecar/portal entram
quando estabilizarem. Documentação no padrão **voyager** (`.ia/` + README conceito
mission-control).
