# znuny/Custom/Kernel/GenericInterface/Operation/GertiAdmin/AdminObjectAdd.pm
# --
# Gerti — Spec #4 (Bloco A), ADR D21. Creates a row of one allowlisted object
# (Queue/SLA/Service/Type/State/Priority). A field outside the object's
# allowlist is an explicit error (never silently dropped — an operator must
# never believe something saved that didn't). No delete operation exists in
# this spec; Znuny invalidates via ValidID = 2 through AdminObjectUpdate.
#
# Request:
#   { AccessToken, AgentLogin, Object, Fields: { <allowlisted attrs> } }
# Response:
#   { Object, ID, Item: { ID, <Fields...> } }
# --
package Kernel::GenericInterface::Operation::GertiAdmin::AdminObjectAdd;

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
        ErrorCode => 'AdminObjectAdd.MissingParameter', ErrorMessage => 'empty request!',
    ) if !IsHashRefWithData( $Param{Data} );

    my $TokenError = $Self->_CheckAccessToken( Data => $Param{Data} );
    return $TokenError if $TokenError;

    my $D = $Param{Data};

    return $Self->ReturnError(
        ErrorCode => 'AdminObjectAdd.MissingParameter', ErrorMessage => 'Object missing!',
    ) if !IsStringWithData( $D->{Object} );

    my $Spec = Kernel::GenericInterface::Operation::GertiAdmin::AdminSpec->Spec( $D->{Object} );
    return $Self->ReturnError(
        ErrorCode    => 'AdminObjectAdd.UnknownObject',
        ErrorMessage => "AdminObjectAdd: unknown object '$D->{Object}'.",
    ) if !$Spec;

    return $Self->ReturnError(
        ErrorCode => 'AdminObjectAdd.MissingParameter', ErrorMessage => 'AgentLogin missing!',
    ) if !IsStringWithData( $D->{AgentLogin} );

    my $UserObject = $Kernel::OM->Get('Kernel::System::User');
    my $UserID = $UserObject->UserLookup( UserLogin => $D->{AgentLogin}, Silent => 1 );
    return $Self->ReturnError(
        ErrorCode => 'AdminObjectAdd.UnknownAgent', ErrorMessage => 'agent login not found',
    ) if !$UserID;

    my $Fields = IsHashRefWithData( $D->{Fields} ) ? { %{ $D->{Fields} } } : {};

    my @Invalid = Kernel::GenericInterface::Operation::GertiAdmin::AdminSpec
        ->ValidateFields( $D->{Object}, $Fields );
    return $Self->ReturnError(
        ErrorCode    => 'AdminObjectAdd.InvalidField',
        ErrorMessage => "AdminObjectAdd: field(s) not allowed for '$D->{Object}': "
            . join( ', ', @Invalid ),
    ) if @Invalid;

    # ValidID defaults to 1 when the object allows it and the caller omitted
    # it (same convention as CustomerCompanyAdd's ValidID default).
    if ( grep { $_ eq 'ValidID' } @{ $Spec->{Fields} } ) {
        $Fields->{ValidID} = 1 if !defined $Fields->{ValidID} || $Fields->{ValidID} eq '';
    }

    # SLA::ServiceIDs must be an arrayref for SLAAdd (an already-empty
    # arrayref — "no linked services" — must stay [], not get wrapped again).
    if ( $D->{Object} eq 'SLA' && exists $Fields->{ServiceIDs} ) {
        my $Value = $Fields->{ServiceIDs};
        if ( ref $Value ne 'ARRAY' ) {
            $Fields->{ServiceIDs} = ( defined $Value && length $Value ) ? [$Value] : [];
        }
    }

    my @Missing = Kernel::GenericInterface::Operation::GertiAdmin::AdminSpec
        ->MissingRequired( $D->{Object}, $Fields );
    return $Self->ReturnError(
        ErrorCode    => 'AdminObjectAdd.MissingRequired',
        ErrorMessage => "AdminObjectAdd: required field(s) missing for '$D->{Object}': "
            . join( ', ', @Missing ),
    ) if @Missing;

    my $Module    = $Kernel::OM->Get( $Spec->{Module} );
    my $AddMethod = $Spec->{AddMethod};

    my $NewID = $Module->$AddMethod( %{$Fields}, UserID => $UserID );
    return $Self->ReturnError(
        ErrorCode    => 'AdminObjectAdd.AddError',
        ErrorMessage => "AdminObjectAdd: could not create '$D->{Object}'"
            . ' (maybe a duplicate name or rejected input).',
    ) if !$NewID;

    my $GetMethod = $Spec->{GetMethod};
    my %Row = $Module->$GetMethod( $Spec->{GetIDParam} => $NewID, UserID => $UserID );

    return {
        Success => 1,
        Data    => {
            Object => $D->{Object},
            ID     => $NewID,
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
