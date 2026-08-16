# --
# Gerti — custom Generic Interface operation (T-R2.1, Onda 1 / R2 do vídeo).
# Wraps the native Kernel::System::CustomerUser->CustomerUserUpdate so the
# console can EDIT a customer's person after onboarding — today the sidecar can
# only create, and there is no way to change a phone or deactivate anybody.
#
# "Sem exclusão" (invariante 3): deactivating is ValidID = 2, never a delete.
#
# Native CustomerUserUpdate is a FULL REPLACE across the mapped fields: a field
# left out is blanked. So this op reads the current record and merges the
# provided fields over it (same shape as GertiAdmin/AdminAgentSet.pm).
#
# Password is NEVER a side effect here — CustomerUser/SetPassword.pm is the one
# explicit operation that changes it, and any pw-ish key is rejected outright.
# --
# This software comes with ABSOLUTELY NO WARRANTY.
# --

package Kernel::GenericInterface::Operation::CustomerUser::CustomerUserUpdate;

use strict;
use warnings;

use Kernel::System::VariableCheck qw(IsHashRefWithData IsStringWithData);

use parent qw(
    Kernel::GenericInterface::Operation::Common
);

our $ObjectManagerDisabled = 1;

# Allowlist of cadastro fields a CALLER may set. UserPw/Password are
# DELIBERATELY absent — see module header.
#
# UserCustomerID is DELIBERATELY absent too, and that is a security decision,
# not an oversight: it is the company the person belongs to. Letting a caller
# set it here would turn "edit this user" into "move this person to another
# customer" — a cross-tenant move through the edit form. It still has to be
# SENT to the native Update (which is a full replace and would blank it), so it
# is merged from the current record below and never from the request.
my @WRITABLE_FIELDS = qw(
    UserTitle
    UserFirstname
    UserLastname
    UserEmail
    UserPhone
    UserMobile
    UserComment
    ValidID
);

# Preserved from the current record, never accepted from the request.
my @PRESERVED_FIELDS = qw(UserCustomerID);

=head1 NAME

Kernel::GenericInterface::Operation::CustomerUser::CustomerUserUpdate
- GenericInterface CustomerUser Update operation backend (Gerti custom).

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

Update an existing CustomerUser (merge over current data).

    my $Result = $OperationObject->Run(
        Data => {
            AccessToken   => '...',                  # shared secret (GertiAdmin)
            UserLogin     => 'ana@acme.example',     # required; never renamed here
            UserFirstname => 'Ana',                  # optional
            UserLastname  => 'Souza',                # optional
            UserEmail     => 'ana@acme.example',     # optional
            UserPhone     => '+553133330000',        # optional
            UserMobile    => '+5531999990000',       # optional
            ValidID       => 2,                      # 2 = invalid (desativado)
        },
    );

    $Result = {
        Success => 1,
        Data    => { UserLogin => 'ana@acme.example', ValidID => 2 },
    };

Renaming the login is deliberately NOT supported: the login is the identity the
portal role (`gerti.portal_user_role.customer_login`) and every ticket's
CustomerUserID point at. Changing it here would orphan both.

=cut

sub Run {
    my ( $Self, %Param ) = @_;

    if ( !IsHashRefWithData( $Param{Data} ) ) {
        return $Self->ReturnError(
            ErrorCode    => 'CustomerUserUpdate.MissingParameter',
            ErrorMessage => 'CustomerUserUpdate: the request is empty!',
        );
    }

    my $TokenError = $Self->_CheckAccessToken( Data => $Param{Data} );
    return $TokenError if $TokenError;

    my $D = $Param{Data};

    if ( !IsStringWithData( $D->{UserLogin} ) ) {
        return $Self->ReturnError(
            ErrorCode    => 'CustomerUserUpdate.MissingParameter',
            ErrorMessage => 'CustomerUserUpdate: UserLogin parameter is missing!',
        );
    }

    # Guardrail: password is never a side effect of this op. Reject outright.
    for my $Key ( keys %{$D} ) {
        if ( $Key =~ m{pw|password}xmsi ) {
            return $Self->ReturnError(
                ErrorCode    => 'CustomerUserUpdate.PasswordNotAllowed',
                ErrorMessage => "field '$Key' is rejected: setting a password is a"
                    . ' separate, explicit operation.',
            );
        }
    }

    # Guardrail: field allowlist. Anything unknown => explicit error.
    my %Allowed = map { $_ => 1 } ( @WRITABLE_FIELDS, qw(AccessToken UserLogin) );
    for my $Key ( keys %{$D} ) {
        if ( !$Allowed{$Key} ) {
            return $Self->ReturnError(
                ErrorCode    => 'CustomerUserUpdate.UnknownField',
                ErrorMessage => "field '$Key' is not writable on a customer user.",
            );
        }
    }

    my $CustomerUserObject = $Kernel::OM->Get('Kernel::System::CustomerUser');

    my %Current = $CustomerUserObject->CustomerUserDataGet(
        User => $D->{UserLogin},
    );
    if ( !IsHashRefWithData( \%Current ) ) {
        return $Self->ReturnError(
            ErrorCode    => 'CustomerUserUpdate.NotFound',
            ErrorMessage => 'CustomerUserUpdate: customer user not found.',
        );
    }

    # Merge: native Update is a full replace — a field we do not send is erased.
    my %UpdateParam;
    for my $Field (@WRITABLE_FIELDS) {
        $UpdateParam{$Field} = exists $D->{$Field} ? $D->{$Field} : $Current{$Field};
    }
    for my $Field (@PRESERVED_FIELDS) {
        $UpdateParam{$Field} = $Current{$Field};
    }

    # NOT NULL on the native side; never let a merge blank them.
    for my $Needed (qw(UserFirstname UserLastname UserEmail UserCustomerID)) {
        if ( !IsStringWithData( $UpdateParam{$Needed} ) ) {
            return $Self->ReturnError(
                ErrorCode    => 'CustomerUserUpdate.MissingParameter',
                ErrorMessage => "CustomerUserUpdate: $Needed would be emptied by this update!",
            );
        }
    }
    $UpdateParam{ValidID} = $Current{ValidID} || 1
        if !IsStringWithData( $UpdateParam{ValidID} );

    my $OK = $CustomerUserObject->CustomerUserUpdate(
        %UpdateParam,
        Source    => 'CustomerUser',
        ID        => $Current{UserLogin},    # old login: no rename
        UserLogin => $Current{UserLogin},
        UserID    => 1,                      # system agent (audit field)
    );

    if ( !$OK ) {
        my $Msg = $Kernel::OM->Get('Kernel::System::Log')->GetLogEntry(
            Type => 'error',
            What => 'Message',
        ) || 'could not update the customer user';
        return $Self->ReturnError(
            ErrorCode    => 'CustomerUserUpdate.WriteError',
            ErrorMessage => $Msg,
        );
    }

    my %Saved = $CustomerUserObject->CustomerUserDataGet( User => $Current{UserLogin} );
    delete @Saved{ grep {m{pw}xmsi} keys %Saved };

    return {
        Success => 1,
        Data    => {
            UserLogin      => $Saved{UserLogin},
            UserFirstname  => $Saved{UserFirstname},
            UserLastname   => $Saved{UserLastname},
            UserEmail      => $Saved{UserEmail},
            UserCustomerID => $Saved{UserCustomerID},
            UserPhone      => $Saved{UserPhone},
            UserMobile     => $Saved{UserMobile},
            ValidID        => $Saved{ValidID},
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
