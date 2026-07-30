# znuny/Custom/Kernel/GenericInterface/Operation/GertiAdmin/AdminCiClassDefinitionGet.pm
# --
# Gerti — custom GI operation (Spec #4, Bloco B). Read-only: current definition
# (YAML) of one ITSM CI class. Kernel::System::ITSMConfigItem::Definition
# (role) -> DefinitionGet(ClassID). Read-only, never persisted by the console.
# Upgrade-safe Custom/ overlay.
# --
package Kernel::GenericInterface::Operation::GertiAdmin::AdminCiClassDefinitionGet;

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
        ErrorCode => 'AdminCiClassDefinitionGet.MissingParameter', ErrorMessage => 'empty request!',
    ) if !IsHashRefWithData( $Param{Data} );
    my $TokenError = $Self->_CheckAccessToken( Data => $Param{Data} );
    return $TokenError if $TokenError;

    my $D = $Param{Data};
    for my $Needed (qw(AgentLogin ClassID)) {
        return $Self->ReturnError(
            ErrorCode => 'AdminCiClassDefinitionGet.MissingParameter', ErrorMessage => "$Needed missing!",
        ) if !IsStringWithData( $D->{$Needed} );
    }

    my $UserID = $Kernel::OM->Get('Kernel::System::User')->UserLookup(
        UserLogin => $D->{AgentLogin}, Silent => 1,
    );
    if ( !$UserID ) {
        return $Self->ReturnError(
            ErrorCode => 'AdminCiClassDefinitionGet.UnknownAgent', ErrorMessage => 'agent login not found',
        );
    }

    my $GeneralCatalogObject = $Kernel::OM->Get('Kernel::System::GeneralCatalog');
    my $ClassMap = $GeneralCatalogObject->ItemList( Class => 'ITSM::ConfigItem::Class', Valid => 0 ) || {};
    my $ClassName = $ClassMap->{ $D->{ClassID} };

    if ( !$ClassName ) {
        return $Self->ReturnError(
            ErrorCode => 'AdminCiClassDefinitionGet.NotFound', ErrorMessage => 'unknown ClassID',
        );
    }

    my $Definition = $Kernel::OM->Get('Kernel::System::ITSMConfigItem')->DefinitionGet(
        ClassID => $D->{ClassID},
    );

    if ( !IsHashRefWithData($Definition) || !$Definition->{DefinitionID} ) {
        return $Self->ReturnError(
            ErrorCode => 'AdminCiClassDefinitionGet.NotFound', ErrorMessage => 'no definition for this class',
        );
    }

    return {
        Success => 1,
        Data    => {
            ClassID      => $D->{ClassID},
            ClassName    => $ClassName,
            DefinitionID => $Definition->{DefinitionID},
            Version      => $Definition->{Version},
            Definition   => $Definition->{Definition},    # raw YAML string — console edits/validates this
            CreateTime   => $Definition->{CreateTime},
            CreateBy     => $Definition->{CreateBy},
        },
    };
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
