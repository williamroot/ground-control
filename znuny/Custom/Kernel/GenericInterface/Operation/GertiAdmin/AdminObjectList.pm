# znuny/Custom/Kernel/GenericInterface/Operation/GertiAdmin/AdminObjectList.pm
# --
# Gerti — Spec #4 (Bloco A), ADR D21. Lists every row of one allowlisted
# object (Queue/SLA/Service/Type/State/Priority/SystemAddress), reading the
# native Znuny API live — the console persists nothing, this operation is the
# read side of that contract. Also returns the support lists (GroupList/
# StateTypeList/ValidList/CalendarList/SystemAddressList/SalutationList/
# SignatureList) so the console can render selects without a second round
# trip. The request sends an object KEY, never a Perl class/method — see
# AdminSpec.pm for the allowlist that translates it.
#
# T-R9.2: the last three support lists exist because Queue's RequiredOnAdd
# demands SystemAddressID/SalutationID/SignatureID and the console had no way
# to discover valid ids — creating a queue failed every time.
#
# Request:
#   { AccessToken, AgentLogin, Object }
# Response:
#   { Object, Items: [ { ID, <Fields...> }, ... ],
#     GroupList, StateTypeList, ValidList, CalendarList,
#     SystemAddressList, SalutationList, SignatureList }
# --
package Kernel::GenericInterface::Operation::GertiAdmin::AdminObjectList;

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
        ErrorCode => 'AdminObjectList.MissingParameter', ErrorMessage => 'empty request!',
    ) if !IsHashRefWithData( $Param{Data} );

    my $TokenError = $Self->_CheckAccessToken( Data => $Param{Data} );
    return $TokenError if $TokenError;

    my $D = $Param{Data};

    return $Self->ReturnError(
        ErrorCode => 'AdminObjectList.MissingParameter', ErrorMessage => 'Object missing!',
    ) if !IsStringWithData( $D->{Object} );

    my $Spec = Kernel::GenericInterface::Operation::GertiAdmin::AdminSpec->Spec( $D->{Object} );
    return $Self->ReturnError(
        ErrorCode    => 'AdminObjectList.UnknownObject',
        ErrorMessage => "AdminObjectList: unknown object '$D->{Object}'.",
    ) if !$Spec;

    return $Self->ReturnError(
        ErrorCode => 'AdminObjectList.MissingParameter', ErrorMessage => 'AgentLogin missing!',
    ) if !IsStringWithData( $D->{AgentLogin} );

    my $UserObject = $Kernel::OM->Get('Kernel::System::User');
    my $UserID = $UserObject->UserLookup( UserLogin => $D->{AgentLogin}, Silent => 1 );
    return $Self->ReturnError(
        ErrorCode => 'AdminObjectList.UnknownAgent', ErrorMessage => 'agent login not found',
    ) if !$UserID;

    my $Module     = $Kernel::OM->Get( $Spec->{Module} );
    my $ListMethod = $Spec->{ListMethod};
    my $GetMethod  = $Spec->{GetMethod};

    # Valid => 0: admin screens must also see (and be able to re-validate)
    # invalidated rows, not just the active ones.
    my %Ids = $Module->$ListMethod( Valid => 0, UserID => $UserID );

    my @Items;
    for my $ID ( sort { $a <=> $b } keys %Ids ) {
        my %Row = $Module->$GetMethod( $Spec->{GetIDParam} => $ID, UserID => $UserID );
        next if !%Row;
        push @Items, $Self->_ItemFromRow( Spec => $Spec, Row => \%Row );
    }

    return {
        Success => 1,
        Data    => {
            Object        => $D->{Object},
            Items         => \@Items,
            GroupList     => { $Kernel::OM->Get('Kernel::System::Group')->GroupList( Valid => 0 ) },
            StateTypeList => {
                $Kernel::OM->Get('Kernel::System::State')->StateTypeList( UserID => $UserID )
            },
            ValidList    => { $Kernel::OM->Get('Kernel::System::Valid')->ValidList() },
            CalendarList => $Self->_CalendarList(),

            # T-R9.2 — the three lists a queue form needs. Valid => 0 for the
            # same reason as above: admin screens must see (and be able to
            # re-validate) invalidated rows. Both SalutationList and
            # SignatureList take Valid only (no UserID) in 7.2.3 core.
            SystemAddressList => $Self->_SystemAddressList(),
            SalutationList    => {
                $Kernel::OM->Get('Kernel::System::Salutation')->SalutationList( Valid => 0 )
            },
            SignatureList => {
                $Kernel::OM->Get('Kernel::System::Signature')->SignatureList( Valid => 0 )
            },
        },
    };
}

# Native SystemAddressList labels each row with the bare e-mail (value0) only,
# so an operator picking "which address does this queue answer from" sees no
# human name at all. We keep the exact { id => label } shape of every other
# support list and only enrich the LABEL, composing it from the two columns
# SystemAddressGet already returns (Realname + Name) — no invented field, no
# extra key, nothing persisted. Falls back to the bare e-mail when Realname is
# empty or identical to it.
sub _SystemAddressList {
    my ($Self) = @_;

    my $SystemAddressObject = $Kernel::OM->Get('Kernel::System::SystemAddress');

    # Valid => 0 lists invalid rows too (7.2.3: any defined-but-false Valid).
    my %Ids = $SystemAddressObject->SystemAddressList( Valid => 0 );

    my %List;
    for my $ID ( keys %Ids ) {
        my %Row = $SystemAddressObject->SystemAddressGet( ID => $ID );

        my $Email    = ( defined $Row{Name} && length $Row{Name} ) ? $Row{Name} : $Ids{$ID};
        my $Realname = $Row{Realname} // '';

        $List{$ID} = ( length $Realname && $Realname ne $Email )
            ? "$Realname <$Email>"
            : $Email;
    }

    return \%List;
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

# Mirrors Kernel::Modules::AdminQueue::_Edit()'s calendar select construction
# so the console gets the exact same labels/ids the native Znuny admin UI uses.
sub _CalendarList {
    my ($Self) = @_;

    my $ConfigObject = $Kernel::OM->Get('Kernel::Config');
    my %Calendar = ( '' => '-' );
    my $Maximum = $ConfigObject->Get('MaximumCalendarNumber') || 50;

    for my $CalendarNumber ( '', 1 .. $Maximum ) {
        if ( $ConfigObject->Get("TimeVacationDays::Calendar$CalendarNumber") ) {
            $Calendar{$CalendarNumber} = 'Calendar ' . $CalendarNumber . ' - '
                . ( $ConfigObject->Get( 'TimeZone::Calendar' . $CalendarNumber . 'Name' ) // '' );
        }
    }

    return \%Calendar;
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
