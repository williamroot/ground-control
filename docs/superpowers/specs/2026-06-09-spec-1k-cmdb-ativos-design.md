# Spec #1K — CMDB/Ativos (Znuny ITSM Configuration Management) + exposição no portal

**Data:** 2026-06-09
**Status:** aprovado no brainstorming (Seção 1 + decisões) → pronto para plano/execução
**Escopo deste ciclo (#1K):** ativar o **Configuration Management (CMDB)** do Znuny — a equipe
MSP cadastra/gere **ativos/hosts** (Config Items) — e **expor no portal white-label** os ativos
de cada cliente (**read-only**, escopados por tenant), com atalho **"abrir chamado sobre este
ativo"** que pré-vincula o Config Item ao ticket (#1E).
**Fora deste ciclo:** ITSM Change/Incident-Problem/Service Level Management (specs futuras);
cliente criar/editar ativos pelo portal; import em massa pela UI do cliente.

## 1. Decisões (brainstorming 2026-06-09)

- **D-1K-1 (escopo):** CMDB no Znuny **+ exposição read-only no portal** do cliente, com
  "abrir chamado a partir do ativo".
- **D-1K-2 (módulos):** add-ons **OFICIAIS** do Znuny ITSM, na ordem de dependência:
  **GeneralCatalog → ITSMCore → ImportExport → ITSMConfigurationManagement**. Núcleo Znuny
  imutável — CMDB é pacote oficial instalado por `Admin::Package::Install` (não é modificação
  de core). Não usar add-ons comunitários.
- **D-1K-3 (instalação):** **bakear os `.opm` oficiais na imagem** (download no build, versão
  casada com 7.2.3) e **instalar idempotentemente** no provisionamento (`Admin::Package::Install`
  de caminho local) — reprodutível, sem dependência de rede em runtime. Precedente: o entrypoint
  já instala `Znuny-Elasticsearch` via repo.
- **D-1K-4 (classes):** as **5 classes padrão** do ITSMConfigurationManagement (Computer,
  Hardware, Network, Software, Location) — sem classes custom.
- **D-1K-5 (escopo por tenant / white-label):** estender cada classe CI com **um atributo
  `CustomerCompany`** (referência à empresa-cliente). O ativo "pertence" ao tenant cujo
  `znuny_customer_id` está nesse atributo. O portal/sidecar filtra por ele; **nunca** retorna
  ativo de outro tenant (guarda server-trusted, anti-IDOR, igual ao #1E).
- **D-1K-6 (portal read-only + abrir chamado):** o cliente **só visualiza** seus ativos (lista
  + detalhe). Um botão **"Abrir chamado sobre este ativo"** leva ao `/tickets/novo` pré-vinculado;
  na criação, o ticket Znuny é **linkado ao Config Item** (LinkObject nativo). Quem cadastra/edita
  ativos é a MSP no Znuny.
- **D-1K-7 (acesso):** ver ativos é permitido a **qualquer cliente logado** (é o inventário da
  empresa dele), escopo por `tenant.znuny_customer_id` — não é admin-only (diferente de contratos).

## 2. Incógnitas a congelar no SPIKE (bloqueante — R1K)

Antes de implementar, um spike contra o `znuny-web` vivo (padrão R1/#1F, R1G/#1G) confirma e
**congela**:
1. **Pacotes ITSM p/ 7.2:** nomes/versões/URLs exatos dos `.opm` (GeneralCatalog, ITSMCore,
   ImportExport, ITSMConfigurationManagement) compatíveis com 7.2.3, e a ordem/instalação via
   `Admin::Package::Install`. Confirmar que instalam limpo e criam as 5 classes + tabelas.
2. **Definição de classe CI:** como adicionar o atributo `CustomerCompany` a cada classe
   (definição YAML via `Admin::ITSMConfigItem...`/SysConfig, ou a UI Admin → "Config Item
   Classes"); congelar o snippet de definição.
3. **API nativa ConfigItem:** os métodos de `Kernel::System::ITSMConfigItem` para
   **buscar por atributo** (CustomerCompany), **obter** um CI (com versão/atributos) e **listar
   classes**; e o `Kernel::System::LinkObject` para **linkar** Ticket↔ConfigItem. Congelar as
   assinaturas que as ops GI vão embrulhar.

O spike CONGELA: os pacotes/versões, o snippet de definição de classe, e as assinaturas GI.

## 3. Arquitetura

```
Znuny ITSM (CMDB, pacotes oficiais)              sidecar /v1/*                 portal (cliente, gsid)
 Config Items (5 classes padrão)        ◄──GI──  /v1/assets (lista p/ CustomerID)   /ativos (lista)
 + atributo CustomerCompany (tenant)             /v1/assets/{id} (detalhe)          /ativos/[id] (detalhe)
 LinkObject Ticket↔ConfigItem           ◄──GI──  POST /v1/tickets (+config_item_id) └─ "Abrir chamado" → /tickets/novo
```

### 3.1 Znuny (`znuny/`)
- **Dockerfile:** baixar os 4 `.opm` (versões do spike) no build → `${OTRS_HOME}/var/packages/`.
- **entrypoint.sh:** instalar idempotentemente na ordem de dependência
  (`Admin::Package::List | grep -qi <pkg> || Admin::Package::Install <path.opm>`), depois
  aplicar a definição de classe com o atributo `CustomerCompany` (idempotente).
- **GI (novo webservice `GertiCMDB` OU ops no `GertiTicket`):** `ConfigItemSearch`
  (filtra por `CustomerCompany`), `ConfigItemGet` (atributos + classe), e link Ticket↔CI
  (estende `GertiTicket::TicketCreate` com `ConfigItemID` opcional → `LinkObject` após criar).
  Token: reusar o padrão `AccessToken` (definir se token customer/cliente ou agente — o portal
  só LÊ ativos do próprio tenant, então usa o token de cliente já existente).

### 3.2 Sidecar (`apps/sidecar`)
- `integrations/znuny_cmdb.py` (ou +funções no cliente GI): `config_item_search(customer_id)`,
  `config_item_get(id, customer_id)` (guarda de posse por CustomerCompany).
- `routers/assets.py`: `GET /v1/assets` (sessão cliente; filtra pelo `tenant.znuny_customer_id`),
  `GET /v1/assets/{id}` (guarda anti-IDOR: 404 se o CI não for do tenant).
- `routers/tickets.py` (#1E): `POST /v1/tickets` ganha `config_item_id` opcional → repassa ao
  GI p/ linkar o CI ao ticket criado.

### 3.3 Portal (`apps/portal`)
- `pages/ativos/index.vue` (lista: nome, classe, status, nº de série/IP) + `pages/ativos/[id].vue`
  (detalhe + botão **"Abrir chamado sobre este ativo"** → `/tickets/novo?ativo=<id>`).
- `/tickets/novo` (#1E) lê `?ativo=` e inclui `config_item_id` no submit.
- Server proxies `server/api/portal/assets/*`. Nav ganha "Ativos". Read-only.

## 4. Segurança / invariantes
- Ativos escopados por **tenant** via `CustomerCompany` = `tenant.znuny_customer_id` (server-trusted
  da sessão, nunca input do cliente). `GET /v1/assets/{id}` retorna 404 se o CI não pertence ao
  tenant (anti-IDOR, igual ao #1E). Leitura via **GI** (Spec #0) — sem SQL direto no schema znuny.
- Portal é read-only sobre o CMDB; escrita (cadastro/edição) só pela MSP no Znuny.
- Núcleo Znuny imutável; CMDB são pacotes oficiais; provisionamento idempotente (re-install não
  duplica, re-definição de classe não quebra).

## 5. Testes
- **Spike:** prova viva da instalação dos pacotes + classes + atributo + API ConfigItem/Link.
- **Znuny:** instalação idempotente (re-run não falha; `Admin::Package::List` lista os 4);
  classe com `CustomerCompany` presente; `perl -c` das ops GI no build.
- **Sidecar (pytest):** assets list filtra por CustomerID; `{id}` anti-IDOR (CI de outro tenant →
  404); GI mockado (sucesso/`ZnunyUnavailable`→503); ticket-create com `config_item_id` chama o
  link; grep-guard (sem SQL direto no schema znuny).
- **Portal (vitest):** render lista/detalhe; botão "abrir chamado" leva o `?ativo=`.
- **Stack base (`make test`) e suíte sidecar atual continuam verdes.**

## 6. Deploy (profile `gerti` + rebuild Znuny, padrão D13)
Rebuild `znuny-web` (bakeia os 4 `.opm`; instala+define classe no provisionamento; perl -c das
ops GI) + recria; import/Update do webservice GI; rebuild `sidecar` + `portal`. e2e (local e
staging): MSP cadastra um ativo p/ Aurora no Znuny → cliente vê em `/ativos` → "abrir chamado"
→ ticket criado **linkado ao CI** (conferir o link no Znuny). Runbook em `OPS.md` +
`ARCHITECTURE`/`INTEGRATION` no mesmo PR. Rollback: `$DC stop portal sidecar`; pacotes ITSM
desinstalam por `Admin::Package::Uninstall` se necessário (ordem inversa). **NUNCA** `make reset`.

## 7. Faseamento (gate verde cada)
0. **SPIKE R1K** — congela pacotes/versões + definição de classe + API GI ConfigItem/Link.
1. **Znuny** — bake `.opm` + install idempotente + atributo `CustomerCompany` + ops GI
   (ConfigItemSearch/Get + link no TicketCreate).
2. **Sidecar** — cliente GI + `/v1/assets*` + `config_item_id` no `/v1/tickets`.
3. **Portal** — `/ativos` (lista+detalhe) + "abrir chamado a partir do ativo" + nav.
4. **Deploy + docs + e2e** (local e staging).

## 8. Não-objetivos (explícitos)
ITSM Change/Incident-Problem/SLM; escrita de ativo pelo cliente; import em massa pela UI do
cliente; classes/atributos custom além do `CustomerCompany`.
