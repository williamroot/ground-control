# znuny/Custom/Kernel/GenericInterface/Operation/GertiAdmin/AdminAgentResolveLogin.pm
# --
# Gerti — custom GI operation. Login universal do console (#2-login-por-email):
# o operador pode digitar o LOGIN do agente ou o seu E-MAIL (preferência
# `user_preferences.UserEmail` — a tabela `users` do Znuny NÃO tem coluna de
# e-mail). Esta operação recebe um `Identifier` cru e devolve o LOGIN
# CANÔNICO do agente, nunca o e-mail — quem guarda o resultado (sidecar) usa
# esse valor como `AgentLogin` em toda operação GI subsequente, então um
# valor errado aqui quebra o console inteiro depois do login.
#
# Regras (não negociáveis):
#   - Primeiro tenta `UserLookup` — se `Identifier` casar EXATAMENTE um
#     UserLogin existente, devolve ele direto (nenhuma ambiguidade possível:
#     UserLogin é UNIQUE no schema nativo do Znuny).
#   - Só se isso falhar E `Identifier` contiver '@', tenta resolver por
#     e-mail via `UserSearch(PostMasterSearch => Identifier)` — API nativa
#     que casa contra a preferência `UserEmail`.
#   - FALHA FECHADA quando o e-mail casa mais de um agente válido:
#     ambiguidade em autenticação pode logar na conta errada. Nunca escolhe
#     um — devolve `AdminAgentResolveLogin.Ambiguous`, código distinto de
#     "não encontrado" (o sidecar não distingue os dois no HTTP que devolve
#     ao browser — 401 idêntico — mas aqui o erro é explícito e auditável).
#   - Só agentes VÁLIDOS (`ValidID = 1`) contam como candidato — tanto no
#     atalho de login quanto na resolução por e-mail. Um agente sem e-mail
#     nenhum (ex.: o `root@localhost` do instalador) nunca é alcançado por
#     esta operação — continua entrando só pelo login exato.
#   - `AccessToken` fail-closed (`GertiAdmin::AccessToken`), como as irmãs.
# Upgrade-safe Custom/ overlay.
# --
package Kernel::GenericInterface::Operation::GertiAdmin::AdminAgentResolveLogin;

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
        ErrorCode => 'AdminAgentResolveLogin.MissingParameter', ErrorMessage => 'empty request!',
    ) if !IsHashRefWithData( $Param{Data} );
    my $TokenError = $Self->_CheckAccessToken( Data => $Param{Data} );
    return $TokenError if $TokenError;

    my $D = $Param{Data};
    for my $Needed (qw(Identifier)) {
        return $Self->ReturnError(
            ErrorCode => 'AdminAgentResolveLogin.MissingParameter', ErrorMessage => "$Needed missing!",
        ) if !IsStringWithData( $D->{$Needed} );
    }

    my $Identifier = $D->{Identifier};
    my $UserObject = $Kernel::OM->Get('Kernel::System::User');

    # ── 1) Atalho: Identifier já É um UserLogin exato. UserLogin é UNIQUE no
    #    schema nativo — se casar, não há ambiguidade possível. ──
    my $DirectUserID = $UserObject->UserLookup( UserLogin => $Identifier, Silent => 1 );
    if ($DirectUserID) {
        my $Login = $Self->_ValidLogin( UserID => $DirectUserID );
        return { Success => 1, Data => { Login => $Login, UserID => $DirectUserID } } if $Login;

        # Login existe mas o agente está inválido: não resolve — mesmo caminho
        # de "não encontrado" abaixo, nenhum atalho por e-mail teria como salvar
        # um Identifier que já é o login exato.
        return $Self->ReturnError(
            ErrorCode => 'AdminAgentResolveLogin.NotFound', ErrorMessage => 'agent login not found',
        );
    }

    # ── 2) Sem casar como login: só tenta e-mail se Identifier parecer um. ──
    if ( $Identifier !~ m{\@}xms ) {
        return $Self->ReturnError(
            ErrorCode => 'AdminAgentResolveLogin.NotFound', ErrorMessage => 'agent login not found',
        );
    }

    my %Matches = $UserObject->UserSearch( PostMasterSearch => $Identifier, Valid => 0 );

    # Filtra para agentes VÁLIDOS apenas — um match inválido não conta como
    # candidato, nem para sucesso nem para ambiguidade.
    my @ValidLogins;
    for my $MatchUserID ( sort { $a <=> $b } keys %Matches ) {
        my $Login = $Self->_ValidLogin( UserID => $MatchUserID );
        push @ValidLogins, { UserID => $MatchUserID, Login => $Login } if $Login;
    }

    if ( !@ValidLogins ) {
        return $Self->ReturnError(
            ErrorCode => 'AdminAgentResolveLogin.NotFound', ErrorMessage => 'agent email not found',
        );
    }

    if ( @ValidLogins > 1 ) {
        return $Self->ReturnError(
            ErrorCode    => 'AdminAgentResolveLogin.Ambiguous',
            ErrorMessage => 'email matches more than one valid agent — refusing to pick one',
        );
    }

    return {
        Success => 1,
        Data    => { Login => $ValidLogins[0]->{Login}, UserID => $ValidLogins[0]->{UserID} },
    };
}

# Devolve o UserLogin canônico se, e só se, o UserID resolver para um agente
# com ValidID = 1. undef caso contrário (agente sumiu ou está inválido).
sub _ValidLogin {
    my ( $Self, %Param ) = @_;

    my $UserObject = $Kernel::OM->Get('Kernel::System::User');
    my %Agent = $UserObject->GetUserData( UserID => $Param{UserID}, NoOutOfOffice => 1 );
    return if !%Agent;
    return if !IsStringWithData( $Agent{ValidID} ) || $Agent{ValidID} != 1;
    return $Agent{UserLogin};
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
