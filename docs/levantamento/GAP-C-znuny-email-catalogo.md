# GAP-C — R9 (e-mail), R10 (mesas/filas), R11 (recorrentes), R12 (catálogo), R13 (feriados/checklists), R17 (FAQ)

> Recorte deste documento: apenas R9, R10, R11, R12, R13, R17. Demais requisitos
> ficam com outros agentes.
>
> **Regra do subsistema (ADR D21, `.ia/DECISIONS.md:552-590`):** a capa
> administrativa **não persiste um byte de configuração do Znuny**. Toda tela lê e
> escreve ao vivo pelo Generic Interface; a única gravação em `gerti` é a linha de
> `audit_log`. Toda tarefa abaixo que proponha tabela/cache traz justificativa
> explícita de por que não é cópia de config do Znuny.
>
> **Sem exclusão:** o Znuny invalida com `ValidID = 2`. As telas dizem "Invalidar".
> Onde o objeto nativo **não tem** `ValidID` (PostMaster Filter), isso vira decisão
> aberta e está marcado como tal.
>
> **Método/evidência:** além do repositório, li o **fonte real do Znuny 7.2.3**
> extraído da imagem `ground-control/znuny:7.2.3` já buildada nesta máquina
> (`docker run --rm --entrypoint sh ground-control/znuny:7.2.3`). Caminhos que
> começam com `/opt/otrs/...` são desse fonte, não do repo.

---

## R9 — E-mail: entrada e saída amarradas por fila

**Pedido (citação curta do Kleber):**
> "Quando enviar para esse e-mail, vai para a fila X. Quando enviar para esse
> e-mail, vai para a fila Y." / "E os endereços de resposta. Nas filas de DPO a
> gente usa esse. Na fila de suporte, usa esse." / "**Se entrou pelo suporte, tem
> que sair pelo suporte; se entrou pelo financeiro, sai pelo financeiro; se entrou
> por um DPO... tem que voltar também pelo encarregado de dados.**" / "Esses caras
> aqui, quando a gente recebe uma solicitação dele, volta o e-mail por ele também."
> / "Toda vez que cadastra um domínio lá no cliente, ele aparece aqui. Mas aqui a
> gente consegue ver tudo centralizado."
> (`docs/transcricoes/2026-08-15-kleber-recursos-administrativos-tiflux.txt:87-109`,
> `:95-97`)

**Estado atual:** **AUSENTE** (a superfície administrativa inteira; e o caminho de
saída está **quebrado na infra**).

Evidências, item por item:

1. **Contas de recebimento (PostMaster mail accounts) — AUSENTE na nossa capa.**
   A allowlist do dispatcher tem exatamente 6 chaves e nenhuma é `MailAccount`:
   `znuny/Custom/Kernel/GenericInterface/Operation/GertiAdmin/AdminSpec.pm:50-145`
   (`Queue`, `SLA`, `Service`, `Type`, `State`, `Priority`). Espelhada no sidecar em
   `apps/sidecar/src/gerti_sidecar/routers/admin_znuny.py:40`. Zero ocorrências de
   `MailAccount` em `znuny/` e `apps/` (grep). O objeto **existe e é limpo** no
   Znuny: `/opt/otrs/Kernel/System/MailAccount.pm:82` (`MailAccountAdd`), `:308`
   (`MailAccountGet`), `:414` (`MailAccountUpdate`), `:528` (`MailAccountList`).

2. **Endereços de sistema (SystemAddress) — AUSENTE na nossa capa, e isso já
   quebra a criação de fila hoje.** `SystemAddressID` está na lista de campos
   graváveis da Queue (`AdminSpec.pm:62`) e é **obrigatório na criação**
   (`AdminSpec.pm:67`: `RequiredOnAdd => [qw(Name GroupID SystemAddressID
   SalutationID SignatureID FollowUpID)]`), com o guard aplicado em
   `AdminObjectAdd.pm:95-100`. Mas:
   - `AdminObjectList.pm:87-99` devolve como listas de apoio apenas
     `GroupList`/`StateTypeList`/`ValidList`/`CalendarList` — **não há
     `SystemAddressList`/`SalutationList`/`SignatureList`**;
   - o rascunho de fila do console **não tem esses campos**
     (`apps/admin/composables/useZnunyObject.ts:131-142`), e o payload enviado
     também não (`useZnunyObject.ts:214-229`);
   - `apps/admin/pages/znuny/filas.vue:97-103` posta esse payload em
     `POST /api/admin/znuny/objects/Queue`.
   → **"Nova fila" no console sempre falha com `AdminObjectAdd.MissingRequired`.**
   Nenhum teste pega isso porque todos mockam o GI
   (`apps/sidecar/tests/test_admin_znuny_router.py:364`,
   `apps/admin/test/znuny-object.test.ts`). Isto é um **bug já existente**, não só
   um gap de requisito — e cai em cima do R10 também.

3. **Invariante "entrou pelo suporte, sai pelo suporte" — é NATIVA no Znuny, com
   uma ressalva importante.** O remetente de saída é derivado do
   `system_address_id` **da fila do ticket**, não do endereço pelo qual o e-mail
   entrou: `/opt/otrs/Kernel/System/Queue.pm:104-132` (`GetSystemAddress`,
   `SELECT sa.value0, sa.value1 FROM system_address sa, queue sq WHERE sq.id = ?`),
   consumido por `/opt/otrs/Kernel/System/TemplateGenerator.pm:308-310` (resposta do
   agente), `/opt/otrs/Kernel/System/TemplateGenerator.pm:836-838` (auto-resposta),
   `/opt/otrs/Kernel/System/Ticket/Event/NotificationEvent/Transport/Email.pm:272`,
   `/opt/otrs/Kernel/System/ProcessManagement/TransitionAction/ArticleSend.pm:417`.
   Do lado da entrada, `MailAccountAdd/Update` aceitam
   `DispatchingBy => 'Queue'|'From'` + `QueueID`
   (`/opt/otrs/Kernel/System/MailAccount.pm:63-72`, `:417`); com `'From'`, o
   roteamento usa `SystemAddressQueueID` (`/opt/otrs/Kernel/System/SystemAddress.pm:378`).
   → **Configurado corretamente, o invariante é automático. Mas a granularidade é
   FILA, não "endereço de entrada": se um ticket é movido de fila, a próxima
   resposta sai por outro endereço.** Isso não é bug — é o desenho do Znuny — e o
   Kleber precisa saber, porque o fluxo dele (N1 classifica e **move** o ticket da
   fila padrão para solicitação/incidente) atravessa exatamente esse caso.
4. **Remetente específico por cliente — AUSENTE e não-nativo.** Não existe
   `SystemAddress` por `CustomerID` em lugar nenhum do Znuny: o `From` só sai de
   fila (evidência do item 3) ou de auto-resposta
   (`/opt/otrs/Kernel/System/TemplateGenerator.pm:825-832`, que lê
   `AutoResponse.SystemAddressID`). Para atender literalmente, ou se cria **uma
   fila dedicada por cliente especial** (nativo, sem código), ou se escreve um
   override de saída (não-nativo, mexe no caminho de envio).

5. **Domínios autorizados por cliente + visão centralizada — AUSENTE.**
   `CustomerCompany` do Znuny não tem campo de domínio (o `CustomerCompanyAdd.pm`
   custom grava só `CustomerID`/`CustomerCompanyName` — `znuny/Custom/Kernel/
   GenericInterface/Operation/CustomerCompany/CustomerCompanyAdd.pm:61-62,88`). O
   equivalente nativo é um **PostMaster Filter** casando `From` por regex de
   domínio e setando `X-OTRS-CustomerNo`:
   `/opt/otrs/Kernel/System/PostMaster/Filter.pm:106` (`FilterAdd`), `:56`
   (`FilterList`), `:191` (`FilterGet`), `:156` (`FilterDelete`). Zero ocorrências
   de `PostMaster` em `apps/` (grep).

