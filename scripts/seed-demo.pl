#!/usr/bin/perl
# ─────────────────────────────────────────────────────────────────────────────
#  seed-demo.pl — Semeia a instância Znuny com uma operação MSP fictícia,
#  porém crível, em PT-BR (cenário Gerti Service Desk / demo Tiflux→Znuny).
#
#  IDEMPOTENTE: cada entidade é verificada-antes-de-criar. Reexecutar não
#  duplica nem aborta — apenas reporta "já existe" e segue.
#
#  Executado DENTRO do container znuny-web, como usuário 'otrs':
#    docker compose exec -T znuny-web su -s /bin/bash otrs \
#      -c "perl /opt/otrs/var/seed-demo.pl"
#
#  Empresa fictícia: Móveis Aurora Indústria e Comércio Ltda.
#  (nome fantasia "Aurora Móveis"), fabricante de móveis planejados em
#  Bento Gonçalves/RS — cliente da Gerti (MSP).
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
    'Kernel::System::Log' => { LogPrefix => 'seed-demo' },
);

my $DBObject       = $Kernel::OM->Get('Kernel::System::DB');
my $UserObject     = $Kernel::OM->Get('Kernel::System::User');
my $GroupObject    = $Kernel::OM->Get('Kernel::System::Group');
my $QueueObject    = $Kernel::OM->Get('Kernel::System::Queue');
my $ServiceObject  = $Kernel::OM->Get('Kernel::System::Service');
my $SLAObject      = $Kernel::OM->Get('Kernel::System::SLA');
my $CCObject       = $Kernel::OM->Get('Kernel::System::CustomerCompany');
my $CUObject       = $Kernel::OM->Get('Kernel::System::CustomerUser');
my $TicketObject   = $Kernel::OM->Get('Kernel::System::Ticket');
my $ArticleObject  = $Kernel::OM->Get('Kernel::System::Ticket::Article');
my $StateObject    = $Kernel::OM->Get('Kernel::System::State');
my $TimeObject     = $Kernel::OM->Get('Kernel::System::Time');

my $ROOT = 1;    # UserID root para operações de criação
my %REPORT;
sub note { my ($k) = @_; $REPORT{$k}++; }
sub say2 { print "  $_[0]\n"; }

print "\n=== SEED DEMO — Gerti Service Desk (Aurora Móveis) ===\n\n";

# ─────────────────────────────────────────────────────────────────────────────
# 0. CONFIG: cenário
# ─────────────────────────────────────────────────────────────────────────────
my $COMPANY = {
    CustomerID  => 'AURORA',
    CustomerCompanyName => 'Móveis Aurora Indústria e Comércio Ltda.',
    CustomerCompanyStreet  => 'Rua dos Marceneiros, 1240 — Distrito Industrial',
    CustomerCompanyZIP     => '95700-000',
    CustomerCompanyCity    => 'Bento Gonçalves/RS',
    CustomerCompanyCountry => 'Brazil',
    CustomerCompanyURL     => 'https://www.auroramoveis.com.br',
    CustomerCompanyComment =>
        'Fabricante de móveis planejados. CNPJ 18.472.366/0001-90. '
      . 'Tel. (54) 3452-7700. Cliente da Gerti desde 2023 — contrato Suporte Gerenciado (SLA Ouro).',
};
my $DOMAIN = 'auroramoveis.com.br';

# Agentes (técnicos da Gerti / MSP) + admin William
my @AGENTS = (
    {   login => 'william', first => 'William', last => 'Alves',
        email => 'williamalvesroot@gmail.com', pass => 'Gerti@Demo2026',
        admin => 1, role => 'Administradores',
        groups => [qw(admin users stats)],
        comment => 'Owner / Administrador da plataforma (Gerti).',
    },
    {   login => 'bruno.cardoso', first => 'Bruno', last => 'Cardoso',
        email => 'bruno.cardoso@gerti.com.br', pass => 'Gerti@Demo2026',
        role => 'Suporte N1', groups => [qw(users)],
        comment => 'Analista de Suporte N1.',
    },
    {   login => 'patricia.menezes', first => 'Patrícia', last => 'Menezes',
        email => 'patricia.menezes@gerti.com.br', pass => 'Gerti@Demo2026',
        role => 'Suporte N1', groups => [qw(users)],
        comment => 'Analista de Suporte N1.',
    },
    {   login => 'rafael.tavares', first => 'Rafael', last => 'Tavares',
        email => 'rafael.tavares@gerti.com.br', pass => 'Gerti@Demo2026',
        role => 'Suporte N2', groups => [qw(users)],
        comment => 'Especialista N2 — Infraestrutura e Redes.',
    },
    {   login => 'diego.fontana', first => 'Diego', last => 'Fontana',
        email => 'diego.fontana@gerti.com.br', pass => 'Gerti@Demo2026',
        role => 'Field Service', groups => [qw(users)],
        comment => 'Técnico de campo (Field Service) — atendimento on-site.',
    },
);

# Customer users — colaboradores da Aurora Móveis
my @CUSTOMERS = (
    {   login => 'mariana.bianchi', first => 'Mariana', last => 'Bianchi',
        email => "mariana.bianchi\@$DOMAIN", phone => '(54) 3452-7710',
        title => 'Coordenadora Administrativa', pass => 'Aurora@Demo2026' },
    {   login => 'eduardo.salvi', first => 'Eduardo', last => 'Salvi',
        email => "eduardo.salvi\@$DOMAIN", phone => '(54) 3452-7715',
        title => 'Gerente de TI', pass => 'Aurora@Demo2026' },
    {   login => 'carla.dorneles', first => 'Carla', last => 'Dorneles',
        email => "carla.dorneles\@$DOMAIN", phone => '(54) 3452-7720',
        title => 'Analista Financeiro', pass => 'Aurora@Demo2026' },
    {   login => 'fernando.rech', first => 'Fernando', last => 'Rech',
        email => "fernando.rech\@$DOMAIN", phone => '(54) 3452-7725',
        title => 'Supervisor de Produção', pass => 'Aurora@Demo2026' },
    {   login => 'juliana.peruzzo', first => 'Juliana', last => 'Peruzzo',
        email => "juliana.peruzzo\@$DOMAIN", phone => '(54) 3452-7730',
        title => 'Assistente de RH', pass => 'Aurora@Demo2026' },
);

