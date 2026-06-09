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
            ByState     => \%ByState,
            ByPriority  => \%ByPriority,
            ByDay       => \@ByDay,
            SlaBreached => $SlaBreached,
            SlaAtRisk   => $SlaAtRisk,
            Total       => $Total,
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
