# znuny/Custom/Kernel/GenericInterface/Operation/GertiTicket/TicketStats.pm
# --
# Gerti — custom GI operation (Spec #1O). Read-only aggregated ticket counts
# scoped by CustomerID (anti-IDOR: counts ONLY tickets whose CustomerID matches
# the requesting tenant's CustomerCompany — NEVER another tenant's tickets).
# Returns counts by State, by Priority, by day, plus SLA breached/at-risk
# (derived from the escalation fields of TicketGet). Period filtered by the
# native TicketCreateTimeNewerDate/OlderDate of TicketSearch.
# Upgrade-safe Custom/ overlay (same pattern as the other GertiTicket ops).
# --
package Kernel::GenericInterface::Operation::GertiTicket::TicketStats;

use strict;
use warnings;

use Kernel::System::VariableCheck qw(IsHashRefWithData IsStringWithData);

use parent qw(Kernel::GenericInterface::Operation::Common);

our $ObjectManagerDisabled = 1;

# At-risk window: a ticket whose escalation fires within this many seconds is
# flagged SlaAtRisk (here: 2 hours). Already-breached escalations (<= 0) are
# SlaBreached and take precedence.
use constant AT_RISK_WINDOW_SECONDS => 2 * 60 * 60;

# Teto da "listona de chamados" do relatório executivo (T-R18b.2). Um cliente
# com mil chamados no mês não pode virar um payload GI de vários MB nem um PDF
# de cem páginas. Acima do teto a resposta marca `TicketsTruncated` — a
# contagem em `Total` continua exata, é só a lista que é cortada, e quem
# consome precisa poder dizer isso ao operador em vez de mostrar menos.
use constant MAX_TICKETS => 1000;

sub new {
    my ( $Type, %Param ) = @_;
    my $Self = {};
    bless( $Self, $Type );
    for my $Needed (qw(DebuggerObject WebserviceID)) {
        return { Success => 0, ErrorMessage => "Got no $Needed!" } if !$Param{$Needed};
        $Self->{$Needed} = $Param{$Needed};
    }
    return $Self;
}

