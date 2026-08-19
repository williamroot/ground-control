# --
# Gerti — custom GI operation (T-R9.5, R9). Cria, atualiza ou remove um filtro
# de PostMaster (a regra "e-mail deste domínio é deste cliente").
#
# O Znuny **não tem** `FilterUpdate`: só `FilterAdd` e `FilterDelete`. Atualizar
# é apagar e recriar sob o mesmo nome — e é isso que esta op faz, com duas
# guardas que a diferença exige:
#
#  • em modo update (`Mode => 'update'`), **recusa** nome inexistente. Sem isso,
#    um erro de digitação criaria um filtro novo em vez de editar o pretendido,
#    silenciosamente;
#  • em modo create, **recusa** nome já existente, pelo mesmo motivo ao contrário.
#
# **Exceção declarada à regra "sem exclusão" do projeto** (invariante 3): o
# filtro de PostMaster não tem `ValidID`, então não há como invalidar — só
# apagar. A exceção vale só para este objeto, e o estado anterior COMPLETO vai
# na resposta, para a auditoria do sidecar poder registrá-lo antes de sumir.
# --
# This software comes with ABSOLUTELY NO WARRANTY.
# --

package Kernel::GenericInterface::Operation::GertiAdmin::AdminPostMasterFilterSet;

use strict;
use warnings;

use Kernel::System::VariableCheck qw(IsArrayRefWithData IsHashRefWithData IsStringWithData);

use parent qw(Kernel::GenericInterface::Operation::Common);

our $ObjectManagerDisabled = 1;