# Roles (agente)
my @ROLES = (
    { name => 'Administradores', comment => 'Administração total da plataforma.' },
    { name => 'Suporte N1',      comment => 'Atendimento de 1º nível (triagem).' },
    { name => 'Suporte N2',      comment => 'Atendimento de 2º nível (especialista).' },
    { name => 'Field Service',   comment => 'Atendimento de campo / on-site.' },
);

# Queues — árvore MSP
my @QUEUES = (
    { name => 'Suporte',                group => 'users',
      comment => 'Raiz de suporte ao cliente.' },
    { name => 'Suporte::N1',            group => 'users',
      comment => 'Primeiro nível — triagem e incidentes simples.',
      first_response => 30, update => 120, solution => 480 },
    { name => 'Suporte::N2',            group => 'users',
      comment => 'Segundo nível — escalonamento técnico.',
      first_response => 60, update => 240, solution => 960 },
    { name => 'Field Service',          group => 'users',
      comment => 'Atendimento presencial / on-site.',
      first_response => 120, update => 480, solution => 1920 },
    { name => 'Financeiro',             group => 'users',
      comment => 'Faturamento, contratos e cobrança.',
      first_response => 240, update => 960, solution => 2880 },
);

# Serviços (catálogo MSP)
my @SERVICES = (
    { name => 'Infraestrutura' },
    { name => 'Infraestrutura::Servidores' },
    { name => 'Infraestrutura::Backup' },
    { name => 'Microsoft 365' },
    { name => 'Microsoft 365::E-mail (Exchange)' },
    { name => 'Rede' },
    { name => 'Rede::VPN' },
    { name => 'Rede::Wi-Fi' },
    { name => 'Hardware' },
    { name => 'Hardware::Impressoras' },
    { name => 'Acesso e Senhas' },
);

# SLAs
my @SLAS = (
    { name => 'SLA Bronze', first_response => 480, update => 960,  solution => 2880,
      comment => 'Resposta 8h / Solução 48h (horário comercial).' },
    { name => 'SLA Prata',  first_response => 240, update => 480,  solution => 1440,
      comment => 'Resposta 4h / Solução 24h (horário comercial).' },
    { name => 'SLA Ouro',   first_response => 60,  update => 120,  solution => 480,
      comment => 'Resposta 1h / Solução 8h — contrato gerenciado.' },
);

# ─────────────────────────────────────────────────────────────────────────────
# 1. ROLES
# ─────────────────────────────────────────────────────────────────────────────
print "[1] Roles (perfis de agente)\n";
my %ROLE_ID;
for my $r (@ROLES) {
    my %list = $GroupObject->RoleList( Valid => 0 );
    my ($rid) = grep { $list{$_} eq $r->{name} } keys %list;
    if ($rid) { say2 "= role '$r->{name}' já existe (#$rid)"; }
    else {
        $rid = $GroupObject->RoleAdd(
            Name => $r->{name}, Comment => $r->{comment},
            ValidID => 1, UserID => $ROOT,
        );
        die "FALHA ao criar role $r->{name}\n" unless $rid;
        say2 "+ role '$r->{name}' criada (#$rid)"; note('roles_created');
    }
    $ROLE_ID{ $r->{name} } = $rid;
}

# Permissões role→group: todas as roles operacionais com rw em 'users'
my %GRP = reverse $GroupObject->GroupList( Valid => 1 );  # name => id
for my $rname (keys %ROLE_ID) {
    my $gid = $GRP{users} or next;
    $GroupObject->PermissionGroupRoleAdd(
        RID => $ROLE_ID{$rname}, GID => $gid,
        Permission => { ro => 1, move_into => 1, create => 1,
                        owner => 1, priority => 1, rw => 1 },
        UserID => $ROOT,
    );
}
# Administradores também rw em admin + stats
for my $g (qw(admin stats)) {
    next unless $GRP{$g};
    $GroupObject->PermissionGroupRoleAdd(
        RID => $ROLE_ID{'Administradores'}, GID => $GRP{$g},
        Permission => { ro => 1, move_into => 1, create => 1,
                        owner => 1, priority => 1, rw => 1 },
        UserID => $ROOT,
    );
}
say2 "= permissões role→grupo aplicadas";

# ─────────────────────────────────────────────────────────────────────────────
# 2. AGENTES
# ─────────────────────────────────────────────────────────────────────────────
print "\n[2] Agentes (técnicos Gerti + admin)\n";
my %AGENT_ID;
for my $a (@AGENTS) {
    my %exist = $UserObject->UserList( Type => 'Long', Valid => 0 );
    my $uid = $UserObject->UserLookup( UserLogin => $a->{login} );
    if ($uid) {
        say2 "= agente '$a->{login}' já existe (#$uid)";
    }
    else {
        $uid = $UserObject->UserAdd(
            UserFirstname => $a->{first}, UserLastname => $a->{last},
            UserLogin => $a->{login}, UserEmail => $a->{email},
            UserPw => $a->{pass}, ValidID => 1, ChangeUserID => $ROOT,
        );
        die "FALHA ao criar agente $a->{login}\n" unless $uid;
        say2 "+ agente '$a->{login}' criado (#$uid)"; note('agents_created');
    }
    # senha sempre re-aplicada (garante credencial documentada)
    $UserObject->SetPassword( UserLogin => $a->{login}, PW => $a->{pass} );
    $AGENT_ID{ $a->{login} } = $uid;

    # vincular grupos diretos
    for my $g ( @{ $a->{groups} } ) {
        next unless $GRP{$g};
        $GroupObject->PermissionGroupUserAdd(
            GID => $GRP{$g}, UID => $uid,
            Permission => { ro => 1, move_into => 1, create => 1,
                            owner => 1, priority => 1, rw => 1 },
            UserID => $ROOT,
        );
    }
    # vincular role
    if ( $a->{role} && $ROLE_ID{ $a->{role} } ) {
        $GroupObject->PermissionRoleUserAdd(
            RID => $ROLE_ID{ $a->{role} }, UID => $uid,
            Active => 1, UserID => $ROOT,
        );
    }
}
say2 "= grupos/roles dos agentes aplicados";

