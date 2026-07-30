# Ground Control — o que foi entregue e o que vem a seguir

## Em uma página

O Ground Control é a plataforma de Service Desk que a operação usa para atender
seus clientes: cada cliente final tem o **seu próprio portal, com a sua marca**, e
a equipe trabalha num console único. O núcleo é o Znuny — um sistema de ticketing
maduro e open-source — e tudo que construímos em volta existe para resolver o que
ele não resolve sozinho: contratos de MSP, faturamento por consumo, portal
white-label e automação.

Esta rodada entregou **duas frentes**. A primeira completou a experiência do
cliente final e da equipe: base de conhecimento, catálogo de serviços,
notificações, identidade visual editável, trilha de auditoria e painel de saúde.
A segunda tirou a equipe de dentro do painel técnico do Znuny: filas, SLAs,
serviços, classes de ativo, agentes e calendário agora se administram pelo próprio
console.

Tudo está **instalado e verificado no ambiente de homologação**.

---

## O que o cliente final ganhou

### Base de conhecimento

Artigos de autoatendimento no portal, com busca e organização por categoria. A
equipe publica pelo console e escolhe se o artigo é **público** (o cliente vê) ou
**interno** (só a equipe). Enquanto está em rascunho, ninguém de fora enxerga.

Efeito prático: parte dos chamados repetitivos deixa de virar chamado.

### Catálogo de serviços

Uma vitrine do que a operação oferece — "solicitar acesso VPN", "provisionar novo
usuário" — cada item com o prazo de atendimento à vista. O cliente escolhe o
serviço e **o chamado abre já preenchido**, na fila certa, com a prioridade certa.

Efeito prático: menos chamado mal classificado chegando, menos retrabalho de
triagem.

### Notificações e preferências

Central de avisos no portal, com contador de não lidas. O cliente é avisado quando
uma fatura é emitida ou quando há movimento no chamado dele. Cada pessoa ajusta o
que quer receber e o tema visual — e a escolha **persiste de verdade**.

### Busca unificada

Um único campo que procura ao mesmo tempo em chamados, ativos, base de
conhecimento e catálogo, separando os resultados por tipo.

---

## O que a operação ganhou

### Identidade visual por cliente, editável

A marca de cada cliente — nome, cores e logotipo — passa a ser configurada pela
equipe, com **prévia ao vivo** antes de salvar. Antes isso exigia intervenção
técnica.

### Trilha de auditoria

Toda ação administrativa fica registrada: quem fez, o quê, em qual cliente e
quando. Com busca, filtro por tipo de ação, por cliente e por período.

Mudança de permissão registra **o antes e o depois** — não apenas "alterou". E o
registro nunca guarda senha, token ou o conteúdo de um chamado.

### Painel de saúde

Uma tela que responde "está tudo funcionando?" olhando cada peça: banco de dados,
integração com o Znuny, processamento de consumo, inteligência artificial e meio
de pagamento. Cada uma com seu próprio indicador.

Se uma integração cai, o painel diz **qual** caiu — ele não cai junto.

### Administração do Znuny pelo console

A equipe passa a configurar pelo próprio console, sem entrar no painel técnico:

| Área | O que dá para fazer |
|---|---|
| **Filas** | Criar e ajustar filas de atendimento e seus prazos |
| **Políticas de SLA** | Tempos de resposta, atualização e solução, com escalonamento |
| **Serviços** | Catálogo de serviços em hierarquia |
| **Classificação** | Tipos de chamado, estados e prioridades |
| **Classes de ativo** | Estrutura do inventário (CMDB) de cada cliente |
| **Agentes** | Cadastro da equipe e permissões de acesso |
| **Calendário** | Jornada de trabalho e feriados — o que define o cálculo de SLA |

Uma decisão de arquitetura que vale explicar, porque protege o cliente: **o
console não guarda cópia dessas configurações**. Ele lê e escreve direto no Znuny.
Não existe "duas verdades" que possam divergir — o que você vê no console é o que
está valendo no sistema.

---

## Cuidados que ficaram embutidos

Estes não aparecem na tela, mas definem a confiabilidade do que foi entregue.

**Isolamento entre clientes.** A separação é imposta pelo banco de dados, não por
filtro de tela. Um cliente não alcança dado de outro nem forçando o endereço
diretamente no navegador — e a resposta é "não encontrado", que sequer revela que
o registro existe.

**Configuração destrutiva não passa sem validação.** Alterar a estrutura de
inventário de um cliente só é aceito depois que o próprio Znuny valida a mudança.
Uma definição inválida é recusada com a explicação do erro, sem gravar.

**Ninguém se tranca para fora.** Um administrador não consegue remover a própria
permissão de administrador — a trava está no servidor, não na tela.

**Nada é apagado.** O Znuny invalida registros em vez de excluir, e as telas dizem
"Invalidar", não "Excluir". Histórico não se perde.

**Senhas não circulam.** Nenhuma tela, resposta de sistema ou registro de auditoria
carrega senha ou o hash dela. Definir senha é uma ação separada e explícita.

**Login por e-mail ou usuário**, nos dois lados, indiferentemente.

---

## O que já existia antes desta rodada

Para dar a dimensão do conjunto: abertura e acompanhamento de chamados no portal,
contratos com banco de horas e crédito, medição automática de consumo, faturas com
PDF na marca do cliente, inventário de ativos, agente de inventário que se
autorregistra nas máquinas, pesquisa de satisfação, painéis de indicadores,
automação por regras, assistente de inteligência artificial para a equipe e para o
cliente, e contratação self-service com pagamento.

