# --
# Gerti — custom GI operation (T-R9.4, R9 do vídeo do Kleber).
# Lista as contas de RECEBIMENTO (PostMaster mail accounts) da instância.
#
# *"Quando enviar para esse e-mail, vai para a fila X"* (05:57).
#
# Por que uma op dedicada, e não a genérica AdminObject*: o
# `MailAccountGet` nativo devolve a **senha em texto claro** (a coluna `pw`
# vai direto para o hash de resposta). Passar isso pela allowlist genérica
# significaria que qualquer leitura da capa de administração traria senha de
# caixa postal na resposta HTTP. Aqui a senha é REMOVIDA antes de sair, e é o
# aceite A9.4 — a mesma guarda que o Bloco C aplica ao `UserPw` do agente.
#
# Read-only: nunca escreve no Znuny.
# --
# This software comes with ABSOLUTELY NO WARRANTY.
# --

package Kernel::GenericInterface::Operation::GertiAdmin::AdminMailAccountList;

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
        ErrorCode => 'AdminMailAccountList.MissingParameter', ErrorMessage => 'empty request!',
    ) if !IsHashRefWithData( $Param{Data} );
    my $TokenError = $Self->_CheckAccessToken( Data => $Param{Data} );
    return $TokenError if $TokenError;

    my $MailAccountObject = $Kernel::OM->Get('Kernel::System::MailAccount');
    my $QueueObject       = $Kernel::OM->Get('Kernel::System::Queue');

    # Valid => 0: telas de administração precisam ver (e poder revalidar) o que
    # foi invalidado. Esconder seria mentir sobre o estado da instância.
    my %List = $MailAccountObject->MailAccountList( Valid => 0 );

    my @Accounts;
    for my $ID ( sort { $a <=> $b } keys %List ) {
        my %A = $MailAccountObject->MailAccountGet( ID => $ID );
        next if !IsHashRefWithData( \%A );

        # A senha morre AQUI. Nunca entra no hash de resposta.
        delete @A{ grep {m{pw|password}xmsi} keys %A };

        my $QueueName = '';
        if ( $A{QueueID} ) {
            $QueueName = $QueueObject->QueueLookup( QueueID => $A{QueueID} ) || '';
        }

        push @Accounts, {
            ID            => $A{ID},
            Login         => $A{Login} // '',
            Host          => $A{Host} // '',
            Type          => $A{Type} // '',
            ValidID       => $A{ValidID} // 1,
            Trusted       => $A{Trusted} // 0,
            DispatchingBy => $A{DispatchingBy} // 'Queue',
            QueueID       => $A{QueueID} // 0,
            QueueName     => $QueueName,
            Comment       => $A{Comment} // '',
            IMAPFolder    => $A{IMAPFolder} // '',
            # Diz que EXISTE senha guardada, sem dizer qual. A tela usa isto
            # para mostrar "•••• (mantida)" em vez de um campo vazio, que
            # pareceria "não tem senha".
            HasPassword   => 1,
        };
    }

    return {
        Success => 1,
        Data    => { Accounts => \@Accounts },
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
