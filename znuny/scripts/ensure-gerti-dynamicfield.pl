# znuny/scripts/ensure-gerti-dynamicfield.pl
# Cria o DynamicField GertiContractId (Text, objeto Ticket) se ainda não existir.
# Idempotente: se já existe, não faz nada. Roda como otrs no deploy.
use strict;
use warnings;
use lib '/opt/otrs';
use lib '/opt/otrs/Kernel/cpan-lib';
use lib '/opt/otrs/Custom';
use Kernel::System::ObjectManager;

local $Kernel::OM = Kernel::System::ObjectManager->new();
my $DFObject = $Kernel::OM->Get('Kernel::System::DynamicField');

my $Existing = $DFObject->DynamicFieldGet( Name => 'GertiContractId' );
if ( $Existing && %{$Existing} ) {
    print "GertiContractId already present — skipping\n";
    exit 0;
}

my $ID = $DFObject->DynamicFieldAdd(
    Name       => 'GertiContractId',
    Label      => 'Contrato Gerti',
    FieldOrder => 9000,
    FieldType  => 'Text',
    ObjectType => 'Ticket',
    Config     => { DefaultValue => '', Link => '' },
    ValidID    => 1,
    UserID     => 1,
);
die "FATAL: could not create GertiContractId DynamicField\n" if !$ID;
print "GertiContractId created (id $ID)\n";
exit 0;
