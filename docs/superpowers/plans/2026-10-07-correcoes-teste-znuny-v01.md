# Correções do teste "TESTE_Znuny-V01" — plano de execução

**Origem:** `docs/TESTE_Znuny-V01.pdf`, de 03/09/2026. É o resultado do roteiro da Parte 3 de
`docs/ENTREGA-RECURSOS-ADMINISTRATIVOS.md` executado pelo cliente no staging.
**Diagnóstico:** feito ao vivo em 07/10/2026 no staging (`ssh gc`, `main` em `2d70ea6`/`39f78ff`),
com Playwright e leitura do banco. Capturas do "antes" em `docs/assets/teste-v01/antes/`.
**Entrega:** código corrigido e deployado no staging, todos os 26 passos do roteiro re-executados
pelo navegador, e o documento de resposta `docs/RESPOSTA-TESTE-ZNUNY-V01.md` (+ PDF) com captura do
antes e do depois de cada item.

---

## 1. O que o teste encontrou, e a causa de cada um

Placar do teste: 13 OK, 13 NOK. Dos 13 NOK, **6 são defeitos reais**, **3 são falhas do nosso
documento ou dos dados de demonstração**, e **4 ficaram bloqueados** por outro NOK.

| # | Passo | O que o testador viu | Causa real (verificada) | Tipo |
|---|---|---|---|---|
| 1 | A3 | "Não localizado a opção Filas"; "a página está quebrando a formatação" | O botão da tela de filas se chama **"Relacionamentos"** (termo do vídeo). O roteiro diz "Filas". E os **13 botões** do cliente estão num `flex` sem quebra: a página tem 1800 px de conteúdo numa janela de 1480 px (rolagem horizontal), e "Relacionamentos" é um dos que somem à direita. O título "Gerti · Console de Administração" também quebra em 3 linhas. | Defeito (UI) |
| 2 | A4 | Bloqueado pelo A3 | — | Bloqueado |
| 3 | B5 | "Não aparece o botão de ações" | Não há **nenhuma fatura com valor** no staging. As duas da Aurora são de R$ 0,00 e estão `paid`, e o botão só aparece em fatura aberta. O roteiro prometia "numa fatura com valor". Para gerar uma, a tela pede o **UUID de um ciclo**, o que ninguém de fora consegue fornecer. | Dados + UI |
| 4 | C2 | `eduardo.salvi` não entra no portal | **Senha errada no documento.** Publicamos `Gerti@Demo2026`; a do portal é `Aurora@Demo2026` (o login dá 200 com ela). Além disso, a mensagem "Credenciais inválidas **ou serviço indisponível**" não diz qual dos dois aconteceu. | Documento |
| 5 | C3–C6 | Bloqueados pelo C2 | Os 2 chamados aguardando aprovação ainda estão lá. O passo C6 não diz **qual** usuário é de help-desk (existe `helpdesk@auroramoveis.com.br`). | Bloqueado + doc |
| 6 | D3 | Buscar "#84" → "Nenhum chamado encontrado" | A busca do console **só procura no título**. `AgentTicketSearch.pm:34-37` diz "número OU título", mas o código só preenche `Title`. Nem o número completo `2026081910000081` acha nada. E "#84" é o **TicketID** interno, enquanto a tela mostra o número longo. A lista sem filtro tem limite de 50 e o #84 já saiu dela. | Defeito (Znuny GI) + doc |
| 7 | D4–D5 | Bloqueados pelo D3 | — | Bloqueado |
| 8 | E1 | Trava após Salvar; tela 500 `Cannot access 'calendarName' before initialization` | Em `apps/admin/pages/znuny/calendario.vue`: o `watch(data, …, { immediate: true })` (l. 77) usa `calendarName`, que só é declarado na l. 97 (erro de temporal dead zone). **A página dá 500 já na carga direta**, não só ao salvar. Na l. 120, `const calendarLabel = computed(() => calendarLabel(…))` sombreia a função importada e chama a si mesma (o modal mostrou "Calendário:" vazio). O seletor corta os nomes ("Calen…"). Nenhum teste renderiza a página, por isso nada pegou. | Defeito (UI) |
| 9 | F3 | Não há como atribuir "whatsapp" | A tela **corretamente** só oferece Chamados e Inventário. A recusa existe na API. O roteiro pedia algo que a UI, de propósito, não permite. | Documento |
| 10 | F5 | Caso da Georgia não testável | (a) A atribuição aceita **qualquer login digitado**. Das 7 licenças em uso, 6 são de logins que **não existem** no Znuny (`mariana`, `rafael`, `juliana`, `pedro`, `carla`, `georgia`). Os agentes reais são `william`, `bruno.cardoso`, `patricia.menezes`, `rafael.tavares` e `diego.fontana`. (b) Não existe agente `georgia` para entrar e tentar abrir o inventário. (c) A chave `LICENSE_ENFORCEMENT_ENABLED` está desligada e só nós podemos ligar. (d) No print, "georgia" é o *placeholder* em cinza, então o campo parecia preenchido e veio "Informe o login do agente". | Defeito + dados |

