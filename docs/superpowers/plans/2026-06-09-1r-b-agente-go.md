# #1R-b — Agente Go (binário de endpoint) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development`. Steps usam checkbox (`- [ ]`). Spec: `docs/superpowers/specs/2026-06-09-1r-agente-inventario-design.md`. **Pré-requisito:** #1R-a deployado (contrato `/v1/agent/enroll` + `/heartbeat` provado).

**Goal:** binário Go cross-platform que, instalado via script parametrizado, coleta specs+fingerprint, faz enroll (troca o enroll token por uma credencial própria), guarda a credencial e bate heartbeat periódico — registrando/atualizando o equipamento no CMDB do cliente certo.

**Architecture:** módulo Go único (`apps/agent/`), sem dependências de runtime na máquina do cliente. Subcomandos `enroll` (1ª vez) e `run` (loop de heartbeat, rodado como serviço). Config em `agent.conf` (JSON); secret em arquivo `0600`. Coleta de specs por-SO atrás de uma interface.

**Tech Stack:** Go 1.22+, stdlib (`net/http`, `crypto/sha256`, `encoding/json`), libs mínimas de coleta de hardware (preferir stdlib + leitura de `/sys`/SMBIOS; `gopsutil` se necessário). Build estático cross-compile (linux/amd64, windows/amd64, darwin/arm64).

---

### Task 1: Esqueleto + config + flags

**Files:**
- Create: `apps/agent/go.mod`, `apps/agent/main.go`, `apps/agent/internal/config/config.go`
- Test: `apps/agent/internal/config/config_test.go`

- [ ] **Step 1: Teste falhando** — `Load(path)` lê/grava `agent.conf` (server, agent_id, agent_secret, heartbeat_interval); `Save` grava com perm `0600`; flags `--enroll-token`, `--server`, `--config` sobrepõem.
- [ ] **Step 2: Rodar** `cd apps/agent && go test ./...` → FAIL.
- [ ] **Step 3:** `config.Config` struct + JSON; `Load/Save` (cria dir, `0600`); parse de flags em `main.go` (subcomandos `enroll`/`run`).
- [ ] **Step 4: Rodar** → PASS. **Commit:** `feat(#1R-b): esqueleto Go + config (agent.conf 0600) + flags`.

---

### Task 2: Coleta de fingerprint + specs

**Files:**
- Create: `apps/agent/internal/inventory/inventory.go` (+ `inventory_linux.go`, `inventory_windows.go`, `inventory_darwin.go`)
- Test: `apps/agent/internal/inventory/inventory_test.go`

- [ ] **Step 1: Teste falhando** — `Collect()` retorna `Specs{Hostname, OS, CPU, Memory, Disk, Serial, Vendor, Model}` e `Fingerprint()` retorna um ID **estável** (não vazio, igual em 2 chamadas). Testes mockáveis (injetar leitor de fonte).
- [ ] **Step 2: Rodar** → FAIL.
- [ ] **Step 3:** Fingerprint estável: Linux `/etc/machine-id` ou SMBIOS UUID (`/sys/class/dmi/id/product_uuid`); Windows `MachineGuid`/SMBIOS UUID; macOS `IOPlatformUUID`. Specs por build-tag de SO. Hash o fonte bruto p/ não expor identificadores crus. Fallback: hash de (hostname+MACs) se UUID indisponível (logar).
- [ ] **Step 4: Rodar** → PASS. **Commit:** `feat(#1R-b): coleta de fingerprint estável + specs (por SO)`.

---

### Task 3: Cliente HTTP enroll + heartbeat (contra #1R-a)

