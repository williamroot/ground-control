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
    ) if !$DBObject->Prepare(
        SQL => 'SELECT id, ticket_id, article_id, time_unit, create_time '
            . 'FROM time_accounting WHERE id > ? ORDER BY id ASC',
        Bind  => [ \$SinceId ],
        Limit => $Limit,
    );

    my @Entries;
    my $MaxId = $SinceId;
    while ( my @Row = $DBObject->FetchrowArray() ) {
        push @Entries, {
            Id        => $Row[0],
            TicketId  => $Row[1],
            ArticleId => $Row[2],
            TimeUnit  => $Row[3],
            Created   => $Row[4],
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
