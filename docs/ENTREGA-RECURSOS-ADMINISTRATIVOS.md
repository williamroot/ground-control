# Recursos administrativos — o que mudou, o que assumimos e como testar

Este documento fecha a campanha aberta a partir do seu vídeo. Os 18 requisitos
que levantamos dele foram executados em seis ondas, todas **no ar no ambiente
de homologação** e verificadas ao vivo — não apenas em teste automatizado.

Ele tem três partes, e a segunda é a que mais precisa de você:

1. **O que mudou** — requisito por requisito, com o que dá para ver na tela.
2. **O que assumimos** — as decisões que tomamos no seu lugar para não parar a
   obra, cada uma com o que muda se você discordar e quanto custa mudar.
3. **Como testar** — um roteiro para você conferir com as próprias mãos.

> **Por que existe a parte 2.** Várias coisas do vídeo admitiam mais de uma
> leitura, e esperar resposta teria travado tudo. Em vez disso, escolhemos uma
> leitura, **construímos de um jeito que a outra continua possível**, e
> anotamos. Nenhuma dessas escolhas está cravada no código: cada uma é uma
> configuração ou um campo do contrato. Discordar custa um ajuste, não uma
> reescrita.

---

## Parte 1 — O que mudou

### Cadastro e usuários

**Cadastro de cliente completo (R1).** O cadastro passou a ter endereço e
contato, num assistente de três passos. O endereço fica com a gente e é
espelhado no Znuny — antes ele existia só de um lado.

**Um usuário, um cadastro (R2).** Editar um usuário do cliente não recria mais
o registro: agora é edição de verdade, preservando o que você não tocou. O
ramal e a permissão de abrir chamado por e-mail entraram como campos.

**Filas por cliente (R5).** Você escolhe quais mesas de serviço cada cliente
enxerga e qual é a padrão. Antes, **todo chamado de todo cliente caía na mesma
fila** (`Raw`), sem como configurar. Agora o chamado nasce onde você definiu, e
tentar abrir numa fila que não é do cliente é recusado.

### E-mail

**Entrada e saída de e-mail (R9).** A instância **não enviava e-mail nenhum** —
faltava o transporte configurado. Agora envia, e a tela de e-mail administra as
caixas de entrada e as regras de triagem sem sair do console.

> Um detalhe que apareceu ao ligar isso: a saída de e-mail fez as mensagens do
> agendador interno do Znuny virarem chamados, num laço. Já está resolvido com
> uma regra de triagem, mas vale saber que existe.

### Relatórios

**Consumo dos últimos ciclos (R18a)** e **relatório executivo mensal em PDF
(R18b)**, com o que foi consumido, os principais serviços e o resumo do
período — o entregável que você manda para o cliente todo mês.

### Configuração da plataforma

**Atividades recorrentes (R11).** "Toda segunda às 8h" abre o chamado sozinho.
Ele não abre chamados retroativos ao cadastrar, e rodar duas vezes não duplica.

**Importação em massa (R8).** São 60 clientes vindos do TIFLUX; não dá um a um.
A importação tem simulação (que não grava nada) antes de valer.

**Permissões por fila (R14).** Um agente pode ler a fila do financeiro sem
poder mexer nela.

### Financeiro

**Contrato por pacote de atendimentos passou a cobrar (R3).** Este era um
defeito silencioso e caro: fechar o ciclo de um contrato de pacote gerava
**fatura de R$ 0,00**. O saldo nunca baixava. Agora ele conta atendimentos,
calcula o excedente e cobra — provamos ao vivo: um pacote de 3 com 5
atendimentos gerou **R$ 300,00** onde antes saía zero.

**Bolsa de crédito compartilhada (R3).** O tipo "crédito compartilhado" existia
e **não compartilhava nada**: cada filial via a bolsa inteira como se fosse só
dela. Na prática, o cliente podia gastar o crédito tantas vezes quantas fossem
as filiais. Agora o saldo é um só, do grupo.

**Glosa aprovada agora abate a fatura.** O cliente contestava 2 h, você
aprovava, e a cobrança saía com as 2 h dentro.

**Contrato suspenso não cobra mais mensalidade**, e contrato trimestral cobra
os três meses (antes cobrava um).

**Lançamentos avulsos (R15).** Deslocamento, hora extra, peça, despesa — o que
é feito fora do contrato agora entra na fatura, e o cliente pode contestar como
qualquer outro lançamento.

