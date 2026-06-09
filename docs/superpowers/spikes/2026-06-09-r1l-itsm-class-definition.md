# R1L — Spike: congelar a definição da classe ITSM Computer + campos Disco/Memória/CPU

> **Spec #1L · Fase 2 · Task 4 (SPIKE, bloqueante).** Rodado contra o `znuny-web`
> **vivo** (stack local, Znuny **7.2.3**, ITSM add-ons 7.2.1 instalados, branch
> `feature/spec-1l-video-cmdb`). Tudo abaixo foi verificado ao vivo: definição
> dumpada, `DefinitionAdd` executado (criou versão nova), idempotência confirmada
> (2ª run = skip), `ConfigItemGet` header inspecionado, `VersionAdd` com os novos
> campos e `VersionGet(XMLDataGet=>1)` lendo os atributos. As Tasks 5/6/7/8/9
> implementam contra este doc; onde divergir do plano, vale a **realidade** aqui.

---

## 0. TL;DR / o que muda no plano (LEIA)

1. **Formato = YAML** (array de hashes top-level, doc separado por `---`). Confirmado.
   NÃO é o Perl array-of-hashes do OTRS antigo.
2. **`CLASSID` da Computer = `22` nesta instância** — **resolver por nome em runtime**
   (`GeneralCatalog->ItemList(Class => 'ITSM::ConfigItem::Class')`), NUNCA hardcodar (id é
   por-instância).
3. **A definição default da Computer JÁ tem `OperatingSystem` E `CPU`.** O `CPU` nativo é
   **multi-valor** (`CountMax: 16`), não um Text simples. O plano pede `Disco`/`Memoria`/`CPU`
   simples; como `CPU` já existe e satisfaz o requisito (campo `CPU` legível em
   `XMLData->[1]{Version}[1]{CPU}[1]{Content}`), **só adicionamos `Memoria` e `Disco`**.
   Reaproveitar o `CPU` existente evita colidir/duplicar a chave (a definição não pode ter 2
   `Key: CPU`). **Não há `Disco` nem `Memoria` na default** → esses 2 são os que adicionamos.
   - Existe também `Ram` (`CountMax: 10`) e `HardDisk` (com `Sub: Capacity`) na default, mas
     são chaves diferentes de `Memoria`/`Disco` e não os reusamos (nomes PT-BR pedidos pela spec).
4. **`DefinitionAdd` é versionado e idempotente-por-detecção, NÃO por retorno.** Re-adicionar a
   definição **idêntica** loga `ERROR ... Can't add new definition! The definition was not
   changed.` e retorna `undef`. → O ensure-script deve **detectar por regex/parse ANTES** de
   chamar `DefinitionAdd` (não depender do undef, que polui o log com ERROR). Verificado ao vivo.
5. **Data de criação no header do `ConfigItemGet` = `CreateTime`** (string `YYYY-MM-DD HH:MM:SS`).
   Confirmado (Task 6 usa `Created => $ConfigItem->{CreateTime}`).

---

## 1. CLASSID + DefinitionID (vivo)

```
CLASSID       = 22         (Computer; resolver por NOME, não hardcodar)
DEFINITION_ID = 1          (era 1 antes do spike; virou 6 após o DefinitionAdd dos 2 campos)
```

`GeneralCatalog->ItemList(Class => 'ITSM::ConfigItem::Class')` →
`{ 22 => 'Computer', 23 => 'Hardware', 24 => 'Location', 25 => 'Network', 26 => 'Software' }`.

---

## 2. Definição YAML atual da classe Computer (verbatim, formato congelado)

Formato: `---` no topo, depois uma **lista YAML** (`- Key: ...`) de campos. Cada campo:
`Key`, `Name`, opcional `Searchable: 1`, e `Input:` (com `Type` + opcionais `Size`,
`MaxLength`, `Class`, `Translation`, `Required`). Campos multi-valor usam `CountMin`/`CountMax`/
`CountDefault`; campos compostos usam `Sub:` (lista aninhada). Indentação = **2 espaços**.

