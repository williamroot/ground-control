# znuny/Custom/Kernel/GenericInterface/Operation/GertiTicket/ConfigItemUpsert.pm
# --
# Gerti — custom GI operation (Spec #1R-a). WRITE path into the ITSM CMDB:
# create OR update a Config Item from the inventory agent enrollment/heartbeat.
#
# Security (the core of #1R): the CustomerCompany is the tenant that OWNS the
# enroll token, resolved server-side by the sidecar — never the agent's input.
# Token of tenant A is structurally incapable of writing into B.
#
# Anti-IDOR on UPDATE: when ConfigItemID is given we read the CI's CURRENT
# CustomerID attribute and require it to equal the requested CustomerCompany,
# else NotFound (never let a token mutate another tenant's CI).
#
# ClassID/DeplStateID/InciStateID are resolved by NAME via GeneralCatalog
# (the numeric ids are per-instance — same lesson as seed-cmdb.pl).
# XMLData shape is the frozen one: [undef,{Version=>[undef,{<Key>=>[undef,{Content=>$v}]}]}].
# Upgrade-safe Custom/ overlay (same pattern as ConfigItemGet.pm).
# --
package Kernel::GenericInterface::Operation::GertiTicket::ConfigItemUpsert;

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
        ErrorCode => 'ConfigItemUpsert.MissingParameter', ErrorMessage => 'empty request!',
    ) if !IsHashRefWithData( $Param{Data} );
    my $TokenError = $Self->_CheckAccessToken( Data => $Param{Data} );
    return $TokenError if $TokenError;

    my $D = $Param{Data};
    for my $Needed (qw(CustomerCompany Name)) {
        return $Self->ReturnError(
            ErrorCode => 'ConfigItemUpsert.MissingParameter', ErrorMessage => "$Needed missing!",
        ) if !IsStringWithData( $D->{$Needed} );
    }

    my $Class     = $D->{ConfigItemClass} || 'Computer';
    my $DeplState = $D->{DeplState}        || 'Production';
    my $InciState = $D->{InciState}        || 'Operational';

    my $ConfigItemObject   = $Kernel::OM->Get('Kernel::System::ITSMConfigItem');
    my $GeneralCatalogObj  = $Kernel::OM->Get('Kernel::System::GeneralCatalog');

    # ── resolve ids by NAME (per-instance ids; never hardcode). ──────────────
    my %CLASS = reverse %{ $GeneralCatalogObj->ItemList( Class => 'ITSM::ConfigItem::Class' ) || {} };
    my %DEPL  = reverse %{ $GeneralCatalogObj->ItemList( Class => 'ITSM::ConfigItem::DeploymentState' ) || {} };
    my %INCI  = reverse %{ $GeneralCatalogObj->ItemList( Class => 'ITSM::Core::IncidentState' ) || {} };

    my $ClassID = $CLASS{$Class};
    if ( !$ClassID ) {
        return $Self->ReturnError(
            ErrorCode => 'ConfigItemUpsert.BadClass', ErrorMessage => "unknown class '$Class'",
        );
    }
    my $DeplStateID = $DEPL{$DeplState};
    my $InciStateID = $INCI{$InciState};
    if ( !$DeplStateID || !$InciStateID ) {
        return $Self->ReturnError(
            ErrorCode    => 'ConfigItemUpsert.BadState',
            ErrorMessage => "unknown DeplState/InciState",
        );
    }

    # Current definition of the class (for VersionAdd).
    my $Definition = $ConfigItemObject->DefinitionGet( ClassID => $ClassID );
    if ( !$Definition || !$Definition->{DefinitionID} ) {
        return $Self->ReturnError(
            ErrorCode    => 'ConfigItemUpsert.NoDefinition',
            ErrorMessage => "no definition for class '$Class'",
        );
    }
    my $DefinitionID = $Definition->{DefinitionID};

    # ── Build the XMLData node: native CustomerID (tenant scope) + Fingerprint
    #    + any extra attributes. CustomerID is server-trusted (== CustomerCompany).
    my %Ver = ( CustomerID => [ undef, { Content => $D->{CustomerCompany} } ] );
    if ( IsStringWithData( $D->{Fingerprint} ) ) {
        $Ver{Fingerprint} = [ undef, { Content => $D->{Fingerprint} } ];
    }
    my $Attributes = IsHashRefWithData( $D->{Attributes} ) ? $D->{Attributes} : {};
    for my $Key ( sort keys %{$Attributes} ) {
        my $Value = $Attributes->{$Key};
        next if !defined $Value || $Value eq '';
        $Ver{$Key} = [ undef, { Content => "$Value" } ];
    }
    my $XMLData = [ undef, { Version => [ undef, \%Ver ] } ];

    my $ConfigItemID = $D->{ConfigItemID};
    my $Action;

    if ( $ConfigItemID ) {
        # ── UPDATE: anti-IDOR — the CI's CURRENT CustomerID must match. ──────
        my $Current = $ConfigItemObject->VersionGet(
            ConfigItemID => $ConfigItemID,
            XMLDataGet   => 1,
        );
        if ( !IsHashRefWithData($Current) ) {
            return $Self->ReturnError(
                ErrorCode => 'ConfigItemUpsert.NotFound', ErrorMessage => 'config item not found',
            );
        }
        my $CurrentCustomerID = eval { $Current->{XMLData}->[1]{Version}[1]{CustomerID}[1]{Content} };
        if ( !defined $CurrentCustomerID || $CurrentCustomerID ne $D->{CustomerCompany} ) {
            # Belongs to another tenant (or none) => NotFound (never leak/mutate).
            return $Self->ReturnError(
                ErrorCode => 'ConfigItemUpsert.NotFound', ErrorMessage => 'config item not found',
            );
        }
        $Action = 'updated';
    }
    else {
        # ── CREATE: shell + first version. ───────────────────────────────────
        $ConfigItemID = $ConfigItemObject->ConfigItemAdd(
            ClassID => $ClassID,
            UserID  => 1,
        );
        if ( !$ConfigItemID ) {
            return $Self->ReturnError(
                ErrorCode => 'ConfigItemUpsert.AddFailed', ErrorMessage => 'ConfigItemAdd failed',
            );
        }
        $Action = 'created';
    }

    my $VersionID = $ConfigItemObject->VersionAdd(
        ConfigItemID => $ConfigItemID,
        Name         => $D->{Name},
        DefinitionID => $DefinitionID,
        DeplStateID  => $DeplStateID,
        InciStateID  => $InciStateID,
        UserID       => 1,
        XMLData      => $XMLData,
    );
    if ( !$VersionID ) {
        return $Self->ReturnError(
            ErrorCode => 'ConfigItemUpsert.VersionFailed', ErrorMessage => 'VersionAdd failed',
        );
    }

    my $CI = $ConfigItemObject->ConfigItemGet( ConfigItemID => $ConfigItemID );

    return {
        Success => 1,
        Data    => {
            ConfigItemID => $ConfigItemID,
            VersionID    => $VersionID,
            Number       => ( $CI ? $CI->{Number} : undef ),
            Action       => $Action,
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
