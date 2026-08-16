# Campanha "Recursos Administrativos" — registro de execução

Ledger da execução do plano
[`docs/superpowers/plans/2026-08-15-recursos-administrativos.md`](superpowers/plans/2026-08-15-recursos-administrativos.md).
Uma linha por tarefa: estado, gate, evidência de aceite, sha deployado.

É deste arquivo que sai a prestação de contas ao Kleber, requisito a requisito.

---

## Onda 0 — Defeitos existentes

Branch `campanha/onda-0-defeitos`, a partir de `main @ 50fb3c9`.

**Sha deployado em staging: `42d38af`** (2026-08-15). Depois mergeada na `main` em
`811cb9f`. Runbook, provas e rollback em
[`../.ia/OPS.md`](../.ia/OPS.md), seção "Deploy da Onda 0". Sha anterior do
staging: `214842b`.

### Tarefas

| Tarefa | O que corrigiu | Estado | Sha deployado | Evidência |
|---|---|---|---|---|
| **T-R15.4** | Fatura de contrato não-crédito saía R$ 0,00 | ✅ | `42d38af` | `test_invoice_service.py` — banco de horas 12 h sobre franquia de 10 h a R$ 200/h → **R$ 400,00** (antes: 0) |
| **T-R9.2 + T-R9.3** (= T-R10.1) | Criar fila pelo console falhava sempre | ✅ | `42d38af` | `znuny-object.test.ts` — 51 casos; paridade Perl↔Python em `test_admin_znuny_router.py`. **Ao vivo no staging:** listas de apoio preenchidas, `POST` da fila → **201**, fila visível no painel nativo com o endereço de sistema escolhido; sem os campos → **422** nomeando-os |
| **T-R2.4** | Detalhe de chamado mais permissivo que a lista | ✅ | `42d38af` | `test_tickets_router.py` — helpdesk pedindo chamado de colega → **404**. **Ao vivo:** helpdesk → 404 no chamado do colega, **200** no próprio; admin do portal vê os 22 da empresa |
| **T-R2.4 (extensão)** | `reply` e `submit_csat` tinham a mesma falha | ✅ | `42d38af` | 4 testes novos; admin do portal preservado (201). **Ao vivo:** `reply` e `csat` em chamado alheio → **404** `ticket_not_found` |
| **T-R3.1** | Catálogo de contratos sem teste-guarda | ✅ | `42d38af` | `test_admin_contracts.py`, `test_enums.py` |
| **T-R0.6** | Fallback ReportLab era código morto | ✅ | `42d38af` | Dependência declarada; a suíte fecha no macOS sem as libs nativas do WeasyPrint. **Ao vivo:** `reportlab 5.0.0` importa no venv do sidecar |
| **T-R13.1** | Trava de calendário nunca exercitada contra o Znuny real | ✅ | `42d38af` | **Exercitada no staging contra o Znuny real (2026-08-15)** com falha injetada de verdade na 2ª das 3 gravações: resposta **422** nomeando `applied` e `failed_setting`, `audit_log` com "aplicação PARCIAL (1/3)", e o `SettingLock` do setting que falhou **LIBERADO** (`exclusive_lock_guid='0'`, sem lock preso em toda a `sysconfig_default`). Procedimento e saída em `../.ia/OPS.md` |

### Achados do deploy (pré-existentes, não são regressão desta onda)

| Achado | Gravidade | Onde | Onda |
|---|---|---|---|
| **A gravação do calendário estoura o timeout do cliente.** `AdminSysConfigSet` leva ~12 s no staging (faz `ConfigurationDeploy`) contra `_TIMEOUT = 10.0` do cliente; o console devolve **503 com mensagem vazia** e `applied: []` numa gravação que o Znuny pode estar concluindo — exatamente o "aplicação parcial silenciosa" que o Bloco D existe para evitar | alto | `integrations/znuny_admin_sysconfig.py` | a definir |
| **O papel do portal é resolvido pela string exata do login.** `eduardo.salvi` cai em `helpdesk` (papel default) e `eduardo.salvi@auroramoveis.com.br` em `admin` — a mesma pessoa vê coisas diferentes conforme o formato que digitou. O console já canonicaliza o login do agente; o portal não faz o equivalente para o papel. **A Onda 1 mostrou a causa raiz:** o papel aponta para um login que **não existe** no `customer_user` do Znuny — são dois cadastros para a mesma pessoa, o defeito que o R2 combate | alto | resolução de papel do portal (`portal_user_role`) | **Onda 2** |

### Achados que a onda não previu

