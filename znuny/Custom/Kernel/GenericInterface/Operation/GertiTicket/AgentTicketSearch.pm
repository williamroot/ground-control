# znuny/Custom/Kernel/GenericInterface/Operation/GertiTicket/AgentTicketSearch.pm
# Busca de tickets para o agente (sem escopo de customer). Spec #1J.
package Kernel::GenericInterface::Operation::GertiTicket::AgentTicketSearch;

use strict;
use warnings;
use Kernel::System::VariableCheck qw(IsHashRefWithData IsStringWithData);
use parent qw(Kernel::GenericInterface::Operation::Common);
our $ObjectManagerDisabled = 1;

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
        ErrorCode => 'AgentTicketSearch.MissingParameter', ErrorMessage => 'empty request!',
    ) if !IsHashRefWithData( $Param{Data} );
    my $TokenError = $Self->_CheckAccessToken( Data => $Param{Data} );
    return $TokenError if $TokenError;

    my $D = $Param{Data};
    my $TicketObject = $Kernel::OM->Get('Kernel::System::Ticket');

    my %Search = ( Result => 'ARRAY', Limit => 50, UserID => 1, OrderBy => 'Down', SortBy => 'Age' );
    # Fulltext em número/título; filtro opcional por CustomerID.
    if ( IsStringWithData( $D->{Query} ) ) {
        # Busca por número exato OU título (fulltext do Znuny usa %...%).
        $Search{Title} = '%' . $D->{Query} . '%';
    }
    $Search{CustomerID} = $D->{CustomerID} if IsStringWithData( $D->{CustomerID} );
    $Search{TicketNumber} = $D->{Number} if IsStringWithData( $D->{Number} );

    my @TicketIDs = $TicketObject->TicketSearch(%Search);

    my @Tickets;
    for my $ID (@TicketIDs) {
        my %T = $TicketObject->TicketGet( TicketID => $ID, UserID => 1 );
        next if !%T;
        push @Tickets, {
            TicketID     => $ID,
            TicketNumber => $T{TicketNumber},
            Title        => $T{Title},
            State        => $T{State},
            CustomerID   => $T{CustomerID},
            Owner        => $T{Owner},
            Created      => $T{Created},
        };
    }
    return { Success => 1, Data => { Tickets => \@Tickets } };
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
