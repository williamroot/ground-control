# Suposições a validar com o Kleber

Seis pontos do vídeo **Recursos Administrativos** admitem mais de uma leitura. Em vez de
parar a campanha esperando resposta, cada um foi fechado pelo padrão mais provável — e
construído **atrás de uma chave**, para que mudar de ideia custe uma configuração, não uma
reescrita.

Este documento é o contrato dessa promessa: para cada suposição, **onde está a chave, como
se vira, quanto custa e qual teste prova que o outro lado também funciona**.

> Decisão de 15/08/2026 (William): seguir os padrões e marcar como suposição.
> Registro completo em `docs/superpowers/plans/2026-08-15-recursos-administrativos.md`.
> Requisitos e termos de aceite em `docs/REQUISITOS-RECURSOS-ADMINISTRATIVOS.md`.

---

## A regra que torna isso verdade

**Nenhuma suposição pode ser codificada como constante.** Cada uma delas nasce com:

1. **Uma chave nomeada** — variável de ambiente, coluna ou parâmetro — nunca um número ou
   string cravado no meio da regra.
2. **O default documentado** aqui, com a fala do Kleber que o motivou.
3. **Teste parametrizado nos dois estados.** Não basta testar o padrão: o caminho
   alternativo precisa ter teste passando, senão "fácil de mudar" é promessa vazia — a
   troca só se descobre quebrada em produção.
4. **Procedimento de virada** escrito abaixo, executável sem tocar em código.

O agente `gc-general` trata isso como invariante de campanha: suposição sem chave e sem
teste do outro estado **não fecha a onda**.

---

## Painel de viradas

O que fazer quando ele responder. Nenhuma linha exige alterar código.

| Se o Kleber disser | Faça | Onde | Custo |
|---|---|---|---|
| "Aceito três níveis no catálogo" | `ZNUNY_SERVICE_MAX_DEPTH=3` (ou `0` = ilimitado) | `.env.prod` | Reiniciar `sidecar` e `znuny-web` |
| "É o tipo do chamado, não o serviço" | `REPORT_TOP_DIMENSION=type` (ou `queue`) | `.env.prod` | Reiniciar `sidecar` |
| "Três meses é mês-calendário" | `CONSUMPTION_WINDOW_MODE=months` | `.env.prod` — ou o próprio seletor na tela | Reiniciar `sidecar`, ou nada |
| "Manutenção preventiva consome contrato" | Preencher o contrato na tarefa recorrente | Tela de atividades | Nenhum |
| "Qualquer remetente pode abrir chamado" | `EMAIL_UNKNOWN_SENDER_POLICY=auto_create` | `.env.prod` | Reiniciar `znuny-web` |
| "Remetente por cliente tem que ser por cliente mesmo" | Criar fila dedicada + endereço de sistema | Console | Nenhum |

---

## S1 — Catálogo de serviço tem teto de dois níveis

> *"Aqui a gente cadastra o item e o sub-item. **Aqui só dá dois níveis.**"* — 07:53

**O que assumimos:** que ele **quer** dois níveis.
**Por que é suposição:** ele descreveu a limitação **do TIFLUX**, não um requisito dele. O
catálogo de serviços do Znuny é hierárquico sem teto. Impor um limite que ninguém pediu é
criar dívida; não impor contraria o que ele disse.

**É a suposição de maior risco das seis.**

| | |
|---|---|
| **Chave** | `ZNUNY_SERVICE_MAX_DEPTH` (inteiro; `2` = padrão, `0` = sem teto) |
| **Onde vive** | Renderizada no `Kernel/Config.pm` pelo `entrypoint.sh` e lida pelo `AdminSpec.pm`; espelhada no sidecar e devolvida à tela no bloco `support` de `GET /v1/admin/znuny/objects/Service` |
| **Como vira** | Alterar no `.env.prod` e recriar `sidecar` e `znuny-web` |
| **Custo** | Uma linha de env. **Serviços já criados com 3+ níveis não são invalidados** — a guarda vale para criação e edição, nunca retroage |
| **Teste dos dois estados** | `test_admin_znuny_router.py` parametrizado: com teto 2, criar neto → 422 com a mensagem do Znuny; com teto 3, o mesmo neto → 201. E `service-tree.test.ts`: `parentOptions` respeita o teto recebido da API, não um número cravado |

**Sinal de que erramos:** ele pedir para cadastrar um terceiro nível na demonstração.

---

## S2 — "Principais tipos de chamado" é o catálogo de serviço

