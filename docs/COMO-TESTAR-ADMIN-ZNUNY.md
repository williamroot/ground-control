# Como testar a capa de administração do Znuny (#4) — passo a passo

O console agora administra o **próprio Znuny**: filas, SLAs, serviços,
tipos/estados/prioridades, classes de CI, agentes/permissões e calendário. Tudo ao
vivo, pelo Generic Interface — o console **não guarda nada**, o Znuny continua
sendo o único armazenamento.

> **Leia antes de começar.** Diferente das outras telas do console, estas mudam a
> configuração da instância do Znuny. Não há rascunho nem desfazer. Este roteiro
> foi escrito para ser rodado em **staging**, e a Parte 6 (calendário) pede que
> você anote o estado atual antes de mexer.

| Papel | URL | Login |
|---|---|---|
| Console (operador MSP) | https://gerti.was.dev.br | `william` / `Gerti@Demo2026` |
| Painel nativo do Znuny (para conferir) | https://znuny-dev.was.dev.br | mesmo login |

A conferência cruzada é o ponto deste roteiro: **tudo que você fizer no console
tem que aparecer no painel nativo do Znuny**, porque é lá que o dado mora.

---

## Parte 1 — Filas

1. Entre no console e abra **Znuny → Filas**.

✅ **Esperado:** a lista traz as filas **reais** da sua instância (as mesmas do
painel do Znuny em *Admin → Filas*), não uma lista de exemplo.

2. Clique em **Nova fila** e crie `Teste Paridade` no grupo `users`, com tempo de
   primeira resposta `240` minutos.

✅ **Esperado:** ao lado do campo de minutos aparece o equivalente legível
("240 min · 4 h") — o Znuny trabalha em minutos e é fácil errar uma ordem de
grandeza aqui.

3. Abra o painel nativo do Znuny em *Admin → Filas*.

✅ **Esperado:** `Teste Paridade` está lá, com os mesmos valores. **Esta é a prova
de que é uma capa, e não um cadastro paralelo.**

4. De volta ao console, edite a fila e clique em **Invalidar**.

✅ **Esperado:** o botão diz "Invalidar", **não "Excluir"** — no Znuny nada é
apagado, o registro recebe `ValidID = 2`. Confirme e veja a fila mudar para
inválida (e continuar existindo no painel do Znuny).

---

## Parte 2 — SLAs, serviços e classificação

1. **Znuny → SLA**: crie uma política com tempos de resposta/atualização/solução e
   confira que ela aparece no painel nativo em *Admin → SLA*.
2. **Znuny → Serviços**: crie `Teste Pai`, depois crie `Teste Filho` escolhendo
   `Teste Pai` como pai.

✅ **Esperado:** a lista mostra a hierarquia indentada, e ao editar `Teste Pai` o
select de pai **não oferece** `Teste Pai` nem `Teste Filho` — a guarda anti-ciclo
impede que você crie um serviço que é pai de si mesmo.

3. **Znuny → Classificação**: as três abas (Tipos, Estados, Prioridades) listam os
   valores reais. Crie um tipo `Teste` e confirme no painel nativo.

### O que deve falhar

4. Tente salvar uma fila **sem nome**.

✅ **Esperado:** recusado com mensagem clara.

5. Tente criar uma fila com um nome **que já existe**.

✅ **Esperado:** a tela mostra **a mensagem que o Znuny devolveu**, não um erro
genérico. Você precisa saber *por que* o Znuny recusou.

---

## Parte 3 — Classes de CI (cuidado: afeta o CMDB do cliente)

1. Abra **Znuny → Classes de CI** e selecione `Computer`.

✅ **Esperado:** aparece a definição YAML real da classe.

2. **Quebre a definição de propósito** — apague dois espaços de indentação no meio
   de um bloco — e clique em salvar.

✅ **Esperado:** **não salva**, e a tela mostra a mensagem do `DefinitionCheck` do
Znuny explicando o erro. Esta guarda existe porque uma definição inválida derruba
o CMDB de quem usa a classe.

3. Corrija e salve de verdade (pode salvar igual ao que estava).

✅ **Esperado:** a tela avisa que salvar **cria uma nova versão** — o Znuny
versiona a definição, não sobrescreve. Confira em *ITSM → Classes de Config Item*
no painel nativo.

---

## Parte 4 — Agentes e permissões (a parte mais perigosa)

1. **Znuny → Agentes**: a lista traz os agentes reais.

✅ **Esperado crítico:** em nenhum lugar da tela — nem no formulário, nem no
detalhe, nem no HTML da página — aparece senha ou hash de senha. Abra o inspetor
do navegador e confirme.

2. Crie um agente `teste.paridade`.

✅ **Esperado:** o formulário de cadastro **não tem campo de senha**. Definir senha
é um botão separado e explícito — nunca um efeito colateral de salvar o cadastro.

