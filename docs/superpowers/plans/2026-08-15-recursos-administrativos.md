# Plano de campanha — Recursos Administrativos (vídeo do Kleber)

> **Fonte do escopo:** `docs/REQUISITOS-RECURSOS-ADMINISTRATIVOS.md` (18 requisitos,
> 89 tarefas, 92 termos de aceite, 104 testes). Análise técnica com caminhos de arquivo em
> `docs/levantamento/GAP-{A,B,C}-*.md`. Transcrição em `docs/transcricoes/`.
>
> **Comandante da campanha:** agente `gc-general` (`.claude/agents/gc-general.md`).
>
> **Definição de pronto de cada onda:** gates verdes → deploy no staging → evidência de
> aceite registrada → `.ia/` atualizado. Uma onda não é "concluída" enquanto não estiver
> no ar em `*.was.dev.br`.

---

## Registro de decisões

Nenhuma tarefa cuja decisão esteja **ABERTA** pode ser iniciada. O general **para e
reporta** — nunca escolhe por conta própria. Decisão fechada vira linha aqui, com data.

> **Todas as decisões foram fechadas pelo William em 15/08/2026.** A campanha está liberada
> de ponta a ponta. As marcadas **SUPOSIÇÃO** foram fechadas pelo padrão recomendado por
> decisão explícita dele, para não parar a campanha — devem ser **validadas com o Kleber**
> e estão listadas juntas na seção "Suposições a validar", ao final.

| ID | Decisão | Trava | Estado | Resolução |
|---|---|---|---|---|
| D-A | Modelo comercial de licenças: quem define o total de agentes contratados | R16 (6 tarefas) | **FECHADA 15/08** | **A Gerti define no próprio console.** O licenciamento é ferramenta de gestão da própria Gerti, não espelho do contrato WAS↔Gerti. `seats_total` é editável pelo console, com auditoria |
| D-B | Fonte de verdade do endereço do cliente | R1 | **FECHADA 15/08** | `gerti.tenant` dona + espelho best-effort no Znuny (padrão já usado no branding) |
| D-C | Fonte de verdade do usuário do cliente | R2 | **FECHADA 15/08** | Znuny dono da identidade; `gerti` guarda papel e flags |
| D-D | Cobrança sem contrato | R15, R3 | **FECHADA 15/08** | Criar o tipo "livre" — preserva a invariante do #1C, sem afrouxar o vínculo obrigatório |
| D-E | Cursor de faturamento em lançamento órfão | R2 | **FECHADA 15/08** | Manter o avanço + tabela de pendência reprocessável. **Não mexer no avanço do cursor** — é código financeiro vivo |
| D-F | Onde mora a associação cliente↔fila | R5 | **FECHADA 15/08** | Tabela nossa (`gerti.tenant_queue`), com a limitação declarada: a restrição é da nossa camada, não vale na interface nativa do Znuny |
| D-G | Remetente desconhecido por e-mail | R2, R9 | **FECHADA 15/08 · SUPOSIÇÃO** | Aceitar só de domínio autorizado do cliente (é o que ele descreve em 06:19). Sem auto-criação indiscriminada |
| D-H | "Remetente por cliente" | R9 | **FECHADA 15/08 · SUPOSIÇÃO** | Fila dedicada por cliente especial — nativo, zero código no caminho de envio |
| D-I | Teto de dois níveis no catálogo | R12 | **FECHADA 15/08 · SUPOSIÇÃO** | Impor o teto de 2 níveis. **É a suposição de maior risco** — ele descreveu o limite do TIFLUX, não necessariamente um requisito. Implementar como guarda configurável, para reverter barato |
| D-J | "Principais tipos de chamado" | R18b | **FECHADA 15/08 · SUPOSIÇÃO** | Catálogo de serviço, não o `Type` do Znuny (que tem 2 valores e gera gráfico sem significado). Ainda assim expor `ByType` no GI, que é barato |
| D-K | "Últimos 3 meses" | R18a | **FECHADA 15/08 · SUPOSIÇÃO** | Por **ciclo** de faturamento (ele diz "ciclo de utilização"), com os 3 últimos ciclos fechados |
| D-L | Atividades recorrentes consomem horas do contrato | R11 | **FECHADA 15/08 · SUPOSIÇÃO** | `contract_id` **nullable** na tarefa recorrente: por padrão **não** consome; quem quiser vincular, vincula. Preserva as duas leituras sem refazer o modelo |
| D-M | Representação de "aguardando aprovação" + SLA | R7 | **FECHADA 15/08** | Estado novo do Znuny, do tipo `pending`, para o relógio de SLA não correr enquanto o cliente não decide |
| D-N | Formato de importação | R8 | **RESOLVIDA POR PADRÃO** | CSV UTF-8 com modelo baixável; XLSX depois |
| D-O | Instalar o pacote FAQ do Znuny | R17 | **RESOLVIDA POR PADRÃO** | Não instalar — criaria segunda base de conhecimento |
| D-P | Expor papéis (Roles) do Znuny além de grupos | R14 | **RESOLVIDA POR PADRÃO** | Não expor — duas hierarquias confundem quem opera |
| D-Q | **Mensalidade de contrato de valor fixo é por ciclo ou por mês?** | R15, Onda 5 | **ABERTA — surgida na Onda 0** | — (ver abaixo) |
| D-R | **Saldo acumulado entre ciclos tem teto e validade?** Implementado ilimitado e sem expiração ao corrigir a cobrança indevida da Onda 0. Contratos de MSP costumam ter cap ou prazo; nada disso está modelado | R3, R15 | **ABERTA — surgida na Onda 0** | Pergunta ao Kleber: *"hora que sobra num mês acumula para sempre, ou tem teto e prazo?"* |

