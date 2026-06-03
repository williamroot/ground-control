# --
# Gerti — custom Generic Interface operation (Spec #1G-a, ADR D19, Opção A).
# Wraps the native Kernel::System::CustomerUser->SetPassword so the Gerti admin
# sidecar can set a CustomerUser password via GI (Spec #0: writes to Znuny are
# ALWAYS via GI, never direct SQL). Shipped through the upgrade-safe Custom/
# overlay (same mechanism as Custom/Kernel/System/Cache/Redis.pm).
# --
# This software comes with ABSOLUTELY NO WARRANTY.
# --

package Kernel::GenericInterface::Operation::CustomerUser::SetPassword;

use strict;
use warnings;

use Kernel::System::VariableCheck qw(IsHashRefWithData IsStringWithData);

use parent qw(
    Kernel::GenericInterface::Operation::Common
);

our $ObjectManagerDisabled = 1;

=head1 NAME

Kernel::GenericInterface::Operation::CustomerUser::SetPassword
- GenericInterface CustomerUser SetPassword operation backend (Gerti custom).

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

Set the password of an existing CustomerUser.

    my $Result = $OperationObject->Run(
        Data => {
            AccessToken => '...',                    # shared secret (GertiAdmin)
            UserLogin   => 'jdoe',
            Password    => 'plain-text-password',
        },
    );

    $Result = {
        Success => 1,
        Data    => { Success => 1 },
    };

=cut

sub Run {
    my ( $Self, %Param ) = @_;

    if ( !IsHashRefWithData( $Param{Data} ) ) {
        return $Self->ReturnError(
            ErrorCode    => 'SetPassword.MissingParameter',
            ErrorMessage => 'SetPassword: the request is empty!',
        );
    }

    # AccessToken gate (shared secret, validated against Znuny config).
    my $TokenError = $Self->_CheckAccessToken( Data => $Param{Data} );
    return $TokenError if $TokenError;

    for my $Needed (qw(UserLogin Password)) {
        if ( !IsStringWithData( $Param{Data}->{$Needed} ) ) {
            return $Self->ReturnError(
                ErrorCode    => 'SetPassword.MissingParameter',
                ErrorMessage => "SetPassword: $Needed parameter is missing!",
            );
        }
    }

    my $Success = $Kernel::OM->Get('Kernel::System::CustomerUser')->SetPassword(
        UserLogin => $Param{Data}->{UserLogin},
        PW        => $Param{Data}->{Password},
    );

    if ( !$Success ) {
        return $Self->ReturnError(
            ErrorCode    => 'SetPassword.SetError',
            ErrorMessage => 'SetPassword: could not set the password'
                . ' (maybe the user does not exist or the password was rejected).',
        );
    }

    return {
        Success => 1,
        Data    => {
            Success => 1,
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
