# znuny/Custom/Kernel/GenericInterface/Operation/GertiTicket/TicketReply.pm
# Resposta do cliente a um ticket existente. Mesma guarda de posse do TicketGet.
package Kernel::GenericInterface::Operation::GertiTicket::TicketReply;

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
        ErrorCode => 'TicketReply.MissingParameter', ErrorMessage => 'empty request!',
    ) if !IsHashRefWithData( $Param{Data} );
    my $TokenError = $Self->_CheckAccessToken( Data => $Param{Data} );
    return $TokenError if $TokenError;

    my $D = $Param{Data};
    for my $Needed (qw(TicketID CustomerUser CustomerID Body)) {
        return $Self->ReturnError(
            ErrorCode => 'TicketReply.MissingParameter', ErrorMessage => "$Needed missing!",
        ) if !IsStringWithData( $D->{$Needed} );
    }

    my $TicketObject = $Kernel::OM->Get('Kernel::System::Ticket');
    my %T = $TicketObject->TicketGet( TicketID => $D->{TicketID}, UserID => 1 );
    if ( !%T || ( $T{CustomerID} // '' ) ne $D->{CustomerID} ) {
        return $Self->ReturnError(
            ErrorCode => 'TicketReply.NotFound', ErrorMessage => 'ticket not found',
        );
    }

    my $ArticleObject = $Kernel::OM->Get('Kernel::System::Ticket::Article');
    my $Backend       = $ArticleObject->BackendForChannel( ChannelName => 'Internal' );
    my $ArticleID = $Backend->ArticleCreate(
        TicketID             => $D->{TicketID},
        SenderType           => 'customer',
        IsVisibleForCustomer => 1,
        From                 => $D->{CustomerUser},
        Subject              => $D->{Subject} || 'Re: ' . ( $T{Title} // '' ),
        Body                 => $D->{Body},
        ContentType          => 'text/plain; charset=utf-8',
        HistoryType          => 'FollowUp',
        HistoryComment       => 'Gerti portal reply',
        UserID               => 1,
    );
    return $Self->ReturnError(
        ErrorCode => 'TicketReply.ArticleError', ErrorMessage => 'reply failed',
    ) if !$ArticleID;

    return { Success => 1, Data => { ArticleID => $ArticleID } };
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
