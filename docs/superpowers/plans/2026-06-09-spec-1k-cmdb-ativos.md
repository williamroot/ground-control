# Spec #1K — CMDB/Ativos Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans. Steps use checkbox (`- [ ]`) syntax. **Fase 0 (SPIKE) é bloqueante e congela os detalhes do Znuny ITSM que as Fases 1+ consomem** — não pular.

**Goal:** Ativar o Configuration Management (CMDB) do Znuny (ativos/hosts via Config Items) e expor, read-only e escopado por tenant, os ativos de cada cliente no portal white-label, com "abrir chamado a partir do ativo" (linkando o CI ao ticket #1E).

**Architecture:** Add-ons oficiais Znuny ITSM (GeneralCatalog→ITSMCore→ImportExport→ITSMConfigurationManagement) bakeados na imagem (.opm) e instalados idempotentemente no provisionamento; as 5 classes padrão ganham um atributo `CustomerCompany` (escopo por tenant). Ops GI custom (padrão GertiTicket/AccessToken) embrulham a API nativa `ITSMConfigItem` (search/get) e `LinkObject` (CI↔ticket). Sidecar expõe `/v1/assets*` (sessão cliente, filtro por `tenant.znuny_customer_id`, anti-IDOR) e estende `/v1/tickets` com `config_item_id`. Portal ganha `/ativos` (lista+detalhe) + atalho de abrir chamado.

**Tech Stack:** Znuny 7.2.3 ITSM (Perl/GI, `Kernel::System::ITSMConfigItem`, `LinkObject`), FastAPI+SQLAlchemy async (sidecar), Nuxt 3 + Nuxt UI (portal), pytest/testcontainers + vitest. Spec: `docs/superpowers/specs/2026-06-09-spec-1k-cmdb-ativos-design.md`.

**Gate:** sidecar `ruff`+`ruff format --check`+`mypy`+`DATABASE_URL=… pytest -q`; Znuny `perl -c` no build + smoke vivo; `make test` (24) intacto; portal `npx nuxi typecheck`+`npx vitest run`. Commits `feat(#1K …)` com trailer `Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>`.

---

## FASE 0 — SPIKE R1K (bloqueante): congelar Znuny ITSM

Roda contra o `znuny-web` **vivo** (local), descobre os fatos e **escreve um doc de congelamento** que as Fases 1+ citam. Sem fabricar URLs/API.

### Task 0: Spike de ativação ITSM + descoberta da API

**Files:**
- Create: `docs/superpowers/spikes/2026-06-09-r1k-znuny-itsm-cmdb.md` (findings congelados)

- [ ] **Step 1: Instalar os pacotes ITSM no znuny-web vivo (via repo online) e capturar versões**

Run (stack local de pé):
```bash
DC="docker compose --env-file .env --env-file .env.prod --profile gerti"
docker compose exec -T znuny-web su otrs -s /bin/bash -c 'cd /opt/otrs && \
  for p in GeneralCatalog ITSMCore ImportExport ITSMConfigurationManagement; do \
    bin/otrs.Console.pl Admin::Package::List | grep -qi "$p" || \
    bin/otrs.Console.pl Admin::Package::Install "$p"; done'
docker compose exec -T znuny-web su otrs -s /bin/bash -c 'cd /opt/otrs && bin/otrs.Console.pl Admin::Package::List'
```
Capturar no doc: o **nome exato** de cada pacote, a **versão** instalada, e a **URL `.opm`**
correspondente em `download.znuny.org` (para o bake no build da Fase 1). Se algum nome/versão
divergir para 7.2, registrar o real.

- [ ] **Step 2: Confirmar as 5 classes CI + o mecanismo de definição de classe**

Run:
```bash
docker compose exec -T znuny-web su otrs -s /bin/bash -c 'cd /opt/otrs && \
  bin/otrs.Console.pl Admin::ITSM::ConfigItem::ListClasses 2>/dev/null || \
  echo "(comando não existe — descobrir via DB/SysConfig)"'
docker compose exec -T postgres psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" \
  -c "select id, name from general_catalog where general_catalog_class='ITSM::ConfigItem::Class';"
```
Descobrir e **congelar**: como editar a **definição** de uma classe (a definição é YAML/Perl em
`configitem_definition`; via UI Admin → "Config Item" → classe → "Change definition", ou via
`Kernel::System::ITSMConfigItem::DefinitionAdd`). Congelar o snippet que **adiciona o atributo
`CustomerCompany`** (tipo que referencia empresa-cliente — provavelmente `Customer` ou um
`Text`/`GeneralCatalog`; confirmar o tipo de campo suportado) a cada classe.

- [ ] **Step 3: Congelar a API nativa que as ops GI vão embrulhar**

Inspecionar (no container) os métodos disponíveis e **congelar assinaturas**:
```bash
docker compose exec -T znuny-web sh -c 'grep -nE "^=item|sub (ConfigItemSearch|ConfigItemGet|VersionGet|ConfigItemLookup|ClassList)" /opt/otrs/Kernel/System/ITSMConfigItem.pm | head -40'
docker compose exec -T znuny-web sh -c 'grep -nE "sub (LinkAdd|LinkList)" /opt/otrs/Kernel/System/LinkObject.pm | head'
```
Congelar: como **buscar CIs por um atributo** (CustomerCompany) — provavelmente
`ConfigItemSearchExtended`/`ConfigItemSearch` com `What`/XML attrs, ou `ConfigItemSearch` +
filtro; como **obter** um CI + sua versão (`VersionGet`); e `LinkObject->LinkAdd(SourceObject
=>'Ticket', SourceKey=>tid, TargetObject=>'ITSMConfigItem', TargetKey=>ciid, Type=>'RelevantTo',
State=>'Valid', UserID=>1)` para linkar.

- [ ] **Step 4: Escrever o doc de congelamento** com TUDO acima (pacotes+versões+URLs, snippet de
  definição da classe com `CustomerCompany`, e as assinaturas GI a embrulhar). Este doc é a fonte
  das Fases 1.

- [ ] **Step 5: Commit**
```bash
git add docs/superpowers/spikes/2026-06-09-r1k-znuny-itsm-cmdb.md
git commit -m "spike(#1K): R1K — congela pacotes ITSM + definição de classe + API ConfigItem/Link

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

> **As Fases 1 abaixo consomem o doc de congelamento.** Onde o plano diz "(per R1K)", use o
> valor/assinatura/snippet exato que o spike congelou — NÃO invente.

---

> **⚠️ R1K SUPERSEDE (ler `docs/superpowers/spikes/2026-06-09-r1k-znuny-itsm-cmdb.md`):**
> (1) São **3 pacotes** (GeneralCatalog→ITSMCore→ITSMConfigurationManagement), **versão 7.2.1**;
> **ImportExport NÃO é necessário**. (2) `.opm` em `https://addons.znuny.com/public/<Pkg>-7.2.1.opm`
> (NÃO `download.znuny.org/releases/itsm`); instalar por **caminho local** (`Admin::Package::Install
> /path.opm`). (3) **`CustomerID` já é nativo** nas 5 classes (Input type `CustomerCompany`) →
> **NÃO criar atributo custom**; o escopo por tenant usa o `CustomerID` nativo (o
> `ensure-cmdb-customercompany.pl` é desnecessário). (4) API congelada: search =
> `ConfigItemSearchExtended(ClassIDs=>[id], What=>[{"[%]{'Version'}[%]{'CustomerID'}[%]{'Content'}"=>cid}])`;
> get = `ConfigItemGet`+`VersionGet(XMLDataGet=>1)`; link = `LinkObject->LinkAdd(SourceObject=>'Ticket',
> TargetObject=>'ITSMConfigItem', Type=>'RelevantTo', State=>'Valid', UserID=>1)`. CI só é
> pesquisável após `VersionAdd`; ids de classe/estado resolvidos por nome. **Onde o texto abaixo
> diz "atributo CustomerCompany", leia "campo CustomerID nativo" e pule a criação de atributo.**

## FASE 1 — Znuny: instalar CMDB (3 add-ons) + ops GI (escopo por CustomerID nativo)

### Task 1: Bake dos `.opm` + install idempotente + atributo CustomerCompany

**Files:**
- Create: `znuny/itsm/*.opm` (os 4 pacotes, versões per R1K) — baixados no build
- Create: `znuny/scripts/ensure-itsm.sh` (install idempotente + definição de classe)
- Modify: `znuny/Dockerfile` (download/COPY dos .opm) · `znuny/entrypoint.sh` (chama ensure-itsm)

- [ ] **Step 1: Dockerfile — baixar os 4 `.opm` no build** (URLs/versões per R1K), para
  `${OTRS_HOME}/var/packages/`. Mirror do bloco de download do tarball (curl -fSL). Ordem de
  dependência preservada nos nomes.

- [ ] **Step 2: `ensure-itsm.sh` — install idempotente + classe** (per R1K):
```sh
#!/bin/bash
set -e
cd /opt/otrs
for opm in GeneralCatalog ITSMCore ImportExport ITSMConfigurationManagement; do
  bin/otrs.Console.pl Admin::Package::List | grep -qi "$opm" || \
    bin/otrs.Console.pl Admin::Package::Install "/opt/otrs/var/packages/${opm}-<versão-R1K>.opm"
done
# Adiciona o atributo CustomerCompany a cada classe (idempotente — checa antes), per R1K:
perl scripts/ensure-cmdb-customercompany.pl
```
(O `ensure-cmdb-customercompany.pl` aplica a definição congelada no R1K, idempotente.)

- [ ] **Step 3: entrypoint.sh — chamar `ensure-itsm.sh`** no provisionamento, após o init do DB
  e antes do exec do Apache (mesma seção do install do Elasticsearch). Idempotente.

- [ ] **Step 4: Build + smoke** — `docker compose build znuny-web` (sem erro); subir e rodar
  `ensure-itsm.sh`; `Admin::Package::List` lista os 4; a definição de uma classe mostra o
  atributo `CustomerCompany`.

- [ ] **Step 5: Commit** `feat(#1K fase 1): bake+install ITSM CMDB idempotente + atributo CustomerCompany`.

### Task 2: Ops GI ConfigItemSearch + ConfigItemGet (+ link no TicketCreate)

**Files:**
- Create: `znuny/Custom/Kernel/GenericInterface/Operation/GertiTicket/ConfigItemSearch.pm`,
  `ConfigItemGet.pm` (espelham as ops GertiTicket existentes; embrulham a API congelada no R1K)
- Modify: `znuny/Custom/.../GertiTicket/TicketCreate.pm` (aceitar `ConfigItemID` opcional → `LinkObject->LinkAdd` após criar o ticket, per R1K)
- Modify: `znuny/webservices/GertiTicket.yml` (+2 ops + rotas `/ConfigItem/Search`, `/ConfigItem/Get`) · `znuny/Dockerfile` (COPY + perl -c das 2 ops)

- [ ] **Step 1: Escrever `ConfigItemSearch.pm`** — estrutura idêntica às ops GertiTicket
  (`new`/`Run`/`_CheckAccessToken` lendo `GertiAdmin::AccessToken`; `ObjectManagerDisabled`).
  `Run` recebe `CustomerCompany` (obrigatório) → busca CIs cujo atributo `CustomerCompany` casa
  (chamada congelada no R1K) → retorna `{ ConfigItems: [{Id, Number, Class, Name, DeplState,
  InciState}] }`. Código exato dos campos/método **per R1K**.

- [ ] **Step 2: Escrever `ConfigItemGet.pm`** — recebe `ConfigItemID` + `CustomerCompany`;
  **guarda de posse:** retorna NotFound se o CI não tiver esse `CustomerCompany` (anti-IDOR).
  Retorna atributos + versão (per R1K).

- [ ] **Step 3: Estender `TicketCreate.pm`** — se `Data->{ConfigItemID}` presente e o ticket foi
  criado, `LinkObject->LinkAdd(...)` (assinatura per R1K) ligando Ticket↔ConfigItem; falha do link
  não derruba a criação (loga). Retornar o `ConfigItemID` linkado no Data.

- [ ] **Step 4: YAML + Dockerfile** — registrar `ConfigItemSearch`/`ConfigItemGet` (+rotas) no
  `GertiTicket.yml`; COPY das 2 ops + incluí-las no loop `perl -c` do Dockerfile.

- [ ] **Step 5: Build (perl -c gate)** — `docker compose build znuny-web`; as 2 ops `syntax OK`.

- [ ] **Step 6: Commit** `feat(#1K fase 1): GI ConfigItemSearch/Get + link CI↔ticket no TicketCreate`.

---

## FASE 2 — Sidecar: /v1/assets + config_item_id no ticket

### Task 3: Cliente GI de CMDB

**Files:**
- Modify: `apps/sidecar/src/gerti_sidecar/integrations/znuny_ticket.py` (+ `config_item_search`, `config_item_get`; e `create_ticket` ganha `config_item_id`)
- Test: `apps/sidecar/tests/test_znuny_cmdb_client.py`

- [ ] **Step 1: Teste** (mock `_post`): `config_item_search(customer_id)` → mapeia
  `{ConfigItems:[...]}` para uma lista de dataclasses `AssetSummary(id, number, class_, name,
  deploy_state, inci_state)`; `config_item_get(id, customer_id)` → `AssetDetail`; e
  `create_ticket(..., config_item_id=...)` inclui `ConfigItemID` no payload.

```python
# apps/sidecar/tests/test_znuny_cmdb_client.py
from __future__ import annotations
import pytest
from gerti_sidecar.integrations import znuny_ticket

@pytest.mark.asyncio
async def test_config_item_search(monkeypatch):
    async def fake_post(route, body):
        assert route == "/ConfigItem/Search"
        assert body["CustomerCompany"] == "AURORA"
        return {"ConfigItems": [{"Id": 5, "Number": "10001", "Class": "Computer",
                                 "Name": "PC-001", "DeplState": "Production", "InciState": "Operational"}]}
    monkeypatch.setattr(znuny_ticket, "_post", fake_post)
    rows = await znuny_ticket.config_item_search(customer_id="AURORA")
    assert rows[0].id == 5 and rows[0].class_ == "Computer" and rows[0].name == "PC-001"

@pytest.mark.asyncio
async def test_config_item_get_passes_customer(monkeypatch):
    async def fake_post(route, body):
        assert route == "/ConfigItem/Get"
        assert body["CustomerCompany"] == "AURORA" and body["ConfigItemID"] == 5
        return {"Id": 5, "Number": "10001", "Class": "Computer", "Name": "PC-001",
                "DeplState": "Production", "InciState": "Operational", "Attributes": {"SerialNumber": "SN9"}}
    monkeypatch.setattr(znuny_ticket, "_post", fake_post)
    d = await znuny_ticket.config_item_get(config_item_id=5, customer_id="AURORA")
    assert d.number == "10001" and d.attributes.get("SerialNumber") == "SN9"
```

- [ ] **Step 2: Rodar e ver falhar** `cd apps/sidecar && uv run pytest tests/test_znuny_cmdb_client.py -q`.

- [ ] **Step 3: Implementar** (em `znuny_ticket.py`): dataclasses `AssetSummary`/`AssetDetail`;
  `config_item_search(*, customer_id)` → POST `/ConfigItem/Search {CustomerCompany}`;
  `config_item_get(*, config_item_id, customer_id)` → POST `/ConfigItem/Get {ConfigItemID, CustomerCompany}`;
  e adicionar param opcional `config_item_id: int | None = None` em `create_ticket` → inclui
  `ConfigItemID` no payload quando presente. Incluir nomes no `__all__`. (Estas usam o `_post`
  do token de cliente — o portal só lê ativos do próprio tenant.)

- [ ] **Step 4: Rodar + gate** `… pytest tests/test_znuny_cmdb_client.py -q && uv run ruff check . && uv run mypy src`.

- [ ] **Step 5: Commit** `feat(#1K fase 2): cliente GI config_item_search/get + config_item_id em create_ticket`.

### Task 4: Router `/v1/assets*` + `config_item_id` no `/v1/tickets`

**Files:**
- Create: `apps/sidecar/src/gerti_sidecar/routers/assets.py`
- Modify: `apps/sidecar/src/gerti_sidecar/main.py` (registrar) · `routers/tickets.py` (campo `config_item_id` no form de criação)
- Test: `apps/sidecar/tests/test_assets_router.py`

- [ ] **Step 1: Teste** (sessão cliente; GI mockado; escopo por CustomerID; anti-IDOR):

```python
# apps/sidecar/tests/test_assets_router.py
from __future__ import annotations
import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from gerti_sidecar import db
from gerti_sidecar.auth.session import encode_session
from gerti_sidecar.config import get_settings
from gerti_sidecar.integrations import znuny_ticket
from gerti_sidecar.main import create_app
from gerti_sidecar.models import Tenant, TenantBranding, ZnunyInstance

@pytest.mark.asyncio
async def test_assets_scoped_by_tenant(engine, app_session_factory, session, monkeypatch):
    monkeypatch.setenv("SESSION_SECRET", "test-secret-32-chars-minimum-xxxx")
    monkeypatch.setenv("ENVIRONMENT", "test"); get_settings.cache_clear()
    inst = ZnunyInstance(name="i", base_url="http://z", db_dsn_secret_ref="x",
                         webservice_token_secret_ref="x", webhook_signing_secret_ref="x", mode="pool")
    session.add(inst); await session.flush()
    t = Tenant(legal_name="Aurora", trade_name="Aurora", document="1",
               znuny_customer_id="AURORA", znuny_instance_id=inst.id, subdomain="aurora")
    session.add(t); await session.flush(); session.add(TenantBranding(tenant_id=t.id, display_name="Aurora"))
    await session.commit()
    captured = {}
    async def fake_search(*, customer_id):
        captured["cid"] = customer_id
        return [znuny_ticket.AssetSummary(id=5, number="10001", class_="Computer",
                                          name="PC-001", deploy_state="Production", inci_state="Operational")]
    monkeypatch.setattr(znuny_ticket, "config_item_search", fake_search)
    monkeypatch.setattr(db, "AdminSessionLocal",
                        async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession))
    monkeypatch.setattr(db, "SessionLocal", app_session_factory)
    app = create_app(); st = get_settings(); h = {"host": "aurora.suporte.gerti.com.br"}
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        assert (await c.get("/v1/assets", headers=h)).status_code == 401
        c.cookies.set("gsid", encode_session(str(t.id), "joe", "helpdesk", st))
        r = await c.get("/v1/assets", headers=h)
        assert r.status_code == 200 and r.json()[0]["name"] == "PC-001"
        assert captured["cid"] == "AURORA"   # escopo por tenant (server-trusted)
```

- [ ] **Step 2: Rodar e ver falhar.**

- [ ] **Step 3: Implementar `assets.py`** (mirror de `ticketing_meta.py`/`tickets.py`):
  `GET /v1/assets` (`get_current_session`; `customer_id = request.state.tenant.znuny_customer_id`;
  chama `config_item_search(customer_id=...)`; mapeia para JSON); `GET /v1/assets/{id}` (chama
  `config_item_get(config_item_id, customer_id)`; `ZnunyWriteError`→404 anti-IDOR,
  `ZnunyUnavailable`→503). Registrar no `main.py`.

- [ ] **Step 4: `tickets.py`** — `POST /v1/tickets` ganha `config_item_id: int | None = Form(None)`
  → passa para `ticketing_service.open_ticket` → `znuny_ticket.create_ticket(..., config_item_id=...)`.
  (Estender `OpenTicketInput` com `config_item_id`.)

- [ ] **Step 5: Gate + commit** `feat(#1K fase 2): /v1/assets* (escopo por tenant, anti-IDOR) + config_item_id no /v1/tickets`.

### Task 5: Grep-guard só-GI

**Files:** Test `apps/sidecar/tests/test_assets_no_direct_znuny.py` (mirror dos guards #1E/#1B/#1J:
`assets.py` não contém needles de SQL direto no schema znuny). Rodar + commit
`test(#1K fase 2): grep-guard — assets só via GI`.

---

## FASE 3 — Portal: /ativos + abrir chamado a partir do ativo

> **REQUIRED SUB-SKILL:** `frontend-design`. Reusa os padrões do portal (`server/utils/sidecar.ts`, páginas de contratos/tickets, branding tokens). Read-only; cores semânticas nunca = cor de marca (H8).

### Task 6: Server proxies + página `/ativos` (lista)

**Files:**
- Create: `apps/portal/server/api/portal/assets/index.get.ts`, `[id].get.ts`
- Create: `apps/portal/pages/ativos/index.vue` · Modify `apps/portal/layouts/default.vue` (nav "Ativos")

- [ ] **Step 1: Proxies** (padrão `sidecarFetch`): `index.get.ts` → `GET /v1/assets`;
  `[id].get.ts` → `GET /v1/assets/${id}`.
- [ ] **Step 2: `/ativos`** (`middleware: 'auth'`): `useAsyncData` → `GET /api/portal/assets`;
  lista (nome, classe, status de deploy/incidente como badges, número). Linha → `/ativos/[id]`.
  Estados vazio/carregando/erro PT-BR. Nav "Ativos" para os papéis logados.
- [ ] **Step 3: typecheck/eslint + commit** `feat(#1K fase 3): /ativos (lista) + proxies + nav`.

### Task 7: Página `/ativos/[id]` (detalhe) + "abrir chamado a partir do ativo"

**Files:**
- Create: `apps/portal/pages/ativos/[id].vue` · Modify `apps/portal/pages/tickets/novo.vue` (ler `?ativo=`)

- [ ] **Step 1: `/ativos/[id]`** — `GET /api/portal/assets/[id]`; 404 amigável; cabeçalho (nome,
  classe, status) + atributos (serial, etc.); botão **"Abrir chamado sobre este ativo"** →
  `navigateTo('/tickets/novo?ativo=' + id)`.
- [ ] **Step 2: `/tickets/novo`** — ler `route.query.ativo`; se presente, mostrar um aviso
  "Chamado sobre o ativo #N" e **incluir `config_item_id` no FormData** do submit.
- [ ] **Step 3: typecheck/eslint + commit** `feat(#1K fase 3): /ativos/[id] + abrir chamado vinculado ao ativo`.

### Task 8: Smoke vitest do portal

**Files:** teste no harness vitest do portal — lógica do "abrir chamado a partir do ativo"
(monta o link `?ativo=` e inclui `config_item_id` no FormData) + render dos badges de status.
Rodar + commit `test(#1K fase 3): smoke /ativos + link de chamado`.

---

## FASE 4 — Deploy + docs + e2e

### Task 9: Runbook OPS + ARCHITECTURE + INTEGRATION
- [ ] **Step 1:** `.ia/OPS.md` nova seção "Deploy do CMDB/ativos (#1K)": rebuild `znuny-web`
  (bakeia .opm + install idempotente + classe), recria; Update do `GertiTicket` (`--webservice-id`);
  rebuild `sidecar`+`portal`; e2e; rollback (`$DC stop portal sidecar`; `Admin::Package::Uninstall`
  na ordem inversa se preciso; **NUNCA** `make reset`). `> Status` factual.
- [ ] **Step 2:** `.ia/ARCHITECTURE.md` (subseção CMDB + fluxo ativo→chamado) + `.ia/INTEGRATION.md`
  (tabela (e): linhas #1K Pronto/gateado). Commit.

### Task 10: Gate final + e2e (local e staging)
- [ ] **Step 1:** sidecar gate completo + `make test` + portal typecheck/vitest verdes.
- [ ] **Step 2: e2e local** — MSP cadastra um ativo p/ Aurora no Znuny (UI agente ou
  `ITSMConfigItem` console) com `CustomerCompany=AURORA` → cliente loga no portal → `/ativos`
  mostra o ativo → "abrir chamado" → ticket criado **linkado ao CI** (conferir o link no Znuny
  via `LinkObject->LinkList` ou a UI). Limpar throwaway.
- [ ] **Step 3: e2e staging** — mesma prova na VPS; serviços anteriores intactos.

---

## Self-Review (cobertura da spec)
- **D-1K-1 escopo (CMDB+portal+abrir chamado)** → Fases 1-3. ✅
- **D-1K-2/3 add-ons oficiais + bake/install idempotente** → Task 1 (+R1K congela versões). ✅
- **D-1K-4 classes padrão** → Task 0/1. ✅
- **D-1K-5 escopo por tenant via CustomerCompany** → Task 1 (atributo) + 2 (search filtra) + 4 (server-trusted). ✅
- **D-1K-6 read-only + abrir chamado linka CI** → Task 2 (link no TicketCreate) + 4 (config_item_id) + 7 (UI). ✅
- **D-1K-7 acesso a qualquer cliente logado** → Task 4 (`get_current_session`, não require_admin). ✅
- **Segurança §4:** anti-IDOR no get (Task 2/4), só-GI (grep-guard Task 5), server-trusted CustomerID. ✅
- **Testes §5 / Deploy §6:** Tasks 3-8 (testes), 9-10 (deploy+e2e). ✅

**Spike-gated (não placeholders — congelados no R1K, padrão #1F/#1G):** versões/URLs dos `.opm`,
snippet de definição da classe com `CustomerCompany`, e as assinaturas exatas de
`ITSMConfigItem`/`LinkObject` embrulhadas nas ops GI (Tasks 1-2). Tudo o mais (sidecar/portal)
está concreto.
