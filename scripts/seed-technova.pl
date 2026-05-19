#!/usr/bin/perl
# seed-technova.pl — fixture MÍNIMO de login Znuny p/ o 2º tenant de teste
# (Spec #1F-a). IDEMPOTENTE. Roda DENTRO do container znuny-web como 'otrs'.
# NÃO é onboarding (#1G): só 1 CustomerCompany + 1 CustomerUser para o
# login do portal validar contra o Znuny real para o tenant TechNova.
use strict; use warnings;
use lib '/opt/otrs'; use lib '/opt/otrs/Kernel/cpan-lib'; use lib '/opt/otrs/Custom';
use Kernel::System::ObjectManager;
local $Kernel::OM = Kernel::System::ObjectManager->new();
my $CC = $Kernel::OM->Get('Kernel::System::CustomerCompany');
my $CU = $Kernel::OM->Get('Kernel::System::CustomerUser');
my $ROOT = 1;

my %COMPANY = (
    CustomerID          => 'TECHNOVA',
    CustomerCompanyName => 'TechNova Soluções em Tecnologia Ltda.',
    CustomerCompanyCountry => 'Brazil',
    CustomerCompanyURL  => 'https://www.technova.example',
    CustomerCompanyComment => 'Tenant de teste #1F-a (white-label 2).',
);
my %USER = (
    UserLogin     => 'admin.tech@technova.example',
    UserFirstname => 'Admin',
    UserLastname  => 'TechNova',
    UserEmail     => 'admin.tech@technova.example',
    UserCustomerID => 'TECHNOVA',
    UserTitle     => 'Administrador (tenant de teste)',
);
my $PASS = 'TechNova@Demo2026';   # senha demo pública, padrão <Marca>@Demo2026

my %cc = $CC->CustomerCompanyGet( CustomerID => $COMPANY{CustomerID} );
if ( $cc{CustomerID} ) {
    $CC->CustomerCompanyUpdate( %COMPANY,
        CustomerCompanyID => $COMPANY{CustomerID}, ValidID => 1, UserID => $ROOT );
    print "= empresa 'TECHNOVA' já existia — atualizada\n";
} else {
    $CC->CustomerCompanyAdd( %COMPANY, ValidID => 1, UserID => $ROOT )
        or die "FALHA ao criar empresa TECHNOVA\n";
    print "+ empresa 'TECHNOVA' criada\n";
}

my %u = $CU->CustomerUserDataGet( User => $USER{UserLogin} );
if ( $u{UserLogin} ) {
    $CU->CustomerUserUpdate( %USER, ID => $USER{UserLogin},
        Source => 'CustomerUser', ValidID => 1, UserID => $ROOT );
    print "= cliente 'admin.tech\@technova.example' já existia — atualizado\n";
} else {
    $CU->CustomerUserAdd( %USER, Source => 'CustomerUser',
        ValidID => 1, UserID => $ROOT )
        or die "FALHA ao criar cliente admin.tech\@technova.example\n";
    print "+ cliente 'admin.tech\@technova.example' criado\n";
}
$CU->SetPassword( UserLogin => $USER{UserLogin}, PW => $PASS );
print "= senha do cliente TechNova aplicada\n";
