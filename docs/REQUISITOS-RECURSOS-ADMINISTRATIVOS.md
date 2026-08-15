# Recursos administrativos — levantamento, termos de aceite e plano de validação

## Como ler este documento

Este documento converte o vídeo **"Recursos Administrativos"**, gravado por **Kleber**
(administrador da plataforma na Gerti), em três coisas que se pode cobrar:

1. **Requisitos numerados** (R1 a R18), cada um com a fala que o originou e o momento
   exato do vídeo — para que ninguém precise confiar na memória de quem assistiu.
2. **Termos de aceite** por requisito: a frase que, quando verdadeira, encerra a
   discussão sobre aquele item. Escrita em linguagem de operação, não de código.
3. **Testes de validação** que provam cada termo de aceite — automatizados sempre que
   possível, com roteiro manual quando o que se prova só existe ao vivo.

O que **não** está aqui: estimativa de prazo e sequenciamento de sprint. O levantamento
diz o que precisa existir e como se prova que existe; a ordem de execução é decisão de
planejamento, e vem depois do aceite deste escopo.

---

## De onde veio o material

| | |
|---|---|
| **Arquivo** | `Recursos Administrativos - TIFLUX.webm` |
| **Duração** | 13 min 02 s |
| **Quem fala** | Kleber, administrador da plataforma na Gerti |
| **Assunto** | Toda a parte de **configuração/administração** do TIFLUX — a ferramenta que o Ground Control substitui |
| **Vídeo irmão** | Um segundo vídeo, gravado por **Vinícius**, cobre *gestão de tickets* — **fora do escopo deste documento** |

### Uma limitação do material que precisa ficar registrada

