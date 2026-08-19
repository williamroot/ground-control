# --
# Gerti — custom GI operation (T-R9.4, R9). Cria OU atualiza uma conta de
# recebimento, numa operação só (mesma forma do AdminAgentSet).
#
# Duas coisas fazem esta op existir em vez de usar a genérica, e as duas são
# sobre a senha:
#
#  1. `MailAccountUpdate` do Znuny **exige** `Password` não-vazio. Se o console
#     tivesse que mandar a senha a cada "salvar", ele precisaria conhecê-la — o
#     que significa tê-la trafegado de volta em alguma leitura. Aqui, quando o
#     chamador NÃO manda senha, a op relê a senha atual **dentro do Znuny** e a
#     reenvia. A senha nunca cruza a rede para depois voltar.
#  2. A resposta nunca ecoa senha (aceite A9.4).
#
# --
# This software comes with ABSOLUTELY NO WARRANTY.
# --

package Kernel::GenericInterface::Operation::GertiAdmin::AdminMailAccountSet;

use strict;
use warnings;

use Kernel::System::VariableCheck qw(IsHashRefWithData IsStringWithData);

use parent qw(Kernel::GenericInterface::Operation::Common);

our $ObjectManagerDisabled = 1;

# Tipos de caixa que o Znuny 7.2 traz de fábrica. Allowlist explícita: um
# `Type` inventado viraria erro obscuro lá dentro, na hora do fetch.
my @VALID_TYPES = qw(POP3 POP3S POP3TLS IMAP IMAPS IMAPTLS);

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
        ErrorCode => 'AdminMailAccountSet.MissingParameter', ErrorMessage => 'empty request!',
    ) if !IsHashRefWithData( $Param{Data} );
    my $TokenError = $Self->_CheckAccessToken( Data => $Param{Data} );
    return $TokenError if $TokenError;

    my $D = $Param{Data};

    my $UserObject = $Kernel::OM->Get('Kernel::System::User');
    my $ActorID    = $UserObject->UserLookup( UserLogin => $D->{AgentLogin} // '', Silent => 1 );
    return $Self->ReturnError(
        ErrorCode => 'AdminMailAccountSet.UnknownAgent', ErrorMessage => 'agent login not found',
    ) if !$ActorID;

    my $MailAccountObject = $Kernel::OM->Get('Kernel::System::MailAccount');

    my %Current;
    if ( IsStringWithData( $D->{ID} ) ) {
        %Current = $MailAccountObject->MailAccountGet( ID => $D->{ID} );
        return $Self->ReturnError(
            ErrorCode => 'AdminMailAccountSet.NotFound', ErrorMessage => 'mail account not found',
        ) if !IsHashRefWithData( \%Current );
    }

    my $Merged = sub {
        my ($Field, $Default) = @_;
        return $D->{$Field} if exists $D->{$Field};
        return $Current{$Field} if exists $Current{$Field};
        return $Default;
    };

    my %Args = (
        Login         => $Merged->('Login'),
        Host          => $Merged->('Host'),
        Type          => $Merged->('Type', 'IMAPS'),
        ValidID       => $Merged->('ValidID', 1),
        Trusted       => $Merged->('Trusted', 0),
        DispatchingBy => $Merged->('DispatchingBy', 'Queue'),
        QueueID       => $Merged->('QueueID', 0),
        Comment       => $Merged->('Comment', ''),
        IMAPFolder    => $Merged->('IMAPFolder', ''),
    );

    for my $Needed (qw(Login Host Type)) {
        return $Self->ReturnError(
            ErrorCode    => 'AdminMailAccountSet.MissingParameter',
            ErrorMessage => "$Needed is required",
        ) if !IsStringWithData( $Args{$Needed} );
    }
    if ( !grep { $_ eq $Args{Type} } @VALID_TYPES ) {
        return $Self->ReturnError(
            ErrorCode    => 'AdminMailAccountSet.InvalidType',
            ErrorMessage => "Type '$Args{Type}' is not supported (use: @VALID_TYPES)",
        );
    }

    # `DispatchingBy => 'Queue'` precisa de uma fila de verdade; é o que amarra
    # "esse e-mail cai na fila X" (05:57). Sem isso o Znuny aceita e a mensagem
    # some numa fila 0 inexistente.
    if ( $Args{DispatchingBy} eq 'Queue' && !$Args{QueueID} ) {
        return $Self->ReturnError(
            ErrorCode    => 'AdminMailAccountSet.MissingParameter',
            ErrorMessage => 'QueueID is required when DispatchingBy is Queue',
        );
    }

    # A senha: só vem do chamador se ele digitou uma nova. Caso contrário é
    # relida do próprio Znuny e reenviada — ela não vai e volta pela rede.
    my $Password = IsStringWithData( $D->{Password} ) ? $D->{Password} : $Current{Password};
    if ( !IsStringWithData($Password) ) {
        return $Self->ReturnError(
            ErrorCode    => 'AdminMailAccountSet.MissingParameter',
            ErrorMessage => 'Password is required when creating a mail account',
        );
    }

    my $ID = $D->{ID};
    my $OK;
    my $Action;
    if ( IsStringWithData($ID) ) {
        $OK = $MailAccountObject->MailAccountUpdate(
            %Args, Password => $Password, ID => $ID, UserID => $ActorID,
        );
        $Action = 'updated';
    }
    else {
        $ID = $MailAccountObject->MailAccountAdd(
            %Args, Password => $Password, UserID => $ActorID,
        );
        $OK     = $ID;
        $Action = 'created';
    }

    if ( !$OK ) {
        my $Msg = $Kernel::OM->Get('Kernel::System::Log')->GetLogEntry(
            Type => 'error', What => 'Message',
        ) || 'could not save the mail account';
        return $Self->ReturnError(
            ErrorCode => 'AdminMailAccountSet.WriteError', ErrorMessage => $Msg,
        );
    }

    # Resposta sem senha — nem a que veio, nem a que estava lá.
    return {
        Success => 1,
        Data    => {
            Action  => $Action,
            Account => {
                ID            => $ID,
                Login         => $Args{Login},
                Host          => $Args{Host},
                Type          => $Args{Type},
                ValidID       => $Args{ValidID},
                Trusted       => $Args{Trusted},
                DispatchingBy => $Args{DispatchingBy},
                QueueID       => $Args{QueueID},
                Comment       => $Args{Comment},
                HasPassword   => 1,
            },
        },
    };
}

sub _CheckAccessToken {
    my ( $Self, %Param ) = @_;
    my $Provided = $Param{Data}->{AccessToken} || '';
    my $Expected = $Kernel::OM->Get('Kernel::Config')->Get('GertiAdmin::AccessToken') || '';
    return $Self->ReturnError(
        ErrorCode => 'GertiAdmin.AuthFail', ErrorMessage => 'invalid or missing AccessToken.',
    ) if !IsStringWithData($Expected) || !IsStringWithData($Provided) || $Provided ne $Expected;
    return;
}

1;