6. **A infra de e-mail de SAÍDA está quebrada hoje — achado independente do
   requisito.** O default do Znuny é `SendmailModule =
   Kernel::System::Email::Sendmail` com `/usr/sbin/sendmail`
   (`/opt/otrs/Kernel/Config/Defaults.pm:387-388`), e **não existe MTA na imagem**
   (`docker run --rm --entrypoint sh ground-control/znuny:7.2.3 -c "ls -l
   /usr/sbin/sendmail"` → `No such file or directory`; nenhum postfix/exim/msmtp na
   lista de pacotes de `znuny/Dockerfile:27-60`). O `Config.pm.tmpl` também não
   configura SMTP (grep `SendmailModule` → nada;
   `znuny/Config.pm.tmpl:34` só define `AdminEmail`).
   A **entrada**, ao contrário, está pronta: a tarefa de cron do Daemon
   `MailAccountFetch` vem `Valid="1"`, `*/10 * * * *`
   (`/opt/otrs/Kernel/Config/Files/XML/Daemon.xml:327-343`) e o `znuny-daemon` roda
   (`znuny/entrypoint.sh:211-219`, `docker-compose.yml:132-135`). Ou seja: hoje
   **entraria** e-mail se houvesse conta cadastrada, e **não sairia** nada.

**Gap (comportamento observável que falta):**
- Não existe nenhuma tela nem endpoint para cadastrar conta de recebimento,
  endereço de sistema ou filtro de PostMaster; toda essa configuração só é possível
  pelo painel nativo do Znuny.
- Criar fila pelo console falha (não há como informar `SystemAddressID`).
- O Znuny não envia e-mail nenhum (sem MTA/SMTP configurado).
- Não existe visão centralizada de "domínio → cliente".
- Não existe remetente por cliente.

**Tarefas:**

- **T-R9.1 — Configurar o transporte de saída (SMTP) do Znuny, sem MTA local.**
  Camada: znuny (infra/config). Arquivos: `znuny/Config.pm.tmpl` (adicionar
  `SendmailModule = Kernel::System::Email::SMTPS|SMTPTLS`, `::Host`, `::Port`,
  `::AuthUser`, `::AuthPassword` a partir de env), `znuny/entrypoint.sh`
  (substituição idempotente dos placeholders, mesmo padrão de `__FQDN__`),
  `docker-compose.yml` (env `ZNUNY_SMTP_*`), `.env.example`, `.ia/OPS.md`.
  **Pronto quando:** `bin/otrs.Console.pl Maint::Email::...` / um ticket com
  resposta ao cliente sai de fato para uma caixa de teste, e o log do Znuny não
  registra `Can't send email`. Segredo de SMTP só em `.env.prod` (gitignored).

- **T-R9.2 — Estender a allowlist com `SystemAddress` e expor as listas de apoio
  que faltam à fila.** Camada: znuny GI. Arquivos:
  `znuny/Custom/.../GertiAdmin/AdminSpec.pm` (nova chave `SystemAddress`:
  `Module => 'Kernel::System::SystemAddress'`, `ListMethod/GetMethod/AddMethod/
  UpdateMethod = SystemAddressList/Get/Add/Update`, `GetIDParam/GetIDField/
  UpdateIDParam = ID`, `Fields => [qw(Name Realname Comment ValidID QueueID)]`,
  `RequiredOnAdd => [qw(Name Realname ValidID QueueID)]` — assinatura conferida em
  `/opt/otrs/Kernel/System/SystemAddress.pm:68-77` e `:217-228`);
  `AdminObjectList.pm:87-99` (acrescentar `SystemAddressList`, `SalutationList`,
  `SignatureList` às listas de apoio). Sem `COPY` novo no Dockerfile (não há `.pm`
  novo) — **mas o rebuild da imagem é obrigatório**, pois o overlay copia arquivo a
  arquivo (`znuny/Dockerfile:161-171`).
  **Pronto quando:** `GET /v1/admin/znuny/objects/SystemAddress` devolve os
  endereços reais da instância e `GET /objects/Queue` traz `SystemAddressList`
  não-vazia no bloco `support`.
  *Nota D21:* nada é persistido — é leitura/escrita ao vivo, exatamente como
  Queue/SLA.

- **T-R9.3 — Corrigir o bug de criação de fila (campos obrigatórios ausentes).**
  Camada: admin. Arquivos: `apps/admin/composables/useZnunyObject.ts:131-142,
  214-229` (adicionar `SystemAddressID`, `SalutationID`, `SignatureID`,
  `FollowUpID` ao `QueueDraft`/payload e à validação),
  `apps/admin/pages/znuny/filas.vue` (três selects novos alimentados pelo `support`
  da T-R9.2). **Este é o campo onde o Kleber amarra o endereço de resposta da
  fila** — atende diretamente "na fila de suporte usa esse".
  **Pronto quando:** criar uma fila pelo console retorna 201 e a fila aparece no
  Znuny com o endereço de sistema escolhido.

- **T-R9.4 — Operação GI dedicada para contas de recebimento (`MailAccount`), com
  o segredo blindado.** Camada: znuny GI. Arquivos novos:
  `znuny/Custom/.../GertiAdmin/AdminMailAccountList.pm`, `AdminMailAccountGet.pm`,
  `AdminMailAccountSet.pm` (Add+Update numa op, como `AdminAgentSet`).
  **Não usar as ops genéricas** por dois motivos duros, ambos verificados no fonte:
  (a) `MailAccountGet` devolve a **senha em texto claro** (`/opt/otrs/Kernel/System/
  MailAccount.pm:344`, `Password => $Data[1]` sobre a coluna `pw`) — a resposta GI
  precisa **remover** `Password`, mesma guarda do Bloco C para `UserPw`
  (`.ia/ARCHITECTURE.md:672-675`); (b) `MailAccountUpdate` **exige** `Password`
  não-vazio (`/opt/otrs/Kernel/System/MailAccount.pm:417`), então "salvar sem
  trocar a senha" só é possível se a própria op Perl reler a senha atual e
  reenviá-la — **dentro do Znuny, nunca pela rede**.
  Também obrigatório: `znuny/webservices/GertiAdmin.yml` (3 `Operation` +
  3 `Route`, seguindo `:20-65` e `:86-146`), `znuny/Dockerfile` (**3 linhas `COPY`
  + 3 nomes no loop `perl -c` de `:205-231`** — o overlay não usa wildcard),
  redeploy com `Admin::WebService::Update --webservice-id 2 --source-path
  /opt/otrs/webservices/GertiAdmin.yml`.
  **Pronto quando:** `perl -c` verde no build para os 3 módulos e
  `GET /v1/admin/znuny/mail-accounts` devolve as contas **sem nenhum campo de
  senha**.

- **T-R9.5 — Operação GI para filtros de PostMaster (domínio → cliente/fila).**
  Camada: znuny GI. Arquivos novos: `AdminPostMasterFilterList.pm`,
  `AdminPostMasterFilterGet.pm`, `AdminPostMasterFilterSet.pm` (+ YAML + Dockerfile
  + `perl -c`, idem T-R9.4). Não cabe nas ops genéricas: a API é por **nome**, não
  por id numérico, e **não existe `FilterUpdate`** — só `FilterAdd`/`FilterDelete`
  (`/opt/otrs/Kernel/System/PostMaster/Filter.pm:56,106,156,191`). A op `Set` faz
  `FilterDelete` + `FilterAdd` sob o mesmo nome, e a `Set` deve **recusar** nome
  inexistente em modo update para não criar filtro por engano.
  **Pronto quando:** criar um filtro `Match: From =~ @cliente\.com\.br` →
  `Set: X-OTRS-CustomerNo = CLIENTE` pelo console faz um e-mail daquele domínio
  cair como ticket do cliente certo, validado contra o Znuny real.

- **T-R9.6 — Sidecar: rotas de e-mail sob `get_admin_session`.** Camada: sidecar.
  Arquivos: `apps/sidecar/src/gerti_sidecar/integrations/znuny_admin_mail.py`
  (novo), `routers/admin_znuny_mail.py` (novo),
  `routers/admin_znuny.py:40` (`_ALLOWED_OBJECTS` += `SystemAddress`),
  `main.py` (registrar router). Rotas: `/v1/admin/znuny/mail-accounts[/{id}]`,
  `/v1/admin/znuny/postmaster-filters[/{name}]`. Reaproveitar `_call`/`_call_get` e
  o mapeamento de erro de `admin_znuny.py:57-81` (503 indisponível, 422 recusa
  limpa em escrita, 404 em leitura). Auditar via `audit_service.record` com
  `metadata` **sem senha**.
  **Pronto quando:** os endpoints respondem 401 sem `gsid_adm` e o `audit_log`
  registra o ato sem nenhum segredo.

