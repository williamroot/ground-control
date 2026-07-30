# Spec #4 — Console como capa de administração do Znuny

> **Para workers agênticos:** este documento é o **contrato**. Znuny (Perl/GI),
> sidecar e console trabalham em paralelo contra ele.

## Correção de rumo (supera o D20 parcialmente)

O D20 tirou de escopo filas, SLAs, estados/tipos de chamado, classes de CI,
calendário e gestão de agentes alegando "segunda fonte de verdade". **Estava
errado.** A invariante do projeto é *núcleo Znuny imutável* — não editar o
tarball, escrever só por overlay `Custom/` + Generic Interface. Ela nunca proibiu
**administrar** o Znuny através do GI; o próprio `GertiAdmin` já faz isso com
`CustomerCompanyAdd`/`CustomerUserAdd`/`SetPassword`.

O risco de segunda fonte de verdade é real, mas o remédio não é abrir mão da tela:
é **não persistir nada**.

### A regra desta spec, em uma linha

**O console não guarda um byte de configuração do Znuny.** Zero tabela nova, zero
cache que possa divergir. Toda tela lê ao vivo pelo GI e escreve ao vivo pelo GI.
O Znuny continua sendo o único armazenamento — a interface é uma capa.

Persistimos exatamente uma coisa: a **linha de auditoria** (quem mudou o quê e
quando), que é registro do nosso ato administrativo, não cópia do dado.

---

## Design: operações genéricas dirigidas por allowlist

6 objetos × 4 operações dariam 24 módulos Perl — e no `znuny/Dockerfile` **cada
`.pm` exige uma linha `COPY` e uma entrada no loop `perl -c`** (o esquecimento
disso já quebrou o projeto duas vezes: `TicketStats` e o XML de SysConfig).

Em vez disso: **4 operações genéricas** para os objetos de CRUD simples, dirigidas
por uma tabela de allowlist em um módulo auxiliar compartilhado.

### Guardas inegociáveis do dispatcher

1. **A requisição nunca nomeia classe ou método Perl.** Ela manda uma **chave de
   objeto** (`Queue`, `SLA`, `Service`, `Type`, `State`, `Priority`); o módulo
   traduz para classe/método por tabela **hardcoded**. Chave fora da tabela →
   erro, sem tentar carregar nada.
2. **Allowlist de campos por objeto.** Campo não previsto → **erro explícito**,
   nunca descartado em silêncio (descartar em silêncio faz o operador achar que
   salvou).
3. **Sem exclusão real.** O Znuny invalida com `ValidID = 2`. Não existe operação
   de delete nesta spec.
4. **Atribuição.** O corpo traz `AgentLogin`; o Perl resolve o `UserID` real (mesmo
   padrão de `TimeAccountingAdd`). Ação administrativa sem autor identificado não
   entra.
5. **`AccessToken` fail-closed**, reusando `GertiAdmin::AccessToken`
   (`ZNUNY_WS_TOKEN`).

---

## Bloco A — objetos de CRUD simples (risco baixo)

**Módulo auxiliar:** `znuny/Custom/Kernel/GenericInterface/Operation/GertiAdmin/AdminSpec.pm`
— só a tabela de allowlist e helpers. Não é operação, não entra no YAML (mas
**entra** no `COPY` e no `perl -c` do Dockerfile).

**Operações:** `AdminObjectList`, `AdminObjectGet`, `AdminObjectAdd`, `AdminObjectUpdate`.

| Chave | Classe Perl | Métodos | Campos graváveis |
|---|---|---|---|
| `Queue` | `Kernel::System::Queue` | `QueueList/Get/Add/Update` | `Name`, `GroupID`, `Comment`, `ValidID`, `SystemAddressID`, `SalutationID`, `SignatureID`, `FollowUpID`, `FollowUpLock`, `UnlockTimeout`, `FirstResponseTime`, `UpdateTime`, `SolutionTime`, `Calendar` |
| `SLA` | `Kernel::System::SLA` | `SLAList/Get/Add/Update` | `Name`, `Comment`, `ValidID`, `Calendar`, `FirstResponseTime`, `FirstResponseNotify`, `UpdateTime`, `UpdateNotify`, `SolutionTime`, `SolutionNotify`, `ServiceIDs` |
| `Service` | `Kernel::System::Service` | `ServiceList/Get/Add/Update` | `Name`, `ParentID`, `Comment`, `ValidID`, `TypeID`, `Criticality` |
| `Type` | `Kernel::System::Type` | `TypeList/Get/Add/Update` | `Name`, `ValidID` |
| `State` | `Kernel::System::State` | `StateList/Get/Add/Update` | `Name`, `Comment`, `ValidID`, `TypeID` |
| `Priority` | `Kernel::System::Priority` | `PriorityList/Get/Add/Update` | `Name`, `ValidID` |

`AdminObjectList` devolve também as **listas de apoio** que a UI precisa para
montar select (`GroupList`, `StateTypeList`, `ValidList`, `CalendarList`) —
senão o console teria que adivinhar ids.

## Bloco B — classes de CI (risco médio)

**Operações:** `AdminCiClassList`, `AdminCiClassDefinitionGet`, `AdminCiClassDefinitionSet`.

- Classes vêm de `Kernel::System::GeneralCatalog` (`ITSM::ConfigItem::Class`).
- Definição vem de `Kernel::System::ITSMConfigItem::Definition` (`DefinitionGet`,
  `DefinitionList`, `DefinitionAdd`).