### D-Q — descoberta ao corrigir a fatura zerada (Onda 0)

`contract.initial_amount_brl` é **semanticamente sobrecarregado**: para `credit_brl` e
`credit_shared` é *saldo inicial consumível*; para `closed_value` e `saas_product` passa a
ser *valor da mensalidade*. A correção da fatura emite **1 mensalidade por ciclo,
quantidade 1**.

Consequência: um contrato com `closing_period_months = 3` fatura **1×** o valor contratado
por ciclo trimestral, não 3×. Se o valor contratado for mensal, a quantidade correta seria
`closing_period_months`.

**Hoje isso é inobservável** — não existe gerador de ciclos no código; os ciclos são criados
à mão. Por isso não bloqueia a Onda 0. Mas **bloqueia a Onda 5**, que é quando o faturamento
de valor fixo passa a valer de verdade.

Pergunta para o Kleber, em uma linha: *"num contrato de valor fechado com fechamento
trimestral, o valor contratado é por mês ou por fechamento?"*

**ABERTA** = o general não começa. **RESOLVIDA POR PADRÃO** = decisão de baixo risco tomada
no levantamento, o general segue; se o Kleber discordar, o custo de reverter é pequeno e
está declarado aqui de propósito.

---

## Insumos externos que a campanha não produz sozinha

| ID | Insumo | Estado | Bloqueia |
|---|---|---|---|
| I-1/2/3 | Servidor de envio, caixa de entrada e caixa de teste | **RESOLVIDO 15/08 — Mailpit no staging** | — |
| I-4 | Emissor de boleto e NF | **RESOLVIDO 15/08 — Asaas emite os dois** | — (resta configuração de conta, ver abaixo) |
| I-5 | Provedor de SMS | **RESOLVIDO 15/08 — mock de console agora, provedor depois** | — |

### I-5 — SMS com transporte trocável (decisão de 15/08)

O provedor ainda não está escolhido (Twilio é o candidato). Em vez de deixar o requisito
parado, o SMS é construído **inteiro**, com o envio atrás de uma interface de transporte —
e o primeiro transporte é um **mock que imprime a mensagem no log**.

Isso não é gambiarra: é a mesma forma dos outros adaptadores do projeto
(`integrations/ollama.py`, `integrations/asaas_client.py` — transporte injetável, erro
tipado). Quando o provedor for escolhido, entra um segundo transporte e a chave muda; nada
mais no fluxo é reescrito.

| | |
|---|---|
| **Chave** | `SMS_PROVIDER` (`console` = padrão · `twilio` quando existir) |
| **Onde vive** | `integrations/sms.py` (novo), `config.py` |
| **O mock faz** | Registra no log do container a mensagem que teria saído — destinatário mascarado, corpo curto, sem valor sensível além do necessário. Visível com `docker compose logs sidecar` |
| **Como vira** | Implementar o transporte do provedor e mudar `SMS_PROVIDER` + credenciais no `.env.prod`. **Nenhuma mudança em `billing_config_service`, no fluxo de fatura ou na tela** |
| **Teste dos dois estados** | Transporte falso recebe 1 chamada quando `sms_enabled=true`; **zero** quando desligado; transporte que levanta exceção **não** derruba a emissão da fatura (best-effort, igual ao e-mail) |

