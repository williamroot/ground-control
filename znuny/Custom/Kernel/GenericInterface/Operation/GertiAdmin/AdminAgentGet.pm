# znuny/Custom/Kernel/GenericInterface/Operation/GertiAdmin/AdminAgentGet.pm
# --
# Gerti — custom GI operation (Spec #4, Bloco C). Read-only detail of a single
# Znuny agent (Kernel::System::User->GetUserData). Guardrail: UserPw (password
# hash) is NEVER returned — filtered explicitly, in hypothesis alone (this is
# the one rule of this op that is not negotiable).
# Upgrade-safe Custom/ overlay.
# --
package Kernel::GenericInterface::Operation::GertiAdmin::AdminAgentGet;

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
        ErrorCode => 'AdminAgentGet.MissingParameter', ErrorMessage => 'empty request!',
    ) if !IsHashRefWithData( $Param{Data} );
    my $TokenError = $Self->_CheckAccessToken( Data => $Param{Data} );
    return $TokenError if $TokenError;

    my $D = $Param{Data};
    for my $Needed (qw(AgentLogin TargetUserID)) {
        return $Self->ReturnError(
            ErrorCode => 'AdminAgentGet.MissingParameter', ErrorMessage => "$Needed missing!",
        ) if !IsStringWithData( $D->{$Needed} );
    }

    my $UserObject = $Kernel::OM->Get('Kernel::System::User');
    my $UserID     = $UserObject->UserLookup( UserLogin => $D->{AgentLogin}, Silent => 1 );
    if ( !$UserID ) {
        return $Self->ReturnError(
            ErrorCode => 'AdminAgentGet.UnknownAgent', ErrorMessage => 'agent login not found',
        );
    }

    my %Agent = $UserObject->GetUserData( UserID => $D->{TargetUserID}, NoOutOfOffice => 1 );
    if ( !%Agent ) {
        return $Self->ReturnError(
            ErrorCode => 'AdminAgentGet.NotFound', ErrorMessage => 'agent not found',
        );
    }

    # ── Guardrail: NEVER return the password hash (or anything password-shaped). ──
    delete @Agent{ grep { /pw/i } keys %Agent };

    return {
        Success => 1,
        Data    => {
            UserID        => $Agent{UserID},
            UserLogin     => $Agent{UserLogin},
            UserTitle     => $Agent{UserTitle},
            UserFirstname => $Agent{UserFirstname},
            UserLastname  => $Agent{UserLastname},
            UserEmail     => $Agent{UserEmail},
            UserMobile    => $Agent{UserMobile},
            ValidID       => $Agent{ValidID},
            CreateTime    => $Agent{CreateTime},
            ChangeTime    => $Agent{ChangeTime},
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