- **T-R9.7 — Tela `/znuny/email` (3 abas: Contas de recebimento · Endereços de
  resposta · Domínios autorizados).** Camada: admin. Arquivos:
  `apps/admin/pages/znuny/email.vue` (nova),
  `apps/admin/composables/useMailConfig.ts` (nova, lógica pura),
  `apps/admin/server/api/admin/znuny/**` (proxies com guard de path-injection, no
  padrão dos existentes), nav. A aba "Domínios autorizados" é literalmente a **visão
  centralizada** que o Kleber pediu: lista de todos os filtros de PostMaster que
  casam por domínio, com a coluna "cliente". Senha da conta: campo write-only com
  placeholder "•••• (mantida)" e envio de `Password` apenas quando digitado.
  **Pronto quando:** as 3 abas listam dado real da instância e a aba de endereços
  mostra, por fila, qual endereço sai — o par entrada/saída visível numa tela só.

- **T-R9.8 — Decisão + implementação de "remetente por cliente".** Camada:
  decisão de produto (depois znuny GI ou admin). Ver "Risco/decisão aberta".

**Testes de validação:**

- **V-R9.1** — `perl -c` (gate de build). Alvo: loop de `znuny/Dockerfile:205-231`.
  ASSERT: `docker compose --env-file .env --profile gerti build znuny-web` conclui
  com `syntax OK` para `AdminMailAccountList/Get/Set.pm` e
  `AdminPostMasterFilterList/Get/Set.pm`; remover uma linha `COPY` faz o build
  **falhar** (prova de que o gate cobre os módulos novos).
- **V-R9.2** — pytest. Alvo:
  `apps/sidecar/tests/test_admin_znuny_mail_router.py` (novo). ASSERT: GI mockado
  devolvendo `{"MailAccounts":[{"ID":1,"Login":"suporte","Password":"s3cr3t"}]}` →
  a resposta HTTP **não contém a string `s3cr3t` nem a chave `Password`** em
  nenhum nível do JSON (asserção sobre o corpo serializado, não sobre o dict).
- **V-R9.3** — pytest. Alvo: `tests/test_gi_routes_match_webservice.py` (já existe;
  estender). ASSERT: toda rota nova usada por `znuny_admin_mail.py` aparece no
  `RouteOperationMapping` de `znuny/webservices/GertiAdmin.yml` e vice-versa
  (bidirecional — foi exatamente esse teste que pegou o bug de rota das classes de
  CI, `.ia/OPS.md:1330-1334`).
- **V-R9.4** — vitest. Alvo: `apps/admin/test/znuny-object.test.ts`. ASSERT:
  `buildQueuePayload(draft)` com `SystemAddressID='3'`, `SalutationID='1'`,
  `SignatureID='1'`, `FollowUpID='1'` produz payload contendo **os quatro** campos
  como número; e `validateQueueDraft` com `SystemAddressID: ''` retorna erro
  (regressão do bug de criação de fila).
- **V-R9.5** — manual contra o Znuny real (staging), roteiro em
  `docs/COMO-TESTAR-ADMIN-ZNUNY.md`. ASSERT (invariante do Kleber, ponta a ponta):
  cria `SystemAddress` `suporte@gerti…` ligado à fila `Suporte` e
  `dpo@gerti…` ligado à fila `DPO`; envia e-mail para cada um; verifica que o
  ticket cai na fila certa; responde pelo `/atendimento`; **confere no cabeçalho
  `From:` da mensagem recebida na caixa de teste que suporte→suporte e DPO→DPO**.
  Depois **move** o ticket de Suporte para DPO, responde de novo e registra que o
  `From:` mudou — comportamento nativo, precisa ser aceito ou tratado.
- **V-R9.6** — manual contra o Znuny real. ASSERT: e-mail vindo de
  `alguem@dominioteste.com.br` (endereço nunca cadastrado) vira ticket com
  `CustomerID` = o cliente configurado no filtro de PostMaster, e o filtro aparece
  na aba "Domínios autorizados" do console.

**Risco/decisão aberta:**
1. **Senha de conta de e-mail em claro no banco do Znuny** (coluna `mail_account.pw`,
   `/opt/otrs/Kernel/System/MailAccount.pm:344`). É do produto, não nosso — mas ao
   expor essa configuração pelo console **assumimos** esse risco. Mitigação
   proposta: nunca trafegar a senha na resposta e preferir contas OAuth2 quando o
   provedor permitir (`AuthenticationType => 'oauth2_token'`,
   `/opt/otrs/Kernel/System/MailAccount.pm:69-70`). **Decisão pendente:** expor ou
   não o cadastro de senha pelo console, ou deixar essa etapa no painel nativo.
2. **PostMaster Filter não tem `ValidID`** — a única remoção possível é
   `FilterDelete` (DELETE real). Isso **colide frontalmente** com a regra "sem
   exclusão" do D21. Opções: (a) aceitar exclusão real só para este objeto,
   documentando a exceção no D21 e exigindo dupla confirmação + auditoria do estado
   anterior completo no `metadata`; (b) convenção de nome (`zz-inativo-…`) que o
   PostMaster ainda avalia — **não serve**, o filtro continuaria ativo. Recomendo
   (a), com o `FilterGet` completo gravado no `audit_log` antes do delete.
3. **Remetente por cliente** ("volta o e-mail por ele também"): não é nativo.
   Caminho barato e 100% nativo = **uma fila por cliente especial**, com o
   `SystemAddress` dele — resolve o pedido sem uma linha de código, ao custo de
   proliferar filas. Caminho caro = override do `From` no envio, que exige tocar o
   caminho de saída do Znuny (contra a invariante mãe se feito por patch; possível
   por `Ticket::DefineEmailFrom` só para o *realname*, não para o endereço).
   **Levar as duas opções ao Kleber antes de estimar.**
4. **Movimentação de fila muda o remetente.** O fluxo declarado por ele (fila padrão
   → N1 classifica → move) faz o invariante dele valer "por fila atual", não "por
   porta de entrada". Precisa ser validado com ele explicitamente.

---

## R10 — Mesas de serviço (= filas)

**Pedido (citação curta do Kleber):**
> "Mesas de serviço, que são as filas. Então, fila do suporte, fila de solicitação,
> fila de requisição, fila do DPO, fila para assuntos administrativos. **O OTRS
> aqui trata como mesa, mas no Znuny é tratado como fila.**" / "Pode associar quais
> técnicos vão atender cada fila. Tem toda uma estratégia de permissionamento lá."
> (`docs/transcricoes/…:125-127`, `:63-65`)

**Estado atual:** **PARCIAL** — listar/editar/invalidar funciona; **criar não**.

- Chave `Queue` na allowlist com 14 campos:
  `znuny/Custom/.../GertiAdmin/AdminSpec.pm:51-68`.
- Ops genéricas: `AdminObjectList/Get/Add/Update.pm`; rotas
  `/AdminObject/{List,Get,Add,Update}` em `znuny/webservices/GertiAdmin.yml:94-108`.
- Sidecar: `apps/sidecar/src/gerti_sidecar/routers/admin_znuny.py:93-167`
  (GET lista, GET item, POST, PUT) com allowlist redundante em `:40`.
- Tela: `apps/admin/pages/znuny/filas.vue` (316 linhas), com invalidação
  `ValidID=2` e nunca exclusão (`useZnunyObject.ts:231-235`).
- Verificado ao vivo em staging: `GET /objects/Queue` devolveu as filas reais
  (`.ia/OPS.md:1296-1300`).
- **Quebra:** criar fila é impossível — ver R9 item 2 (`AdminSpec.pm:67` exige
  `SystemAddressID`/`SalutationID`/`SignatureID`; `useZnunyObject.ts:131-142,214-229`
  não os envia; guard em `AdminObjectAdd.pm:95-100`).
- "Quais técnicos atendem cada fila": indireto e **funcional** — a fila aponta para
  um grupo (`AdminSpec.pm:62`, `GroupID`) e a associação agente↔grupo existe
  (`AdminAgentGroupSet.pm`, rota `/Agent/Group/Set` em `GertiAdmin.yml:142`, tela
  `apps/admin/pages/znuny/agentes.vue`). O que falta é **legibilidade**: em lugar
  nenhum se lê "quem atende a fila X".
- Terminologia: as telas dizem "fila" — alinhado com a tradução que o próprio
  Kleber fez.

**Gap:** criar fila pelo console retorna erro sempre; e não existe uma visão
"fila → grupo → agentes que atendem".