```yaml
---
- Key: Vendor
  Name: Vendor
  Searchable: 1
  Input:
    Type: Text
    Size: 50
    MaxLength: 50
    # Example for CI attribute syntax check for text and textarea fields
    #RegEx: ^ABC.*
    #RegExErrorMessage: Value must start with ABC!

- Key: Model
  Name: Model
  Searchable: 1
  Input:
    Type: Text
    Size: 50
    MaxLength: 50

- Key: Description
  Name: Description
  Searchable: 1
  Input:
    Type: TextArea

- Key: Type
  Name: Type
  Searchable: 1
  Input:
    Type: GeneralCatalog
    Class: ITSM::ConfigItem::Computer::Type
    Translation: 1

- Key: CustomerID
  Name: Customer Company
  Searchable: 1
  Input:
    Type: CustomerCompany

- Key: Owner
  Name: Owner
  Searchable: 1
  Input:
    Type: Customer

- Key: SerialNumber
  Name: Serial Number
  Searchable: 1
  Input:
    Type: Text
    Size: 50
    MaxLength: 100

- Key: OperatingSystem
  Name: Operating System
  Input:
    Type: Text
    Size: 50
    MaxLength: 100

- Key: CPU
  Name: CPU
  Input:
    Type: Text
    Size: 50
    MaxLength: 100
  CountMax: 16

- Key: Ram
  Name: Ram
  Input:
    Type: Text
    Size: 50
    MaxLength: 100
  CountMax: 10

- Key: HardDisk
  Name: Hard Disk
  Input:
    Type: Text
    Size: 50
    MaxLength: 100
  CountMax: 10
  Sub:
  - Key: Capacity
    Name: Capacity
    Input:
      Type: Text
      Size: 20
      MaxLength: 10

- Key: FQDN
  Name: FQDN
  Searchable: 1
  Input:
    Type: Text
    Size: 50
    MaxLength: 100

- Key: NIC
  Name: Network Adapter
  Input:
    Type: Text
    Size: 50
    MaxLength: 100
    Required: 1
  CountMin: 0
  CountMax: 10
  CountDefault: 1
  Sub:
  - Key: IPoverDHCP
    Name: IP over DHCP
    Input:
      Type: GeneralCatalog
      Class: ITSM::ConfigItem::YesNo
      Translation: 1
      Required: 1
  - Key: IPAddress
    Name: IP Address
    Searchable: 1
    Input:
      Type: Text
      Size: 40
      MaxLength: 40
      Required: 1
    CountMin: 0
    CountMax: 20
    CountDefault: 0

- Key: GraphicAdapter
  Name: Graphic Adapter
  Input:
    Type: Text
    Size: 50
    MaxLength: 100

- Key: OtherEquipment
  Name: Other Equipment
  Input:
    Type: TextArea
    Required: 1
  CountMin: 0
  CountDefault: 0

- Key: WarrantyExpirationDate
  Name: Warranty Expiration Date
  Searchable: 1
  Input:
    Type: Date
    YearPeriodPast: 20
    YearPeriodFuture: 10

- Key: InstallDate
  Name: Install Date
  Searchable: 1
  Input:
    Type: Date
    Required: 1
    YearPeriodPast: 20
    YearPeriodFuture: 10
  CountMin: 0
  CountDefault: 0

- Key: Note
  Name: Note
  Searchable: 1
  Input:
    Type: TextArea
    Required: 1
  CountMin: 0
  CountDefault: 0
```

> **Importante para o `ensure-cmdb-fields.pl` (Task 5):** NÃO reescrever a definição inteira
> a partir deste snippet hardcoded. Faça **`DefinitionGet` da definição VIVA** e **acrescente**
> os 2 campos ao final da string (string-append), preservando o que estiver lá (a default pode
> variar entre versões de pacote). O snippet acima é referência de formato, não fonte de verdade.

---

## 3. Snippet EXATO a ADICIONAR (copy-paste ready) — só `Memoria` + `Disco`

Anexar ao **final** da string YAML da definição viva (mesmo formato/indentação de 2 espaços; cada
campo separado por uma linha em branco). `CPU` NÃO é adicionado (já existe na default — ver §0.3):

```yaml

- Key: Memoria
  Name: Memória
  Input:
    Type: Text
    Size: 50
    MaxLength: 100

- Key: Disco
  Name: Disco
  Input:
    Type: Text
    Size: 50
    MaxLength: 100
```