# ─────────────────────────────────────────────────────────────────────────────
# 3. EMPRESA CLIENTE (tenant)
# ─────────────────────────────────────────────────────────────────────────────
print "\n[3] Empresa cliente (Aurora Móveis)\n";
my %cc = $CCObject->CustomerCompanyGet( CustomerID => $COMPANY->{CustomerID} );
if ( $cc{CustomerID} ) {
    $CCObject->CustomerCompanyUpdate(
        %$COMPANY, CustomerCompanyID => $COMPANY->{CustomerID},
        ValidID => 1, UserID => $ROOT,
    );
    say2 "= empresa '$COMPANY->{CustomerID}' já existia — atualizada";
}
else {
    my $ok = $CCObject->CustomerCompanyAdd(
        %$COMPANY, ValidID => 1, UserID => $ROOT,
    );
    die "FALHA ao criar empresa\n" unless $ok;
    say2 "+ empresa '$COMPANY->{CustomerID}' criada"; note('companies_created');
}

# ─────────────────────────────────────────────────────────────────────────────
# 4. CUSTOMER USERS
# ─────────────────────────────────────────────────────────────────────────────
print "\n[4] Customer users (colaboradores Aurora)\n";
for my $c (@CUSTOMERS) {
    my %u = $CUObject->CustomerUserDataGet( User => $c->{login} );
    if ( $u{UserLogin} ) {
        $CUObject->CustomerUserUpdate(
            ID => $c->{login}, Source => 'CustomerUser',
            UserLogin => $c->{login}, UserFirstname => $c->{first},
            UserLastname => $c->{last}, UserEmail => $c->{email},
            UserCustomerID => $COMPANY->{CustomerID},
            UserPhone => $c->{phone}, UserTitle => $c->{title},
            ValidID => 1, UserID => $ROOT,
        );
        say2 "= cliente '$c->{login}' já existia — atualizado";
    }
    else {
        my $ok = $CUObject->CustomerUserAdd(
            Source => 'CustomerUser',
            UserLogin => $c->{login}, UserFirstname => $c->{first},
            UserLastname => $c->{last}, UserEmail => $c->{email},
            UserCustomerID => $COMPANY->{CustomerID},
            UserPhone => $c->{phone}, UserTitle => $c->{title},
            ValidID => 1, UserID => $ROOT,
        );
        die "FALHA ao criar cliente $c->{login}\n" unless $ok;
        say2 "+ cliente '$c->{login}' criado"; note('customers_created');
    }
    $CUObject->SetPassword( UserLogin => $c->{login}, PW => $c->{pass} );
}
say2 "= senhas dos clientes aplicadas";

# ─────────────────────────────────────────────────────────────────────────────
# 5. QUEUES
# ─────────────────────────────────────────────────────────────────────────────
print "\n[5] Filas (árvore MSP)\n";
my %QUEUE_ID;
for my $q (@QUEUES) {
    my $qid = $QueueObject->QueueLookup( Queue => $q->{name}, Silent => 1 );
    my $gid = $GRP{ $q->{group} } || $GRP{users};
    if ($qid) {
        say2 "= fila '$q->{name}' já existe (#$qid)";
    }
    else {
        $qid = $QueueObject->QueueAdd(
            Name => $q->{name}, ValidID => 1, GroupID => $gid,
            FirstResponseTime => $q->{first_response} || 0,
            UpdateTime => $q->{update} || 0,
            SolutionTime => $q->{solution} || 0,
            UnlockTimeout => 1440, SystemAddressID => 1,
            SalutationID => 1, SignatureID => 1,
            Comment => $q->{comment}, UserID => $ROOT,
        );
        die "FALHA ao criar fila $q->{name}\n" unless $qid;
        say2 "+ fila '$q->{name}' criada (#$qid)"; note('queues_created');
    }
    $QUEUE_ID{ $q->{name} } = $qid;
}

# ─────────────────────────────────────────────────────────────────────────────
# 6. SERVIÇOS
# ─────────────────────────────────────────────────────────────────────────────
print "\n[6] Serviços (catálogo)\n";
my %SVC_ID;
for my $s (@SERVICES) {
    my $full = $s->{name};
    my $sid  = $ServiceObject->ServiceLookup( Name => $full, Silent => 1 );
    if ($sid) { say2 "= serviço '$full' já existe (#$sid)"; }
    else {
        my ($parent_id) = ( 0 );
        my $leaf = $full;
        if ( $full =~ /^(.+)::([^:]+)$/ ) {
            $parent_id = $SVC_ID{$1} || $ServiceObject->ServiceLookup( Name => $1, Silent => 1 ) || 0;
            $leaf = $2;
        }
        $sid = $ServiceObject->ServiceAdd(
            Name => $leaf, ParentID => $parent_id,
            ValidID => 1, UserID => $ROOT,
        );
        die "FALHA ao criar serviço $full\n" unless $sid;
        say2 "+ serviço '$full' criado (#$sid)"; note('services_created');
    }
    $SVC_ID{$full} = $sid;
}

# ─────────────────────────────────────────────────────────────────────────────
# 7. SLAs
# ─────────────────────────────────────────────────────────────────────────────
print "\n[7] SLAs\n";
my %SLA_ID;
for my $sla (@SLAS) {
    my %list = $SLAObject->SLAList( UserID => $ROOT );
    my ($sid) = grep { $list{$_} eq $sla->{name} } keys %list;
    if ($sid) { say2 "= SLA '$sla->{name}' já existe (#$sid)"; }
    else {
        $sid = $SLAObject->SLAAdd(
            Name => $sla->{name},
            FirstResponseTime => $sla->{first_response},
            UpdateTime => $sla->{update},
            SolutionTime => $sla->{solution},
            Comment => $sla->{comment}, ValidID => 1, UserID => $ROOT,
        );
        die "FALHA ao criar SLA $sla->{name}\n" unless $sid;
        say2 "+ SLA '$sla->{name}' criado (#$sid)"; note('slas_created');
    }
    $SLA_ID{ $sla->{name} } = $sid;
}

# ─────────────────────────────────────────────────────────────────────────────
# 8. TICKETS
# ─────────────────────────────────────────────────────────────────────────────
print "\n[8] Tickets (chamados realistas)\n";