**Cliente sem contrato (R15).** Ganhou um tipo de contrato "livre": sem
franquia e sem mensalidade, tudo cobrado por lançamento.

**Boleto e nota fiscal (R15).** A fatura vira cobrança no Asaas com um clique, e
a nota é emitida em cima dela. *(Depende de configuração da conta — ver a
parte 2.)*

**Avisos de cobrança (R6).** Por e-mail e por SMS, configuráveis por cliente.
*(O SMS ainda sai em modo simulado — ver a parte 2.)*

### Fluxo e licenciamento

**Aprovação de chamados (R7).** Com a chave ligada para um cliente, todo chamado
dele nasce **aguardando decisão de um aprovador**, e nenhum técnico o atende
antes disso. Quem reprova precisa dizer por quê, e o motivo vai para o próprio
chamado.

> Dois cuidados que valem menção: o chamado fica num estado real de espera (não
> é "criado e escondido"), e esse estado **para o relógio de SLA** — cliente
> que demora a aprovar não queima o seu prazo.

**Licenciamento (R16).** O quadro que você desenhou: agentes licenciados contra
o total contratado, clientes cadastrados e contratos ativos. Por agente, quais
módulos ficam ativos. E o caso da Georgia funciona de verdade: **sem o módulo
de inventário, ela não entra no inventário nem digitando o endereço na barra do
navegador.**

---

## Parte 2 — O que assumimos, e o que muda se você discordar

Aqui estão as escolhas que fizemos no seu lugar. Cada uma tem uma pergunta no
fim — se a resposta for diferente do que assumimos, o ajuste é pequeno.

### Financeiro

**1. O valor de um contrato de valor fechado é MENSAL.**
Assumimos que "R$ 1.500" quer dizer R$ 1.500 por mês, então um ciclo trimestral
cobra três. Antes, o trimestral cobrava um mês só.
→ *Existe contrato seu cotado "por fechamento" e não por mês?* Se sim, é um
campo no contrato, e os dois tipos convivem na mesma base.

**2. Hora que sobra acumula para sempre, sem teto e sem prazo.**
É como estava; mantivemos. Mas criamos o teto e a validade prontos para ligar
por contrato, porque contrato de MSP costuma ter um ou outro.
→ *Hora que sobra num mês acumula indefinidamente, ou tem teto e prazo para
usar?* Se tiver, é preenchimento de campo, não desenvolvimento.

**3. "Atendimento" é o chamado, não o apontamento de hora.**
Num pacote de 10 atendimentos, um chamado com três apontamentos de tempo gasta
**um**, não três.
→ *Confere?* Se você conta visitas em vez de chamados, muda a contagem.

**4. Deslocamento não consome atendimento do pacote.**
Ele é cobrado pelo próprio valor. Se também baixasse um atendimento, o cliente
pagaria a visita **e** perderia uma do pacote.
→ *Confere, ou o deslocamento deve consumir uma visita do pacote?*

**5. Contrato assinado no dia 25 cobra o mês inteiro.**
Não implementamos cobrança proporcional por dias, porque ninguém pediu e
inventá-la mudaria valores sem decisão sua.
→ *Precisa de proporcional?*

### Cobrança e avisos

**6. Boleto primeiro, nota depois — e a nota depende da sua conta Asaas.**
O boleto está pronto. A nota fiscal exige, **na conta Asaas**: inscrição
municipal, certificado digital, regime tributário e o serviço/alíquota do seu
município. Sem isso, o Asaas aceita a cobrança e **recusa a nota** — e o erro
só aparece na hora de emitir. Assumimos ISS não retido e alíquotas zeradas
(Simples Nacional).
→ *Podemos configurar a conta Asaas? Qual o regime e o código de serviço do
município?*

**7. O SMS está construído, mas sai em modo simulado.**
Não há provedor contratado. A mensagem vai para o registro do servidor, com o
telefone mascarado. Trocar por um provedor real é ligar uma peça — o resto do
caminho já existe.
→ *Quer SMS de verdade? Tem preferência de provedor?* (Lembrando que SMS tem
custo por mensagem.)

### Catálogo e fluxo