**Tarefas:**

- **T-R10.1 — (= T-R9.2 + T-R9.3)** Destravar a criação de fila expondo
  `SystemAddress`/`Salutation`/`Signature`. **É a mesma tarefa**, listada aqui
  porque o requisito R10 depende dela. Não duplicar esforço.
- **T-R10.2 — Coluna "Quem atende" na lista de filas.** Camada: admin (+ sidecar,
  só composição). Arquivos: `apps/admin/pages/znuny/filas.vue`,
  `apps/admin/composables/useZnunyObject.ts`. Compõe **em memória, no request**,
  `Queue.GroupID` × `AdminGroupList` × `AdminAgentList` (todas já existem:
  `GertiAdmin.yml:122,138`). **Justificativa D21:** nada é gravado nem cacheado — é
  um join de leitura por request; se o dado mudar no Znuny, a próxima carga já
  reflete.
  **Pronto quando:** a lista mostra, por fila, o grupo e a contagem/nomes dos
  agentes com permissão `rw` nele.
- **T-R10.3 — Rótulo bilíngue "Filas (mesas de serviço)" no menu e no título.**
  Camada: admin. Arquivos: `apps/admin/pages/znuny/filas.vue`, layout/nav. Custo
  quase zero, remove atrito de vocabulário na demo.

**Testes de validação:**
- **V-R10.1** — vitest. Alvo: `apps/admin/test/znuny-object.test.ts`. ASSERT: igual
  ao V-R9.4 (payload de fila completo / validação rejeita `SystemAddressID` vazio).
- **V-R10.2** — pytest. Alvo: `apps/sidecar/tests/test_admin_znuny_router.py`.
  ASSERT: GI mockado devolvendo `MissingRequired` numa criação → o router responde
  **422 com a mensagem original do Znuny** (não um 500 nem uma mensagem genérica) —
  contrato de `admin_znuny.py:57-64`.
- **V-R10.3** — manual contra o Znuny real. ASSERT: criar a fila `DPO` pelo console,
  com grupo `dpo` e endereço `dpo@…`; ela aparece em `AgentTicketQueue` no Znuny
  nativo e um agente fora do grupo `dpo` **não** a enxerga.
- **V-R10.4** — vitest. Alvo: `apps/admin/test/znuny-queue-staff.test.ts` (novo).
  ASSERT: função pura `staffForQueue(queue, groups, agents)` com fila
  `GroupID=3` e dois agentes (um em `3` com `rw`, um em `4`) retorna **apenas** o
  primeiro.

**Risco/decisão aberta:** nenhum de arquitetura. Só confirmar com o Kleber se a
"estratégia de permissionamento" dele precisa de granularidade além de grupo
(`ro`/`rw`/`move_into`/`create`/`note`/`owner`/`priority`) — hoje a tela de agentes
expõe grupos, e se ele precisar dos 7 níveis do Znuny por grupo isso é escopo extra
(cabe em T-R10.2 estendida).

---

## R11 — Atividades agendadas / tickets recorrentes

**Pedido (citação curta do Kleber):**
> "Atividades agendadas. Então, tickets recorrentes. […] verificação de backup,
> verificação de pets [patches], vulnerabilidades, atualização de servidor. […] que
> acontecem uma vez, que acontecem toda semana, que acontecem todo mês. Então, é
> uma agenda. E a gente pode programar recorrência. **Isso é importante também,
> porque é o dia a dia dos técnicos.**"
> (`docs/transcricoes/…:110-118`)

**Estado atual:** **AUSENTE** — e o mecanismo nativo candidato **não serve**.

- Zero ocorrências de recorrência/agendamento de ticket em `apps/` (grep por
  `recorren|recurring|agendad|schedule` só bate em feriado recorrente do calendário,
  `apps/admin/composables/useWorkingHours.ts:195-507`).
- **Avaliação do `GenericAgent` do Znuny (pedida no método) — veredito: NÃO SERVE
  para tarefa recorrente que *cria* ticket.** Três razões, todas verificadas no
  fonte:
  1. **GenericAgent não cria ticket.** Ele **busca** tickets e aplica ações neles
     (`/opt/otrs/Kernel/System/GenericAgent.pm:179` `JobRun`, `:926`
     `_JobRunTicket`). Não existe ação "criar ticket"; o único escape é
     `New->{Module}` (`:1389-1434`), execução de módulo Perl arbitrário **por
     ticket encontrado** e gateada por config — o que é exatamente o oposto do que
     precisamos, além de ser um vetor de execução de código.
  2. **A recorrência "todo mês" não é expressável.** O mapa de agendamento tem só
     `ScheduleDays` (dia da semana), `ScheduleHours`, `ScheduleMinutes`
     (`/opt/otrs/Kernel/System/GenericAgent.pm:112-118`) — **não há dia do mês**.
     "Uma vez" também não existe (não há job de disparo único auto-desativante).
  3. **Não há update, e a chave é o nome.** `JobAdd` **recusa** nome existente
     (`/opt/otrs/Kernel/System/GenericAgent.pm:766-773`) e a única remoção é
     `JobDelete` (`:830`) — DELETE real, sem `ValidID`. Editar = apagar e recriar,
     o mesmo conflito com "sem exclusão" do PostMaster Filter.
  → **Conclusão: implementar no nosso worker**, não no GenericAgent. Precedente
  direto: o motor de automação #1Q já foi decidido como próprio, não GenericAgent
  (`docs/superpowers/plans/2026-06-09-1q-automation.md:5,149`).
- **O que já existe e serve de base:** o `sidecar-worker` tem loop asyncio com
  passo diário idempotente e heartbeat
  (`apps/sidecar/src/gerti_sidecar/jobs/worker.py:37-72`, padrão
  `state.last_close_date != day`); a criação de ticket via GI já existe
  (`znuny/Custom/.../GertiTicket/TicketCreate.pm`, rota em
  `znuny/webservices/GertiTicket.yml`); e há motor de regras com RLS por tenant
  (`apps/sidecar/src/gerti_sidecar/domain/automation_service.py`,
  `models/automation.py`).

**Gap:** não existe agenda de atividade recorrente; não existe ticket criado
automaticamente; o técnico não tem a "agenda do dia a dia".

**Tarefas:**