Achado de brinde, já resolvido: na tabela "Lançamentos registrados" (print do B2) as colunas
"VALOR" e "LANÇADO POR" estavam coladas. A correção (`24b87df`) estava na `main` mas não no
container, e foi deployada em 07/10. Vai no documento de resposta com o depois.

---

## 2. Correções

Branch única `fix/teste-znuny-v01`. Cada item tem um teste que falha antes e passa depois. Para
UI, o teste é **de navegador** (`e2e/`), porque foi a falta dele que deixou o E1 passar.

### T1 — Página do cliente: "Filas" visível e sem rolagem horizontal (A3)
- `apps/admin/pages/clientes/[id]/index.vue`: separar **navegação** (Usuários, Filas, Chamados,
  Atividades, Consumo, Agentes, Faturas, Faturamento, Conhecimento, Catálogo, Identidade visual)
  de **ações** (Editar cadastro, Novo contrato). A navegação vira uma faixa própria abaixo do
  cabeçalho com `flex-wrap`, sem nada fora da tela.
- Rótulo **"Filas"** no botão. Em `filas.vue`, título "Filas de atendimento" e o termo
  "relacionamentos" no subtítulo, para quem vem do vídeo.
- `layouts/default.vue`: marca em uma linha (`whitespace-nowrap`, "Gerti · Console").
- **Teste:** `e2e/test_admin.py::test_cliente_sem_rolagem_horizontal` em 1280 e 1480 px
  (`scrollWidth <= innerWidth`, link "Filas" visível e clicável).

