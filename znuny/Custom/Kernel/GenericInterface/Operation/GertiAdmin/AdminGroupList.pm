# znuny/Custom/Kernel/GenericInterface/Operation/GertiAdmin/AdminGroupList.pm
# --
# Gerti — custom GI operation (Spec #4, Bloco C). Read-only list of Znuny
# groups (Kernel::System::Group->GroupDataList). Feeds the agent<->group
# assignment screen — the console never persists it.
# Upgrade-safe Custom/ overlay.
# --
package Kernel::GenericInterface::Operation::GertiAdmin::AdminGroupList;

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
        ErrorCode => 'AdminGroupList.MissingParameter', ErrorMessage => 'empty request!',
    ) if !IsHashRefWithData( $Param{Data} );
    my $TokenError = $Self->_CheckAccessToken( Data => $Param{Data} );
    return $TokenError if $TokenError;

    my $D = $Param{Data};
    for my $Needed (qw(AgentLogin)) {
        return $Self->ReturnError(
            ErrorCode => 'AdminGroupList.MissingParameter', ErrorMessage => "$Needed missing!",
        ) if !IsStringWithData( $D->{$Needed} );
    }

    my $UserID = $Kernel::OM->Get('Kernel::System::User')->UserLookup(
        UserLogin => $D->{AgentLogin}, Silent => 1,
    );
    if ( !$UserID ) {
        return $Self->ReturnError(
            ErrorCode => 'AdminGroupList.UnknownAgent', ErrorMessage => 'agent login not found',
        );
    }

    my %GroupData = $Kernel::OM->Get('Kernel::System::Group')->GroupDataList();

    my @Groups;
    for my $GroupID ( sort { $a <=> $b } keys %GroupData ) {
        my $G = $GroupData{$GroupID};
        push @Groups, {
            GroupID => $GroupID,
            Name    => $G->{Name},
            ValidID => $G->{ValidID},
            Comment => $G->{Comment},
        };
    }

    return { Success => 1, Data => { Groups => \@Groups } };
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
