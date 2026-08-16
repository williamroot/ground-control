# --
# Gerti — custom Generic Interface operation (T-R2.2, Onda 1 / R2 do vídeo).
# Read-only list of the CustomerUsers belonging to one CustomerID.
#
# Why it exists: the console lists a customer's people from OUR table
# (`gerti.portal_user_role`), so anybody created straight inside the Znuny panel
# — or, from R9 on, auto-created by the PostMaster — is INVISIBLE in the
# console. Decision D-C makes the Znuny the owner of identity; this op is how
# the console reads that owner.
#
# Includes invalid (deactivated) users on purpose: "sem exclusão" (invariante 3)
# means a deactivated person still exists and must remain visible, marked.
#
# Read-only: never writes Znuny.
# --
# This software comes with ABSOLUTELY NO WARRANTY.
# --

package Kernel::GenericInterface::Operation::CustomerUser::CustomerUserList;

use strict;
use warnings;

use Kernel::System::VariableCheck qw(IsHashRefWithData IsStringWithData);

use parent qw(
    Kernel::GenericInterface::Operation::Common
);

our $ObjectManagerDisabled = 1;

# Hard cap: a runaway CustomerID must not turn one console render into a
# thousand CustomerUserDataGet round-trips.
my $MAX_USERS = 500;

=head1 NAME

Kernel::GenericInterface::Operation::CustomerUser::CustomerUserList
- GenericInterface CustomerUser List operation backend (Gerti custom).

=head2 new()

usually created via Kernel::GenericInterface::Operation->new();

=cut

sub new {
    my ( $Type, %Param ) = @_;

    my $Self = {};
    bless( $Self, $Type );

    for my $Needed (qw(DebuggerObject WebserviceID)) {
        if ( !$Param{$Needed} ) {
            return {
                Success      => 0,
                ErrorMessage => "Got no $Needed!",
            };
        }
        $Self->{$Needed} = $Param{$Needed};
    }

    return $Self;
}

=head2 Run()

List the CustomerUsers of a CustomerID, valid and invalid alike.

    my $Result = $OperationObject->Run(
        Data => {
            AccessToken => '...',      # shared secret (GertiAdmin)
            CustomerID  => 'AURORA',
        },
    );

    $Result = {
        Success => 1,
        Data    => {
            Users => [
                {
                    UserLogin     => 'ana@acme.example',
                    UserFirstname => 'Ana',
                    UserLastname  => 'Souza',
                    UserEmail     => 'ana@acme.example',
                    UserPhone     => '+553133330000',
                    UserMobile    => '',
                    ValidID       => 1,
                },
                ...
            ],
            Truncated => 0,
        },
    };

=cut

sub Run {
    my ( $Self, %Param ) = @_;

    if ( !IsHashRefWithData( $Param{Data} ) ) {
        return $Self->ReturnError(
            ErrorCode    => 'CustomerUserList.MissingParameter',
            ErrorMessage => 'CustomerUserList: the request is empty!',
        );
    }

    my $TokenError = $Self->_CheckAccessToken( Data => $Param{Data} );
    return $TokenError if $TokenError;

    my $D = $Param{Data};

    if ( !IsStringWithData( $D->{CustomerID} ) ) {
        return $Self->ReturnError(
            ErrorCode    => 'CustomerUserList.MissingParameter',
            ErrorMessage => 'CustomerUserList: CustomerID parameter is missing!',
        );
    }

    my $CustomerUserObject = $Kernel::OM->Get('Kernel::System::CustomerUser');

    # Valid => 0 includes deactivated people — they must stay visible, marked.
    my %Logins = $CustomerUserObject->CustomerSearch(
        CustomerID => $D->{CustomerID},
        Valid      => 0,
    );

    my @Sorted    = sort keys %Logins;
    my $Truncated = 0;
    if ( scalar @Sorted > $MAX_USERS ) {
        @Sorted    = @Sorted[ 0 .. $MAX_USERS - 1 ];
        $Truncated = 1;
    }

    my @Users;
    for my $Login (@Sorted) {
        my %U = $CustomerUserObject->CustomerUserDataGet( User => $Login );
        next if !IsHashRefWithData( \%U );
        push @Users, {
            UserLogin     => $U{UserLogin},
            UserFirstname => $U{UserFirstname} // '',
            UserLastname  => $U{UserLastname} // '',
            UserEmail     => $U{UserEmail} // '',
            UserPhone     => $U{UserPhone} // '',
            UserMobile    => $U{UserMobile} // '',
            ValidID       => $U{ValidID} // 1,
        };
    }

    return {
        Success => 1,
        Data    => {
            Users     => \@Users,
            Truncated => $Truncated,
        },
    };
}

=head2 _CheckAccessToken()

Validates the shared AccessToken against C<GertiAdmin::AccessToken>. Fails closed.

=cut

sub _CheckAccessToken {
    my ( $Self, %Param ) = @_;

    my $Provided = $Param{Data}->{AccessToken} || '';
    my $Expected = $Kernel::OM->Get('Kernel::Config')->Get('GertiAdmin::AccessToken') || '';

    if ( !IsStringWithData($Expected) || !IsStringWithData($Provided) || $Provided ne $Expected ) {
        return $Self->ReturnError(
            ErrorCode    => 'GertiAdmin.AuthFail',
            ErrorMessage => 'GertiAdmin: invalid or missing AccessToken.',
        );
    }

    return;
}

1;
