# znuny/Custom/Kernel/GenericInterface/Operation/GertiAdmin/AdminAgentSet.pm
# --
# Gerti — custom GI operation (Spec #4, Bloco C). WRITE: create OR update a
# Znuny agent (Kernel::System::User). Same "Set" shape as
# CustomerUser/SetPassword.pm and GertiTicket/ConfigItemUpsert.pm — presence
# of TargetUserID decides create vs update, one Perl module, one route.
#
# Guardrails (not negotiable):
#   - Allowlist of writable fields. Anything else in the request => explicit
#     error, never silently dropped (an operator who thinks a field saved when
#     it didn't is worse than one who gets an error).
#   - Setting a password is a SEPARATE, EXPLICIT operation — never a side
#     effect of this cadastro update. Any Password/UserPw/PW-shaped field in
#     the request is REJECTED outright (this op does not exist yet in this
#     spec's scope; native UserAdd auto-generates an unusable random one).
#   - Update is a partial patch from the caller's point of view: fields not
#     sent keep their current value (native UserUpdate() is a full replace,
#     so we merge onto the current GetUserData() first).
# Upgrade-safe Custom/ overlay.
# --
package Kernel::GenericInterface::Operation::GertiAdmin::AdminAgentSet;

use strict;
use warnings;

use Kernel::System::VariableCheck qw(IsHashRefWithData IsStringWithData);

use parent qw(Kernel::GenericInterface::Operation::Common);

our $ObjectManagerDisabled = 1;

# Allowlist of cadastro fields this op will ever write. UserPw/Password are
# DELIBERATELY absent — see module header.
my @WRITABLE_FIELDS = qw(UserTitle UserFirstname UserLastname UserLogin UserEmail UserMobile ValidID);

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
        ErrorCode => 'AdminAgentSet.MissingParameter', ErrorMessage => 'empty request!',
    ) if !IsHashRefWithData( $Param{Data} );
    my $TokenError = $Self->_CheckAccessToken( Data => $Param{Data} );
    return $TokenError if $TokenError;

    my $D = $Param{Data};
    for my $Needed (qw(AgentLogin)) {
        return $Self->ReturnError(
            ErrorCode => 'AdminAgentSet.MissingParameter', ErrorMessage => "$Needed missing!",
        ) if !IsStringWithData( $D->{$Needed} );
    }

    my $UserObject = $Kernel::OM->Get('Kernel::System::User');
    my $ActorUserID = $UserObject->UserLookup( UserLogin => $D->{AgentLogin}, Silent => 1 );
    if ( !$ActorUserID ) {
        return $Self->ReturnError(
            ErrorCode => 'AdminAgentSet.UnknownAgent', ErrorMessage => 'agent login not found',
        );
    }

    # ── Guardrail: password is never a side effect of this op. Reject outright. ──
    for my $Key ( keys %{$D} ) {
        if ( $Key =~ m{pw|password}xmsi ) {
            return $Self->ReturnError(
                ErrorCode    => 'AdminAgentSet.PasswordNotAllowed',
                ErrorMessage => "field '$Key' is rejected: setting a password is a separate, explicit operation.",
            );
        }
    }

    # ── Guardrail: field allowlist. Anything unknown => explicit error. ──
    my %Allowed = map { $_ => 1 } ( @WRITABLE_FIELDS, qw(AccessToken AgentLogin TargetUserID) );
    for my $Key ( keys %{$D} ) {
        if ( !$Allowed{$Key} ) {
            return $Self->ReturnError(
                ErrorCode    => 'AdminAgentSet.UnknownField',
                ErrorMessage => "field '$Key' is not writable on an agent.",
            );
        }
    }

    my $Action;
    my $TargetUserID;

    if ( IsStringWithData( $D->{TargetUserID} ) ) {

        # ── UPDATE: merge onto current data (native UserUpdate() is a full replace). ──
        $TargetUserID = $D->{TargetUserID};
        my %Current = $UserObject->GetUserData( UserID => $TargetUserID, NoOutOfOffice => 1 );
        if ( !%Current ) {
            return $Self->ReturnError(
                ErrorCode => 'AdminAgentSet.NotFound', ErrorMessage => 'agent not found',
            );
        }

        my %UpdateParam;
        for my $Field (@WRITABLE_FIELDS) {
            $UpdateParam{$Field} = exists $D->{$Field} ? $D->{$Field} : $Current{$Field};
        }
        for my $Needed (qw(UserFirstname UserLastname UserLogin ValidID)) {
            return $Self->ReturnError(
                ErrorCode => 'AdminAgentSet.MissingParameter', ErrorMessage => "$Needed missing!",
            ) if !IsStringWithData( $UpdateParam{$Needed} );
        }

        my $OK = $UserObject->UserUpdate(
            %UpdateParam,
            UserID       => $TargetUserID,
            ChangeUserID => $ActorUserID,
        );
        if ( !$OK ) {
            my $Msg = $Kernel::OM->Get('Kernel::System::Log')->GetLogEntry( Type => 'error', What => 'Message' )
                || 'could not update the agent';
            return $Self->ReturnError(
                ErrorCode => 'AdminAgentSet.WriteError', ErrorMessage => $Msg,
            );
        }
        $Action = 'updated';
    }
    else {

        # ── CREATE. ──
        for my $Needed (qw(UserFirstname UserLastname UserLogin UserEmail ValidID)) {
            return $Self->ReturnError(
                ErrorCode => 'AdminAgentSet.MissingParameter', ErrorMessage => "$Needed missing!",
            ) if !IsStringWithData( $D->{$Needed} );
        }

        $TargetUserID = $UserObject->UserAdd(
            ( map { $_ => $D->{$_} } grep { defined $D->{$_} } @WRITABLE_FIELDS ),
            ChangeUserID => $ActorUserID,
        );
        if ( !$TargetUserID ) {
            my $Msg = $Kernel::OM->Get('Kernel::System::Log')->GetLogEntry( Type => 'error', What => 'Message' )
                || 'could not create the agent';
            return $Self->ReturnError(
                ErrorCode => 'AdminAgentSet.WriteError', ErrorMessage => $Msg,
            );
        }
        $Action = 'created';
    }

    my %Saved = $UserObject->GetUserData( UserID => $TargetUserID, NoOutOfOffice => 1 );
    delete @Saved{ grep { /pw/i } keys %Saved };

    return {
        Success => 1,
        Data    => {
            Action => $Action,
            Agent  => {
                UserID        => $Saved{UserID},
                UserLogin     => $Saved{UserLogin},
                UserTitle     => $Saved{UserTitle},
                UserFirstname => $Saved{UserFirstname},
                UserLastname  => $Saved{UserLastname},
                UserEmail     => $Saved{UserEmail},
                UserMobile    => $Saved{UserMobile},
                ValidID       => $Saved{ValidID},
            },
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
