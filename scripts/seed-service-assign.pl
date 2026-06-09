#!/usr/bin/perl
# ─────────────────────────────────────────────────────────────────────────────
#  seed-service-assign.pl — Atribui todos os serviços válidos do Znuny aos
#  customer users da Aurora e cria os 3 tipos de ticket padrão.
#  (Fix #1E form-meta: Ticket::Service/Type ligados + Service::CustomerUser
#   MemberList populado → dropdowns do portal deixam de estar vazios.)
#
#  IDEMPOTENTE: CustomerUserServiceMemberAdd com Active=>1 é re-set (não duplica).
#  TypeLookup → só adiciona se não existe.  Reexecutar é seguro.
#
#  Executado DENTRO do container znuny-web, como usuário 'otrs':
#    docker compose exec -T znuny-web su -s /bin/bash otrs \
#      -c "perl /opt/otrs/var/seed-service-assign.pl"
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
    'Kernel::System::Log' => { LogPrefix => 'seed-service-assign' },
);

my $ServiceObject = $Kernel::OM->Get('Kernel::System::Service');
my $CUObject      = $Kernel::OM->Get('Kernel::System::CustomerUser');
my $TypeObject    = $Kernel::OM->Get('Kernel::System::Type');
my $ROOT          = 1;
my $TENANT        = 'AURORA';

print "\n=== SEED SERVICE-ASSIGN — atribui serviços + tipos (Aurora · #1E) ===\n\n";

# ── 1. Serviços válidos ───────────────────────────────────────────────────────
my %services = $ServiceObject->ServiceList( Valid => 1, UserID => $ROOT );
die "Nenhum serviço válido encontrado — rode o seed principal primeiro.\n"
    unless %services;
printf "  serviços válidos: %d\n", scalar keys %services;

# ── 2. Customer users da Aurora ───────────────────────────────────────────────
my %cu_hash = $CUObject->CustomerSearch( CustomerID => $TENANT );
die "Nenhum customer user para CustomerID='$TENANT' — rode o seed principal primeiro.\n"
    unless %cu_hash;
my @logins = sort keys %cu_hash;
printf "  customer users Aurora: %d (%s)\n\n", scalar @logins, join(', ', @logins);

# ── 3. Atribui cada serviço a cada customer user ──────────────────────────────
my $assigned = 0;
for my $login (@logins) {
    for my $sid ( sort { $a <=> $b } keys %services ) {
        $ServiceObject->CustomerUserServiceMemberAdd(
            CustomerUserLogin => $login,
            ServiceID         => $sid,
            Active            => 1,
            UserID            => $ROOT,
        );
        $assigned++;
    }
    printf "  + %-40s  %d serviços atribuídos\n", $login, scalar keys %services;
}
printf "\n  total de atribuições (re)aplicadas: %d\n\n", $assigned;

# ── 4. Tipos de ticket padrão ─────────────────────────────────────────────────
my @TYPES = ( 'Incidente', 'Requisição', 'Dúvida' );
my %type_report = ( created => 0, skipped => 0 );

for my $name (@TYPES) {
    my $tid = $TypeObject->TypeLookup( Type => $name );
    if ($tid) {
        print "  = tipo '$name' já existe (id $tid) — pulado\n";
        $type_report{skipped}++;
    } else {
        my $new_id = $TypeObject->TypeAdd(
            Name    => $name,
            ValidID => 1,
            UserID  => $ROOT,
        );
        die "FALHA ao criar tipo '$name'\n" unless $new_id;
        print "  + tipo '$name' criado (id $new_id)\n";
        $type_report{created}++;
    }
}

print "\n=== RESUMO ===\n";
printf "  atribuições (re)aplicadas: %d\n", $assigned;
printf "  tipos criados:             %d\n", $type_report{created};
printf "  tipos pulados:             %d (já existiam)\n", $type_report{skipped};
print "\nSeed service-assign concluído. Reexecutar é seguro (idempotente).\n\n";
exit 0;
