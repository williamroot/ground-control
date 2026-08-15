# znuny/Custom/Kernel/GenericInterface/Operation/GertiAdmin/AdminSpec.pm
# --
# Gerti — Spec #4 (Bloco A), ADR D21. Shared allowlist table consumed by the
# AdminObjectList/Get/Add/Update generic GI operations. This is NOT a GI
# operation itself (no Run(), never appears in a webservice YAML) — it is the
# single hardcoded map from an object KEY the request may send (Queue, SLA,
# Service, Type, State, Priority, SystemAddress) to the real Znuny Perl
# class/methods/fields.
#
# Why this file exists: the dispatcher guard is "the request never names a
# Perl class or method" — only this table may do that translation, and only
# for the seven keys below. An unknown key must error before anything is
# loaded; a field outside an object's Fields list must error explicitly,
# never be silently dropped (see plan Bloco A guards).
#
# Contract reference: docs/superpowers/plans/2026-07-30-spec-4-capa-admin-znuny.md
# --
package Kernel::GenericInterface::Operation::GertiAdmin::AdminSpec;

use strict;
use warnings;

=head1 NAME

Kernel::GenericInterface::Operation::GertiAdmin::AdminSpec - allowlist table
for the Bloco A generic admin GI operations (Gerti custom, Spec #4).

=head2 Table shape

For each object key:

    Module        - Perl class to load via $Kernel::OM->Get()
    ListMethod    - lists all rows (ID => Name hash)
    GetMethod     - fetches one row by id
    AddMethod     - creates a row, returns the new numeric id
    UpdateMethod  - updates a row in place, returns 1/undef
    GetIDParam    - param name the GetMethod call expects for the id
    GetIDField    - key in the GetMethod()/row hash that holds the id
    UpdateIDParam - param name the UpdateMethod call expects for the id
    Fields        - allowlisted, writable/readable attribute names (exact
                    match to both the Get() row keys and the Add/Update
                    param names for that object — verified against Znuny
                    7.2 core: the only name that differs from the row key is
                    the id itself, handled via Get/UpdateIDParam above)
    RequiredOnAdd - subset of Fields that AdminObjectAdd must reject as
                    missing. Convention: ValidID is normally excluded here,
                    because AdminObjectAdd defaults it to 1 when the caller
                    omits it (same convention as CustomerCompanyAdd).
                    EXCEPTION - SystemAddress lists ValidID explicitly:
                    Kernel::System::SystemAddress::SystemAddressAdd itself
                    hard-rejects without it ("Need ValidID!", verified in
                    7.2.3 core), unlike QueueAdd & friends. Listing it does
                    not break a caller that omits it (AdminObjectAdd fills
                    the default BEFORE MissingRequired runs); it documents
                    the native contract instead of hiding it.

=cut

our %ObjectSpec = (
    Queue => {
        Module        => 'Kernel::System::Queue',
        ListMethod    => 'QueueList',
        GetMethod     => 'QueueGet',
        AddMethod     => 'QueueAdd',
        UpdateMethod  => 'QueueUpdate',
        GetIDParam    => 'ID',
        GetIDField    => 'QueueID',
        UpdateIDParam => 'QueueID',
        Fields        => [
            qw(
                Name GroupID Comment ValidID SystemAddressID SalutationID
                SignatureID FollowUpID FollowUpLock UnlockTimeout
                FirstResponseTime UpdateTime SolutionTime Calendar
            )
        ],
        RequiredOnAdd => [qw(Name GroupID SystemAddressID SalutationID SignatureID FollowUpID)],
    },
    SLA => {
        Module        => 'Kernel::System::SLA',
        ListMethod    => 'SLAList',
        GetMethod     => 'SLAGet',
        AddMethod     => 'SLAAdd',
        UpdateMethod  => 'SLAUpdate',
        GetIDParam    => 'SLAID',
        GetIDField    => 'SLAID',
        UpdateIDParam => 'SLAID',
        # TypeID is NOT in the plan's Bloco A field table, but was added here
        # after live verification against this stack's actual Znuny install:
        # ITSMCore's packagesetup ALTERs the sla table to add type_id (see
        # provisioning log: "ALTER TABLE sla ADD type_id INTEGER NULL"), and
        # Kernel::System::SLA::SLAAdd hard-rejects with "Need TypeID!" without
        # it once that column exists. Values come from GeneralCatalog class
        # ITSM::SLA::Type (Availability/Response Time/Recovery Time/...).
        Fields => [
            qw(
                Name Comment ValidID Calendar FirstResponseTime
                FirstResponseNotify UpdateTime UpdateNotify SolutionTime
                SolutionNotify ServiceIDs TypeID
            )
        ],
        RequiredOnAdd => [qw(Name TypeID)],
    },
    Service => {
        Module        => 'Kernel::System::Service',
        ListMethod    => 'ServiceList',
        GetMethod     => 'ServiceGet',
        AddMethod     => 'ServiceAdd',
        UpdateMethod  => 'ServiceUpdate',
        GetIDParam    => 'ServiceID',
        GetIDField    => 'ServiceID',
        UpdateIDParam => 'ServiceID',
        Fields        => [qw(Name ParentID Comment ValidID TypeID Criticality)],
        # TypeID/Criticality are required by Kernel::System::Service itself
        # once ITSMCore is installed (it is, in this stack — see Dockerfile
        # #1K/R1K) — the native Add/Update reject without them.
        RequiredOnAdd => [qw(Name TypeID Criticality)],
    },
    Type => {
        Module        => 'Kernel::System::Type',
        ListMethod    => 'TypeList',
        GetMethod     => 'TypeGet',
        AddMethod     => 'TypeAdd',
        UpdateMethod  => 'TypeUpdate',
        GetIDParam    => 'ID',
        GetIDField    => 'ID',
        UpdateIDParam => 'ID',
        Fields        => [qw(Name ValidID)],
        RequiredOnAdd => [qw(Name)],
    },
    State => {
        Module        => 'Kernel::System::State',
        ListMethod    => 'StateList',
        GetMethod     => 'StateGet',
        AddMethod     => 'StateAdd',
        UpdateMethod  => 'StateUpdate',
        GetIDParam    => 'ID',
        GetIDField    => 'ID',
        UpdateIDParam => 'ID',
        Fields        => [qw(Name Comment ValidID TypeID)],
        RequiredOnAdd => [qw(Name TypeID)],
    },
    Priority => {
        Module        => 'Kernel::System::Priority',
        ListMethod    => 'PriorityList',
        GetMethod     => 'PriorityGet',
        AddMethod     => 'PriorityAdd',
        UpdateMethod  => 'PriorityUpdate',
        GetIDParam    => 'PriorityID',
        GetIDField    => 'ID',
        UpdateIDParam => 'PriorityID',
        Fields        => [qw(Name ValidID)],
        RequiredOnAdd => [qw(Name)],
    },

    # T-R9.2 — the queue's reply address. Without this key the console had no
    # way to discover a valid SystemAddressID, and Queue's RequiredOnAdd
    # (above) made creating a queue impossible.
    #
    # Signature verified against 7.2.3 core (/opt/otrs/Kernel/System/
    # SystemAddress.pm inside the znuny-web image):
    #   SystemAddressAdd    - needs Name, ValidID, Realname, QueueID, UserID
    #   SystemAddressGet    - needs ID; the returned row keys the id as ID
    #   SystemAddressUpdate - needs ID, Name, ValidID, Realname, QueueID, UserID
    #   SystemAddressList   - Valid => 0 lists invalid rows too
    # Note SystemAddressUpdate refuses to set ValidID > 1 while the address is
    # still referenced by a queue or auto response — that rejection surfaces as
    # AdminObjectUpdate.UpdateError, which is the native (and correct) behaviour.
    SystemAddress => {
        Module        => 'Kernel::System::SystemAddress',
        ListMethod    => 'SystemAddressList',
        GetMethod     => 'SystemAddressGet',
        AddMethod     => 'SystemAddressAdd',
        UpdateMethod  => 'SystemAddressUpdate',
        GetIDParam    => 'ID',
        GetIDField    => 'ID',
        UpdateIDParam => 'ID',
        Fields        => [qw(Name Realname Comment ValidID QueueID)],
        RequiredOnAdd => [qw(Name Realname ValidID QueueID)],
    },
);

=head2 Keys()

Sorted list of the allowlisted object keys (for error messages / introspection).

=cut

sub Keys {
    my ($Class) = @_;
    return sort keys %ObjectSpec;
}

=head2 Spec()

    my $Spec = Kernel::GenericInterface::Operation::GertiAdmin::AdminSpec->Spec('Queue');

Returns the spec hashref for a known object key, or undef (never dies, never
loads anything) for an unknown one — callers must treat undef as a hard error.

=cut

sub Spec {
    my ( $Class, $ObjectKey ) = @_;
    return if !defined $ObjectKey || !length $ObjectKey;
    return $ObjectSpec{$ObjectKey};
}

=head2 ValidateFields()

    my @Invalid = Kernel::GenericInterface::Operation::GertiAdmin::AdminSpec
        ->ValidateFields( 'Queue', \%RequestedFields );

Returns the list of field names in C<%RequestedFields> that are NOT in the
object's allowlist. Empty list means every field is allowed. Never drops a
field silently — the caller is expected to reject the whole request when
this returns anything.

=cut

sub ValidateFields {
    my ( $Class, $ObjectKey, $Fields ) = @_;

    my $Spec = $Class->Spec($ObjectKey);
    return if !$Spec;

    my %Allowed = map { $_ => 1 } @{ $Spec->{Fields} };
    my @Invalid = grep { !$Allowed{$_} } keys %{ $Fields || {} };

    return @Invalid;
}

=head2 MissingRequired()

    my @Missing = Kernel::GenericInterface::Operation::GertiAdmin::AdminSpec
        ->MissingRequired( 'Queue', \%RequestedFields );

Returns the list of C<RequiredOnAdd> field names that are absent or empty in
C<%RequestedFields>.

=cut

sub MissingRequired {
    my ( $Class, $ObjectKey, $Fields ) = @_;

    my $Spec = $Class->Spec($ObjectKey);
    return if !$Spec;

    my @Missing;
    for my $Required ( @{ $Spec->{RequiredOnAdd} || [] } ) {
        my $Value = $Fields->{$Required};
        push @Missing, $Required if !defined $Value || ( !ref $Value && $Value eq '' );
    }

    return @Missing;
}

1;
