# Spec #1L — Vídeo + CMDB rico Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans. Steps use checkbox (`- [ ]`) syntax.

**Goal:** (A) permitir anexar vídeos (até 100 MB) ao abrir chamado; (B) enriquecer a ficha de ativo (Computer) com Disco/Memória/CPU + Sistema Operacional + data de criação, exibida no portal.

**Architecture:** (A) é só ampliar allowlist+cap no sidecar, MaxLength no GI e `accept` no portal. (B) estende a definição da classe Computer do ITSM (idempotente), faz a op GI `ConfigItemGet` mapear todos os atributos da versão + a data de criação, o sidecar/portal exibem a ficha completa, e o seed popula os campos. Spec: `docs/superpowers/specs/2026-06-09-spec-1l-video-cmdb-rico-design.md`.

**Tech Stack:** FastAPI+SQLAlchemy (sidecar), Nuxt 3 (portal), Znuny ITSM Perl (`ITSMConfigItem` definition + ConfigItemGet/VersionGet). Gate: sidecar `ruff`+`mypy`+`pytest`; `perl -c` no build; portal typecheck+vitest.

---

## FASE 1 — Parte A: anexos de vídeo

### Task 1: sidecar allowlist + cap

**Files:** Modify `apps/sidecar/src/gerti_sidecar/routers/tickets.py` · Test `apps/sidecar/tests/test_tickets_router.py`

- [ ] **Step 1: teste** — adicionar em `test_tickets_router.py` um teste que um anexo `.mp4` é aceito (201) e que um arquivo > 100 MB → 413. Reusar o harness do arquivo (`_seed`, monkeypatch `znuny_ticket.create_ticket`, multipart). Exemplo do happy path com vídeo (arquivo pequeno, ext .mp4):
```python
@pytest.mark.asyncio
async def test_video_attachment_allowed(engine, app_session_factory, session, monkeypatch):
    monkeypatch.setenv("SESSION_SECRET", "test-secret-32-chars-minimum-xxxx")
    monkeypatch.setenv("ENVIRONMENT", "test"); get_settings.cache_clear()
    t = await _seed(session)
    async def fake_create(**kw):
        assert kw["attachments"] and kw["attachments"][0].filename.endswith(".mp4")
        return znuny_ticket.TicketCreated(7, "N7")
    monkeypatch.setattr(znuny_ticket, "create_ticket", fake_create)
    monkeypatch.setattr(db, "AdminSessionLocal",
                        async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession))
    monkeypatch.setattr(db, "SessionLocal", app_session_factory)
    app = create_app(); st = get_settings(); h = {"host": "acme.suporte.gerti.com.br"}
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        c.cookies.set("gsid", encode_session(str(t.id), "joe", "helpdesk", st))
        r = await c.post("/v1/tickets", headers=h,
                         data={"title": "t", "body": "b"},
                         files={"files": ("clip.mp4", b"\x00\x00\x00\x18ftypmp42", "video/mp4")})
        assert r.status_code == 201
```
(Confirme o import de `db`/`async_sessionmaker`/`AsyncSession` já usados no arquivo.)

- [ ] **Step 2: rodar e ver falhar** `cd apps/sidecar && DATABASE_URL=postgresql+asyncpg://x:y@localhost/z uv run pytest tests/test_tickets_router.py::test_video_attachment_allowed -q` → FAIL (415 ext_not_allowed:.mp4).

- [ ] **Step 3: implementar** em `tickets.py`:
```python
_MAX_ATTACH_BYTES = 100 * 1024 * 1024  # 100 MB por arquivo (#1L)
_ALLOWED_EXT = {
    ".png", ".jpg", ".jpeg", ".pdf", ".txt", ".log", ".csv", ".zip", ".doc", ".docx",
    ".mp4", ".mov", ".webm", ".mkv", ".avi",  # vídeo (#1L)
}
```

- [ ] **Step 4: rodar + gate** `... uv run pytest tests/test_tickets_router.py -q && uv run ruff check . && uv run mypy src` → passa.

- [ ] **Step 5: commit** `feat(#1L): aceita anexos de vídeo (mp4/mov/webm/mkv/avi) + cap 100MB`.

