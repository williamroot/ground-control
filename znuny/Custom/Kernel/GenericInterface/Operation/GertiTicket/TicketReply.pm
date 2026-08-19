# znuny/Custom/Kernel/GenericInterface/Operation/GertiTicket/TicketReply.pm
# Resposta do cliente a um ticket existente. Mesma guarda de posse do TicketGet:
# o ticket DEVE pertencer ao CustomerID informado, senão NotFound. CustomerUserID
# é OPCIONAL: quando informado, o ticket também precisa ser do próprio usuário —
# alinha a resposta ao escopo `own` que a lista já usa no papel `helpdesk`.
# Ausente => escopo de empresa (papel `admin` do portal).
#
# CUIDADO: CustomerUser (obrigatório) e CustomerUserID (opcional) são parâmetros
# DIFERENTES e não podem ser fundidos. CustomerUser é o AUTOR do artigo (o From
# da resposta); CustomerUserID é a GUARDA de posse. Guardar pelo autor
# bloquearia o `admin` do portal, que legitimamente responde chamado da empresa.
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

    # Posse (empresa): ticket inexistente OU de outra empresa => NotFound.
    my $NotFound = !%T || ( $T{CustomerID} // '' ) ne $D->{CustomerID};

    # Posse por USUÁRIO, guarda ADICIONAL (nunca substitui a de empresa acima).
    # A resposta era mais permissiva que a lista: a lista usa escopo `own` para o
    # papel `helpdesk`, a resposta conferia só a empresa — um helpdesk que
    # adivinhasse o id escrevia no chamado de colega (IDOR). CustomerUserID
    # ausente ou vazio => comportamento de antes, escopo de empresa.
    if ( !$NotFound && IsStringWithData( $D->{CustomerUserID} ) ) {
        # Comparação sem diferenciar caixa, alinhada ao TicketSearch, que já
        # compara assim. Não achamos caminho para o dono legítimo cair no 404 —
        # caixa errada morre antes, no 401 do login — mas duas camadas de
        # autorização com regras diferentes é dívida esperando virar defeito.
        # Registrada na Onda 0, fechada aqui (Onda 2).
        $NotFound = lc( $T{CustomerUserID} // '' ) ne lc( $D->{CustomerUserID} );
    }

    # Sempre o MESMO NotFound: nunca 403, nunca erro distinto — não pode vazar
    # a existência do chamado nem para a empresa errada nem para o colega.
    if ($NotFound) {
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
