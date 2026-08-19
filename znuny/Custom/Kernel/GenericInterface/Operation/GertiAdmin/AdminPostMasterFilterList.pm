# --
# Gerti — custom GI operation (T-R9.5, R9). Lista os filtros de PostMaster.
#
# *"visão centralizada dos domínios autorizados de todos os clientes"* (06:19) —
# é literalmente esta lista. Cada filtro que casa `From` por domínio e seta
# `X-OTRS-CustomerNo` é a regra "e-mail deste domínio pertence a este cliente".
#
# Não cabe nas ops genéricas: a API do PostMaster::Filter é por **nome**, não
# por id numérico, e o dispatcher genérico assume id.
#
# Read-only.
# --
# This software comes with ABSOLUTELY NO WARRANTY.
# --

package Kernel::GenericInterface::Operation::GertiAdmin::AdminPostMasterFilterList;

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
        ErrorCode => 'AdminPostMasterFilterList.MissingParameter',
        ErrorMessage => 'empty request!',
    ) if !IsHashRefWithData( $Param{Data} );
    my $TokenError = $Self->_CheckAccessToken( Data => $Param{Data} );
    return $TokenError if $TokenError;

    my $FilterObject = $Kernel::OM->Get('Kernel::System::PostMaster::Filter');
    my %List = $FilterObject->FilterList();

    my @Filters;
    for my $Name ( sort keys %List ) {
        my %F = $FilterObject->FilterGet( Name => $Name );
        next if !IsHashRefWithData( \%F );
        push @Filters, {
            Name           => $Name,
            StopAfterMatch => $F{StopAfterMatch} // 0,
            Match          => _Pairs( $F{Match} ),
            Set            => _Pairs( $F{Set} ),
        };
    }

    return { Success => 1, Data => { Filters => \@Filters } };
}

# O Znuny devolve Match/Set ora como arrayref de {Key,Value}, ora como hashref
# simples, dependendo da versão e de como o filtro foi gravado. Normalizamos
# para UMA forma (lista de pares) para o console não ter que adivinhar.
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