### Task 2: Znuny MaxLength

**Files:** Modify `znuny/webservices/GertiTicket.yml`

- [ ] **Step 1:** trocar `MaxLength: '100000000'` por `MaxLength: '200000000'` (cabe o base64 de 100 MB).
- [ ] **Step 2: commit** `feat(#1L): GertiTicket MaxLength 200MB (base64 de vídeo 100MB)`. (O perl -c/import re-aplica no deploy via Update do webservice.)

### Task 3: portal accept + ajuda

**Files:** Modify `apps/portal/pages/tickets/novo.vue`

- [ ] **Step 1:** no `<input type="file">`, trocar o `accept` para incluir vídeo:
  `accept=".png,.jpg,.jpeg,.pdf,.txt,.log,.csv,.zip,.doc,.docx,.mp4,.mov,.webm,.mkv,.avi"`.
  Atualizar o texto do `UFormField` "Anexos" help para: `"Opcional. Imagens, PDF, docs e vídeos (mp4/mov/webm) · até 100 MB cada."`.
- [ ] **Step 2: verificar** `cd apps/portal && npx nuxi typecheck 2>&1 | tail -8` (só erros pré-existentes de nuxt.config) + `npx eslint pages/tickets/novo.vue`.
- [ ] **Step 3: commit** `feat(#1L): portal aceita vídeo no anexo (accept + ajuda)`.

---

## FASE 2 — Parte B: CMDB enriquecido

### Task 4: SPIKE-curto — congelar o formato de definição da classe Computer

**Files:** Create `docs/superpowers/spikes/2026-06-09-r1l-itsm-class-definition.md`

- [ ] **Step 1:** ler a definição viva da classe Computer (stack local de pé):
```bash
docker compose exec -T znuny-web su otrs -s /bin/bash -c "cd /opt/otrs && perl -e '
use lib qw(/opt/otrs /opt/otrs/Kernel/cpan-lib /opt/otrs/Custom);
use Kernel::System::ObjectManager; local \$Kernel::OM = Kernel::System::ObjectManager->new();
my \$GC=\$Kernel::OM->Get(q{Kernel::System::GeneralCatalog});
my \$L=\$GC->ItemList(Class=>q{ITSM::ConfigItem::Class});
my (\$cid)=grep { \$L->{\$_} eq q{Computer} } keys %\$L;
my \$CI=\$Kernel::OM->Get(q{Kernel::System::ITSMConfigItem});
my \$D=\$CI->DefinitionGet(ClassID=>\$cid);
print qq{CLASSID=\$cid\n}; print \$D->{Definition};'"
```
Capturar a **definição YAML atual** (lista de campos: Key/Name/Input). Confirmar o formato exato (YAML array de hashes) e que NÃO há Disco/Memória/CPU.

- [ ] **Step 2:** validar o `DefinitionAdd` idempotente: `DefinitionGet` retorna `Definition` (string YAML) + `DefinitionID`; `DefinitionAdd(ClassID, Definition => <YAML novo>, UserID => 1)` cria uma nova versão da definição. Idempotência: comparar se os campos já existem antes de regravar (não criar versão nova se já presentes). Congelar o snippet exato dos 3 campos a inserir (no formato do YAML real visto), p.ex.:
```yaml
---
- Key: CustomerID
  Name: Empresa
  ...
- Key: OperatingSystem
  ...
- Key: CPU
  Name: CPU
  Searchable: 1
  Input:
    Type: Text
    Size: 50
    MaxLength: 100
- Key: Memoria
  Name: Memória
  Input: { Type: Text, Size: 50, MaxLength: 100 }
- Key: Disco
  Name: Disco
  Input: { Type: Text, Size: 50, MaxLength: 100 }
```
(o formato/indentação EXATOS vêm do Step 1 — não inventar; espelhar a estrutura da definição real.)

- [ ] **Step 3:** escrever o doc de congelamento (definição atual + os 3 campos no formato certo + a forma idempotente) e commit `spike(#1L): R1L — formato da definição de classe ITSM + campos Disco/Memória/CPU`.

### Task 5: `ensure-cmdb-fields.pl` — estende a classe Computer (idempotente)