Três elos quebrados que só apareceram ao executar, todos registrados porque a lição vale além do caso:

1. **A criação de fila estava quebrada em três camadas, não uma.** O Perl exigia os campos, o
   **sidecar descartava as listas de apoio** antes de chegarem ao console
   (`_SUPPORT_LIST_KEYS` é filtro, não documentação), e a tela tinha o script atualizado e o
   **template não** — o botão ficava permanentemente desabilitado, sem explicação. Corrigir
   só uma camada teria trocado um bug por outro. Dois testes de paridade Perl↔Python passam
   a impedir a repetição.

2. **A correção do IDOR fechou uma rota e deixou duas irmãs abertas.** `reply` e
   `submit_csat` seguiam passando só a empresa. A armadilha: `TicketReply.pm` já recebia um
   `CustomerUser`, mas ele é o **autor da resposta**, não a guarda — usá-lo como guarda
   bloquearia o admin do portal, que legitimamente responde pela empresa inteira.

3. **Duas faturas de R$ 0,00 no staging não eram vítimas do defeito.** Verificado em
   transação **somente leitura**: as duas estavam dentro da franquia. Não há receita perdida
   em documento já emitido, e nada a corrigir retroativamente.

### Bloqueantes levantados pela revisão adversarial (antes do deploy)

| # | Achado | Estado |
|---|---|---|
| 1 | Fatura de banco de horas somava 12 h de consumo **mais** 2 h de excedente — o cliente lia 14 h, com uma linha de serviço a R$ 0,00 | 🔧 corrigido antes do deploy |
| 2 | "Acumular saldo entre ciclos" cobrava excedente inexistente: o `carry_over` era calculado e **nunca lido**. Antes invisível (fatura zerada), agora viraria cobrança indevida | 🔧 corrigido antes do deploy |
| 3 | Busca do portal entregava chamado de colega ao papel `helpdesk` — e clicar dava 404, pela guarda nova | 🔧 corrigido antes do deploy |

O item 2 merece registro: **foi uma regressão criada pela própria onda**. Enquanto a fatura
saía zerada, a falta do acúmulo não aparecia. Corrigir um defeito tornou o outro visível — e
cobrável.

---

## Onda 1 — Cadastro de cliente e usuário único

Branch `campanha/onda-1-cadastro`, a partir de `main @ 811cb9f`.

**Sha deployado em staging: `bce770b`** (2026-08-16) — branch rodando no host.
Runbook, provas e rollback em [`../.ia/OPS.md`](../.ia/OPS.md), seção "Deploy da
Onda 1". Sha anterior do staging: `c7f9025`; alembic anterior: `0026`.

### Tarefas

