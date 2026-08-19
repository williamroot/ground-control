# Decisões assumidas nas Ondas 2 a 6 — para validar com o Kleber

> **O que este documento é.** O William autorizou, em 16/08/2026, fechar por
> suposição tudo o que ainda estava aberto e implementar as ondas restantes até
> o fim. Este arquivo é a contrapartida: **toda escolha feita sem ele está
> aqui**, com o que foi assumido, por que, o que muda se estiver errado, e
> quanto custa reverter.
>
> Complementa — não substitui — o [`SUPOSICOES-A-VALIDAR.md`](SUPOSICOES-A-VALIDAR.md),
> que cobre as seis suposições nascidas do vídeo. Aqui estão as que nasceram da
> **execução**.
>
> **Invariante que vale para todas:** suposição não vira constante no meio da
> regra. Nasce atrás de chave nomeada ou de campo configurável, com teste nos
> dois estados. Reverter é mudar configuração, não reescrever fluxo.

## Como ler a tabela de cada decisão

| Campo | O que diz |
|---|---|
| **Assumimos** | a escolha feita |
| **Por quê** | o raciocínio, não a justificativa depois do fato |
| **Se ele discordar** | o que muda de verdade |
| **Custo de reverter** | e onde se mexe |
| **Chave / campo** | como virar sem tocar em código |

---

# Onda 2 — E-mail (R9, R10, T-R2.6)

## A2.1 — O transporte de saída padrão é SMTP simples, apontado para o Mailpit

**Assumimos** que o Znuny sai por `Kernel::System::Email::SMTP` (sem TLS),
apontado para um Mailpit interno, e que produção troca isso por env.

**Por quê.** O Znuny **não enviava e-mail nenhum**: o padrão do produto é
`sendmail`, e o binário não existe na imagem. Isso não era detalhe — nem
resposta a chamado nem notificação saíam, e nada do R9 era demonstrável. O
Mailpit resolve os dois lados (recebe SMTP, serve POP3) sem depender de
provedor externo nem de DNS.

**Se ele discordar** — ou seja, se a Gerti já tiver um relay corporativo —,
nada muda no fluxo: é outro host.

**Custo de reverter:** zero código. `ZNUNY_SMTP_MODULE=SMTPTLS` (ou `SMTPS`) +
`ZNUNY_SMTP_HOST/PORT/USER/PASSWORD` no `.env.prod`.

**Chave:** `ZNUNY_SMTP_MODULE`, `ZNUNY_SMTP_HOST`, `ZNUNY_SMTP_PORT`,
`ZNUNY_SMTP_USER`, `ZNUNY_SMTP_PASSWORD`, `ZNUNY_SMTP_FROM`.

> **Achado ao ligar:** havia mensagem **presa** na fila de e-mail do Znuny,
> falhando em silêncio com `No such binary: /usr/sbin/sendmail`. Depois da
> correção a fila drenou. Vale perguntar a ele há quanto tempo respostas de
> chamado deixaram de chegar aos clientes — pode ser mais tempo do que parece.

## A2.2 — A senha da caixa postal é gravável pelo console, nunca legível

**Assumimos** que vale expor o cadastro da caixa (incluindo senha) pelo
console, com a senha em modo write-only.

**Por quê.** A alternativa é o operador não conseguir cadastrar caixa nenhuma
sem abrir o painel técnico do Znuny — o que derrota o propósito da capa de
administração. O risco existe e é do produto: **o Znuny guarda essa senha em
texto claro no banco**, e o `MailAccountGet` nativo a devolve. Mitigamos com
três barreiras: a op Perl remove o campo antes de responder; o cliente Python
varre a resposta de novo; e a auditoria registra **que** a senha mudou, nunca
qual é. Salvar sem digitar senha relê a atual **dentro do Znuny** — ela nunca
trafega de volta.

**Se ele discordar:** a tela vira somente-leitura para caixas, e o cadastro
volta a ser feito no painel do Znuny.

**Custo de reverter:** baixo — remover a aba de escrita. As rotas de leitura
seguem servindo a tela de diagnóstico.

## A2.3 — Filtro de domínio é apagado de verdade (exceção à regra "sem exclusão")

**Assumimos** a exclusão real, só para este objeto.

