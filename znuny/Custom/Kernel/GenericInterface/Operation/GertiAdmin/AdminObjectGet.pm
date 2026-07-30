# znuny/Custom/Kernel/GenericInterface/Operation/GertiAdmin/AdminObjectGet.pm
# --
# Gerti — Spec #4 (Bloco A), ADR D21. Reads a single row of one allowlisted
# object (Queue/SLA/Service/Type/State/Priority) live from Znuny. Same
# dispatcher guards as AdminObjectList: the request sends an object KEY,
# never a Perl class/method (see AdminSpec.pm).
#
# Request:
#   { AccessToken, AgentLogin, Object, ID }
# Response:
#   { Object, Item: { ID, <Fields...> } }
# --
package Kernel::GenericInterface::Operation::GertiAdmin::AdminObjectGet;

use strict;
use warnings;

use Kernel::System::VariableCheck qw(IsHashRefWithData IsStringWithData);
use Kernel::GenericInterface::Operation::GertiAdmin::AdminSpec;

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
        ErrorCode => 'AdminObjectGet.MissingParameter', ErrorMessage => 'empty request!',
    ) if !IsHashRefWithData( $Param{Data} );

    my $TokenError = $Self->_CheckAccessToken( Data => $Param{Data} );
    return $TokenError if $TokenError;

    my $D = $Param{Data};

    return $Self->ReturnError(
        ErrorCode => 'AdminObjectGet.MissingParameter', ErrorMessage => 'Object missing!',
    ) if !IsStringWithData( $D->{Object} );

    my $Spec = Kernel::GenericInterface::Operation::GertiAdmin::AdminSpec->Spec( $D->{Object} );
    return $Self->ReturnError(
        ErrorCode    => 'AdminObjectGet.UnknownObject',
        ErrorMessage => "AdminObjectGet: unknown object '$D->{Object}'.",
    ) if !$Spec;

    return $Self->ReturnError(
        ErrorCode => 'AdminObjectGet.MissingParameter', ErrorMessage => 'ID missing!',
    ) if !IsStringWithData( $D->{ID} );

    return $Self->ReturnError(
        ErrorCode => 'AdminObjectGet.MissingParameter', ErrorMessage => 'AgentLogin missing!',
    ) if !IsStringWithData( $D->{AgentLogin} );

    my $UserObject = $Kernel::OM->Get('Kernel::System::User');
    my $UserID = $UserObject->UserLookup( UserLogin => $D->{AgentLogin}, Silent => 1 );
    return $Self->ReturnError(
        ErrorCode => 'AdminObjectGet.UnknownAgent', ErrorMessage => 'agent login not found',
    ) if !$UserID;

    my $Module    = $Kernel::OM->Get( $Spec->{Module} );
    my $GetMethod = $Spec->{GetMethod};

    my %Row = $Module->$GetMethod( $Spec->{GetIDParam} => $D->{ID}, UserID => $UserID );
    return $Self->ReturnError(
        ErrorCode => 'AdminObjectGet.NotFound', ErrorMessage => 'object not found',
    ) if !%Row;

    return {
        Success => 1,
        Data    => {
            Object => $D->{Object},
            Item   => $Self->_ItemFromRow( Spec => $Spec, Row => \%Row ),
        },
    };
}

sub _ItemFromRow {
    my ( $Self, %Param ) = @_;

    my $Spec = $Param{Spec};
    my %Row  = %{ $Param{Row} };

    my %Item = ( ID => $Row{ $Spec->{GetIDField} } );
    for my $Field ( @{ $Spec->{Fields} } ) {
        $Item{$Field} = $Row{$Field};
    }

    return \%Item;
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
