#!/usr/bin/perl
# ─────────────────────────────────────────────────────────────────────────────
#  seed-cmdb.pl — Semeia Config Items (CMDB / ITSM) demo da Aurora Móveis.
#  (Spec #1K Fase 4 — inventário real p/ o portal do cliente em /ativos.)
#
#  IDEMPOTENTE: cada ativo é procurado por Name (escopado em CustomerID=AURORA)
#  via ConfigItemSearchExtended; se já existe, PULA. Reexecutar é seguro.
#
#  Executado DENTRO do container znuny-web, como usuário 'otrs':
#    docker compose exec -T znuny-web su -s /bin/bash otrs \
#      -c "perl /opt/otrs/var/seed-cmdb.pl"
#
#  API nativa (congelada no spike R1K):
#    - GeneralCatalog->ItemList  → resolve ClassID/DeplStateID/InciStateID p/ NOME
#    - ConfigItemSearchExtended + What (path XML do CustomerID) → idempotência
#    - ConfigItemAdd (casco) + VersionAdd (1ª versão c/ DeplState/InciState/XMLData)
#
#  Escopo por tenant = atributo NATIVO CustomerID (Type CustomerCompany) = AURORA.
#  Só usa atributos que EXISTEM na definição de cada classe (Text/TextArea);
#  evita campos GeneralCatalog (Type/LicenceType) que exigem id de catálogo.
# ─────────────────────────────────────────────────────────────────────────────
use strict;
use warnings;
use utf8;
use lib '/opt/otrs';
use lib '/opt/otrs/Kernel/cpan-lib';
use lib '/opt/otrs/Custom';

binmode STDOUT, ':encoding(UTF-8)';
binmode STDERR, ':encoding(UTF-8)';

use Kernel::System::ObjectManager;

local $Kernel::OM = Kernel::System::ObjectManager->new(
    'Kernel::System::Log' => { LogPrefix => 'seed-cmdb' },
);

my $CIObj  = $Kernel::OM->Get('Kernel::System::ITSMConfigItem');
my $GCObj  = $Kernel::OM->Get('Kernel::System::GeneralCatalog');
my $ROOT   = 1;
my $TENANT = 'AURORA';

print "\n=== SEED CMDB — Config Items demo (Aurora Móveis · CustomerID=$TENANT) ===\n\n";

# ── resolve ids por NOME (ids do general_catalog são por-instância) ──────────
my %CLASS = reverse %{ $GCObj->ItemList( Class => 'ITSM::ConfigItem::Class' ) || {} };
my %DEPL  = reverse %{ $GCObj->ItemList( Class => 'ITSM::ConfigItem::DeploymentState' ) || {} };
my %INCI  = reverse %{ $GCObj->ItemList( Class => 'ITSM::Core::IncidentState' ) || {} };

my $DEPL_PROD = $DEPL{Production}  or die "DeploymentState 'Production' não encontrado\n";
my $INCI_OP   = $INCI{Operational} or die "IncidentState 'Operational' não encontrado\n";

for my $c (qw(Computer Network Software Hardware)) {
    die "Classe '$c' não encontrada (CMDB instalado?)\n" unless $CLASS{$c};
}

# cache da DefinitionID corrente por classe
my %DEF;
sub def_id {
    my ($class) = @_;
    return $DEF{$class} //= do {
        my $d = $CIObj->DefinitionGet( ClassID => $CLASS{$class} );
        die "DefinitionGet falhou p/ classe $class\n" unless $d && $d->{DefinitionID};
        $d->{DefinitionID};
    };
}

# ── catálogo de ativos demo da Aurora ────────────────────────────────────────
# attrs: SÓ chaves Text/TextArea que existem na definição de cada classe.
my @ASSETS = (
    {   class => 'Computer', name => 'AUR-NB-001',
        attrs => {
            Vendor          => 'Dell',
            Model           => 'Latitude 5440',
            SerialNumber    => 'AUR-NB-001-SN7H2K',
            OperatingSystem => 'Windows 11 Pro',
            CPU             => 'Intel i5-1135G7',
            Memoria         => '16 GB',
            Disco           => '512 GB SSD',
            Description     => 'Notebook da gerência de produção (Eduardo Salvi).',
        },
    },
    {   class => 'Computer', name => 'AUR-PC-014',
        attrs => {
            Vendor          => 'Lenovo',
            Model           => 'ThinkCentre M70q',
            SerialNumber    => 'AUR-PC-014-SN9X4B',
            OperatingSystem => 'Ubuntu 22.04 LTS',
            CPU             => 'AMD Ryzen 5',
            Memoria         => '32 GB',
            Disco           => '1 TB SSD',
            Description     => 'Desktop do setor financeiro (estação 14).',
        },
    },
    {   class => 'Network', name => 'AUR-FW-01',
        attrs => {
            NetworkAddress => '192.168.10.1/24',
            Description    => 'Firewall/roteador de borda (matriz Bento Gonçalves/RS).',
        },
    },
    {   class => 'Software', name => 'M365 Business',
        attrs => {
            Vendor       => 'Microsoft',
            Version      => 'Business Standard',
            SerialNumber => 'AUR-M365-12LIC',
            Description  => 'Microsoft 365 Business Standard — 12 licenças (Exchange + Office).',
        },
    },
    {   class => 'Hardware', name => 'Impressora Recepção',
        attrs => {
            Vendor       => 'HP',
            Model        => 'LaserJet Pro M428fdw',
            SerialNumber => 'AUR-IMP-REC-SN3T8',
            Description  => 'Multifuncional da recepção (contingência do financeiro).',
        },
    },
);

