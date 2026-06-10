# R1Q — Como o Znuny entrega eventos de ticket ao sidecar (Event module vs Invoker GI)

**Data:** 2026-06-09 · **Spec:** #1Q (Motor de automação próprio no sidecar) · **Status:** decidido

## Pergunta

O motor de automação do #1Q precisa reagir a eventos de ticket (criar, novo
artigo, mudança de estado, escalonamento). Como o Znuny entrega esses eventos
ao sidecar de forma **assinada (HMAC), confiável e upgrade-safe**?

Duas abordagens candidatas:

1. **Invoker GI nativo (HTTP::REST)** registrado num webservice, disparado por
   um *Event* configurado no SysConfig (`GenericInterface::Invoker::SettingsModule`
   + `Ticket::EventModulePost###...GenericInterface`).
2. **Event module Perl próprio** em `Custom/Kernel/System/Ticket/Event/` que, no
   evento, monta a payload, **assina HMAC-SHA256** e faz o `POST` ao sidecar.

## Investigação

- **Eventos disponíveis** (núcleo Znuny 7.2, `Kernel/Config/Files/XML/Ticket.xml`):
  `TicketCreate`, `ArticleCreate`, `TicketStateUpdate`, `TicketQueueUpdate`,
  `TicketPriorityUpdate`, `EscalationResponseTimeStart`, `EscalationUpdateTimeStart`,
  `EscalationSolutionTimeStart`, etc. Todos passam `Data => { TicketID => ... }`
  ao handler (o `ArticleCreate` também traz `ArticleID`). Confirma a 7.2.3 do
  roadmap §4.
- **Invoker nativo NÃO assina HMAC.** O Generic Interface Invoker manda a payload
  via o módulo de mapping configurado, mas **não há ponto de extensão nativo** para
  injetar um header `X-Gerti-Signature` derivado por HMAC do corpo *exato* enviado.
  Para assinar teríamos que escrever um *mapping module* custom de qualquer forma —
  ou seja, já cairíamos em Perl custom. O Invoker nativo também acopla a payload ao
  formato de mapping do GI (verboso, frágil em upgrade de schema do webservice).
- **Confiabilidade do corpo:** o sidecar verifica HMAC sobre o **raw body**. Para
  o `compare_digest` casar, o Znuny precisa controlar **byte a byte** o corpo que
  assina e envia. Um Event module Perl com `JSON->encode` + `POST` com esse corpo
  literal garante isso; o Invoker GI, que serializa por conta própria depois do
  mapping, não dá essa garantia.

## Decisão: **Event module Perl custom** (`GertiAutomation.pm`)

`Custom/Kernel/System/Ticket/Event/GertiAutomation.pm` — overlay `Custom/`
(upgrade-safe, primeiro no `@INC`). Registrado via **SysConfig XML**
(`Custom/Kernel/Config/Files/XML/GertiAutomation.xml`) nos eventos
`TicketCreate|ArticleCreate|TicketStateUpdate|TicketPriorityUpdate|TicketQueueUpdate|Escalation*TimeStart`.

No evento, o módulo:

1. Lê `TicketID` de `$Param{Data}`; `TicketGet` para puxar
   `CustomerID, State, Priority, Queue, Service, Title, Type, Created, Age`.
2. Monta a payload canônica:
   ```json
   {"event":"<nome_normalizado>","ticket_id":<int>,"customer_id":"<CustomerID>",
    "title":"...","state":"...","priority":"...","queue":"...","service":"...",
    "type":"...","age_minutes":<int>,"sla_state":"<ok|warning|breached>"}
   ```
   Normaliza o nome do evento Znuny → nome do trigger do sidecar
   (`TicketCreate→ticket_create`, `ArticleCreate→article_create`,
   `TicketStateUpdate→state_update`, `Escalation*TimeStart→escalation`).