- **T-R11.1 — Modelo `gerti.recurring_task` + `recurring_task_run` (migration com
  FORCE RLS).** Camada: sidecar. Arquivos:
  `apps/sidecar/src/gerti_sidecar/models/recurring_task.py` (novo),
  `apps/sidecar/migrations/versions/00XX_recurring_task.py` (novo),
  `models/__init__.py`. Campos: `tenant_id`, `name`, `frequency`
  (`once|weekly|monthly` — enum fechado, espelha as três opções do Kleber),
  `weekday`, `day_of_month`, `run_at_time`, `timezone`, `znuny_queue`,
  `znuny_service`, `znuny_type`, `priority`, `owner_login`, `title_template`,
  `body_template`, `active`, `next_run_at`, `last_run_at`.
  **Justificativa D21 (obrigatória):** isto **não é configuração do Znuny** — o
  Znuny não tem objeto "tarefa recorrente" (provado acima: `GenericAgent` não cria
  ticket e não sabe "mensal"). Não há fonte de verdade no Znuny para duplicar. O
  artefato que o Znuny possui — o **ticket gerado** — continua sendo criado e
  armazenado **só nele**, via GI. A tabela guarda a *regra*, do mesmo jeito que
  `automation_rule` (#1Q) guarda a regra da automação sem duplicar ticket.
  `recurring_task_run` existe para **idempotência** (chave única
  `(task_id, scheduled_for)`), não como cópia: sem ela, um restart do worker
  duplica o chamado do técnico.
  **Pronto quando:** migration aplica, RLS `FORCE` verificada por teste com o papel
  `gerti_sidecar` (sem BYPASSRLS), e `REVOKE` explícito onde aplicável (regra D20.1,
  `.ia/DECISIONS.md:532-551`).

- **T-R11.2 — `domain/recurring_task_service.py`: cálculo puro de `next_run_at` +
  materialização idempotente.** Camada: sidecar. Arquivos: novo módulo + testes.
  Regras: `once` desativa após o disparo; `weekly` avança 7 dias; `monthly`
  **clampa** dia 29/30/31 para o último dia do mês (fevereiro é o caso que quebra
  implementações ingênuas). Todo cálculo em função pura, sem I/O.
  **Pronto quando:** a função de próxima ocorrência é 100% testável sem banco.

- **T-R11.3 — Passo no worker: materializar as tarefas vencidas em tickets do
  Znuny.** Camada: sidecar. Arquivos:
  `apps/sidecar/src/gerti_sidecar/jobs/worker.py:37-72` (novo passo no `tick`, no
  mesmo padrão failure-soft dos existentes),
  `apps/sidecar/src/gerti_sidecar/integrations/znuny_ticket.py` (reuso de
  `TicketCreate`), `domain/worker_heartbeat.py` (novo `WORKER_RECURRING` ou reuso).
  Falha de uma tarefa **não** pode impedir as outras (mesmo contrato de
  `worker.py:41-66`).
  **Pronto quando:** subir o worker duas vezes no mesmo dia gera **um** ticket por
  tarefa, não dois.

- **T-R11.4 — CRUD `/v1/admin/tenants/{id}/recurring-tasks` + tela
  `/znuny/atividades` (ou `/atividades`).** Camada: sidecar + admin. Arquivos:
  `routers/admin_recurring.py` (novo, sob `get_admin_session`, padrão de
  `routers/admin_catalog.py:1-27`), `apps/admin/pages/atividades/index.vue`,
  `apps/admin/composables/useRecurringTask.ts` (lógica pura),
  proxies em `apps/admin/server/api/admin/`.
  **Pronto quando:** o administrador cria "Verificação de backup — toda segunda,
  08:00, fila Preventivos" pela tela e vê a próxima ocorrência calculada.

- **T-R11.5 — Visão "agenda" para o técnico.** Camada: admin. Arquivo:
  `apps/admin/pages/atividades/index.vue` (aba calendário/próximos 30 dias) e link
  do ticket gerado para `/atendimento/[id]`. É o que o Kleber chamou de "é uma
  agenda… é o dia a dia dos técnicos" — sem isso o requisito fica só como
  automação invisível.

**Testes de validação:**
- **V-R11.1** — pytest. Alvo: `apps/sidecar/tests/test_recurring_task_service.py`
  (novo). ASSERT: `next_run(frequency='monthly', day_of_month=31, from=2026-01-31)`
  → `2026-02-28`; `from=2026-02-28` → `2026-03-31`. E
  `next_run(frequency='once', …)` após disparo → `None` + `active=False`.
- **V-R11.2** — pytest. Alvo: `apps/sidecar/tests/test_recurring_worker.py` (novo).
  ASSERT: com GI mockado, rodar `tick()` **duas vezes** no mesmo dia para uma
  tarefa vencida chama `TicketCreate` **exatamente uma vez**, e a segunda execução
  não levanta exceção (idempotência por `(task_id, scheduled_for)`).
- **V-R11.3** — pytest. Alvo: `apps/sidecar/tests/test_rls_recurring_task.py`
  (novo). ASSERT: sob o papel `gerti_sidecar` com `app.current_tenant` = tenant A,
  `SELECT` na `recurring_task` **não retorna** linha do tenant B (zero linhas, e
  `INSERT` para B é rejeitado) — mesmo padrão de `test_rls_isolation.py`.
- **V-R11.4** — vitest. Alvo: `apps/admin/test/recurring-task.test.ts` (novo).
  ASSERT: `validateRecurringDraft({frequency:'monthly', day_of_month: 0})` retorna
  erro; `{frequency:'weekly', weekday: undefined}` retorna erro; `describeSchedule`
  de `weekly/segunda/08:00` devolve "Toda segunda-feira às 08:00".
- **V-R11.5** — manual contra o Znuny real. ASSERT: criar tarefa "Verificação de
  backup" com horário 2 minutos à frente; após o tick, o ticket existe no Znuny na
  fila e serviço corretos, com o `CustomerID` do tenant, e aparece no `/atendimento`.

**Risco/decisão aberta:**
1. **Quem é o "cliente" do ticket recorrente?** Atividade interna de manutenção
   (verificar backup do cliente X) precisa de `CustomerID` para o anti-IDOR e para
   o billing (`gerti.ticket_contract_link`). **Decisão:** a tarefa recorrente é
   por tenant (já é, pela RLS) e opcionalmente vinculada a um contrato — precisa de
   confirmação do Kleber se essas atividades **consomem horas do contrato** ou não.
   Isso muda o modelo (`contract_id` nullable ou não).
2. **Fuso horário.** O worker roda em UTC (`worker.py:38`,
   `dt.datetime.now(dt.UTC)`); "toda segunda 08:00" é 08:00 de quem? Guardar
   `timezone` por tarefa e converter — senão a agenda escorrega no horário de verão.
3. **Volume.** 43 contratos ativos × várias atividades = pico diário de criação de
   tickets via GI. Definir um teto por tick e um backoff, para não estourar o Znuny
   às 08:00 de segunda.

---

## R12 — Catálogo de serviço (dois níveis: item e sub-item)

**Pedido (citação curta do Kleber):**
> "Aí tem catálogo de serviço, que a gente pode configurar aqui. O que eu vou ter no
> tipo de solicitação? Aí tem aqui acesso à identidade, comunicação e colaboração,
> backup e recuperação de dados. **Aqui a gente cadastra o item e o sub-item. Aqui
> só dá dois níveis.**"
> (`docs/transcricoes/…:119-124`)

**Estado atual:** **PARCIAL — e com um problema estrutural: existem DOIS catálogos
paralelos, ligados por string.**

Catálogo A — **`Service` do Znuny** (o que o Kleber chama de "tipo de solicitação"):
- Na allowlist com `ParentID`: `znuny/Custom/.../GertiAdmin/AdminSpec.pm:94-108`
  (`Fields => [qw(Name ParentID Comment ValidID TypeID Criticality)]`).
- Tela com árvore e guarda anti-ciclo: `apps/admin/pages/znuny/servicos.vue`,
  lógica pura em `apps/admin/composables/useServiceTree.ts:68-89` (`buildServiceTree`),
  `:124-139` (`invalidParentIds`/`parentOptions`), `:48-52` (`leafName`, o Znuny
  nomeia com o caminho `Pai::Filho`).
- **Profundidade é ILIMITADA** — `build(row.id, depth + 1, …)` em
  `useServiceTree.ts:83` não tem teto, e a validação
  (`useServiceTree.ts:168-175`) só proíbe `::` no nome, nunca o nível 3.
  O Kleber disse "só dá dois níveis" — hoje a tela permite neto, bisneto, etc.
- É o catálogo que o portal realmente usa no formulário de chamado:
  `znuny/Custom/.../GertiTicket/FormMeta.pm:35-42`
  (`CustomerUserServiceMemberList`) → `apps/portal/pages/tickets/novo.vue:97`.

Catálogo B — **`gerti.catalog_item`** (a vitrine do portal, Spec #3 V2):
- `apps/sidecar/src/gerti_sidecar/models/catalog_item.py:49-87`. **Não tem
  `parent_id`**; a hierarquia é emulada por um campo `category` **texto livre**
  (`:70`, `String`, sem FK e sem tabela de categorias), validado só por tamanho
  (`apps/sidecar/src/gerti_sidecar/routers/admin_catalog.py:32`, 2..60 chars;
  `apps/admin/composables/useCatalogItem.ts:107-108`).
- Ligação com o catálogo A: campo **texto** `znuny_service`
  (`models/catalog_item.py:75`), resolvido por **match case-insensitive de string**
  em `apps/portal/components/ticket/catalog-prefill.ts:36-38` (`matchMetaKey`) — se
  o serviço for renomeado no Znuny, o vínculo **quebra em silêncio** (a função
  retorna `undefined` e o select fica sem seleção, `:31-34`).
- Divergência já documentada no próprio código: o item de catálogo tem
  `znuny_queue` mas **não existe campo de fila** na criação de chamado, então a
  fila é exibida como texto informativo (`catalog-prefill.ts:1-12`).

Ou seja: `category` + `name` de `catalog_item` **é** dois níveis na prática, mas
como texto livre sem integridade; e `Service` **é** hierárquico de verdade, mas
sem o teto de dois níveis e sem vínculo forte com a vitrine.

**Gap:**
- Não há restrição de dois níveis em lugar nenhum.
- Duas fontes de "catálogo" que podem divergir, amarradas por string frágil.
- Não existe uma tela onde o administrador veja "item → sub-item" como o Kleber
  desenhou.

**Tarefas:**

- **T-R12.1 — DECISÃO ANTES DE CÓDIGO: o `Service` do Znuny é a fonte de verdade
  do catálogo; `catalog_item` vira apresentação.** Camada: decisão (ADR novo).
  Arquivo: `.ia/DECISIONS.md` (ADR D23). Fundamento: é o `Service` que o Znuny usa
  para SLA (`AdminSpec.pm:89`, `ServiceIDs` no SLA), para o formulário
  (`FormMeta.pm:37`) e para relatório; manter a taxonomia em `catalog_item` cria a
  segunda fonte de verdade que o D21 combate. `catalog_item` continua existindo
  para o que **não é** taxonomia (ícone, descrição comercial, ordem, SLA
  informativo, ativo/inativo na vitrine) — isso não é config do Znuny, é
  merchandising do portal.
  **Pronto quando:** ADR escrito e aprovado.

- **T-R12.2 — Trocar `catalog_item.znuny_service` (texto) por
  `znuny_service_id` (inteiro, id do Service).** Camada: sidecar. Arquivos:
  `models/catalog_item.py:75`, migration nova (backfill por nome, mantendo a coluna
  antiga um ciclo), `routers/admin_catalog.py:37`,
  `apps/portal/components/ticket/catalog-prefill.ts:36-38`,
  `apps/admin/composables/useCatalogItem.ts`.
  **Justificativa D21:** guardar o **id** não é cache de config — é uma
  referência, exatamente como `gerti.ticket_contract_link` guarda o número do
  ticket sem duplicar o ticket. O nome, a validade e a hierarquia continuam sendo
  lidos ao vivo do Znuny.
  **Pronto quando:** renomear o serviço no Znuny **não** quebra o
  pré-preenchimento do portal.

- **T-R12.3 — Impor o teto de dois níveis no `Service`.** Camada: znuny GI +
  admin. Arquivos: `znuny/Custom/.../GertiAdmin/AdminSpec.pm` (novo campo de spec
  `MaxDepth => 2` para `Service`) e `AdminObjectAdd.pm`/`AdminObjectUpdate.pm`
  (guard: se o pai escolhido já tem pai, erro explícito
  `AdminObject*.DepthExceeded` — nunca descarte silencioso, mesma filosofia de
  `AdminSpec.pm:9-13`); `apps/admin/composables/useServiceTree.ts:132-139`
  (`parentOptions` só oferece serviços de nível 0) e `:168-175` (validação).
  Rebuild da imagem obrigatório (overlay arquivo a arquivo,
  `znuny/Dockerfile:161-171`) — sem `COPY` novo, sem entrada nova no `perl -c`.
  **Pronto quando:** tentar criar um "neto" retorna 422 com mensagem clara, tanto
  pela tela quanto por chamada direta ao GI.
  *Ressalva:* se já existirem serviços de 3+ níveis na instância, a guarda deve
  bloquear **criação/edição**, não invalidar o que existe.

- **T-R12.4 — Renomear a UI para o vocabulário do Kleber.** Camada: admin.
  Arquivos: `apps/admin/pages/znuny/servicos.vue` ("Catálogo de serviço", colunas
  "Item" / "Sub-item" em vez de árvore genérica); `apps/admin/pages/clientes/[id]/
  catalogo.vue` (deixar explícito que é a *vitrine do portal*, não a taxonomia).
  **Pronto quando:** na demo, o Kleber reconhece a tela sem tradução.

- **T-R12.5 — Aviso de item órfão.** Camada: admin. Arquivo:
  `apps/admin/pages/clientes/[id]/catalogo.vue`. Item de vitrine cujo
  `znuny_service_id` não existe mais (ou está com `ValidID=2`) aparece com selo
  "serviço inválido no Znuny". Leitura ao vivo, zero persistência.

**Testes de validação:**
- **V-R12.1** — vitest. Alvo: `apps/admin/test/service-tree.test.ts` (já existe;
  estender). ASSERT: `parentOptions(rows, null)` com um serviço raiz e um filho
  devolve **apenas** o raiz + "(nenhum)" — o filho **não** pode ser oferecido como
  pai (teto de dois níveis).
- **V-R12.2** — pytest. Alvo: `apps/sidecar/tests/test_admin_znuny_router.py`.
  ASSERT: `POST /v1/admin/znuny/objects/Service` com `ParentID` de um serviço que
  já tem pai → o GI mockado responde `DepthExceeded` e o router devolve **422** com
  a mensagem repassada.
- **V-R12.3** — manual contra o Znuny real. ASSERT: criar
  `Acesso e Identidade` (raiz) e `Reset de senha` (filho) pelo console; o Znuny
  nativo mostra `Acesso e Identidade::Reset de senha`; o portal
  `/tickets/novo` lista os dois no select de serviço (via `FormMeta.pm:37`); criar
  um terceiro nível é recusado.
- **V-R12.4** — vitest. Alvo: `apps/portal/test/catalog-prefill.test.ts` (existe ou
  novo). ASSERT: com `znuny_service_id = 7` e `services = [{Key:'7',
  Value:'Acesso e Identidade::Reset de senha'}]`, `prefillFromCatalogItem` resolve
  `service === '7'` **mesmo se o `Value` mudar** de nome (regressão do match por
  string).
- **V-R12.5** — pytest. Alvo: `apps/sidecar/tests/test_migration_00XX_catalog_service_id.py`
  (novo). ASSERT: backfill converte `znuny_service='Acesso e Identidade'` em
  `znuny_service_id` correspondente e deixa `NULL` (não erro) quando não há
  correspondência.

**Risco/decisão aberta:**
1. **Migração de dados.** Já há itens de catálogo em staging com `znuny_service`
   texto. O backfill precisa de uma lista de serviços do Znuny no momento da
   migration — que é I/O externo dentro de uma migration, coisa que evitamos.
   Alternativa: migration adiciona a coluna nullable e um **comando de console** do
   sidecar faz o backfill depois. Recomendo a alternativa.
2. **Teto de 2 níveis é decisão de produto, não limitação técnica.** O Kleber
   descreveu o limite do TIFLUX ("aqui só dá dois níveis") — pode ser que ele
   *aceite* três. Perguntar antes de implementar T-R12.3: impor um limite que ele
   não pediu é criar dívida.
3. **ITSMCore torna `TypeID`/`Criticality` obrigatórios** no `ServiceAdd`
   (`AdminSpec.pm:104-107`). A tela precisa oferecer esses selects do
   GeneralCatalog — hoje são campos livres em `useServiceTree.ts:143-154`. Isso é
   um subgap de R12 que vale confirmar ao vivo.

---

## R13 — Feriados e checklists personalizáveis

**Pedido (citação curta do Kleber):**
> "Temos aqui configurações de feriados, checklists personalizáveis."
> (`docs/transcricoes/…:128`)

**Estado atual:** **feriados = COBERTO (com 3 arestas). Checklists = AUSENTE.**

**Feriados — COBERTO:**
- Bloco D da Spec #4, forma composta (jornada + feriado recorrente + feriado
  pontual num só payload):
  `apps/sidecar/src/gerti_sidecar/routers/admin_znuny_people.py:350-373` (GET) e
  `:376-474` (PUT).
- Allowlist fechada de settings:
  `apps/sidecar/src/gerti_sidecar/integrations/znuny_admin_sysconfig.py:74-85`;
  validação de forma antes de tocar o Znuny: `:196-283` (jornada `Dia→[0..23]`,
  feriado recorrente `Mês→Dia→texto`, feriado pontual `Ano→Mês→Dia→texto`).
- Lado Perl: `AdminSysConfigGet.pm`/`AdminSysConfigSet.pm`, rotas
  `/SysConfig/Get` e `/SysConfig/Set` (`znuny/webservices/GertiAdmin.yml:86-90`),
  com `SettingLock → SettingUpdate → ConfigurationDeploy` e liberação garantida do
  lock (`.ia/ARCHITECTURE.md:676-684`).
- Tela: `apps/admin/pages/znuny/calendario.vue` + lógica pura
  `apps/admin/composables/useWorkingHours.ts:195-507` (editor de feriado
  recorrente/pontual, diff antes-depois) e testes
  `apps/admin/test/working-hours.test.ts`.
- Guarda de aplicação parcial: se a 2ª das 3 gravações falhar, a resposta de erro
  **nomeia o que já foi aplicado e o que falhou**, e audita
  (`admin_znuny_people.py:416-452`).
- Verificado ao vivo em staging: `GET /calendar` devolveu a jornada real e
  `?calendar=99` deu 404 (`.ia/OPS.md:1295-1301`, `:1322-1327`).
- Amarração com fila existe: `Queue.Calendar` está na allowlist
  (`AdminSpec.pm:64`) e a tela de filas oferece o select
  (`apps/admin/pages/znuny/filas.vue:57`).

**Arestas reais dos feriados (não são "coberto perfeito"):**
1. **O caminho de falha do `SettingLock` nunca foi exercitado contra um Znuny
   vivo** — só por leitura de código e teste com GI mockado
   (`.ia/OPS.md:1310-1313` e `:1339-1341`;
   `docs/ENTREGA-E-ROADMAP.md:258-259`). O teste automatizado existe
   (`apps/sidecar/tests/test_admin_znuny_people_router.py:475-522`,
   `test_calendar_put_partial_failure_reports_applied_and_failed`), o que é bom, mas
   é mock. **Lock preso trava a administração do Znuny para todos.**
2. **Não dá para NOMEAR nem dar fuso a um calendário pelo console.**
   `TimeZone::Calendar1Name` existe no Znuny
   (`/opt/otrs/Kernel/Config/Files/XML/Framework.xml:1505`) mas **não está** na
   allowlist (`znuny_admin_sysconfig.py:74-85` só tem `TimeWorkingHours*`,
   `TimeVacationDays*`, `TimeVacationDaysOneTime*`, `TimeZone` e
   `CalendarWeekDayStart` — sem `::CalendarN`). E o select de calendário da tela de
   filas monta o rótulo a partir justamente desse nome
   (`AdminObjectList.pm:126-129`). Resultado: os calendários aparecem como
   "Calendar 3 - " (vazio).
3. **`_CalendarList` só lista calendários que já têm `TimeVacationDays::CalendarN`
   configurado** (`AdminObjectList.pm:126`) — um calendário recém-criado só aparece
   na tela de filas **depois** que feriados forem salvos nele. E o console limita a
   1..9 (`znuny_admin_sysconfig.py:92`) enquanto o Znuny vai até
   `MaximumCalendarNumber` (`/opt/otrs/Kernel/Config/Files/XML/Framework.xml:1373`,
   default 50 no `_CalendarList`, `AdminObjectList.pm:123`).

**Checklists — AUSENTE:** zero ocorrências de `checklist` em `apps/` e `znuny/`
(grep, sem resultado). Não existe objeto nativo equivalente no Znuny 7.2.3 (o mais
próximo seria Dynamic Field multiselect ou o Process Management, nenhum dos dois é
checklist de tarefa).

**Tarefas:**

- **T-R13.1 — Exercitar o caminho de falha do `SettingLock` contra o Znuny real.**
  Camada: manual/ops. Arquivos: `docs/COMO-TESTAR-ADMIN-ZNUNY.md` (Parte 6),
  `.ia/OPS.md:1310-1313` (baixar a pendência). Não é código — é a última prova
  que falta do bloco de maior risco da spec.
- **T-R13.2 — Permitir nomear/fusar calendários.** Camada: sidecar (+ Perl só se a
  validação de forma exigir). Arquivos:
  `znuny_admin_sysconfig.py:74-85` (`ALLOWED_SETTINGS` += `TimeZone::CalendarN` e
  `TimeZone::CalendarNName` para N=1..9), `:267-283` (`validate_setting_shape` →
  escalar), `AdminSysConfigSet.pm` (espelhar allowlist e `_SettingKind`),
  `apps/admin/pages/znuny/calendario.vue` (campo "Nome do calendário").
  **Pronto quando:** o select de calendário da tela de filas mostra
  "Calendar 3 - Feriados SP" em vez de "Calendar 3 - ".
- **T-R13.3 — Alinhar o número de calendários com `MaximumCalendarNumber`.**
  Camada: sidecar + admin. Arquivos: `znuny_admin_sysconfig.py:71,92`,
  `apps/admin/composables/useWorkingHours.ts` (`CALENDAR_OPTIONS`). Decidir: ou
  subir para 50, ou documentar o teto de 9 como decisão. Hoje é divergência
  silenciosa.
- **T-R13.4 — Checklists: modelo + CRUD + aplicação no ticket.** Camada: sidecar +
  admin (+ portal, opcional). Arquivos:
  `models/checklist_template.py` e `models/checklist_instance.py` (novos, FORCE
  RLS), migration nova, `domain/checklist_service.py`,
  `routers/admin_checklists.py`, `apps/admin/pages/checklists/index.vue`,
  e o painel de checagem no `apps/admin/pages/atendimento/[id].vue`.
  **Justificativa D21:** o Znuny **não tem** objeto checklist — não existe fonte de
  verdade para duplicar, logo não há segunda fonte de verdade. Alternativa
  considerada e rejeitada: Dynamic Field multiselect por ticket (seria config do
  Znuny, mas não permite template reutilizável nem marcar item a item com autor e
  horário). O ticket continua sendo do Znuny; o checklist referencia
  `znuny_ticket_id`, não copia o ticket.
  **Pronto quando:** o agente aplica o template "Verificação de backup" a um ticket
  e marca os itens, com o progresso visível.
  *Escopo:* dá para entregar em duas fases — templates + aplicação manual (fase 1),
  vínculo automático com R11/catálogo (fase 2).

**Testes de validação:**
- **V-R13.1** — manual contra o Znuny real (Parte 6 de
  `docs/COMO-TESTAR-ADMIN-ZNUNY.md`). ASSERT: forçar falha na **segunda** das três
  gravações do calendário (ex.: derrubar o `znuny-web` entre as chamadas, ou lockar
  o setting pelo painel nativo) → a resposta HTTP traz
  `{"applied": ["TimeWorkingHours"], "failed_setting": "TimeVacationDays"}`, o
  `audit_log` tem a linha "aplicação PARCIAL (1/3)", **e o `SettingLock` do setting
  que falhou está LIBERADO** (verificar via
  `bin/otrs.Console.pl Admin::Config::...` / painel nativo, com o console rodando
  como `su otrs -s /bin/bash -c "cd /opt/otrs && …"`). Esta última asserção é o
  ponto inteiro do teste.
- **V-R13.2** — pytest. Alvo: `apps/sidecar/tests/test_znuny_admin_sysconfig.py`.
  ASSERT: `"TimeZone::Calendar3Name" in ALLOWED_SETTINGS` e
  `validate_setting_shape("TimeZone::Calendar3Name", {"a":1})` levanta
  `CalendarSettingInvalid` (dict não é escalar).
- **V-R13.3** — pytest. Alvo: `apps/sidecar/tests/test_znuny_admin_sysconfig.py`.
  ASSERT (regressão, já deve passar hoje): `"Ticket::Frontend::AgentTicketZoom"
  not in ALLOWED_SETTINGS` — a allowlist do SysConfig continua fechada e ninguém
  abriu a porta para setting arbitrário.
- **V-R13.4** — pytest. Alvo: `apps/sidecar/tests/test_checklist_service.py` (novo).
  ASSERT: aplicar o mesmo template duas vezes ao mesmo ticket cria **uma** instância
  (idempotente); marcar item alheio a outro tenant → 404 (anti-IDOR pela RLS).
- **V-R13.5** — vitest. Alvo: `apps/admin/test/checklist.test.ts` (novo). ASSERT:
  `progress(items)` com 2 de 5 marcados → `0.4`; template sem item → validação
  rejeita.

**Risco/decisão aberta:**
1. O caminho de falha do `SettingLock` é o único ponto do subsistema que pode
   **travar a administração do Znuny inteira**. Enquanto V-R13.1 não rodar contra
   um Znuny vivo, esse risco continua declarado, não fechado.
2. Checklist **transborda o recorte administrativo**: só faz sentido se o agente
   usar no atendimento. Confirmar com o Vinícius (vídeo de gestão de tickets) antes
   de dimensionar — pode haver requisito conflitante no outro vídeo.

---

## R17 — FAQ / base de conhecimento

**Pedido (citação curta do Kleber):**
> "A FAQ, o OTRS já tem, o Zuni já tem uma FAQ, **é feinha, mas tem**."
> (`docs/transcricoes/…:156`; o brief classifica como "paridade já coberta,
> expectativa é de qualidade visual superior")

**Estado atual:** **COBERTO** — e por um caminho melhor do que o pedido, com um
esclarecimento importante.

- **O pacote FAQ do Znuny NÃO está instalado.** A imagem baixa apenas
  `GeneralCatalog`, `ITSMCore`, `ITSMConfigurationManagement`
  (`znuny/Dockerfile:308-314`); grep por `FAQ` no `znuny/` não retorna nada.
  Então a premissa do Kleber ("o Znuny já tem") **não vale nesta instalação** — o
  requisito está atendido por implementação própria, não por paridade.
- Base de conhecimento própria, tenant-scoped:
  `apps/sidecar/src/gerti_sidecar/models/kb.py:32-68` (`kb_article`, UNIQUE
  `(tenant_id, slug)`, `visibility public|internal`, `status
  draft|published|archived`, `views`, `tags`), com FORCE RLS por tenant (D20
  Decisão 3, `.ia/DECISIONS.md:513-519`).
- Serviço: `apps/sidecar/src/gerti_sidecar/domain/kb_service.py:1-11` (slug estável
  — o update **nunca** recalcula, preserva links; incremento de `views` sem race).
- Rotas: `apps/sidecar/src/gerti_sidecar/routers/kb.py` (portal, só
  `public`+`published`) e `routers/admin_kb.py` (console, vê tudo).
- Telas: `apps/portal/pages/base-conhecimento/index.vue` e `[slug].vue`;
  console `apps/admin/pages/clientes/[id]/conhecimento.vue`.
- Testes já existentes: `apps/sidecar/tests/test_kb_service.py`,
  `test_kb_router.py`, `test_admin_kb_router.py`, `test_admin_kb_audit.py`;
  vitest `apps/admin/test/kb-article-editor.test.ts`.
- Busca integrada: `apps/sidecar/src/gerti_sidecar/domain/search_service.py` +
  `routers/search.py` / `admin_search.py`, telas `/busca` nos dois apps.

**Gap:** nenhum bloqueante. Três lacunas menores, todas de produto:
1. **Categoria é texto livre** (`models/kb.py:52`) — mesma fragilidade do catálogo,
   sem hierarquia nem lista fechada.
2. **Não há "sugerir artigo" no fluxo do chamado** — nem no portal ao abrir
   (`apps/portal/pages/tickets/novo.vue`), nem no console ao atender
   (`apps/admin/pages/atendimento/[id].vue`).
3. **Base interna vs. base do cliente compartilham a mesma tabela** por
   `visibility` (decisão explícita e correta, `.ia/DECISIONS.md:513-519`), mas o
   console não separa visualmente as duas — o agente não tem "minha base interna".

**Tarefas:**

- **T-R17.1 — Confirmar com o Kleber que a base própria substitui a FAQ do
  Znuny.** Camada: decisão. Arquivo: nota em `.ia/DECISIONS.md`. Custo zero,
  evita a expectativa de "cadê o menu FAQ do Znuny" na demo. **Recomendação: não
  instalar o pacote FAQ** — instalaria uma segunda base de conhecimento, com
  segunda fonte de verdade e a interface "feinha" que ele mesmo criticou.
- **T-R17.2 — Sugestão de artigos no fluxo do chamado.** Camada: portal + admin
  (+ sidecar só como query). Arquivos: `apps/portal/pages/tickets/novo.vue`
  (busca no KB conforme o título é digitado, `public`+`published`),
  `apps/admin/pages/atendimento/[id].vue` (artigos relacionados por tags/serviço),
  reuso de `domain/search_service.py`. É o que transforma a base em desvio de
  chamado — o valor real da FAQ para um MSP.
  **Pronto quando:** digitar "senha" em `/tickets/novo` sugere o artigo de reset de
  senha antes do envio.
- **T-R17.3 — Aba "Base interna" no console.** Camada: admin. Arquivo:
  `apps/admin/pages/clientes/[id]/conhecimento.vue` (filtro por `visibility`).
  Nenhuma mudança de modelo.
- **T-R17.4 — (opcional) Categorias de KB alinhadas ao catálogo.** Camada: sidecar
  + admin. Se T-R12.1 for aprovada, usar a mesma taxonomia (`Service` do Znuny)
  como categoria do artigo, via `znuny_service_id`. Mesma justificativa D21 da
  T-R12.2 (referência, não cópia).

**Testes de validação:**
- **V-R17.1** — pytest (regressão, já deve passar). Alvo:
  `apps/sidecar/tests/test_kb_router.py`. ASSERT: artigo com
  `visibility='internal'` ou `status='draft'` → `GET /v1/kb/{slug}` pelo portal
  devolve **404** (não 403 — não vaza existência).
- **V-R17.2** — pytest. Alvo: `apps/sidecar/tests/test_kb_service.py`. ASSERT
  (regressão): editar o título de um artigo publicado **não** muda o `slug` — o
  link antigo continua resolvendo.
- **V-R17.3** — pytest. Alvo: `apps/sidecar/tests/test_kb_suggest.py` (novo).
  ASSERT: `suggest(title="não consigo resetar minha senha")` para o tenant A
  retorna o artigo "Reset de senha" do tenant A e **nenhum** artigo do tenant B
  (isolamento sob o papel `gerti_sidecar`).
- **V-R17.4** — e2e/manual em staging. ASSERT: um usuário do portal vê o artigo
  sugerido, abre, e o contador de `views` sobe; um artigo `internal` não aparece
  em nenhuma sugestão do portal.

**Risco/decisão aberta:** apenas a T-R17.1 (não instalar o pacote FAQ). Se o Kleber
insistir na FAQ nativa, isso vira uma segunda base de conhecimento — recomendo
recusar, com o argumento dele mesmo ("é feinha").

---

## Tabela-resumo

| Requisito | Estado | # tarefas | Esforço |
|---|---|---|---|
| **R9** — e-mail (contas, endereços, invariante, remetente por cliente, domínios) | **AUSENTE** (+ saída de e-mail quebrada na infra) | 8 (T-R9.1…8) | **G** |
| **R10** — mesas de serviço (= filas) | **PARCIAL** — criar fila **falha hoje** | 3 (T-R10.1…3; a .1 é a mesma de R9) | **P** |
| **R11** — atividades agendadas / tickets recorrentes | **AUSENTE** — `GenericAgent` **não serve** | 5 (T-R11.1…5) | **G** |
| **R12** — catálogo de serviço, item + sub-item | **PARCIAL** — dois catálogos paralelos, sem teto de 2 níveis | 5 (T-R12.1…5) | **M** |
| **R13a** — feriados | **COBERTO** — 3 arestas + 1 caminho de falha não exercitado | 3 (T-R13.1…3) | **P** |
| **R13b** — checklists personalizáveis | **AUSENTE** | 1 (T-R13.4, 2 fases) | **M** |
| **R17** — FAQ / base de conhecimento | **COBERTO** (implementação própria; pacote FAQ do Znuny **não** instalado) | 4 (T-R17.1…4, 3 opcionais) | **P** |

**Legenda de esforço:** P ≤ 1 dia · M = 2–4 dias · G > 1 semana.

**Ordem sugerida (dependências reais, não prioridade comercial):**
`T-R9.2 → T-R9.3/T-R10.1` (destrava criar fila, prerequisito de tudo em e-mail) →
`T-R9.1` (SMTP, sem ele R9 não é demonstrável) → `T-R13.1` (fecha a última
pendência de risco da Spec #4, custo quase zero) → `T-R12.1` (decisão, bloqueia
T-R12.2/3) → `T-R9.4…7` → `T-R11.*` → `T-R13.4`.

**Lembretes operacionais para quem executar (já quebraram o projeto 2×):**
cada `.pm` novo exige **linha `COPY` + nome no loop `perl -c`** do
`znuny/Dockerfile:205-231` (não há wildcard); operação nova exige entrada
**e rota** em `znuny/webservices/GertiAdmin.yml`; deploy = rebuild `znuny-web` +
`Admin::WebService::Update --webservice-id 2 --source-path
/opt/otrs/webservices/GertiAdmin.yml` (**`--webservice-id`, não `--name`**);
console **não roda como root**
(`su otrs -s /bin/bash -c "cd /opt/otrs && …"`); e nenhuma mudança fecha sem
`make test` (24 asserts) verde.