**Por quê.** Filtro de PostMaster **não tem `ValidID`** no Znuny — não existe
"invalidar". As opções eram: não expor remoção (e deixar lixo acumulando sem
saída), ou aceitar a exclusão. Aceitamos, com duas mitigações: a confirmação
exige o nome digitado, e o **estado anterior completo** vai para a auditoria
antes de o objeto sumir, então a remoção é reconstituível.

**Se ele discordar:** some o botão de remover; regras velhas ficam para sempre.

**Custo de reverter:** trivial (esconder a ação).

## A2.4 — "Remetente por cliente" resolve-se com fila dedicada (S6 do vídeo)

**Assumimos** o caminho nativo: cliente que precisa de remetente próprio ganha
uma **fila dedicada** com o endereço dele.

**Por quê.** O Znuny não tem remetente por cliente — o `From` sai do endereço
de sistema **da fila**. A alternativa é interferir no envio, o que significa
código nosso no caminho de saída de e-mail, que é onde menos se quer código
nosso.

**Se ele discordar:** custo alto — passa a exigir um módulo de evento no envio.

**Custo de reverter:** nada a desfazer; é decisão de configuração.

## A2.5 — A ressalva de A9.6 é aceita e mostrada na tela

**Assumimos** que o comportamento nativo fica como está: o remetente da
resposta é o da fila **onde o chamado está**, não o da caixa por onde entrou.

**Por quê.** No fluxo que ele mesmo descreve — tudo cai na fila padrão, o N1
classifica e **move** — a resposta passa a sair pelo endereço da fila de
destino. Não é defeito; é o desenho do Znuny. Mudar isso é reescrever o envio.

**Se ele discordar:** vira requisito novo e caro.

**Mitigação já entregue:** a aba "Endereços de resposta" mostra o aviso em
texto, na tela, para ninguém descobrir isso numa reunião com cliente.

## A2.6 — O papel do portal passa a ser resolvido por login **ou** e-mail

Não é suposição, é **correção de defeito** — mas muda comportamento, então
está registrada. `gerti.portal_user_role` da Aurora está chaveado por
`eduardo.salvi@auroramoveis.com.br`, e a pessoa entra como `eduardo.salvi`:
strings diferentes, não diferença de caixa. O mesmo humano via coisas
diferentes conforme o formato que digitava. Agora a resolução tenta os dois
identificadores, com o digitado tendo prioridade.

**Efeito colateral a conferir com ele:** quem hoje entra pelo login curto e vê
só os próprios chamados vai passar a ver **a empresa inteira**, se houver papel
`admin` gravado sob o e-mail. É a intenção — mas é uma mudança visível.

## Dois achados operacionais que só a execução ao vivo revelou

Nenhum é suposição — são fatos, e os dois viram pergunta ou procedimento.

### 1. O `MailAccount` do Znuny **não tem campo de porta**

O cadastro nativo tem servidor, usuário, senha e protocolo — e nada de porta.
Quem usa POP3/IMAP em porta não-padrão precisa escrever `host:porta` no campo
de servidor (`mailpit:1110` foi o que funcionou aqui). Não é limitação nossa e
não dá para corrigir sem mexer no núcleo.

**O que fica:** a tela de e-mail aceita `host:porta`, e o texto de ajuda
explica. Se a caixa da Gerti usar porta padrão (993/995), isso nunca aparece.

### 2. Ligar o SMTP fez o Znuny abrir chamado com o próprio ruído

Assim que o envio passou a funcionar, o cron do daemon começou a **entregar** a
saída dele por e-mail (antes ela sumia junto com o `sendmail` inexistente).
Como a caixa de staging é catch-all, o PostMaster leu essas mensagens de volta
e abriu chamados a partir delas — quatro, em minutos.

Não é defeito do que construímos; é o que acontece quando um sistema que nunca
enviou e-mail passa a enviar, com uma caixa que aceita tudo. Em produção, com
caixa dedicada, o cron não cai nela.

**O que fica:** um filtro `zz-ignora-cron-do-znuny` no staging, marcando
`X-OTRS-Ignore` para remetentes do próprio domínio da instância. Vale conferir
com o Kleber se a caixa de produção é dedicada — se for catch-all, o mesmo
filtro é obrigatório lá.

