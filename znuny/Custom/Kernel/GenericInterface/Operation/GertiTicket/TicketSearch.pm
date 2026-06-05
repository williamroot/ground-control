# znuny/Custom/Kernel/GenericInterface/Operation/GertiTicket/TicketSearch.pm
# Lista tickets do cliente. scope "own" => CustomerUserID; "company" => CustomerID.
package Kernel::GenericInterface::Operation::GertiTicket::TicketSearch;

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
        ErrorCode => 'TicketSearch.MissingParameter', ErrorMessage => 'empty request!',
    ) if !IsHashRefWithData( $Param{Data} );
    my $TokenError = $Self->_CheckAccessToken( Data => $Param{Data} );
    return $TokenError if $TokenError;

    my $D = $Param{Data};
    my $Scope = $D->{Scope} || 'own';
    my $TicketObject = $Kernel::OM->Get('Kernel::System::Ticket');

    my %Search = ( Result => 'ARRAY', Limit => 200, UserID => 1, OrderBy => 'Down', SortBy => 'Created' );
    if ( $Scope eq 'company' && IsStringWithData( $D->{CustomerID} ) ) {
        $Search{CustomerID} = $D->{CustomerID};
    }
    else {
        $Search{CustomerUserLogin} = $D->{CustomerUser};
    }
    my @TicketIDs = $TicketObject->TicketSearch(%Search);

    my $DFObject  = $Kernel::OM->Get('Kernel::System::DynamicField');
    my $DFConfig  = $DFObject->DynamicFieldGet( Name => 'GertiContractId' );
    my $DFBackend = $Kernel::OM->Get('Kernel::System::DynamicField::Backend');

    my @Tickets;
    for my $ID (@TicketIDs) {
        my %T = $TicketObject->TicketGet( TicketID => $ID, DynamicFields => 1, UserID => 1 );
        next if !%T;
        my $Contract = IsHashRefWithData($DFConfig)
            ? $DFBackend->ValueGet( DynamicFieldConfig => $DFConfig, ObjectID => $ID )
            : undef;
        push @Tickets, {
            TicketID     => $ID,
            TicketNumber => $T{TicketNumber},
            Title        => $T{Title},
            State        => $T{State},
            Created      => $T{Created},
            ContractId   => $Contract,
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
