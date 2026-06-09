# znuny/Custom/Kernel/GenericInterface/Operation/GertiTicket/AgentTicketGet.pm
# Detalhe de ticket para o agente (staff). Spec #1J.
package Kernel::GenericInterface::Operation::GertiTicket::AgentTicketGet;

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
        ErrorCode => 'AgentTicketGet.MissingParameter', ErrorMessage => 'empty request!',
    ) if !IsHashRefWithData( $Param{Data} );
    my $TokenError = $Self->_CheckAccessToken( Data => $Param{Data} );
    return $TokenError if $TokenError;

    my $D = $Param{Data};
    return $Self->ReturnError(
        ErrorCode => 'AgentTicketGet.MissingParameter', ErrorMessage => 'TicketID missing!',
    ) if !IsStringWithData( $D->{TicketID} );

    my $TicketObject = $Kernel::OM->Get('Kernel::System::Ticket');
    my %T = $TicketObject->TicketGet( TicketID => $D->{TicketID}, DynamicFields => 1, UserID => 1 );
    return $Self->ReturnError(
        ErrorCode => 'AgentTicketGet.NotFound', ErrorMessage => 'ticket not found',
    ) if !%T;

    my $ArticleObject = $Kernel::OM->Get('Kernel::System::Ticket::Article');
    my @ArticleList = $ArticleObject->ArticleList( TicketID => $D->{TicketID} );
    my @Articles;
    for my $Meta (@ArticleList) {
        my $Backend = $ArticleObject->BackendForArticle( %{$Meta} );
        my %A = $Backend->ArticleGet( %{$Meta}, DynamicFields => 0 );
        push @Articles, {
            ArticleID  => $A{ArticleID},
            From       => $A{From},
            SenderType => $A{SenderType},
            Subject    => $A{Subject},
            Body       => $A{Body},
            CreateTime => $A{CreateTime},
        };
    }

    return {
        Success => 1,
        Data    => {
            TicketID     => $D->{TicketID},
            TicketNumber => $T{TicketNumber},
            Title        => $T{Title},
            State        => $T{State},
            Priority     => $T{Priority},
            CustomerID   => $T{CustomerID},
            Owner        => $T{Owner},
            Created      => $T{Created},
            Articles     => \@Articles,
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
