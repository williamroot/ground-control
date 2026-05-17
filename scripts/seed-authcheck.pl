#!/usr/bin/perl
# seed-authcheck.pl — valida credenciais via API nativa do Znuny.
#   Uso: perl seed-authcheck.pl <agent|customer> <login> <senha>
#   Saída: "OK:<login>" se autenticou, "FAIL" caso contrário.
# Usado pelo seed-demo.sh para provar (sem clicar) que as credenciais
# documentadas em .ia/DEMO.md realmente autenticam na instância viva.
use strict;
use warnings;
use lib '/opt/otrs';
use lib '/opt/otrs/Kernel/cpan-lib';
use lib '/opt/otrs/Custom';
use Kernel::System::ObjectManager;

local $Kernel::OM = Kernel::System::ObjectManager->new();
my ( $kind, $user, $pw ) = @ARGV;
my $mod = ( $kind && $kind eq 'customer' )
    ? 'Kernel::System::CustomerAuth'
    : 'Kernel::System::Auth';
my $r = $Kernel::OM->Get($mod)->Auth( User => $user, Pw => $pw );
print $r ? "OK:$r\n" : "FAIL\n";
exit( $r ? 0 : 1 );
