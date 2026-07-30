# znuny/Custom/Kernel/GenericInterface/Operation/GertiAdmin/AdminSysConfigSet.pm
# --
# Gerti — custom GI op (Spec #4, Bloco D). Write path for a CLOSED allowlist of
# SysConfig settings (working hours / vacation days / time zone / week start).
#
# HIGHEST RISK OPERATION IN THE PROJECT: a bad write here does not break one
# screen, it can break Znuny's whole configuration. Three non-negotiable
# guards, in order:
#   1. Allowlist gate — unknown setting name rejected WITHOUT calling
#      Kernel::System::SysConfig at all.
#   2. Shape validation — WorkingHours must be Dia => [hours 0-23]; vacation
#      settings must be (Ano =>) Mes => Dia => texto. Wrong shape rejects
#      WITHOUT touching Znuny.
#   3. Lock/Update/Deploy with GUARANTEED lock release: SettingLock ->
#      SettingUpdate -> ConfigurationDeploy. Every failure path after the lock
#      is acquired unlocks before returning the error. A stuck lock freezes
#      SysConfig administration for the whole instance (Znuny does auto-expire
#      locks after 5 minutes server-side, but we do not rely on that grace
#      period — we always release explicitly).
# --
package Kernel::GenericInterface::Operation::GertiAdmin::AdminSysConfigSet;

use strict;
use warnings;

use Kernel::System::VariableCheck qw(IsHashRefWithData IsStringWithData);

use parent qw(
    Kernel::GenericInterface::Operation::Common
);

our $ObjectManagerDisabled = 1;

# Closed allowlist (Spec #4, Bloco D contract) — must stay in lockstep with
# AdminSysConfigGet.pm's allowlist.
our @AllowedBaseNames = qw(
    TimeWorkingHours
    TimeVacationDays
    TimeVacationDaysOneTime
    TimeZone
    CalendarWeekDayStart
);

=head1 NAME