**8. O catálogo de serviços tem no máximo dois níveis.**
**Esta é a suposição de maior risco desta entrega.** Você descreveu o limite de
dois níveis **do TIFLUX** — pode ter sido a descrição de uma limitação que você
tolera, não um requisito seu. Criar um terceiro nível é recusado, com a
mensagem explicando.
→ *Dois níveis é o que você quer, ou era só como o TIFLUX funcionava?* O teto é
uma configuração: dá para elevar ou desligar.

**9. Chamado por e-mail só de domínio autorizado do cliente.**
Nada de criar usuário para qualquer remetente que escreva.
→ *Confere?*

**10. "Últimos três meses" no relatório são três ciclos de faturamento.**
Você disse "ciclo de utilização". Ciclo e mês são a mesma coisa em contrato
mensal e divergem fora disso. A tela deixa escolher os dois.
→ *Confere?*

**11. "Principais tipos de chamado" é o catálogo de serviço.**
Usar o campo "tipo" do Znuny daria um gráfico com dois valores e nenhuma
informação.
→ *Confere?*

**12. Atividade recorrente não consome horas do contrato por padrão.**
Manutenção preventiva normalmente é combinada à parte. Quem quiser vincular a
um contrato, vincula.
→ *Confere?*

### Licenciamento

**13. Os módulos ainda NÃO bloqueiam nada — a chave está desligada.**
Isso é de propósito. Ligar antes de você atribuir as licenças tiraria o
inventário de **todos** os agentes de uma vez. A sequência é: atribuir as
licenças, conferir o quadro, e aí ligar. O quadro avisa, em letras, enquanto
estiver desligado.
→ *Quando quiser ligar, avise — é uma configuração.*

**14. Só existem dois módulos: chamados e inventário.**
Você citou WhatsApp e acesso remoto, mas nenhum dos dois existe no produto
hoje. Um botão "WhatsApp: ativo" seria uma promessa que o sistema não cumpre.
→ *Confere deixar de fora até o recurso existir?*

**15. O total de licenças é definido por você, no console.**
Não é herdado de contrato externo. Toda mudança fica registrada na auditoria.

**16. MFA: decidimos onde ele mora, e não construímos ainda.**
As três telas de entrada (Znuny, console e portal do cliente) autenticam contra
o Znuny. Um segundo fator só no console deixaria a porta do Znuny aberta ao
lado — pior que não ter, porque parece proteção. Então o MFA vai no Znuny,
quando for a hora.
→ Três perguntas antes de construir: *obrigatório ou opcional? Qual fator (app
autenticador, e-mail ou SMS)? Vale também para o usuário do cliente?* A
terceira muda o tamanho do trabalho em uma ordem de grandeza.

---

## Parte 3 — Como testar

Ambiente de homologação. Tudo abaixo pode ser feito e desfeito sem medo.

| Onde | Endereço | Entrar com |
|---|---|---|
| Console (você e sua equipe) | https://gerti.was.dev.br | `william` / `Gerti@Demo2026` |
| Portal do cliente (Aurora) | https://aurora.was.dev.br | `eduardo.salvi` / `Gerti@Demo2026` |
| Znuny nativo (para conferir) | https://znuny-dev.was.dev.br | mesmo login do console |
| Caixa de e-mail de teste | https://mail-dev.was.dev.br | sem senha |

> Login aceita **usuário ou e-mail** nos dois lados — é a mesma conta.

### Roteiro A — o cadastro e as filas (R1, R2, R5)

1. Console → **Clientes → Novo cliente**. Preencha os três passos.

✅ **Esperado:** endereço e contato são pedidos no cadastro, não depois.

2. Abra um cliente existente → **Usuários** → edite um. Mude só o telefone.

✅ **Esperado:** o resto dos dados continua lá. (Antes, editar recriava o
usuário e apagava o que você não redigitou.)

3. No mesmo cliente → **Filas**. Marque duas filas e defina uma como padrão.

✅ **Esperado:** só uma pode ser a padrão. Tentar salvar sem padrão é recusado.

4. Entre no **portal da Aurora** e abra um chamado.

✅ **Esperado:** ele nasce na fila padrão que você escolheu — não mais no `Raw`.

### Roteiro B — o financeiro (R3, R15, R6)

5. Console → um cliente → **Faturamento**.

✅ **Esperado:** a aba tem avisos de cobrança, lançamentos avulsos e bolsas de
crédito, numa tela só.

