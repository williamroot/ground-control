# Como testar a paridade de interface (#3) — passo a passo

Este roteiro cobre as seis funcionalidades novas: **base de conhecimento**,
**catálogo de serviços**, **notificações e preferências**, **identidade visual
editável**, **trilha de auditoria** e **saúde do sistema + busca global**. Tudo
roda no ambiente de **staging**. As credenciais abaixo são de demonstração e
públicas — não são de cliente real.

## Visão geral do que você vai testar

Você vai assumir **dois papéis**. Primeiro o de **operador do MSP** (equipe Gerti),
que publica conhecimento, monta o catálogo de serviços do cliente e configura a
marca dele. Depois o de **cliente final**, que consome tudo isso no portal
white-label. No fim, você volta ao papel de operador para conferir que **cada
ação sua ficou registrada na auditoria**.

| Papel | URL | Login |
|---|---|---|
| Console (operador MSP) | https://gerti.was.dev.br | `william` / `Gerti@Demo2026` |
| Portal do cliente (Aurora Móveis) | https://aurora.was.dev.br | `eduardo.salvi` / `Aurora@Demo2026` |
| Portal do cliente (TechNova) | https://technova.was.dev.br | `admin.tech@technova.example` / `TechNova@Demo2026` |

> **Login aceita e-mail ou usuário.** Os dois formatos funcionam nos dois lados —
> `william` ou `williamalvesroot@gmail.com` no console; `eduardo.salvi` ou
> `eduardo.salvi@auroramoveis.com.br` no portal. É a mesma conta, não duas.


> O TechNova existe aqui por um motivo só: provar que **um cliente nunca vê o
> conteúdo do outro**. A Parte 6 é a mais importante deste roteiro.

---

## Parte 1 — Publicar um artigo de conhecimento (no console)

1. Acesse **https://gerti.was.dev.br** e entre com `william` / `Gerti@Demo2026`.
2. Vá em **Clientes** → abra **Aurora Móveis**.
3. Clique na aba **Conhecimento**.
4. Clique em **Novo artigo** e preencha:
   - **Título:** `Como solicitar acesso à VPN`
   - **Resumo:** `Passo a passo para pedir e configurar o acesso remoto.`
   - **Conteúdo:** escreva alguns parágrafos usando markdown — inclua um
     `## subtítulo`, uma lista com `-` e um trecho com `**negrito**`.
   - **Categoria:** `Redes`
   - **Tags:** `vpn, acesso remoto, rede`
   - **Visibilidade:** `Público`
   - **Situação:** `Publicado`
5. Salve.

✅ **Esperado:** o artigo aparece na lista com a situação **Publicado** e a
categoria **Redes**.

6. Crie um **segundo** artigo, agora com **Visibilidade: Interno** e
   **Situação: Rascunho**. Título: `Runbook interno — reset de VPN`.

✅ **Esperado:** os dois aparecem na lista do console. Guarde essa diferença — ela
é testada na Parte 6.

### Validações que você deve ver falhar

7. Tente salvar um artigo com **título de 2 caracteres** → a tela recusa com
   mensagem de campo obrigatório/curto.
8. Tente colocar **11 tags** → a tela recusa (o limite é 10).

---

## Parte 2 — Montar o catálogo de serviços (no console)

1. Ainda em **Aurora Móveis**, clique na aba **Catálogo**.
2. Clique em **Novo serviço** e preencha:
   - **Nome:** `Solicitar acesso VPN`
   - **Categoria:** `Redes`
   - **Descrição:** `Liberação de acesso remoto para colaborador.`
   - **SLA (horas):** `8`
   - **Ícone:** `shield`
   - **Fila (Znuny):** deixe a fila padrão de suporte do ambiente
   - **Ativo:** ligado
   - **Ordem:** `1`
3. Salve. Crie um segundo serviço, **Ativo desligado**, chamado
   `Serviço desativado (teste)`.

✅ **Esperado:** os dois aparecem na lista do console, com o segundo marcado como
inativo.

### Validação que você deve ver falhar

4. Tente salvar com **SLA = 0** ou **SLA = 5000** → recusado (a faixa é 1 a 720).

---

## Parte 3 — Configurar a identidade visual (no console)

1. Em **Aurora Móveis**, clique na aba **Identidade visual**.
2. Altere a **cor primária** e veja o **preview ao lado mudar na hora**.
3. Digite uma cor inválida no campo hexadecimal (ex.: `#XYZ`).

✅ **Esperado:** a tela recusa com mensagem clara e **não salva**.

4. Coloque uma URL de logo começando com `http://` (sem o `s`).

✅ **Esperado:** recusado — só `https://` é aceito.

5. Volte a cor para o laranja/âmbar original da Aurora e salve.

