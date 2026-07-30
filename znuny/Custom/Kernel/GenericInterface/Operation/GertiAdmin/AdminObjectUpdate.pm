# znuny/Custom/Kernel/GenericInterface/Operation/GertiAdmin/AdminObjectUpdate.pm
# --
# Gerti — Spec #4 (Bloco A), ADR D21. Updates a row of one allowlisted object
# (Queue/SLA/Service/Type/State/Priority). Znuny's native *Update() calls all
# require the FULL param set (they don't do partial column updates) — so this
# reads the current row first, overlays only the allowlisted fields the
# caller sent, and writes the merged result back. That is also how the
# invalidation guard in the plan works: PUT with Fields => { ValidID => 2 }
# is how the console "deletes" — there is no delete operation.
#
# Request:
#   { AccessToken, AgentLogin, Object, ID, Fields: { <allowlisted attrs> } }
# Response:
#   { Object, ID, Item: { ID, <Fields...> } }
# --
package Kernel::GenericInterface::Operation::GertiAdmin::AdminObjectUpdate;

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
        ErrorCode => 'AdminObjectUpdate.MissingParameter', ErrorMessage => 'empty request!',
    ) if !IsHashRefWithData( $Param{Data} );

    my $TokenError = $Self->_CheckAccessToken( Data => $Param{Data} );
    return $TokenError if $TokenError;

    my $D = $Param{Data};

    return $Self->ReturnError(
        ErrorCode => 'AdminObjectUpdate.MissingParameter', ErrorMessage => 'Object missing!',
    ) if !IsStringWithData( $D->{Object} );

    my $Spec = Kernel::GenericInterface::Operation::GertiAdmin::AdminSpec->Spec( $D->{Object} );
    return $Self->ReturnError(
        ErrorCode    => 'AdminObjectUpdate.UnknownObject',
        ErrorMessage => "AdminObjectUpdate: unknown object '$D->{Object}'.",
    ) if !$Spec;

    return $Self->ReturnError(
        ErrorCode => 'AdminObjectUpdate.MissingParameter', ErrorMessage => 'ID missing!',
    ) if !IsStringWithData( $D->{ID} );

    return $Self->ReturnError(
        ErrorCode => 'AdminObjectUpdate.MissingParameter', ErrorMessage => 'AgentLogin missing!',
    ) if !IsStringWithData( $D->{AgentLogin} );

    my $UserObject = $Kernel::OM->Get('Kernel::System::User');
    my $UserID = $UserObject->UserLookup( UserLogin => $D->{AgentLogin}, Silent => 1 );
    return $Self->ReturnError(
        ErrorCode => 'AdminObjectUpdate.UnknownAgent', ErrorMessage => 'agent login not found',
    ) if !$UserID;

    my $RequestedFields = IsHashRefWithData( $D->{Fields} ) ? $D->{Fields} : {};

    my @Invalid = Kernel::GenericInterface::Operation::GertiAdmin::AdminSpec
        ->ValidateFields( $D->{Object}, $RequestedFields );
    return $Self->ReturnError(
        ErrorCode    => 'AdminObjectUpdate.InvalidField',
        ErrorMessage => "AdminObjectUpdate: field(s) not allowed for '$D->{Object}': "
            . join( ', ', @Invalid ),
    ) if @Invalid;

    my $Module    = $Kernel::OM->Get( $Spec->{Module} );
    my $GetMethod = $Spec->{GetMethod};

    my %Current = $Module->$GetMethod( $Spec->{GetIDParam} => $D->{ID}, UserID => $UserID );
    return $Self->ReturnError(
        ErrorCode => 'AdminObjectUpdate.NotFound', ErrorMessage => 'object not found',
    ) if !%Current;

    # Merge: allowlisted fields the caller sent win, everything else keeps
    # its current value — the native *Update() calls require the full
    # param set, not a partial diff.
    my %Merged;
    for my $Field ( @{ $Spec->{Fields} } ) {
        $Merged{$Field} = exists $RequestedFields->{$Field}
            ? $RequestedFields->{$Field}
            : $Current{$Field};
    }

    # ServiceIDs must stay an arrayref — including an already-empty one
    # ("no linked services"), which must not get wrapped into [ [] ].
    if ( $D->{Object} eq 'SLA' && ref $Merged{ServiceIDs} ne 'ARRAY' ) {
        $Merged{ServiceIDs} = ( defined $Merged{ServiceIDs} && length $Merged{ServiceIDs} )
            ? [ $Merged{ServiceIDs} ]
            : [];
    }

    my $UpdateMethod = $Spec->{UpdateMethod};

    my $OK = $Module->$UpdateMethod(
        $Spec->{UpdateIDParam} => $D->{ID},
        %Merged,
        UserID => $UserID,
    );
    return $Self->ReturnError(
        ErrorCode    => 'AdminObjectUpdate.UpdateError',
        ErrorMessage => "AdminObjectUpdate: could not update '$D->{Object}'"
            . ' (maybe a duplicate name or rejected input).',
    ) if !$OK;

    my %Row = $Module->$GetMethod( $Spec->{GetIDParam} => $D->{ID}, UserID => $UserID );

    return {
        Success => 1,
        Data    => {
            Object => $D->{Object},
            ID     => $D->{ID},
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
