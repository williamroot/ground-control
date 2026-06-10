# znuny/Custom/Kernel/GenericInterface/Operation/GertiTicket/AgentTicketUpdate.pm
# --
# Gerti — custom GI op (Spec #1Q). Aplica mudanças de Queue/State/Priority/Owner
# e cria uma nota interna (Note → ArticleCreate) num ticket. Usado pelo motor de
# automação do sidecar (executor de ações). Token de AGENTE (GertiAgent::AccessToken,
# como TimeAccountingAdd/AgentTicketGet). Escopado por TicketID — nunca toca outro
# ticket. Upgrade-safe Custom/ overlay.
# --
package Kernel::GenericInterface::Operation::GertiTicket::AgentTicketUpdate;

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
        ErrorCode => 'AgentTicketUpdate.MissingParameter', ErrorMessage => 'empty request!',
    ) if !IsHashRefWithData( $Param{Data} );
    my $TokenError = $Self->_CheckAccessToken( Data => $Param{Data} );
    return $TokenError if $TokenError;

    my $D = $Param{Data};
    return $Self->ReturnError(
        ErrorCode => 'AgentTicketUpdate.MissingParameter', ErrorMessage => 'TicketID missing!',
    ) if !IsStringWithData( $D->{TicketID} );

    my $TicketObject = $Kernel::OM->Get('Kernel::System::Ticket');

    # Confirma que o ticket existe antes de mexer (anti-IDOR/anti-fantasma).
    my %T = $TicketObject->TicketGet( TicketID => $D->{TicketID}, UserID => 1 );
    return $Self->ReturnError(
        ErrorCode => 'AgentTicketUpdate.NotFound', ErrorMessage => 'ticket not found',
    ) if !%T;

    my %Applied;

    # ── Queue (por nome) ───────────────────────────────────────────────
    if ( IsStringWithData( $D->{Queue} ) ) {
        my $OK = $TicketObject->TicketQueueSet(
            Queue    => $D->{Queue},
            TicketID => $D->{TicketID},
            UserID   => 1,
        );
        return $Self->ReturnError(
            ErrorCode => 'AgentTicketUpdate.QueueError', ErrorMessage => 'TicketQueueSet failed',
        ) if !$OK;
        $Applied{Queue} = $D->{Queue};
    }

    # ── State (por nome) ───────────────────────────────────────────────
    if ( IsStringWithData( $D->{State} ) ) {
        my $OK = $TicketObject->TicketStateSet(
            State    => $D->{State},
            TicketID => $D->{TicketID},
            UserID   => 1,
        );
        return $Self->ReturnError(
            ErrorCode => 'AgentTicketUpdate.StateError', ErrorMessage => 'TicketStateSet failed',
        ) if !$OK;
        $Applied{State} = $D->{State};
    }

    # ── Priority (por nome) ────────────────────────────────────────────
    if ( IsStringWithData( $D->{Priority} ) ) {
        my $OK = $TicketObject->TicketPrioritySet(
            Priority => $D->{Priority},
            TicketID => $D->{TicketID},
            UserID   => 1,
        );
        return $Self->ReturnError(
            ErrorCode => 'AgentTicketUpdate.PriorityError', ErrorMessage => 'TicketPrioritySet failed',
        ) if !$OK;
        $Applied{Priority} = $D->{Priority};
    }

    # ── Owner (por login) ──────────────────────────────────────────────
    if ( IsStringWithData( $D->{Owner} ) ) {
        my $UserObject = $Kernel::OM->Get('Kernel::System::User');
        my $NewUserID  = $UserObject->UserLookup( UserLogin => $D->{Owner}, Silent => 1 );
        return $Self->ReturnError(
            ErrorCode => 'AgentTicketUpdate.UnknownOwner', ErrorMessage => 'owner login not found',
        ) if !$NewUserID;
        my $OK = $TicketObject->TicketOwnerSet(
            TicketID  => $D->{TicketID},
            NewUserID => $NewUserID,
            UserID    => 1,
        );
        return $Self->ReturnError(
            ErrorCode => 'AgentTicketUpdate.OwnerError', ErrorMessage => 'TicketOwnerSet failed',
        ) if !$OK;
        $Applied{Owner} = $D->{Owner};
    }

    # ── Note → nota interna (ArticleCreate, não visível ao cliente) ────
    my $ArticleID;
    if ( IsStringWithData( $D->{Note} ) ) {
        my $ArticleObject = $Kernel::OM->Get('Kernel::System::Ticket::Article');
        my $Backend       = $ArticleObject->BackendForChannel( ChannelName => 'Internal' );
        $ArticleID = $Backend->ArticleCreate(
            TicketID             => $D->{TicketID},
            SenderType           => 'agent',
            IsVisibleForCustomer => 0,
            From                 => 'Gerti Automation',
            Subject              => 'Automação',
            Body                 => $D->{Note},
            ContentType          => 'text/plain; charset=utf-8',
            HistoryType          => 'AddNote',
            HistoryComment       => 'Gerti automation',
            UserID               => 1,
        );
        return $Self->ReturnError(
            ErrorCode => 'AgentTicketUpdate.ArticleError', ErrorMessage => 'article create failed',
        ) if !$ArticleID;
        $Applied{Note} = 1;
    }

    return {
        Success => 1,
        Data    => {
            OK        => 1,
            TicketID  => $D->{TicketID},
            Applied   => \%Applied,
            ArticleID => $ArticleID,
        },
    };
}

sub _CheckAccessToken {
    my ( $Self, %Param ) = @_;
    my $Provided = $Param{Data}->{AccessToken} || '';
    my $Expected = $Kernel::OM->Get('Kernel::Config')->Get('GertiAgent::AccessToken') || '';
    return $Self->ReturnError( ErrorCode => 'GertiAgent.AuthFail', ErrorMessage => 'invalid AccessToken.' )
        if !IsStringWithData($Expected) || !IsStringWithData($Provided) || $Provided ne $Expected;
    return;
}

1;