# Cabeçalhos que um filtro pode SETAR. Allowlist explícita: `Set` é a parte
# perigosa (define dono, fila, prioridade do chamado que entra), e deixá-la
# aberta permitiria escrever qualquer X-OTRS-* pela API do console.
my @ALLOWED_SET_KEYS = qw(
    X-OTRS-CustomerNo
    X-OTRS-CustomerUser
    X-OTRS-Queue
    X-OTRS-Priority
    X-OTRS-State
    X-OTRS-Type
    X-OTRS-Service
    X-OTRS-Ignore
);

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
        ErrorCode => 'AdminPostMasterFilterSet.MissingParameter',
        ErrorMessage => 'empty request!',
    ) if !IsHashRefWithData( $Param{Data} );
    my $TokenError = $Self->_CheckAccessToken( Data => $Param{Data} );
    return $TokenError if $TokenError;

    my $D = $Param{Data};
    return $Self->ReturnError(
        ErrorCode => 'AdminPostMasterFilterSet.MissingParameter', ErrorMessage => 'Name is required',
    ) if !IsStringWithData( $D->{Name} );

    my $Mode = $D->{Mode} // 'create';
    if ( $Mode ne 'create' && $Mode ne 'update' && $Mode ne 'delete' ) {
        return $Self->ReturnError(
            ErrorCode    => 'AdminPostMasterFilterSet.InvalidMode',
            ErrorMessage => "Mode must be create, update or delete (got '$Mode')",
        );
    }

    my $FilterObject = $Kernel::OM->Get('Kernel::System::PostMaster::Filter');
    my %Existing = $FilterObject->FilterGet( Name => $D->{Name} );
    my $Exists   = IsHashRefWithData( \%Existing ) ? 1 : 0;

    if ( $Mode eq 'create' && $Exists ) {
        return $Self->ReturnError(
            ErrorCode    => 'AdminPostMasterFilterSet.AlreadyExists',
            ErrorMessage => "a filter named '$D->{Name}' already exists",
        );
    }
    if ( $Mode ne 'create' && !$Exists ) {
        return $Self->ReturnError(
            ErrorCode    => 'AdminPostMasterFilterSet.NotFound',
            ErrorMessage => "no filter named '$D->{Name}'",
        );
    }

    # Estado anterior completo, para a auditoria registrar antes de sumir.
    my %Before = $Exists
        ? (
            Name           => $D->{Name},
            StopAfterMatch => $Existing{StopAfterMatch} // 0,
            Match          => _Pairs( $Existing{Match} ),
            Set            => _Pairs( $Existing{Set} ),
        )
        : ();

    if ( $Mode eq 'delete' ) {
        my $OK = $FilterObject->FilterDelete( Name => $D->{Name} );
        return $Self->ReturnError(
            ErrorCode => 'AdminPostMasterFilterSet.WriteError', ErrorMessage => 'delete failed',
        ) if !$OK;
        return { Success => 1, Data => { Action => 'deleted', Before => \%Before } };
    }

    my $Match = _NormalizeIn( $D->{Match} );
    my $Set   = _NormalizeIn( $D->{Set} );

    return $Self->ReturnError(
        ErrorCode    => 'AdminPostMasterFilterSet.MissingParameter',
        ErrorMessage => 'Match must have at least one Key/Value pair',
    ) if !IsArrayRefWithData($Match);
    return $Self->ReturnError(
        ErrorCode    => 'AdminPostMasterFilterSet.MissingParameter',
        ErrorMessage => 'Set must have at least one Key/Value pair',
    ) if !IsArrayRefWithData($Set);

    for my $Pair ( @{$Set} ) {
        if ( !grep { $_ eq $Pair->{Key} } @ALLOWED_SET_KEYS ) {
            return $Self->ReturnError(
                ErrorCode    => 'AdminPostMasterFilterSet.UnknownField',
                ErrorMessage => "'$Pair->{Key}' is not a settable header (allowed: @ALLOWED_SET_KEYS)",
            );
        }
    }

    # Update = delete + add sob o mesmo nome (não existe FilterUpdate nativo).
    if ($Exists) {
        $FilterObject->FilterDelete( Name => $D->{Name} );
    }

    my $OK = $FilterObject->FilterAdd(
        Name           => $D->{Name},
        Match          => $Match,
        Set            => $Set,
        StopAfterMatch => $D->{StopAfterMatch} ? 1 : 0,
        UserID         => 1,
    );

    if ( !$OK ) {
        # Falhou depois do delete: tenta repor o que existia, para não deixar o
        # sistema pior do que estava.
        if ($Exists) {
            $FilterObject->FilterAdd(
                Name           => $D->{Name},
                Match          => _Pairs( $Existing{Match} ),
                Set            => _Pairs( $Existing{Set} ),
                StopAfterMatch => $Existing{StopAfterMatch} // 0,
                UserID         => 1,
            );
        }
        my $Msg = $Kernel::OM->Get('Kernel::System::Log')->GetLogEntry(
            Type => 'error', What => 'Message',
        ) || 'could not save the PostMaster filter';
        return $Self->ReturnError(
            ErrorCode => 'AdminPostMasterFilterSet.WriteError', ErrorMessage => $Msg,
        );
    }

    return {
        Success => 1,
        Data    => {
            Action => $Exists ? 'updated' : 'created',
            Before => \%Before,
            Filter => {
                Name           => $D->{Name},
                StopAfterMatch => $D->{StopAfterMatch} ? 1 : 0,
                Match          => $Match,
                Set            => $Set,
            },
        },
    };
}

sub _NormalizeIn {
    my ($Value) = @_;
    my @Out;
    return \@Out if ref $Value ne 'ARRAY';
    for my $Item ( @{$Value} ) {
        next if ref $Item ne 'HASH';
        next if !IsStringWithData( $Item->{Key} );
        push @Out, { Key => $Item->{Key}, Value => $Item->{Value} // '' };
    }
    return \@Out;
}

sub _Pairs {
    my ($Value) = @_;
    my @Out;
    if ( ref $Value eq 'ARRAY' ) {
        for my $Item ( @{$Value} ) {
            next if ref $Item ne 'HASH';
            push @Out, { Key => $Item->{Key} // '', Value => $Item->{Value} // '' };
        }
    }
    elsif ( ref $Value eq 'HASH' ) {
        for my $Key ( sort keys %{$Value} ) {
            push @Out, { Key => $Key, Value => $Value->{$Key} // '' };
        }
    }
    return \@Out;
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
