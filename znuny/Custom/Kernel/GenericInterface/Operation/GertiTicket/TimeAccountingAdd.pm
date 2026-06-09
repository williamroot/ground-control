# znuny/Custom/Kernel/GenericInterface/Operation/GertiTicket/TimeAccountingAdd.pm
# --
# Gerti — custom GI op (Spec #1J). Wraps native Ticket::TicketAccountTime so the
# agent time-tracker (via sidecar) can log a time_accounting entry. Resolves the
# Znuny UserID from the agent login. Upgrade-safe Custom/ overlay.
# --
package Kernel::GenericInterface::Operation::GertiTicket::TimeAccountingAdd;

use strict;
use warnings;

use Kernel::System::VariableCheck qw(IsHashRefWithData IsStringWithData IsNumber);

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
        ErrorCode => 'TimeAccountingAdd.MissingParameter', ErrorMessage => 'empty request!',
    ) if !IsHashRefWithData( $Param{Data} );
    my $TokenError = $Self->_CheckAccessToken( Data => $Param{Data} );
    return $TokenError if $TokenError;

    my $D = $Param{Data};
    for my $Needed (qw(TicketID AgentLogin TimeUnit)) {
        return $Self->ReturnError(
            ErrorCode => 'TimeAccountingAdd.MissingParameter', ErrorMessage => "$Needed missing!",
        ) if !IsStringWithData( $D->{$Needed} );
    }
    if ( !IsNumber( $D->{TimeUnit} ) || $D->{TimeUnit} <= 0 ) {
        return $Self->ReturnError(
            ErrorCode => 'TimeAccountingAdd.BadTimeUnit', ErrorMessage => 'TimeUnit must be > 0',
        );
    }

    my $UserObject = $Kernel::OM->Get('Kernel::System::User');
    my $UserID = $UserObject->UserLookup( UserLogin => $D->{AgentLogin}, Silent => 1 );
    if ( !$UserID ) {
        return $Self->ReturnError(
            ErrorCode => 'TimeAccountingAdd.UnknownAgent', ErrorMessage => 'agent login not found',
        );
    }

    my $TicketObject = $Kernel::OM->Get('Kernel::System::Ticket');

    # Native TicketAccountTime REQUIRES a truthy ArticleID. Create an internal
    # agent note (from the stop note) and account the time to it.
    my $ArticleObject = $Kernel::OM->Get('Kernel::System::Ticket::Article');
    my $Backend       = $ArticleObject->BackendForChannel( ChannelName => 'Internal' );
    my $ArticleID     = $Backend->ArticleCreate(
        TicketID             => $D->{TicketID},
        SenderType           => 'agent',
        IsVisibleForCustomer => 0,
        From                 => $D->{AgentLogin},
        Subject              => 'Apontamento de tempo',
        Body                 => ( $D->{Note} // 'Tempo registrado via timer' ),
        ContentType          => 'text/plain; charset=utf-8',
        HistoryType          => 'AddNote',
        HistoryComment       => 'Gerti timer',
        UserID               => $UserID,
    );
    if ( !$ArticleID ) {
        return $Self->ReturnError(
            ErrorCode => 'TimeAccountingAdd.ArticleError', ErrorMessage => 'article create failed',
        );
    }

    my $OK = $TicketObject->TicketAccountTime(
        TicketID  => $D->{TicketID},
        ArticleID => $ArticleID,
        TimeUnit  => $D->{TimeUnit},
        UserID    => $UserID,
    );
    if ( !$OK ) {
        return $Self->ReturnError(
            ErrorCode => 'TimeAccountingAdd.AccountError', ErrorMessage => 'TicketAccountTime failed',
        );
    }

    return { Success => 1, Data => { OK => 1, UserID => $UserID, ArticleID => $ArticleID } };
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
