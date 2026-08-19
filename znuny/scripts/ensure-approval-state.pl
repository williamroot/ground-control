#!/usr/bin/perl
# --
# Gerti — cria o estado de "aguardando aprovação" (T-R7.6, R7 do vídeo).
#
# *"todo ticket passa por aqui e vai pra um aprovador… ele entra lá no portal e
# aprova ou não aprova o ticket."* (07:40)
#
# O estado é do tipo **`pending reminder`**, e essa escolha é a parte que
# importa: nele o relógio de SLA do Znuny NÃO corre. Um estado do tipo `new` ou
# `open` faria o cliente que demora dois dias para aprovar queimar o SLA da
# Gerti — transformando um recurso em armadilha contratual.
#
# Idempotente (D6): rodar de novo não duplica nem altera nada.
# --
use strict;
use warnings;

use lib '/opt/otrs';
use lib '/opt/otrs/Kernel/cpan-lib';
use lib '/opt/otrs/Custom';

use Kernel::System::ObjectManager;

local $Kernel::OM = Kernel::System::ObjectManager->new(
    'Kernel::System::Log' => { LogPrefix => 'ensure-approval-state' },
);

my $StateObject = $Kernel::OM->Get('Kernel::System::State');
my $NAME        = 'aguardando aprovacao';

my %Existing = $StateObject->StateGet( Name => $NAME );
if ( $Existing{ID} ) {
    print "[ensure-approval-state] estado '$NAME' já existe (id $Existing{ID}) — nada a fazer.\n";
    exit 0;
}

# O TypeID de `pending reminder`, resolvido pelo nome — o id numérico varia
# entre instalações e cravá-lo seria a receita para quebrar em outra base.
my %Types = $StateObject->StateTypeList( UserID => 1 );
my ($PendingTypeID) = grep { lc( $Types{$_} ) eq 'pending reminder' } keys %Types;

if ( !$PendingTypeID ) {
    print STDERR "[ensure-approval-state] FATAL: tipo 'pending reminder' não encontrado.\n";
    exit 1;
}

my $ID = $StateObject->StateAdd(
    Name    => $NAME,
    Comment => 'Chamado aguardando aprovacao do cliente (Gerti R7). SLA nao corre neste estado.',
    ValidID => 1,
    TypeID  => $PendingTypeID,
    UserID  => 1,
);

if ( !$ID ) {
    print STDERR "[ensure-approval-state] FATAL: nao foi possivel criar o estado.\n";
    exit 1;
}
print "[ensure-approval-state] estado '$NAME' criado (id $ID, tipo pending reminder).\n";
exit 0;