# helper p/ timestamp relativo: dias atrás, hora
sub ts_back {
    my ( $days_ago, $hour, $min ) = @_;
    $hour //= 9; $min //= 0;
    my $sys = $TimeObject->SystemTime();
    my $t   = $sys - ( $days_ago * 86400 );
    my ( $s, $m, $h, $D, $M, $Y ) = ( localtime $t )[ 0 .. 5 ];
    return sprintf( '%04d-%02d-%02d %02d:%02d:00',
        $Y + 1900, $M + 1, $D, $hour, $min );
}
sub sysdate_back {
    my ($days_ago, $hour, $min) = @_;
    return $TimeObject->TimeStamp2SystemTime(
        String => ts_back($days_ago, $hour, $min) );
}

my %STATE = reverse $StateObject->StateList( UserID => $ROOT );  # name=>id not needed; use names

# cada ticket: chave única via Title-prefix p/ idempotência
my @TICKETS = (
    {   key => 'AUR-EMAIL-OUTLOOK',
        title => 'Não consigo acessar o e-mail no Outlook',
        queue => 'Suporte::N1', service => 'Microsoft 365::E-mail (Exchange)',
        sla => 'SLA Ouro', prio => '3 normal', state => 'closed successful',
        owner => 'bruno.cardoso', cust => 'mariana.bianchi',
        days_ago => 27, time_units => [ 20, 15 ],
        articles => [
            { from => 'cust', d => 27, h => 8,  m => 41,
              s => 'Não consigo acessar o e-mail no Outlook',
              b => "Bom dia,\n\nDesde ontem à tarde o Outlook fica pedindo a senha repetidamente e não recebe e-mails novos. Já reiniciei o computador duas vezes. Preciso do e-mail funcionando para fechar os pedidos da semana.\n\nObrigada,\nMariana Bianchi" },
            { from => 'agent', who => 'bruno.cardoso', d => 27, h => 9, m => 12,
              s => 'RES: Não consigo acessar o e-mail no Outlook',
              b => "Olá, Mariana.\n\nObrigado pelo contato. Identificamos que sua senha do Microsoft 365 expirou pela política de 90 dias. Vou redefinir a senha temporária e te oriento a troca.\n\nPor favor, abra o Outlook novamente e quando solicitar a senha use a temporária que enviei no seu WhatsApp corporativo. Aguardo o retorno.\n\nAtenciosamente,\nBruno Cardoso — Suporte N1 Gerti" },
            { from => 'cust', d => 27, h => 9, m => 58,
              s => 'RES: Não consigo acessar o e-mail no Outlook',
              b => "Funcionou! Troquei a senha e o Outlook já sincronizou tudo. Muito obrigada pela agilidade." },
            { from => 'agent', who => 'bruno.cardoso', d => 27, h => 10, m => 5,
              internal => 1, s => 'Nota interna',
              b => "Senha M365 expirada (política 90d). Redefinida e usuária orientada. Sugerido habilitar aviso de expiração 7 dias antes — registrar como melhoria no contrato." },
            { from => 'agent', who => 'bruno.cardoso', d => 27, h => 10, m => 7,
              s => 'RES: Não consigo acessar o e-mail no Outlook',
              b => "Que ótimo, Mariana! Chamado resolvido então. Qualquer coisa estamos à disposição.\n\nAbraço,\nBruno" },
        ],
    },
    {   key => 'AUR-IMPRESSORA-FIN',
        title => 'Impressora do setor financeiro fora de operação',
        queue => 'Field Service', service => 'Hardware::Impressoras',
        sla => 'SLA Prata', prio => '4 high', state => 'closed successful',
        owner => 'diego.fontana', cust => 'carla.dorneles',
        days_ago => 21, time_units => [ 30, 90 ],
        articles => [
            { from => 'cust', d => 21, h => 8, m => 20,
              s => 'Impressora do financeiro não liga',
              b => "Bom dia, a impressora multifuncional do setor financeiro (HP LaserJet do corredor) não liga de jeito nenhum. Já testamos outra tomada. Estamos sem imprimir boletos e notas.\n\nCarla Dorneles — Financeiro" },
            { from => 'agent', who => 'diego.fontana', d => 21, h => 9, m => 2,
              s => 'RES: Impressora do financeiro não liga',
              b => "Olá, Carla. Vou agendar uma visita técnica ainda hoje à tarde para diagnóstico no local. Enquanto isso, podem usar a impressora da recepção como contingência. Confirmo a ida até 14h." },
            { from => 'agent', who => 'diego.fontana', d => 20, h => 15, m => 40,
              internal => 1, s => 'Nota de campo',
              b => "Visita realizada. Fonte interna queimada (provável surto elétrico). Substituída por fonte de reposição do estoque Gerti. Recomendado nobreak dedicado para o setor financeiro — abrir orçamento via Financeiro." },
            { from => 'agent', who => 'diego.fontana', d => 20, h => 16, m => 10,
              s => 'RES: Impressora do financeiro não liga',
              b => "Carla, a impressora foi reparada (troca de fonte) e está operando normalmente. Recomendamos a instalação de um nobreak dedicado para evitar recorrência — vamos enviar orçamento pelo Financeiro. Encerro o chamado, qualquer coisa reabrimos." },
        ],
    },
    {   key => 'AUR-NOVO-COLAB',
        title => 'Solicitação de novo colaborador — provisionar acessos',
        queue => 'Suporte::N1', service => 'Acesso e Senhas',
        sla => 'SLA Ouro', prio => '3 normal', state => 'closed successful',
        owner => 'patricia.menezes', cust => 'juliana.peruzzo',
        days_ago => 17, time_units => [ 25, 20 ],
        articles => [
            { from => 'cust', d => 17, h => 10, m => 0,
              s => 'Provisionar acessos — novo colaborador (Produção)',
              b => "Olá, vamos receber um novo colaborador na Produção na próxima segunda:\n\nNome: Anderson Folle\nCargo: Auxiliar de Produção\nPrecisa de: usuário de rede, e-mail corporativo, acesso ao sistema de PCP e crachá.\n\nPodem deixar tudo pronto até sexta? Obrigada — Juliana, RH" },
            { from => 'agent', who => 'patricia.menezes', d => 17, h => 10, m => 35,
              s => 'RES: Provisionar acessos — novo colaborador',
              b => "Oi, Juliana! Recebido. Vou abrir o provisionamento: usuário de rede, caixa Exchange (anderson.folle\@auroramoveis.com.br), acesso ao PCP perfil 'operador' e solicitar o crachá com a portaria. Te confirmo conforme for concluindo." },
            { from => 'agent', who => 'patricia.menezes', d => 15, h => 14, m => 12,
              internal => 1, s => 'Checklist provisionamento',
              b => "[x] AD/usuário de rede\n[x] Caixa M365\n[x] Perfil PCP operador\n[ ] Crachá (com a portaria — previsto p/ sexta)" },
            { from => 'agent', who => 'patricia.menezes', d => 14, h => 11, m => 0,
              s => 'RES: Provisionar acessos — novo colaborador',
              b => "Juliana, acessos de rede, e-mail e PCP já criados e testados. O crachá fica pronto na portaria até sexta. Senha inicial enviada ao gestor. Encerro o chamado — bom trabalho ao novo colega!" },
        ],
    },
    {   key => 'AUR-VPN-LENTA',
        title => 'Lentidão na VPN para acesso ao ERP',
        queue => 'Suporte::N2', service => 'Rede::VPN',
        sla => 'SLA Ouro', prio => '4 high', state => 'open',
        owner => 'rafael.tavares', cust => 'eduardo.salvi',
        days_ago => 4, time_units => [ 45 ],
        articles => [
            { from => 'cust', d => 4, h => 9, m => 15,
              s => 'VPN muito lenta para o ERP',
              b => "Pessoal, a VPN está extremamente lenta nos últimos dias, principalmente das 9h às 11h. O ERP fica travando para a equipe que trabalha de casa. Podem verificar? Eduardo Salvi — TI Aurora" },
            { from => 'agent', who => 'rafael.tavares', d => 4, h => 10, m => 2,
              s => 'RES: VPN muito lenta para o ERP',
              b => "Olá, Eduardo. Estamos analisando. Em uma primeira coleta vimos saturação do link no horário de pico. Vou levantar o consumo por usuário e verificar a política de QoS do firewall. Retorno ainda hoje com diagnóstico." },
            { from => 'agent', who => 'rafael.tavares', d => 3, h => 16, m => 30,
              internal => 1, s => 'Diagnóstico parcial',
              b => "Link de 200Mbps saturando 9-11h por backup em nuvem rodando em horário comercial + tráfego de atualização Windows. Proposta: reagendar backup p/ madrugada e aplicar QoS priorizando VPN/ERP. Aguardando janela com o cliente." },
        ],
    },
    {   key => 'AUR-BACKUP-FALHA',
        title => 'Backup falhou na madrugada — servidor de arquivos',
        queue => 'Suporte::N2', service => 'Infraestrutura::Backup',
        sla => 'SLA Ouro', prio => '5 very high', state => 'pending reminder',
        owner => 'rafael.tavares', cust => 'eduardo.salvi',
        days_ago => 2, pending_days => 1, time_units => [ 35 ],
        articles => [
            { from => 'agent', who => 'rafael.tavares', d => 2, h => 6, m => 5,
              s => 'Alerta: backup do FILE-SRV falhou (00:30)',
              b => "Chamado aberto proativamente pelo monitoramento Gerti. O job de backup do servidor de arquivos (FILE-SRV) falhou às 00:30 com erro de espaço insuficiente no destino. Iniciando tratativa e abrindo acompanhamento com o cliente." },
            { from => 'agent', who => 'rafael.tavares', d => 2, h => 7, m => 50,
              s => 'RES: Backup do FILE-SRV falhou',
              b => "Eduardo, bom dia. O backup noturno falhou por falta de espaço no repositório (retenção acumulada). Já liberei espaço expurgando pontos antigos conforme política e disparei o backup manual, que está em execução. Vou monitorar e te dou retorno ao concluir. Coloco em pendência aguardando a conclusão do job." },
        ],
    },
    {   key => 'AUR-WIFI-PROD',
        title => 'Wi-Fi instável no chão de fábrica',
        queue => 'Field Service', service => 'Rede::Wi-Fi',
        sla => 'SLA Prata', prio => '3 normal', state => 'open',
        owner => 'diego.fontana', cust => 'fernando.rech',
        days_ago => 6, time_units => [ 60 ],
        articles => [
            { from => 'cust', d => 6, h => 13, m => 25,
              s => 'Wi-Fi cai direto na produção',
              b => "O Wi-Fi do galpão de produção cai toda hora. Os coletores de código de barras perdem conexão e atrasam o apontamento. Já está atrapalhando a linha. Fernando Rech — Supervisor de Produção" },
            { from => 'agent', who => 'diego.fontana', d => 6, h => 14, m => 10,
              s => 'RES: Wi-Fi cai direto na produção',
              b => "Fernando, vamos agendar um site survey no galpão para mapear cobertura e interferências. Provável necessidade de mais um ponto de acesso na área das prensas. Combino a visita com você ainda esta semana." },
        ],
    },
    {   key => 'AUR-SENHA-ERP',
        title => 'Reset de senha do ERP',
        queue => 'Suporte::N1', service => 'Acesso e Senhas',
        sla => 'SLA Ouro', prio => '2 low', state => 'closed successful',
        owner => 'bruno.cardoso', cust => 'carla.dorneles',
        days_ago => 12, time_units => [ 10 ],
        articles => [
            { from => 'cust', d => 12, h => 8, m => 5,
              s => 'Esqueci a senha do ERP',
              b => "Bom dia, esqueci a senha do ERP e bloqueou depois de algumas tentativas. Podem resetar? Carla — Financeiro" },
            { from => 'agent', who => 'bruno.cardoso', d => 12, h => 8, m => 22,
              s => 'RES: Esqueci a senha do ERP',
              b => "Bom dia, Carla. Senha resetada e desbloqueada. Enviei a senha provisória no seu WhatsApp corporativo — o sistema vai pedir a troca no primeiro acesso. Pode confirmar que entrou?" },
            { from => 'cust', d => 12, h => 8, m => 40,
              s => 'RES: Esqueci a senha do ERP',
              b => "Entrei normalmente, obrigada!" },
            { from => 'agent', who => 'bruno.cardoso', d => 12, h => 8, m => 45,
              s => 'RES: Esqueci a senha do ERP',
              b => "Perfeito, Carla. Encerro o chamado. Abraço!" },
        ],
    },
    {   key => 'AUR-TELA-AZUL',
        title => 'Computador da recepção com tela azul recorrente',
        queue => 'Suporte::N1', service => 'Hardware',
        sla => 'SLA Prata', prio => '3 normal', state => 'pending reminder',
        owner => 'patricia.menezes', cust => 'mariana.bianchi',
        days_ago => 5, pending_days => 2, time_units => [ 30 ],
        articles => [
            { from => 'cust', d => 5, h => 11, m => 0,
              s => 'PC da recepção dá tela azul',
              b => "O computador da recepção está dando tela azul várias vezes ao dia e reiniciando sozinho. Já perdemos trabalho por causa disso. Mariana" },
            { from => 'agent', who => 'patricia.menezes', d => 5, h => 11, m => 30,
              s => 'RES: PC da recepção dá tela azul',
              b => "Oi, Mariana. Acessei remotamente e coletei os logs. Os despejos apontam falha de memória RAM. Vamos agendar a troca do pente de memória com o time de campo. Coloco em pendência aguardando o agendamento da visita." },
        ],
    },
    {   key => 'AUR-M365-LICENCA',
        title => 'Solicitação de licença Microsoft 365 adicional',
        queue => 'Financeiro', service => 'Microsoft 365',
        sla => 'SLA Prata', prio => '2 low', state => 'open',
        owner => 'william', cust => 'eduardo.salvi',
        days_ago => 8, time_units => [ 15 ],
        articles => [
            { from => 'cust', d => 8, h => 15, m => 0,
              s => 'Precisamos de mais 3 licenças M365',
              b => "Olá, com a contratação de novos colaboradores vamos precisar de mais 3 licenças Microsoft 365 Business Standard. Podem providenciar e incluir na próxima fatura? Eduardo Salvi" },
            { from => 'agent', who => 'william', d => 8, h => 16, m => 20,
              s => 'RES: Precisamos de mais 3 licenças M365',
              b => "Eduardo, recebido. Vou provisionar as 3 licenças Business Standard e incluir o ajuste proporcional na fatura do mês. Encaminho a confirmação e o aditivo de quantidade para o setor financeiro de vocês. Mantenho o chamado aberto até a confirmação do faturamento." },
        ],
    },
    {   key => 'AUR-SHARE-LENTO',
        title => 'Acesso lento à pasta compartilhada de Engenharia',
        queue => 'Suporte::N2', service => 'Infraestrutura::Servidores',
        sla => 'SLA Ouro', prio => '3 normal', state => 'closed successful',
        owner => 'rafael.tavares', cust => 'fernando.rech',
        days_ago => 24, time_units => [ 40, 25 ],
        articles => [
            { from => 'cust', d => 24, h => 9, m => 30,
              s => 'Pasta de Engenharia muito lenta para abrir',
              b => "Os arquivos da pasta de Engenharia (projetos dos móveis) estão demorando muito para abrir, às vezes mais de um minuto. Atrapalha a produção. Fernando Rech" },
            { from => 'agent', who => 'rafael.tavares', d => 24, h => 10, m => 15,
              s => 'RES: Pasta de Engenharia muito lenta',
              b => "Fernando, identificamos alta latência de disco no servidor de arquivos no horário de pico. Vamos mover o volume de Engenharia para o disco SSD e revisar a indexação. Aviso quando aplicar (fora do horário comercial)." },
            { from => 'agent', who => 'rafael.tavares', d => 22, h => 19, m => 0,
              internal => 1, s => 'Nota interna — janela',
              b => "Migração do volume ENG para SSD executada às 19h. Tempo de abertura caiu de ~70s para ~3s em teste. Monitorar por 48h." },
            { from => 'agent', who => 'rafael.tavares', d => 21, h => 9, m => 0,
              s => 'RES: Pasta de Engenharia muito lenta',
              b => "Fernando, aplicamos a melhoria (volume em SSD). Os tempos de abertura normalizaram. Pode validar com a equipe? Vou encerrar o chamado; reabrimos se persistir." },
        ],
    },
    {   key => 'AUR-PHISHING',
        title => 'E-mail suspeito recebido — possível phishing',
        queue => 'Suporte::N2', service => 'Microsoft 365::E-mail (Exchange)',
        sla => 'SLA Ouro', prio => '4 high', state => 'closed successful',
        owner => 'rafael.tavares', cust => 'juliana.peruzzo',
        days_ago => 19, time_units => [ 30 ],
        articles => [
            { from => 'cust', d => 19, h => 14, m => 5,
              s => 'Recebi um e-mail estranho pedindo dados',
              b => "Recebi um e-mail dizendo que minha conta seria bloqueada e pedindo para clicar em um link e confirmar a senha. Achei suspeito e não cliquei. Encaminho para vocês verificarem. Juliana — RH" },
            { from => 'agent', who => 'rafael.tavares', d => 19, h => 14, m => 40,
              s => 'RES: E-mail suspeito',
              b => "Juliana, você agiu certíssimo em não clicar. É de fato uma tentativa de phishing. Já bloqueamos o remetente e o domínio no filtro de e-mail e fizemos uma varredura na sua caixa (nada comprometido). Vamos enviar um alerta de conscientização para toda a empresa. Obrigado por reportar!" },
            { from => 'agent', who => 'rafael.tavares', d => 19, h => 15, m => 0,
              internal => 1, s => 'Ação de segurança',
              b => "Remetente e domínio bloqueados no Exchange Online Protection. Sem indício de comprometimento. Sugerido treinamento anti-phishing trimestral — registrar no plano do contrato." },
        ],
    },
    {   key => 'AUR-NOVO-NOTE',
        title => 'Solicitação de novo notebook para gerência',
        queue => 'Financeiro', service => 'Hardware',
        sla => 'SLA Bronze', prio => '2 low', state => 'new',
        owner => 'william', cust => 'eduardo.salvi',
        days_ago => 1, time_units => [],
        articles => [
            { from => 'cust', d => 1, h => 16, m => 30,
              s => 'Orçamento de notebook para a gerência',
              b => "Boa tarde, precisamos de um notebook novo para a gerência de produção (uso de planilhas pesadas e ERP). Podem enviar um orçamento com 2 opções? Eduardo Salvi" },
        ],
    },
    {   key => 'AUR-TELEFONE-IP',
        title => 'Ramal IP do comercial sem áudio',
        queue => 'Suporte::N1', service => 'Rede',
        sla => 'SLA Prata', prio => '3 normal', state => 'new',
        owner => 'bruno.cardoso', cust => 'mariana.bianchi',
        days_ago => 1, time_units => [],
        articles => [
            { from => 'cust', d => 1, h => 9, m => 10,
              s => 'Telefone do comercial não tem áudio',
              b => "O ramal IP da mesa do comercial conecta a ligação mas fica sem áudio (não ouvimos e não nos ouvem). Já reiniciamos o aparelho. Mariana" },
        ],
    },
    {   key => 'AUR-OUTLOOK-TRAVA',
        title => 'Outlook travando ao anexar arquivos grandes',
        queue => 'Suporte::N1', service => 'Microsoft 365',
        sla => 'SLA Prata', prio => '2 low', state => 'open',
        owner => 'patricia.menezes', cust => 'carla.dorneles',
        days_ago => 3, time_units => [ 20 ],
        articles => [
            { from => 'cust', d => 3, h => 10, m => 45,
              s => 'Outlook trava ao anexar PDF grande',
              b => "Quando tento anexar os PDFs de notas (uns 15MB) o Outlook congela e fecha sozinho. Preciso enviar para a contabilidade. Carla — Financeiro" },
            { from => 'agent', who => 'patricia.menezes', d => 3, h => 11, m => 20,
              s => 'RES: Outlook trava ao anexar PDF grande',
              b => "Carla, o anexo está acima do limite recomendado e o perfil do Outlook está com o arquivo de dados grande. Vou compactar o perfil e te mostrar como enviar arquivos grandes via OneDrive (link), que é mais seguro e rápido. Agendo um remoto rápido hoje à tarde." },
        ],
    },
    {   key => 'AUR-SERVIDOR-LENTO',
        title => 'Servidor de ERP lento no fechamento do mês',
        queue => 'Suporte::N2', service => 'Infraestrutura::Servidores',
        sla => 'SLA Ouro', prio => '4 high', state => 'closed successful',
        owner => 'rafael.tavares', cust => 'eduardo.salvi',
        days_ago => 29, time_units => [ 50, 30 ],
        articles => [
            { from => 'cust', d => 29, h => 8, m => 30,
              s => 'ERP travando no fechamento mensal',
              b => "No fechamento do mês o ERP fica muito lento, relatórios demoram demais e às vezes dá timeout. Acontece todo fim de mês. Podem analisar a fundo? Eduardo Salvi" },
            { from => 'agent', who => 'rafael.tavares', d => 29, h => 9, m => 40,
              s => 'RES: ERP travando no fechamento mensal',
              b => "Eduardo, vamos investigar com calma: coleta de métricas do servidor de banco, análise das queries mais pesadas dos relatórios e revisão de índices. Abro acompanhamento e te dou um diagnóstico estruturado." },
            { from => 'agent', who => 'rafael.tavares', d => 26, h => 18, m => 0,
              internal => 1, s => 'Diagnóstico técnico',
              b => "Gargalo: relatórios de fechamento sem índice adequado + estatísticas desatualizadas no SQL. Aplicado: criação de 3 índices, REINDEX e job de atualização de estatísticas semanal. Tempo do relatório principal caiu de 8min para 40s." },
            { from => 'agent', who => 'rafael.tavares', d => 25, h => 9, m => 30,
              s => 'RES: ERP travando no fechamento mensal',
              b => "Eduardo, aplicamos otimizações no banco do ERP (índices + manutenção de estatísticas). Em teste, o relatório crítico de fechamento caiu de 8 minutos para menos de 1. Acompanhem o próximo fechamento e nos avisem. Encerro o chamado com o plano de manutenção preventiva ativado." },
        ],
    },
    {   key => 'AUR-IMPRESSORA-ETIQ',
        title => 'Impressora de etiquetas da expedição não imprime',
        queue => 'Field Service', service => 'Hardware::Impressoras',
        sla => 'SLA Prata', prio => '4 high', state => 'pending reminder',
        owner => 'diego.fontana', cust => 'fernando.rech',
        days_ago => 3, pending_days => 1, time_units => [ 25 ],
        articles => [
            { from => 'cust', d => 3, h => 8, m => 0,
              s => 'Impressora de etiquetas parou na expedição',
              b => "A impressora térmica de etiquetas da expedição parou de imprimir — sai tudo em branco. Estamos sem etiquetar os volumes para despacho. Urgente. Fernando Rech" },
            { from => 'agent', who => 'diego.fontana', d => 3, h => 8, m => 35,
              s => 'RES: Impressora de etiquetas parou',
              b => "Fernando, etiqueta térmica saindo em branco geralmente é cabeçote sujo ou ribbon/mídia incorreta. Oriento limpeza do cabeçote pelo telefone agora e já agendo visita com peça de reposição (cabeçote) caso não resolva. Coloco em pendência aguardando o teste de vocês." },
        ],
    },
    {   key => 'AUR-CONTA-DESLIG',
        title => 'Desligamento de colaborador — bloquear acessos',
        queue => 'Suporte::N1', service => 'Acesso e Senhas',
        sla => 'SLA Ouro', prio => '4 high', state => 'closed successful',
        owner => 'patricia.menezes', cust => 'juliana.peruzzo',
        days_ago => 9, time_units => [ 15 ],
        articles => [
            { from => 'cust', d => 9, h => 17, m => 0,
              s => 'Bloquear acessos — desligamento hoje',
              b => "Tivemos um desligamento hoje (colaborador do setor de compras, login marcos.lima). Por favor, bloquear imediatamente todos os acessos: rede, e-mail, ERP e VPN. Confidencial. Juliana — RH" },
            { from => 'agent', who => 'patricia.menezes', d => 9, h => 17, m => 20,
              s => 'RES: Bloquear acessos — desligamento',
              b => "Juliana, tratado como prioridade e confidencial. Acessos de rede, e-mail, ERP e VPN do usuário marcos.lima desabilitados imediatamente. Caixa de e-mail convertida em compartilhada e delegada ao gestor por 30 dias conforme política. Encerro o chamado." },
            { from => 'agent', who => 'patricia.menezes', d => 9, h => 17, m => 25,
              internal => 1, s => 'Offboarding executado',
              b => "Offboarding completo: AD desabilitado, sessões revogadas, VPN removida, ERP inativado, mailbox→shared (delegação gestor 30d). Sem pendências." },
        ],
    },
);

