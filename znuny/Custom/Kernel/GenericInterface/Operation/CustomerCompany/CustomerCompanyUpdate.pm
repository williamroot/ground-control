# --
# Gerti — custom Generic Interface operation (T-R1.3, Onda 1 / R1 do vídeo).
# Wraps the native Kernel::System::CustomerCompany->CustomerCompanyUpdate so the
# console can correct a customer's cadastro AFTER onboarding (today there is no
# way at all: the router only creates, lists and reads).
#
# `gerti.tenant` is the OWNER of address/contact (decision D-B); this op writes
# the best-effort MIRROR into the native customer_company, so an agent working
# inside the Znuny panel sees the same address the operator typed in the console.
#
# Native CustomerCompanyUpdate is a FULL REPLACE: any mapped field left out is
# blanked. So this op reads the current record and merges the provided fields
# over it (same shape as GertiAdmin/AdminAgentSet.pm).
# --
# This software comes with ABSOLUTELY NO WARRANTY.
# --

package Kernel::GenericInterface::Operation::CustomerCompany::CustomerCompanyUpdate;

use strict;
use warnings;

use Kernel::System::VariableCheck qw(IsHashRefWithData IsStringWithData);

use parent qw(
    Kernel::GenericInterface::Operation::Common
);

our $ObjectManagerDisabled = 1;

# Allowlist of fields this op will ever write. Anything else is rejected loudly
# instead of silently ignored — a typo in the sidecar must not look like success.
my @WRITABLE_FIELDS = qw(
    CustomerCompanyName
    CustomerCompanyStreet
    CustomerCompanyZIP
    CustomerCompanyCity
    CustomerCompanyCountry
    CustomerCompanyURL
    CustomerCompanyComment
    ValidID
);

=head1 NAME

Kernel::GenericInterface::Operation::CustomerCompany::CustomerCompanyUpdate
- GenericInterface CustomerCompany Update operation backend (Gerti custom).

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

Update an existing CustomerCompany (merge over current data).

    my $Result = $OperationObject->Run(
        Data => {
            AccessToken            => '...',          # shared secret (GertiAdmin)
            CustomerID             => 'acme',         # required, never renamed here
            CustomerCompanyName    => 'ACME Ltda',    # optional
            CustomerCompanyStreet  => 'Rua X, 100',   # optional
            CustomerCompanyZIP     => '30110000',     # optional
            CustomerCompanyCity    => 'Belo Horizonte',
            CustomerCompanyCountry => 'Brasil',
            CustomerCompanyComment => 'contato: Ana / ana@acme.example',
            ValidID                => 1,
        },
    );

    $Result = {
        Success => 1,
        Data    => { CustomerID => 'acme' },
    };

Renaming the CustomerID is deliberately NOT supported: it is the join key to
`gerti.tenant.znuny_customer_id` and to every ticket's CustomerID. The sidecar
rejects the attempt before it gets here (422); this op simply never renames.

=cut

sub Run {
    my ( $Self, %Param ) = @_;

    if ( !IsHashRefWithData( $Param{Data} ) ) {
        return $Self->ReturnError(
            ErrorCode    => 'CustomerCompanyUpdate.MissingParameter',
            ErrorMessage => 'CustomerCompanyUpdate: the request is empty!',
        );
    }

    my $TokenError = $Self->_CheckAccessToken( Data => $Param{Data} );
    return $TokenError if $TokenError;

    my $D = $Param{Data};

    if ( !IsStringWithData( $D->{CustomerID} ) ) {
        return $Self->ReturnError(
            ErrorCode    => 'CustomerCompanyUpdate.MissingParameter',
            ErrorMessage => 'CustomerCompanyUpdate: CustomerID parameter is missing!',
        );
    }

    # Field allowlist: unknown key => explicit error, never a silent no-op.
    my %Allowed = map { $_ => 1 } ( @WRITABLE_FIELDS, qw(AccessToken CustomerID) );
    for my $Key ( keys %{$D} ) {
        if ( !$Allowed{$Key} ) {
            return $Self->ReturnError(
                ErrorCode    => 'CustomerCompanyUpdate.UnknownField',
                ErrorMessage => "field '$Key' is not writable on a customer company.",
            );
        }
    }

    my $CustomerCompanyObject = $Kernel::OM->Get('Kernel::System::CustomerCompany');

    my %Current = $CustomerCompanyObject->CustomerCompanyGet(
        CustomerID => $D->{CustomerID},
    );
    if ( !IsHashRefWithData( \%Current ) ) {
        return $Self->ReturnError(
            ErrorCode    => 'CustomerCompanyUpdate.NotFound',
            ErrorMessage => 'CustomerCompanyUpdate: customer company not found.',
        );
    }

    # Merge: native Update is a full replace — a field we do not send is erased.
    my %UpdateParam;
    for my $Field (@WRITABLE_FIELDS) {
        $UpdateParam{$Field} = exists $D->{$Field} ? $D->{$Field} : $Current{$Field};
    }

    # Name and ValidID are NOT NULL on the native side; fall back to current.
    $UpdateParam{CustomerCompanyName} = $Current{CustomerCompanyName}
        if !IsStringWithData( $UpdateParam{CustomerCompanyName} );
    $UpdateParam{ValidID} = $Current{ValidID} || 1
        if !IsStringWithData( $UpdateParam{ValidID} );

    my $OK = $CustomerCompanyObject->CustomerCompanyUpdate(
        %UpdateParam,
        CustomerCompanyID => $D->{CustomerID},    # old key: no rename
        CustomerID        => $D->{CustomerID},
        UserID            => 1,                   # system agent (audit field)
    );

    if ( !$OK ) {
        my $Msg = $Kernel::OM->Get('Kernel::System::Log')->GetLogEntry(
            Type => 'error',
            What => 'Message',
        ) || 'could not update the customer company';
        return $Self->ReturnError(
            ErrorCode    => 'CustomerCompanyUpdate.WriteError',
            ErrorMessage => $Msg,
        );
    }

    return {
        Success => 1,
        Data    => {
            CustomerID => $D->{CustomerID},
        },
    };
}

=head2 _CheckAccessToken()

Validates the shared AccessToken against C<GertiAdmin::AccessToken>. Fails
closed: missing configured token, missing request token, or mismatch all reject.

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
