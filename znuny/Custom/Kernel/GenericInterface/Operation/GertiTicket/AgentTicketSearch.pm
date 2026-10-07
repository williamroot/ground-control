# znuny/Custom/Kernel/GenericInterface/Operation/GertiTicket/AgentTicketSearch.pm
# Busca de tickets para o agente (sem escopo de customer). Spec #1J.
package Kernel::GenericInterface::Operation::GertiTicket::AgentTicketSearch;

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
        ErrorCode => 'AgentTicketSearch.MissingParameter', ErrorMessage => 'empty request!',
    ) if !IsHashRefWithData( $Param{Data} );
    my $TokenError = $Self->_CheckAccessToken( Data => $Param{Data} );
    return $TokenError if $TokenError;

    my $D = $Param{Data};
    my $TicketObject = $Kernel::OM->Get('Kernel::System::Ticket');

    # Filtros comuns a TODAS as buscas abaixo. O CustomerID (quando vem) entra
    # aqui para que nenhuma das buscas (título, número ou ID) vaze chamado de
    # outro cliente.
    my %Base = ( Result => 'ARRAY', Limit => 50, UserID => 1, OrderBy => 'Down', SortBy => 'Age' );
    $Base{CustomerID}   = $D->{CustomerID} if IsStringWithData( $D->{CustomerID} );
    $Base{TicketNumber} = $D->{Number}     if IsStringWithData( $D->{Number} );

    my $Query = IsStringWithData( $D->{Query} ) ? $D->{Query} : '';
    $Query =~ s/^\s+|\s+$//g;

    my @TicketIDs;
    if ( !length $Query ) {
        @TicketIDs = $TicketObject->TicketSearch(%Base);
    }
    else {
        # O TicketSearch do Znuny faz AND entre campos, nunca OU. Então cada
        # critério é uma busca separada:
        #   - sempre: título contém a Query (%...%);
        #   - Query numérica ("84", "#84", "2026081910000081"): também
        #     TicketNumber exato, TicketNumber terminando nos dígitos e
        #     TicketID igual ao número (o "#84" que a tela do console mostra).
        my @Searches = ( { Criteria => { Title => '%' . $Query . '%' } } );
        if ( $Query =~ m/^#?([0-9]+)$/ ) {
            my $Digits = $1;
            # Um Number explícito já restringe o TicketNumber; não sobrescrever.
            if ( !IsStringWithData( $D->{Number} ) ) {
                push @Searches,
                    { Criteria => { TicketNumber => $Digits }, Exact => 1 },
                    { Criteria => { TicketNumber => '%' . $Digits } };
            }
            ( my $AsID = $Digits ) =~ s/^0+//;
            if ( length $AsID && length $AsID <= 10 && $AsID <= 2_147_483_647 ) {
                push @Searches, { Criteria => { TicketID => $AsID }, Exact => 1 };
            }
        }

        # União sem duplicados. Cada busca já leva %Base (CustomerID/Number).
        my ( %Seen, %Exact, @Union );
        for my $Search (@Searches) {
            for my $ID ( $TicketObject->TicketSearch( %Base, %{ $Search->{Criteria} } ) ) {
                $Exact{$ID} = 1 if $Search->{Exact};
                push @Union, $ID if !$Seen{$ID}++;
            }
        }

        if (@Union) {
            # Reordena a união (mais novo primeiro), reaplicando %Base como
            # segunda trava contra vazamento entre clientes. Acertos exatos
            # (TicketID / número completo) vêm na frente, para que o sufixo
            # (ex.: todo número terminado em 84) não os empurre para fora do
            # limite. O limite de 50 é aplicado só no final.
            my @Sorted = $TicketObject->TicketSearch(
                %Base,
                TicketID => \@Union,
                Limit    => scalar @Union,
            );
            @TicketIDs = ( ( grep { $Exact{$_} } @Sorted ), ( grep { !$Exact{$_} } @Sorted ) );
            splice @TicketIDs, 50 if @TicketIDs > 50;
        }
    }

    my @Tickets;
    for my $ID (@TicketIDs) {
        my %T = $TicketObject->TicketGet( TicketID => $ID, UserID => 1 );
        next if !%T;
        push @Tickets, {
            TicketID     => $ID,
            TicketNumber => $T{TicketNumber},
            Title        => $T{Title},
            State        => $T{State},
            CustomerID   => $T{CustomerID},
            Owner        => $T{Owner},
            Created      => $T{Created},
        };
    }
    return { Success => 1, Data => { Tickets => \@Tickets } };
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