- `Searchable` omitido de propósito (não precisamos buscar por esses; a busca de escopo é por
  `CustomerID`). Adicionar `Searchable: 1` é inócuo se quiserem.
- `Name: Memória` com acento — o YAML é UTF-8; gravou e leu OK ao vivo.
- Estrutura de campo simples confirmada válida: `Input: { Type: Text, Size: 50, MaxLength: 100 }`
  (a forma em bloco acima e a forma inline são equivalentes em YAML; usamos a forma em bloco para
  espelhar a default).

---

## 4. Mecanismo idempotente do `DefinitionAdd` (congelado)

```perl
my $GC  = $Kernel::OM->Get('Kernel::System::GeneralCatalog');
my $L   = $GC->ItemList(Class => 'ITSM::ConfigItem::Class');
my ($cid) = grep { $L->{$_} eq 'Computer' } keys %$L;   # resolver por NOME
my $CI  = $Kernel::OM->Get('Kernel::System::ITSMConfigItem');
my $D   = $CI->DefinitionGet(ClassID => $cid);          # ->{Definition} (YAML str), ->{DefinitionID}
my $yaml = $D->{Definition};

# DETECÇÃO ANTES de gravar (idempotência correta — não depender do retorno):
my $has_disco   = $yaml =~ /^- Key:\s*Disco\s*$/m   ? 1 : 0;
my $has_memoria = $yaml =~ /^- Key:\s*Memoria\s*$/m ? 1 : 0;
if ($has_disco && $has_memoria) { print "skip\n"; exit 0; }   # já presentes → no-op limpo

my $new = $yaml . <<'YAMLBLOCK';

- Key: Memoria
  Name: Memória
  Input:
    Type: Text
    Size: 50
    MaxLength: 100

- Key: Disco
  Name: Disco
  Input:
    Type: Text
    Size: 50
    MaxLength: 100
YAMLBLOCK

my $newid = $CI->DefinitionAdd( ClassID => $cid, Definition => $new, UserID => 1 );
#   → retorna o novo DefinitionID (ex.: 6) em sucesso.
```

**Comportamento verificado ao vivo:**

| Cenário | Resultado |
|---|---|
| 1ª run (faltavam Disco/Memoria) | `DefinitionAdd` → novo `DefinitionID=6`; DefID 1→6. Disco/Memoria/CPU presentes. |
| 2ª run (já presentes) | regex detecta → **`skip`**, NÃO chama `DefinitionAdd`. Idempotente. |
| `DefinitionAdd` com YAML **idêntico** ao atual | loga `ERROR ... Can't add new definition! The definition was not changed.` e retorna **`undef`**; DefID inalterado. |

> **Gotcha (congelado):** confiar no `undef` do `DefinitionAdd` como "já ok" **funciona mas
> polui o log com um ERROR** a cada provisionamento. A forma limpa e idempotente é **detectar
> por regex/parse antes** (acima) e só gravar se faltar. Trate um `undef` eventual como
> "já igual" (não-erro), mas o caminho normal nem chega lá.
>
> `DefinitionAdd` é **versionado**: cada gravação cria uma nova linha em
> `configitem_definition` (nova `DefinitionID`). Versões antigas de CI continuam apontando
> para a DefinitionID antiga; novas `VersionAdd` devem usar a `DefinitionID` corrente
> (`DefinitionGet` após o add). NÃO é destrutivo.

---

## 5. Data de criação no header do `ConfigItemGet` (congelado)

