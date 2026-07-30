# znuny/Custom/Kernel/GenericInterface/Operation/GertiAdmin/AdminAgentSetPassword.pm
# --
# Gerti — custom GI operation (Spec #4, Bloco C — correção pós-revisão
# adversarial). Sets an existing Znuny agent's password. SEPARATE, EXPLICIT
# operation from AdminAgentSet.pm — the spec forbids a password change ever
# being a side effect of a cadastro update. Same wrapping pattern as
# CustomerUser/SetPassword.pm (Kernel::System::User->SetPassword, confirmed
# signature: SetPassword(UserLogin => ..., PW => ...) — verified against
# Kernel/System/User.pm ~line 841 in the 7.2.3 image).
#
# Guardrails (not negotiable):
#   - AgentLogin (the acting admin) is required and resolved to a real
#     UserID — same "attribution" pattern as every other GertiAdmin write.
#   - TargetUserID (whose password is being set) is required and must
#     resolve to a real agent.
#   - AccessToken fail-closed (shared GertiAdmin secret).
#   - The password is NEVER echoed back in the response, and NEVER logged —
#     not even the fact that a specific value was used. Only UserID/UserLogin
#     of the target come back, so the caller can audit "who changed X's
#     password", never the value.
# Upgrade-safe Custom/ overlay.
# --
package Kernel::GenericInterface::Operation::GertiAdmin::AdminAgentSetPassword;

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
        ErrorCode => 'AdminAgentSetPassword.MissingParameter', ErrorMessage => 'empty request!',
    ) if !IsHashRefWithData( $Param{Data} );
    my $TokenError = $Self->_CheckAccessToken( Data => $Param{Data} );
    return $TokenError if $TokenError;

    my $D = $Param{Data};
    for my $Needed (qw(AgentLogin TargetUserID NewPassword)) {
        return $Self->ReturnError(
            ErrorCode => 'AdminAgentSetPassword.MissingParameter', ErrorMessage => "$Needed missing!",
        ) if !IsStringWithData( $D->{$Needed} );
    }

    # Light shape guard, mirroring the sidecar's Field(min_length=8) — belt
    # and suspenders, not the source of truth for password policy.
    if ( length( $D->{NewPassword} ) < 8 ) {
        return $Self->ReturnError(
            ErrorCode    => 'AdminAgentSetPassword.WeakPassword',
            ErrorMessage => 'NewPassword must be at least 8 characters long.',
        );
    }

    my $UserObject = $Kernel::OM->Get('Kernel::System::User');

    # Resolve the acting admin (author) — administrative write without an
    # identified author does not happen.
    my $ActorUserID = $UserObject->UserLookup( UserLogin => $D->{AgentLogin}, Silent => 1 );
    if ( !$ActorUserID ) {
        return $Self->ReturnError(
            ErrorCode => 'AdminAgentSetPassword.UnknownAgent', ErrorMessage => 'agent login not found',
        );
    }

    # Resolve the target agent — TargetUserID travels as a UserID, SetPassword()
    # wants the UserLogin, so we look it up via GetUserData (same pattern as
    # AdminAgentSet.pm / AdminAgentGet.pm).
    my %Target = $UserObject->GetUserData( UserID => $D->{TargetUserID}, NoOutOfOffice => 1 );
    if ( !%Target ) {
        return $Self->ReturnError(
            ErrorCode => 'AdminAgentSetPassword.NotFound', ErrorMessage => 'agent not found',
        );
    }

    # ── Never let the password reach the log. Do not interpolate $D->{NewPassword}
    #    into any Log()/ReturnError() call below. ──
    my $Success = $UserObject->SetPassword(
        UserLogin => $Target{UserLogin},
        PW        => $D->{NewPassword},
    );

    if ( !$Success ) {
        return $Self->ReturnError(
            ErrorCode    => 'AdminAgentSetPassword.SetError',
            ErrorMessage => 'could not set the password (agent may not exist or the password was rejected).',
        );
    }

    return {
        Success => 1,
        Data    => {
            Success   => 1,
            UserID    => $Target{UserID},
            UserLogin => $Target{UserLogin},
        },
    };
}

sub _CheckAccessToken {
    my ( $Self, %Param ) = @_;
    my $Provided = $Param{Data}->{AccessToken} || '';
    my $Expected = $Kernel::OM->Get('Kernel::Config')->Get('GertiAdmin::AccessToken') || '';
    return $Self->ReturnError( ErrorCode => 'GertiAdmin.AuthFail', ErrorMessage => 'invalid AccessToken.' )
        if !IsStringWithData($Expected) || !IsStringWithData($Provided) || $Provided ne $Expected;
    return;
}

1;
