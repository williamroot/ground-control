# --
# Gerti — custom Generic Interface operation (Spec #1G-a, ADR D19, Opção A).
# Wraps the native Kernel::System::CustomerUser->CustomerUserAdd so the Gerti
# admin sidecar can create a CustomerUser via GI (Spec #0: writes to Znuny are
# ALWAYS via GI, never direct SQL). Shipped through the upgrade-safe Custom/
# overlay (same mechanism as Custom/Kernel/System/Cache/Redis.pm).
# --
# This software comes with ABSOLUTELY NO WARRANTY.
# --

package Kernel::GenericInterface::Operation::CustomerUser::CustomerUserAdd;

use strict;
use warnings;

use Kernel::System::VariableCheck qw(IsHashRefWithData IsStringWithData);

use parent qw(
    Kernel::GenericInterface::Operation::Common
);

our $ObjectManagerDisabled = 1;

=head1 NAME

Kernel::GenericInterface::Operation::CustomerUser::CustomerUserAdd
- GenericInterface CustomerUser Add operation backend (Gerti custom).

=head2 new()

usually created via Kernel::GenericInterface::Operation->new();

=cut

sub new {
    my ( $Type, %Param ) = @_;

    my $Self = {};
    bless( $Self, $Type );

    for my $Needed (qw(DebuggerObject WebserviceID)) {
        if ( !$Param{$Needed} ) {
            return {
                Success      => 0,
                ErrorMessage => "Got no $Needed!",
            };
        }
        $Self->{$Needed} = $Param{$Needed};
    }

    return $Self;
}

=head2 Run()

Create a CustomerUser.

    my $Result = $OperationObject->Run(
        Data => {
            AccessToken    => '...',                 # shared secret (GertiAdmin)
            UserLogin      => 'jdoe',
            UserEmail      => 'jdoe@acme.example',
            UserFirstname  => 'John',
            UserLastname   => 'Doe',
            UserCustomerID => 'acme',
            ValidID        => 1,                      # optional, defaults to 1
        },
    );

    $Result = {
        Success => 1,
        Data    => { UserLogin => 'jdoe' },
    };

=cut

sub Run {
    my ( $Self, %Param ) = @_;

    if ( !IsHashRefWithData( $Param{Data} ) ) {
        return $Self->ReturnError(
            ErrorCode    => 'CustomerUserAdd.MissingParameter',
            ErrorMessage => 'CustomerUserAdd: the request is empty!',
        );
    }

    # AccessToken gate (shared secret, validated against Znuny config).
    my $TokenError = $Self->_CheckAccessToken( Data => $Param{Data} );
    return $TokenError if $TokenError;

    for my $Needed (
        qw(UserLogin UserEmail UserFirstname UserLastname UserCustomerID)
        )
    {
        if ( !IsStringWithData( $Param{Data}->{$Needed} ) ) {
            return $Self->ReturnError(
                ErrorCode    => 'CustomerUserAdd.MissingParameter',
                ErrorMessage => "CustomerUserAdd: $Needed parameter is missing!",
            );
        }
    }

    my $ValidID = $Param{Data}->{ValidID};
    $ValidID = 1 if !defined $ValidID || $ValidID eq '';

    my $UserLogin = $Kernel::OM->Get('Kernel::System::CustomerUser')->CustomerUserAdd(
        Source         => 'CustomerUser',
        UserLogin      => $Param{Data}->{UserLogin},
        UserEmail      => $Param{Data}->{UserEmail},
        UserFirstname  => $Param{Data}->{UserFirstname},
        UserLastname   => $Param{Data}->{UserLastname},
        UserCustomerID => $Param{Data}->{UserCustomerID},
        ValidID        => $ValidID,
        UserID         => 1,                           # system agent (audit field)
    );

    if ( !$UserLogin ) {
        return $Self->ReturnError(
            ErrorCode    => 'CustomerUserAdd.AddError',
            ErrorMessage => 'CustomerUserAdd: could not create the customer user'
                . ' (maybe the login already exists or the input was rejected).',
        );
    }

    return {
        Success => 1,
        Data    => {
            UserLogin => $UserLogin,
        },
    };
}

=head2 _CheckAccessToken()

Validates the shared AccessToken against the configured expected value
(C<GertiAdmin::AccessToken> in Znuny config). Fails closed.

Returns a ReturnError hashref on failure, or undef on success.

=cut

sub _CheckAccessToken {
    my ( $Self, %Param ) = @_;

    my $Provided = $Param{Data}->{AccessToken} || '';
    my $Expected = $Kernel::OM->Get('Kernel::Config')->Get('GertiAdmin::AccessToken') || '';

    if ( !IsStringWithData($Expected) || !IsStringWithData($Provided) || $Provided ne $Expected ) {
        return $Self->ReturnError(
            ErrorCode    => 'GertiAdmin.AuthFail',
            ErrorMessage => 'GertiAdmin: invalid or missing AccessToken.',
        );
    }

    return;
}

1;
