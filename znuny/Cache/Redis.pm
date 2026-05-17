# --
#  Kernel::System::Cache::Redis
#
#  Redis cache backend for Znuny 7.2.
#
#  Znuny 7.2 *core* ships only Kernel::System::Cache::FileStorable.
#  Ground Control wires Znuny to Redis (a fixed stack decision), so we
#  provide a faithful Redis backend implementing the exact same backend
#  contract as FileStorable (Set / Get / Delete / CleanUp), proven by
#  the smoke test (Znuny cache keys appear in Redis).
#
#  Design:
#   * Values are serialized with Kernel::System::Storable (same as
#     FileStorable) so structures round-trip identically.
#   * One Redis key per cache entry:
#       znuny:<Type>:<md5(Key)>
#     Native Redis TTL via SETEX → no manual expiry bookkeeping.
#   * A per-Type Redis SET ("znuny:idx:<Type>") indexes member keys so
#     CleanUp(Type/KeepTypes/Expired) can purge precisely & cheaply.
#   * Connection lazily established; auto-reconnect enabled.
# --

package Kernel::System::Cache::Redis;

use strict;
use warnings;

use Digest::MD5 qw(md5_hex);
use Redis;

our @ObjectDependencies = (
    'Kernel::Config',
    'Kernel::System::Encode',
    'Kernel::System::Log',
    'Kernel::System::Storable',
);

sub new {
    my ( $Type, %Param ) = @_;

    my $Self = {};
    bless( $Self, $Type );

    my $ConfigObject = $Kernel::OM->Get('Kernel::Config');
    my $Conf = $ConfigObject->Get('Cache::Redis') || {};

    $Self->{Server}  = $Conf->{Server}         || '127.0.0.1:6379';
    $Self->{DBNum}   = $Conf->{DatabaseNumber} // 0;
    $Self->{Prefix}  = $Conf->{Prefix}         || 'znuny';
    $Self->{Options} = $Conf->{RedisConnectorOptions} || {};

    return $Self;
}

# Lazily (re)connect.
sub _Redis {
    my ($Self) = @_;

    if ( $Self->{Redis} ) {
        my $alive = eval { $Self->{Redis}->ping() };
        return $Self->{Redis} if $alive;
        delete $Self->{Redis};
    }

    my $Redis = eval {
        Redis->new(
            server    => $Self->{Server},
            reconnect => 60,
            every     => 250_000,
            %{ $Self->{Options} },
        );
    };
    if ( !$Redis ) {
        $Kernel::OM->Get('Kernel::System::Log')->Log(
            Priority => 'error',
            Message  => "Cache::Redis: cannot connect to $Self->{Server}: $@",
        );
        return;
    }
    eval { $Redis->select( $Self->{DBNum} ) };

    $Self->{Redis} = $Redis;
    return $Redis;
}

sub _Key {
    my ( $Self, $Type, $Key ) = @_;
    my $K = $Key;
    $Kernel::OM->Get('Kernel::System::Encode')->EncodeOutput( \$K );
    return $Self->{Prefix} . ':' . $Type . ':' . md5_hex($K);
}

sub _IndexKey {
    my ( $Self, $Type ) = @_;
    return $Self->{Prefix} . ':idx:' . $Type;
}

sub Set {
    my ( $Self, %Param ) = @_;

    for my $Needed (qw(Type Key Value TTL)) {
        if ( !defined $Param{$Needed} ) {
            $Kernel::OM->Get('Kernel::System::Log')->Log(
                Priority => 'error', Message => "Need $Needed!",
            );
            return;
        }
    }

    my $Redis = $Self->_Redis() or return;

    my $Dump = $Kernel::OM->Get('Kernel::System::Storable')->Serialize(
        Data => { Value => $Param{Value} },
    );

    my $RedisKey = $Self->_Key( $Param{Type}, $Param{Key} );
    my $TTL = $Param{TTL} > 0 ? int( $Param{TTL} ) : 1;

    my $ok = eval {
        $Redis->setex( $RedisKey, $TTL, $Dump );
        $Redis->sadd( $Self->_IndexKey( $Param{Type} ), $RedisKey );
        1;
    };
    if ( !$ok ) {
        $Kernel::OM->Get('Kernel::System::Log')->Log(
            Priority => 'error', Message => "Cache::Redis Set failed: $@",
        );
        return;
    }
    return 1;
}

sub Get {
    my ( $Self, %Param ) = @_;

    for my $Needed (qw(Type Key)) {
        if ( !defined $Param{$Needed} ) {
            $Kernel::OM->Get('Kernel::System::Log')->Log(
                Priority => 'error', Message => "Need $Needed!",
            );
            return;
        }
    }

    my $Redis = $Self->_Redis() or return;
    my $RedisKey = $Self->_Key( $Param{Type}, $Param{Key} );

    my $Dump = eval { $Redis->get($RedisKey) };
    return if !defined $Dump || $Dump eq '';

    my $Storage = eval {
        $Kernel::OM->Get('Kernel::System::Storable')->Deserialize( Data => $Dump );
    };
    return if ref $Storage ne 'HASH';
    return $Storage->{Value};
}

sub Delete {
    my ( $Self, %Param ) = @_;

    for my $Needed (qw(Type Key)) {
        if ( !defined $Param{$Needed} ) {
            $Kernel::OM->Get('Kernel::System::Log')->Log(
                Priority => 'error', Message => "Need $Needed!",
            );
            return;
        }
    }

    my $Redis = $Self->_Redis() or return;
    my $RedisKey = $Self->_Key( $Param{Type}, $Param{Key} );

    eval {
        $Redis->del($RedisKey);
        $Redis->srem( $Self->_IndexKey( $Param{Type} ), $RedisKey );
    };
    return 1;
}

sub CleanUp {
    my ( $Self, %Param ) = @_;

    my $Redis = $Self->_Redis() or return;

    # Enumerate all Type index sets.
    my @IndexKeys = eval { $Redis->keys( $Self->{Prefix} . ':idx:*' ) };
    @IndexKeys = () if !@IndexKeys;

    my %KeepType;
    if ( $Param{KeepTypes} && ref $Param{KeepTypes} eq 'ARRAY' ) {
        %KeepType = map { $_ => 1 } @{ $Param{KeepTypes} };
    }

    for my $IndexKey (@IndexKeys) {
        ( my $TypeName = $IndexKey ) =~ s/^\Q$Self->{Prefix}\E:idx://;

        # Single-Type cleanup
        next if $Param{Type} && $TypeName ne $Param{Type};

        # KeepTypes: skip protected types
        next if %KeepType && $KeepType{$TypeName};

        my @Members = eval { $Redis->smembers($IndexKey) };
        @Members = () if !@Members;

        if ( $Param{Expired} ) {
            # Redis already auto-expires entries; just prune dead index
            # members whose value key no longer exists.
            for my $M (@Members) {
                my $Exists = eval { $Redis->exists($M) };
                if ( !$Exists ) {
                    eval { $Redis->srem( $IndexKey, $M ) };
                }
            }
            next;
        }

        # Full purge of this Type
        if (@Members) {
            eval { $Redis->del(@Members) };
        }
        eval { $Redis->del($IndexKey) };
    }

    return 1;
}

1;