# ── busca idempotente: CI da classe c/ Name e CustomerID=AURORA já existe? ────
sub already_seeded {
    my ($class, $name) = @_;
    my $ids = $CIObj->ConfigItemSearchExtended(
        ClassIDs => [ $CLASS{$class} ],
        Name     => $name,
        What     => [
            { "[%]{'Version'}[%]{'CustomerID'}[%]{'Content'}" => $TENANT },
        ],
    );
    return ( ref $ids eq 'ARRAY' && @$ids ) ? $ids->[0] : undef;
}

# ── XMLData no shape congelado: [undef, {Version=>[undef, {Key=>[undef,{Content=>..}]}]}] ──
sub build_xmldata {
    my ($attrs) = @_;
    my %ver = ( CustomerID => [ undef, { Content => $TENANT } ] );
    for my $k ( sort keys %$attrs ) {
        $ver{$k} = [ undef, { Content => $attrs->{$k} } ];
    }
    return [ undef, { Version => [ undef, \%ver ] } ];
}

# ── verifica se a versão atual do CI já tem o campo Memoria preenchido ────────
sub needs_enrichment {
    my ($cid) = @_;
    my $v = $CIObj->VersionGet( ConfigItemID => $cid, XMLDataGet => 1 );
    return 0 unless $v && ref $v eq 'HASH';
    my $node = eval { $v->{XMLData}->[1]{Version}[1] } || {};
    my $mem  = eval { $node->{Memoria}[1]{Content} };
    return ( !defined $mem || $mem eq '' ) ? 1 : 0;
}

my %REPORT = ( created => 0, skipped => 0, enriched => 0 );

for my $a (@ASSETS) {
    my $existing = already_seeded( $a->{class}, $a->{name} );
    if ($existing) {
        # approach (a): se já existe mas falta Memoria, adiciona versão enriquecida
        if ( $a->{class} eq 'Computer' && needs_enrichment($existing) ) {
            my $vid = $CIObj->VersionAdd(
                ConfigItemID => $existing,
                Name         => $a->{name},
                DefinitionID => def_id( $a->{class} ),
                DeplStateID  => $DEPL_PROD,
                InciStateID  => $INCI_OP,
                UserID       => $ROOT,
                XMLData      => build_xmldata( $a->{attrs} ),
            );
            if ($vid) {
                print "  ~ [$a->{class}] '$a->{name}' enriquecido (CI #$existing, nova versão #$vid)\n";
                $REPORT{enriched}++;
            } else {
                print "  ! [$a->{class}] '$a->{name}' FALHA ao enriquecer (CI #$existing)\n";
            }
        } else {
            print "  = [$a->{class}] '$a->{name}' já existe (CI #$existing) — pulado\n";
            $REPORT{skipped}++;
        }
        next;
    }

    my $cid = $CIObj->ConfigItemAdd(
        ClassID => $CLASS{ $a->{class} },
        UserID  => $ROOT,
    );
    die "FALHA ConfigItemAdd [$a->{class}] '$a->{name}'\n" unless $cid;

    my $vid = $CIObj->VersionAdd(
        ConfigItemID => $cid,
        Name         => $a->{name},
        DefinitionID => def_id( $a->{class} ),
        DeplStateID  => $DEPL_PROD,
        InciStateID  => $INCI_OP,
        UserID       => $ROOT,
        XMLData      => build_xmldata( $a->{attrs} ),
    );
    die "FALHA VersionAdd [$a->{class}] '$a->{name}'\n" unless $vid;

    my $ci = $CIObj->ConfigItemGet( ConfigItemID => $cid );
    print "  + [$a->{class}] '$a->{name}' criado (CI #$cid · "
        . ( $ci->{Number} // '?' ) . " · Production/Operational)\n";
    $REPORT{created}++;
}

print "\n=== RESUMO ===\n";
printf "  ativos criados:    %d\n", $REPORT{created};
printf "  ativos enriquecidos: %d (VersionAdd com SO/CPU/Memória/Disco)\n", $REPORT{enriched};
printf "  ativos pulados:    %d (já existiam e já tinham os campos)\n", $REPORT{skipped};
print "\nSeed CMDB concluído. Reexecutar é seguro (idempotente).\n\n";
exit 0;