---

## Acessos do ambiente de demonstração

> **Leia antes de usar.** As credenciais abaixo são de **demonstração**, do
> ambiente de **homologação**, e são padronizadas de propósito para apresentação.
> Não são de nenhum cliente real e **não devem ser reaproveitadas em produção** —
> o ambiente produtivo terá senhas próprias, individuais e não compartilhadas.
> O login aceita **e-mail ou usuário**, indiferentemente.

### Endereços

| Ambiente | Endereço | Para quem |
|---|---|---|
| Console da operação | `gerti.was.dev.br` | Equipe do provedor |
| Portal — Aurora Móveis | `aurora.was.dev.br` | Cliente final (exemplo 1) |
| Portal — TechNova | `technova.was.dev.br` | Cliente final (exemplo 2) |
| Painel técnico do Znuny | `znuny-dev.was.dev.br` | Conferência técnica |
| Site institucional | `groundcontrol.was.dev.br` | Público |

### Equipe do provedor — console

| Usuário | Nome | Papel | Senha |
|---|---|---|---|
| `william` | William Alves | Owner / Administrador | `Gerti@Demo2026` |
| `bruno.cardoso` | Bruno Cardoso | Suporte N1 | `Gerti@Demo2026` |
| `patricia.menezes` | Patrícia Menezes | Suporte N1 | `Gerti@Demo2026` |
| `rafael.tavares` | Rafael Tavares | Suporte N2 (especialista) | `Gerti@Demo2026` |
| `diego.fontana` | Diego Fontana | Atendimento em campo | `Gerti@Demo2026` |

### Cliente Aurora Móveis — portal

| Usuário | Nome | Cargo | Senha |
|---|---|---|---|
| `eduardo.salvi` | Eduardo Salvi | Gerente de TI | `Aurora@Demo2026` |
| `mariana.bianchi` | Mariana Bianchi | Coordenadora Administrativa | `Aurora@Demo2026` |
| `carla.dorneles` | Carla Dorneles | Analista Financeiro | `Aurora@Demo2026` |
| `fernando.rech` | Fernando Rech | Supervisor de Produção | `Aurora@Demo2026` |
| `juliana.peruzzo` | Juliana Peruzzo | Assistente de RH | `Aurora@Demo2026` |

### Cliente TechNova — portal

| Usuário | Senha | Observação |
|---|---|---|
| `admin.tech@technova.example` | `TechNova@Demo2026` | Segundo cliente, existe para demonstrar o isolamento |

### Um roteiro curto de demonstração

1. Entre no console como `william` e abra **Znuny → Filas**. Crie uma fila.
2. Abra o painel técnico do Znuny em *Admin → Filas*: a fila está lá. **Essa é a
   prova de que o console administra o sistema de verdade, e não mantém um
   cadastro paralelo.**
3. No console, vá em **Clientes → Aurora Móveis → Conhecimento** e publique um
   artigo.
4. Entre no portal da Aurora como `eduardo.salvi` e veja o artigo em **Base de
   Conhecimento**.
5. Abra **Catálogo**, clique em **Solicitar**: o chamado nasce preenchido.
6. **O teste que mais importa:** copie o endereço do artigo da Aurora e troque o
   domínio para o da TechNova. A resposta é "não encontrado" — o conteúdo de um
   cliente não alcança o outro, e o sistema sequer confirma que aquele registro
   existe.

---

## Próximos passos

### Curto prazo — completam o que já está no ar

| Item | O que resolve |
|---|---|
| **Painel de SLA** | Uma tela dedicada aos chamados em risco ou já estourados, para ação imediata |
| **Regras de notificação** | Escolher, por evento, quem é avisado e por qual canal |
| **Parâmetros de faturamento** | Valor-hora padrão e tabela de preços por tipo de serviço |
| **Agenda da equipe** | Turnos e ausências, para dimensionar a capacidade da semana |

### Médio prazo — ampliam o produto

| Item | O que resolve |
|---|---|
| **Relatórios exportáveis** | Levar os indicadores para PDF e planilha, incluindo relatório periódico automático |
| **Controle de estoque** | Equipamentos e peças em posse da operação, além dos ativos já instalados no cliente |
| **Portal em aplicativo** | Abrir e acompanhar chamados pelo celular |

### Estrutural — sustentam o crescimento

| Item | O que resolve |
|---|---|
| **Rotina de backup** | Cópia automática com retenção definida e restauração testada |
| **Monitoramento** | Alerta proativo quando uma integração para, em vez de descoberta pelo painel |
| **Publicação em produção** | Endereços definitivos e certificados para o ambiente produtivo |

---

## Estado atual, com transparência

O que está descrito aqui está **instalado e verificado em homologação**, incluindo
teste pelo navegador de cada tela nova, com os dois perfis (equipe e cliente).

Três pontos honestos sobre o ambiente:

1. A página pública de contratação está construída e funcional, mas ainda **não
   tem endereço publicado** — depende de uma configuração de DNS e da chave da
   operadora de pagamento.
2. O processamento automático de consumo está **parado desde 24 de junho** no
   ambiente de homologação. É anterior a esta entrega e foi justamente o novo
   painel de saúde que tornou isso visível — o que é o próprio painel funcionando.
3. Um caminho de falha específico do calendário (interrupção no meio da gravação)
   foi validado por análise e por teste automatizado, mas **ainda não exercitado
   contra o sistema real**.

Nenhum dos três impede o uso do que foi entregue.