`ConfigItemGet(ConfigItemID => N)` (sem `VersionGet`) retorna o header. Chaves vivas (CI #1):

```
ConfigItemID = 1
Number       = 1022000001
Class        = Computer            ClassID = 22
CurDeplState = Production          CurDeplStateID = 32   CurDeplStateType = productive
CurInciState = Operational         CurInciStateID = 1    CurInciStateType = operational
LastVersionID = 1
CreateTime   = 2026-06-09 17:42:36    CreateBy = 1     <-- DATA DE CRIAÇÃO
ChangeTime   = 2026-06-09 17:42:36    ChangeBy = 1
```

→ **Campo de data de criação = `CreateTime`** (string `YYYY-MM-DD HH:MM:SS`, sem timezone
explícito — é o horário do sistema Znuny). Task 6: `Created => $ConfigItem->{CreateTime}`.

---

## 6. Caminho XMLData para ler os novos atributos (congelado)

Após `DefinitionAdd` (campos na definição) + `VersionAdd` setando os valores, todos são lidos
por `VersionGet(ConfigItemID => N, XMLDataGet => 1)` no caminho **idêntico** ao do `SerialNumber`
(R1K): `$V->{XMLData}->[1]{Version}[1]{<Key>}[1]{Content}`. Verificado ao vivo (CI #1, versão 2):

```perl
my $V = $CI->VersionGet(ConfigItemID => 1, XMLDataGet => 1);
my $node = $V->{XMLData}->[1]{Version}[1];
$node->{OperatingSystem}[1]{Content};   # 'Ubuntu 22.04'
$node->{CPU}[1]{Content};               # 'Intel i5-1135G7'
$node->{Memoria}[1]{Content};           # '16 GB'
$node->{Disco}[1]{Content};             # '512 GB SSD'
$node->{CustomerID}[1]{Content};        # 'AURORA'
$node->{SerialNumber}[1]{Content};      # 'SN-R1K-9'
```

→ **O loop genérico da Task 6** (`for my $Key (sort keys %{$VerNode})` lendo
`$VerNode->{$Key}[1]{Content}`) captura `OperatingSystem`/`CPU`/`Memoria`/`Disco`
automaticamente, pulando `CustomerID` (que já vai no topo). Confirmado que os 4 ficam em
`%{$VerNode}` com `[1]{Content}` definido.

> **Nota sobre `CPU` multi-valor:** como `CPU` tem `CountMax: 16`, em teoria pode ter mais de um
> índice (`[1]`, `[2]`, ...). Ao setar um único valor (`CPU => [undef, {Content=>'...'}]`) o
> conteúdo fica em `[1]{Content}` e o loop genérico `[1]{Content}` o lê normalmente — basta um
> valor para a ficha do portal. Se houver múltiplos CPUs, o loop pega só o `[1]` (suficiente p/
> exibição read-only; a spec #1L não pede multi-valor).

---

## 7. Estado deixado na instância local (após o spike)

- **Definição da Computer:** `DefinitionID` avançou de `1` → `6` (acrescentou `Memoria` + `Disco`;
  `CPU`/`OperatingSystem` já existiam). É baseline esperado; a Task 5 (`ensure-cmdb-fields.pl`)
  reexecuta idempotente (detecta presentes → skip).
- **CI #1** (Number `1022000001`, classe Computer, `CustomerID=AURORA`): ganhou a **versão 2**
  (`R1L-PC`) com `OperatingSystem=Ubuntu 22.04`, `CPU=Intel i5-1135G7`, `Memoria=16 GB`,
  `Disco=512 GB SSD`, `SerialNumber=SN-R1K-9`. É throwaway do R1K; o seed da Task 9 popula os
  ativos reais (AUR-NB-001/AUR-PC-014) idempotentemente.

Nada destrutivo; reexecução é segura.

---

## 8. Resumo para Tasks 5/6/7/8/9

| Task | Fato congelado |
|---|---|
| 5 `ensure-cmdb-fields.pl` | Resolver ClassID por nome; `DefinitionGet`; regex `^- Key:\s*(Disco\|Memoria)\s*$` p/ detectar; se faltar, **string-append** do §3 à definição viva + `DefinitionAdd`. Idempotente. CPU não é adicionado (já existe). |
| 6 `ConfigItemGet.pm` | Data: `Created => $ConfigItem->{CreateTime}`. Loop genérico sobre `$V->{XMLData}->[1]{Version}[1]` lendo `[1]{Content}`, pulando `CustomerID`. |
| 7 sidecar | `AssetDetail.created` = string `YYYY-MM-DD HH:MM:SS`; `attributes` traz `OperatingSystem`/`CPU`/`Memoria`/`Disco`/etc. |
| 8 portal | Mapa de rótulos PT-BR; renderizar todos os `attributes` + `fmtDate(created)`. |
| 9 seed | `VersionAdd` com `OperatingSystem`/`CPU`/`Memoria`/`Disco` no `XMLData` (formato `<Key> => [undef, {Content=>...}]`). |
