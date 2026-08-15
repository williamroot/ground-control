# Campanha "Recursos Administrativos" — registro de execução

Ledger da execução do plano
[`docs/superpowers/plans/2026-08-15-recursos-administrativos.md`](superpowers/plans/2026-08-15-recursos-administrativos.md).
Uma linha por tarefa: estado, gate, evidência de aceite, sha deployado.

É deste arquivo que sai a prestação de contas ao Kleber, requisito a requisito.

---

## Onda 0 — Defeitos existentes

Branch `campanha/onda-0-defeitos`, a partir de `main @ 50fb3c9`.

**Sha deployado em staging: `42d38af`** (2026-08-15) — branch rodando no host, **não**
mergeada na `main`. Runbook, provas e rollback em
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
| **O papel do portal é resolvido pela string exata do login.** `eduardo.salvi` cai em `helpdesk` (papel default) e `eduardo.salvi@auroramoveis.com.br` em `admin` — a mesma pessoa vê coisas diferentes conforme o formato que digitou. O console já canonicaliza o login do agente; o portal não faz o equivalente para o papel | alto | resolução de papel do portal (`portal_user_role`) | a definir |

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
