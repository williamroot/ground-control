# R1K — Spike: congelar Znuny ITSM (CMDB / Config Items)

> **Spec #1K · Fase 0 (SPIKE, bloqueante).** Rodado contra o `znuny-web` **vivo**
> (stack local, Znuny **7.2.3**, build `f7d0f3c`). Tudo abaixo foi verificado ao
> vivo — pacotes instalados de verdade, classe inspecionada, CI criado, busca por
> atributo e link Ticket↔CI executados. As Fases 1+ consomem este doc; onde divergir
> do plano, vale a **realidade** registrada aqui.

---

## 0. TL;DR / divergências do plano (LEIA)

1. **ImportExport NÃO é necessário.** `ITSMConfigurationManagement-7.2.1` depende só de
   `ITSMCore`, que depende só de `GeneralCatalog`. São **3 pacotes**, não 4. ImportExport
   nem está no repositório online (`addons.znuny.com/public`) — e o CMDB instala/funciona
   sem ele. **Cadeia real:** `GeneralCatalog → ITSMCore → ITSMConfigurationManagement`.
2. **As 5 classes padrão JÁ vêm com um atributo de empresa-cliente nativo:** `Key: CustomerID`,
   `Input: Type: CustomerCompany`. **Não precisamos ADICIONAR** um atributo `CustomerCompany` —
   o escopo por tenant usa o atributo nativo **`CustomerID`** (tipo `CustomerCompany`). O
   `ensure-cmdb-*.pl` da Fase 1 vira opcional/no-op (a definição default já basta); se mesmo
   assim quiserem reforçar, o mecanismo idempotente está na §3.