**Cuidado que vale desde já:** SMS tem custo por mensagem. O mock esconde isso — é fácil
deixar um laço mandando mil mensagens e só descobrir com o provedor real ligado. O teste de
"zero envios com a chave desligada" existe justamente para isso, e a tela deve dizer com
todas as letras quando o envio está em modo simulado.

### I-4 — Asaas emite boleto e NF-e (decisão de 15/08)

Não é preciso contratar emissor fiscal separado: o **Asaas**, que já é o meio de pagamento
do checkout (Spec #2), emite **boleto** e **nota fiscal de serviço**. Isso encurta o
T-R15.5 e elimina a decisão que estava em aberto sobre emissor.

**O que já existe:** `integrations/asaas_client.py` cobre cliente, cobrança
(`create_payment` com `billingType`, que aceita `BOLETO`), assinatura, consulta e
`get_billing_info` — ou seja, **boleto é caminho pronto**, falta apenas acioná-lo a partir
de `gerti.invoice` em vez de só a partir do checkout.

**O que falta construir:** método novo no cliente para a **API de notas fiscais** do Asaas
(o cliente não tem nenhum hoje), mais o disparo a partir da emissão da fatura.

**O que depende de configuração, não de código** — e por isso continua sendo pré-requisito
humano da Onda 5:

- `ASAAS_API_KEY` no `.env.prod` e `ASAAS_ENABLED=true` (hoje o padrão é `false`,
  fail-safe: sem isso o checkout responde 404).
- Na **conta Asaas**: inscrição municipal, certificado digital, regime tributário e
  serviço/alíquota configurados. Sem isso o Asaas aceita a cobrança mas **não** emite a
  nota — e o erro aparece só na hora de emitir, não na integração.

**Sequência recomendada em T-R15.5:** boleto primeiro (caminho pronto, prova rápida),
nota fiscal depois (depende da configuração municipal da conta).

### I-1/2/3 — Mailpit no staging (decisão de 15/08)

Em vez de depender de provedor externo e DNS, sobe-se **Mailpit** como serviço aditivo e
profile-gated no staging: ele recebe SMTP (saída do Znuny) e serve POP3 (entrada do
PostMaster), com interface web para conferir a mensagem.

Isso permite provar **ponta a ponta e sem dependência externa** os dois aceites que mais
importam:

- **A9.3** — chamado que entrou pelo suporte é respondido pelo endereço do suporte,
  conferido no cabeçalho `From:` da mensagem capturada.
- **A2.2 ao vivo** — e-mail de um usuário conhecido vira chamado e aparece no portal dele.

Regras: serviço **aditivo**, `profiles:["gerti"]`, **somente na rede interna** (nunca
exposto pelo tunnel), e toda a configuração de e-mail por env — trocar por provedor real
depois é mudar `.env.prod`, não código.

**T-R9.0 (nova, primeira da Onda 2):** subir o Mailpit, apontar o Znuny para ele e provar
que uma mensagem sai e é capturada.

> **Nenhum insumo externo bloqueia a campanha.** O que falta — provedor de SMS real e a
> configuração fiscal da conta Asaas — troca-se por chave, sem reescrever fluxo.

---

## Ondas

Ordem por **dependência técnica e proteção de receita**, não por ordem dos requisitos.
Cada onda termina no staging.

### Onda 0 — Defeitos existentes  ·  **desbloqueada, zero decisão pendente**

O que já está quebrado hoje, independente do vídeo. É a onda mais barata e a de maior
retorno; nenhuma decisão aberta e nenhum insumo externo.

| Tarefa | Origem | Camada |
|---|---|---|
| Fatura de contrato não-crédito sai R$ 0,00 | T-R15.4 | domínio |
| Criar fila pelo console falha sempre | T-R9.2 + T-R9.3 (= T-R10.1) | znuny GI + admin |
| Detalhe de chamado mais permissivo que a lista | T-R2.4 | sidecar + znuny |
| Catálogo de contratos sem teste-guarda | T-R3.1 | testes |
| Caminho de falha da trava de calendário não exercitado | T-R13.1 | manual em staging |
| Fallback ReportLab do PDF é código morto — nunca declarado como dependência | novo, T-R0.6 | sidecar |

**T-R0.6 (achado ao validar o baseline):** `domain/invoice_pdf.py:102` importa `reportlab`
como fallback do WeasyPrint, mas `reportlab` **não existe** no `pyproject.toml` nem no
`uv.lock`. O fallback nunca pôde executar. Consequência prática: no CI (Linux) passa
despercebido porque o WeasyPrint funciona; no macOS a suíte fecha com 2 vermelhos
fantasma. Pronto quando: `reportlab` declarado, `uv.lock` atualizado, e
`test_invoice_pdf.py` passa no host **sem** as bibliotecas nativas do WeasyPrint.

**Aceite:** V-R15.4 (fatura de banco de horas com 2h excedentes → R$ 400,00, hoje dá 0),
V-R9.4 + V-R10.2, V-R2.4 (helpdesk → 404), V-R3.1, V-R13.1 (trava liberada após falha).

> Atenção: a correção da fatura muda valor de documento financeiro. Antes de tocar,
> levantar se há fatura já emitida com valor zerado em staging e registrar no relatório.

### Onda 1 — Cadastro de cliente e usuário único  ·  **desbloqueada** (D-B, D-C, D-E, D-F fechadas)

R1 (6) · R2 exceto T-R2.6 (5) · R5 (5). É o coração do fluxo declarado por ele.

**T-R2.3 vem antes de qualquer coisa de e-mail.** Ligar ingestão sem o vínculo
chamado↔contrato faz a Gerti perder faturamento em silêncio.

**Aceite:** A1.1–A1.5, A2.1, A2.3–A2.6, A5.1–A5.5.

### Onda 2 — E-mail  ·  **desbloqueada** (Mailpit, D-G e D-H fechadas)

T-R9.0 (Mailpit) · R9 (8) · T-R2.6 · R10 restante (2). Fecha o diferencial: **A2.2 ao
vivo** — chamado que entra por e-mail aparece no portal do autor.

**Aceite:** A9.1–A9.6, A2.2 ao vivo, A10.1–A10.4.

### Onda 3 — Relatórios  ·  **desbloqueada** (D-J, D-K fechadas como suposição)

R18a (4) · R18b (5). É o que a Gerti manda para os clientes dela todo mês.

**Aceite:** A18a.1–A18a.4, A18b.1–A18b.6.

### Onda 4 — Configuração da plataforma  ·  **desbloqueada** (D-I, D-L fechadas como suposição)

R12 (5) · R11 (5) · R8 (4) · R14 (4) · R13b (1) · R13a arestas (3).

**Aceite:** A12.*, A11.*, A8.*, A14.*, A13.*.

### Onda 5 — Financeiro e fluxo  ·  **desbloqueada** (I-4 via Asaas, I-5 via mock de console)

R3 restante (3) · R15 (5) · R6 (5) · R7 (6).

**Aceite:** A3.*, A15.*, A6.*, A7.*.

### Onda 6 — Licenciamento  ·  **desbloqueada** (D-A fechada)

R16 (6). **A Gerti define o total de seats no próprio console** — `seats_total` é campo
editável com auditoria, não valor herdado de contrato externo. O console impede estourar o
teto (recusa explícita, não aviso) e os módulos gateiam de verdade no servidor, não só no
menu — o caso da Georgia (10:00) é o teste.

Modelar apenas os módulos que existem no produto hoje (`tickets`, `inventory`); WhatsApp e
acesso remoto ficam de fora até haver o recurso, para não vender botão que não faz nada.

**Aceite:** A16.1–A16.6.

---

## Gates obrigatórios por onda

Nenhum deploy sem os cinco verdes, na ordem:

```bash
# 1 — backend (mesmo escopo do CI: mypy em `src`, não em `.` —
#     `mypy .` inclui os testes não anotados e devolve ~900 falsos vermelhos)
cd apps/sidecar && uv run ruff check . && uv run ruff format --check . \
  && uv run mypy src && uv run pytest -q

# 2 — interfaces
docker run --rm -v $PWD:/w -w /w/apps/admin  node:22-bookworm npm run test:run
docker run --rm -v $PWD:/w -w /w/apps/portal node:22-bookworm npm run test:run

# 3 — Znuny compila (gate de build da imagem)
docker compose --env-file .env --profile gerti build znuny-web

# 4 — smoke da stack
make test        # 24 asserts

# 5 — revisão adversarial
# agente gc-review sobre o diff da onda: cross-tenant, IDOR, invariante, validação faltando
```

E, no staging, a verificação de serviços anteriores intactos do `gc-deploy` — Znuny,
sidecar, os dois portais, console e landing.

---

## Invariantes que a campanha não pode violar

1. **Nunca `make reset`** — destrói o banco compartilhado (Znuny + `gerti`).
2. **Zero persistência de configuração do Znuny** (D21). Tabela nova só com justificativa
   escrita de por que não é cópia de config — as três já justificadas no levantamento são
   tarefa recorrente, checklist e associação cliente↔fila.
3. **Sem exclusão** — Znuny invalida com `ValidID = 2`; as telas dizem "Invalidar". A única
   exceção proposta é o filtro de PostMaster, que não tem `ValidID`, e ela exige decisão.
4. **Núcleo Znuny imutável** — escrita só por Generic Interface, em `Custom/`.
5. **Todo `.pm` novo** exige linha `COPY` **e** nome no loop `perl -c` do Dockerfile. Já
   quebrou o projeto duas vezes.
6. **Isolamento entre clientes provado por teste**, nunca presumido.
7. **Segredo só em `.env.prod`** na VPS, gitignored, nunca ecoado em log.
8. **Migration antes do app**, e rollback escrito antes de subir.

---

## Relatório de campanha

O general mantém `docs/CAMPANHA-RECURSOS-ADMINISTRATIVOS.md` — uma linha por tarefa com
estado, gate, evidência de aceite e sha deployado. É desse arquivo que sai a prestação de
contas ao Kleber, requisito a requisito.

---

## Suposições a validar com o Kleber

> **Documento dedicado: [`docs/SUPOSICOES-A-VALIDAR.md`](../../SUPOSICOES-A-VALIDAR.md)** —
> traz, para cada suposição, a chave que a controla, o procedimento de virada, o custo e o
> teste que prova o outro estado. É o contrato de "fácil de mudar".
>
> **Invariante de campanha:** suposição não pode ser constante no meio da regra. Nasce
> atrás de uma chave nomeada, com teste parametrizado **nos dois estados**. Onda com
> suposição sem chave ou sem o teste do caminho alternativo não fecha.

Seis decisões de produto foram fechadas **pelo padrão recomendado**, por decisão explícita
do William em 15/08/2026, para não parar a campanha. Elas são construídas e entregues, mas
seguem sendo suposições até ele confirmar. O general marca cada requisito afetado no
relatório de campanha.

| Suposição | Requisito | Risco se ele discordar | Custo de reverter |
|---|---|---|---|
| Catálogo tem **teto de dois níveis** | R12 | **Alto** — impor limite que ele não pediu vira dívida. Ele descreveu a limitação *do TIFLUX*, não um requisito dele | Baixo **se** a guarda for configurável — por isso ela deve nascer assim |
| "Principais tipos de chamado" = **catálogo de serviço** | R18b | Médio — o relatório mensal sai com o agrupamento errado | Baixo: o `ByType` também é exposto no GI, então é trocar a fonte do gráfico |
| "Últimos 3 meses" = **3 ciclos** de faturamento | R18a | Médio — se ele quis mês-calendário, o eixo muda | Baixo: parâmetro no serviço de leitura |
| Atividade recorrente **não consome** contrato por padrão | R11 | Baixo — o campo é nullable, as duas leituras cabem | Nenhum |
| Remetente desconhecido aceito **só de domínio autorizado** | R2, R9 | Médio — se ele quiser auto-criar qualquer remetente, muda a política de entrada | Baixo: é configuração de filtro |
| Remetente por cliente via **fila dedicada** | R9 | Baixo — é o caminho nativo; a alternativa exige tocar o envio do Znuny | Nenhum código a desfazer |

**Recomendação:** levar as seis ao Kleber **antes da Onda 3** — é quando as suposições
começam a virar código (D-J e D-K, nos relatórios). A de maior risco, o teto de dois
níveis (D-I), só entra na Onda 4, o que dá duas ondas de folga para ele responder.