> **A pergunta que vale fazer a ele:** havia mensagem **presa** na fila de
> e-mail do Znuny, falhando em silêncio desde sempre. Há quanto tempo respostas
> de chamado deixaram de chegar aos clientes dele? Pode ser bem mais tempo do
> que parece.


---

# Onda 4 — Configuração da plataforma (R11, R8, R12, R14)

## A4.1 — A agenda recupera no máximo uma semana, e abre UM chamado por atividade

**Assumimos** que o processador de atividades recorrentes: (a) ignora
ocorrências mais velhas que 7 dias; (b) abre **um** chamado por atividade em
cada execução, referente à ocorrência mais recente pendente.

**Por quê.** As duas regras vieram de erros que o teste pegou antes do deploy.
A primeira versão caminhava desde a data de início do cadastro — uma tarefa
criada em janeiro e processada em agosto abriria, uma por vez, todas as
segundas-feiras do período. A segunda versão limitou a janela, mas ainda
deixava as ocorrências antigas pendentes, e elas voltavam a cada execução.

A regra final: se três verificações de backup venceram, o técnico precisa de
*um* chamado dizendo "verifique o backup", não de três idênticos. O trabalho é
o mesmo.

**Se ele discordar** — se quiser um chamado por ocorrência perdida —, muda o
serviço, não o modelo: a tabela de ocorrências já registra cada data.

**Custo de reverter:** baixo, localizado em `due_tasks`.

**Chave:** `catch_up_days` é parâmetro do serviço (padrão 7); virar chave de
ambiente é uma linha, se ele pedir.

## A4.2 — Falha ao abrir o chamado NÃO é tentada de novo automaticamente

**Assumimos** que, se a ocorrência foi marcada e a criação do chamado falhou, a
linha fica com o erro registrado e **não** é retentada.

**Por quê.** É a contrapartida honesta de gravar a marca antes de chamar o
Znuny — que é o que impede a duplicata. Preferimos a falha visível (uma linha
com erro, que a tela mostra) ao risco de abrir o mesmo chamado duas vezes para
o técnico.

**Se ele discordar:** dá para acrescentar retentativa com limite. Reprocessar
hoje é apagar a linha de erro — ato deliberado.

## A4.3 — Senha não entra por planilha; o importador gera e mostra uma vez

**Assumimos** que uma coluna `password` no CSV é motivo para **recusar o
arquivo inteiro**, com explicação, e que o importador gera uma senha por
usuário devolvida uma única vez na tela.

**Por quê.** Senha em planilha fica no disco de quem exportou, no anexo do
e-mail que mandou o arquivo e no histórico do navegador de quem baixou. A
alternativa (criar sem senha e mandar convite) depende de e-mail funcionando —
o que só passou a valer na Onda 2 — e continua sendo o caminho melhor no
futuro.

**Se ele discordar:** dá para trocar por convite por e-mail agora que o SMTP
existe. Custo médio (fluxo de convite + token).

## A4.4 — O teto de dois níveis do catálogo é imposto, mas é uma chave (S1)

**Assumimos** o teto de dois níveis, com recusa explícita ao criar o terceiro.

**Por quê.** É a **suposição de maior risco da campanha**: ele descreveu o
limite *do TIFLUX*, e pode ter sido a descrição de uma limitação que ele
tolera, não um requisito dele. Impor um teto que ninguém pediu vira dívida.

**Mitigação já construída:** `ZNUNY_SERVICE_MAX_DEPTH`. `2` é o padrão, `0`
desliga por completo, `3` eleva. O teste roda nos três estados.

**Custo de reverter:** uma variável de ambiente e recriar o sidecar.

## A4.5 — Permissões granulares são opcionais; sem elas, tudo segue como antes

**Assumimos** que o payload de permissões por grupo é **opcional** e que a
ausência dele mantém o comportamento histórico (`rw`, que o Znuny trata como
superconjunto).

**Por quê.** Retrocompatibilidade sem bifurcação: nenhuma tela existente muda
de comportamento, e a granularidade fica disponível para quem precisar da
"estratégia de permissionamento" de 04:39 — um agente que LÊ a fila do
financeiro sem poder mover chamado nela.

