# znuny/Custom/Kernel/GenericInterface/Operation/GertiTicket/TimeAccountingSince.pm
# --
# Gerti — custom GI operation (Spec #1B). Read-only pull of native Znuny
# time_accounting rows (agent TimeUnits) with id > SinceId, for the sidecar
# reconciliation worker to turn into gerti.consumption_event. Read-only: never
# writes Znuny. Upgrade-safe Custom/ overlay (same as the other GertiTicket ops).
# --
package Kernel::GenericInterface::Operation::GertiTicket::TimeAccountingSince;

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
        ErrorCode => 'TimeAccountingSince.MissingParameter', ErrorMessage => 'empty request!',
    ) if !IsHashRefWithData( $Param{Data} );
    my $TokenError = $Self->_CheckAccessToken( Data => $Param{Data} );
    return $TokenError if $TokenError;

    my $D = $Param{Data};
    my $SinceId = $D->{SinceId};
    $SinceId = 0 if !defined $SinceId || $SinceId !~ /^\d+$/;
    my $Limit = $D->{Limit};
    $Limit = 500 if !defined $Limit || $Limit !~ /^\d+$/ || $Limit < 1 || $Limit > 2000;

    my $DBObject = $Kernel::OM->Get('Kernel::System::DB');
    return $Self->ReturnError(
        ErrorCode => 'TimeAccountingSince.DBError', ErrorMessage => 'prepare failed',
    # O JOIN em `ticket` traz o dono do chamado junto com o lançamento (T-R2.3).
    # Sem ele, uma hora lançada em chamado SEM vínculo contrato↔chamado — o caso
    # de todo chamado que entra por e-mail — é indistinguível de lixo, e o worker
    # a descarta em silêncio. Com o CustomerID em mãos, o worker resolve o tenant
    # e ou vincula ao único contrato ativo, ou registra a pendência.
    # LEFT JOIN de propósito: lançamento cujo ticket sumiu ainda precisa aparecer.
    ) if !$DBObject->Prepare(
        SQL => 'SELECT ta.id, ta.ticket_id, ta.article_id, ta.time_unit, ta.create_time, '
            . 't.customer_id, t.customer_user_id '
            . 'FROM time_accounting ta LEFT JOIN ticket t ON t.id = ta.ticket_id '
            . 'WHERE ta.id > ? ORDER BY ta.id ASC',
        Bind  => [ \$SinceId ],
        Limit => $Limit,
    );

    my @Entries;
    my $MaxId = $SinceId;
    while ( my @Row = $DBObject->FetchrowArray() ) {
        push @Entries, {
            Id             => $Row[0],
            TicketId       => $Row[1],
            ArticleId      => $Row[2],
            TimeUnit       => $Row[3],
            Created        => $Row[4],
            CustomerId     => $Row[5] // '',
            CustomerUserId => $Row[6] // '',
        };
        $MaxId = $Row[0] if $Row[0] > $MaxId;
    }

    return {
        Success => 1,
        Data    => { Entries => \@Entries, MaxId => $MaxId },
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
