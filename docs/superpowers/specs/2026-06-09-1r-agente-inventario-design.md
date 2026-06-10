# Spec #1R — Agente de inventário com auto-registro seguro

**Data:** 2026-06-09
**Status:** aprovado no brainstorming → pronto para plano/execução
**Escopo:** um **agente** (binário Go) que, ao ser instalado numa máquina do cliente, **registra o equipamento automaticamente no inventário (CMDB) daquele cliente** e mantém um heartbeat; com modelo de segurança que **garante que o ativo só entra no cliente certo**.

## Decisões aprovadas (brainstorming)

| Tema | Decisão |
|------|---------|
| **Escopo do agente** | **Persistente com heartbeat**: registra na instalação + re-sincroniza specs periodicamente + marca online/offline. |
| **Identidade** | **Credencial por-agente** trocada no 1º boot (o token de enrollment NÃO é a credencial de longo prazo). Bearer token de alta entropia, guardado **hasheado** (sha256) no servidor; transporte HTTPS. (mTLS/TPM = endurecimento futuro.) |
| **Confiança** | **Híbrido: auto + travas** — token válido registra o ativo automaticamente, com dedupe por fingerprint de hardware, `max_registrations` por token, janela de tempo; anomalias → `pending` (não entra no CMDB até aprovação). |
| **Entrega do token** | **Script de instalação parametrizado** (`curl .../install.sh \| sh -s -- --enroll-token=XXX --server=...`), mostrado no console por tenant. |
| **Linguagem do agente** | **Go** (binário estático cross-platform, sem runtime na máquina do cliente). |
| **Aprovação de `pending`** | **Operador MSP no console** (pode ser exposto ao admin do portal no futuro). |

## Decomposição (dois subsistemas, specs/planos próprios)

- **#1R-a — Servidor**: tokens de enrollment por tenant + endpoints `enroll`/`heartbeat` no sidecar + op GI de **escrita** no CMDB (`ConfigItemUpsert`) + UI no console (instalar/listar/aprovar/revogar/rotacionar). **Testável sozinho** via curl (simula o agente). Plano: `2026-06-09-1r-a-agente-servidor.md`.
- **#1R-b — Agente Go**: o binário que coleta specs, faz enroll, guarda a credencial e bate heartbeat — contra o contrato já provado de #1R-a. Plano: `2026-06-09-1r-b-agente-go.md`.

**Ordem:** #1R-a primeiro (carrega o modelo de segurança), depois #1R-b.

## Arquitetura

### Modelo de segurança (o núcleo)
- **Cliente certo, garantido por construção**: `enroll_token → tenant → CustomerID` é **server-trusted**. O agente **nunca** declara para qual cliente vai; o token decide. Token do cliente A é **estruturalmente incapaz** de criar ativo em B (o sidecar resolve o `CustomerID` do tenant dono do token).
- **Token de enrollment**: alta entropia (`gcat_` + 32 bytes urlsafe), guardado **só como sha256** (nunca plaintext); `expires_at` + `max_registrations` + `enabled`; **rotacionável** (revoga o antigo, emite novo). Mostrado em claro **uma única vez** na criação.
- **Travas híbridas (anti-token-vazado)**: dedupe por **fingerprint de hardware** (re-enroll da mesma máquina = atualiza, não duplica); `registration_count >= max_registrations` ou token expirado → novo device entra como **`pending`** (não escreve no CMDB) até aprovação no console.
- **Credencial por-agente**: `agent_secret` (urlsafe 32) emitido **uma vez** no enroll, guardado **hasheado** (sha256) no servidor + arquivo `0600` no agente; heartbeats autenticam por `Authorization: Bearer <agent_secret>` (comparação constant-time do hash). **Revogável** (status `revoked` → 401).
- **Transporte**: HTTPS via Cloudflare Tunnel. Endurecimento futuro: HMAC do corpo, mTLS, TPM.

### Modelos (sidecar, RLS por tenant, migration `0019_agent_inventory`)
- **`agent_enroll_token`**: `id`, `tenant_id` FK, `token_hash` (sha256, UNIQUE), `label`, `expires_at NULL`, `max_registrations INT NULL` (NULL = ilimitado), `registration_count INT default 0`, `enabled bool default true`, `created_at`. FORCE RLS por `tenant_id`.
- **`device_agent`**: `id`, `tenant_id` FK, `fingerprint` (UNIQUE por tenant), `agent_secret_hash` (sha256), `status` (CHECK `pending|active|revoked`), `znuny_config_item_id INT NULL`, `hostname`, `os`, `specs JSONB`, `last_seen_at NULL`, `enrolled_at`, `created_at`, `updated_at`. `UNIQUE(tenant_id, fingerprint)`. FORCE RLS por `tenant_id`.