**Cuidado que valeu código extra:** com permissão granular, um agente pode
continuar "no grupo admin" e ainda assim perder o `rw` — o que tranca a
instância exatamente como sair do grupo. O anti-lockout foi estendido para
barrar os dois caminhos.

---

# Onda 5 — Financeiro e fluxo (R3 restante, R15, R6, R7)

Esta é a onda que mexe em **dinheiro**. Cada suposição abaixo muda o valor que
sai na fatura de alguém, então nenhuma delas foi cravada no código: todas são
**coluna do contrato** ou **chave de configuração**, e o padrão de cada uma
preserva o comportamento anterior. Discordar custa um `UPDATE`, não um deploy.

## A5.1 — O valor de contrato fixo é MENSAL (decisão D-Q)

**Assumimos** que o "Valor inicial (R$)" de um contrato de valor fechado ou
SaaS é o valor **por mês**. Um ciclo trimestral emite quantidade 3 e cobra 3×.

**Por quê.** É como o mercado de MSP cota: "R$ 1.500 por mês". Antes desta
onda o contrato trimestral cobrava **um** mês — um erro de 66% para baixo que
não tinha como ser percebido, porque não havia gerador de ciclos que tornasse
o caso observável.

**Se ele discordar:** o contrato cotado "por fechamento" muda
`billing_amount_period` para `'cycle'` e volta a cobrar 1×. É por contrato, não
global — dá para ter os dois tipos na mesma base.

**Custo de reverter:** um `UPDATE` por contrato. Zero código.

**Chave:** `contract.billing_amount_period` ∈ `('month', 'cycle')`, padrão
`'month'`. Testado nos dois estados.

## A5.2 — Saldo acumulado é ilimitado e não vence, até alguém dizer o contrário (D-R)

**Assumimos** que hora que sobra continua acumulando **sem teto e sem prazo** —
o comportamento de hoje —, mas que teto e validade passam a existir e ficam
prontos para serem ligados por contrato.

**Por quê.** Contratos de MSP costumam ter cap ou prazo, e nada disso estava
modelado; ao mesmo tempo, ligar um teto que ninguém pediu tira saldo do cliente
sem aviso. O padrão nulo mantém tudo como estava.

**O que isso obrigou a mudar por baixo.** Validade não tem como ser aplicada
sobre um número só: o acúmulo é em cadeia (o saldo do mês N já embute o de
N-1), e a cadeia apaga a data de origem — todo saldo pareceria ter nascido no
último fechamento e nunca venceria. O saldo virou uma **lista de baldes
datados**. Duas escolhas dentro da regra, ambas a favor do cliente:

- **consumo é FIFO** — gasta primeiro o que vence antes, para não perder saldo
  por expiração tendo saldo em caixa;
- **quando o teto corta, sobrevive o mais NOVO** — o de maior vida útil.

O que expira e o que o teto descarta ficam **registrados no fechamento**
(`carry_expired`, `carry_capped`). Saldo que some sem ninguém poder ver por quê
é discussão com o cliente sem resposta.

**Se ele discordar:** três colunas por contrato —
`carry_over_cap_minutes`, `carry_over_cap_amount_brl`,
`carry_over_expires_days`. Nulo em todas = como está hoje.

**Custo de reverter:** um `UPDATE`. Ciclos fechados antes desta onda seguem
valendo: o número antigo vira um balde datado no fim daquele ciclo, senão
ligar a validade apagaria o saldo histórico de todos de uma vez.

## A5.3 — "Atendimento" é o CHAMADO, não o apontamento de hora

**Assumimos** que, num contrato por pacote de atendimentos, a unidade
consumida é o **chamado**: um chamado com três apontamentos de hora gasta
**um** atendimento do pacote, não três.

**Por quê.** É como o cliente conta ("tenho 10 atendimentos no mês"). Contar
apontamentos faria o pacote acabar em dias, por um detalhe interno de como o
técnico registra o tempo.

**Se ele discordar** (isto é, se ele quiser contar visitas/execuções em vez de
chamados): é uma consulta, não um redesenho — o evento de consumo já guarda o
chamado de origem.

## A5.4 — Lançamento avulso NÃO consome o pacote de atendimentos

**Assumimos** que um deslocamento, uma despesa ou um item de catálogo lançado
à parte é cobrado pelo próprio valor e **não** baixa um atendimento do pacote.