Kernel::GenericInterface::Operation::GertiAdmin::AdminSysConfigSet
- GenericInterface AdminSysConfigSet operation backend (Gerti custom, Spec #4 Bloco D).

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

Write exactly ONE allowlisted setting (lock -> update -> deploy), scoped to
that single setting so the blast radius of every call is minimal.

    my $Result = $OperationObject->Run(
        Data => {
            AccessToken    => '...',                     # shared secret (GertiAdmin)
            AgentLogin     => 'admin',                    # (required) resolved to a real UserID
            Name           => 'TimeWorkingHours',         # (required) must be in the allowlist
            EffectiveValue => { Mon => [8,9,10], ... },   # (required) shape depends on Name
            Comments       => 'optional deploy comment',  # (optional)
        },
    );

    $Result = {
        Success => 1,
        Data    => {
            Name           => 'TimeWorkingHours',
            EffectiveValue => { Mon => [8,9,10], ... },
            UserID         => 3,
            Deployed       => 1,
        },
    };

=cut

sub Run {
    my ( $Self, %Param ) = @_;

    if ( !IsHashRefWithData( $Param{Data} ) ) {
        return $Self->ReturnError(
            ErrorCode    => 'AdminSysConfigSet.MissingParameter',
            ErrorMessage => 'AdminSysConfigSet: the request is empty!',
        );
    }

    # AccessToken gate (shared secret, validated against Znuny config).
    my $TokenError = $Self->_CheckAccessToken( Data => $Param{Data} );
    return $TokenError if $TokenError;

    my $D = $Param{Data};

    for my $Needed (qw(Name AgentLogin)) {
        if ( !IsStringWithData( $D->{$Needed} ) ) {
            return $Self->ReturnError(
                ErrorCode    => 'AdminSysConfigSet.MissingParameter',
                ErrorMessage => "AdminSysConfigSet: $Needed parameter is missing!",
            );
        }
    }

    if ( !exists $D->{EffectiveValue} ) {
        return $Self->ReturnError(
            ErrorCode    => 'AdminSysConfigSet.MissingParameter',
            ErrorMessage => 'AdminSysConfigSet: EffectiveValue parameter is missing!',
        );
    }

    my $Name = $D->{Name};

    # --- Guard 1: allowlist gate, BEFORE calling SysConfig at all. ---
    my $Kind = $Self->_SettingKind($Name);
    if ( !$Kind ) {
        return $Self->ReturnError(
            ErrorCode    => 'AdminSysConfigSet.NotAllowed',
            ErrorMessage => "AdminSysConfigSet: setting '$Name' is not in the calendar/journey allowlist.",
        );
    }

    # --- Guard 2: shape validation, BEFORE calling SysConfig at all. ---
    my $ShapeError = $Self->_ValidateShape(
        Kind  => $Kind,
        Value => $D->{EffectiveValue},
    );
    if ($ShapeError) {
        return $Self->ReturnError(
            ErrorCode    => 'AdminSysConfigSet.BadShape',
            ErrorMessage => "AdminSysConfigSet: $ShapeError",
        );
    }

    # Resolve the real Znuny UserID from the agent login (same pattern as
    # GertiTicket::TimeAccountingAdd) — an administrative write without an
    # identified author does not happen.
    my $UserObject = $Kernel::OM->Get('Kernel::System::User');
    my $UserID = $UserObject->UserLookup( UserLogin => $D->{AgentLogin}, Silent => 1 );
    if ( !$UserID ) {
        return $Self->ReturnError(
            ErrorCode    => 'AdminSysConfigSet.UnknownAgent',
            ErrorMessage => 'AdminSysConfigSet: agent login not found.',
        );
    }

    my $SysConfigObject = $Kernel::OM->Get('Kernel::System::SysConfig');

    my %Setting = $SysConfigObject->SettingGet(
        Name    => $Name,
        NoLog   => 1,
        NoCache => 1,
    );
    if ( !%Setting || !$Setting{DefaultID} ) {
        return $Self->ReturnError(
            ErrorCode    => 'AdminSysConfigSet.NotFound',
            ErrorMessage => "AdminSysConfigSet: setting '$Name' does not exist in this Znuny instance.",
        );
    }
    my $DefaultID = $Setting{DefaultID};

    # --- Guard 3a: lock. Nothing has been written yet; if this fails there is
    #     nothing to release. ---
    my $LockGUID = $SysConfigObject->SettingLock(
        DefaultID => $DefaultID,
        UserID    => $UserID,
        Force     => 0,
    );
    if ( !$LockGUID ) {
        return $Self->ReturnError(
            ErrorCode    => 'AdminSysConfigSet.LockFailed',
            ErrorMessage => "AdminSysConfigSet: could not lock setting '$Name'"
                . ' — it may be locked by another administrator right now. Try again shortly.',
        );
    }

    # From this point on we hold the lock: EVERY exit path below MUST release
    # it before returning, success or failure.

    my $UpdateError;
    my $UpdateOK = eval {
        my %UpdateResult = $SysConfigObject->SettingUpdate(
            Name              => $Name,
            EffectiveValue    => $D->{EffectiveValue},
            IsValid           => 1,
            UserID            => $UserID,
            ExclusiveLockGUID => $LockGUID,
        );

        if ( !$UpdateResult{Success} ) {
            $UpdateError = $UpdateResult{Error} || "SettingUpdate failed for '$Name'.";
            return 0;
        }

        return 1;
    };

    if ( !$UpdateOK ) {
        $UpdateError ||= "SettingUpdate raised an exception: $@";

        # Guaranteed lock release on failure.
        $SysConfigObject->SettingUnlock( DefaultID => $DefaultID );

        return $Self->ReturnError(
            ErrorCode    => 'AdminSysConfigSet.UpdateFailed',
            ErrorMessage => "AdminSysConfigSet: $UpdateError",
        );
    }

    # SettingUpdate() already releases the lock itself on the success path
    # (global, non-per-user change). We call SettingUnlock() again anyway:
    # Kernel::System::SysConfig::DB::DefaultSettingUnlock is a plain UPDATE
    # keyed by DefaultID, so unlocking an already-unlocked setting is a no-op
    # — this is a deliberate belt-and-suspenders guarantee, not a bug.
    $SysConfigObject->SettingUnlock( DefaultID => $DefaultID );

    # --- Guard 3b: deploy, explicit, authored by the resolved UserID. ---
    my $DeployError;
    my %DeployResult;
    my $DeployOK = eval {
        %DeployResult = $SysConfigObject->ConfigurationDeploy(
            UserID        => $UserID,
            DirtySettings => [$Name],
            Comments      => "Gerti admin ($D->{AgentLogin}): $Name",
        );
        return $DeployResult{Success} ? 1 : 0;
    };

    if ( !$DeployOK ) {
        $DeployError = $DeployResult{Error} || $@ || 'ConfigurationDeploy returned failure.';

        return $Self->ReturnError(
            ErrorCode    => 'AdminSysConfigSet.DeployFailed',
            ErrorMessage => "AdminSysConfigSet: setting '$Name' was saved but NOT deployed"
                . " (not live yet): $DeployError",
        );
    }

    return {
        Success => 1,
        Data    => {
            Name           => $Name,
            EffectiveValue => $D->{EffectiveValue},
            UserID         => $UserID,
            Deployed       => 1,
        },
    };
}

=head2 _SettingKind()

Maps an allowlisted setting name to its shape-validation kind. Returns undef
for anything outside the allowlist (the caller treats undef as "reject").

=cut

sub _SettingKind {
    my ( $Self, $Name ) = @_;

    return if !IsStringWithData($Name);

    return 'WorkingHours'        if $Name eq 'TimeWorkingHours';
    return 'VacationDays'        if $Name eq 'TimeVacationDays';
    return 'VacationDaysOneTime' if $Name eq 'TimeVacationDaysOneTime';
    return 'Select'              if $Name eq 'TimeZone';
    return 'Select'              if $Name eq 'CalendarWeekDayStart';

    if ( $Name =~ m{\A(TimeWorkingHours|TimeVacationDays|TimeVacationDaysOneTime)::Calendar([1-9])\z}xms ) {
        my $Base = $1;
        return 'WorkingHours'        if $Base eq 'TimeWorkingHours';
        return 'VacationDays'        if $Base eq 'TimeVacationDays';
        return 'VacationDaysOneTime' if $Base eq 'TimeVacationDaysOneTime';
    }

    return;
}

=head2 _ValidateShape()

Validates EffectiveValue against the expected Perl structure for its Kind,
BEFORE anything is locked or written. Returns an error string, or undef if
the shape is valid.

    WorkingHours        => { Dia => [ hora_inteira_0_23, ... ], ... }
    VacationDays         => { Mes(1-12) => { Dia(1-31) => 'texto', ... }, ... }
    VacationDaysOneTime  => { Ano(4 digitos) => { Mes(1-12) => { Dia(1-31) => 'texto' } } }
    Select               => scalar (TimeZone / CalendarWeekDayStart)

=cut

sub _ValidateShape {
    my ( $Self, %Param ) = @_;

    my $Kind  = $Param{Kind};
    my $Value = $Param{Value};

    if ( $Kind eq 'WorkingHours' ) {
        return "EffectiveValue must be a hash (Dia => lista de horas)." if ref $Value ne 'HASH';

        my %ValidDay = map { $_ => 1 } qw(Mon Tue Wed Thu Fri Sat Sun);

        for my $Day ( sort keys %{$Value} ) {
            return "'$Day' is not a valid weekday (Mon, Tue, Wed, Thu, Fri, Sat, Sun)."
                if !$ValidDay{$Day};

            return "'$Day' must map to an array of hours."
                if ref $Value->{$Day} ne 'ARRAY';

            for my $Hour ( @{ $Value->{$Day} } ) {
                return "'"
                    . ( defined $Hour ? $Hour : '<undef>' )
                    . "' in '$Day' is not an integer hour between 0 and 23."
                    if !defined $Hour || $Hour !~ m{\A([0-9]|1[0-9]|2[0-3])\z}xms;
            }
        }

        return;
    }

    if ( $Kind eq 'VacationDays' ) {
        return "EffectiveValue must be a hash (Mes => Dia => texto)." if ref $Value ne 'HASH';

        for my $Month ( sort keys %{$Value} ) {
            return "'$Month' is not a valid month (1-12)." if $Month !~ m{\A([1-9]|1[0-2])\z}xms;

            return "Month '$Month' must map to a hash of days."
                if ref $Value->{$Month} ne 'HASH';

            for my $Day ( sort keys %{ $Value->{$Month} } ) {
                return "'$Day' is not a valid day (1-31)." if $Day !~ m{\A([1-9]|[12][0-9]|3[01])\z}xms;

                return "Day '$Day' of month '$Month' must have non-empty text."
                    if !IsStringWithData( $Value->{$Month}{$Day} );
            }
        }

        return;
    }

    if ( $Kind eq 'VacationDaysOneTime' ) {
        return "EffectiveValue must be a hash (Ano => Mes => Dia => texto)." if ref $Value ne 'HASH';

        for my $Year ( sort keys %{$Value} ) {
            return "'$Year' is not a valid 4-digit year." if $Year !~ m{\A\d{4}\z}xms;

            return "Year '$Year' must map to a hash of months."
                if ref $Value->{$Year} ne 'HASH';

            for my $Month ( sort keys %{ $Value->{$Year} } ) {
                return "'$Month' is not a valid month (1-12)." if $Month !~ m{\A([1-9]|1[0-2])\z}xms;

                return "Month '$Month' of year '$Year' must map to a hash of days."
                    if ref $Value->{$Year}{$Month} ne 'HASH';

                for my $Day ( sort keys %{ $Value->{$Year}{$Month} } ) {
                    return "'$Day' is not a valid day (1-31)." if $Day !~ m{\A([1-9]|[12][0-9]|3[01])\z}xms;

                    return "Day '$Day' of $Year-$Month must have non-empty text."
                        if !IsStringWithData( $Value->{$Year}{$Month}{$Day} );
                }
            }
        }

        return;
    }

    if ( $Kind eq 'Select' ) {
        return "EffectiveValue must be a scalar (not a reference)." if ref $Value;
        return "EffectiveValue must not be empty." if !defined $Value || $Value eq '';
        return;
    }

    # Unreachable if _SettingKind() and this table stay in sync.
    return 'unknown setting kind — refusing to write.';
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