O vídeo é **apenas a câmera do Kleber**. A gravação **não capturou a tela** do TIFLUX,
embora ele esteja navegando por ela o tempo todo ("essa tela é uma das telas mais
importantes", "vou meter o botãozinho cliente aqui").

Isso tem uma consequência prática: **não existem prints das telas do TIFLUX neste
material**. As imagens que aparecem ao longo deste documento são quadros do próprio
vídeo, no instante exato de cada fala — servem como marcação temporal e prova de
origem da citação, não como referência visual de interface.

Onde a interface do TIFLUX importar para a decisão de design, será preciso pedir ao
Kleber uma segunda gravação com a tela, ou prints avulsos das telas específicas.
Os pontos em que isso faz falta estão sinalizados como **decisão aberta** ao longo do
documento.

### Como o conteúdo foi extraído

Transcrição automática do áudio (modelo Whisper large-v3-turbo, português), revisada
contra o áudio nos trechos que definem requisito. A transcrição integral com marcação
de tempo está no anexo e versionada no repositório em
`docs/transcricoes/2026-08-15-kleber-recursos-administrativos-tiflux.txt`.

Toda citação neste documento traz o **minuto:segundo** em que foi dita. Qualquer
afirmação sobre o que o cliente pediu pode ser conferida na fonte.

---

## O fluxo que o Kleber declarou

Ele abre e fecha o vídeo com a mesma sequência — é a espinha dorsal do trabalho da
operação, e por isso a espinha dorsal deste levantamento:

> **"Toda vez que entra um contrato novo… a primeira coisa que eu vou fazer é cadastrar
> o cliente."** — 00:37

> **"O cadastro do cliente, o cadastro do contrato do cliente e as configurações padrões
> do sistema — que é fila, SLA, catálogo de serviço, os valores que vão ser cobrados de
> cada cliente."** — 12:41

Ou seja, três blocos: **cliente → contrato → configuração da plataforma**. Os 18
requisitos abaixo se distribuem nesses três blocos, mais um quarto que ele tratou como
uso diário e não como configuração: **relatórios**.

---

## Como funcionam os termos de aceite

Cada requisito tem uma tabela de **termos de aceite**. Um termo de aceite é uma
afirmação **observável e binária** — dá para olhar o sistema e dizer "sim" ou "não",
sem interpretação.

Regras que valem para todos eles:

- **Escrito do ponto de vista de quem opera**, não do sistema. "O usuário cadastrado uma
  única vez recebe no portal o chamado que abriu por e-mail" é um termo de aceite.
  "Implementar `CustomerUser` unificado" não é — isso é tarefa.
- **Cada termo tem um teste que o prova.** Se um termo de aceite não tem como ser
  provado, ele não é um termo de aceite: é uma intenção, e foi reescrito.
- **Teste automatizado tem precedência sobre roteiro manual.** O manual existe onde a
  prova depende de infraestrutura viva (entrega de e-mail real, deploy, integração
  externa).
- **Um requisito só é dado como aceito quando *todos* os seus termos estão verdadeiros.**
  Não há aceite parcial: o que estiver incompleto vira requisito remanescente, com
  número próprio.
- **Termo de aceite não é escopo novo.** Se durante a execução aparecer uma condição que
  não está aqui, ela é registrada como aditivo e negociada — não é absorvida em silêncio.

### O que significa cada estado de cobertura

| Estado | Significado |
|---|---|
| **COBERTO** | Já existe no Ground Control hoje, com evidência no código. Resta apenas provar em conjunto com o cliente. |
| **PARCIAL** | Existe a base, falta comportamento específico que o Kleber descreveu. O gap está nomeado. |
| **AUSENTE** | Não existe. Precisa ser construído do zero. |

Um requisito **COBERTO** ainda gera trabalho: o de **demonstrar o aceite**. É a diferença
entre "está pronto" e "está aceito".

---

# Panorama

## Os 18 requisitos, em uma tela

| # | Requisito | Momento | Estado | Tarefas | Esforço |
|---|---|---|---|---|---|
| R1 | Cadastro de cliente | 00:49 | PARCIAL | 6 | M |
| R2 | **Usuário único (portal + e-mail)** | 02:14 | PARCIAL | 6 | G |
| R3 | Tipos de contrato (catálogo fechado) | 03:15 | PARCIAL | 4 | M |
| R4 | Integração com inventário externo | 03:50 | *adiado pelo cliente* | — | — |
| R5 | Filas por cliente (relacionamentos) | 04:03 | PARCIAL | 5 | M |
| R6 | Faturamento por cliente (e-mail/SMS) | 04:43 | AUSENTE | 5 | G |
| R7 | Aprovação de chamados | 02:37 | AUSENTE | 6 | G |
| R8 | Importações | 05:38 | AUSENTE | 4 | M |
| R9 | **E-mail: entrada e saída por fila** | 06:38 | AUSENTE | 8 | G |
| R10 | Mesas de serviço (= filas) | 08:10 | PARCIAL *(criar fila falha)* | 3 | P |
| R11 | Atividades agendadas / recorrentes | 07:09 | AUSENTE | 5 | G |
| R12 | Catálogo de serviço (2 níveis) | 07:53 | PARCIAL | 5 | M |
| R13a | Feriados | 08:16 | **COBERTO** *(3 arestas)* | 3 | P |
| R13b | Checklists | 08:16 | AUSENTE | 1 | M |
| R14 | Agentes, grupos e permissões | 08:23 | PARCIAL | 4 | M |
| R15 | Financeiro: avulsos e valores extras | 08:40 | AUSENTE | 5 | G |
| R16 | Licenciamento e módulos por agente | 09:13 | AUSENTE | 6 | G |
| R17 | FAQ / base de conhecimento | 10:41 | **COBERTO** | 4 | P |
| R18a | Gráfico de consumo (3 meses) | 11:00 | PARCIAL | 4 | M |
| R18b | Relatório executivo mensal em PDF | 11:36 | AUSENTE | 5 | G |

**Esforço:** P ≤ 1 dia · M = 2 a 4 dias · G > 1 semana. São ordens de grandeza para
priorizar conversa, não compromisso de prazo.

**Totais: 89 tarefas · 94 termos de aceite · 105 testes de validação** (70 automatizados no
backend, 22 na interface, 3 ponta a ponta, 9 roteiros manuais e 1 no gate de construção da
imagem).

**Placar:** 2 requisitos cobertos · 8 parciais · 8 ausentes · 1 adiado pelo próprio cliente.

## Quatro defeitos encontrados que o vídeo não pediu

O levantamento cruzou cada fala com o código real, e nesse caminho apareceram problemas que
**já existem hoje**, independentes do que o Kleber pediu. Estão aqui porque três deles
custam dinheiro ou bloqueiam o requisito, e o quarto é de segurança.

Cada um foi **conferido diretamente no código**, não apenas relatado.

### 1. Fatura de contrato que não é de crédito sai R$ 0,00

A fatura soma apenas o valor faturável dos eventos de consumo, e esse valor **só é calculado
para contratos de crédito** (`reconciliation_service.py:120-124`). O excedente de horas é
calculado no fechamento do ciclo (`cycle_service.py:66-71`) e guardado — mas a fatura
**nunca o lê** (`invoice_service.py:114-119`).

**Efeito:** contrato por **banco de horas** com horas excedentes, **valor fechado** e
**SaaS** faturam **zero**. É receita não faturada, sem erro e sem alarme.

### 2. Criar fila pelo console falha sempre

A criação exige endereço de resposta, saudação e assinatura (`AdminSpec.pm:67`), e a tela
não envia nenhum dos três (`useZnunyObject.ts:214-229`). Nenhum teste pega porque todos
simulam a integração.

**Efeito:** a função existe no menu e nunca funcionou. Bloqueia R9 e R10 juntos.

### 3. O Znuny não envia e-mail nenhum

O padrão do produto é entregar por um programa de envio local que **não existe na imagem** —
verificado dentro do container — e o modelo de configuração não define nenhum servidor de
SMTP.

**Efeito:** nenhuma notificação, nenhuma resposta ao cliente e nenhuma auto-resposta sai
hoje. A **entrada** de e-mail, ao contrário, está pronta e apenas não tem caixa cadastrada.

### 4. Detalhe de chamado é mais permissivo que a lista

Para o papel de helpdesk, a lista mostra apenas os chamados do próprio usuário
(`tickets.py:145`), mas o detalhe valida somente a empresa (`tickets.py:174-176` e
`TicketGet.pm:42`).

**Efeito:** um usuário helpdesk consegue abrir, informando o identificador, um chamado de um
colega que não aparece na lista dele. **É dentro da mesma empresa — a fronteira entre
clientes diferentes continua fechada**, e isso foi conferido. Ainda assim é uma
inconsistência de escopo que deve ser corrigida antes de o número de usuários crescer (R2).

## As decisões que travam o início do trabalho

Estas não são detalhes de implementação — são escolhas de produto ou comerciais que mudam o
que será construído. Enquanto não forem respondidas, as tarefas correspondentes não devem
começar.

| Decisão | Trava | Quem decide |
|---|---|---|
| **Qual é o modelo comercial de licenças** — quem define o total contratado de agentes | R16 inteiro | William / WAS |
| **Cobrança sem contrato:** afrouxar o vínculo obrigatório ou criar um tipo de contrato "livre" | R15 e R3 | William, com o Kleber |
| **Fonte de verdade do usuário do cliente** — o Znuny ou a nossa base | R2 | William |
| **Remetente desconhecido por e-mail** — criar usuário sozinho, recusar, ou aceitar só de domínio autorizado | R2 e R9 | Kleber |
| **"Remetente por cliente"** — uma fila dedicada (nativo, sem código) ou interferir no envio | R9 | Kleber |
| **Teto de dois níveis no catálogo** — ele descreveu o limite do TIFLUX; talvez aceite três | R12 | Kleber |
| **"Principais tipos de chamado"** — tipo do chamado ou catálogo de serviço | R18b | Kleber |
| **"Últimos 3 meses"** — mês-calendário ou 3 ciclos de faturamento | R18a | Kleber |
| **Atividades recorrentes consomem horas do contrato?** | R11 | Kleber |
| **Como representar "aguardando aprovação"** e se o SLA corre durante a espera | R7 | William, com o Kleber |
| **Fonte de verdade do endereço do cliente** — nossa base, o Znuny, ou espelho | R1 | William |

## O que já está pronto e só precisa ser demonstrado

Vale separar: parte do que ele descreveu **já existe**, e o trabalho restante é de
**demonstração de aceite**, não de construção.

- **Base de conhecimento** com artigo público, interno e rascunho, isolamento entre clientes
  e link estável (R17) — inclusive melhor do que a FAQ nativa que ele mencionou.
- **Jornada de trabalho e feriados** administrados pelo console, ao vivo (R13a).
- **Catálogo fechado de tipos de contrato**, exatamente a recusa de personalização que ele
  fez (R3) — falta comportamento em três dos seis tipos, mas o princípio está implementado.
- **A unidade do consumo já segue o tipo do contrato** — horas para banco de horas, reais
  para crédito (R18a). É a regra que costuma sair errada, e está certa.
- **Filas, SLAs, serviços, classificação, classes de ativo e agentes** administrados pelo
  console sem cadastro paralelo — a base do bloco de configuração que ele pediu.
- **A arquitetura de usuário único do cliente já é a correta** (R2): existe um só cadastro
  de pessoa, e a listagem do portal não filtra por canal de origem. O que falta é o caminho
  de e-mail existir.

---

# Bloco 1 — Cadastro do cliente

> *"Toda vez que entra um contrato novo… a primeira coisa que eu vou fazer é cadastrar o
> cliente. Então essa tela é uma das telas mais importantes."* — 00:49

## R1 — Cadastro de cliente

![Kleber no momento em que descreve o cadastro de cliente](assets/kleber/r01-cadastro-cliente.jpg)

*00:49 — "A primeira coisa que eu vou fazer é cadastrar o cliente aqui. Então essa tela é uma das telas mais importantes."*{: .legenda }

**Estado: PARCIAL**{: .estado-parcial }

### O que ele pediu

Assistente **passo a passo** que, ao terminar, cai numa **tela de edição**. Campos: logo,
nome fantasia, dados cadastrais, **endereço** e **contato** (01:10).

### Onde estamos

O onboarding de cliente existe e é real: `POST /v1/admin/tenants` orquestra
`onboarding_service.onboard()`, com lista e detalhe no console. As abas de Agentes,
Faturas, Conhecimento, Catálogo, Identidade visual e Novo contrato já estão na ficha.

### O que falta

| Lacuna | Consequência para quem opera |
|---|---|
| Não existe endpoint nem tela de **edição** — o router só tem criar, listar e ver | Errou o CNPJ na criação? Não há como corrigir pelo console |
| **Endereço e contato não existem** como dado, nem em `gerti.tenant` nem no Znuny (a op GI grava só ID + nome) | Um dado que o Kleber considera cadastral básico não tem onde morar |
| O cadastro é um formulário único, não um assistente com validação por etapa | Divergência de expectativa, não de função |
| Logo é **URL digitada**, não upload | Força o operador a hospedar a imagem em outro lugar antes |
| Não há aba de **chamados do cliente** na ficha (o backend já suporta o filtro) | Falta a visão que ele cita em 02:59 |

### Tarefas

| # | Tarefa | Camada | Pronto quando |
|---|---|---|---|
| T-R1.1 | Estender `gerti.tenant` com endereço e contato | migration | `upgrade head` limpo, colunas nullable, RLS intacta |
| T-R1.2 | Expor `PUT /v1/admin/tenants/{id}` | sidecar | 200 com o cadastro atualizado; `subdomain` e `znuny_customer_id` imutáveis (422) |
| T-R1.3 | Propagar endereço/contato ao Znuny (`CustomerCompanyUpdate`) | znuny GI | `perl -c` verde no build; grava `Street/Zip/City` no `customer_company` |
| T-R1.4 | Converter `/clientes/novo` em assistente de 3 etapas | admin | Não avança com etapa inválida; erro em português |
| T-R1.5 | Tela de edição do cliente | admin | Campos imutáveis desabilitados com explicação |
| T-R1.6 | Aba "Chamados" na ficha do cliente | admin | Lista os chamados daquele cliente, com estado vazio e de erro |

### Termos de aceite

| # | Termo de aceite | Como se prova |
|---|---|---|
| A1.1 | O operador corrige razão social, documento, endereço e contato de um cliente já cadastrado, e a correção persiste após recarregar | V-R1.1 (pytest) + V-R1.7 (e2e) |
| A1.2 | O subdomínio de um cliente **não** pode ser alterado depois de criado, e a tentativa é recusada com explicação | V-R1.2 (pytest, 422) |
| A1.3 | O cadastro percorre etapas e recusa avançar com dado obrigatório faltando | V-R1.5 (vitest) |
| A1.4 | Endereço gravado no console aparece também no cadastro da empresa dentro do Znuny | V-R1.3 + conferência manual no painel técnico |
| A1.5 | A ficha do cliente mostra os chamados daquele cliente | V-R1.7 (e2e) |

### Testes de validação

| # | Tipo | Alvo | Asserção |
|---|---|---|---|
| V-R1.1 | pytest | `tests/test_admin_tenants.py` | `PUT` com nova razão social e cidade → 200; `GET` devolve os dois campos alterados |
| V-R1.2 | pytest | idem | `PUT` alterando `subdomain` → **422**; valor no banco permanece o original |
| V-R1.3 | pytest | idem | `PUT` em id inexistente → **404**; sem cookie → **401**; com cookie de cliente → **401** |
| V-R1.4 | pytest | `tests/test_migration_0027_tenant_address.py` (novo) | Tenant antigo sem endereço continua inserível; as 10 colunas existem |
| V-R1.5 | vitest | `test/tenant-wizard.test.ts` (novo) | `canAdvance` sem documento → `false` com mensagem; CEP normalizado só com dígitos |
| V-R1.6 | vitest | `test/tenant-edit-proxy.test.ts` (novo) | Proxy com id não-UUID → 404 **sem** chamar o sidecar |
| V-R1.7 | e2e | `test/e2e/cliente-editar.spec.ts` (novo) | Criar → editar cidade → recarregar → cidade persistida |

### Decisões abertas

- **Quem é dono do endereço:** a nossa base (`gerti.tenant`), o Znuny (`customer_company`),
  ou a nossa base espelhando no Znuny? A terceira segue o padrão já usado no branding, mas
  cria duplicidade consciente. **Precisa da tua decisão antes de T-R1.1.**
- **Upload de logo** exige storage de arquivo, que não existe na stack de produção hoje.
  Manter URL até haver decisão é aceitável.

---

## R2 — Usuário único do cliente (portal **e** e-mail)

![Kleber no momento em que descreve o problema dos cadastros duplicados](assets/kleber/r02-usuario-unico.jpg)

*02:14 — "Não é melhor a gente cadastrar um usuário único e dar acesso ao portal, deixar esse cara, todo o usuário do cliente já é automaticamente um solicitante?"*{: .legenda }

**Estado: PARCIAL**{: .estado-parcial }

> **Este é o requisito mais importante do vídeo.** Não é paridade com o TIFLUX — é a
> correção de um defeito que ele diz ter reclamado várias vezes sem ser atendido. Vale
> tratá-lo como o diferencial que se demonstra numa apresentação.

### O que ele pediu

No TIFLUX há dois cadastros para a mesma pessoa: "usuário do portal" e "solicitante de
e-mail". A consequência, nas palavras dele (02:01):

> *"Quando a pessoa manda e-mail, os tickets que ela mandou por e-mail não vai pro portal.
> Então isso é um defeito na plataforma que a gente já falou diversas vezes."*

Campos do cadastro: **nome, e-mail, telefone, ramal, ativo/inativo** (02:27), mais a chave
**"libera tickets por e-mail"** (01:44).

### Onde estamos — a parte boa

A arquitetura já está certa, e isso merece ser dito com precisão:

- Existe **um único** cadastro de pessoa do cliente — o `CustomerUser` do Znuny, com login
  igual ao e-mail. Não há tabela paralela de "solicitante".
- A listagem do portal busca por **login do usuário** ou por **empresa** — ela **não filtra
  por canal de origem** (`TicketSearch.pm:35-40`).
- Consequência: **se** um chamado entrar por e-mail com o login daquela pessoa, ele aparece
  no portal dela **sem nenhuma mudança de código**.

### Onde estamos — a parte incômoda

| Lacuna | Consequência |
|---|---|
| **Não existe nenhuma ingestão de e-mail configurada** — zero contas de recebimento em toda a stack | O cenário do Kleber hoje não é reproduzível *nem para falhar*. O diferencial está pronto no papel e inexistente na prática |
| Um chamado que entrasse por e-mail **nasceria sem contrato vinculado** | Ver o alerta abaixo — é o risco mais caro do documento |
| Telefone, ramal e ativo/inativo não existem no cadastro; não há como desativar um usuário | Falta o cadastro que ele descreve em 02:27 |
| A chave "libera tickets por e-mail" não existe | — |
| A ficha do cliente lista usuários da **nossa** tabela de papéis, não do Znuny | Usuário criado direto no Znuny é invisível no console |
| Não há tela para adicionar usuário depois do onboarding (o endpoint existe, o proxy não) | Só dá para cadastrar gente no momento da criação do cliente |

> **Alerta — ligar e-mail sem T-R2.3 faz a Gerti perder faturamento em silêncio.**
> O vínculo chamado↔contrato só é criado quando o chamado nasce pelo portal. O
> processamento de consumo descarta lançamentos de chamados sem vínculo **e avança o
> cursor mesmo assim** (`reconciliation_service.py:105-109`). Ou seja: hora trabalhada em
> chamado que entrou por e-mail seria perdida, sem erro e sem aviso. A ordem correta é
> **T-R2.3 antes de T-R2.6**, nunca o contrário.

### Tarefas

| # | Tarefa | Camada | Pronto quando |
|---|---|---|---|
| T-R2.1 | Cadastro rico de usuário (telefone, ramal, ativo, flag de e-mail) | znuny + sidecar + migration | Criar e editar aceitam os novos campos; `perl -c` verde |
| T-R2.2 | Listar usuários lendo do Znuny como fonte de verdade | znuny + sidecar | Usuário criado direto no Znuny aparece no console |
| T-R2.3 | **Vincular contrato a chamado originado por e-mail** | sidecar | Lançamento sem vínculo gera vínculo automático (1 contrato ativo) ou pendência auditável (0 ou ≥2) — nunca silêncio |
| T-R2.4 | Alinhar a guarda do detalhe de chamado ao escopo da lista | sidecar + znuny | Helpdesk pedindo id de colega → 404 |
| T-R2.5 | Tela de usuários do cliente (listar/adicionar/editar/desativar) | admin | Um único formulário por pessoa, dizendo explicitamente que o cadastro serve para portal **e** e-mail |
| T-R2.6 | Configurar ingestão de e-mail (pré-requisito do diferencial) | znuny | E-mail de um usuário conhecido vira chamado com o login dele |

### Termos de aceite

| # | Termo de aceite | Como se prova |
|---|---|---|
| A2.1 | **A mesma pessoa é cadastrada uma única vez** e passa a poder abrir chamado pelo portal e por e-mail, sem segundo cadastro | V-R2.1 + V-R2.8 |
| A2.2 | **Um chamado aberto por e-mail aparece no portal do autor**, ao lado dos que ele abriu pelo portal | V-R2.2 (automatizado) e V-R2.8 (ao vivo) — *este é o aceite que encerra a reclamação do Kleber* |
| A2.3 | Hora lançada em chamado que entrou por e-mail **é faturada**, ou fica registrada como pendência visível — nunca some | V-R2.3 |
| A2.4 | O cadastro guarda telefone e ramal, e o usuário pode ser desativado sem ser apagado | V-R2.1 + V-R2.6 |
| A2.5 | Usuário criado direto no Znuny aparece na lista do console | V-R2.2 |
| A2.6 | Um usuário comum **não** consegue abrir, por id, chamado de um colega que não vê na própria lista | V-R2.4 (negativo) |

### Testes de validação

| # | Tipo | Alvo | Asserção |
|---|---|---|---|
| V-R2.1 | pytest | `tests/test_tenant_users_router.py` (novo) | Criar usuário com telefone e ramal → 201; listagem devolve os dois campos |
| V-R2.2 | pytest | estende `tests/test_tickets_router.py` | Dois chamados do **mesmo** login — um do portal, um de e-mail — → **ambos** na resposta de `/v1/tickets` |
| V-R2.3 | pytest | estende `tests/test_reconciliation_service.py` | Lançamento em chamado sem vínculo, tenant com 1 contrato ativo → vincula e debita. Com 2 contratos → nenhum débito, **pendência registrada**, cursor não avança |
| V-R2.4 | pytest | estende `tests/test_tickets_router.py` | Helpdesk pedindo chamado de colega da mesma empresa → **404** (hoje retorna 200) |
| V-R2.5 | pytest | idem | Rotas de usuário sem cookie de agente → 401; com cookie de cliente → 401 |
| V-R2.6 | vitest | `test/tenant-users.test.ts` (novo) | E-mail inválido recusado; payload de edição nunca carrega senha; desativação exige o e-mail digitado |
| V-R2.7 | vitest | idem | Proxy com login contendo `../` → 404 sem chamar o sidecar |
| V-R2.8 | manual | roteiro de homologação | E-mail real de um usuário conhecido → vira chamado → o autor o vê no portal com o contrato vinculado |

### Decisões abertas

- **Fonte de verdade do usuário:** o Znuny (identidade) com a nossa base guardando só papel
  e flags — recomendado, resolve o "usuário criado no Znuny some do console" — ou a nossa
  base como dona, espelhando no Znuny. **Bloqueia T-R2.2.**
- **Remetente desconhecido:** e-mail de alguém não cadastrado deve criar usuário
  automaticamente, ser recusado, ou ser aceito só se o domínio estiver autorizado para
  aquele cliente? A terceira é o que o próprio Kleber descreve em 06:19, e é a
  recomendação — mas depende do R9. **Bloqueia T-R2.6.**
- **Comportamento do cursor de faturamento** em T-R2.3: alterar o avanço do cursor mexe em
  código financeiro em produção. Alternativa menos invasiva: manter o avanço e gravar as
  entradas órfãs numa tabela de pendência, reprocessando quando o vínculo aparecer.

---

## R5 — Relacionamentos: quais filas cada cliente acessa

![Kleber no momento em que descreve as filas por cliente](assets/kleber/r05-filas-por-cliente.jpg)

*04:03 — "Aqui a gente vai falar quais filas de atendimento o cara vai ter acesso. Então a gente tem uma fila padrão. Tudo que entra por e-mail vem pra essa fila."*{: .legenda }

**Estado: PARCIAL**{: .estado-parcial }

### O que ele pediu

Por cliente, definir a quais filas ele tem acesso. Uma **fila padrão** que recebe tudo que
entra por e-mail, onde o analista N1 classifica entre solicitação e incidente; uma fila de
**chamados preventivos**; uma fila **IMAC** para movimentação de dispositivos. Filas
personalizáveis, com **técnicos associados** a cada uma — *"tem toda uma estratégia de
permissionamento lá"* (04:39).

### Onde estamos

O cadastro de filas no Znuny já é feito pelo console, ao vivo (tela `/znuny/filas`). A
associação técnico↔fila também existe, indiretamente: fila pertence a um grupo, e agentes
são associados a grupos — mas não há uma tela que mostre isso como uma coisa só.

### O que falta

| Lacuna | Consequência |
|---|---|
| **A associação cliente↔fila não existe em nenhuma tabela** | Não dá para dizer "a Aurora acessa Suporte, IMAC e Preventivo" |
| A fila padrão é a string `'Raw'` **fixa no código** (`TicketCreate.pm:67`) | Todo chamado de todo cliente cai na mesma fila, e isso não é configurável |
| Não há tela que responda "quem atende esta fila?" | A "estratégia de permissionamento" fica espalhada entre duas telas |

### Tarefas

| # | Tarefa | Camada | Pronto quando |
|---|---|---|---|
| T-R5.1 | Tabela de associação cliente↔fila com marcação de padrão | migration | No máximo uma fila padrão por cliente, garantido no banco |
| T-R5.2 | `GET/PUT /v1/admin/tenants/{id}/queues` | sidecar | Fila inexistente no Znuny → 422; gravação auditada |
| T-R5.3 | Aplicar a fila padrão do cliente na abertura de chamado | sidecar | Chamado do cliente A nasce na fila padrão de A, e `Raw` deixa de ser destino silencioso |
| T-R5.4 | Tela "Relacionamentos" na ficha do cliente | admin | Multi-seleção de filas, uma marcada como padrão, e quem atende cada uma |
| T-R5.5 | Coluna "atendida por" na tela global de filas | admin | Cada fila mostra o grupo e a contagem de agentes |

### Termos de aceite

| # | Termo de aceite | Como se prova |
|---|---|---|
| A5.1 | O operador escolhe quais filas cada cliente acessa e marca **uma** como padrão | V-R5.1 |
| A5.2 | Chamado aberto por um cliente nasce **na fila padrão daquele cliente** | V-R5.4 + V-R5.6 |
| A5.3 | Tentar associar fila que não existe no Znuny é recusado, sem gravar nada | V-R5.2 (negativo) |
| A5.4 | A configuração de filas de um cliente é invisível para outro cliente no banco | V-R5.3 (isolamento) |
| A5.5 | O operador vê, por fila, quais técnicos a atendem | V-R5.5 |

### Testes de validação

| # | Tipo | Alvo | Asserção |
|---|---|---|---|
| V-R5.1 | pytest | `tests/test_admin_tenant_queues_router.py` (novo) | Associar filas 3 e 5 com a 3 como padrão → `GET` devolve as duas, padrão só na 3 |
| V-R5.2 | pytest | idem | Fila inexistente → **422** e **nenhuma** linha gravada; duas filas marcadas como padrão → 422 |
| V-R5.3 | pytest | `tests/test_rls_tenant_queue.py` (novo) | Sob a sessão do cliente A, a consulta não retorna nenhuma linha de B; sem cliente definido → 0 linhas |
| V-R5.4 | pytest | estende `tests/test_ticketing_service.py` | Abrir chamado sem fila → payload contém a fila padrão do cliente, **não** `Raw`; fila não associada → 422 |
| V-R5.5 | vitest | `test/tenant-queues.test.ts` (novo) | Seleção vazia e seleção sem padrão são recusadas com mensagem |
| V-R5.6 | e2e | `test/e2e/cliente-filas.spec.ts` (novo) | Associar filas → abrir chamado pelo portal → chamado aparece na fila configurada |

### Decisões abertas

- **Onde mora a restrição:** numa tabela nossa (simples, mas o agente logado direto no Znuny
  não a enxerga) ou em grupos nativos do Znuny por cliente (paridade real, porém cria N
  grupos e mexe em configuração de risco alto). Recomendação: tabela nossa no primeiro
  momento, com a limitação declarada.
- Mudar a fila padrão `Raw` **altera onde chamados novos caem** num ambiente que já roda.
  Precisa de janela e aviso, não é ajuste silencioso.

---

## R7 — Aprovação de chamados (chave por cliente)

**Estado: AUSENTE**{: .estado-ausente }

### O que ele pediu

> *"Tem uma função de autorização de tickets, de aprovação, mas a gente não usa. Na verdade,
> na DataStone a gente utiliza: todo ticket passa, quando essa chave tá habilitada, vai pra
> um aprovador. Ele tem acesso ao portal, quando vem um ticket ele recebe um e-mail pra
> aprovar, ele entra lá no portal e aprova ou não aprova."* — 02:37

Note-se: **a Gerti não usa, mas um cliente dela usa.** É requisito real, gateado por chave
por cliente — não é item descartável.

### Onde estamos

O fluxo inteiro não existe. Há aprovação de *dispositivo* e de *glosa*, que são outros
domínios. Os papéis do portal são apenas administrador e helpdesk — não há papel de
aprovador.

### Tarefas

| # | Tarefa | Camada | Pronto quando |
|---|---|---|---|
| T-R7.1 | Modelo de aprovação (chave no cliente, papel aprovador, registro da decisão) | migration | Enum de papéis estendido sem quebrar os papéis existentes |
| T-R7.2 | Barrar o chamado na criação quando o cliente exige aprovação | sidecar + znuny | Chamado nasce em estado real de espera no Znuny — não "criado e escondido" |
| T-R7.3 | Endpoint de aprovar/reprovar | sidecar | Decisão é única: segunda chamada → 409 |
| T-R7.4 | Notificar o aprovador | sidecar | Aprovador vê a pendência nas notificações do portal |
| T-R7.5 | Chave no console + fila de aprovação no portal | admin + portal | Reprovar exige motivo |
| T-R7.6 | Definir o estado Znuny de "aguardando aprovação" | znuny | Estado existe após provisionamento, sem passo manual |

### Termos de aceite

| # | Termo de aceite | Como se prova |
|---|---|---|
| A7.1 | Com a chave desligada, nada muda no fluxo atual de abertura de chamado | V-R7.1 |
| A7.2 | Com a chave ligada, o chamado fica **aguardando aprovação** e o aprovador é avisado | V-R7.1 + V-R7.2 |
| A7.3 | Só quem tem papel de aprovador decide; helpdesk é recusado | V-R7.3 (negativo) |
| A7.4 | A decisão é única — não se aprova duas vezes | V-R7.3 (409) |
| A7.5 | Aprovador de um cliente **não** decide chamado de outro cliente, e a resposta não revela que o chamado existe | V-R7.4 (negativo, 404) |
| A7.6 | Reprovar sem motivo é recusado | V-R7.3 (422) |

### Testes de validação

| # | Tipo | Alvo | Asserção |
|---|---|---|---|
| V-R7.1 | pytest | `tests/test_ticket_approval_service.py` (novo) | Chave desligada → sem registro de aprovação; ligada → chamado `pending` + 1 registro |
| V-R7.2 | pytest | idem | Aprovador decide "aprovado" → 200 e o Znuny recebe a mudança de estado |
| V-R7.3 | pytest | idem | Helpdesk decidindo → 403; decisão repetida → 409; reprovação sem motivo → 422 |
| V-R7.4 | pytest | idem | Aprovador do cliente B decidindo chamado do cliente A → **404** |
| V-R7.5 | pytest | `tests/test_rls_ticket_approval.py` (novo) | Isolamento da tabela de aprovação entre clientes |
| V-R7.6 | vitest | `test/approval.test.ts` (novo) | Só aprovador/admin podem decidir; reprovação sem motivo bloqueada na tela |
| V-R7.7 | e2e | `test/e2e/aprovacao.spec.ts` (novo) | Ligar a chave → abrir chamado → aprovador aprova → chamado sai da espera |

### Decisões abertas

- **Como representar "aguardando aprovação" no Znuny:** estado novo (mais limpo, afeta
  relatórios e SLA), fila de quarentena (não mexe em estados, mas polui as filas e confunde
  com o R5), ou campo dinâmico (impacto mínimo, porém o agente pode atender sem perceber
  que não foi aprovado). Recomendação: estado novo.
- **O relógio de SLA corre durante a espera?** Se correr, o cliente que demora a aprovar
  queima o SLA da Gerti. Isso provavelmente decide a pergunta anterior.
- **O aprovador pode ser alguém que não abre chamados?** Confirmar com o Kleber.

---

## R8 — Importações

**Estado: AUSENTE**{: .estado-ausente }

### O que ele pediu

> *"Tem as importações que a gente pode eventualmente fazer. Quero importar cadastros, quero
> importar cliente, quero importar usuário do cliente."* — 05:38

O peso real disso está em outro trecho: ele cita **60 clientes cadastrados e 43 contratos
ativos** (09:32). Sem importação, a migração do TIFLUX é feita cliente a cliente, na mão.

### Onde estamos

Não existe nenhuma forma de carga em lote. O que mais se aproxima são scripts de semente
para demonstração, que não servem para dado de cliente. A peça reaproveitável é que o
onboarding **já é idempotente** — reexecutar não duplica.

### Tarefas

| # | Tarefa | Camada | Pronto quando |
|---|---|---|---|
| T-R8.1 | Validação de importação (simulação, sem gravar) | sidecar | Cabeçalho errado → 422 com as colunas esperadas; nenhuma escrita |
| T-R8.2 | Execução idempotente por linha | sidecar | Reexecutar o mesmo arquivo → zero duplicata |
| T-R8.3 | Limites e proteção | sidecar | Arquivo acima do teto → 413; coluna de senha no arquivo → 422 |
| T-R8.4 | Tela de importações | admin | Baixar modelo → subir → **pré-visualizar** → confirmar com a contagem |

### Termos de aceite

| # | Termo de aceite | Como se prova |
|---|---|---|
| A8.1 | O operador vê o resultado da importação **antes** de gravar qualquer coisa | V-R8.1 |
| A8.2 | Importar o mesmo arquivo duas vezes não cria cliente duplicado | V-R8.2 |
| A8.3 | Uma linha com erro não impede as demais, e o erro aponta o número da linha | V-R8.3 |
| A8.4 | Senha nunca trafega em planilha | V-R8.3 (422) |
| A8.5 | Conteúdo de planilha nunca é interpretado como fórmula ou HTML na tela | V-R8.6 |

### Testes de validação

| # | Tipo | Alvo | Asserção |
|---|---|---|---|
| V-R8.1 | pytest | `tests/test_admin_import_router.py` (novo) | Simulação de 3 linhas válidas → 200 e **zero** chamadas de escrita |
| V-R8.2 | pytest | idem | Executar → 3 criados; repetir → 0 criados, 3 ignorados, total no banco continua 3 |
| V-R8.3 | pytest | idem | Linha 2 conflitante → falha isolada citando a linha 2, linhas 1 e 3 criadas |
| V-R8.4 | pytest | idem | Sem cookie de agente → 401; com cookie de cliente → 401 |
| V-R8.5 | pytest | idem | Tipo fora da lista permitida → 404 |
| V-R8.6 | vitest | `test/import-csv.test.ts` (novo) | Célula com fórmula é tratada como texto e nunca renderizada como HTML |

### Decisões abertas

- **Formato:** CSV (simples, e o Kleber já exporta do TIFLUX) ou XLSX (o que o pessoal usa,
  mas exige dependência nova). Recomendação: CSV com modelo baixável; XLSX depois.
- **Senha na importação:** gerar e exibir uma vez, ou criar sem senha e enviar convite por
  e-mail — o convite depende de e-mail funcionando (R2/T-R2.6).


---

# Bloco 2 — Contrato do cliente

## R3 — Tipos de contrato (catálogo fechado)

![Kleber no momento em que recusa contratos personalizáveis](assets/kleber/r03-tipos-contrato.jpg)

*03:26 — "A TIFLUX permite personalizar os contratos, mas eu não acho legal isso aqui, cara. Acho que a plataforma tem que ter os modelos e o contrato tem que funcionar conforme os fluxos estabelecidos na plataforma."*{: .legenda }

**Estado: PARCIAL**{: .estado-parcial }

### O que ele pediu

Os tipos que ele usa (03:15): **livre, crédito, crédito compartilhado, limite de horas,
SaaS, contrato com limite de atendimento** — mais um que ele mesmo criou, "intercâmbio".

E, logo em seguida, uma **recusa de produto explícita**: contrato não deve ser
programável pelo usuário. A plataforma oferece modelos; o contrato obedece aos fluxos.

### Onde estamos — o que está certo

Essa é uma das raras vezes em que o pedido do cliente e a arquitetura já existente
coincidem. O catálogo é fechado em **quatro camadas independentes**: tipo nativo no banco,
enumeração no código, contrato de API que só aceita os valores conhecidos, e a interface
que espelha os mesmos seis — sem campo livre em lugar nenhum.

### Onde estamos — o que é só rótulo

| Tipo citado | Situação real |
|---|---|
| **crédito** | Existe e funciona: saldo em reais é debitado |
| **limite de horas** | Existe e funciona: saldo em horas, com franquia e excedente no fechamento |
| **crédito compartilhado** | **Nome existe, comportamento não.** O saldo é calculado sobre o valor do próprio contrato, ignorando o pool comum — dois contratos "compartilhados" consomem saldos separados |
| **limite de atendimento** | **Nome existe, nunca consome.** O saldo conta eventos de um tipo que nenhum produtor gera — o saldo nunca baixa, por mais atendimentos que entrem |
| **SaaS** | Existe como rótulo, sem cobrança recorrente do valor fixo |
| **livre** | **Não existe.** Não há tipo pós-pago que fature hora a hora sem saldo prévio |

Também não há **teste-guarda** provando que o catálogo é fechado: a suíte exercita os seis
tipos válidos, mas nenhum caso com tipo desconhecido. Uma refatoração que trocasse o
contrato de API por texto livre passaria despercebida — exatamente o que o Kleber recusou.

### Tarefas

| # | Tarefa | Camada | Pronto quando |
|---|---|---|---|
| T-R3.1 | Teste-guarda de catálogo fechado (sem código de produção) | testes | Tipo fora dos seis → 422; o teste falha se alguém abrir o contrato de API |
| T-R3.2 | Ligar crédito compartilhado ao pool comum | domínio | Consumo num contrato reduz o saldo exibido no irmão |
| T-R3.3 | Fazer "limite de atendimento" consumir de verdade | domínio + worker | Um atendimento reduz o saldo em 1 serviço |
| T-R3.4 | Decidir e, se aprovado, introduzir o tipo "livre" | modelo + domínio + UI | Acumula consumo faturável, sem saldo e sem alerta de saldo baixo |

### Termos de aceite

| # | Termo de aceite | Como se prova |
|---|---|---|
| A3.1 | Não é possível criar contrato de um tipo fora do catálogo — pela tela **ou** por chamada direta à API | V-R3.1 |
| A3.2 | Dois contratos marcados como crédito compartilhado consomem **o mesmo** saldo | V-R3.2 |
| A3.3 | Contrato por limite de atendimento perde saldo a cada atendimento | V-R3.3 |
| A3.4 | Cada um dos seis tipos tem comportamento de saldo definido e demonstrável — nenhum é apenas rótulo | V-R3.2 + V-R3.3 + a decisão sobre SaaS |

### Testes de validação

| # | Tipo | Alvo | Asserção |
|---|---|---|---|
| V-R3.1 | pytest | `tests/test_admin_contracts.py` e `test_enums.py` | Criar contrato com tipo `"intercambio"` → **422**, nenhuma linha gravada; o conjunto de tipos é exatamente os seis conhecidos |
| V-R3.2 | pytest | `tests/test_consumption_service.py` | Pool de R$ 1.000, contratos A e B no mesmo pool; consumo de R$ 300 em A → saldo **700 em ambos** (hoje B mostraria 1.000) |
| V-R3.3 | pytest | idem | Contrato com 10 atendimentos, 2 reconciliados → saldo 8 |
| V-R3.4 | vitest | `test/contract-types.test.ts` (novo) | A lista de tipos da interface é idêntica à do backend; tipo desconhecido nunca é criado pela tela |

### Decisões abertas

- **"Livre" e "intercâmbio" precisam da decisão do Kleber antes de virarem tipo.**
  Acrescentar um valor ao catálogo é praticamente irreversível no banco, e cada novo valor
  amplia justamente o catálogo que ele quis manter fechado. Sugestão: mapear "intercâmbio"
  para um dos seis e documentar a equivalência.
- **"Compartilhado" é entre contratos do mesmo cliente**, e não entre clientes distintos —
  o isolamento por cliente torna a segunda hipótese impossível. Confirmar.

---

## R6 — Configuração de faturamento por cliente

**Estado: AUSENTE**{: .estado-ausente }

### O que ele pediu

> *"E aí a parte de faturamento do cliente, que são algumas configurações pra enviar SMS,
> pra enviar e-mail, com detalhamento. Se tiver integração com sistemas financeiros,
> aparece aqui."* — 04:43

### Onde estamos

Não existe configuração de faturamento por cliente, e **nada no sistema envia e-mail ou
SMS** — a notificação de fatura emitida grava uma linha na caixa de avisos do portal e para
por aí. Existem preferências de "receber e-mail" no cadastro de cada usuário, mas nenhum
consumidor as lê para enviar coisa alguma. A integração financeira existe apenas na página
pública de contratação, nunca a partir de uma fatura de ciclo.

### Tarefas

| # | Tarefa | Camada | Pronto quando |
|---|---|---|---|
| T-R6.1 | Modelar a configuração de faturamento por cliente | migration | Isolamento entre clientes provado por teste |
| T-R6.2 | Endpoints de leitura e gravação da configuração | sidecar | Defaults seguros (tudo desligado); e-mail inválido → 422; gravação auditada |
| T-R6.3 | Canal de envio de e-mail, atrás de chave | integração | Com a chave desligada nada sai; falha de envio **não** derruba a emissão da fatura |
| T-R6.4 | SMS com transporte trocável — mock de console primeiro | integração | Aviso curto, sem dado sensível; trocar por provedor real é chave, não código |
| T-R6.5 | Aba "Faturamento" na ficha do cliente | admin | Estado salvo reflete após recarregar |

### Termos de aceite

| # | Termo de aceite | Como se prova |
|---|---|---|
| A6.1 | O operador define, por cliente, se a fatura vai por e-mail, para quem, e com qual nível de detalhe | V-R6.2 |
| A6.2 | Emitir fatura de um cliente configurado envia **um** e-mail com o PDF anexado | V-R6.3 |
| A6.3 | Falha no envio **não** impede a emissão da fatura | V-R6.3 |
| A6.4 | A configuração de um cliente é invisível para outro | V-R6.1 |
| A6.5 | Com a chave global desligada, nenhum e-mail sai — nem por engano | V-R6.3 |
| A6.6 | O SMS percorre o fluxo inteiro e a mensagem que sairia fica visível no log; a tela diz com todas as letras que o envio está **em modo simulado** | V-R6.6 |
| A6.7 | Trocar o mock pelo provedor real é mudança de configuração — nenhuma alteração no fluxo de fatura nem na tela | V-R6.6 (transporte injetado) |

### Testes de validação

| # | Tipo | Alvo | Asserção |
|---|---|---|---|
| V-R6.1 | pytest | `tests/test_rls_contract_tables.py` | Configuração do cliente A invisível na sessão do cliente B |
| V-R6.2 | pytest | `tests/test_admin_billing_config_router.py` (novo) | Destinatário inválido → 422 citando o campo; gravação válida → o `GET` devolve exatamente o gravado |
| V-R6.3 | pytest | `tests/test_invoice_notification_producer.py` | Chave desligada → 0 envios; ligada → 1 envio cujo anexo começa com `%PDF-`; envio que falha → fatura continua gravada |
| V-R6.4 | vitest | `test/billing-config.test.ts` (novo) | Lista de destinatários normalizada (sem duplicata, sem vazio) |
| V-R6.5 | manual | homologação | Ligar para um cliente, emitir fatura, confirmar chegada; desligar, emitir outra, confirmar que nada chega |
| V-R6.6 | pytest | `tests/test_sms_transport.py` (novo) | Com SMS ligado → o transporte falso recebe **1** chamada, com o destinatário mascarado e sem valor sensível; desligado → **0** chamadas; transporte que levanta exceção → a fatura **continua emitida** |

### Decisões abertas

- **Quem envia o e-mail da fatura:** o Znuny (dono da comunicação com o cliente, mas exige
  operação nova) ou o sistema de contratos (mais simples, não toca o núcleo). Recomendação:
  o sistema de contratos — a fatura não pertence a nenhuma fila de atendimento.
- **SMS: provedor ainda não escolhido** (Twilio é o candidato), mas o requisito **não fica
  parado** — o envio nasce atrás de uma interface de transporte, e o primeiro transporte é
  um mock que registra no log a mensagem que teria saído. Quando o provedor entrar, muda a
  chave, não o fluxo. Vale um cuidado: SMS custa por mensagem e o mock esconde isso, então
  a tela precisa dizer quando o envio está em modo simulado, e o teste de "zero envios com
  a chave desligada" é obrigatório.
- **"Com detalhamento" precisa de definição:** é o PDF anexado, o corpo do e-mail com as
  linhas, ou um link para o portal?

---

# Bloco 3 — Configurações padrão da plataforma

> *"A outra tela que é importante pra gente é isso aqui — as configurações padrão da
> plataforma."* — 05:06
>
> Ele mesmo já fez a tradução para o nosso contexto: *"as configurações têm que ser
> focadas no Znuny — ele é de um jeito"* (05:29), e *"o OTRS trata como mesa, mas no Znuny
> é tratado como fila"* (08:10). Ou seja, ele não espera cópia do TIFLUX; espera equivalência.

## R9 — E-mail: entrada e saída amarradas por fila

![Kleber no momento em que descreve a invariante de entrada e saída](assets/kleber/r09-email-entrada-saida.jpg)

*06:38 — "Se entrou pelo suporte, tem que sair pelo suporte. Se entrou pelo financeiro, tem que sair pelo financeiro. Se entrou por um DPO, tem que voltar também pelo encarregado de dados."*{: .legenda }

**Estado: AUSENTE — e a saída de e-mail está quebrada na infraestrutura**{: .estado-ausente }

### O que ele pediu

Quatro coisas distintas, todas em 05:57–07:00:

1. **Contas de recebimento** mapeadas para filas ("quando enviar para esse e-mail, vai para
   a fila X").
2. **Endereços de resposta por fila** — DPO usa um, suporte outro, administrativo outro.
3. A **invariante**: entrou por um canal, sai pelo mesmo canal.
4. **Remetente específico para certos clientes**, e **visão centralizada dos domínios
   autorizados** de todos os clientes.

### Onde estamos

Nenhuma dessas configurações é acessível pelo console — só pelo painel técnico do Znuny.
Mas há três descobertas que mudam o desenho da solução:

**A boa:** a invariante que ele pede **é nativa do Znuny**. O remetente de saída sai do
endereço de sistema vinculado à fila do chamado. Configurado corretamente, funciona sem
uma linha de código nossa.

**A ressalva:** essa amarração é **pela fila atual**, não pela porta de entrada. No fluxo
que ele mesmo descreve — tudo cai na fila padrão, o N1 classifica e **move** — a resposta
passa a sair pelo endereço da fila de destino. Não é defeito, é o desenho do Znuny, e ele
precisa saber disso antes de aceitar o requisito.

**A ruim:**

> **O Znuny não envia e-mail nenhum hoje.** O padrão do produto é entregar via `sendmail`,
> e **não existe esse programa na imagem** — verificado dentro do container. O
> `Config.pm.tmpl` também não configura nenhum servidor de SMTP. A **entrada** está pronta
> (a tarefa de busca de caixas já roda no daemon a cada 10 minutos); a **saída** não sai.
> Sem resolver isso, nada do R9 é sequer demonstrável — e, mais grave, notificação de
> chamado e resposta ao cliente também não saem.

Há ainda um bug que atravessa R9 e R10, tratado no R10 abaixo: **criar fila pelo console
falha sempre**, porque o endereço de resposta é obrigatório e a tela não o envia.

### Tarefas

| # | Tarefa | Camada | Pronto quando |
|---|---|---|---|
| T-R9.1 | Configurar transporte de saída (SMTP), sem servidor local | znuny/infra | Resposta a um chamado chega de fato numa caixa de teste; segredo só no arquivo de ambiente protegido |
| T-R9.2 | Expor endereços de sistema e as listas de apoio que faltam à fila | znuny GI | Endereços reais da instância listados; a tela de fila recebe as opções |
| T-R9.3 | **Corrigir o bug de criação de fila** | admin | Criar fila pelo console retorna sucesso e o endereço escolhido fica gravado |
| T-R9.4 | Operação dedicada para contas de recebimento, com o segredo blindado | znuny GI | Resposta **nunca** contém campo de senha |
| T-R9.5 | Operação para filtros de domínio (domínio → cliente) | znuny GI | E-mail de um domínio configurado cai como chamado do cliente certo |
| T-R9.6 | Rotas de e-mail no backend, sob sessão de agente | sidecar | 401 sem sessão; auditoria sem nenhum segredo |
| T-R9.7 | Tela de e-mail com 3 abas: recebimento · resposta · domínios autorizados | admin | As três abas listam dado real; senha é campo write-only |
| T-R9.8 | Decidir "remetente por cliente" | decisão | Ver abaixo |

### Termos de aceite

| # | Termo de aceite | Como se prova |
|---|---|---|
| A9.1 | **O Znuny envia e-mail** — resposta a um chamado chega na caixa do cliente | V-R9.5 (ao vivo) |
| A9.2 | O operador cadastra conta de recebimento e a amarra a uma fila, pelo console | V-R9.5 |
| A9.3 | **Chamado que entrou pelo suporte é respondido pelo endereço do suporte; o do DPO, pelo endereço do DPO** — conferido no cabeçalho da mensagem recebida | V-R9.5 (ao vivo) |
| A9.4 | A senha de uma conta de e-mail **nunca** aparece em resposta de sistema, tela ou auditoria | V-R9.2 |
| A9.5 | Existe uma tela única que mostra todos os domínios autorizados e a que cliente cada um pertence | V-R9.6 |
| A9.6 | **Aceite com ressalva registrada:** mover o chamado de fila muda o endereço de resposta — comportamento nativo, aceito conscientemente ou tratado | V-R9.5, segunda parte |

### Testes de validação

| # | Tipo | Alvo | Asserção |
|---|---|---|---|
| V-R9.1 | build | gate `perl -c` da imagem | Os módulos novos compilam; remover o registro de um deles **quebra** o build (prova de que o gate cobre) |
| V-R9.2 | pytest | `tests/test_admin_znuny_mail_router.py` (novo) | Resposta do sistema **não contém** a senha nem a chave de senha, em nenhum nível do JSON |
| V-R9.3 | pytest | `tests/test_gi_routes_match_webservice.py` | Toda rota nova está declarada nos dois lados — foi esse teste que pegou um bug equivalente antes |
| V-R9.4 | vitest | `test/znuny-object.test.ts` | Payload de fila carrega os campos obrigatórios; rascunho sem endereço de resposta é recusado (regressão do bug) |
| V-R9.5 | manual | roteiro de homologação | Dois endereços em duas filas → e-mail para cada um cai na fila certa → resposta sai pelo endereço correspondente, conferido no cabeçalho. Depois **mover** o chamado e registrar a mudança de remetente |
| V-R9.6 | manual | idem | E-mail de um domínio configurado vira chamado do cliente certo, e o domínio aparece na tela centralizada |

### Decisões abertas

- **Expor ou não o cadastro de senha de caixa postal pelo console.** O Znuny guarda essa
  senha em texto claro no banco — é característica do produto, não nossa, mas expor a
  configuração significa assumir o risco. Mitigação: nunca trafegar a senha de volta e
  preferir autenticação moderna quando o provedor permitir.
- **Filtro de domínio não tem "invalidar", só apagar.** Isso colide com a regra do projeto
  de nunca excluir. Recomendação: aceitar a exclusão real **apenas** para este objeto,
  documentando a exceção e gravando o estado anterior completo na auditoria.
- **"Remetente por cliente"** não é nativo. Caminho barato e 100% nativo: **uma fila
  dedicada** para o cliente especial, com o endereço dele — resolve sem código, ao custo de
  multiplicar filas. Caminho caro: interferir no envio. **Levar as duas opções ao Kleber.**

---

## R10 — Mesas de serviço (= filas)

**Estado: PARCIAL — criar fila falha hoje**{: .estado-parcial }

### O que ele pediu

As filas que ele opera: suporte, solicitação, requisição, DPO, assuntos administrativos —
e ele mesmo traduz o vocabulário: *"o OTRS trata como mesa, mas no Znuny é tratado como
fila"* (08:10).

### Onde estamos

Listar, editar e invalidar filas pelo console já funciona, ao vivo, e foi verificado em
homologação. A associação técnico↔fila existe de forma indireta (fila pertence a um grupo,
agentes pertencem a grupos). As telas já dizem "fila", alinhadas à tradução dele.

> **Bug confirmado:** criar fila pelo console **falha sempre**. O backend exige endereço de
> resposta, saudação e assinatura na criação (`AdminSpec.pm:67`), e a tela não envia nenhum
> dos três (`useZnunyObject.ts:214-229`). Nenhum teste pega porque todos simulam a
> integração. É defeito existente, não lacuna de requisito — e bloqueia o R9 junto.

### Tarefas

| # | Tarefa | Camada | Pronto quando |
|---|---|---|---|
| T-R10.1 | *(é a mesma de T-R9.2 + T-R9.3)* Destravar a criação de fila | znuny + admin | Não duplicar esforço — uma tarefa, dois requisitos |
| T-R10.2 | Coluna "quem atende" na lista de filas | admin | Cada fila mostra o grupo e os agentes; composição em memória, nada gravado |
| T-R10.3 | Rótulo "Filas (mesas de serviço)" no menu | admin | Remove atrito de vocabulário na demonstração |

### Termos de aceite

| # | Termo de aceite | Como se prova |
|---|---|---|
| A10.1 | **O operador cria uma fila nova pelo console e ela aparece no Znuny** | V-R10.3 |
| A10.2 | A tela de filas responde "quem atende esta fila" sem precisar de outra tela | V-R10.4 |
| A10.3 | Recusa do Znuny chega ao operador com a mensagem original, não como erro genérico | V-R10.2 |
| A10.4 | Fila nunca é excluída — apenas invalidada, e a tela diz isso | regressão já coberta |

### Testes de validação

| # | Tipo | Alvo | Asserção |
|---|---|---|---|
| V-R10.1 | vitest | `test/znuny-object.test.ts` | Igual a V-R9.4 — payload completo e validação do campo obrigatório |
| V-R10.2 | pytest | `tests/test_admin_znuny_router.py` | Recusa do Znuny na criação → **422 com a mensagem original**, nunca 500 |
| V-R10.3 | manual | homologação | Criar a fila DPO pelo console → ela aparece no Znuny nativo → agente fora do grupo não a enxerga |
| V-R10.4 | vitest | `test/znuny-queue-staff.test.ts` (novo) | Dado uma fila e dois agentes, só o do grupo certo é listado |

### Decisões abertas

Nenhuma de arquitetura. Confirmar apenas se a "estratégia de permissionamento" precisa de
granularidade além de grupo — hoje a associação é tudo-ou-nada (ver R14).

---

## R11 — Atividades agendadas / chamados recorrentes

![Kleber no momento em que descreve os chamados recorrentes](assets/kleber/r11-tickets-recorrentes.jpg)

*07:09 — "Verificação de backup, verificação de patches, vulnerabilidades, atualização de servidor… que acontecem uma vez, que acontecem toda semana, que acontecem todo mês. É uma agenda. Isso é importante também, porque é o dia a dia dos técnicos."*{: .legenda }

**Estado: AUSENTE**{: .estado-ausente }

### O que ele pediu

Agenda de atividades recorrentes que viram chamados automaticamente, com recorrência
**única, semanal ou mensal**. Ele enquadra isso como **o dia a dia dos técnicos** — não é
automação de bastidor, é a agenda de trabalho da equipe.

### Onde estamos

Não existe. E há uma conclusão técnica que evita semanas de trabalho na direção errada:

> **O mecanismo nativo candidato do Znuny não serve.** Foi avaliado no código-fonte da
> versão instalada e falha em três pontos independentes: ele **não cria** chamados (só age
> sobre chamados que encontra); **não sabe expressar "todo mês"** (só dia da semana e
> hora); e **não tem edição** — alterar significa apagar e recriar, o que conflita com a
> regra do projeto de nunca excluir.
>
> O caminho correto é o nosso processador de rotinas, que já roda com ciclo diário
> idempotente e sinal de vida. Há precedente: o motor de automação já foi decidido assim.

### Tarefas

| # | Tarefa | Camada | Pronto quando |
|---|---|---|---|
| T-R11.1 | Modelar tarefa recorrente e seus disparos | migration | Isolamento por cliente provado; registro de disparo garante que reiniciar não duplica chamado |
| T-R11.2 | Cálculo da próxima ocorrência (função pura) | domínio | Dia 31 em fevereiro resolve para o último dia do mês |
| T-R11.3 | Passo no processador: materializar as vencidas em chamados | domínio | Rodar duas vezes no mesmo dia gera **um** chamado, não dois |
| T-R11.4 | Cadastro e tela de atividades | sidecar + admin | "Verificação de backup — toda segunda, 08:00, fila Preventivos" com a próxima ocorrência à vista |
| T-R11.5 | Visão de agenda para o técnico | admin | Próximos 30 dias, com link para o chamado gerado |

### Termos de aceite

| # | Termo de aceite | Como se prova |
|---|---|---|
| A11.1 | O operador cadastra uma atividade que se repete **uma vez, toda semana ou todo mês** | V-R11.1 |
| A11.2 | No horário programado, o chamado **nasce sozinho** na fila e serviço corretos | V-R11.5 |
| A11.3 | Reiniciar o sistema **não duplica** o chamado do dia | V-R11.2 |
| A11.4 | Recorrência mensal em dia 29, 30 ou 31 não pula fevereiro nem falha | V-R11.1 |
| A11.5 | A atividade de um cliente é invisível para outro | V-R11.3 |
| A11.6 | O técnico enxerga a agenda dos próximos dias, não só o chamado avulso | V-R11.5 |

### Testes de validação

| # | Tipo | Alvo | Asserção |
|---|---|---|---|
| V-R11.1 | pytest | `tests/test_recurring_task_service.py` (novo) | Mensal dia 31 a partir de 31/01 → **28/02**; a partir de 28/02 → 31/03; "uma vez" desativa após disparar |
| V-R11.2 | pytest | `tests/test_recurring_worker.py` (novo) | Dois ciclos no mesmo dia → **exatamente uma** criação de chamado |
| V-R11.3 | pytest | `tests/test_rls_recurring_task.py` (novo) | Sob a sessão do cliente A, nenhuma tarefa de B é visível |
| V-R11.4 | vitest | `test/recurring-task.test.ts` (novo) | Rascunho inválido recusado; "toda segunda às 08:00" descrito em português |
| V-R11.5 | manual | homologação | Tarefa com horário 2 minutos à frente → o chamado existe no Znuny na fila certa e aparece no atendimento |

### Decisões abertas

- **Essas atividades consomem horas do contrato do cliente?** Isso muda o modelo. Manutenção
  preventiva pode ser cortesia contratual ou consumo faturável — é decisão comercial.
- **Fuso horário:** "toda segunda às 08:00" é 08:00 de quem? O processador roda em UTC.
  Guardar o fuso por tarefa evita a agenda escorregar no horário de verão.
- **Volume:** 43 contratos ativos × várias atividades cria um pico de chamados às 08:00 de
  segunda. Definir teto por ciclo.

---

## R12 — Catálogo de serviço (item e sub-item)

![Kleber no momento em que descreve os dois níveis do catálogo](assets/kleber/r12-catalogo-dois-niveis.jpg)

*07:53 — "Aqui a gente cadastra o item e o sub-item. Aqui só dá dois níveis."*{: .legenda }

**Estado: PARCIAL**{: .estado-parcial }

### O que ele pediu

Catálogo que define "o que eu vou ter no tipo de solicitação", em categorias como *acesso e
identidade*, *comunicação e colaboração*, *backup e recuperação de dados* — com **exatamente
dois níveis**: item e sub-item.

### Onde estamos — e um problema estrutural

Existem **dois catálogos paralelos**, ligados por texto:

- O **catálogo de serviços do Znuny**, hierárquico de verdade, é o que o SLA usa, o que
  aparece no formulário de chamado e o que sai em relatório. Tem tela com árvore e proteção
  contra ciclo — mas **profundidade ilimitada**: hoje dá para criar neto e bisneto, o que
  contraria o "só dá dois níveis".
- A **vitrine do portal**, que é a que o cliente vê para pedir serviço. A hierarquia dela é
  emulada por um campo de **categoria em texto livre**, e o vínculo com o catálogo do Znuny
  é feito por **comparação de nome**. Renomear o serviço no Znuny **quebra o vínculo em
  silêncio** — o formulário simplesmente aparece sem a seleção.

Na prática o cliente tem dois níveis, mas sem integridade; e o Znuny tem hierarquia real,
sem o teto pedido.

### Tarefas

| # | Tarefa | Camada | Pronto quando |
|---|---|---|---|
| T-R12.1 | **Decidir antes de codificar:** o catálogo do Znuny é a fonte de verdade; a vitrine é apresentação | decisão (ADR) | Decisão escrita e aprovada |
| T-R12.2 | Trocar o vínculo por texto pelo identificador do serviço | sidecar | Renomear o serviço no Znuny **não** quebra o pré-preenchimento |
| T-R12.3 | Impor o teto de dois níveis | znuny + admin | Criar um terceiro nível é recusado com mensagem clara, pela tela e pela API |
| T-R12.4 | Renomear a interface para o vocabulário dele ("item"/"sub-item") | admin | Na demonstração ele reconhece a tela sem tradução |
| T-R12.5 | Aviso de item órfão na vitrine | admin | Item apontando para serviço inexistente aparece marcado |

### Termos de aceite

| # | Termo de aceite | Como se prova |
|---|---|---|
| A12.1 | O operador cadastra **item e sub-item**, e um terceiro nível é recusado | V-R12.1 + V-R12.2 + V-R12.3 |
| A12.2 | Renomear um serviço no Znuny **não** quebra o catálogo do portal | V-R12.4 |
| A12.3 | O que o cliente escolhe na vitrine chega ao chamado como o serviço correto do Znuny | V-R12.3 |
| A12.4 | Existe **uma** fonte de verdade da taxonomia, e ela está declarada | T-R12.1 (ADR) |

### Testes de validação

| # | Tipo | Alvo | Asserção |
|---|---|---|---|
| V-R12.1 | vitest | `test/service-tree.test.ts` | Um serviço que já é filho **não** pode ser oferecido como pai |
| V-R12.2 | pytest | `tests/test_admin_znuny_router.py` | Criar terceiro nível → **422** com a mensagem repassada |
| V-R12.3 | manual | homologação | "Acesso e Identidade" + "Reset de senha" criados pelo console aparecem no Znuny e no formulário do portal; terceiro nível recusado |
| V-R12.4 | vitest | `test/catalog-prefill.test.ts` | O vínculo resolve pelo identificador **mesmo se o nome mudar** |
| V-R12.5 | pytest | teste de migração (novo) | Conversão dos vínculos existentes; sem correspondência fica vazio, não quebra |

### Decisões abertas

- **O teto de dois níveis é decisão de produto, não limitação técnica.** O Kleber descreveu
  o limite **do TIFLUX** ("aqui só dá dois níveis") — pode ser que ele aceite três de bom
  grado. **Perguntar antes de implementar:** impor um limite que ninguém pediu é criar
  dívida.
- A conversão dos vínculos existentes precisa consultar a lista de serviços do Znuny.
  Recomendação: fazer isso por comando explícito depois da migração, não dentro dela.

---

## R13 — Feriados e checklists

**Estado: feriados COBERTO**{: .estado-coberto } · **checklists AUSENTE**{: .estado-ausente }

### O que ele pediu

> *"Temos aqui configurações de feriados, checklists personalizáveis."* — 08:16

### Onde estamos — feriados

Coberto, e bem: jornada de trabalho, feriado recorrente e feriado pontual são
administrados pelo console, ao vivo, com validação de forma antes de tocar a configuração
do Znuny e liberação garantida da trava em qualquer falha. Verificado em homologação.

Três arestas honestas:

1. **O caminho de falha da trava de configuração nunca foi exercitado contra um Znuny
   vivo** — existe teste automatizado, mas com a integração simulada. É a última pendência
   de risco do subsistema, e o risco é sério: trava presa paralisa a administração do Znuny
   **para todos**.
2. **Não dá para dar nome a um calendário pelo console** — por isso eles aparecem como
   "Calendar 3 - " na tela de filas.
3. O console limita a 9 calendários; o Znuny permite mais. Divergência silenciosa.

### Onde estamos — checklists

Não existe, e não há equivalente nativo no Znuny para reaproveitar.

### Tarefas

| # | Tarefa | Camada | Pronto quando |
|---|---|---|---|
| T-R13.1 | **Exercitar o caminho de falha da trava contra o Znuny real** | manual/ops | A trava fica comprovadamente liberada após a falha |
| T-R13.2 | Permitir nomear calendários | sidecar + znuny | A tela de filas mostra "Calendar 3 — Feriados SP" |
| T-R13.3 | Alinhar o número de calendários ao limite real | sidecar + admin | Ou sobe o limite, ou o teto vira decisão documentada |
| T-R13.4 | Checklists: modelo, cadastro e aplicação no chamado | sidecar + admin | O agente aplica um modelo a um chamado e marca item a item |

### Termos de aceite

| # | Termo de aceite | Como se prova |
|---|---|---|
| A13.1 | Jornada e feriados são configurados pelo console e afetam o cálculo de SLA | já coberto; reconferir na demonstração |
| A13.2 | **Se a gravação do calendário falha no meio, a trava é liberada e o operador sabe o que foi aplicado e o que falhou** | V-R13.1 (contra o Znuny real) |
| A13.3 | Calendários têm nome legível na hora de escolher | V-R13.2 |
| A13.4 | O agente aplica um checklist a um chamado e marca os itens, com progresso visível | V-R13.4 |
| A13.5 | Aplicar o mesmo checklist duas vezes não duplica a lista | V-R13.4 |

### Testes de validação

| # | Tipo | Alvo | Asserção |
|---|---|---|---|
| V-R13.1 | manual | roteiro de administração do Znuny | Forçar falha na **segunda** das três gravações → resposta nomeia aplicado e falhado, auditoria registra a aplicação parcial, **e a trava está liberada** — esta última é o ponto inteiro do teste |
| V-R13.2 | pytest | `tests/test_znuny_admin_sysconfig.py` | Nome de calendário entra na lista permitida; formato inválido é recusado |
| V-R13.3 | pytest | idem | Regressão: a lista de configurações permitidas continua fechada — nenhuma configuração arbitrária passa |
| V-R13.4 | pytest | `tests/test_checklist_service.py` (novo) | Aplicar duas vezes cria **uma** instância; marcar item de outro cliente → 404 |
| V-R13.5 | vitest | `test/checklist.test.ts` (novo) | 2 de 5 marcados → 40%; modelo sem item é recusado |

### Decisões abertas

- Enquanto V-R13.1 não rodar contra um Znuny vivo, **o risco de trava presa continua
  declarado, não fechado**. É barato de fazer e vale priorizar.
- **Checklist transborda o recorte administrativo** — só faz sentido se o agente usar
  durante o atendimento. Vale conferir o vídeo do Vinícius antes de dimensionar, para não
  colidir com requisito do outro lado.

---

## R14 — Agentes, grupos de atendente e permissões

**Estado: PARCIAL**{: .estado-parcial }

### O que ele pediu

> *"Aqui a parte de usuários da plataforma, os grupos de atendente, as permissões. Isso é
> importante também."* — 08:23

E, antes, ao falar de filas: *"tem toda uma estratégia de permissionamento lá"* (04:39).

### Onde estamos

É o requisito mais bem coberto deste bloco. Cadastro de agentes, associação a grupos,
definir senha como ação separada, senha nunca exposta em resposta nem em auditoria,
trava anti-lockout no servidor (um administrador não se remove do próprio grupo de
administração) e auditoria com **antes e depois** da mudança de permissão.

O que falta:

| Lacuna | Consequência |
|---|---|
| **Permissão é tudo-ou-nada** — a associação grava apenas acesso total | Não dá para dar **somente leitura** de uma fila a um técnico. É exatamente a "estratégia de permissionamento" que ele cita |
| **Não dá para criar grupo** pelo console — só listar | Criar o grupo "DPO" exige entrar no painel técnico |
| Não há perfil reutilizável | Cada agente é configurado grupo a grupo |

### Tarefas

| # | Tarefa | Camada | Pronto quando |
|---|---|---|---|
| T-R14.1 | Permissões granulares por grupo | znuny + sidecar | Tipo fora da lista permitida → 422; anti-lockout preservado e estendido |
| T-R14.2 | Criar e invalidar grupos | znuny + sidecar | Reusa o mecanismo genérico existente — zero módulo novo |
| T-R14.3 | Matriz agente × grupo × permissão | admin | Diálogo mostra o diff antes de gravar |
| T-R14.4 | Tela de grupos | admin | Diz "Invalidar", nunca "Excluir" |

### Termos de aceite

| # | Termo de aceite | Como se prova |
|---|---|---|
| A14.1 | Um técnico recebe **somente leitura** de uma fila, sem poder alterá-la | V-R14.1 |
| A14.2 | Um administrador **não consegue** remover a própria permissão de administrador | V-R14.3 |
| A14.3 | Senha de agente **nunca** aparece em resposta, tela ou auditoria | V-R14.4 |
| A14.4 | O operador cria um grupo novo pelo console | V-R14.5 |
| A14.5 | Nada é excluído — apenas invalidado | V-R14.7 |
| A14.6 | Mudança de permissão fica registrada com o antes e o depois | já coberto; reconferir |

### Testes de validação

| # | Tipo | Alvo | Asserção |
|---|---|---|---|
| V-R14.1 | pytest | `tests/test_admin_znuny_people_router.py` | Conceder leitura + nota a um grupo → a integração recebe exatamente essas permissões e **não** o acesso total |
| V-R14.2 | pytest | idem | Permissão inventada → **422** e **zero** chamadas à integração |
| V-R14.3 | pytest | idem | Administrador removendo a si mesmo → 422 com a mensagem do servidor; a permissão continua lá |
| V-R14.4 | pytest | idem | A resposta não contém nenhuma chave parecida com senha ou hash, mesmo que a integração devolva |
| V-R14.5 | pytest | `tests/test_admin_znuny_router.py` | Criar grupo → 201; campo fora da lista permitida → 422 citando o campo |
| V-R14.6 | vitest | `test/agent-permissions.test.ts` | O diff mostra ganhos e perdas **por tipo** de permissão |
| V-R14.7 | vitest | `test/znuny-group.test.ts` (novo) | Invalidar grupo usa o marcador de inválido, nunca exclusão |
| V-R14.8 | pytest | vários | Todas as rotas novas: sem sessão de agente → 401; com sessão de cliente → 401 |

### Decisões abertas

- **Expor os papéis nativos do Znuny além dos grupos?** Ele fala de "grupos de atendente",
  não de papéis. Recomendação: só grupos — duas hierarquias de permissão confundem quem opera.
- Migrar de "tudo-ou-nada" para granular **muda o significado do estado atual**: hoje todo
  agente associado tem acesso total. A tela precisa dizer isso na primeira abertura, senão o
  operador acha que perdeu configuração.

---

## R15 — Financeiro global: serviços avulsos e valores extras

![Kleber no momento em que descreve a cobrança avulsa](assets/kleber/r15-servicos-avulsos.jpg)

*08:50 — "Para quando o cliente não tem contrato, entrou um serviço avulso, a gente bilheta também aquele cliente e manda nota fiscal e boleto por atendimento."*{: .legenda }

**Estado: AUSENTE**{: .estado-ausente }

### O que ele pediu

Três coisas em 08:40–09:07: **catálogo de serviços avulsos com valor-hora** para cliente
**sem contrato**, com nota fiscal e boleto **por atendimento**; e **valores extras** como
deslocamento e personalizações por cliente.

### Onde estamos

> **Cliente sem contrato hoje não consegue nem abrir chamado**, quanto mais ser cobrado.
> A regra recusa a abertura quando não há contrato ativo, e todo o modelo financeiro exige
> contrato — o vínculo é obrigatório tanto no registro de consumo quanto na fatura.
> Cobrança avulsa é **estruturalmente impossível**, não é "falta de tela".

Também: deslocamento é meia-implementação — existe franquia no contrato e o rótulo na
fatura, mas **nenhum caminho gera o lançamento**. E a fatura atual é declaradamente **não
fiscal**; o meio de pagamento só é acionado na página pública de contratação, nunca a partir
de uma fatura de ciclo.

> **Defeito financeiro confirmado, adjacente a este requisito.** A fatura soma apenas o
> valor faturável dos eventos, e esse valor **só é preenchido para contratos de crédito**
> (`reconciliation_service.py:120-124`). O excedente de horas é calculado no fechamento do
> ciclo (`cycle_service.py:66-71`) e **nunca é lido** pela fatura
> (`invoice_service.py:114-119`). Resultado observável: **fatura de contrato por banco de
> horas, valor fechado ou SaaS sai R$ 0,00** — mesmo com horas excedentes ou mensalidade
> contratada. Isso é dinheiro não faturado, silenciosamente.

Há três estruturas financeiras **já no banco e sem nenhum leitor**: o catálogo de serviços
com preço unitário (inclusive com suporte a itens globais), o pool de crédito compartilhado,
e a sobreposição de preço por escopo de contrato. **Reusar, não criar tabela nova.**

### Tarefas

| # | Tarefa | Camada | Pronto quando |
|---|---|---|---|
| T-R15.1 | Reanimar o catálogo global de serviços avulsos com preço | domínio + admin | "Hora técnica avulsa — R$ 220/h" cadastrada como item global vale para todos os clientes |
| T-R15.2 | Permitir consumo e fatura **sem contrato** | modelo + domínio | Cliente sem contrato abre chamado, o tempo vira consumo precificado e é possível faturar por atendimento |
| T-R15.3 | Lançamento de valores extras (deslocamento) | domínio + admin | Um deslocamento vira linha "Deslocamento" na fatura, respeitando a franquia do contrato |
| T-R15.4 | **Fazer a fatura refletir mensalidade fixa e excedente** | domínio | Fatura de banco de horas traz o excedente; de valor fechado, a mensalidade |
| T-R15.5 | Boleto **e nota fiscal** por atendimento, via Asaas | integração | Emitir fatura cria a cobrança, vincula o pagamento e emite a nota |

### Termos de aceite

| # | Termo de aceite | Como se prova |
|---|---|---|
| A15.1 | **Cliente sem contrato é atendido e cobrado**, com valor-hora do catálogo | V-R15.1 + V-R15.2 |
| A15.2 | **Fatura de contrato por banco de horas com excedente não sai zerada** | V-R15.4 — *hoje esse cenário dá R$ 0,00* |
| A15.3 | Deslocamento lançado num atendimento aparece como linha própria na fatura | V-R15.3 |
| A15.4 | Item de catálogo global vale para todos os clientes; item de um cliente não vaza para outro | V-R15.5 |
| A15.5 | Emitir fatura gera a cobrança no meio de pagamento, quando configurado | V-R15.5 + manual |

### Testes de validação

| # | Tipo | Alvo | Asserção |
|---|---|---|---|
| V-R15.1 | pytest | `tests/test_invoice_service.py` | Cliente com **zero** contratos; consumo avulso de 90 min a R$ 200/h → fatura sem contrato, **R$ 300,00**, 1 linha de 1,50 h |
| V-R15.2 | pytest | `tests/test_ticketing_service.py` | Cliente sem contrato em modo avulso abre chamado sem erro |
| V-R15.3 | pytest | `tests/test_invoice_service.py` | Ciclo com 2 h de trabalho + 1 deslocamento de R$ 80 → **2 linhas**, uma delas "Deslocamento" de R$ 80,00 |
| V-R15.4 | pytest | idem | Banco de horas com franquia de 10 h, 12 h consumidas, R$ 200/h → **R$ 400,00**. *Hoje esse mesmo cenário dá R$ 0,00* |
| V-R15.5 | pytest | `tests/test_rls_contract_tables.py` | Item global lido por dois clientes; item de um cliente invisível para o outro |

### Decisões abertas

- **Como permitir cobrança sem contrato:** afrouxar a obrigatoriedade do vínculo (mais
  simples, mas enfraquece uma invariante do modelo de contratos) ou **criar um contrato
  implícito do tipo "livre"** para clientes avulsos (preserva o modelo). **Recomendação: a
  segunda** — e ela depende da decisão do R3 sobre o tipo "livre".
- **Boleto e nota fiscal saem os dois pelo Asaas** (definido em 15/08), que já é o meio de
  pagamento da página de contratação — não é preciso contratar emissor fiscal separado. O
  boleto é caminho pronto no cliente que já existe; a nota exige um método novo e, do lado
  da conta Asaas, inscrição municipal, certificado e regime tributário configurados. Sem
  essa configuração o Asaas aceita a cobrança e **não** emite a nota, e o erro só aparece
  na hora de emitir. Sugestão: boleto primeiro, nota fiscal em seguida.
- Precificação especial por cliente deve reusar a sobreposição de preço que já existe no
  modelo, em vez de criar estrutura nova.

---

## R16 — Licenciamento e módulos por agente

![Kleber no momento em que descreve o quadro de licenças](assets/kleber/r16-licenciamento.jpg)

*09:24 — "Hoje tem sete usuários ativos, a gente tem um total de nove. Total de clientes cadastrados, 60. Contratos ativos, 43. […] Isso aqui impacta no faturamento da plataforma para a gente."*{: .legenda }

**Estado: AUSENTE**{: .estado-ausente }

### O que ele pediu

Um quadro de direitos — **agentes ativos contra o total contratado**, total de clientes,
contratos ativos — e, por agente, **qual licença e quais módulos ficam ativos**: pode falar
no WhatsApp? pode fazer acesso remoto? mais MFA e dados de segurança.

O exemplo que ele dá é o teste de aceite pronto: *"a Georgia só usa tickets e não tem acesso
remoto, então ela não vê o inventário"* (10:00).

E fecha com a frase que define a prioridade: *"isso aqui impacta no faturamento da
plataforma para a gente"*.

### Onde estamos

O conceito inteiro não existe — não há licença, seat, módulo por agente nem MFA em lugar
nenhum do código. Também não existe **painel agregado da operação**: os indicadores são por
cliente, e não há nada que responda "60 clientes, 43 contratos ativos, 7 de 9 agentes". O
dado-base existe; a visão, não.

### Tarefas

| # | Tarefa | Camada | Pronto quando |
|---|---|---|---|
| T-R16.1 | Modelar licenças, direitos contratados e módulos por agente | migration | Tabelas operacionais protegidas, sem acesso pela conexão da aplicação |
| T-R16.2 | Atribuir e revogar licença | sidecar | Atribuir sem seat livre → **recusa explícita**, não aviso |
| T-R16.3 | O "quadrinho": agentes, clientes e contratos | sidecar | Os números batem com a contagem direta no banco |
| T-R16.4 | Módulos passam a controlar o acesso de verdade | sidecar + admin | Agente sem o módulo recebe **403 na API**, não só menu escondido |
| T-R16.5 | Telas de licenciamento | admin | Sem seat livre → aviso; estouro → erro |
| T-R16.6 | MFA (avaliar antes de comprometer) | investigação | Existir decisão escrita sobre onde o MFA mora |

### Termos de aceite

| # | Termo de aceite | Como se prova |
|---|---|---|
| A16.1 | O console mostra **agentes ativos contra o total contratado**, clientes e contratos ativos, corretos | V-R16.3 |
| A16.2 | Atribuir licença **sem seat disponível é recusado**, com a contagem na mensagem | V-R16.1 |
| A16.3 | **O agente sem o módulo de inventário não acessa o inventário — nem pela URL direta** (o caso da Georgia) | V-R16.4 |
| A16.4 | Módulo inventado é recusado | V-R16.2 |
| A16.5 | Dado de licença é da operação e **nunca** aparece em resposta ao cliente final | V-R16.5 |
| A16.6 | A tabela de licenças não é legível pela conexão comum da aplicação | V-R16.6 |

### Testes de validação

| # | Tipo | Alvo | Asserção |
|---|---|---|---|
| V-R16.1 | pytest | `tests/test_licensing_service.py` (novo) | Teto de 2 seats, 2 em uso → terceira atribuição → **409** citando "2 de 2"; após revogar → 200 |
| V-R16.2 | pytest | idem | Módulo inventado → 422 citando o nome; nada gravado |
| V-R16.3 | pytest | `tests/test_admin_licensing_router.py` (novo) | 3 clientes, 2 contratos ativos, 2 de 9 seats → o resumo devolve exatamente esses números |
| V-R16.4 | pytest | idem | Agente **sem** o módulo → 403 no endpoint de inventário; com o módulo → 200 |
| V-R16.5 | pytest | idem | Rotas de licenciamento: sem sessão de agente → 401; nenhuma resposta ao cliente carrega campo de licença |
| V-R16.6 | pytest | `tests/test_licensing_not_readable_by_app.py` (novo) | A conexão comum da aplicação recebe erro de permissão ao ler licenças |
| V-R16.7 | vitest | `test/licensing.test.ts` (novo) | 9 de 9 → aviso; 10 de 9 → erro; texto "7 de 9 licenças em uso · 2 disponíveis" |
| V-R16.8 | vitest | idem | Revogar exige o login digitado |

### Decisões abertas — **esta trava o início da tarefa**

- **Qual é o modelo comercial?** O Kleber descreve o licenciamento que **ele compra do
  TIFLUX**. No Ground Control a relação é outra: quem define o total contratado — a WAS, no
  contrato com a Gerti, ou a própria Gerti? Isso muda quem escreve o número e se o console é
  apenas um espelho ou também o motor de cobrança. **Decisão do William, bloqueante.**
- **Dois módulos que ele cita não existem no produto:** WhatsApp e acesso remoto (Splashtop).
  Recomendação: modelar só os módulos reais hoje e crescer — evita vender no console um
  botão que não faz nada.
- **MFA:** recomendação de adiar e resolver junto com login federado, em vez de criar agora
  um segundo sistema de identidade para desfazer depois.

---

## R17 — FAQ / base de conhecimento

**Estado: COBERTO**{: .estado-coberto }

### O que ele pediu

> *"A FAQ, o OTRS já tem, o Znuny já tem uma FAQ — é feinha, mas tem."* — 10:41

### Onde estamos

Coberto, e por um caminho melhor do que o pedido — com um esclarecimento que vale registrar:

> **A premissa dele não vale nesta instalação.** O pacote de FAQ do Znuny **não está
> instalado**. O requisito está atendido por implementação própria: base de conhecimento com
> isolamento por cliente, artigos públicos ou internos, rascunho invisível para o cliente,
> link estável que não quebra quando o título muda, e busca integrada.

Três lacunas menores, todas de produto: categoria é texto livre; não há sugestão de artigo
no fluxo de abertura do chamado (que é o que transforma a base em desvio de chamado — o
valor real para um MSP); e o console não separa visualmente base interna e base do cliente.

### Tarefas

| # | Tarefa | Camada | Pronto quando |
|---|---|---|---|
| T-R17.1 | **Confirmar com o Kleber** que a base própria substitui a FAQ nativa | decisão | Alinhado antes da demonstração |
| T-R17.2 | Sugestão de artigos ao abrir e ao atender chamado | portal + admin | Digitar "senha" sugere o artigo de reset antes do envio |
| T-R17.3 | Aba "base interna" no console | admin | Filtro por visibilidade |
| T-R17.4 | *(opcional)* Categorias alinhadas ao catálogo | sidecar + admin | Depende da decisão do R12 |

### Termos de aceite

| # | Termo de aceite | Como se prova |
|---|---|---|
| A17.1 | Artigo em rascunho ou interno é **invisível** para o cliente — e o sistema nem confirma que existe | V-R17.1 |
| A17.2 | Editar o título de um artigo publicado **não** quebra o link já divulgado | V-R17.2 |
| A17.3 | Sugestão de artigo aparece antes de o cliente enviar o chamado | V-R17.3 + V-R17.4 |
| A17.4 | Artigo de um cliente nunca é sugerido a outro | V-R17.3 |

### Testes de validação

| # | Tipo | Alvo | Asserção |
|---|---|---|---|
| V-R17.1 | pytest | `tests/test_kb_router.py` | Artigo interno ou em rascunho → **404** pelo portal (não 403 — não revela existência) |
| V-R17.2 | pytest | `tests/test_kb_service.py` | Editar título não altera o endereço do artigo |
| V-R17.3 | pytest | `tests/test_kb_suggest.py` (novo) | Sugestão para o cliente A traz artigo de A e **nenhum** de B |
| V-R17.4 | manual | homologação | O cliente vê a sugestão, abre, e o contador sobe; artigo interno não aparece em nenhuma sugestão |

### Decisões abertas

- **Não instalar o pacote de FAQ do Znuny.** Instalá-lo criaria uma segunda base de
  conhecimento, com segunda fonte de verdade e a interface que ele mesmo chamou de "feinha".
  A recomendação é recusar, usando o argumento dele.


---

# Bloco 4 — Relatórios

> Ele não tratou relatório como configuração, e sim como **uso mensal**: *"isso aqui, todo
> mês, a gente manda"* (10:51). É o entregável recorrente da Gerti para os clientes dela.

## R18a — Gráfico de consumo por cliente

**Estado: PARCIAL**{: .estado-parcial }

### O que ele pediu

> *"Se eu quero saber qual o consumo de cada cliente, eu venho aqui e pego esse cara e vejo
> nos últimos três meses qual foi o ciclo de utilização dele. Quando é contrato de hora, é
> hora, aparece em formato de hora. Quando é contrato de grana, aparece em formato de
> grana."* — 11:00

### Onde estamos

A regra que costuma dar errado **já está certa**: a unidade segue o tipo do contrato —
contrato por horas devolve horas, contrato por crédito devolve reais, e contrato sem saldo
não exibe série. Isso está implementado e coberto por teste.

O que está errado é a **janela** e a **superfície**:

| Lacuna | Consequência |
|---|---|
| A série cobre a **vida inteira** do contrato, não os últimos 3 meses, e não agrega por ciclo | Não é a visão que ele descreve |
| O gráfico existe **no portal do cliente**, sob a sessão do cliente | O Kleber é agente da Gerti — para ver o consumo de um cliente ele teria que entrar no portal daquele cliente, contrato a contrato |
| Não há visão agregada por cliente | Cliente com 3 contratos não tem um gráfico só |

### Tarefas

| # | Tarefa | Camada | Pronto quando |
|---|---|---|---|
| T-R18a.1 | Janela por período no cálculo da série | domínio | 3 pontos mensais, sem mudar a unidade |
| T-R18a.2 | Endpoint de consumo por cliente para o console | sidecar | Uma série por contrato ativo, com a unidade de cada uma |
| T-R18a.3 | Gráfico no console, com seleção de cliente | admin | O eixo mostra **h** para horas e **R$** para crédito, **nunca misturados** |
| T-R18a.4 | *(opcional)* Série por ciclo, fiel a "ciclo de utilização" | domínio | Os 3 pontos batem com o fechado de cada ciclo |

### Termos de aceite

| # | Termo de aceite | Como se prova |
|---|---|---|
| A18a.1 | O agente da Gerti escolhe um cliente **no console** e vê o consumo dos últimos 3 meses | V-R18a.3 + V-R18a.4 |
| A18a.2 | **Contrato de horas mostra horas; contrato de crédito mostra reais** — e nunca os dois no mesmo gráfico | V-R18a.1 + V-R18a.2 + V-R18a.5 |
| A18a.3 | Consumo anterior à janela **não** aparece | V-R18a.3 |
| A18a.4 | Contrato sem saldo não exibe gráfico vazio enganoso | V-R18a.2 |

### Testes de validação

| # | Tipo | Alvo | Asserção |
|---|---|---|---|
| V-R18a.1 | pytest | `tests/test_contract_series_router.py` | Banco de horas com 90 min + 30 min no mês → unidade "horas", ponto = **2.0** (não 120) |
| V-R18a.2 | pytest | idem | Crédito com R$ 300 + R$ 150 → unidade "reais", ponto = **450.0**, e a resposta **não** traz minutos. Contrato SaaS → sem série |
| V-R18a.3 | pytest | `tests/test_contract_read_service.py` | Contrato de 12 meses com consumo em M-5 e M-1 → **3 pontos**, e o consumo de M-5 **não** aparece |
| V-R18a.4 | pytest | `tests/test_admin_analytics_router.py` | Rota nova: sem sessão de agente → 401; com sessão de cliente → 401; cliente inexistente → 404 |
| V-R18a.5 | vitest | `test/charts.test.ts` | Rótulo de unidade correto por tipo; sem gráfico quando não há saldo |

### Decisões abertas

- **"Últimos 3 meses" é mês-calendário ou 3 ciclos de faturamento?** Ele diz "ciclo de
  utilização", o que sugere ciclo — e ciclos podem não ser mensais. Decidir antes de
  implementar.
- Cliente com contratos de tipos diferentes **não pode** ter um gráfico único. Um gráfico
  por unidade é requisito, não detalhe estético.

---

## R18b — Relatório executivo mensal em PDF

![Kleber no momento em que descreve o relatório executivo](assets/kleber/r18-relatorio-executivo.jpg)

*11:36 — "Tenho um report executivo mensal aqui… vou pegar maio, vou pegar a DataStone… isso aqui eu consigo fazer em PDF… para ele saber quanto gastou, quanto consumiu, quais foram os principais tipos de ticket. No final, a gente põe a listona de chamados."*{: .legenda }

**Estado: AUSENTE**{: .estado-ausente }

### O que ele pediu

Escolher **mês + cliente** e gerar um resumo em **PDF** com: quanto consumiu, principais
tipos de chamado, e **ao final a lista completa dos chamados** do período. Ele manda esse
documento **todo mês** para os clientes.

Vale registrar a avaliação dele sobre o original: *"acho um relatório bem feinho da TIFLUX,
mas são os indicadores que a gente mostra para o cliente"* (12:10). Ou seja: **paridade de
conteúdo é obrigatória; a apresentação deve ser melhor**.

### Onde estamos

Existe um gerador de PDF com a marca do cliente — mas ele produz **fatura**, que é outro
documento: agrega o período em 2 ou 3 linhas por tipo de consumo, sem chamados, sem tipos,
sem gráfico, e roda por **ciclo de contrato**, não por mês escolhido.

Três peças faltam, e uma delas não é só de interface:

| Lacuna | Observação |
|---|---|
| Não há seleção de mês + cliente gerando relatório | O console **não tem nenhuma referência a PDF** — o agente da Gerti não consegue baixar nada |
| **"Principais tipos de chamado" não é computável hoje** | A agregação disponível na integração é por estado, prioridade e dia — **não há agregação por tipo nem por serviço** |
| A "listona de chamados" não existe como agregado mensal | Há busca de chamados para operação, mas nenhum consolidado do mês com horas por chamado |

### Tarefas

| # | Tarefa | Camada | Pronto quando |
|---|---|---|---|
| T-R18b.1 | Estender a integração com agregação por tipo de chamado | znuny GI | A agregação por tipo vem preenchida; o gate de compilação continua verde |
| T-R18b.2 | Listagem dos chamados do período com horas | integração + domínio | Lista com número, título, abertura, estado e horas, ordenada por data |
| T-R18b.3 | Serviço e modelo do relatório executivo | domínio | PDF com cabeçalho branded, consumo **na unidade do contrato**, tipos, satisfação e a lista final |
| T-R18b.4 | Endpoints do relatório | sidecar | Mês malformado → 422; cliente inexistente → 404; o corpo é PDF de verdade |
| T-R18b.5 | Tela no console: mês + cliente → visualizar e baixar | admin | "maio/2026 + DataStone" → prévia e download |

### Termos de aceite

| # | Termo de aceite | Como se prova |
|---|---|---|
| A18b.1 | O agente escolhe **mês e cliente** e baixa o relatório em PDF pelo console | V-R18b.4 + manual |
| A18b.2 | O relatório traz **quanto consumiu**, na unidade do contrato daquele cliente | V-R18b.1 + V-R18b.2 |
| A18b.3 | O relatório traz os **principais tipos de chamado** do mês | V-R18b.1 |
| A18b.4 | O relatório termina com a **lista completa dos chamados** do período | V-R18b.1 + V-R18b.3 |
| A18b.5 | Mês inválido é recusado, e cliente inexistente responde "não encontrado" | V-R18b.4 |
| A18b.6 | Se a integração com o Znuny estiver fora do ar, o comportamento é **decidido e travado por teste** — relatório degradado ou erro claro, nunca meio termo silencioso | V-R18b.4 |

### Testes de validação

| # | Tipo | Alvo | Asserção |
|---|---|---|---|
| V-R18b.1 | pytest | `tests/test_report_service.py` (novo) | Mês com 3 chamados (2 incidentes, 1 solicitação) e 5 h lançadas → tipo mais frequente = incidente com 2; consumo em horas = 5.0; 3 chamados na lista |
| V-R18b.2 | pytest | idem | Cliente com contrato de crédito → consumo em reais, e o relatório **não** expõe minutos |
| V-R18b.3 | pytest | `tests/test_report_pdf.py` (novo) | O arquivo gerado é PDF de verdade, acima de 1 KB, e o conteúdo cita o nome do cliente e o número de cada chamado |
| V-R18b.4 | pytest | `tests/test_admin_reports_router.py` (novo) | PDF com sessão de agente → 200 com tipo de conteúdo correto; mês `2026-13` → 422; sem sessão → 401; cliente inexistente → 404 |
| V-R18b.5 | pytest | `tests/test_ticket_stats_client.py` | Agregação por tipo é lida corretamente; ausência do bloco não gera exceção |
| V-R18b.6 | vitest | `test/reports.test.ts` (novo) | Mês inválido nunca chega a chamar a API |

### Decisões abertas

- **"Principais tipos de ticket" é o tipo do chamado ou o catálogo de serviço?** O Znuny
  costuma ter poucos tipos (incidente, solicitação) — um gráfico de duas barras não diz
  nada. Na cabeça dele pode ser o **catálogo de serviço** (R12). **Confirmar antes de
  implementar**, senão o relatório sai vazio de significado.
- **O relatório vai na marca do cliente ou da Gerti?** A fatura hoje usa a marca do cliente;
  o relatório executivo é enviado *pela Gerti*, e a resposta pode ser outra.
- Relatório de meses anteriores ao go-live só existe se houver dado. Combinar a expectativa
  antes da migração.
- Cliente com muitos chamados no mês torna a geração lenta — considerar geração assíncrona.

---

## R4 — Integração com o inventário das máquinas do cliente

**Estado: adiado pelo próprio cliente**{: .estado-parcial }

> *"Aqui tem uma integração com os recursos dos computadores dos clientes. **Não necessário
> pra iniciar agora**, mas no futuro pode-se ter."* — 03:50
>
> E, ao falar das configurações globais: *"configurações de recursos, nesse momento não
> essencial, porque a gente não vai ter integração agora — vai ter que deixar para um
> segundo momento."* — 08:31

Registrado como escopo declarado fora da primeira entrega, **pelo próprio Kleber**. Vale
notar que o Ground Control **já tem** inventário de ativos com visão para o cliente e agente
de coleta que se autorregistra — o que ele adiou é a *integração com ferramentas externas de
gestão de recursos*, não o inventário em si.


---

# Plano de validação

## Como o aceite acontece

O aceite não é uma reunião de demonstração — é a execução de uma lista. A sequência
proposta:

1. **Aceite deste escopo.** O Kleber confirma que os 18 requisitos representam o que ele
   descreveu, e responde às decisões abertas da tabela anterior. Sem isso, começar a
   construir é apostar.
2. **Execução por requisito**, na ordem de dependência (abaixo), com os testes automatizados
   escritos **junto** com a tarefa, não depois.
3. **Prova de aceite por requisito:** rodar os testes daquele requisito e executar os
   roteiros manuais correspondentes, com o Kleber presente nos que são a razão de ser do
   pedido — sobretudo o A2.2 (chamado por e-mail aparecendo no portal) e o A9.3 (entrou pelo
   suporte, sai pelo suporte).
4. **Registro:** cada requisito aceito é anotado com data e quem validou. O que não passou
   vira requisito remanescente numerado, não uma pendência informal.

## A composição dos 105 testes

| Tipo | Quantidade | O que provam |
|---|---|---|
| Automatizado no backend | 70 | Regra de negócio, isolamento entre clientes, contratos de API, cálculo financeiro |
| Automatizado na interface | 22 | Validação de formulário, proteção de rota, formatação — lógica pura, sem navegador |
| Ponta a ponta | 3 | Percursos completos: editar cliente, filas por cliente, aprovação |
| Roteiro manual | 9 | O que só existe ao vivo: entrega de e-mail, comportamento real do Znuny, trava de configuração |
| Gate de construção | 1 | Os módulos novos compilam — e removê-los quebra a construção da imagem |

Dentro dos automatizados há um subconjunto que merece nome próprio: **os testes negativos**.
São os que provam que algo **não** acontece — cliente que não alcança dado de outro, papel
que não decide o que não é dele, tipo de contrato que não é aceito, senha que não aparece na
resposta. São eles que sustentam os termos de aceite mais caros de recuperar se falharem
depois.

## Ordem sugerida de execução

Esta ordem é de **dependência técnica**, não de prioridade comercial — a prioridade é
decisão do William com o Kleber.

**Primeiro — o que destrava outros itens e custa pouco:**

1. **Corrigir a criação de fila** (R9/R10). É defeito existente, bloqueia dois requisitos e é
   das tarefas mais baratas da lista.
2. **Configurar o envio de e-mail** (R9). Sem isso, nada de e-mail é demonstrável — e hoje
   nem notificação de chamado sai.
3. **Exercitar o caminho de falha da trava de calendário** (R13). Fecha a última pendência de
   risco do subsistema de administração do Znuny, com custo quase zero.
4. **Corrigir a fatura zerada** (R15). É dinheiro.

**Segundo — o diferencial, na ordem que protege o faturamento:**

5. Cadastro rico de usuário do cliente (R2).
6. **Vínculo de contrato em chamado que entra por e-mail (R2) — antes de ligar o e-mail.**
7. Filas por cliente (R5).
8. Só então ligar a ingestão de e-mail (R2/R9).

**Terceiro — o que o Kleber usa todo mês:**

9. Consumo por cliente no console (R18a).
10. Relatório executivo em PDF (R18b).

**Depois:** importações (R8), permissões granulares (R14), catálogo em dois níveis (R12),
atividades recorrentes (R11), aprovação (R7), checklists (R13b), financeiro avulso (R15),
licenciamento (R16 — **bloqueado por decisão comercial**).

## O que este documento não cobre

- **Gestão de tickets** — é o vídeo do Vinícius, um levantamento à parte. Há pelo menos um
  ponto de contato conhecido: checklists (R13b) só fazem sentido no atendimento, e podem
  aparecer lá com requisito diferente.
- **Prazos e alocação.** O esforço indicado é ordem de grandeza para priorizar conversa.
- **As telas do TIFLUX.** Como registrado na abertura, a gravação não as capturou.

---

# Anexo — transcrição integral com marcação de tempo

Transcrição completa do áudio, na ordem em que foi dita. É a fonte de toda citação deste
documento; qualquer afirmação sobre o pedido do cliente pode ser conferida aqui.

**00:00** — Falo eu! Boa tarde, tudo bem?

**00:04** — Cara, conforme prometido aqui, eu vou trazer pra você os pontos que são mais importantes pra gente como administrador da plataforma aqui, tá?

**00:14** — O Vinícius gravou lá pra você a parte da gestão dos tickets, né?

**00:18** — Aí depois a gente pode até esclarecer dúvidas, se você tiver visto já o vídeo dele, a gente marca uma sessão e esclarece algumas dúvidas.

**00:26** — E aqui eu vou te passar toda a parte de configuração da plataforma, né?

**00:32** — Como que a gente trabalha hoje.

**00:34** — Primeiro assim, toda vez, qual que é o fluxo da Gert, né?

**00:37** — Toda vez que entra um contrato novo, que a gente inicia um cadastro,

**00:46** — mandei uma proposta, fechei um contrato.

**00:49** — A primeira coisa que eu vou fazer é cadastrar o cliente aqui.

**00:52** — Então essa tela é uma das telas mais importantes.

**00:54** — Eu vou meter o botãozinho cliente aqui, ele tem um passo a passo de cadastro do cliente, tá?

**01:01** — E aí ao final do cadastro do cliente, ele vai me levar pra uma telinha de edição aqui da parada.

**01:08** — O que a gente configura aqui?

**01:10** — Se a gente quiser, pode colocar logo, nome fantasia, os dados cadastrados da empresa, endereço, contato, tal, tal, tal.

**01:18** — Aqui a gente tem os usuários do cliente, e isso é uma coisa bem ruim da plataforma Teiflux,

**01:24** — porque é o seguinte, usuários que eu quero dar acesso ao portal, eu tenho uma tabela, um cadastro específico.

**01:31** — Então eu tenho que vir aqui e colocar novo usuário, cadastro o cara.

**01:35** — Usuários que eu quero que sejam solicitantes, que podem solicitar e-mail,

**01:40** — eu tenho que vir aqui e cadastrar também o cara como solicitante.

**01:44** — E aqui embaixo, eu libero tickets por e-mail, tá?

**01:50** — Normalmente, o que que dá de Zika?

**01:52** — A pessoa que tá cadastrada no portal, quando ela abre os chamados,

**01:57** — ele identifica os tickets que foram abertos pelo portal.

**02:01** — Quando a pessoa manda e-mail, os tickets que ela mandou por e-mail não vai pro portal.

**02:07** — Então, isso é um defeito na plataforma que a gente já falou diversas vezes.

**02:10** — Cara, por que que você tem vários cadastros?

**02:13** — Não é melhor a gente cadastrar um usuário único e dar acesso ao portal,

**02:16** — deixar esse cara, todo o usuário do cliente já é automaticamente um solicitante, entendeu?

**02:22** — Então a gente sempre fala isso pra ter fluxo, mas os caras nunca melhoraram o fluxo, tá?

**02:27** — Então aqui a gente tem um cadastro de cliente, normal, nome, e-mail, telefone e ramal.

**02:32** — Não tem muito segredo e se o cara tá ativo ou não ativo.

**02:35** — Basicamente é isso.

**02:37** — Tem uma função de autorização de tickets, de aprovação, mas a gente não usa.

**02:41** — Na verdade, na DataStone a gente utiliza, todo ticket passa,

**02:44** — quando essa chave tá habilitada, todo ticket passa por aqui e vai pra um aprovador.

**02:49** — Então, no caso aí de vocês, o Pedro tem que aprovar.

**02:52** — Ele tem acesso ao portal, quando vem um ticket ele recebe um e-mail pra aprovar,

**02:56** — ele entra lá no portal e aprova ou não aprova o ticket, tá?

**02:59** — Aqui tem uma visão geral dos tickets de cada cliente, né?

**03:03** — Que tá cadastrado pra cada cliente.

**03:05** — Os contratos, aqui a gente já começa a linkar com a proposta que a gente fechou com o cliente,

**03:10** — a gente vai cadastrar, se vai ser um contrato, entra no fluxo de cadastro do contrato, né?

**03:15** — Livre, crédito, crédito compartilhado, limite de horas, contrato de SaaS,

**03:20** — contrato com limite de atendimento.

**03:22** — E eu criei um tipo de contrato aqui chamado intercâmbio.

**03:25** — A Teinflux permite personalizar os contratos, mas eu não acho legal isso aqui, cara.

**03:32** — Acho que a plataforma tem que ter os modelos e o contrato tem que funcionar conforme os fluxos estabelecidos na plataforma.

**03:40** — Aí a gente segue o passo a passo aqui e cadastra o contrato.

**03:43** — A partir do momento que a gente cadastrou o contrato, ele vai aparecer aqui pro cliente como um contrato cadastrado.

**03:50** — Aqui tem uma integração com os recursos dos computadores dos clientes.

**03:55** — Não necessário pra iniciar agora, né?

**03:59** — Mas no futuro pode-se ter.

**04:01** — Os relacionamentos.

**04:02** — Aqui a gente vai falar quais filas de atendimento o cara vai ter acesso, tá?

**04:07** — Então a gente tem uma fila padrão.

**04:10** — Tudo que entra por e-mail vem pra essa fila.

**04:13** — E aí o analista no nível 1, ele classifica se é uma solicitação, se é um incidente.

**04:18** — Ou se é uma fila de chamados preventivos, tá?

**04:22** — E aí a gente tem uma outra fila aqui também chamada de iMac, que é pra movimentação de dispositivos.

**04:27** — Então isso aqui é personalizável.

**04:29** — Você pode criar novas filas nas configurações.

**04:32** — Pode associar quais pessoas vão estar...

**04:36** — Quais técnicos vão atender cada fila.

**04:39** — Tem toda uma estratégia de permissionamento lá.

**04:43** — E aí a parte de faturamento do cliente, que são algumas configurações pra enviar SMS, pra enviar e-mail, né?

**04:52** — Com detalhamento.

**04:53** — Se tiver integração com sistemas financeiros, aparece aqui.

**04:57** — Tem algumas coisinhas assim, tá?

**05:00** — Isso aqui é a parte de cadastro do cliente.

**05:02** — Isso é a primeira coisa que a gente faz, tá?

**05:04** — Quando um cliente entra.

**05:06** — A outra tela que é importante pra gente é isso aqui, ó.

**05:10** — Que aqui são as configurações padrão da plataforma.

**05:16** — Aqui tem algumas configurações gerais da plataforma.

**05:20** — Que aí, assim, não adianta a gente entrar no detalhe aqui.

**05:23** — Porque o Zune vai ser de...

**05:24** — Ele é de um jeito.

**05:25** — Ele traz algumas configurações ali que são importantes, né?

**05:29** — Então acho que a gente tem que ter configurações ali focadas no Zune aqui, tá?

**05:35** — Aqui o que a gente traz de principal, né?

**05:38** — Tem as importações que a gente pode eventualmente fazer.

**05:46** — Então, ó.

**05:47** — Quero importar cadastros, quero importar cliente, quero importar usuário do cliente, quero importar, sei lá.

**05:52** — Algumas outras coisas.

**05:53** — Eles têm algumas informações de importação.

**05:57** — Aqui a gente configura os e-mails também, que vão ser...

**06:00** — Que vai ter o recebimento, né?

**06:01** — De...

**06:02** — Das filas.

**06:03** — Então, quando enviar para esse e-mail, vai para a fila X.

**06:07** — Quando enviar para esse e-mail, vai para a fila Y.

**06:09** — Ou pode ser tudo para diversas filas também.

**06:12** — Aí é uma questão de estratégia no fluxo.

**06:15** — A parte de configurações, de autorização dos clientes que recebe.

**06:19** — Toda vez que cadastra um domínio lá no cliente, ele aparece aqui.

**06:22** — Mas aqui a gente consegue ver tudo centralizado.

**06:25** — E os endereços de resposta.

**06:27** — Então, por exemplo, nas filas de DPO, a gente usa esse.

**06:29** — Na fila de suporte, usa esse.

**06:31** — Na fila do administrativo, usa esse.

**06:34** — Então, tem a entrada do e-mail e a saída do e-mail.

**06:37** — Se entrou pelo suporte, tem que sair pelo suporte.

**06:39** — Se entrou pelo financeiro, tem que sair pelo financeiro.

**06:41** — Entendeu?

**06:42** — Se entrou por um DPO, que é a fila de encarregado de dados, tem que voltar também pelo encarregado de dados.

**06:49** — E aqui a gente tem até personalizações para alguns clientes.

**06:52** — Então, por exemplo, esses caras aqui, quando a gente recebe uma solicitação dele, volta o e-mail por ele também.

**07:00** — Então, tem essa entrada e saída sempre sincronizada pelo mesmo e-mail.

**07:04** — Aqui a gente configura as mesas de serviços e atividades agendadas.

**07:08** — Então, tickets recorrentes.

**07:10** — Isso aqui a gente tem uma visão, a gente tem atividades que são recorrentes.

**07:13** — Então, verificação de backup, verificação de pets, vulnerabilidades, atualização de servidor.

**07:20** — Tem várias atividades aqui que são recorrentes, que acontecem uma vez, que acontecem toda semana, que acontecem todo mês.

**07:26** — Então, é uma agenda.

**07:28** — E a gente pode programar recorrência, tá?

**07:31** — Isso é importante também, porque é o dia a dia dos técnicos, né?

**07:35** — Então, a gente configura aqui essas agendas.

**07:38** — Aí tem catálogo de serviço, que a gente pode configurar aqui.

**07:43** — O que eu vou ter no tipo de solicitação?

**07:46** — Aí tem aqui acesso à identidade, comunicação e colaboração, backup e recuperação de dados.

**07:52** — Aqui a gente cadastra o item e o sub-item.

**07:54** — Aqui só dá dois níveis, tá?

**07:57** — A parte do catálogo de serviços também é importante.

**08:01** — Mesas de serviço, que são as filas.

**08:03** — Então, fila do suporte, fila de solicitação, fila de requisição, fila do DPO, fila para assuntos administrativos.

**08:10** — O OTRS aqui trata como mesa, mas no Zune é tratado como fila.

**08:16** — Temos aqui configurações de feriados, checklists personalizáveis.

**08:21** — Então, tem algumas configurações do sistema.

**08:23** — Aqui a parte de usuários da plataforma, os grupos de atendente, as permissões.

**08:28** — Isso é importante também.

**08:31** — Configurações de recursos, nesse momento não essencial, porque a gente não vai ter integração agora.

**08:37** — Então, vai ter que deixar para um segundo momento.

**08:40** — E aqui a parte financeiro, né?

**08:42** — Que são lá os tipos de contrato, os serviços avulsos, se forem cadastrados aqui, quanto que a gente cobra por hora, tal.

**08:49** — Para quando o cliente não tem contrato, entrou um serviço avulso, a gente bilheta também aquele cliente e manda nota fiscal e boleto por atendimento.

**08:58** — E valores extras, caso a gente tenha aqui valor de deslocamento, valor de, sei lá, alguma personalização de contrato para um cliente específico.

**09:07** — Entendeu?

**09:08** — Então, essas informações aqui de configuração da plataforma são importantes.

**09:13** — E aqui a gente coloca a configuração do licenciamento também, tá?

**09:19** — Esse quadrinho aqui à direita, são o que a gente tem de direito.

**09:23** — Então, hoje tem sete usuários ativos, a gente tem um total de nove, né?

**09:28** — Está faltando dois recursos no time, que está em reposição.

**09:32** — Total de clientes cadastrados, 60.

**09:35** — Contratos ativos, 43.

**09:37** — Traz algumas informações.

**09:39** — Mas, no geral aqui, a gente acaba no usuário cadastrando aqui qual tipo de licença ele tem.

**09:48** — Então, toda a parte de segurança, nome do usuário, telefone, autenticação MFA, qual licença, qual módulo esse cara vai ter ativo,

**09:57** — se ele vai poder falar no WhatsApp, se ele vai poder fazer acesso remoto ou não.

**10:00** — Então, a Georgia aqui, por exemplo, ela só usa tickets e ela não tem acesso remoto.

**10:06** — Então, ela não vai lá, ela não vê o inventário.

**10:09** — Agora, por exemplo, o Vinícius, como ele é um cara que tem acesso remoto, ele tem uma integração aqui com o Splash Top e ele acaba tendo essa licença atribuída ao perfil dele.

**10:20** — Isso aqui impacta no faturamento da plataforma para a gente.

**10:23** — Então, esses recursos, eu acho que são os mais importantes para a administração que vai ditar o fluxo do sistema.

**10:32** — Aí, outras coisas que a gente tem aqui, né, que não necessariamente agora, mas que é interessante ter.

**10:41** — A FAQ, o OTRS já tem, o Zuni já tem uma FAQ, é feinha, mas tem.

**10:48** — A gente consegue ver também os relatórios.

**10:51** — Isso aqui, todo mês, a gente manda.

**10:53** — O que a gente tem aqui, né?

**10:55** — A gente tem o gráfico de apontamentos do faturamento, né?

**11:00** — Então, por exemplo, se eu quero saber qual o consumo de cada cliente, eu venho aqui e pego esse cara aqui e vejo nos últimos três meses qual foi o ciclo de utilização dele nos últimos três meses, tá vendo?

**11:15** — Quando é contrato de hora, é hora, aparece em formato de hora.

**11:20** — Quando é contrato de grana, aparece em formato de grana, tá vendo?

**11:24** — Então, isso é importante.

**11:27** — E tem aqui os relatórios, que a gente chama de relatório executivo.

**11:32** — Esse aqui, todo mês, a gente manda para os clientes.

**11:35** — Então, eu tenho um report executivo mensal aqui, que eu vou pegar, por exemplo, maio.

**11:41** — Vou pegar aqui a data stone, por exemplo.

**11:45** — Vou exibir isso aqui, ó.

**11:48** — Aí, isso aqui eu consigo fazer em PDF.

**11:51** — Ele me dá um resumo de como foi o mês de maio, por exemplo, para o cliente data stone.

**11:59** — Aí, eu exporto esse relatório e mando essa informação para o cliente, para ele saber quanto gastou, quanto consumiu, quais foram os principais tipos de ticket, né?

**12:10** — Acho um relatório bem feinho da Teiflux, mas, cara, são indicadores que a gente mostra para o cliente.

**12:18** — No final, a gente põe a listona de chamados, tá vendo?

**12:20** — De tudo que foi consumido aí, tá?

**12:23** — Então, esses pontos, acho que são os mais importantes para a gente poder operar a plataforma, tá?

**12:32** — Eu acho que é isso, cara.

**12:34** — Se ficar alguma dúvida, você me avisa.

**12:39** — Mas eu acho que, em teoria, é isso.

**12:41** — O cadastro do cliente, o cadastro do contrato do cliente e as configurações padrões do sistema,

**12:47** — que é fila, SLA, catálogo de serviço, os valores que vão ser cobrados de cada cliente, essas coisas.

**12:56** — A princípio, eu acho que é isso.

**12:58** — Beleza?