**Por quê.** Se baixasse, o cliente pagaria os R$ 80 da visita **e** perderia
uma visita do pacote — cobrança em dobro pela mesma coisa. Este foi um defeito
real: a verificação ao vivo mostrou o saldo do `AUR-PACOTE-2026` caindo de 50
para 49 por causa de um deslocamento, e foi assim que a regra errada apareceu.

**Se ele discordar** (por exemplo: "deslocamento consome uma visita do pacote,
sim"): é uma condição a mais na contagem.

## A5.5 — Contrato "livre" em vez de consumo sem contrato

**Assumimos** que o cliente avulso — o que não tem contrato formal — recebe um
contrato do tipo **livre**: sem franquia, sem mensalidade, em que tudo o que
for feito é cobrado como lançamento.

**Por quê.** A alternativa seria permitir consumo órfão, e isso quebraria a
invariante de que todo trabalho pertence a algum contrato — a mesma invariante
que garante que nada é feito sem alguém para cobrar. O contrato livre dá o
efeito que ele pediu sem abrir esse buraco.

**Se ele discordar:** o tipo existe e pode simplesmente não ser usado.

## A5.6 — Boleto primeiro, nota fiscal depois; a nota exige configuração da conta

**Assumimos** a ordem recomendada: a cobrança (boleto) é emitida primeiro, e a
nota fiscal é **uma ação separada**, sobre a cobrança já existente.

**Por quê.** A nota do Asaas pendura numa cobrança, então não há como emitir
nota de uma fatura que nunca virou cobrança. Poderíamos emitir o boleto por
baixo ao pedir a nota — e ninguém deve descobrir que cobrou o cliente porque
pediu uma nota fiscal.

**O que depende dele, não de nós.** A nota exige, na **conta Asaas**:
inscrição municipal, certificado digital, regime tributário e serviço/alíquota
do município. Sem isso o Asaas **aceita a cobrança e recusa a nota** — e o erro
só aparece na hora de emitir. A mensagem do Asaas é repassada inteira para a
tela justamente por causa disso.

**Padrão de imposto assumido:** ISS não retido e alíquotas zeradas, que é o
caso do Simples Nacional. Município que exija retenção precisa dos valores
reais — já é parâmetro da chamada.

**Chave:** `ASAAS_ENABLED` (padrão `false`) e `ASAAS_API_KEY`. Desligado, a
emissão recusa dizendo que está desligada, em vez de tentar e falhar torto.

## A5.7 — Aprovação: o chamado nasce esperando, e o SLA não corre

**Assumimos** que, com a exigência de aprovação ligada, o chamado é criado no
Znuny em um estado **real** de espera (`aguardando aprovacao`), do tipo
`pending reminder`.

**Por quê.** Duas coisas de uma vez. Primeira: se o chamado nascesse normal e
apenas sumisse do portal, um agente o pegaria e atenderia algo que o cliente
ainda não autorizou. Segunda: o tipo `pending reminder` **para o relógio de
SLA** — quem demora a aprovar não queima o SLA da Gerti.

**Regras que vêm junto:** a decisão é única (a segunda vira 409, não
sobrescrita silenciosa); reprovar **exige motivo**, e o motivo vai como nota no
próprio chamado, para o autor ler por que o pedido dele não passou; quem
decide é o papel `approver` ou o admin do portal — help-desk recebe 403, e
chamado de outro cliente recebe 404 (403 confirmaria que ele existe).

**Se ele discordar:** a exigência é uma chave por cliente
(`tenant.approval_required`), desligada por padrão.

## A5.8 — A bolsa compartilhada acumula desde o início e não renova sozinha

**Assumimos** que o saldo da bolsa de crédito compartilhada é o total comprado
menos tudo o que os contratos ligados consumiram, **sem renovação automática
por ciclo**.

**Por quê.** A bolsa tem ciclo próprio no modelo, mas renovar automaticamente
faria um cliente que gastou tudo em maio ver crédito novo em junho sem ter
comprado. Errar para o lado de cobrar a mais é percebido e corrigido; errar
para o lado de liberar crédito que não existe, não.

**Se ele discordar:** a renovação por ciclo é a evolução natural, e os campos
de ciclo já estão no modelo.
