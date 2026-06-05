# znuny/Custom/Kernel/GenericInterface/Operation/GertiTicket/FormMeta.pm
# Catálogo do formulário: serviços do CustomerUser, prioridades, tipos.
package Kernel::GenericInterface::Operation::GertiTicket::FormMeta;

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
        ErrorCode => 'FormMeta.MissingParameter', ErrorMessage => 'empty request!',
    ) if !IsHashRefWithData( $Param{Data} );
    my $TokenError = $Self->_CheckAccessToken( Data => $Param{Data} );
    return $TokenError if $TokenError;

    my $D = $Param{Data};
    return $Self->ReturnError(
        ErrorCode => 'FormMeta.MissingParameter', ErrorMessage => 'CustomerUser missing!',
    ) if !IsStringWithData( $D->{CustomerUser} );

    # Serviços disponíveis ao cliente (Service::ServiceList do CustomerUser).
    my $ServiceObject = $Kernel::OM->Get('Kernel::System::Service');
    my %ServiceHash   = $ServiceObject->CustomerUserServiceMemberList(
        CustomerUserLogin => $D->{CustomerUser},
        Result            => 'HASH',
        DefaultServices   => 1,
    );
    my @Services = map { { Key => $_, Value => $ServiceHash{$_} } } sort keys %ServiceHash;

    # Prioridades.
    my $PriorityObject = $Kernel::OM->Get('Kernel::System::Priority');
    my %PriorityHash   = $PriorityObject->PriorityList( Valid => 1, UserID => 1 );
    my @Priorities = map { { Key => $_, Value => $PriorityHash{$_} } } sort { $a <=> $b } keys %PriorityHash;

    # Tipos (se Ticket::Type estiver ativo).
    my @Types;
    if ( $Kernel::OM->Get('Kernel::Config')->Get('Ticket::Type') ) {
        my $TypeObject = $Kernel::OM->Get('Kernel::System::Type');
        my %TypeHash   = $TypeObject->TypeList( Valid => 1, UserID => 1 );
        @Types = map { { Key => $_, Value => $TypeHash{$_} } } sort keys %TypeHash;
    }

    return {
        Success => 1,
        Data    => { Services => \@Services, Priorities => \@Priorities, Types => \@Types },
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