> *"para ele saber quanto gastou, quanto consumiu, **quais foram os principais tipos de
> ticket**"* — 11:59

**O que assumimos:** que "tipo" na fala dele é o **catálogo de serviço** (R12), não o campo
`Type` do Znuny.
**Por que é suposição:** o `Type` do Znuny costuma ter dois valores (incidente e
solicitação) — um gráfico de duas barras não informa nada. Mas "tipo de ticket" é
literalmente o nome do campo, e ele pode ter dito exatamente isso.

| | |
|---|---|
| **Chave** | `REPORT_TOP_DIMENSION` (`service` = padrão · `type` · `queue`) |
| **Onde vive** | `config.py` do sidecar, consumida pelo `report_service.py` |
| **Como vira** | Alterar no `.env.prod` e recriar `sidecar` |
| **Custo** | Nenhum trabalho novo: a operação `TicketStats` do Znuny passa a expor `ByType`, `ByService` **e** `ByQueue` de uma vez (T-R18b.1). As três dimensões chegam prontas; a chave só escolhe qual vai para o gráfico |
| **Teste dos dois estados** | `test_report_service.py` parametrizado nos três valores, cada um assertando a dimensão correspondente no relatório |

**Sinal de que erramos:** ele olhar o relatório e dizer "não é isso que eu chamo de tipo".

> **Construída e no ar (Onda 3, 2026-08-16).** A chave existe, o teste roda nos
> três valores, e a execução ao vivo deu argumento: o relatório de maio da
> Aurora, em `service`, distingue "Acesso e Senhas" (2), "Hardware" (2) e
> "Microsoft 365" (2). Em `type`, o Znuny da Gerti daria duas barras. Vira com
> `REPORT_TOP_DIMENSION=type` no `.env.prod` e recriar o sidecar.

---

## S3 — "Últimos três meses" são três ciclos de faturamento

> *"vejo nos últimos três meses qual foi o **ciclo de utilização** dele"* — 11:00

**O que assumimos:** três **ciclos de faturamento** fechados, porque ele diz "ciclo".
**Por que é suposição:** ciclo e mês coincidem quando o contrato é mensal — e divergem
quando não é. Ele pode estar usando "ciclo" como sinônimo de mês.

| | |
|---|---|
| **Chave** | `CONSUMPTION_WINDOW_MODE` (`cycles` = padrão · `months`) e `CONSUMPTION_WINDOW_COUNT` (`3`) |
| **Onde vive** | `config.py`, consumida por `contract_read_service.series`; sobrescritível por requisição via `?window=` e `?count=` |
| **Como vira** | Env, **ou nem isso**: como os dois modos são parâmetro de rota, a tela pode oferecer o seletor e deixar ele escolher na hora |
| **Custo** | Nenhum. Os dois modos coexistem |
| **Teste dos dois estados** | `test_contract_read_service.py`: contrato com ciclos bimestrais → `cycles` devolve 3 pontos cobrindo 6 meses; `months` devolve 3 pontos mensais. Ambos preservam a unidade do contrato |

**Recomendação:** entregar o seletor. Custa quase nada e transforma a suposição em escolha
dele — que é melhor do que acertar por sorte.

> **Construída e no ar (Onda 3, 2026-08-16), com o seletor.** Os dois modos
> coexistem e a tela `/clientes/[id]/consumo` deixa escolher na hora. A execução
> ao vivo mostrou a diferença sendo real, não teórica: em `cycles`, o contrato
> `AUR-HORAS-2026` devolve os ciclos de janeiro (6,0 h) e fevereiro (2,0 h) —
> consumo que a janela de meses-calendário a partir de agosto não alcança.

---

## S4 — Atividade recorrente não consome o contrato

> *"verificação de backup, verificação de patches, vulnerabilidades, atualização de
> servidor… é o dia a dia dos técnicos"* — 07:09

**O que assumimos:** que manutenção preventiva **não** debita o saldo do cliente por padrão.
**Por que é suposição:** em MSP, preventiva às vezes é cortesia contratual e às vezes é
trabalho faturável — depende do contrato, e ele não disse.

| | |
|---|---|
| **Chave** | Coluna `contract_id` **nullable** em `gerti.recurring_task` — vazia por padrão |
| **Onde vive** | Na própria tarefa, editável na tela de atividades |
| **Como vira** | Preencher o contrato na tarefa. Por tarefa, não global — o que é mais fiel à realidade: uma atividade pode consumir e a outra não |
| **Custo** | **Nenhum.** O modelo já comporta as duas leituras desde o primeiro dia; não há migração para fazer |
| **Teste dos dois estados** | `test_recurring_worker.py`: sem contrato → chamado criado e **nenhum** evento de consumo; com contrato → chamado criado **e** o vínculo gravado, alimentando o faturamento |

