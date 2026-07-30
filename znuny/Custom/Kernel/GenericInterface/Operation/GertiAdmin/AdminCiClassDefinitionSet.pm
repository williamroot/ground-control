# znuny/Custom/Kernel/GenericInterface/Operation/GertiAdmin/AdminCiClassDefinitionSet.pm
# --
# Gerti — custom GI operation (Spec #4, Bloco B). WRITE: new version of an ITSM
# CI class definition (YAML). Kernel::System::ITSMConfigItem::Definition
# (role) -> DefinitionCheck (MANDATORY, explicit, BEFORE DefinitionAdd) then
# DefinitionAdd (creates a NEW version — never overwrites, history stays in
# Znuny). A broken definition takes down the whole CMDB, so DefinitionCheck is
# NOT optional and its Znuny log message is surfaced back verbatim so the
# operator knows exactly why it was refused.
# Upgrade-safe Custom/ overlay.
# --
package Kernel::GenericInterface::Operation::GertiAdmin::AdminCiClassDefinitionSet;

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
        ErrorCode => 'AdminCiClassDefinitionSet.MissingParameter', ErrorMessage => 'empty request!',
    ) if !IsHashRefWithData( $Param{Data} );
    my $TokenError = $Self->_CheckAccessToken( Data => $Param{Data} );
    return $TokenError if $TokenError;

    my $D = $Param{Data};
    for my $Needed (qw(AgentLogin ClassID Definition)) {
        return $Self->ReturnError(
            ErrorCode => 'AdminCiClassDefinitionSet.MissingParameter', ErrorMessage => "$Needed missing!",
        ) if !IsStringWithData( $D->{$Needed} );
    }

    my $UserID = $Kernel::OM->Get('Kernel::System::User')->UserLookup(
        UserLogin => $D->{AgentLogin}, Silent => 1,
    );
    if ( !$UserID ) {
        return $Self->ReturnError(
            ErrorCode => 'AdminCiClassDefinitionSet.UnknownAgent', ErrorMessage => 'agent login not found',
        );
    }

    my $GeneralCatalogObject = $Kernel::OM->Get('Kernel::System::GeneralCatalog');
    my $ClassMap = $GeneralCatalogObject->ItemList( Class => 'ITSM::ConfigItem::Class', Valid => 0 ) || {};
    if ( !$ClassMap->{ $D->{ClassID} } ) {
        return $Self->ReturnError(
            ErrorCode => 'AdminCiClassDefinitionSet.NotFound', ErrorMessage => 'unknown ClassID',
        );
    }

    my $ConfigItemObject = $Kernel::OM->Get('Kernel::System::ITSMConfigItem');
    my $LogObject         = $Kernel::OM->Get('Kernel::System::Log');

    # ── Guardrail: DefinitionCheck is NOT optional. Explicit, BEFORE the write. ──
    my $CheckOK = $ConfigItemObject->DefinitionCheck( Definition => $D->{Definition} );
    if ( !$CheckOK ) {
        my $Msg = $LogObject->GetLogEntry( Type => 'error', What => 'Message' )
            || 'invalid definition (syntax error)';
        return $Self->ReturnError(
            ErrorCode => 'AdminCiClassDefinitionSet.InvalidDefinition', ErrorMessage => $Msg,
        );
    }

    my $DefinitionID = $ConfigItemObject->DefinitionAdd(
        ClassID    => $D->{ClassID},
        Definition => $D->{Definition},
        UserID     => $UserID,
    );

    if ( !$DefinitionID ) {
        # DefinitionAdd() refuses (returns undef, logs) if the definition is byte-identical
        # to the current one — treat that specific case as an idempotent no-op success,
        # not a failure, so re-saving an unchanged definition doesn't look broken to the
        # operator. Any other failure is a genuine write error, surfaced verbatim.
        my $Current = $ConfigItemObject->DefinitionGet( ClassID => $D->{ClassID} );
        if (
            IsHashRefWithData($Current)
            && $Current->{DefinitionID}
            && $Current->{Definition} eq $D->{Definition}
            )
        {
            return {
                Success => 1,
                Data    => {
                    ClassID      => $D->{ClassID},
                    DefinitionID => $Current->{DefinitionID},
                    Version      => $Current->{Version},
                    Unchanged    => 1,
                },
            };
        }

        my $Msg = $LogObject->GetLogEntry( Type => 'error', What => 'Message' )
            || 'could not save the definition';
        return $Self->ReturnError(
            ErrorCode => 'AdminCiClassDefinitionSet.WriteError', ErrorMessage => $Msg,
        );
    }

    my $Saved = $ConfigItemObject->DefinitionGet( DefinitionID => $DefinitionID );

    return {
        Success => 1,
        Data    => {
            ClassID      => $D->{ClassID},
            DefinitionID => $DefinitionID,
            Version      => $Saved ? $Saved->{Version} : undef,
            Unchanged    => 0,
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
