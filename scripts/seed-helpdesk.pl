#!/usr/bin/perl
# seed-helpdesk.pl — cria os customer_user de HELP-DESK dos 2 tenants de teste
# (Spec #1H). IDEMPOTENTE. Roda DENTRO do container znuny-web como 'otrs'.
# As empresas (AURORA / TECHNOVA) já existem (seed-demo.pl / seed-technova.pl);
# aqui só garantimos 1 customer_user help-desk por tenant + senha de demo, para
# o portal demonstrar a diferença de papéis (admin × help-desk). O PAPEL em si
# (admin/helpdesk) mora no schema gerti (portal_user_role, seed_demo_branding.py)
# — este script só cria o login que autentica no Znuny.
use strict; use warnings;
use lib '/opt/otrs'; use lib '/opt/otrs/Kernel/cpan-lib'; use lib '/opt/otrs/Custom';
use Kernel::System::ObjectManager;
local $Kernel::OM = Kernel::System::ObjectManager->new();
my $CU = $Kernel::OM->Get('Kernel::System::CustomerUser');
my $ROOT = 1;

# (login/e-mail, primeiro, último, CustomerID, senha demo)
my @USERS = (
    {
        UserLogin => 'helpdesk@auroramoveis.com.br', UserFirstname => 'Equipe',
        UserLastname => 'Help Desk', UserEmail => 'helpdesk@auroramoveis.com.br',
        UserCustomerID => 'AURORA', UserTitle => 'Help Desk (tenant de teste)',
        PW => 'Aurora@Help2026',
    },
    {
        UserLogin => 'suporte.ops@technova.example', UserFirstname => 'Operação',
        UserLastname => 'Help Desk', UserEmail => 'suporte.ops@technova.example',
        UserCustomerID => 'TECHNOVA', UserTitle => 'Help Desk (tenant de teste)',
        PW => 'TechNova@Help2026',
    },
);

for my $u (@USERS) {
    my $pw = delete $u->{PW};
    my %existing = $CU->CustomerUserDataGet( User => $u->{UserLogin} );
    if ( $existing{UserLogin} ) {
        $CU->CustomerUserUpdate( %$u, ID => $u->{UserLogin},
            Source => 'CustomerUser', ValidID => 1, UserID => $ROOT );
        print "= cliente help-desk '$u->{UserLogin}' já existia — atualizado\n";
    } else {
        $CU->CustomerUserAdd( %$u, Source => 'CustomerUser',
            ValidID => 1, UserID => $ROOT )
            or die "FALHA ao criar help-desk $u->{UserLogin}\n";
        print "+ cliente help-desk '$u->{UserLogin}' criado\n";
    }
    $CU->SetPassword( UserLogin => $u->{UserLogin}, PW => $pw );
    print "= senha do help-desk '$u->{UserLogin}' aplicada\n";
}