sub Run {
    my ( $Self, %Param ) = @_;

    return $Self->ReturnError(
        ErrorCode => 'TicketStats.MissingParameter', ErrorMessage => 'empty request!',
    ) if !IsHashRefWithData( $Param{Data} );
    my $TokenError = $Self->_CheckAccessToken( Data => $Param{Data} );
    return $TokenError if $TokenError;

    my $D = $Param{Data};

    # anti-IDOR: CustomerCompany is mandatory and is the ONLY tenant scope.
    return $Self->ReturnError(
        ErrorCode => 'TicketStats.MissingParameter', ErrorMessage => 'CustomerCompany missing!',
    ) if !IsStringWithData( $D->{CustomerCompany} );

    my $TicketObject = $Kernel::OM->Get('Kernel::System::Ticket');

    my %Search = (
        Result     => 'ARRAY',
        Limit      => 5000,
        UserID     => 1,
        CustomerID => $D->{CustomerCompany},    # anti-IDOR scope (exact match)
    );
    if ( IsStringWithData( $D->{Since} ) ) {
        $Search{TicketCreateTimeNewerDate} = $D->{Since};
    }
    if ( IsStringWithData( $D->{Until} ) ) {
        $Search{TicketCreateTimeOlderDate} = $D->{Until};
    }

    my @TicketIDs = $TicketObject->TicketSearch(%Search);

    my %ByState;
    my %ByPriority;
    my %ByDay;
    # T-R18b.1 — as três dimensões de "principais tipos de chamado" saem juntas,
    # de uma passada só. Qual delas vai para o relatório é escolha do sidecar
    # (chave REPORT_TOP_DIMENSION): o `Type` do Znuny costuma ter dois valores e
    # render pouco, o catálogo de serviço costuma ser o que o operador chama de
    # "tipo". Entregar as três agora custa nada e faz a virada ser configuração.
    my %ByType;
    my %ByService;
    my %ByQueue;
    # T-R18b.2 — a "listona de chamados" do fim do relatório. Sai do MESMO loop:
    # o TicketGet já foi pago para as agregações.
    #
    # OPT-IN de propósito (`IncludeTickets`): esta mesma operação alimenta o
    # painel de analytics, que precisa só das contagens. Sem a chave, o painel
    # passaria a arrastar até mil chamados e um TicketAccountedTimeGet por
    # chamado a cada carga — custo que só o relatório tem motivo de pagar.
    my $IncludeTickets = $D->{IncludeTickets} ? 1 : 0;
    my @Tickets;
    my $TicketsTruncated = 0;
    my $SlaBreached = 0;
    my $SlaAtRisk   = 0;
    my $Total       = 0;

    for my $ID (@TicketIDs) {
        my %T = $TicketObject->TicketGet(
            TicketID => $ID,
            UserID   => 1,
            Extended => 1,
        );
        next if !%T;

        # Defensive re-check of the scope (never count another tenant's ticket).
        next if !defined $T{CustomerID} || $T{CustomerID} ne $D->{CustomerCompany};

        $Total++;

        # By state (human state name, e.g. open/closed successful/...).
        my $State = defined $T{State} && $T{State} ne '' ? $T{State} : 'unknown';
        $ByState{$State}++;

        # By priority (e.g. "3 normal").
        my $Priority = defined $T{Priority} && $T{Priority} ne '' ? $T{Priority} : 'unknown';
        $ByPriority{$Priority}++;

        # By day (YYYY-MM-DD from the Created timestamp 'YYYY-MM-DD HH:MM:SS').
        if ( defined $T{Created} && $T{Created} =~ m{^(\d{4}-\d{2}-\d{2})} ) {
            $ByDay{$1}++;
        }

        # Type / Service / Queue. Um chamado sem serviço definido NÃO vira
        # 'unknown' silencioso em ByService: ele fica de fora, senão o relatório
        # anunciaria "o tipo mais frequente é 'não informado'". Type e Queue
        # sempre existem no Znuny, então esses caem em 'unknown' se vierem vazios.
        my $Type = defined $T{Type} && $T{Type} ne '' ? $T{Type} : 'unknown';
        $ByType{$Type}++;
        my $Queue = defined $T{Queue} && $T{Queue} ne '' ? $T{Queue} : 'unknown';
        $ByQueue{$Queue}++;
        if ( defined $T{Service} && $T{Service} ne '' ) {
            $ByService{ $T{Service} }++;
        }

        if ( $IncludeTickets && scalar @Tickets < MAX_TICKETS ) {
            push @Tickets, {
                TicketID     => $T{TicketID},
                TicketNumber => $T{TicketNumber},
                Title        => $T{Title},
                State        => $State,
                Priority     => $Priority,
                Type         => ( defined $T{Type} ? $T{Type} : '' ),
                Service      => ( defined $T{Service} ? $T{Service} : '' ),
                Queue        => ( defined $T{Queue} ? $T{Queue} : '' ),
                Created      => ( defined $T{Created} ? $T{Created} : '' ),
                CustomerUser => ( defined $T{CustomerUserID} ? $T{CustomerUserID} : '' ),
                # Horas lançadas no chamado. Vem do time_accounting do Znuny —
                # NÃO é a mesma conta do faturamento, que exclui glosa aprovada.
                # A lista do relatório mostra o trabalho feito; o bloco de
                # consumo mostra o que foi cobrado. Podem divergir de propósito.
                AccountedTime => ( $TicketObject->TicketAccountedTimeGet( TicketID => $ID ) || 0 ),
            };
        }
        elsif ($IncludeTickets) {
            $TicketsTruncated = 1;
        }

        # SLA: EscalationTime is seconds until the next escalation fires
        # (negative => already breached). Only meaningful for tickets that still
        # have a running escalation (open). closed/resolved tickets typically
        # have EscalationTime == 0 / undef and are ignored.
        my $Esc = $T{EscalationTime};
        if ( defined $Esc && $Esc != 0 ) {
            if ( $Esc < 0 ) {
                $SlaBreached++;
            }
            elsif ( $Esc <= AT_RISK_WINDOW_SECONDS ) {
                $SlaAtRisk++;
            }
        }
    }

    my @ByDay =
        map { { date => $_, count => $ByDay{$_} } }
        sort keys %ByDay;

    return {
        Success => 1,
        Data    => {
            ByState          => \%ByState,
            ByPriority       => \%ByPriority,
            ByDay            => \@ByDay,
            ByType           => \%ByType,
            ByService        => \%ByService,
            ByQueue          => \%ByQueue,
            Tickets          => \@Tickets,
            TicketsTruncated => $TicketsTruncated,
            SlaBreached      => $SlaBreached,
            SlaAtRisk        => $SlaAtRisk,
            Total            => $Total,
        },
    };
}

sub _CheckAccessToken {
    my ( $Self, %Param ) = @_;
    my $Provided = $Param{Data}->{AccessToken} || '';
    my $Expected = $Kernel::OM->Get('Kernel::Config')->Get('GertiAdmin::AccessToken') || '';
    return $Self->ReturnError( ErrorCode => 'GertiTicket.AuthFail', ErrorMessage => 'invalid AccessToken.' )
        if !IsStringWithData($Expected) || !IsStringWithData($Provided) || $Provided ne $Expected;
    return;
}

1;