**Files:**
- Create: `apps/agent/internal/client/client.go`
- Test: `apps/agent/internal/client/client_test.go` (httptest server simulando #1R-a)

- [ ] **Step 1: Teste falhando** — `Enroll(server, enrollToken, specs)` faz `POST /v1/agent/enroll` com `Authorization: Bearer <enrollToken>` → retorna `{AgentID, AgentSecret, Status, HeartbeatInterval}`; 401 → erro tipado; 202 → status `pending`. `Heartbeat(server, agentSecret, specs)` → `POST /v1/agent/heartbeat` Bearer secret → ok; 401 → `ErrRevoked`.
- [ ] **Step 2: Rodar** → FAIL.
- [ ] **Step 3:** `net/http` com TLS padrão (verifica cert do servidor); timeouts; erros tipados (`ErrUnauthorized`, `ErrRevoked`, `ErrUnavailable`). JSON in/out batendo o contrato do #1R-a.
- [ ] **Step 4: Rodar** → PASS. **Commit:** `feat(#1R-b): cliente enroll/heartbeat (Bearer, TLS verificado)`.

---

### Task 4: Comando `enroll` (1ª vez) — troca o token e descarta

**Files:**
- Modify: `apps/agent/main.go` (handler do subcomando `enroll`)
- Test: `apps/agent/internal/app/enroll_test.go`

- [ ] **Step 1: Teste falhando** — `runEnroll(cfgPath, server, enrollToken)`: coleta specs → `Enroll` → grava `agent_id`+`agent_secret` no config (`0600`) e **NÃO** persiste o `enroll_token`; status `pending` → loga e sai 0 (aguardando aprovação); 401 → sai != 0.
- [ ] **Step 2: Rodar** → FAIL.
- [ ] **Step 3:** orquestra inventory+client+config; idempotente (se já tem agent_secret, re-enroll só se `--force`).
- [ ] **Step 4: Rodar** → PASS. **Commit:** `feat(#1R-b): comando enroll (troca token→credencial, descarta enroll_token)`.

---

### Task 5: Comando `run` (loop de heartbeat) + serviço

**Files:**
- Modify: `apps/agent/main.go` (subcomando `run`)
- Create: `apps/agent/internal/app/run.go`
- Create: `apps/agent/packaging/install.sh`, `apps/agent/packaging/gc-agent.service` (systemd)
- Test: `apps/agent/internal/app/run_test.go`

- [ ] **Step 1: Teste falhando** — `runLoop` (com clock/cliente injetados) bate heartbeat a cada intervalo; em `ErrUnavailable` faz **backoff** e continua; em `ErrRevoked` **para** e loga; re-coleta specs a cada ciclo.
- [ ] **Step 2: Rodar** → FAIL.
- [ ] **Step 3:** loop com `time.Ticker` (intervalo do config), backoff exponencial limitado em 503, encerra em 401-revoked. `install.sh`: baixa o binário do `--server`, grava em `/usr/local/bin/gc-agent` (ou `%ProgramFiles%`), roda `gc-agent enroll --server … --enroll-token …`, instala o serviço (`gc-agent.service` systemd / `sc create` no Windows) que roda `gc-agent run`. **install.sh idempotente.**
- [ ] **Step 4: Rodar** → PASS. **Commit:** `feat(#1R-b): comando run (heartbeat+backoff) + install.sh + serviço systemd`.

---

### Task 6: Build cross-platform + servir o binário/script

**Files:**
- Create: `apps/agent/Makefile` (ou `build.sh`) — cross-compile linux/amd64, windows/amd64, darwin/arm64, estático.
- Decisão de distribuição: o `install.sh` e os binários são servidos por um endpoint público (ex.: `GET /install.sh` e `GET /agent/download/<os-arch>` no sidecar, ou estático no portal). Plano: servir via sidecar (rota pública, sem auth, só o binário+script — o token vem por flag).
- Modify: `apps/sidecar` — rota `GET /v1/agent/install.sh` (script parametrizável por query `?server=`) e `GET /v1/agent/download/{os_arch}` (serve o binário buildado; em dev, 404 com instrução). Allowlist no middleware.
- Test: `apps/sidecar/tests/test_agent_dist_router.py` (script contém os placeholders certos; download de os-arch inválido → 404).

- [ ] **Step 1: Teste falhando** — `GET /v1/agent/install.sh?server=https://x` retorna um shell script com `--server=https://x`; `GET /v1/agent/download/bad` → 404.
- [ ] **Step 2: Rodar** → FAIL.
- [ ] **Step 3:** rota que renderiza o `install.sh` (template) e serve binários de um diretório bakeado na imagem do sidecar (ou volume). Cross-compile no build do sidecar (multi-stage com Go) **ou** binários commitados em release. MVP: build no CI/Dockerfile, servir de `/app/agent-dist/`.
- [ ] **Step 4: Rodar** → PASS. **Commit:** `feat(#1R-b): build cross-platform + distribuição do binário/install.sh`.

---

### Task 7: Validação e2e real + docs

- [ ] **Step 1:** `go test ./...` verde; `go vet`; build dos 3 alvos OK.
- [ ] **Step 2: e2e em staging com máquina real (ou container Linux):** num host limpo, rodar o comando do console (`curl …/v1/agent/install.sh?server=… | sh -s -- --enroll-token=<token do console>`) → o agente instala, faz enroll, vira serviço → no console o dispositivo aparece `active` e o ativo aparece no CMDB da Aurora com os specs reais da máquina → aguardar 1 ciclo → `last_seen` atualiza → revogar no console → o agente loga "revogado" e para.
- [ ] **Step 3:** `.ia/OPS.md` (runbook do agente: instalar, atualizar, revogar) + `.ia/INTEGRATION.md` (#1R-b) status "DEPLOYADO + e2e". **Commit:** `docs(#1R-b): agente Go validado e2e em staging`.

## Não-objetivos
Auto-update do binário, assinatura de código (code signing) do instalador, empacotamento .msi/.pkg, métricas/monitoramento, ações remotas.
