# znuny/Custom/Kernel/GenericInterface/Operation/GertiTicket/TicketCreate.pm
# --
# Gerti — custom GI operation (Spec #1E). Wraps native Ticket::TicketCreate +
# Article backend so the portal (via sidecar) can open a customer ticket linked
# to a contract. Writes the contract UUID into DynamicField GertiContractId.
# Upgrade-safe Custom/ overlay (same as GertiAdmin ops).
# --
package Kernel::GenericInterface::Operation::GertiTicket::TicketCreate;

use strict;
use warnings;

use MIME::Base64 qw(decode_base64);
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

    if ( !IsHashRefWithData( $Param{Data} ) ) {
        return $Self->ReturnError(
            ErrorCode    => 'TicketCreate.MissingParameter',
            ErrorMessage => 'TicketCreate: the request is empty!',
        );
    }
    my $TokenError = $Self->_CheckAccessToken( Data => $Param{Data} );
    return $TokenError if $TokenError;

    my $D = $Param{Data};
    # `ContractId` saiu da lista de obrigatórios na Onda 4, e a razão importa:
    # ele não é obrigatório do ponto de vista do ZNUNY — é uma invariante do
    # fluxo do PORTAL ("todo chamado do cliente nasce vinculado a um
    # contrato"), e ela continua sendo garantida onde nasceu, no
    # `TicketingService._resolve_contract` do sidecar.
    #
    # O que forçou a mudança foi a agenda de atividades recorrentes (R11):
    # manutenção preventiva NÃO consome contrato por padrão (suposição S4), e
    # com `ContractId` obrigatório aqui ela simplesmente não conseguia abrir
    # chamado nenhum. Achado na verificação ao vivo da Onda 4 — o teste
    # unitário usava um GI falso, que aceitava qualquer coisa.
    for my $Needed (qw(CustomerUser CustomerID Title Body)) {
        if ( !IsStringWithData( $D->{$Needed} ) ) {
            return $Self->ReturnError(
                ErrorCode    => 'TicketCreate.MissingParameter',
                ErrorMessage => "TicketCreate: $Needed is missing!",
            );
        }
    }

    my $TicketObject = $Kernel::OM->Get('Kernel::System::Ticket');

    # Queue: derive from Service if not given. Customer tickets land in the
    # service's default queue; fall back to 'Raw' (Znuny default) if absent.
    my %CreateArgs = (
        Title        => $D->{Title},
        CustomerUser => $D->{CustomerUser},
        CustomerID   => $D->{CustomerID},
        Lock         => 'unlock',
        OwnerID      => 1,
        UserID       => 1,
        StateType    => 'new',
        State        => 'new',
    );
    $CreateArgs{Queue} = $D->{Queue} || 'Raw';

    # O portal (#1E) envia os IDs (Keys do form-meta) de prioridade/tipo/serviço,
    # não os nomes. O Znuny aceita PriorityID/TypeID/ServiceID (numérico) OU o nome —
    # então detectamos: dígitos puros → *ID; caso contrário → nome (retrocompat).
    # (staging revelou: enviar o nome "10" em Service falhava o TicketCreate nativo.)
    if ( IsStringWithData( $D->{Priority} ) ) {
        if ( $D->{Priority} =~ m{\A\d+\z} ) { $CreateArgs{PriorityID} = $D->{Priority}; }
        else                                { $CreateArgs{Priority}   = $D->{Priority}; }
    }
    else { $CreateArgs{PriorityID} = 3; }    # 3 normal (default)

    if ( IsStringWithData( $D->{Type} ) ) {
        if ( $D->{Type} =~ m{\A\d+\z} ) { $CreateArgs{TypeID} = $D->{Type}; }
        else                            { $CreateArgs{Type}   = $D->{Type}; }
    }

    if ( IsStringWithData( $D->{Service} ) ) {
        if ( $D->{Service} =~ m{\A\d+\z} ) { $CreateArgs{ServiceID} = $D->{Service}; }
        else                               { $CreateArgs{Service}   = $D->{Service}; }
    }

    my $TicketID = $TicketObject->TicketCreate(%CreateArgs);
    if ( !$TicketID ) {
        # A mensagem ORIGINAL do Znuny, não um erro genérico. "native
        # TicketCreate failed" custou uma rodada inteira de diagnóstico na
        # verificação da Onda 4 para descobrir que a causa era uma fila
        # inexistente — informação que o Znuny tinha e nós jogávamos fora.
        my $Msg = $Kernel::OM->Get('Kernel::System::Log')->GetLogEntry(
            Type => 'error',
            What => 'Message',
        ) || 'native TicketCreate failed';
        my $Queue = $CreateArgs{Queue} // $CreateArgs{QueueID} // '(default)';
        return $Self->ReturnError(
            ErrorCode    => 'TicketCreate.CreateError',
            ErrorMessage => "TicketCreate falhou (fila: $Queue): $Msg",
        );
    }

    # Carimba o contrato no chamado (DynamicField GertiContractId) — só quando
    # existe um. Chamado de preventiva sem contrato fica sem o campo, que é o
    # estado correto: ele não debita saldo de ninguém.
    my $DFObject      = $Kernel::OM->Get('Kernel::System::DynamicField');
    my $DFBackend     = $Kernel::OM->Get('Kernel::System::DynamicField::Backend');
    my $DFConfig      = $DFObject->DynamicFieldGet( Name => 'GertiContractId' );
    if ( IsHashRefWithData($DFConfig) && IsStringWithData( $D->{ContractId} ) ) {
        $DFBackend->ValueSet(
            DynamicFieldConfig => $DFConfig,
            ObjectID           => $TicketID,
            Value              => $D->{ContractId},
            UserID             => 1,
        );
    }

    # First (customer-visible) article.
    my $ArticleObject = $Kernel::OM->Get('Kernel::System::Ticket::Article');
    my $Backend       = $ArticleObject->BackendForChannel( ChannelName => 'Internal' );
    my @Attachments;
    if ( IsArrayRefWithData( $D->{Attachments} ) ) {
        for my $A ( @{ $D->{Attachments} } ) {
            next if !IsHashRefWithData($A) || !IsStringWithData( $A->{Filename} );
            push @Attachments, {
                Content     => decode_base64( $A->{ContentBase64} // '' ),
                ContentType => $A->{ContentType} || 'application/octet-stream',
                Filename    => $A->{Filename},
            };
        }
    }
    my $ArticleID = $Backend->ArticleCreate(
        TicketID             => $TicketID,
        SenderType           => 'customer',
        IsVisibleForCustomer => 1,
        From                 => $D->{CustomerUser},
        Subject              => $D->{Title},
        Body                 => $D->{Body},
        ContentType          => 'text/plain; charset=utf-8',
        HistoryType          => 'WebRequestCustomer',
        HistoryComment       => 'Gerti portal ticket',
        UserID               => 1,
        ( @Attachments ? ( Attachment => \@Attachments ) : () ),
    );
    if ( !$ArticleID ) {
        return $Self->ReturnError(
            ErrorCode    => 'TicketCreate.ArticleError',
            ErrorMessage => 'TicketCreate: article create failed.',
        );
    }

    my $TicketNumber = $TicketObject->TicketNumberLookup( TicketID => $TicketID );

    # Optional: link a Config Item to the new ticket (Spec #1K). A link failure
    # must NOT fail ticket creation — log and ignore (R1K §4.4).
    my $LinkedConfigItemID;
    if ( IsStringWithData( $D->{ConfigItemID} ) ) {
        my $LinkOk = $Kernel::OM->Get('Kernel::System::LinkObject')->LinkAdd(
            SourceObject => 'Ticket',
            SourceKey    => $TicketID,
            TargetObject => 'ITSMConfigItem',
            TargetKey    => $D->{ConfigItemID},
            Type         => 'RelevantTo',
            State        => 'Valid',
            UserID       => 1,
        );
        if ($LinkOk) {
            $LinkedConfigItemID = $D->{ConfigItemID};
        }
        else {
            $Kernel::OM->Get('Kernel::System::Log')->Log(
                Priority => 'error',
                Message  => "GertiTicket::TicketCreate: LinkAdd Ticket $TicketID <-> "
                    . "ITSMConfigItem $D->{ConfigItemID} failed (ignored).",
            );
        }
    }

    return {
        Success => 1,
        Data    => {
            TicketID     => $TicketID,
            TicketNumber => $TicketNumber,
            ( defined $LinkedConfigItemID ? ( ConfigItemID => $LinkedConfigItemID ) : () ),
        },
    };
}

sub _CheckAccessToken {
    my ( $Self, %Param ) = @_;
    my $Provided = $Param{Data}->{AccessToken} || '';
    my $Expected = $Kernel::OM->Get('Kernel::Config')->Get('GertiAdmin::AccessToken') || '';
    if ( !IsStringWithData($Expected) || !IsStringWithData($Provided) || $Provided ne $Expected ) {
        return $Self->ReturnError(
            ErrorCode    => 'GertiTicket.AuthFail',
            ErrorMessage => 'GertiTicket: invalid or missing AccessToken.',
        );
    }
    return;
}

1;