**Files:** Create `znuny/scripts/ensure-cmdb-fields.pl` · Modify `znuny/entrypoint.sh` (chama após `ensure-itsm.sh`)

- [ ] **Step 1:** escrever `ensure-cmdb-fields.pl` (per R1L): resolve a ClassID da Computer por nome; `DefinitionGet`; se a definição **já contém** `Disco`/`Memoria`/`CPU` (regex/parse) → imprime "skip" e sai 0; senão monta a definição YAML nova (a atual + os 3 campos, preservando tudo) e `DefinitionAdd(ClassID, Definition => $yaml, UserID => 1)`. Imprime resultado. Idempotente.
- [ ] **Step 2:** `entrypoint.sh`: após a chamada de `ensure-itsm.sh`, adicionar
  `su otrs -s /bin/bash -c "cd ${OTRS_HOME} && perl scripts/ensure-cmdb-fields.pl" || log "WARN: ensure-cmdb-fields falhou"` (tolerante, idempotente, padrão D6). COPY do script no Dockerfile (com chown), perto do `ensure-itsm.sh`.
- [ ] **Step 3: build** `docker compose build znuny-web` (sem erro; o script é copiado).
- [ ] **Step 4: smoke local** subir znuny-web, rodar `ensure-cmdb-fields.pl` → cria a definição com os 3 campos; re-run → "skip". `DefinitionGet` mostra Disco/Memoria/CPU.
- [ ] **Step 5: commit** `feat(#1L fase 2): ensure-cmdb-fields — estende classe Computer (Disco/Memória/CPU) idempotente`.

### Task 6: GI `ConfigItemGet` — mapear todos os atributos + data de criação

**Files:** Modify `znuny/Custom/Kernel/GenericInterface/Operation/GertiTicket/ConfigItemGet.pm` · `znuny/Dockerfile` (perl -c já cobre)

- [ ] **Step 1:** em `ConfigItemGet.pm`, substituir a extração só-de-SerialNumber por um loop genérico sobre os campos da versão. A guarda de posse por `CustomerID` permanece. Mapear genericamente:
```perl
# Atributos genéricos da versão: itera as chaves do XMLData Version (#1L).
my %Attributes;
my $VerNode = eval { $V->{XMLData}->[1]{Version}[1] } || {};
for my $Key ( sort keys %{$VerNode} ) {
    next if $Key eq 'CustomerID';            # já vai como CustomerID no topo
    my $Content = eval { $VerNode->{$Key}[1]{Content} };
    $Attributes{$Key} = $Content if defined $Content && $Content ne '';
}
```
E incluir a data de criação no retorno (do header do `ConfigItemGet`): `Created => $ConfigItem->{CreateTime}` (confirmar o nome do campo no header — per R1K é `CreateTime`/`CreateBy`; se for outro, ajustar).
Retornar `Data => { ..., CustomerID => $CustomerID, Created => $Created, Attributes => \%Attributes }`.

- [ ] **Step 2: build (perl -c gate)** `docker compose build znuny-web` → `ConfigItemGet.pm syntax OK`.
- [ ] **Step 3: commit** `feat(#1L fase 2): ConfigItemGet mapeia todos os atributos da versão + data de criação`.

### Task 7: sidecar `AssetDetail.created` + mapping

**Files:** Modify `apps/sidecar/src/gerti_sidecar/integrations/znuny_ticket.py` · Test `apps/sidecar/tests/test_znuny_cmdb_client.py`

- [ ] **Step 1: teste** — estender `test_config_item_get_*` para um `_post` mock retornando vários atributos + `Created`; asserta que `AssetDetail.attributes` traz os campos (ex. `OperatingSystem`, `CPU`, `Memoria`, `Disco`) e `AssetDetail.created == "2026-06-09 10:00:00"`.
- [ ] **Step 2: rodar e ver falhar.**
- [ ] **Step 3: implementar** — em `AssetDetail` (dataclass) adicionar `created: str`; em `config_item_get`, `created=str(data.get("Created") or "")` e `attributes=dict(data.get("Attributes") or {})` (já é genérico). Manter os campos existentes.
- [ ] **Step 4: rodar + gate.**
- [ ] **Step 5: commit** `feat(#1L fase 2): AssetDetail.created + atributos genéricos`.