3. Clique em **Permissões** no agente `teste.paridade`, marque um grupo e avance.

✅ **Esperado:** antes de salvar aparece uma confirmação com o **resumo do que
muda** — o que ele vai ganhar e o que vai perder. Só então salva.

4. **O teste que importa:** logado como `william`, abra as permissões do **próprio
   `william`** e tente remover o grupo `admin`.

✅ **Esperado:** **recusado**, com explicação. A guarda é anti-lockout, e ela vive
no servidor (no Perl), não só na tela — então não adianta burlar pelo navegador.

5. Abra **Auditoria** no menu.

✅ **Esperado:** a mudança de permissão da etapa 3 aparece registrando **o antes e
o depois**, não apenas "atualizou".

---

## Parte 5 — Prova de que nada é persistido

Este é o teste de invariante da spec inteira. Pelo terminal, no host:

```sh
ssh gc 'cd ~/ground-control && set -a && . ./.env && set +a && \
  docker compose exec -T postgres psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -t -c \
  "select count(*) from information_schema.tables \
   where table_schema='"'"'gerti'"'"' and table_name like '"'"'znuny%'"'"';"'
```

✅ **Esperado: `0`.** Nenhuma tabela de configuração do Znuny existe no nosso
banco. Tudo que você viu nas telas anteriores foi lido ao vivo do Znuny.

E a tentativa de burlar o dispatcher genérico:

```sh
# objeto fora da allowlist não pode virar uma classe Perl arbitrária
curl -s -o /dev/null -w '%{http_code}\n' \
  'https://api-dev.was.dev.br/v1/admin/znuny/objects/Kernel::System::Ticket' \
  -H "cookie: gsid_adm=<COOKIE>"      # → 404
```

---

## Parte 6 — Calendário e jornada (faça por último, e anote antes)

> **Antes de mexer:** abra **Znuny → Calendário**, aba *Jornada de trabalho*, e
> **anote (ou tire um print) da grade atual**. Você vai restaurá-la no fim. Este é
> o único ponto do console que grava em SysConfig e dispara deploy de
> configuração: mudar a jornada muda o cálculo de SLA de **todos** os chamados.

1. Na grade de 7 dias × 24 horas, clique no atalho **"Comercial 8–18, seg a sex"**.

✅ **Esperado:** a grade preenche e o total semanal mostra **50 h**.

2. Clique em salvar.

✅ **Esperado:** aparece uma confirmação com o resumo (horas semanais antes → depois)
e o aviso explícito sobre o impacto no SLA. Só depois de confirmar é que grava.

3. Confira em *Admin → Configuração do Sistema* no painel nativo, buscando
   `TimeWorkingHours`.

✅ **Esperado:** o valor bate com o que você montou na grade.

4. Vá à aba **Feriados** e adicione um feriado recorrente (mês/dia/descrição) e um
   de data específica (ano/mês/dia/descrição).

✅ **Esperado:** o recorrente vai para `TimeVacationDays`, o de data específica para
`TimeVacationDaysOneTime` — que tem um nível a mais (ano). Confira os dois no
painel nativo.

5. **Restaure a jornada anotada no início** e salve.

---

## Parte 7 — Limpeza

1. Invalide a fila, o SLA, os serviços e o tipo de teste (todos no console).
2. Invalide o agente `teste.paridade`.
3. Remova os dois feriados de teste.
4. Confirme que a jornada voltou ao valor original.

> A **auditoria é append-only**: os registros das suas ações de teste permanecem,
> inclusive os das invalidações. Isso é correto — uma trilha que se apaga não é
> uma trilha.

---

## Solução de problemas

| Sintoma | Causa provável | O que fazer |
|---|---|---|
| Tela `/znuny/*` responde 404 na API | webservice `GertiAdmin` não foi atualizado após o rebuild | Rodar o passo 2 do runbook (`Admin::WebService::Update --webservice-id`) |
| `Can't load operation backend module ...Admin...` | `.pm` sem `COPY` no Dockerfile ou fora do loop `perl -c` | Conferir o checklist em `.claude/agents/gc-znuny.md` e rebuildar |
| Menu não mostra "Znuny" | `admin` não foi reconstruído | `$DC build admin && $DC up -d admin` — o Nuxt é compilado na imagem |
| Salvar calendário dá erro e nada muda | Forma inválida ou setting fora da allowlist | É o comportamento correto: o backend valida antes e libera o lock. Corrija a forma e tente de novo |
| Administração do Znuny travada após um erro no calendário | `SettingLock` preso | Não deveria acontecer (liberamos em toda falha), e o Znuny expira o lock sozinho em 5 min. Se persistir, conferir `AdminSysConfigSet.pm` |
| Mudança feita no console não aparece no Znuny | Você está olhando um cache do navegador | Recarregue o painel nativo; não há cache do nosso lado (D21) |