3. **Assina:** `Digest::SHA::hmac_sha256_hex($body_json, $Secret)` onde
   `$Secret = Config->Get('GertiAutomation::WebhookSecret')` (renderizado pelo
   entrypoint do `Config.pm.tmpl` a partir do env `GERTI_WEBHOOK_SIGNING_SECRET`,
   **o MESMO segredo** que o sidecar resolve do `ZnunyInstance.webhook_signing_secret_ref`).
4. **POST** `http://sidecar:8001/v1/hooks/znuny/ticket-event` com headers
   `Content-Type: application/json` e `X-Gerti-Signature: sha256=<hexdigest>`,
   corpo = o **mesmo** `$body_json` que foi assinado. Best-effort (`eval`/timeout
   curto): falha de rede **nunca** quebra a transação do ticket no Znuny.

### Como o HMAC é assinado/verificado (fonte única de verdade)

- **Algoritmo:** HMAC-SHA256, hexdigest. Header: `X-Gerti-Signature: sha256=<hex>`.
- **Mensagem assinada:** o corpo HTTP **bruto** (bytes exatos), nada de re-serializar
  no meio. Znuny assina o `$body_json` literal e envia esse literal.
- **Segredo compartilhado:** uma string forte (ex.: `openssl rand -hex 32`) presente
  nos DOIS lados:
  - **Znuny:** `Config->Get('GertiAutomation::WebhookSecret')`, renderizado pelo
    `entrypoint.sh`/`Config.pm.tmpl` a partir do env `GERTI_WEBHOOK_SIGNING_SECRET`.
  - **Sidecar:** gravado em `ZnunyInstance.webhook_signing_secret_ref` (a coluna já
    existe no modelo) e lido pelo router via `AdminSessionLocal` (BYPASSRLS). MVP:
    o `_ref` guarda o segredo direto (env-style); um cofre é melhoria futura.
- **Verificação (sidecar):** `hmac.compare_digest` (constant-time) sobre o raw body.
  Assinatura inválida/ausente → **401**. Tenant não resolvido pelo `customer_id` →
  **202** (aceita e ignora, não vaza qual customer existe).

### Idempotência do registro

`znuny/scripts/ensure-automation-invoker.pl` (chamado pelo entrypoint, idempotente):
verifica/garante que o Event module está registrado no SysConfig (via o XML
bakeado) e que o `GertiAutomation::WebhookSecret` está setado; roda
`Maint::Config::Rebuild`. Como o registro vem por **XML SysConfig** (declarativo,
versionado na imagem), o script é majoritariamente um `Rebuild` + verificação —
sem passos destrutivos.

## Snippet congelado (esqueleto do .pm)

```perl
package Kernel::System::Ticket::Event::GertiAutomation;
# evento → TicketGet → payload JSON → HMAC-SHA256 → POST sidecar (best-effort)
use Digest::SHA qw(hmac_sha256_hex);
# ... $Sig = hmac_sha256_hex($Body, $Secret); header X-Gerti-Signature: sha256=$Sig
```

## Consequências / por quê (vs GenericAgent e vs Invoker nativo)

- **Não usamos GenericAgent** porque o motor é **próprio no sidecar** (no-code por
  tenant, RLS, allowlist de ações, avaliador puro) — o GenericAgent é por-instância,
  não multi-tenant nem no-code pelo console.
- **Não usamos Invoker GI nativo** porque ele **não assina HMAC** sobre o corpo
  exato e acopla a payload ao mapping verboso do webservice; o Event module nos dá
  controle byte-a-byte do corpo assinado e é o caminho mais simples e robusto.
- **Upgrade-safe:** `.pm` em `Custom/` (primeiro no `@INC`) + registro por XML
  SysConfig em `Custom/Kernel/Config/Files/XML/` — núcleo Znuny intocado (D-padrão).
- **Bake no Dockerfile:** o `.pm` e o `.xml` entram via `COPY` + `perl -c` (lição #1O).
```