### Endpoints do agente (`routers/agent.py` — `/v1/agent/*` na allowlist do `TenantMiddleware`, como `/v1/hooks`)
- **`POST /v1/agent/enroll`** — `Authorization: Bearer <enroll_token>`, body `{fingerprint, hostname, os, specs:{cpu,memory,disk,serial,vendor,model,operating_system}}`.
  1. `sha256(token)` → busca `agent_enroll_token`; não achou/`!enabled`/expirado → **401**.
  2. resolve `tenant_id`.
  3. dedupe por `(tenant_id, fingerprint)`: existe → re-enroll (rotaciona `agent_secret`, atualiza specs, mantém `config_item_id`, mantém/ativa); novo → guardrails.
  4. guardrails: `max_registrations` atingido ou expirado → cria device `pending` (**202**, sem CMDB); senão `active` + `registration_count++`.
  5. se `active`: GI `ConfigItemUpsert(CustomerCompany=tenant.znuny_customer_id, ConfigItemID?=existente, class=Computer, Name=hostname, specs…, Fingerprint)` → guarda `znuny_config_item_id`.
  6. gera `agent_secret`, guarda hash, retorna `{agent_id, agent_secret, status, heartbeat_interval_seconds}`.
- **`POST /v1/agent/heartbeat`** — `Authorization: Bearer <agent_secret>`, body `{specs, uptime_seconds}`.
  1. `sha256(secret)` → busca `device_agent`; não achou/`revoked` → **401**.
  2. atualiza `last_seen_at`; se specs mudaram e há `config_item_id` → GI `ConfigItemUpsert(ConfigItemID=…)` (nova versão).
  3. retorna `{ok, status, heartbeat_interval_seconds}`.

### GI op nova `ConfigItemUpsert.pm` (caminho de **escrita** — não existe hoje)
- Params: `AccessToken` (admin), `CustomerCompany` (obrigatório), `ConfigItemClass` (default `Computer`), `Name`, `DeplState` (default `Production`), `InciState` (default `Operational`), `ConfigItemID` (opcional, p/ update), `Fingerprint` + atributos (`OperatingSystem/CPU/Memoria/Disco/SerialNumber/Vendor/Model`).
- **Update** (`ConfigItemID` presente): valida que o `CustomerID` atual do CI == `CustomerCompany` (**anti-IDOR**), senão `NotFound`; `VersionAdd` nova versão.
- **Create** (sem `ConfigItemID`): `ConfigItemAdd` + `VersionAdd` (resolve ClassID/DeplStateID/InciStateID por nome). Retorna `{ConfigItemID, VersionID, Number, Action: created|updated}`.
- Registrar em `GertiTicket.yml` (op + rota `/ConfigItem/Upsert`) + **COPY no Dockerfile + nome no loop `perl -c`** (lição #1O/#1Q). Estender `ensure-cmdb-fields.pl` para garantir o campo **`Fingerprint`** na classe Computer.

### Console (UI do operador MSP — onde o admin instala)
Página **"Agentes"** sob o cliente (`apps/admin/pages/clientes/[id]/agentes.vue`):
- **Instalar agente**: botão "Gerar token de instalação" (mostra o token **uma vez** + o comando `curl … | sh -s -- --enroll-token=… --server=…` com copy-to-clipboard); rotacionar/desabilitar token.
- **Dispositivos**: tabela (hostname, status active/pending/**offline** [last_seen > 2× intervalo], OS, último contato, specs resumidas); ações **aprovar** (pending→active, escreve no CMDB), **revogar**.
- Endpoints console: `POST/GET /v1/admin/tenants/{id}/agent-tokens`, `GET /v1/admin/tenants/{id}/devices`, `POST …/devices/{id}/approve`, `…/revoke` (auth `get_admin_session`, `AdminSessionLocal`+`tenant_session_scope`).

### Agente Go (#1R-b)
Binário estático cross-platform; instala como serviço (systemd / Windows service). Config `agent.conf` (`server`, e pós-enroll `agent_id`+`agent_secret`; o `enroll_token` chega só no install e é **descartado** após a troca). Coleta **fingerprint estável** (SMBIOS UUID/`/etc/machine-id`/serial) + OS/CPU/memória/disco/serial/vendor/model. Heartbeat configurável (default 1h). Retry com backoff em 503; em 401 (revogado) para e loga.

## Erros & validação
401 (token/agente inválido/revogado) · 202+`pending` (sobre limite/anomalia, sem CMDB) · 503 (GI fora → agente faz backoff) · idempotência por fingerprint (re-enroll/reinstalação não duplica). **Testes**: hash/verify constant-time do token e do secret; guardrails (limite/janela/dedupe); anti-IDOR (token do tenant A só escreve em `CustomerID` A; update de CI de outro tenant → NotFound); idempotência da GI (create→update). **e2e staging**: gerar token no console → `enroll` (curl) → device `active` → ativo aparece em `/v1/assets` **só** do tenant certo → `heartbeat` atualiza last_seen + specs → estourar `max_registrations` → device `pending` (não no CMDB) → aprovar no console → entra → **revogar** → heartbeat 401 → **rotacionar** token → token antigo 401.

## Arquitetura / invariantes (herdados)
Núcleo Znuny imutável (só overlay `Custom/` + webservice versionado). Multi-tenant: tabelas com `tenant_id` + FORCE RLS. Escopo de ativo por `CustomerID` server-trusted (anti-IDOR). GI failure-safe. Toda op GI nova → COPY no Dockerfile + `perl -c`. Segredos só em `.env.prod`. Docs voyager (`.ia/` no mesmo PR).

## Não-objetivos
Monitoramento/métricas/alertas (RMM completo), ações remotas, patch management, mTLS/TPM (endurecimento futuro), installer empacotado por cliente (.msi/.deb — usamos script parametrizado), descoberta de rede/scan de sub-rede, exposição da UI de instalação no portal do cliente (fica no console; futuro).