# resolve estado-final → estado de criação + transição
my %CLOSED = map { $_ => 1 } ( 'closed successful', 'closed unsuccessful' );

for my $t (@TICKETS) {
    # idempotência: procura ticket com Title exatamente igual
    my @found = $TicketObject->TicketSearch(
        Result => 'ARRAY', Title => $t->{title},
        CustomerID => $COMPANY->{CustomerID}, UserID => $ROOT, Limit => 1,
    );
    if (@found) {
        say2 "= ticket '$t->{title}' já existe (#$found[0])";
        next;
    }

    my $owner_id = $AGENT_ID{ $t->{owner} } or die "owner $t->{owner}?";
    my $create_ts = ts_back( $t->{days_ago},
        $t->{articles}[0]{h}, $t->{articles}[0]{m} );

    my $TID = $TicketObject->TicketCreate(
        Title        => $t->{title},
        QueueID      => $QUEUE_ID{ $t->{queue} },
        Lock         => 'unlock',
        PriorityID   => do { my %p = reverse $Kernel::OM->Get('Kernel::System::Priority')->PriorityList(); $p{ $t->{prio} } },
        State        => 'new',
        CustomerID   => $COMPANY->{CustomerID},
        CustomerUser => do {
            my %cu = $CUObject->CustomerUserDataGet( User => $t->{cust} );
            $cu{UserLogin} || $cu{UserEmail};
        },
        OwnerID      => $owner_id,
        ResponsibleID=> $owner_id,
        ServiceID    => $SVC_ID{ $t->{service} },
        SLAID        => $SLA_ID{ $t->{sla} },
        UserID       => $ROOT,
    );
    die "FALHA TicketCreate '$t->{title}'\n" unless $TID;

    # back-date created
    $DBObject->Do(
        SQL  => 'UPDATE ticket SET create_time = ?, change_time = ? WHERE id = ?',
        Bind => [ \$create_ts, \$create_ts, \$TID ],
    );

    # artigos
    my $backend = $ArticleObject->BackendForChannel( ChannelName => 'Internal' );
    my $first = 1;
    my @agent_art_ids;
    for my $ar ( @{ $t->{articles} } ) {
        my $is_cust = ( $ar->{from} eq 'cust' );
        my %who;
        if ($is_cust) {
            my %cu = $CUObject->CustomerUserDataGet( User => $t->{cust} );
            %who = (
                IsVisibleForCustomer => 1,
                SenderType => 'customer',
                From => "$cu{UserFirstname} $cu{UserLastname} <$cu{UserEmail}>",
            );
        }
        else {
            my $aid = $AGENT_ID{ $ar->{who} };
            my ($adata) = grep { $_->{login} eq $ar->{who} } @AGENTS;
            %who = (
                IsVisibleForCustomer => ( $ar->{internal} ? 0 : 1 ),
                SenderType => 'agent',
                From => "$adata->{first} $adata->{last} <$adata->{email}>",
            );
        }
        my $art_ts = ts_back( $ar->{d}, $ar->{h}, $ar->{m} );

        my $ArtID = $backend->ArticleCreate(
            TicketID    => $TID,
            SenderType  => $who{SenderType},
            IsVisibleForCustomer => $who{IsVisibleForCustomer},
            From        => $who{From},
            To          => $is_cust ? 'Suporte Gerti <suporte@gerti.com.br>' : undef,
            Subject     => $ar->{s},
            Body        => $ar->{b},
            Charset     => 'utf-8',
            MimeType    => 'text/plain',
            HistoryType => $first ? 'NewTicket' : ( $is_cust ? 'FollowUp' : 'AddNote' ),
            HistoryComment => 'Seed demo',
            UserID      => $is_cust ? $ROOT : ( $AGENT_ID{ $ar->{who} } || $ROOT ),
        );
        if ($ArtID) {
            $DBObject->Do(
                SQL => 'UPDATE article SET create_time = ?, change_time = ? WHERE id = ?',
                Bind => [ \$art_ts, \$art_ts, \$ArtID ],
            );
            push @agent_art_ids, $ArtID if !$is_cust;
        }
        $first = 0;
    }

    # time accounting — lançado contra os artigos do agente (apontamento real)
    if ( $t->{time_units} && @{ $t->{time_units} } && @agent_art_ids ) {
        my $i = 0;
        for my $tu ( @{ $t->{time_units} } ) {
            my $art_for_time = $agent_art_ids[ $i % scalar @agent_art_ids ];
            $TicketObject->TicketAccountTime(
                TicketID => $TID, ArticleID => $art_for_time,
                TimeUnit => $tu, UserID => $owner_id,
            );
            $i++;
        }
    }

    # transição de estado para o estado-alvo
    my $target = $t->{state};
    if ( $target ne 'new' ) {
        $TicketObject->TicketStateSet(
            TicketID => $TID, State => $target, UserID => $owner_id,
        );
        # pending: define pending time
        if ( $target =~ /^pending/ ) {
            my $pdays = $t->{pending_days} || 1;
            my $pend = $TimeObject->SystemTime() + ( $pdays * 86400 );
            $TicketObject->TicketPendingTimeSet(
                TicketID => $TID, UserID => $owner_id,
                String => $TimeObject->SystemTime2TimeStamp( SystemTime => $pend ),
            );
        }
        # closed: back-date close to last article day
        if ( $CLOSED{$target} ) {
            my $last = $t->{articles}[-1];
            my $close_ts = ts_back( $last->{d}, $last->{h}, ($last->{m}||0)+5 );
            $DBObject->Do(
                SQL => 'UPDATE ticket SET change_time = ? WHERE id = ?',
                Bind => [ \$close_ts, \$TID ],
            );
        }
    }
    say2 "+ ticket #$TID '$t->{title}' [$target / $t->{queue}]";
    note('tickets_created');
}

# reconstrói índices p/ dashboards
$TicketObject->TicketAcceleratorRebuild() if $TicketObject->can('TicketAcceleratorRebuild');

# ─────────────────────────────────────────────────────────────────────────────
# RESUMO
# ─────────────────────────────────────────────────────────────────────────────
print "\n=== RESUMO DA EXECUÇÃO ===\n";
for my $k (qw(roles_created agents_created companies_created customers_created
              queues_created services_created slas_created tickets_created)) {
    printf "  %-22s %d\n", $k, ( $REPORT{$k} || 0 );
}
print "\nSeed concluído. Reexecutar é seguro (idempotente).\n\n";
exit 0;