3. **Formato da definição de classe é YAML** (não o Perl array-of-hashes do OTRS antigo).
4. **URL `.opm` que funciona é `https://addons.znuny.com/public/<Pkg>-7.2.1.opm`.**
   O `https://download.znuny.org/releases/itsm/…` do enunciado dá **404** para 7.2 —
   não usar. `Admin::Package::Install <NomeNu>` (nome puro) **falha** ("not found in local
   repository"); instalar por **caminho local do `.opm`** baixado no build (padrão do bake).
5. **Versão real dos pacotes para 7.2.3 é `7.2.1`** (não 7.2.3). É a versão publicada no repo.

---

## 1. Pacotes ITSM — nomes, versões, URLs `.opm` (para bake na imagem, Fase 1)

Instalados ao vivo e confirmados por `Admin::Package::List` (status `installed`):

| Ordem | Pacote | Versão | Depende de | URL `.opm` (HTTP 200) | md5 |
|---|---|---|---|---|---|
| 1 | `GeneralCatalog` | `7.2.1` | — | `https://addons.znuny.com/public/GeneralCatalog-7.2.1.opm` | `47981d708309acd1e6e958de4fc1ac30` |
| 2 | `ITSMCore` | `7.2.1` | GeneralCatalog 7.2.1 | `https://addons.znuny.com/public/ITSMCore-7.2.1.opm` | `c8999c4f20098957c2a48f1ab5f5c683` |
| 3 | `ITSMConfigurationManagement` | `7.2.1` | ITSMCore 7.2.1 | `https://addons.znuny.com/public/ITSMConfigurationManagement-7.2.1.opm` | `1e8c17c72917810d9052535f56cacf45` |

> `ITSMConfigurationManagement-7.2.1.opm` ~5.3 MB. `<PackageRequired>` confirmado lendo o XML
> de cada `.opm`: GeneralCatalog = nenhuma; ITSMCore = GeneralCatalog 7.2.1;
> ITSMConfigurationManagement = ITSMCore 7.2.1.

### Bake/install idempotente (Fase 1) — forma exata verificada

`Admin::Package::Install` resolve por **caminho de arquivo** (ou URL completa), **não** por
nome puro. No build, baixar os 3 `.opm` para `${OTRS_HOME}/var/packages/` e no provisionamento:

```sh
#!/bin/bash
set -e
cd /opt/otrs
# ordem de dependência OBRIGATÓRIA
for spec in \
  "GeneralCatalog:GeneralCatalog-7.2.1.opm" \
  "ITSMCore:ITSMCore-7.2.1.opm" \
  "ITSMConfigurationManagement:ITSMConfigurationManagement-7.2.1.opm"
do
  name="${spec%%:*}"; file="${spec##*:}"
  bin/otrs.Console.pl Admin::Package::List | grep -qi "$name" || \
    bin/otrs.Console.pl Admin::Package::Install "/opt/otrs/var/packages/$file"
done
```

> **Gotcha de instalação (não-fatal):** durante o `Install` do `ITSMConfigurationManagement`
> aparecem 2× `ERROR ... Web service Config Requester should be a non empty hash reference!`
> (`_MigrateWebserviceConfigs`). É o migrador tentando "consertar" webservices existentes
> (nossos `GertiAdmin`/`GertiTicket`, que são só **Provider**, sem Requester). **Não aborta o
> install** ("Done."), os 3 pacotes ficam `installed` e os webservices `GertiAdmin (1)` /
> `GertiTicket (2)` **permanecem intactos** (verificado por `Admin::WebService::List`). Pode
> ignorar; se quiser silenciar, é cosmético.

---

## 2. As 5 classes de Config Item (confirmadas ao vivo)

`select id,name from general_catalog where general_catalog_class='ITSM::ConfigItem::Class'`:

| id | name |
|---|---|
| 22 | Computer |
| 23 | Hardware |
| 24 | Location |
| 25 | Network |
| 26 | Software |

> **Os ids (22–26) são desta instância local** — dependem da ordem de carga do
> general_catalog. **Não hardcodar ids**; resolver por nome via
> `GeneralCatalog->ItemList(Class => 'ITSM::ConfigItem::Class')` (retorna `{ id => name }`).

**Deployment states** (`ITSM::ConfigItem::DeploymentState`): Production=32, Planned=31,
Pilot=30, Maintenance=29, Inactive=28, Expired=27, Repair=33, Retired=34, Review=35, Test/QA=36.
**Incident states** (`ITSM::Core::IncidentState`): Operational=1, Warning=2, Incident=3.
(Ids locais — resolver por nome em runtime.) **Um CI exige DeplStateID + InciStateID na versão**
(ver §5).

---

## 3. Atributo de escopo por tenant: usar o nativo `CustomerID` (tipo `CustomerCompany`)

**As 5 classes já trazem, na definição default, o atributo de empresa-cliente.** Trecho real
da definição (formato **YAML**) — presente idêntico em Computer/Hardware/Location/Network/Software:

```yaml
- Key: CustomerID
  Name: Customer Company
  Searchable: 1
  Input:
    Type: CustomerCompany
```

(Também há `Key: Owner` / `Input: Type: Customer`, referência a customer **user** — não usar
para escopo de empresa; o escopo do tenant é o **`CustomerID`**.)

→ **Decisão congelada:** o escopo por tenant (`tenant.znuny_customer_id`, ex. `AURORA`) grava/lê
o atributo **`CustomerID`** do CI. **Nenhuma alteração de definição é necessária.** O
`ensure-cmdb-customercompany.pl` previsto na Fase 1 pode ser **omitido** (ou virar verificação
no-op que apenas confirma que `CustomerID`/`CustomerCompany` existe em cada classe).

### Se ainda assim for preciso editar a definição de uma classe (mecanismo idempotente)

- **Armazenamento:** tabela `configitem_definition` (`class_id`, `configitem_definition` TEXT
  = YAML, `version`, `create_time`, `create_by`). Cada classe tem 1 linha por versão.
- **API:** `Kernel::System::ITSMConfigItem` (role `…/Definition.pm`):

```perl
# Ler a definição corrente (YAML em ->{Definition}):
my $Def = $ConfigItemObject->DefinitionGet( ClassID => $ClassID );
#   $Def->{DefinitionID}, $Def->{Definition} (string YAML), $Def->{Version}, $Def->{Class}

# Gravar nova definição (YAML como STRING):
my $DefinitionID = $ConfigItemObject->DefinitionAdd(
    ClassID    => $ClassID,
    Definition => $YamlString,   # YAML completo da classe
    UserID     => 1,
);
```

> **Idempotência (importante):** `DefinitionAdd` **recusa e retorna `undef`** se a definição
> for **idêntica** à última (`Log error: "Can't add new definition! The definition was not
> changed."`). Portanto o ensure-script deve: `DefinitionGet` → comparar/parsear → só chamar
> `DefinitionAdd` se o atributo desejado **faltar**. Reexecutar sem mudança é seguro (no-op),
> mas trata o `undef` como "já ok", não como erro.

---

## 4. API nativa que as ops GI vão embrulhar (assinaturas congeladas)

Inspecionado em `/opt/otrs/Kernel/System/ITSMConfigItem.pm` e roles
(`ITSMConfigItem/Version.pm`, `/Definition.pm`, `/XML.pm`) + `LinkObject.pm`. Objeto:
`$Kernel::OM->Get('Kernel::System::ITSMConfigItem')`.

### 4.1 Buscar CIs por valor de atributo (`CustomerID`) — **`ConfigItemSearchExtended` + `What`**

A busca por atributo do CI é XML-search via param **`What`** (array de condições AND; cada
hash interno é OR). O caminho da chave espelha a estrutura XML armazenada; **`[%]` casa
qualquer índice** de array. **Verificado ao vivo** (retornou o CI de teste):

```perl
my $ConfigItemIDs = $ConfigItemObject->ConfigItemSearchExtended(
    ClassIDs => [ $ClassID ],          # ARRAYREF de class ids (resolver por nome); omitir = todas
    What     => [
        {
            # chave = path XML do atributo; valor = conteúdo (LIKE; '*' vira '%')
            "[%]{'Version'}[%]{'CustomerID'}[%]{'Content'}" => 'AURORA',
        },
    ],
    # DeplStateIDs => [...], InciStateIDs => [...],  # (opcionais) filtros extra
    # Name => '...', Number => '...',                # (opcionais)
    # OrderBy => ['Number'], OrderByDirection => ['Up'], Limit => 100,  # (opcionais)
);
# → arrayref de ConfigItemIDs (ou [] / undef)
```

**Detalhes congelados (verificados):**
- A chave usa **nomes de elemento entre aspas simples**: `{'Version'}`, `{'CustomerID'}`,
  `{'Content'}`. Os índices podem ser `[%]` (qualquer) — forma robusta — ou literais `[1]`.
- O valor é **LIKE** internamente; `*` é convertido em `%` (`_PrepareLikeString`). Para casar
  exato, passe o valor cru (`'AURORA'`); para substring use `'*AURORA*'`. Para
  igualdade/numérico há a forma hashref `{ '=' => $v }` / `{ '-between' => [$a,$b] }`.
- `ConfigItemSearch` (sem "Extended") **não** filtra por atributo XML — só por Number/ClassIDs/
  DeplStateIDs/InciStateIDs/datas. **Use sempre `ConfigItemSearchExtended` quando filtrar por
  `CustomerID`.**
- Internamente: `ConfigItemSearchExtended` → `_XMLVersionSearch` → `_XMLHashSearch`
  (`xml_storage`, `xml_type = "ITSM::ConfigItem::<ClassID>"`, LIKE em `xml_content_key`/`_value`).

### 4.2 Obter um CI + versão/atributos — **`ConfigItemGet` + `VersionGet`**

```perl
# Cabeçalho do CI (sem atributos XML):
my $CI = $ConfigItemObject->ConfigItemGet(
    ConfigItemID => 123,
    Cache        => 0,          # (opcional) default 1
);
#   ->{ConfigItemID} ->{Number} ->{ClassID} ->{Class} ->{LastVersionID}
#   ->{CurDeplStateID} ->{CurDeplState} ->{CurDeplStateType}
#   ->{CurInciStateID} ->{CurInciState} ->{CurInciStateType}
#   ->{CreateTime} ->{CreateBy} ->{ChangeTime} ->{ChangeBy}

# Versão corrente + ATRIBUTOS (XMLData):
my $V = $ConfigItemObject->VersionGet(
    ConfigItemID => 123,        # (ou VersionID => ...)
    XMLDataGet   => 1,          # (opcional) default 1 — precisa de 1 p/ ler atributos
);
#   ->{Name} ->{DefinitionID} ->{DeplState} ->{InciState}
#   ->{XMLData}  # arrayref aninhado; ler atributo:
my $CustomerID   = $V->{XMLData}->[1]{Version}[1]{CustomerID}[1]{Content};   # 'AURORA'
my $SerialNumber = $V->{XMLData}->[1]{Version}[1]{SerialNumber}[1]{Content}; # 'SN-R1K-9'
```

> **Guarda anti-IDOR (ConfigItemGet.pm da Fase 1):** depois do `ConfigItemGet`+`VersionGet`,
> comparar `XMLData->[1]{Version}[1]{CustomerID}[1]{Content}` com o `CustomerCompany` do
> requisitante; se diferente → **NotFound** (não vazar CI de outro tenant).

### 4.3 Listar classes — **`GeneralCatalog->ItemList`**

```perl
my $ClassRef = $Kernel::OM->Get('Kernel::System::GeneralCatalog')->ItemList(
    Class => 'ITSM::ConfigItem::Class',
);   # → { 22 => 'Computer', 23 => 'Hardware', 24 => 'Location', 25 => 'Network', 26 => 'Software' }
```

(Mesmo padrão para `ITSM::ConfigItem::DeploymentState` e `ITSM::Core::IncidentState`.)

### 4.4 Linkar Ticket ↔ ConfigItem — **`LinkObject->LinkAdd`**

Objeto de link do CI confirmado = **`ITSMConfigItem`** (`/opt/otrs/Kernel/System/LinkObject/ITSMConfigItem.pm`).
Verificado ao vivo (`LinkAdd` → `OK`; `LinkList` devolveu `RelevantTo => Source => {1=>1}`;
`link_relation`: src Ticket key 1 → tgt ITSMConfigItem key 1, type_id 4 = RelevantTo, state 1 = Valid):

```perl
my $Ok = $Kernel::OM->Get('Kernel::System::LinkObject')->LinkAdd(
    SourceObject => 'Ticket',
    SourceKey    => $TicketID,         # string/int
    TargetObject => 'ITSMConfigItem',  # <-- nome do objeto de link do CI
    TargetKey    => $ConfigItemID,
    Type         => 'RelevantTo',      # ver tipos válidos abaixo
    State        => 'Valid',
    UserID       => 1,
);   # → 1 em sucesso

# Ler links de um ticket:
my $Links = $Kernel::OM->Get('Kernel::System::LinkObject')->LinkList(
    Object => 'Ticket', Key => $TicketID, State => 'Valid', UserID => 1,
);   # → $Links->{ITSMConfigItem}{RelevantTo}{Source}{$ConfigItemID} = 1
```

**Tipos de link Ticket↔ITSMConfigItem disponíveis** (do `LinkObject::PossibleLink`):
`AlternativeTo`, `DependsOn`, **`RelevantTo`** (recomendado — usado e validado). Os 3
existem como pares `ITSMConfigItem <-> Ticket`. (Obs.: a tabela `link_type` lista
`Normal/ParentChild/DependsOn` mas o pacote registra `RelevantTo`/`AlternativeTo` via
`PossibleType`; o `LinkAdd RelevantTo` **funcionou**.)

---

## 5. Criar CI por API (e2e congelado) — **`ConfigItemAdd` + `VersionAdd`**

Usado para o CI throwaway de prova (e referência p/ o e2e da Fase 4). Verificado ao vivo:

```perl
my $CIObj = $Kernel::OM->Get('Kernel::System::ITSMConfigItem');

# 1) cria o "casco" do CI na classe:
my $ConfigItemID = $CIObj->ConfigItemAdd(
    ClassID => $ClassID,    # ex.: 22 (Computer) — resolver por nome
    UserID  => 1,
);

# 2) primeira versão com estado de deploy/incidente + atributos (XMLData):
my $Def = $CIObj->DefinitionGet( ClassID => $ClassID );
my $VersionID = $CIObj->VersionAdd(
    ConfigItemID => $ConfigItemID,
    Name         => 'PC-001',
    DefinitionID => $Def->{DefinitionID},
    DeplStateID  => 32,     # Production (resolver por nome)
    InciStateID  => 1,      # Operational (resolver por nome)
    UserID       => 1,
    XMLData      => [
        undef,
        { Version => [
            undef,
            {
                CustomerID   => [ undef, { Content => 'AURORA' } ],   # <-- escopo do tenant
                SerialNumber => [ undef, { Content => 'SN-R1K-9' } ],
            },
        ] },
    ],
);
```

> **Gotcha — um CI só "existe" para a busca depois de ter uma versão** com `DeplStateID` +
> `InciStateID`. `ConfigItemAdd` sozinho não basta; o `VersionAdd` é que grava o `xml_storage`
> e os estados. A estrutura `XMLData` é o array aninhado `[undef, { Version => [undef, { <Key> =>
> [undef, {Content=>...}] }] }]` (índice 0 = undef/TagKey, dados no índice 1).

---

## 6. Gotchas / notas para as Fases 1+

1. **`download.znuny.org/releases/itsm/` → 404 p/ 7.2.** Fonte correta dos `.opm`:
   **`https://addons.znuny.com/public/<Pkg>-7.2.1.opm`** (repo "Znuny Open Source Add-ons").
2. **`Admin::Package::Install <NomePuro>` falha** ("not found in local repository or invalid
   package version"). Instalar por **caminho do `.opm`** (ou URL completa). Bake → install por path.
3. **ImportExport não entra** (sem dependência; sem URL no repo). 3 pacotes só.
4. **Não ADICIONAR atributo** — usar o **`CustomerID`** nativo (`Type: CustomerCompany`). O
   ensure-script de definição vira opcional/no-op.
5. **Definição = YAML string** em `configitem_definition`; `DefinitionAdd` é no-op (retorna
   `undef`) se nada mudou — tratar como sucesso idempotente.
6. **Busca por atributo só via `ConfigItemSearchExtended` + `What`** com chave
   `"[%]{'Version'}[%]{'CustomerID'}[%]{'Content'}"`; valor é LIKE (`*`→`%`).
7. **Ruído YAML "during global destruction" em scripts CLI one-off:** ao destruir o objeto
   Ticket no fim de um script `perl -e`, o handler `Ticket::Event::GenericAgent` carrega
   DynamicFields e o `YAML::XS::Load` fica indisponível na ordem de teardown do Perl, cuspindo
   muitos `ERROR ... Undefined subroutine &YAML::XS::Load ... during global destruction`. **Não
   afeta a operação** (o `LinkAdd`/leitura ocorreram antes e tiveram sucesso) e **não acontece
   sob mod_perl/daemon** (onde rodam as ops GI). É artefato do harness CLI — ignorar nos spikes/
   e2e por console; se incomodar, isolar a operação num bloco e chamar `exit 0` antes do
   teardown implícito.
8. **Ids do general_catalog (classes/estados) são por-instância** — resolver por **nome** em
   runtime (`GeneralCatalog->ItemList`), nunca hardcodar.
9. **Webservices `GertiAdmin (1)` / `GertiTicket (2)` sobreviveram** ao install do ITSM
   (o erro do migrador é cosmético). Reconfirmar no deploy de prod (guard `Admin::WebService::List`).

---

## 7. Estado deixado na instância local (throwaway do spike)

- **CI #1** (Number `1022000001`), classe **Computer**, `CustomerID=AURORA`,
  `SerialNumber=SN-R1K-9`, DeplState Production / InciState Operational, versão `R1K-THROWAWAY-PC`.
- **Link** Ticket #1 ↔ CI #1 (`RelevantTo`, Valid) em `link_relation`.
- Os 3 pacotes ITSM ficam **instalados** (esperado — viram baseline; a Fase 1 os bakeia).

Para limpar o CI throwaway (opcional; a Fase 4 recria limpo):
```perl
$Kernel::OM->Get('Kernel::System::LinkObject')->LinkDelete(
    Object1=>'Ticket', Key1=>1, Object2=>'ITSMConfigItem', Key2=>1, Type=>'RelevantTo', UserID=>1);
$Kernel::OM->Get('Kernel::System::ITSMConfigItem')->ConfigItemDelete(ConfigItemID=>1, UserID=>1);
```
