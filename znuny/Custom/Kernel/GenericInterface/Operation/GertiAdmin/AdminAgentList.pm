# znuny/Custom/Kernel/GenericInterface/Operation/GertiAdmin/AdminAgentList.pm
# --
# Gerti — custom GI operation (Spec #4, Bloco C). Read-only list of Znuny
# agents (Kernel::System::User). Guardrail: UserPw (password hash) is NEVER
# returned — filtered explicitly on every entry, never trusted to just be
# "not selected".
# Upgrade-safe Custom/ overlay.
# --
package Kernel::GenericInterface::Operation::GertiAdmin::AdminAgentList;

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
        ErrorCode => 'AdminAgentList.MissingParameter', ErrorMessage => 'empty request!',
    ) if !IsHashRefWithData( $Param{Data} );
    my $TokenError = $Self->_CheckAccessToken( Data => $Param{Data} );
    return $TokenError if $TokenError;

    my $D = $Param{Data};
    for my $Needed (qw(AgentLogin)) {
        return $Self->ReturnError(
            ErrorCode => 'AdminAgentList.MissingParameter', ErrorMessage => "$Needed missing!",
        ) if !IsStringWithData( $D->{$Needed} );
    }

    my $UserObject = $Kernel::OM->Get('Kernel::System::User');
    my $UserID     = $UserObject->UserLookup( UserLogin => $D->{AgentLogin}, Silent => 1 );
    if ( !$UserID ) {
        return $Self->ReturnError(
            ErrorCode => 'AdminAgentList.UnknownAgent', ErrorMessage => 'agent login not found',
        );
    }

    # Valid => 0: the console must be able to see/reactivate invalidated agents too.
    my %Logins = $UserObject->UserList( Type => 'Short', Valid => 0, NoOutOfOffice => 1 );

    my @Agents;
    for my $AgentUserID ( sort { $a <=> $b } keys %Logins ) {
        my %Agent = $UserObject->GetUserData( UserID => $AgentUserID, NoOutOfOffice => 1 );
        next if !%Agent;

        # Guardrail: never leak the password hash (or anything password-shaped).
        delete @Agent{ grep { /pw/i } keys %Agent };

        push @Agents, {
            UserID        => $Agent{UserID},
            UserLogin     => $Agent{UserLogin},
            UserFirstname => $Agent{UserFirstname},
            UserLastname  => $Agent{UserLastname},
            UserEmail     => $Agent{UserEmail},
            ValidID       => $Agent{ValidID},
        };
    }

    return { Success => 1, Data => { Agents => \@Agents } };
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
