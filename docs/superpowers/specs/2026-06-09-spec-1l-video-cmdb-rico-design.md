# Spec #1L — Anexos de vídeo (#1E) + CMDB enriquecido (#1K)

**Data:** 2026-06-09
**Status:** aprovado no brainstorming → pronto para plano/execução
**Escopo:** duas features independentes. **(A)** permitir **upload de vídeos** nos anexos do
chamado (#1E). **(B)** **enriquecer a gestão de ativos** (#1K): mais atributos no Config Item
(SO, disco, memória, CPU, data de criação…), exibidos no portal.

## Parte A — Anexos de vídeo

### A.1 Decisões
- **A1:** cap por arquivo **100 MB**; formatos de vídeo: `mp4, mov, webm, mkv, avi` (somados aos atuais).
- **A2:** `MaxLength` do GI `GertiTicket` sobe de 100 MB → **200 MB** (base64 de 100 MB ≈ 133 MB cabe).
- **A3 (ressalva, não-bloqueante):** o Cloudflare free limita o corpo da requisição a ~100 MB na
  borda; vídeo próximo do teto pode ser rejeitado antes de chegar (afeta o acesso público via
  tunnel; o caminho interno sidecar→Znuny aceita). Documentado no runbook.

### A.2 Mudanças
- `apps/sidecar/src/gerti_sidecar/routers/tickets.py`: `_ALLOWED_EXT` += `{.mp4,.mov,.webm,.mkv,.avi}`;
  `_MAX_ATTACH_BYTES = 100 * 1024 * 1024`.
- `znuny/webservices/GertiTicket.yml`: `MaxLength: '200000000'`.
- `apps/portal/pages/tickets/novo.vue`: `accept` inclui os vídeos; texto de ajuda atualizado
  ("…vídeos mp4/mov/webm · até 100 MB cada").
- Testes: ext de vídeo aceita (201), arquivo acima de 100 MB → **413**, ext não permitida → 415.

## Parte B — CMDB enriquecido

### B.1 Decisões
- **B1:** estender **a classe Computer** com **Disco**, **Memória**, **CPU** (campos `Text`),
  idempotente. (Demais classes ficam como estão — escopo enxuto.)
- **B2:** o `ConfigItemGet` passa a mapear **todos** os atributos da versão (genérico) + a
  **data de criação** (`CreateTime`/header do CI) + classe/estados. Hoje só mapeia `SerialNumber`.
- **B3:** o portal `/ativos/[id]` mostra a **ficha completa** (SO, CPU, Memória, Disco, Vendor,
  Model, Serial, Descrição, data de criação, estados de deploy/incidente).
- **B4:** o seed demo (`seed-cmdb.pl`) popula os novos campos nos ativos da Aurora.

### B.2 Incógnita a verificar (mini-spike, não bloqueia a Parte A)
O **formato exato da definição de classe** do ITSM no 7.2 (YAML armazenado em
`configitem_definition`) e o `DefinitionAdd` idempotente. O R1K já registrou que é YAML; antes de
editar, ler a definição viva da classe Computer e adicionar os 3 campos preservando os existentes
(`DefinitionGet` → `DefinitionAdd` só se faltar). Congelar o snippet.

### B.3 Mudanças
- **Znuny:** `znuny/scripts/ensure-cmdb-fields.pl` (idempotente: lê a definição da Computer;
  se não tiver Disco/Memória/CPU, regrava a definição com eles preservando o resto). Chamado pelo
  provisionamento (entrypoint, após `ensure-itsm.sh`). Núcleo imutável (é a API de definição do
  próprio ITSM, não patch de core).
- **GI** `ConfigItemGet.pm`: extrair **todos** os pares chave→Content do `XMLData->[1]{Version}[1]`
  (genérico) para o mapa `Attributes`, mantendo a guarda de posse por `CustomerID`; incluir
  `CreateTime` (do `ConfigItemGet` header) no retorno.
- **Sidecar** `znuny_ticket.py`: `AssetDetail` ganha `created: str`; `config_item_get` mapeia
  `Attributes` (genérico, já é dict) + `created` (de `CreateTime`).
- **Portal** `pages/ativos/[id].vue`: renderizar todos os atributos do mapa + data de criação
  (formatada) + estados; rótulos amigáveis PT-BR para as chaves conhecidas (OperatingSystem→"Sistema
  operacional", Ram/Memória, etc.).
- **Seed** `scripts/seed-cmdb.pl`: setar OperatingSystem/CPU/Memória/Disco nos ativos Computer da Aurora.
- Testes: GI mapping genérico (mock retornando vários atributos), `AssetDetail.created`, render do portal.

## Arquitetura / invariantes (herdados)
Núcleo Znuny imutável (vídeo só muda allowlist+MaxLength; CMDB usa a API de definição do ITSM via
script idempotente). Escrita/leitura via GI. Escopo de ativo por `CustomerID` (anti-IDOR no
ConfigItemGet, inalterado). Provisionamento idempotente. White-label preservado (ativos por tenant).

## Deploy (staging, padrão dos anteriores)
Rebuild `znuny-web` (novo `MaxLength` + `ensure-cmdb-fields` no provisionamento + GI mapping) +
recria; Update do `GertiTicket` (`--webservice-id`); rebuild `sidecar`+`portal`; rodar
`ensure-cmdb-fields.pl` + re-seed dos ativos. e2e: anexar um vídeo num chamado; e abrir um ativo
no portal e ver SO/CPU/Memória/Disco/data de criação. Runbook + `.ia/` no mesmo PR.

## Faseamento
1. **Parte A (vídeo)** — sidecar + yml + portal + testes.
2. **Parte B (CMDB)** — mini-spike do formato de definição → ensure-cmdb-fields + GI mapping + sidecar + portal + seed.
3. **Deploy + e2e staging** (vídeo anexado; ficha de ativo rica).

## Não-objetivos
Transcodificação/preview de vídeo; antivírus de anexo; estender Disco/Memória às outras classes
(só Computer); paginação/limite global de tamanho de ticket além do MaxLength.