### T2 — Fatura com valor para testar o boleto (B5)
- `apps/admin/pages/clientes/[id]/faturas.vue`: trocar o campo "ID do ciclo (UUID)" por um
  **seletor de ciclos fechados ainda sem fatura** ("31/08/2026 – 30/09/2026 · AUR-PACOTE-2026 ·
  R$ 160,00"). Se o sidecar não listar isso, adicionar `GET /v1/admin/tenants/{id}/cycles?closed=1&uninvoiced=1`
  com teste pytest, incluindo o teste cross-tenant.
- Seed idempotente: garantir **uma fatura aberta com valor** na Aurora (a partir do ciclo que
  contém os lançamentos de deslocamento).
- **Teste:** pytest do endpoint; e2e: "Emitir boleto" visível na fatura aberta, e o clique
  devolve a mensagem de Asaas **desligado** (não erro genérico).

### T3 — Login do portal: documento certo e mensagem que distingue (C2)
- Documento: `eduardo.salvi` / `Aurora@Demo2026`.
- `apps/portal`: separar "Usuário ou senha incorretos" (401) de "Serviço indisponível, tente em
  instantes" (5xx/timeout).
- **Teste:** vitest do mapeamento status → mensagem; e2e: login com a senha errada mostra
  "incorretos", e com a certa entra.

### T4 — Busca de chamado por número e por ID (D3)
- `znuny/Custom/.../GertiTicket/AgentTicketSearch.pm`: se `Query` casar `^#?\d+$`, buscar por
  `TicketNumber` (exato e sufixo) **e** por `TicketID`, e unir com a busca por título (o
  `TicketSearch` do Znuny não faz OU entre campos; são duas chamadas, sem duplicados, mantendo o
  limite). O comentário passa a dizer a verdade.
- **Teste:** pytest do router com fake GI (passa `#84` sem alterar). Teste ao vivo no Znuny:
  "#84", "84", "2026081910000081" e "ERP" acham o chamado 84.
- Documento: citar o chamado pelo que a tela mostra, ou seja, número + título.

### T5 — Calendário não quebra e mostra os nomes (E1)
- `calendario.vue`: declarar `calendarName` antes do `watch`; renomear o computed para
  `currentCalendarLabel` (fim do sombreamento).
- Seletor com largura mínima e rótulos **"Calendário 3 — Feriados de São Paulo"** vindos dos
  nomes gravados (se a API não devolve a lista de nomes, adicionar ao `GET` existente).
- **Teste que fecha a classe:** `e2e/test_admin.py::test_toda_pagina_do_menu_renderiza`
  percorre todos os links do menu do console e das abas do cliente com **carga direta** e exige
  status 200, sem `pageerror`. Esse teste teria pego o E1 em agosto.
- e2e específico: dar nome ao Calendário 3, salvar, recarregar, ver o nome no seletor; o Padrão
  continua sem campo de nome.

### T6 — Licença só para agente que existe; caso da Georgia testável (F3, F5)
- Sidecar: `POST` de licença valida o login contra os agentes do Znuny (422 "agente não existe").
  pytest, incluindo módulo inválido ("whatsapp") → 422 listando os válidos.
- Admin: o campo livre vira **seletor de agentes reais** (sem placeholder que parece valor).
- Dados do staging: revogar as 6 licenças fantasmas; licenciar os 5 agentes reais; criar o agente
  **`georgia`** (Georgia Lima, senha demo `Gerti@Demo2026`) no seed idempotente, só com
  `tickets`. O quadro passa a mostrar números verdadeiros (6 de 9).
- Ligar `LICENSE_ENFORCEMENT_ENABLED=true` no `.env.prod` do staging **depois** que todos os
  agentes reais tiverem licença (o aviso da tela diz por quê), e anotar no OPS.md como desligar.
- **Teste e2e:** login como `georgia` → menu sem Inventário; URL direta do inventário →
  bloqueio com "falta o módulo Inventário"; `william` continua abrindo.

### T7 — Documento de entrega corrigido
`docs/ENTREGA-RECURSOS-ADMINISTRATIVOS.md`, Parte 3: senha do portal; "Filas"; chamado por
número + título; F3 reescrito ("a tela só oferece os módulos que existem; WhatsApp não aparece");
login da Georgia; usuário de help-desk nomeado no C6 (`helpdesk@auroramoveis.com.br`, senha
conferida ao vivo); aviso de que a chave de licenciamento está **ligada** no staging.

---

## 3. Gates (antes de qualquer deploy)

- sidecar: `ruff`, `mypy`, `pytest` (tudo verde, incluindo os novos).
- admin e portal: `lint`, `typecheck`, `vitest`.
- Revisão adversarial (`gc-review`) do diff: cross-tenant no endpoint de ciclos, validação de
  login de licença, e a busca por TicketID não pode vazar chamado de outro cliente quando
  `customer_id` vier preenchido.
- Mudou o overlay Znuny → `make test` local (24 asserts).

## 4. Deploy no staging (`ssh gc`, profile `gerti`, **nunca** `make reset`)

1. `git pull` da branch na VM.
2. `znuny-web` rebuild (overlay do `AgentTicketSearch.pm`) + `znuny-daemon` up.
3. `sidecar` (e `sidecar-migrate` se houver migration), `admin`, `portal`.
4. Seed idempotente (`scripts/seed-demo.sh`): agente `georgia`, fatura aberta com valor,
   limpeza das licenças fantasmas.
5. `.env.prod`: `LICENSE_ENFORCEMENT_ENABLED=true` → `up -d sidecar admin`.
6. Conferir os 2 chamados aguardando aprovação (há 2 hoje) e a exigência ligada na Aurora.

## 5. Validação real e capturas

Um script Playwright (`e2e/roteiro_v01.py`) executa **os 26 passos do roteiro, na ordem e com as
mesmas credenciais do documento corrigido**, contra `gerti.was.dev.br`, `aurora.was.dev.br` e
`znuny-dev.was.dev.br`, salvando uma captura por passo em `docs/assets/teste-v01/depois/`
(viewport 1480, 2x). Passos que conferem estado no Znuny ou no banco também são checados pela
API/SQL e o resultado vai no log. O script falha se qualquer "Esperado" não aparecer na tela.

Os testes novos de `e2e/test_admin.py` / `test_portal.py` passam a fazer parte da suíte.

## 6. Documento de resposta

`docs/RESPOSTA-TESTE-ZNUNY-V01.md` → PDF por `scripts/docs-pdf.sh`:
- Abertura: placar novo (26/26), o que era defeito nosso e o que era documento, sem rodeio.
- Um bloco por NOK: **o que você viu** (o print do teste) → **por que aconteceu** (uma frase)
  → **o que mudou** → **como ficou** (captura nossa, do staging).
- Os passos bloqueados (A4, C3–C6, D4–D5) com captura própria, porque nunca foram vistos.
- O achado das colunas coladas, com o depois.
- Anexo: os 26 passos com ✅ e link da captura; como desligar a chave de licenciamento.

## 7. Documentação viva

- `.ia/OPS.md`: seção "Deploy das correções do teste V01" + status com as provas ao vivo.
- `.ia/DEMO.md`: agente `georgia`, licenças reais, fatura aberta, usuário help-desk.
- `.ia/INTEGRATION.md`: busca do GI por número/ID.

## 8. Ordem e paralelismo

T1, T3, T5 (admin/portal) ‖ T4 (Znuny) ‖ T2, T6 (sidecar + admin) → gates → review → deploy →
roteiro com capturas → documento de resposta → merge na `main` e atualização do `.ia/`.