✅ **Esperado:** confirmação de sucesso real (não um "Salvo!" que some sozinho).

---

## Parte 4 — Ver tudo isso como cliente (no portal)

1. Abra uma **janela anônima** e acesse **https://aurora.was.dev.br**.
2. Entre com `eduardo.salvi` / `Aurora@Demo2026`.
3. No menu, clique em **Base de Conhecimento**.

✅ **Esperado:** você vê **apenas** `Como solicitar acesso à VPN`. O runbook
interno **não aparece** — ele é interno e está em rascunho.

4. Clique no artigo.

✅ **Esperado:** o markdown aparece formatado (subtítulo, lista e negrito), com as
tags e o contador de visualizações. Recarregue a página: o contador **sobe**.

5. Volte e clique em **Catálogo**.

✅ **Esperado:** você vê **apenas** `Solicitar acesso VPN`, com o selo **SLA 8h**.
O serviço desativado **não aparece**.

6. Clique em **Solicitar**.

✅ **Esperado:** você cai no formulário de novo chamado com **assunto, fila e
serviço já preenchidos** — e todos ainda editáveis.

7. Envie o chamado.

✅ **Esperado:** o chamado é criado normalmente (é um ticket Znuny de verdade).
**Anote o número** — você vai limpá-lo na Parte 8.

---

## Parte 5 — Notificações, perfil e busca (no portal)

1. No menu, clique em **Notificações**.

✅ **Esperado:** a lista carrega. Se ainda não houver nenhuma, você verá o estado
vazio explicando isso — não uma tela em branco.

2. Para gerar uma notificação de verdade: volte ao **console**, abra
   **Aurora Móveis → Faturas** e gere uma fatura de um ciclo fechado. Volte ao
   portal e recarregue **Notificações**.

✅ **Esperado:** aparece uma notificação de **fatura emitida**, marcada como não
lida, e o indicador de não lidas no topo mostra a contagem.

3. Clique na notificação.

✅ **Esperado:** ela é marcada como lida (muda o destaque visual) e leva você à
fatura.

4. Clique em **Marcar todas como lidas**.

✅ **Esperado:** o contador zera e o botão some.

5. Vá em **Perfil**. Desligue **Alertas de SLA**, troque o **tema** e salve.
   Recarregue a página (F5).

✅ **Esperado:** as preferências **persistiram**. Este é o ponto: no protótipo de
referência o "Salvar" era falso e o estado se perdia ao navegar.

6. Vá em **Busca** e digite `vpn`.

✅ **Esperado:** aparecem seções separadas para **Chamados**, **Ativos**,
**Base de Conhecimento** e **Catálogo**, e clicar em qualquer resultado leva à
página certa. Digite só `v` (1 letra): a busca não dispara.

---

## Parte 6 — Testar o isolamento entre clientes (a parte importante)

### 6.1 "O conteúdo de um cliente nunca vaza para o outro"

1. Em outra janela anônima, acesse **https://technova.was.dev.br** e entre com
   `admin.tech@technova.example` / `TechNova@Demo2026`.
2. Vá em **Base de Conhecimento** e em **Catálogo**.

✅ **Esperado:** **vazios**. Nada da Aurora aparece aqui. (Tecnicamente: as
tabelas têm `FORCE ROW LEVEL SECURITY` no Postgres e a consulta roda com o
`tenant_id` da sessão — não é um filtro de tela que dá para burlar.)

3. Ainda como TechNova, cole na barra de endereço a URL do artigo da Aurora:
   `https://technova.was.dev.br/base-conhecimento/como-solicitar-acesso-a-vpn`

✅ **Esperado:** **"Artigo não encontrado"** — e não uma mensagem de "sem
permissão". A diferença importa: responder 404 não revela nem que o artigo existe.

### 6.2 "Rascunho e conteúdo interno não vazam para o cliente"

4. Como Aurora, tente abrir o runbook interno pela URL direta
   (`/base-conhecimento/runbook-interno-reset-de-vpn`).

✅ **Esperado:** **"Artigo não encontrado"**. Só `Público` + `Publicado` chega ao
cliente.

### 6.3 "A notificação de um usuário não é de outro"

5. Como Aurora, faça login com **outro** usuário (`carla.dorneles` /
   `Aurora@Demo2026`) e abra **Notificações**.

✅ **Esperado:** ela **não** vê as notificações do Eduardo, mesmo sendo da mesma
empresa. O escopo é por destinatário, não só por cliente.

---

## Parte 7 — Auditoria e saúde do sistema (no console)

1. Volte ao console e clique em **Auditoria** no menu.

✅ **Esperado:** a tabela lista **as ações que você acabou de fazer** — criação dos
artigos, dos itens de catálogo, a alteração de identidade visual e a geração da
fatura — com data/hora, quem fez, a ação e a descrição.