| Tarefa | O que entregou | Estado | Sha | Evidência |
|---|---|---|---|---|
| **T-R1.1** | Endereço e contato em `gerti.tenant` (migration 0027, 10 colunas nullable) | ✅ | `bce770b` | `test_migration_0027_tenant_address.py` — cliente antigo sem endereço continua inserível; as 10 colunas existem e são nullable |
| **T-R1.2** | `PUT /v1/admin/tenants/{id}` — dá para corrigir o cadastro depois de criado | ✅ | `bce770b` | `test_admin_tenants.py`. **Ao vivo:** cidade e contato da Aurora persistem; `subdomain` → **422** com o valor intacto no banco; id fantasma → **404** |
| **T-R1.3** | GI `CustomerCompanyUpdate` — espelho no `customer_company` | ✅ | `bce770b` | `perl -c` verde. **Ao vivo:** `street`/`zip`/`city`/`comments` da AURORA gravados no Znuny |
| **T-R1.4** | `/clientes/novo` vira assistente de 3 etapas | ✅ | `bce770b` | `tenant-wizard.test.ts` — 15 casos; não avança com etapa inválida, CEP e UF normalizados |
| **T-R1.5** | Tela de edição do cliente | ✅ | `bce770b` | Campos imutáveis renderizados desabilitados **com a explicação do porquê** |
| **T-R1.6** | Aba "Chamados" na ficha | ✅ | `bce770b` | Proxy resolve o `znuny_customer_id` no servidor; estados de vazio e de erro |
| **T-R2.1** | Cadastro rico: telefone, celular, ramal, ativo, chave de e-mail (migration 0028 + GI `CustomerUserUpdate`) | ✅ | `bce770b` | `test_tenant_users_router.py`. **Ao vivo:** os três campos voltam na listagem; desativar → `ValidID=2`, a pessoa continua existindo |
| **T-R2.2** | `GET /{id}/users` lendo o Znuny como fonte de verdade (GI `CustomerUserList`) | ✅ | `bce770b` | **Ao vivo:** 4 pessoas criadas direto no Znuny, até então invisíveis no console, aparecem marcadas "sem acesso ao portal" |
| **T-R2.3** | Hora em chamado sem contrato deixa de sumir (migration 0030 + auto-vínculo) | ✅ | `bce770b` | 4 testes em `test_reconciliation_service.py`: 1 contrato ativo → vincula e fatura; 2 → nada cobrado + pendência `ambiguous_contract`; CustomerID desconhecido → `no_tenant`; rescan não duplica |
| **T-R2.4** | — | ✅ | `42d38af` | Entregue na Onda 0 |
| **T-R2.5** | Tela de usuários do cliente | ✅ | `bce770b` | `tenant-users.test.ts` — 17 casos. Payload de edição **nunca** carrega senha; desativar exige o e-mail digitado |
| **T-R5.1** | `gerti.tenant_queue` com FORCE RLS e no máx. 1 padrão (migration 0029) | ✅ | `bce770b` | `test_rls_tenant_queue.py` — isolamento entre clientes, fail-closed sem GUC, escrita cross-tenant bloqueada, FORCE confirmado no `pg_class` |
| **T-R5.2** | `GET/PUT /v1/admin/tenants/{id}/queues` | ✅ | `bce770b` | `test_admin_tenant_queues_router.py` — 8 casos. **Ao vivo:** fila 99999 → **422** e zero linhas; duas padrões → 422; mover o padrão não colide com o índice |
| **T-R5.3** | Fila padrão do cliente vale na abertura de chamado | ✅ | `bce770b` | **Ao vivo:** chamado da Aurora nasceu em `Suporte::N1`, não em `Raw`; fila não associada → **422** |
| **T-R5.4** | Tela "Relacionamentos" na ficha | ✅ | `bce770b` | `tenant-queues.test.ts` — 14 casos; remover a fila padrão pede confirmação |
| **T-R5.5** | Coluna "atendida por" na tela global de filas | ✅ | `bce770b` | `AdminGroupList` passa a devolver `RwUserCount`; sem a contagem, mostra só o grupo — nunca "0 agentes" inventado |

### Aceites cobertos

A1.1–A1.5 · A2.1, A2.3–A2.6 · A5.1–A5.5. **A2.2 ao vivo** (chamado que entra por
e-mail aparece no portal do autor) depende de T-R2.6, que é Onda 2 — mas o que
o tornava perigoso já está resolvido: **T-R2.3 entrou antes**, como o plano
exige.

### Defeito que só a execução ao vivo revelou

**A guarda de fila não chegava a rodar.** Abrir chamado com `queue=Financeiro`
— fila que a Aurora não acessa — devolvia **201** em vez de 422. O serviço
validava certo; a **rota** não recebia o campo do formulário, então
`OpenTicketInput.queue` era sempre `None` e o 422 prometido era código morto.

Não era brecha de isolamento (o chamado sempre caía na fila padrão do próprio
cliente, nunca na de outro), mas era validação anunciada e inexistente.

A lição repete a da Onda 0, com outra roupa: **o teste de serviço passava**
porque chamava `open_ticket` direto, com a fila já dentro do dataclass. O elo
que faltava era uma camada acima. Entraram dois testes de **rota**; o segundo
falha sem a correção.

### Achados da execução

1. **A demo tem o defeito do Kleber dentro dela.** A listagem por Znuny mostrou
   que a Aurora tem `eduardo.salvi` (usuário real no Znuny, criado pelo seed) e
   `eduardo.salvi@auroramoveis.com.br` (só um papel em `portal_user_role`, sem
   nenhum `customer_user` correspondente). É a mesma pessoa partida em dois
   cadastros — exatamente o que o R2 existe para acabar. Isso **explica** o
   achado da Onda 0 sobre papel resolvido por string exata de login: quem entra
   como `eduardo.salvi` não acha papel nenhum e cai no default `helpdesk`.
   Não é defeito de código desta onda; é dado de seed, e a tela nova o torna
   visível numa olhada.

2. **Duas correções da revisão adversarial, antes do commit.**
   `CustomerUserUpdate` aceitava `UserCustomerID` na allowlist de escrita — o
   que transformaria "editar usuário" em "mover a pessoa para outra empresa";
   o campo agora é preservado do registro atual e nunca lido da requisição. E a
   listagem de pessoas tem teto de 500 no Perl, mas o console engolia a marca de
   corte: lista truncada passava por lista completa, que se lê como exclusão.