> **Nota:** a rota sidecar `/v1/assets/{id}` (assets.py) já devolve `attributes`; adicionar `created` ao dict de resposta (campo novo). Incluir no commit.

### Task 8: portal `/ativos/[id]` — ficha completa

**Files:** Modify `apps/portal/pages/ativos/[id].vue`

- [ ] **Step 1 (frontend-design):** renderizar TODOS os atributos do mapa `attributes` (não só serial) + **data de criação** (`fmtDate(created)`) + estados. Rótulos PT-BR para chaves conhecidas via um pequeno mapa: `{OperatingSystem:"Sistema operacional", Vendor:"Fabricante", Model:"Modelo", SerialNumber:"Nº de série", CPU:"CPU", Memoria:"Memória", Disco:"Disco", Description:"Descrição"}` (chave desconhecida → mostra a própria chave). Layout em `dl`/tabela, no padrão do detalhe atual.
- [ ] **Step 2: verificar** typecheck + eslint do arquivo.
- [ ] **Step 3: commit** `feat(#1L fase 2): ficha de ativo completa no portal (SO/CPU/memória/disco/criação)`.

### Task 9: seed popula os novos campos

**Files:** Modify `scripts/seed-cmdb.pl`

- [ ] **Step 1:** nos ativos Computer da Aurora (AUR-NB-001, AUR-PC-014), setar no `VersionAdd` os campos `OperatingSystem` (ex. "Windows 11 Pro" / "Ubuntu 22.04"), `CPU` ("Intel i5-1135G7"), `Memoria` ("16 GB"), `Disco` ("512 GB SSD") no XMLData (formato congelado no R1L). Idempotente (o seed já pula se o CI existe — para popular nos existentes, ou recria, ou adiciona um `VersionAdd` atualizado; manter idempotência: se já tem versão com esses campos, skip).
- [ ] **Step 2: commit** `feat(#1L fase 2): seed popula SO/CPU/memória/disco nos ativos demo Aurora`.

---

## FASE 3 — Deploy + e2e (staging)

### Task 10: deploy + docs + e2e
- [ ] **Step 1: gate** sidecar (`ruff`+`mypy`+`pytest`) + portal (typecheck+vitest) verdes; `make test` intacto.
- [ ] **Step 2: deploy staging** `ssh gc git pull`; rebuild `znuny-web` (MaxLength + ensure-cmdb-fields + GI mapping) + recria; **Update GertiTicket** (`--webservice-id`); rodar `ensure-cmdb-fields.pl`; rebuild `sidecar`+`portal`; re-rodar `seed-cmdb.pl` (popula os campos).
- [ ] **Step 3: e2e staging** — (A) abrir chamado anexando um `.mp4` pequeno → 201, anexo no ticket Znuny. (B) `GET /v1/assets/{id}` (Aurora) mostra `attributes` com OS/CPU/Memoria/Disco + `created`; portal `/ativos/[id]` renderiza a ficha. Limpar throwaway do vídeo.
- [ ] **Step 4: docs** `.ia/OPS.md` (nota do MaxLength 200MB + ensure-cmdb-fields no deploy + ressalva Cloudflare 100MB) + `INTEGRATION.md` (#1L). Commit.

---

## Self-Review (cobertura)
- **A1/A2/A3 vídeo** → Tasks 1 (allowlist+cap), 2 (MaxLength), 3 (portal accept), Task 10 nota Cloudflare. ✅
- **B1 estende Computer (Disco/Memória/CPU)** → Task 4 (spike formato) + 5 (ensure-cmdb-fields). ✅
- **B2 ConfigItemGet mapeia tudo + criação** → Task 6. ✅
- **B3 portal ficha completa** → Task 8 (+ Task 7 sidecar created/attributes). ✅
- **B4 seed popula** → Task 9. ✅
- Testes (Tasks 1,7) + perl -c (2,5,6) + e2e (10). ✅

**Spike-gated (não placeholder, padrão #1F/#1G/#1K):** o formato EXATO da definição YAML da classe + o snippet dos 3 campos (Task 4) e o nome do campo de data no header do ConfigItem (Task 6) — congelados no R1L antes de implementar.