2. Filtre por **Ação: Criação** e depois por **Cliente: Aurora Móveis**.

✅ **Esperado:** os filtros funcionam e combinam entre si. A paginação avança e
volta.

3. Confira que **nenhuma linha contém senha, token ou o corpo de um chamado**.

✅ **Esperado:** só metadado. Isso é regra, não acaso.

4. Clique em **Sistema** no menu.

✅ **Esperado:** cartões de **banco**, **Znuny**, **worker de consumo**, **IA** e
**Asaas**, cada um verde ou vermelho, com latência quando houver e a versão do
sidecar. O Asaas provavelmente aparece **desligado** — é o esperado enquanto a
chave não estiver no `.env.prod`.

5. Clique em **Verificar novamente**.

✅ **Esperado:** os valores são recalculados.

> Se uma sonda estiver vermelha, a página continua carregando e mostra **qual**
> caiu. Uma integração fora do ar não pode derrubar o painel que existe justamente
> para avisar que ela caiu.

---

## Parte 8 — Limpeza (faça, por favor)

1. **Console → Aurora Móveis → Conhecimento:** exclua os dois artigos de teste
   (o excluir pede confirmação com o título — confirme).
2. **Console → Aurora Móveis → Catálogo:** exclua os dois serviços de teste.
3. **Console → Aurora Móveis → Identidade visual:** confirme que as cores voltaram
   ao laranja/âmbar da Aurora.
4. **Chamado criado na Parte 4:** feche/exclua pelo painel do Znuny
   (https://znuny-dev.was.dev.br).
5. **Fatura gerada na Parte 5:** marque como cancelada (`void`) pelo console.

> A **auditoria é append-only por design** — os registros das suas ações de teste
> permanecem, inclusive os das exclusões acima. Isso é correto: uma trilha que se
> apaga não é uma trilha.

---

## Solução de problemas

| Sintoma | Causa provável | O que fazer |
|---|---|---|
| Menu não mostra as opções novas | `portal`/`admin` não foram reconstruídos | `$DC build portal admin && $DC up -d portal admin` — o Nuxt é compilado na imagem, reiniciar não basta |
| Tela nova responde 404 na API | `sidecar` sem rebuild ou migration não aplicada | `$DC build sidecar && $DC run --rm sidecar-migrate` (aguarde Exit 0) e então `$DC up -d sidecar` |
| Artigo salva no console mas não aparece no portal | Está como `Rascunho` ou `Interno` | Publique e marque como `Público` |
| Portal cai em `/login` ao atualizar a página | Cookie/host não repassado no SSR | Confira `useSidecarHeaders()` na página — é o que preserva a sessão no refresh |
| Auditoria vazia | Nenhuma ação admin depois do deploy | Faça qualquer escrita no console e recarregue |
| Cartão do Znuny vermelho em **Sistema** | `ZNUNY_WS_TOKEN`/URL do GI errados no `.env.prod` | Confira o runbook do #1G-a em `.ia/OPS.md` |

---

## Referência rápida (terminal, sem UI)

Substitua `<COOKIE>` pelo valor do cookie da sua sessão (`gsid` para cliente,
`gsid_adm` para agente) copiado do navegador.

```sh
# Saúde do sistema (agente)
curl -fsS https://api-dev.was.dev.br/v1/admin/system/health -H "cookie: gsid_adm=<COOKIE>" | jq

# Base de conhecimento do cliente
curl -fsS https://aurora.was.dev.br/api/portal/kb/articles -H "cookie: gsid=<COOKIE>" | jq

# Prova de isolamento: o mesmo artigo pedido pelo tenant errado → 404
curl -s -o /dev/null -w '%{http_code}\n' \
  https://technova.was.dev.br/api/portal/kb/articles/como-solicitar-acesso-a-vpn \
  -H "cookie: gsid=<COOKIE_TECHNOVA>"      # → 404

# Auditoria filtrada (agente)
curl -fsS 'https://api-dev.was.dev.br/v1/admin/audit-logs?action=create&limit=20' \
  -H "cookie: gsid_adm=<COOKIE>" | jq

# Limite de paginação é 200 — acima disso é recusado
curl -s -o /dev/null -w '%{http_code}\n' \
  'https://api-dev.was.dev.br/v1/admin/audit-logs?limit=500' \
  -H "cookie: gsid_adm=<COOKIE>"           # → 422
```

Prova de RLS direto no banco (pelo host, via `ssh gc`):

```sh
# Sem o GUC app.current_tenant, o papel do runtime não enxerga nada — fail-closed.
docker compose exec -T postgres psql -U gerti_sidecar -d "$POSTGRES_DB" \
  -c "select count(*) from gerti.kb_article;"     # → 0
```
