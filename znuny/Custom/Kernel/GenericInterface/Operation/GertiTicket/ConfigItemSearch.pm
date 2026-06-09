# znuny/Custom/Kernel/GenericInterface/Operation/GertiTicket/ConfigItemSearch.pm
# --
# Gerti — custom GI operation (Spec #1K). Read-only search of ITSM Config Items
# scoped by the native CustomerID attribute (Type: CustomerCompany). Resolves
# the 5 CI class ids by name at runtime (ids are per-instance — never hardcode)
# and searches across all of them via ConfigItemSearchExtended + What.
# Upgrade-safe Custom/ overlay (same pattern as the other GertiTicket ops).
# --
package Kernel::GenericInterface::Operation::GertiTicket::ConfigItemSearch;

use strict;
use warnings;

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

    return $Self->ReturnError(
        ErrorCode => 'ConfigItemSearch.MissingParameter', ErrorMessage => 'empty request!',
    ) if !IsHashRefWithData( $Param{Data} );
    my $TokenError = $Self->_CheckAccessToken( Data => $Param{Data} );
    return $TokenError if $TokenError;

    my $D = $Param{Data};
    return $Self->ReturnError(
        ErrorCode => 'ConfigItemSearch.MissingParameter', ErrorMessage => 'CustomerCompany missing!',
    ) if !IsStringWithData( $D->{CustomerCompany} );

    # Resolve the CI class ids by name (per-instance ids — never hardcode).
    my $ClassRef = $Kernel::OM->Get('Kernel::System::GeneralCatalog')->ItemList(
        Class => 'ITSM::ConfigItem::Class',
    );
    my @ClassIDs = IsHashRefWithData($ClassRef) ? keys %{$ClassRef} : ();

    my $ConfigItemObject = $Kernel::OM->Get('Kernel::System::ITSMConfigItem');

    # Search by the native CustomerID attribute (Type: CustomerCompany).
    # Exact value (cru = LIKE without wildcards).
    my $ConfigItemIDs = $ConfigItemObject->ConfigItemSearchExtended(
        ClassIDs => \@ClassIDs,
        What     => [
            {
                "[%]{'Version'}[%]{'CustomerID'}[%]{'Content'}" => $D->{CustomerCompany},
            },
        ],
    );

    my @ConfigItems;
    if ( IsArrayRefWithData($ConfigItemIDs) ) {
        for my $ID ( @{$ConfigItemIDs} ) {
            my $CI = $ConfigItemObject->ConfigItemGet( ConfigItemID => $ID );
            next if !IsHashRefWithData($CI);
            # Name lives on the version, not the CI header (R1K §4.2).
            my $V = $ConfigItemObject->VersionGet( ConfigItemID => $ID, XMLDataGet => 0 );
            my $Name = ( IsHashRefWithData($V) && defined $V->{Name} ) ? $V->{Name} : $CI->{Name};
            push @ConfigItems, {
                Id        => $CI->{ConfigItemID},
                Number    => $CI->{Number},
                Class     => $CI->{Class},
                Name      => $Name,
                DeplState => $CI->{CurDeplState},
                InciState => $CI->{CurInciState},
            };
        }
    }

    return {
        Success => 1,
        Data    => { ConfigItems => \@ConfigItems },
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
