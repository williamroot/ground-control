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

# Os tipos de permissão que o Znuny 7.2 conhece por grupo. Allowlist explícita:
# um tipo inventado viraria coluna inexistente e erro obscuro lá dentro.
# `rw` é superconjunto — o Znuny o trata como "tudo" naquele grupo.
my @PERMISSION_TYPES = qw(ro move_into create note owner priority rw);

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

    # ── T-R14.1: permissões GRANULARES, opcionais e retrocompatíveis. ──
    #
    # Até a Onda 4 esta op só sabia `rw`, que o Znuny trata como superconjunto
    # de tudo. Funciona, mas é tudo-ou-nada: não dava para dizer "este agente
    # LÊ a fila do financeiro, mas não move chamado nela" — que é a
    # "estratégia de permissionamento" de que ele fala em 04:39.
    #
    # `Permissions` é um mapa `{ GroupID => [tipos] }`. Ausente => `rw`, e o
    # comportamento é EXATAMENTE o de antes; nenhum chamador existente muda.
    my %PermissionByGroup;
    if ( exists $D->{Permissions} ) {
        if ( ref $D->{Permissions} ne 'HASH' ) {
            return $Self->ReturnError(
                ErrorCode    => 'AdminAgentGroupSet.MissingParameter',
                ErrorMessage => 'Permissions must be an object { GroupID: [types] }',
            );
        }
        for my $GroupID ( keys %{ $D->{Permissions} } ) {
            my $Types = $D->{Permissions}->{$GroupID};
            if ( ref $Types ne 'ARRAY' || !@{$Types} ) {
                return $Self->ReturnError(
                    ErrorCode    => 'AdminAgentGroupSet.MissingParameter',
                    ErrorMessage => "Permissions[$GroupID] must be a non-empty array",
                );
            }
            for my $Type ( @{$Types} ) {
                if ( !grep { $_ eq $Type } @PERMISSION_TYPES ) {
                    return $Self->ReturnError(
                        ErrorCode    => 'AdminAgentGroupSet.UnknownPermission',
                        ErrorMessage => "unknown permission '$Type' (allowed: @PERMISSION_TYPES)",
                    );
                }
            }
            $PermissionByGroup{$GroupID} = { map { $_ => 1 } @{$Types} };
        }
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

    # Anti-lockout ESTENDIDO (T-R14.1): com permissão granular, dá para
    # continuar "no grupo admin" e mesmo assim perder o `rw` — o que tranca
    # exatamente igual, só que por um caminho novo. Bloqueamos os dois.
    if (
        $AdminGroupID
        && $ActorUserID eq $D->{TargetUserID}
        && $CurrentRw{$AdminGroupID}
        && $Desired{$AdminGroupID}
        && $PermissionByGroup{$AdminGroupID}
        && !$PermissionByGroup{$AdminGroupID}->{rw}
        )
    {
        return $Self->ReturnError(
            ErrorCode    => 'AdminAgentGroupSet.AntiLockout',
            ErrorMessage => 'you cannot drop your own rw permission on the admin group.',
        );
    }

    # ── Diff and write only the delta. ──
    my %Touch = ( %CurrentRw, %Desired );
    for my $GroupID ( sort { $a <=> $b } keys %Touch ) {
        my $IsCurrent = exists $CurrentRw{$GroupID} ? 1 : 0;
        my $IsDesired = exists $Desired{$GroupID}   ? 1 : 0;
        next if $IsCurrent == $IsDesired;

        # Sem `Permissions` para este grupo, mantém o comportamento histórico
        # (`rw`). Com, grava exatamente os tipos pedidos e zera os demais — a
        # ausência de um tipo na lista É a remoção dele.
        my %Grant;
        if ( $IsDesired && $PermissionByGroup{$GroupID} ) {
            %Grant = map { $_ => ( $PermissionByGroup{$GroupID}->{$_} ? 1 : 0 ) } @PERMISSION_TYPES;
        }
        elsif ($IsDesired) {
            %Grant = ( rw => 1 );
        }
        else {
            %Grant = map { $_ => 0 } @PERMISSION_TYPES;
        }

        my $OK = $GroupObject->PermissionGroupUserAdd(
            GID        => $GroupID,
            UID        => $D->{TargetUserID},
            Permission => \%Grant,
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
