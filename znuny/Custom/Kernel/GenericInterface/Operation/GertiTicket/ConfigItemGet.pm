# znuny/Custom/Kernel/GenericInterface/Operation/GertiTicket/ConfigItemGet.pm
# --
# Gerti — custom GI operation (Spec #1K). Read-only detail of a single ITSM
# Config Item + its version attributes (XMLData). Ownership guard (anti-IDOR):
# the CI's native CustomerID attribute MUST match the requesting tenant's
# CustomerCompany, else NotFound (never leak another tenant's CI).
# Upgrade-safe Custom/ overlay (same pattern as the other GertiTicket ops).
# --
package Kernel::GenericInterface::Operation::GertiTicket::ConfigItemGet;

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
        ErrorCode => 'ConfigItemGet.MissingParameter', ErrorMessage => 'empty request!',
    ) if !IsHashRefWithData( $Param{Data} );
    my $TokenError = $Self->_CheckAccessToken( Data => $Param{Data} );
    return $TokenError if $TokenError;

    my $D = $Param{Data};
    for my $Needed (qw(ConfigItemID CustomerCompany)) {
        return $Self->ReturnError(
            ErrorCode => 'ConfigItemGet.MissingParameter', ErrorMessage => "$Needed missing!",
        ) if !IsStringWithData( $D->{$Needed} );
    }

    my $ConfigItemObject = $Kernel::OM->Get('Kernel::System::ITSMConfigItem');

    my $CI = $ConfigItemObject->ConfigItemGet( ConfigItemID => $D->{ConfigItemID} );
    my $V  = $ConfigItemObject->VersionGet(
        ConfigItemID => $D->{ConfigItemID},
        XMLDataGet   => 1,
    );

    # CI not found at all => NotFound (don't leak existence).
    if ( !IsHashRefWithData($CI) || !IsHashRefWithData($V) ) {
        return $Self->ReturnError(
            ErrorCode => 'ConfigItemGet.NotFound', ErrorMessage => 'config item not found',
        );
    }

    # Read the native CustomerID attribute from the version XMLData (R1K §4.2).
    my $CustomerID = eval { $V->{XMLData}->[1]{Version}[1]{CustomerID}[1]{Content} };

    # Ownership guard (anti-IDOR): CI of another tenant => NotFound.
    if ( !defined $CustomerID || $CustomerID ne $D->{CustomerCompany} ) {
        return $Self->ReturnError(
            ErrorCode => 'ConfigItemGet.NotFound', ErrorMessage => 'config item not found',
        );
    }

    # Extract any useful attributes from the version XMLData.
    my $SerialNumber = eval { $V->{XMLData}->[1]{Version}[1]{SerialNumber}[1]{Content} };

    my %Attributes;
    $Attributes{SerialNumber} = $SerialNumber if defined $SerialNumber;

    return {
        Success => 1,
        Data    => {
            Id         => $CI->{ConfigItemID},
            Number     => $CI->{Number},
            Class      => $CI->{Class},
            Name       => $V->{Name},
            DeplState  => $CI->{CurDeplState},
            InciState  => $CI->{CurInciState},
            CustomerID => $CustomerID,
            Attributes => \%Attributes,
        },
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