6. Lance um **deslocamento** de R$ 80, quantidade 2, sem preencher descrição.

✅ **Esperado:** recusa explicando que a descrição aparece na fatura do cliente.
Preencha e lance: o total é R$ 160.

7. Preencha "minutos" num deslocamento.

✅ **Esperado:** um aviso avisa que isso vai descontar do banco de horas do
cliente. É engano comum e é caro.

8. Crie uma **bolsa de crédito** e tente ligar um contrato de banco de horas.

✅ **Esperado:** recusa explicando que só contrato de crédito compartilhado
entra numa bolsa (misturar horas e reais na mesma bolsa deixaria "quanto
sobra?" sem resposta).

9. Cliente → **Faturas**. Numa fatura com valor, clique em **Emitir boleto**.

✅ **Esperado:** com o Asaas ainda desligado, a resposta diz **que está
desligado** — não um erro genérico. Ligada a chave, o boleto sai e o link
aparece na lista.

### Roteiro C — a aprovação de chamados (R7)

10. Console → Aurora → **Faturamento** → ligue **"Exigir aprovação antes de
    atender"** e salve.

11. Portal da Aurora → abra um chamado.

✅ **Esperado:** o chamado é criado e volta como **aguardando aprovação**.

12. Confira no **Znuny nativo**: o chamado está no estado `aguardando
    aprovacao`.

✅ **Esperado:** é um estado real, não um chamado escondido. Nenhum técnico o
pega antes da decisão. E o relógio de SLA **não** corre nesse estado.

13. No portal, com um usuário **aprovador**, abra **Aprovações** e reprove sem
    escrever motivo.

✅ **Esperado:** recusa. Reprovar sem motivo deixaria o cliente sem saber o que
fazer a seguir.

14. Escreva o motivo e reprove. Depois tente decidir de novo.

✅ **Esperado:** a segunda decisão é recusada — quem decidiu primeiro vale. E o
motivo aparece **dentro do chamado**, para o autor ler.

15. Com um usuário de **help-desk** (não aprovador), tente aprovar.

✅ **Esperado:** recusado por falta de permissão.

> Ao terminar, **desligue** a exigência de aprovação para não atrapalhar os
> outros testes.

### Roteiro D — o licenciamento e o caso da Georgia (R16)

16. Console → **Licenças**.

✅ **Esperado:** o quadro com agentes licenciados / total, clientes e contratos
ativos. E um aviso, em destaque, de que **os módulos ainda não restringem o
acesso** enquanto a chave estiver desligada.

17. Defina o total como **2** e atribua licença a dois agentes. Tente um
    terceiro.

✅ **Esperado:** recusa **com a contagem na mensagem** ("2 de 2 em uso").
Não é um aviso que dá para clicar por cima — o teto é o que você fatura.

18. Tente atribuir um módulo chamado `whatsapp`.

✅ **Esperado:** recusa listando os módulos que existem.

19. Tente reduzir o total para 1.

✅ **Esperado:** recusa pedindo que você revogue antes. O sistema não escolhe
sozinho quem perde o acesso.

20. **O caso da Georgia.** Peça para ligarmos a chave de licenciamento. Dê a um
    agente só o módulo de **chamados** e, com ele, tente abrir o inventário —
    inclusive **colando o endereço direto na barra do navegador**.

✅ **Esperado:** bloqueado, com a mensagem dizendo qual módulo falta. Não é o
menu escondido: é a porta trancada.

---

## O que ficou de fora, e por quê

- **Cobrança proporcional por dias** (contrato assinado no meio do mês).
  Ninguém pediu, e inventá-la mudaria valores sem decisão sua.
- **MFA.** Decidido onde mora, não construído — ver o item 16 da parte 2.
- **WhatsApp e acesso remoto** como módulos. Não existem no produto.
- **Renovação automática da bolsa de crédito por ciclo.** Se renovasse sozinha,
  um cliente que gastou tudo em maio veria crédito novo em junho sem ter
  comprado.

---

## Um pedido

Se alguma das 16 suposições da parte 2 estiver errada, **quanto antes soubermos,
mais barato é**. Todas foram construídas para serem revertidas com um ajuste de
configuração ou de campo — mas isso vale enquanto não houver dado real em cima
delas. Depois de faturar um mês inteiro com a regra errada, corrigir deixa de
ser configuração e vira conversa com cliente.