Esta é a única das seis em que as duas respostas já estão implementadas ao mesmo tempo.

---

## S5 — Remetente desconhecido só é aceito de domínio autorizado

> *"toda vez que cadastra um domínio lá no cliente, ele aparece aqui. Mas aqui a gente
> consegue ver tudo centralizado"* — 06:19

**O que assumimos:** e-mail de alguém não cadastrado vira chamado **se** o domínio do
remetente estiver autorizado para aquele cliente. Sem auto-criação indiscriminada.
**Por que é suposição:** é o desenho mais seguro e o que a fala sugere, mas ele nunca disse
o que acontece com remetente desconhecido.

| | |
|---|---|
| **Chave** | `EMAIL_UNKNOWN_SENDER_POLICY` (`authorized_domain` = padrão · `auto_create` · `reject`) |
| **Onde vive** | Filtro de PostMaster + a configuração `CustomerUser::AutoCreate` do Znuny, ambos renderizados a partir da env |
| **Como vira** | Env e recriar `znuny-web` |
| **Custo** | Uma linha. **Mas a escolha tem consequência de segurança:** `auto_create` faz qualquer remetente virar usuário do cliente, ou seja, ganha acesso implícito. Se ele pedir isso, vale registrar que foi pedido |
| **Teste dos dois estados** | `test_email_intake.py`: remetente de domínio autorizado → chamado com o cliente certo; remetente desconhecido com `authorized_domain` → fila de triagem, **sem** criar usuário; com `auto_create` → usuário criado. O teste do modo `reject` prova que nada entra |

---

## S6 — Remetente por cliente resolve-se com fila dedicada

> *"esses caras aqui, quando a gente recebe uma solicitação dele, **volta o e-mail por ele
> também**"* — 06:52

**O que assumimos:** atender isso com uma **fila dedicada** para o cliente especial, com o
endereço de sistema dele. É o caminho nativo do Znuny — o remetente de saída sai sempre do
endereço vinculado à fila.
**Por que é suposição:** ele descreveu o efeito, não o mecanismo. Se quiser remetente por
cliente **independente de fila**, aí é outra história.

| | |
|---|---|
| **Chave** | Nenhuma — é procedimento operacional, não configuração de código |
| **Como vira** | Criar a fila e o endereço de sistema pelo console (o que a Onda 0 destrava) e associar o cliente a ela |
| **Custo** | **Zero código.** O custo é multiplicar filas: um cliente especial, uma fila |
| **Se ele recusar a fila dedicada** | Aí vira trabalho novo — interferir no caminho de envio do Znuny, o que colide com a invariante de núcleo imutável. **Nesse caso pare e traga a decisão**, não improvise |
| **Teste** | Coberto pelo aceite A9.3: o cabeçalho `From:` da resposta é o endereço da fila |

---

## Ressalva que vale para todas: movimentação de fila muda o remetente

Independente de S6, o Znuny amarra o remetente de saída à **fila atual** do chamado, não à
porta de entrada. No fluxo que ele mesmo descreve — tudo cai na fila padrão, o N1 classifica
e **move** — a resposta passa a sair pelo endereço da fila de destino.

Não é defeito, é o desenho do produto. Mas contraria a leitura literal de *"se entrou pelo
suporte, tem que sair pelo suporte"*, e por isso está no aceite **A9.6** como ressalva a ser
registrada com ele, não como suposição a virar por chave.

---

## Como usar este documento na conversa com ele

Não leve as seis como perguntas técnicas. Cada uma vira uma frase curta:

1. "O catálogo pode ter mais de dois níveis, ou dois é o certo para vocês?"
2. "No relatório mensal, 'principais tipos de ticket' é o serviço solicitado ou incidente/solicitação?"
3. "Três meses é mês fechado ou três ciclos do contrato?"
4. "Manutenção preventiva desconta do contrato do cliente ou é por fora?"
5. "E-mail de alguém que não está cadastrado: abre chamado, vai para triagem, ou é recusado?"
6. "Para o cliente que responde pelo e-mail dele: uma fila própria resolve?"

As respostas entram no painel de viradas acima. Nenhuma delas exige refazer trabalho.
