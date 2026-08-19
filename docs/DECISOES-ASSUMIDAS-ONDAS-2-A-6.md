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
