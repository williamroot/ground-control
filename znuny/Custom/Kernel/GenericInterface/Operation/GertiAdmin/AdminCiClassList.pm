# znuny/Custom/Kernel/GenericInterface/Operation/GertiAdmin/AdminCiClassList.pm
# --
# Gerti — custom GI operation (Spec #4, Bloco B). Read-only list of ITSM CI
# classes (Kernel::System::GeneralCatalog, class 'ITSM::ConfigItem::Class').
# The console never persists this — it reads it live on every render.
# Upgrade-safe Custom/ overlay (same pattern as the other Gerti* ops).
# --
package Kernel::GenericInterface::Operation::GertiAdmin::AdminCiClassList;

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
        ErrorCode => 'AdminCiClassList.MissingParameter', ErrorMessage => 'empty request!',
    ) if !IsHashRefWithData( $Param{Data} );
    my $TokenError = $Self->_CheckAccessToken( Data => $Param{Data} );
    return $TokenError if $TokenError;

    my $D = $Param{Data};
    for my $Needed (qw(AgentLogin)) {
        return $Self->ReturnError(
            ErrorCode => 'AdminCiClassList.MissingParameter', ErrorMessage => "$Needed missing!",
        ) if !IsStringWithData( $D->{$Needed} );
    }

    # AgentLogin must resolve to a real Znuny agent (same pattern as TimeAccountingAdd) —
    # an unauthenticated caller must not be able to enumerate CI classes.
    my $UserID = $Kernel::OM->Get('Kernel::System::User')->UserLookup(
        UserLogin => $D->{AgentLogin}, Silent => 1,
    );
    if ( !$UserID ) {
        return $Self->ReturnError(
            ErrorCode => 'AdminCiClassList.UnknownAgent', ErrorMessage => 'agent login not found',
        );
    }

    my $GeneralCatalogObject = $Kernel::OM->Get('Kernel::System::GeneralCatalog');

    # Valid => 0: the console must be able to show/administer invalidated classes too.
    my $ClassMap = $GeneralCatalogObject->ItemList( Class => 'ITSM::ConfigItem::Class', Valid => 0 ) || {};

    my @Classes;
    for my $ClassID ( sort { $a <=> $b } keys %{$ClassMap} ) {
        my $Item = $GeneralCatalogObject->ItemGet( ItemID => $ClassID ) || {};
        push @Classes, {
            ClassID => $ClassID,
            Name    => $ClassMap->{$ClassID},
            ValidID => $Item->{ValidID},
            Comment => $Item->{Comment},
        };
    }

    return { Success => 1, Data => { Classes => \@Classes } };
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
