# znuny/Custom/Kernel/GenericInterface/Operation/GertiAdmin/AdminAgentGroupSet.pm
# --
# Gerti — custom GI operation (Spec #4, Bloco C). WRITE: sets an agent's full
# group membership (Kernel::System::Group->PermissionGroupUserAdd, 'rw'
# level — Znuny's own semantics treat 'rw' as a superset of every other
# permission type on that group, see Group.pm PermissionGroupUserAdd). The
# request carries the DESIRED full set of GroupIDs; this op diffs it against
# the current membership and only writes the delta.
#
# This is the most dangerous op in Spec #4:
#   - Anti-lockout: an agent can NEVER remove itself from the 'admin' group
#     through this op. Refused outright, nothing is written.
#   - Returns BEFORE and AFTER membership (both re-read from Znuny after the
#     write, not just echoed back) so the sidecar can audit both sides of the
#     change, per the plan.
# Upgrade-safe Custom/ overlay.
# --
package Kernel::GenericInterface::Operation::GertiAdmin::AdminAgentGroupSet;

use strict;
use warnings;

use Kernel::System::VariableCheck qw(IsHashRefWithData IsStringWithData IsArrayRefWithData);

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
        ErrorCode => 'AdminAgentGroupSet.MissingParameter', ErrorMessage => 'empty request!',
    ) if !IsHashRefWithData( $Param{Data} );
    my $TokenError = $Self->_CheckAccessToken( Data => $Param{Data} );
    return $TokenError if $TokenError;

    my $D = $Param{Data};
    for my $Needed (qw(AgentLogin TargetUserID)) {
        return $Self->ReturnError(
            ErrorCode => 'AdminAgentGroupSet.MissingParameter', ErrorMessage => "$Needed missing!",
        ) if !IsStringWithData( $D->{$Needed} );
    }
    if ( !exists $D->{GroupIDs} || ref $D->{GroupIDs} ne 'ARRAY' ) {
        return $Self->ReturnError(
            ErrorCode => 'AdminAgentGroupSet.MissingParameter', ErrorMessage => 'GroupIDs must be an array!',
        );
    }

    my $UserObject  = $Kernel::OM->Get('Kernel::System::User');
    my $GroupObject = $Kernel::OM->Get('Kernel::System::Group');

    my $ActorUserID = $UserObject->UserLookup( UserLogin => $D->{AgentLogin}, Silent => 1 );
    if ( !$ActorUserID ) {
        return $Self->ReturnError(
            ErrorCode => 'AdminAgentGroupSet.UnknownAgent', ErrorMessage => 'agent login not found',
        );
    }

    my %TargetAgent = $UserObject->GetUserData( UserID => $D->{TargetUserID}, NoOutOfOffice => 1 );
    if ( !%TargetAgent ) {
        return $Self->ReturnError(
            ErrorCode => 'AdminAgentGroupSet.NotFound', ErrorMessage => 'agent not found',
        );
    }

    # ── Validate every requested GroupID against the real group list. ──
    my %AllGroups = $GroupObject->GroupList( Valid => 0 );
    my %Desired;
    for my $GroupID ( @{ $D->{GroupIDs} } ) {
        if ( !$AllGroups{$GroupID} ) {
            return $Self->ReturnError(
                ErrorCode    => 'AdminAgentGroupSet.UnknownGroup',
                ErrorMessage => "unknown GroupID '$GroupID'",
            );
        }
        $Desired{$GroupID} = 1;
    }

    # ── Current ('rw') membership — the BEFORE snapshot. ──
    my %CurrentRw = $GroupObject->PermissionUserGroupGet(
        UserID => $D->{TargetUserID},
        Type   => 'rw',
    );
    my @Before = sort { $a <=> $b } keys %CurrentRw;

    # ── Anti-lockout: never let an agent remove itself from 'admin'. ──
    my $AdminGroupID = $GroupObject->GroupLookup( Group => 'admin' );
    if (
        $AdminGroupID
        && $ActorUserID eq $D->{TargetUserID}
        && $CurrentRw{$AdminGroupID}
        && !$Desired{$AdminGroupID}
        )
    {
        return $Self->ReturnError(
            ErrorCode    => 'AdminAgentGroupSet.AntiLockout',
            ErrorMessage => 'you cannot remove yourself from the admin group.',
        );
    }

    # ── Diff and write only the delta. ──
    my %Touch = ( %CurrentRw, %Desired );
    for my $GroupID ( sort { $a <=> $b } keys %Touch ) {
        my $IsCurrent = exists $CurrentRw{$GroupID} ? 1 : 0;
        my $IsDesired = exists $Desired{$GroupID}   ? 1 : 0;
        next if $IsCurrent == $IsDesired;

        my $OK = $GroupObject->PermissionGroupUserAdd(
            GID        => $GroupID,
            UID        => $D->{TargetUserID},
            Permission => { rw => $IsDesired ? 1 : 0 },
            UserID     => $ActorUserID,
        );
        if ( !$OK ) {
            my $Msg = $Kernel::OM->Get('Kernel::System::Log')->GetLogEntry( Type => 'error', What => 'Message' )
                || "could not update permission for group '$GroupID'";
            return $Self->ReturnError(
                ErrorCode => 'AdminAgentGroupSet.WriteError', ErrorMessage => $Msg,
            );
        }
    }

    # ── Re-read the AFTER snapshot from Znuny (never just echo the request back). ──
    my %AfterRw = $GroupObject->PermissionUserGroupGet(
        UserID => $D->{TargetUserID},
        Type   => 'rw',
    );
    my @After = sort { $a <=> $b } keys %AfterRw;

    return {
        Success => 1,
        Data    => {
            UserID => $D->{TargetUserID},
            Before => [ map { { GroupID => $_, Name => $CurrentRw{$_} } } @Before ],
            After  => [ map { { GroupID => $_, Name => $AfterRw{$_} } } @After ],
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
