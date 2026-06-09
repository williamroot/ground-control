# znuny/Custom/Kernel/GenericInterface/Operation/GertiTicket/TicketCreate.pm
# --
# Gerti — custom GI operation (Spec #1E). Wraps native Ticket::TicketCreate +
# Article backend so the portal (via sidecar) can open a customer ticket linked
# to a contract. Writes the contract UUID into DynamicField GertiContractId.
# Upgrade-safe Custom/ overlay (same as GertiAdmin ops).
# --
package Kernel::GenericInterface::Operation::GertiTicket::TicketCreate;

use strict;
use warnings;

use MIME::Base64 qw(decode_base64);
use Kernel::System::VariableCheck qw(IsHashRefWithData IsStringWithData IsArrayRefWithData);

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

    if ( !IsHashRefWithData( $Param{Data} ) ) {
        return $Self->ReturnError(
            ErrorCode    => 'TicketCreate.MissingParameter',
            ErrorMessage => 'TicketCreate: the request is empty!',
        );
    }
    my $TokenError = $Self->_CheckAccessToken( Data => $Param{Data} );
    return $TokenError if $TokenError;

    my $D = $Param{Data};
    for my $Needed (qw(CustomerUser CustomerID Title Body ContractId)) {
        if ( !IsStringWithData( $D->{$Needed} ) ) {
            return $Self->ReturnError(
                ErrorCode    => 'TicketCreate.MissingParameter',
                ErrorMessage => "TicketCreate: $Needed is missing!",
            );
        }
    }

    my $TicketObject = $Kernel::OM->Get('Kernel::System::Ticket');

    # Queue: derive from Service if not given. Customer tickets land in the
    # service's default queue; fall back to 'Raw' (Znuny default) if absent.
    my %CreateArgs = (
        Title        => $D->{Title},
        CustomerUser => $D->{CustomerUser},
        CustomerID   => $D->{CustomerID},
        Lock         => 'unlock',
        OwnerID      => 1,
        UserID       => 1,
        StateType    => 'new',
        State        => 'new',
    );
    $CreateArgs{Queue}    = $D->{Queue}    || 'Raw';
    $CreateArgs{Priority} = $D->{Priority} || '3 normal';
    $CreateArgs{Type}     = $D->{Type} if IsStringWithData( $D->{Type} );
    $CreateArgs{Service}  = $D->{Service} if IsStringWithData( $D->{Service} );

    my $TicketID = $TicketObject->TicketCreate(%CreateArgs);
    if ( !$TicketID ) {
        return $Self->ReturnError(
            ErrorCode    => 'TicketCreate.CreateError',
            ErrorMessage => 'TicketCreate: native TicketCreate failed.',
        );
    }

    # Stamp the contract on the ticket (DynamicField GertiContractId).
    my $DFObject      = $Kernel::OM->Get('Kernel::System::DynamicField');
    my $DFBackend     = $Kernel::OM->Get('Kernel::System::DynamicField::Backend');
    my $DFConfig      = $DFObject->DynamicFieldGet( Name => 'GertiContractId' );
    if ( IsHashRefWithData($DFConfig) ) {
        $DFBackend->ValueSet(
            DynamicFieldConfig => $DFConfig,
            ObjectID           => $TicketID,
            Value              => $D->{ContractId},
            UserID             => 1,
        );
    }

    # First (customer-visible) article.
    my $ArticleObject = $Kernel::OM->Get('Kernel::System::Ticket::Article');
    my $Backend       = $ArticleObject->BackendForChannel( ChannelName => 'Internal' );
    my @Attachments;
    if ( IsArrayRefWithData( $D->{Attachments} ) ) {
        for my $A ( @{ $D->{Attachments} } ) {
            next if !IsHashRefWithData($A) || !IsStringWithData( $A->{Filename} );
            push @Attachments, {
                Content     => decode_base64( $A->{ContentBase64} // '' ),
                ContentType => $A->{ContentType} || 'application/octet-stream',
                Filename    => $A->{Filename},
            };
        }
    }
    my $ArticleID = $Backend->ArticleCreate(
        TicketID             => $TicketID,
        SenderType           => 'customer',
        IsVisibleForCustomer => 1,
        From                 => $D->{CustomerUser},
        Subject              => $D->{Title},
        Body                 => $D->{Body},
        ContentType          => 'text/plain; charset=utf-8',
        HistoryType          => 'WebRequestCustomer',
        HistoryComment       => 'Gerti portal ticket',
        UserID               => 1,
        ( @Attachments ? ( Attachment => \@Attachments ) : () ),
    );
    if ( !$ArticleID ) {
        return $Self->ReturnError(
            ErrorCode    => 'TicketCreate.ArticleError',
            ErrorMessage => 'TicketCreate: article create failed.',
        );
    }

    my $TicketNumber = $TicketObject->TicketNumberLookup( TicketID => $TicketID );

    # Optional: link a Config Item to the new ticket (Spec #1K). A link failure
    # must NOT fail ticket creation — log and ignore (R1K §4.4).
    my $LinkedConfigItemID;
    if ( IsStringWithData( $D->{ConfigItemID} ) ) {
        my $LinkOk = $Kernel::OM->Get('Kernel::System::LinkObject')->LinkAdd(
            SourceObject => 'Ticket',
            SourceKey    => $TicketID,
            TargetObject => 'ITSMConfigItem',
            TargetKey    => $D->{ConfigItemID},
            Type         => 'RelevantTo',
            State        => 'Valid',
            UserID       => 1,
        );
        if ($LinkOk) {
            $LinkedConfigItemID = $D->{ConfigItemID};
        }
        else {
            $Kernel::OM->Get('Kernel::System::Log')->Log(
                Priority => 'error',
                Message  => "GertiTicket::TicketCreate: LinkAdd Ticket $TicketID <-> "
                    . "ITSMConfigItem $D->{ConfigItemID} failed (ignored).",
            );
        }
    }

    return {
        Success => 1,
        Data    => {
            TicketID     => $TicketID,
            TicketNumber => $TicketNumber,
            ( defined $LinkedConfigItemID ? ( ConfigItemID => $LinkedConfigItemID ) : () ),
        },
    };
}

sub _CheckAccessToken {
    my ( $Self, %Param ) = @_;
    my $Provided = $Param{Data}->{AccessToken} || '';
    my $Expected = $Kernel::OM->Get('Kernel::Config')->Get('GertiAdmin::AccessToken') || '';
    if ( !IsStringWithData($Expected) || !IsStringWithData($Provided) || $Provided ne $Expected ) {
        return $Self->ReturnError(
            ErrorCode    => 'GertiTicket.AuthFail',
            ErrorMessage => 'GertiTicket: invalid or missing AccessToken.',
        );
    }
    return;
}

1;
