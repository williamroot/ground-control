# znuny/Custom/Kernel/GenericInterface/Operation/GertiAdmin/AdminSysConfigGet.pm
# --
# Gerti — custom GI op (Spec #4, Bloco D). Read-only window into a CLOSED
# allowlist of SysConfig settings (working hours / vacation days / time zone /
# week start), scoped to the calendar screen. The console never persists a
# copy of this data — every read goes live through this operation.
#
# HIGH RISK BLOCK: a mistake here touches the whole Znuny instance, not one
# screen. The allowlist gate runs BEFORE any Kernel::System::SysConfig call —
# an unknown name is rejected without ever consulting SysConfig.
# --
package Kernel::GenericInterface::Operation::GertiAdmin::AdminSysConfigGet;

use strict;
use warnings;

use Kernel::System::VariableCheck qw(IsHashRefWithData IsArrayRefWithData IsStringWithData);

use parent qw(
    Kernel::GenericInterface::Operation::Common
);

our $ObjectManagerDisabled = 1;

# Closed allowlist (Spec #4, Bloco D contract). Base settings, plus the
# per-calendar equivalents for WorkingHours/VacationDays/VacationDaysOneTime
# (Calendar1..Calendar9). TimeZone and CalendarWeekDayStart have NO calendar
# variant in this allowlist — only the base names are readable/writable.
our @AllowedBaseNames = qw(
    TimeWorkingHours
    TimeVacationDays
    TimeVacationDaysOneTime
    TimeZone
    CalendarWeekDayStart
);

our @AllowedCalendarBaseNames = qw(
    TimeWorkingHours
    TimeVacationDays
    TimeVacationDaysOneTime
);

=head1 NAME

Kernel::GenericInterface::Operation::GertiAdmin::AdminSysConfigGet
- GenericInterface AdminSysConfigGet operation backend (Gerti custom, Spec #4 Bloco D).

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

Read one, several, or (default) every allowlisted calendar/journey setting.

    my $Result = $OperationObject->Run(
        Data => {
            AccessToken => '...',                          # shared secret (GertiAdmin)
            Names       => [ 'TimeWorkingHours', 'TimeVacationDays::Calendar1' ],  # optional
            # or
            Name        => 'TimeWorkingHours',              # optional, single-name shorthand
            # if neither Names nor Name is given, every allowlisted setting is returned
        },
    );

    $Result = {
        Success => 1,
        Data    => {
            Settings => {
                'TimeWorkingHours' => {
                    Name           => 'TimeWorkingHours',
                    EffectiveValue => { Mon => [8,9,10], ... },
                    IsValid        => 1,
                    IsDirty        => 0,
                },
                ...
            },
        },
    };

Any requested name outside the allowlist rejects the WHOLE request with an
error, without ever calling C<Kernel::System::SysConfig>.

=cut

sub Run {
    my ( $Self, %Param ) = @_;

    if ( !IsHashRefWithData( $Param{Data} ) ) {
        return $Self->ReturnError(
            ErrorCode    => 'AdminSysConfigGet.MissingParameter',
            ErrorMessage => 'AdminSysConfigGet: the request is empty!',
        );
    }

    # AccessToken gate (shared secret, validated against Znuny config).
    my $TokenError = $Self->_CheckAccessToken( Data => $Param{Data} );
    return $TokenError if $TokenError;

    my $D = $Param{Data};

    my @RequestedNames;
    if ( defined $D->{Names} ) {
        if ( !IsArrayRefWithData( $D->{Names} ) ) {
            return $Self->ReturnError(
                ErrorCode    => 'AdminSysConfigGet.BadParameter',
                ErrorMessage => 'AdminSysConfigGet: Names must be a non-empty array of setting names.',
            );
        }
        @RequestedNames = @{ $D->{Names} };
    }
    elsif ( IsStringWithData( $D->{Name} ) ) {
        @RequestedNames = ( $D->{Name} );
    }
    else {
        @RequestedNames = $Self->_AllAllowedNames();
    }

    # Allowlist gate BEFORE touching SysConfig. Reject the whole request on
    # the first unknown name — no partial reads, no silent drop.
    for my $Name (@RequestedNames) {
        if ( !$Self->_IsAllowedSetting($Name) ) {
            return $Self->ReturnError(
                ErrorCode    => 'AdminSysConfigGet.NotAllowed',
                ErrorMessage => "AdminSysConfigGet: setting '"
                    . ( defined $Name ? $Name : '<undef>' )
                    . "' is not in the calendar/journey allowlist.",
            );
        }
    }

    my $SysConfigObject = $Kernel::OM->Get('Kernel::System::SysConfig');

    my %Settings;
    for my $Name (@RequestedNames) {
        my %Setting = $SysConfigObject->SettingGet(
            Name    => $Name,
            NoLog   => 1,
            NoCache => 1,
        );

        if ( !%Setting ) {
            return $Self->ReturnError(
                ErrorCode    => 'AdminSysConfigGet.NotFound',
                ErrorMessage => "AdminSysConfigGet: setting '$Name' does not exist in this Znuny instance.",
            );
        }

        $Settings{$Name} = {
            Name           => $Name,
            EffectiveValue => $Setting{EffectiveValue},
            IsValid        => $Setting{IsValid} ? 1 : 0,
            IsDirty        => $Setting{IsDirty} ? 1 : 0,
        };
    }

    return {
        Success => 1,
        Data    => {
            Settings => \%Settings,
        },
    };
}

=head2 _AllAllowedNames()

Expands the allowlist table into the full list of readable setting names.

=cut

sub _AllAllowedNames {
    my ($Self) = @_;

    my @Names = @AllowedBaseNames;

    for my $CalendarID ( 1 .. 9 ) {
        for my $Base (@AllowedCalendarBaseNames) {
            push @Names, "$Base\::Calendar$CalendarID";
        }
    }

    return @Names;
}

=head2 _IsAllowedSetting()

Checks a single setting name against the closed allowlist.

=cut

sub _IsAllowedSetting {
    my ( $Self, $Name ) = @_;

    return 0 if !IsStringWithData($Name);

    return 1 if grep { $_ eq $Name } @AllowedBaseNames;

    if ( $Name =~ m{\A(TimeWorkingHours|TimeVacationDays|TimeVacationDaysOneTime)::Calendar([1-9])\z}xms ) {
        return 1;
    }

    return 0;
}

=head2 _CheckAccessToken()

Validates the shared AccessToken against the configured expected value
(C<GertiAdmin::AccessToken> in Znuny config). Fails closed.

Returns a ReturnError hashref on failure, or undef on success.

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