- **`DefinitionCheck` é obrigatório antes de gravar.** Definição inválida →
  **422 com a mensagem do Znuny**, sem gravar. Uma definição quebrada derruba o
  CMDB inteiro; esta guarda não é opcional.
- Versionamento: `DefinitionAdd` cria nova versão, não sobrescreve — o histórico
  fica no Znuny.

## Bloco C — agentes e permissões (risco médio-alto)

**Operações:** `AdminAgentList`, `AdminAgentGet`, `AdminAgentSet`, `AdminGroupList`,
`AdminAgentGroupSet`.

- `Kernel::System::User` (`UserAdd`/`UserUpdate`/`UserList`/`GetUserData`),
  `Kernel::System::Group` (grupos, papéis e vínculos).
- **Nunca devolver hash de senha.** `AdminAgentGet` não retorna `UserPw` em
  hipótese alguma.
- Definir senha é operação **separada e explícita**, nunca efeito colateral de um
  update de cadastro.
- Mudança de permissão (grupo/papel) é a ação mais perigosa desta spec: registrar
  na auditoria **o antes e o depois**, não só "atualizou".
- Um agente não pode remover a si mesmo do grupo `admin` — guarda contra
  auto-lockout do console.

## Bloco D — SysConfig: calendário e jornada (risco alto)

**Operações:** `AdminSysConfigGet`, `AdminSysConfigSet`.

Este é o único bloco onde um erro afeta a **instância inteira**, não uma tela.
Guardas proporcionais:

1. **Allowlist fechada de settings** — só estes nomes são legíveis/graváveis:
   `TimeWorkingHours`, `TimeVacationDays`, `TimeVacationDaysOneTime`,
   `TimeZone`, `CalendarWeekDayStart`, e os equivalentes por calendário
   (`TimeWorkingHours::Calendar1`…`Calendar9`, idem vacation). Qualquer outro nome
   → erro, **sem** consultar o SysConfig.
2. **Validação de forma antes de escrever.** Jornada = hash `Dia → lista de horas
   inteiras 0–23`; feriado = `Mês → Dia → texto`. Forma errada → 422, sem tocar no
   Znuny.
3. **Fluxo correto e com liberação garantida:** `SettingLock` → `SettingUpdate` →
   `ConfigurationDeploy`. Se qualquer passo falhar, **liberar o lock** antes de
   propagar o erro — lock preso trava a administração do Znuny para todo mundo.
4. **Deploy é explícito**, com o `AgentLogin` como autor, e sempre auditado.

---

## Contrato do sidecar — `/v1/admin/znuny/*` (todos `get_admin_session`)

Nenhum destes endpoints toca o banco `gerti`, exceto para gravar auditoria.

| Método | Rota | Bloco |
|---|---|---|
| GET | `/v1/admin/znuny/objects/{object}` | A — lista + listas de apoio |
| GET | `/v1/admin/znuny/objects/{object}/{id}` | A |
| POST | `/v1/admin/znuny/objects/{object}` | A → 201 |
| PUT | `/v1/admin/znuny/objects/{object}/{id}` | A |
| GET | `/v1/admin/znuny/ci-classes` | B |
| GET | `/v1/admin/znuny/ci-classes/{id}/definition` | B |
| PUT | `/v1/admin/znuny/ci-classes/{id}/definition` | B — 422 se `DefinitionCheck` reprovar |
| GET | `/v1/admin/znuny/agents` · `/agents/{id}` | C |
| POST | `/v1/admin/znuny/agents` · PUT `/agents/{id}` | C |
| GET | `/v1/admin/znuny/groups` | C |
| PUT | `/v1/admin/znuny/agents/{id}/groups` | C — audita antes e depois |
| GET | `/v1/admin/znuny/calendar` | D |
| PUT | `/v1/admin/znuny/calendar` | D — allowlist + validação de forma |

`{object}` é validado contra a mesma allowlist do Perl **antes** de chamar o GI —
defesa em profundidade, não confiança mútua. Objeto desconhecido → **404**.

Erros: `ZnunyUnavailable` → 503; `ZnunyWriteError` → 422 com a mensagem do Znuny
repassada (o operador precisa saber *por que* o Znuny recusou).
**Toda escrita chama `audit_service.record`** com `entity` = `znuny_<objeto>`.

---

## Superfície do console (`apps/admin`)

| Rota | Tela |
|---|---|
| `/znuny/filas` | Filas: lista, criar, editar, invalidar, tempos de SLA por fila |
| `/znuny/sla` | Políticas de SLA: tempos de resposta/atualização/solução + notificação |
| `/znuny/servicos` | Serviços (com hierarquia por `ParentID`) |
| `/znuny/classificacao` | Tipos, estados e prioridades — três abas, mesma tela |
| `/znuny/classes-ci` | Classes de CI + editor de definição com validação antes de salvar |
| `/znuny/agentes` | Agentes e vínculo com grupos/papéis |
| `/znuny/calendario` | Jornada de trabalho e feriados |

Todas com aviso visível de que **editam o Znuny ao vivo**, os três estados
(carregando/vazio/erro), confirmação em ação destrutiva ou de permissão, e texto
em português do Brasil.

---

## Definição de pronto

Operação GI com `perl -c` verde no build **e** `COPY` no Dockerfile **e** entrada
no loop **e** registro no `GertiAdmin.yml` · rota do sidecar com teste de 401, 404
de objeto desconhecido e 422 de validação · tela com os três estados · auditoria
em toda escrita · nenhuma tabela nova · `.ia/` atualizado no mesmo PR.
