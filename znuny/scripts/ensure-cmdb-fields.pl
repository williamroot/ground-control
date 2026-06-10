# znuny/scripts/ensure-cmdb-fields.pl
# Garante (idempotente) os campos PT-BR `Disco`/`Memoria` (#1L, R1L) E o campo
# `Fingerprint` (#1R-a) na definição da classe ITSM Computer. O Fingerprint é a
# chave estável usada pelo agente de inventário para dedupe (re-enroll = atualiza).
#
# Mecânica (congelada no spike R1L — docs/.../2026-06-09-r1l-itsm-class-definition.md):
#  - ClassID resolvido por NOME ('Computer') via GeneralCatalog (id é por-instância).
#  - Formato da definição = YAML (lista top-level de `- Key: ...`).
#  - OperatingSystem e CPU JÁ existem na default → só adicionamos Disco/Memoria.
#  - Idempotência por DETECÇÃO na definição VIVA (regex), NÃO por retorno do add:
#    DefinitionAdd com YAML idêntico loga ERROR e retorna undef — então só chamamos
#    quando algum campo falta. Cada campo é checado independentemente.
#  - String-append à definição viva (NÃO reescrever a partir de um snippet hardcoded;
#    a default pode variar entre versões de pacote).
# Roda como otrs no deploy (idêntico ao ensure-gerti-dynamicfield.pl). Safe re-run.
use strict;
use warnings;
use lib '/opt/otrs';
use lib '/opt/otrs/Kernel/cpan-lib';
use lib '/opt/otrs/Custom';
use Kernel::System::ObjectManager;

local $Kernel::OM = Kernel::System::ObjectManager->new();

# ── Resolver o ClassID da Computer por NOME (nunca hardcodar — é por-instância).
my $GeneralCatalog = $Kernel::OM->Get('Kernel::System::GeneralCatalog');
my $ClassList = $GeneralCatalog->ItemList( Class => 'ITSM::ConfigItem::Class' );
die "FATAL: GeneralCatalog->ItemList retornou vazio (ITSM instalado?)\n"
    if !$ClassList || !%{$ClassList};

my ($cid) = grep { $ClassList->{$_} eq 'Computer' } keys %{$ClassList};
die "FATAL: classe 'Computer' não encontrada no GeneralCatalog\n" if !$cid;

# ── Pegar a definição VIVA da classe.
my $CI  = $Kernel::OM->Get('Kernel::System::ITSMConfigItem');
my $D   = $CI->DefinitionGet( ClassID => $cid );
die "FATAL: DefinitionGet não retornou definição para ClassID $cid\n"
    if !$D || !$D->{Definition};
my $Def = $D->{Definition};

# ── Detecção idempotente (cada campo checado independentemente).
#    O bloco do campo abre com `- Key: <Nome>` em item de lista top-level.
my $has_memoria     = $Def =~ /^- Key:\s*Memoria\b/m     ? 1 : 0;
my $has_disco       = $Def =~ /^- Key:\s*Disco\b/m       ? 1 : 0;
my $has_fingerprint = $Def =~ /^- Key:\s*Fingerprint\b/m ? 1 : 0;

if ( $has_memoria && $has_disco && $has_fingerprint ) {
    print "skip (já tem Disco/Memoria/Fingerprint) — DefinitionID atual: $D->{DefinitionID}\n";
    exit 0;
}

# ── Blocos a acrescentar (só os que faltam). Indentação de 2 espaços, espelhando
#    a default. Cada bloco começa com uma linha em branco para separar do anterior.
my $MemoriaBlock = <<'YAMLBLOCK';

- Key: Memoria
  Name: Memória
  Input:
    Type: Text
    Size: 50
    MaxLength: 100
YAMLBLOCK

my $DiscoBlock = <<'YAMLBLOCK';

- Key: Disco
  Name: Disco
  Input:
    Type: Text
    Size: 50
    MaxLength: 100
YAMLBLOCK

# Fingerprint (#1R-a): chave estável de hardware do agente de inventário. Text;
# usada server-side pelo dedupe — não precisa ser obrigatória na UI nativa.
my $FingerprintBlock = <<'YAMLBLOCK';

- Key: Fingerprint
  Name: Fingerprint
  Input:
    Type: Text
    Size: 50
    MaxLength: 200
YAMLBLOCK

my $NewDef = $Def;
$NewDef .= $MemoriaBlock     if !$has_memoria;
$NewDef .= $DiscoBlock       if !$has_disco;
$NewDef .= $FingerprintBlock if !$has_fingerprint;

# ── Gravar a nova definição (versionada). Em sucesso retorna o novo DefinitionID.
my $DefID = $CI->DefinitionAdd(
    ClassID    => $cid,
    Definition => $NewDef,
    UserID     => 1,
);

if ( !$DefID ) {
    # undef SEM motivo aparente: a única causa benigna conhecida é "definição não
    # mudou" (mas a detecção acima já teria dado skip). Trate como erro real.
    die "FATAL: DefinitionAdd retornou undef para ClassID $cid (definição não gravada)\n";
}

my @added;
push @added, 'Memoria'     if !$has_memoria;
push @added, 'Disco'       if !$has_disco;
push @added, 'Fingerprint' if !$has_fingerprint;
print "added (" . join( '+', @added ) . ") — nova DefinitionID: $DefID\n";
exit 0;
