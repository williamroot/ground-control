# syntax=docker/dockerfile:1
# ─────────────────────────────────────────────────────────────────────
#  Znuny 7.2.x  —  built from the official Znuny tarball
#
#  Base: debian:bookworm-slim
#    Rationale: Apache's libapache2-mod-perl2 is linked against Debian's
#    SYSTEM perl (/usr/bin/perl, 5.36). To guarantee that mod_perl, the
#    otrs.Daemon and every bin/otrs.Console.pl call all use the SAME
#    perl with the SAME @INC, we use ONE perl: Debian's system perl.
#    Most Znuny deps ship as Debian `lib*-perl` packages; the rest are
#    filled via cpanminus, all into the system perl. (A perl:5.40 base
#    creates a second perl that mod_perl ignores — verified to break
#    CheckModules / runtime — see docs/decisions/0001-stack.md.)
# ─────────────────────────────────────────────────────────────────────
FROM debian:bookworm-slim

ARG ZNUNY_VERSION=7.2.3
ENV ZNUNY_VERSION=${ZNUNY_VERSION} \
    OTRS_HOME=/opt/otrs \
    DEBIAN_FRONTEND=noninteractive \
    LANG=C.UTF-8 \
    LC_ALL=C.UTF-8

# ── System packages: Apache2 + mod_perl2 + every Znuny Perl dep that
#    Debian packages (these install into the system perl that mod_perl
#    uses), plus the toolchain for cpanm to build the rest.
RUN set -eux; \
    apt-get update; \
    apt-get install -y --no-install-recommends \
        ca-certificates curl wget gnupg procps \
        apache2 libapache2-mod-perl2 \
        perl perl-modules \
        cpanminus make gcc g++ \
        postgresql-client \
        libpq-dev libssl-dev zlib1g-dev libxml2-dev libxslt1-dev \
        libgd-dev libexpat1-dev \
        libdbi-perl libdbd-pg-perl \
        libapache-dbi-perl libnet-dns-perl libnet-ldap-perl \
        libio-socket-ssl-perl libnet-ssleay-perl \
        libtimedate-perl libdatetime-perl libdatetime-timezone-perl \
        libtemplate-perl libtext-csv-xs-perl libjson-xs-perl \
        libxml-libxml-perl libxml-libxslt-perl libxml-parser-perl \
        libyaml-libyaml-perl libcgi-pm-perl \
        libarchive-zip-perl libcrypt-eksblowfish-perl \
        libencode-hanextra-perl libmail-imapclient-perl \
        libtemplate-plugin-html-strip-perl \
        libmoo-perl libnamespace-clean-perl \
        libdata-uuid-perl libhash-merge-perl libical-parser-perl \
        libjavascript-minifier-xs-perl libcss-minifier-xs-perl \
        libgd-text-perl libgd-graph-perl \
        libhtml-parser-perl libhtml-scrubber-perl \
        liblwp-protocol-https-perl libwww-perl \
        libauthen-sasl-perl libauthen-ntlm-perl \
        libxml-feedpp-perl libsoap-lite-perl \
        libspreadsheet-xlsx-perl libspreadsheet-parseexcel-perl \
        libexcel-writer-xlsx-perl libpdf-api2-perl \
        libnet-smtp-ssl-perl libauthen-sasl-perl \
        libdbd-mysql-perl \
        cron locales bzip2 ; \
    rm -rf /var/lib/apt/lists/*

# ── otrs user/group
RUN set -eux; \
    useradd -r -m -d ${OTRS_HOME} -s /bin/bash -c "Znuny user" otrs; \
    usermod -aG www-data otrs

# ── Download + unpack the official Znuny tarball
WORKDIR /opt
RUN set -eux; \
    curl -fSL "https://download.znuny.org/releases/znuny-${ZNUNY_VERSION}.tar.gz" \
        -o /tmp/znuny.tar.gz; \
    tar -xzf /tmp/znuny.tar.gz -C /opt; \
    rm -rf ${OTRS_HOME}; \
    mv /opt/znuny-${ZNUNY_VERSION} ${OTRS_HOME}; \
    rm -f /tmp/znuny.tar.gz; \
    # Znuny 7.2's shipped Apache include / startup / cron hardcode the
    # native default path /opt/znuny. We honor OTRS_HOME=/opt/otrs as
    # the real location and expose /opt/znuny as a symlink so every
    # shipped default resolves without rewriting Znuny's own files.
    ln -sfn ${OTRS_HOME} /opt/znuny

WORKDIR ${OTRS_HOME}

# ── Seed the *.dist config files Znuny ships
RUN set -eux; \
    cp Kernel/Config.pm.dist Kernel/Config.pm; \
    [ -f Kernel/Config/GenericAgent.pm.dist ] && \
        cp Kernel/Config/GenericAgent.pm.dist Kernel/Config/GenericAgent.pm || true

# ── Fill the remaining Znuny CPAN deps not packaged by Debian, into the
#    SAME system perl. Sisimai (bounce parsing) + ES client + a couple
#    of helpers. Then run Znuny's own checker as a hard verification
#    gate: any *required* module still missing fails the build.
RUN set -eux; \
    cpanm --notest --quiet \
        Sisimai \
        Search::Elasticsearch \
        Redis \
        Net::Server \
        Linux::Inotify2 \
        || (echo "cpanm batch failed, retrying individually" && \
            for m in Sisimai Search::Elasticsearch Redis Net::Server Linux::Inotify2; do \
                cpanm --notest --quiet "$m" || echo "WARN optional: $m"; \
            done); \
    perl bin/otrs.CheckModules.pl 2>&1 | tee /tmp/checkmodules.txt || true; \
    if grep -E 'Not installed' /tmp/checkmodules.txt | grep -iqE '\(required'; then \
        echo "FATAL: required Perl modules still missing:" >&2; \
        grep -E 'Not installed' /tmp/checkmodules.txt | grep -iE '\(required' >&2; \
        exit 1; \
    fi; \
    echo "==> All REQUIRED Perl modules present."

# ── Permissions via Znuny's own helper (7.2 syntax)
RUN set -eux; \
    bin/otrs.SetPermissions.pl \
        --znuny-user=otrs \
        --web-group=www-data \
        /opt/otrs

# ── Apache: mod_perl + the Znuny vhost include shipped by Znuny
RUN set -eux; \
    a2enmod perl headers deflate filter rewrite; \
    a2dissite 000-default || true; \
    ln -sf ${OTRS_HOME}/scripts/apache2-httpd.include.conf \
           /etc/apache2/sites-available/zzz_znuny.conf; \
    a2ensite zzz_znuny

# ── Front door: bare host (/) → Znuny agent interface
COPY root-redirect.conf /etc/apache2/conf-available/root-redirect.conf
RUN a2enconf root-redirect

# ── Custom Redis cache backend (core 7.2 only ships FileStorable).
#    Placed in Custom/ which Znuny puts first in @INC (upgrade-safe).
COPY Cache/Redis.pm ${OTRS_HOME}/Custom/Kernel/System/Cache/Redis.pm
RUN set -eux; \
    chown -R otrs:www-data ${OTRS_HOME}/Custom; \
    perl -c ${OTRS_HOME}/Custom/Kernel/System/Cache/Redis.pm 2>/dev/null \
        || perl -I${OTRS_HOME} -I${OTRS_HOME}/Kernel/cpan-lib \
                -c ${OTRS_HOME}/Custom/Kernel/System/Cache/Redis.pm

COPY entrypoint.sh /usr/local/bin/entrypoint.sh
COPY Config.pm.tmpl ${OTRS_HOME}/Kernel/Config.pm.tmpl
RUN chmod +x /usr/local/bin/entrypoint.sh

EXPOSE 80
WORKDIR ${OTRS_HOME}
ENTRYPOINT ["/usr/local/bin/entrypoint.sh"]
CMD ["web"]