### Decisões tomadas por padrão nesta onda

**O ramal mora do nosso lado.** O mapa nativo do `customer_user` tem `phone`,
`mobile`, `street`, `city` — e não tem ramal. Colocá-lo no Znuny exigiria coluna
nova no núcleo, que a invariante 4 proíbe; enfiá-lo num campo livre (`comments`,
`fax`) seria pior. Então telefone e celular vão para o Znuny, que é o dono da
identidade (D-C), e o ramal fica em `portal_user_role`, **com a limitação
declarada: ele não aparece no painel nativo.** Risco baixo, reversão barata.

**V-R2.3 foi ajustado à decisão D-E.** O teste como estava redigido no
levantamento exigia que o cursor **não** avançasse sobre lançamento órfão. A
decisão D-E, fechada depois, diz o contrário: não mexer no avanço do cursor (é
código financeiro vivo) e trocar o descarte silencioso por pendência
reprocessável. Os testes seguem a decisão, e asseram explicitamente que o cursor
avança **e** que a pendência ficou registrada.

---

## Dívida registrada, com dono e onda

O que a revisão adversarial encontrou e **não** entrou nesta onda. Está aqui para não virar
surpresa depois.

| Achado | Gravidade | Onde | Onda |
|---|---|---|---|
| **`service_count` ainda fatura R$ 0,00.** A onda corrigiu 3 dos 4 tipos zerados; contrato por limite de atendimento continua sem cobrança porque nenhum produtor gera evento desse tipo. Existe contrato assim no seed do staging (`AUR-PACOTE-2026`, 50 serviços a R$ 150) — fechar o ciclo dele hoje gera fatura zerada | alto | `invoice_service.py`, `reconciliation_service.py` | **T-R3.3, Onda 5** |
| **Glosa aprovada não abate a fatura.** `create_from_cycle` agrega por janela de data, sem excluir glosa aprovada nem filtrar por `closing_cycle_id` — ao contrário do fechamento do ciclo, que exclui. Cliente contesta 2 h, gestor aprova, e a fatura cobra assim mesmo | alto (pré-existente) | `invoice_service.py` | **Onda 5** |
| **Mensalidade sem checar status, sem proporção e sem olhar o tamanho do ciclo.** Contrato `suspended` cobra mês cheio; contrato assinado dia 25 cobra o mês inteiro; ciclo trimestral cobra **um** mês | médio | `invoice_service.py` | **Onda 5**, junto de D-Q |
| Corpo de escrita do admin sem schema Pydantic e auditoria copiando o corpo bruto (sem teto de tamanho) | baixo (pré-existente) | `routers/admin_znuny.py` | **Onda 4** |
| `ReplyBody.body` sem `max_length` (o CSAT já tem limite e truncagem) | baixo (pré-existente) | `routers/tickets.py` | **Onda 4** |
| Guarda de posse compara login byte a byte, enquanto a lista compara sem diferenciar caixa. Não achamos caminho para o dono legítimo cair no 404 — caixa errada morre antes, no 401 — mas alinhar seria mais coerente | observação | `TicketGet.pm`, `TicketReply.pm` | **Onda 2** |
| Fallback ReportLab não pagina: acima de ~35 linhas o conteúdo some do PDF em silêncio. Sem risco hoje (faturas têm 2 a 4 linhas) | observação | `invoice_pdf.py` | **Onda 3**, junto do relatório executivo |

---

## Decisões novas abertas pela execução

**D-R — o saldo acumulado entre ciclos tem teto e validade?** Ao corrigir a cobrança
indevida, o acúmulo foi implementado **ilimitado e sem expiração**. Contratos reais de MSP
costumam ter cap (por exemplo, acumula no máximo uma franquia) ou prazo (saldo de janeiro
expira em 90 dias). Nada disso está modelado — não há coluna de teto nem de validade em
`contract`. Muda cobrança, então é decisão de negócio, não de implementação. A mudança
seria localizada: `_carry_in_minutes` mais uma coluna.

Pergunta para o Kleber: *"hora que sobra num mês acumula para sempre, ou tem teto e prazo
para usar?"*



**D-Q — mensalidade de contrato de valor fixo é por ciclo ou por mês?** Surgiu ao corrigir a
fatura: `initial_amount_brl` é semanticamente sobrecarregado (saldo consumível nos contratos
de crédito, mensalidade nos de valor fixo). Hoje é inobservável — não existe gerador de
ciclos —, mas **bloqueia a Onda 5**. Detalhe e a pergunta pronta para o Kleber estão no
registro de decisões do plano.
