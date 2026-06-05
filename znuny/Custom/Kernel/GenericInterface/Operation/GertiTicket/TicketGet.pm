# znuny/Custom/Kernel/GenericInterface/Operation/GertiTicket/TicketGet.pm
# Detalhe + thread de artigos visíveis ao cliente. Guarda de posse: o ticket
# DEVE pertencer ao CustomerID informado, senão NotFound.
package Kernel::GenericInterface::Operation::GertiTicket::TicketGet;

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
        ErrorCode => 'TicketGet.MissingParameter', ErrorMessage => 'empty request!',
    ) if !IsHashRefWithData( $Param{Data} );
    my $TokenError = $Self->_CheckAccessToken( Data => $Param{Data} );
    return $TokenError if $TokenError;

    my $D = $Param{Data};
    for my $Needed (qw(TicketID CustomerID)) {
        return $Self->ReturnError(
            ErrorCode => 'TicketGet.MissingParameter', ErrorMessage => "$Needed missing!",
        ) if !IsStringWithData( $D->{$Needed} );
    }

    my $TicketObject = $Kernel::OM->Get('Kernel::System::Ticket');
    my %T = $TicketObject->TicketGet( TicketID => $D->{TicketID}, DynamicFields => 1, UserID => 1 );

    # Posse: ticket inexistente OU de outra empresa => NotFound (não vaza existência).
    if ( !%T || ( $T{CustomerID} // '' ) ne $D->{CustomerID} ) {
        return $Self->ReturnError(
            ErrorCode => 'TicketGet.NotFound', ErrorMessage => 'ticket not found',
        );
    }

    my $DFObject  = $Kernel::OM->Get('Kernel::System::DynamicField');
    my $DFConfig  = $DFObject->DynamicFieldGet( Name => 'GertiContractId' );
    my $DFBackend = $Kernel::OM->Get('Kernel::System::DynamicField::Backend');
    my $Contract  = IsHashRefWithData($DFConfig)
        ? $DFBackend->ValueGet( DynamicFieldConfig => $DFConfig, ObjectID => $D->{TicketID} )
        : undef;

    my $ArticleObject = $Kernel::OM->Get('Kernel::System::Ticket::Article');
    my @ArticleList = $ArticleObject->ArticleList(
        TicketID => $D->{TicketID}, IsVisibleForCustomer => 1,
    );
    my @Articles;
    for my $Meta (@ArticleList) {
        my $Backend = $ArticleObject->BackendForArticle(%{$Meta});
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
            Created      => $T{Created},
            CustomerID   => $T{CustomerID},
            ContractId   => $Contract,
            Articles     => \@Articles,
        },
    };
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
