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

# ── Custom GI write operations for the GertiAdmin webservice (#1G-a, D19).
#    Core GI cannot create CustomerCompany/CustomerUser; these wrap the native
#    Perl API. Same upgrade-safe Custom/ overlay as Cache::Redis above.
COPY Custom/Kernel/GenericInterface/Operation/CustomerCompany/CustomerCompanyAdd.pm \
     ${OTRS_HOME}/Custom/Kernel/GenericInterface/Operation/CustomerCompany/CustomerCompanyAdd.pm
COPY Custom/Kernel/GenericInterface/Operation/CustomerUser/CustomerUserAdd.pm \
     ${OTRS_HOME}/Custom/Kernel/GenericInterface/Operation/CustomerUser/CustomerUserAdd.pm
COPY Custom/Kernel/GenericInterface/Operation/CustomerUser/SetPassword.pm \
     ${OTRS_HOME}/Custom/Kernel/GenericInterface/Operation/CustomerUser/SetPassword.pm
RUN set -eux; \
    chown -R otrs:www-data ${OTRS_HOME}/Custom; \
    for m in \
        Custom/Kernel/GenericInterface/Operation/CustomerCompany/CustomerCompanyAdd.pm \
        Custom/Kernel/GenericInterface/Operation/CustomerUser/CustomerUserAdd.pm \
        Custom/Kernel/GenericInterface/Operation/CustomerUser/SetPassword.pm ; \
    do \
        perl -I${OTRS_HOME} -I${OTRS_HOME}/Kernel/cpan-lib -I${OTRS_HOME}/Custom \
             -c ${OTRS_HOME}/$m ; \
    done

# ── GertiAdmin webservice definition (#1G-a, D19). Baked into the image so the
#    deploy imports it idempotently (Admin::WebService::Add --source-path).
COPY webservices/GertiAdmin.yml ${OTRS_HOME}/webservices/GertiAdmin.yml
RUN chown -R otrs:www-data ${OTRS_HOME}/webservices

# ── Custom GI operations for the GertiTicket webservice (#1E). Portal ticketing:
#    open/list/detail/reply linked to a contract. Same Custom/ overlay pattern.
COPY Custom/Kernel/GenericInterface/Operation/GertiTicket/TicketCreate.pm \
     ${OTRS_HOME}/Custom/Kernel/GenericInterface/Operation/GertiTicket/TicketCreate.pm
COPY Custom/Kernel/GenericInterface/Operation/GertiTicket/TicketSearch.pm \
     ${OTRS_HOME}/Custom/Kernel/GenericInterface/Operation/GertiTicket/TicketSearch.pm
COPY Custom/Kernel/GenericInterface/Operation/GertiTicket/TicketGet.pm \
     ${OTRS_HOME}/Custom/Kernel/GenericInterface/Operation/GertiTicket/TicketGet.pm
COPY Custom/Kernel/GenericInterface/Operation/GertiTicket/TicketReply.pm \
     ${OTRS_HOME}/Custom/Kernel/GenericInterface/Operation/GertiTicket/TicketReply.pm
COPY Custom/Kernel/GenericInterface/Operation/GertiTicket/FormMeta.pm \
     ${OTRS_HOME}/Custom/Kernel/GenericInterface/Operation/GertiTicket/FormMeta.pm
COPY Custom/Kernel/GenericInterface/Operation/GertiTicket/TimeAccountingSince.pm \
     ${OTRS_HOME}/Custom/Kernel/GenericInterface/Operation/GertiTicket/TimeAccountingSince.pm
COPY Custom/Kernel/GenericInterface/Operation/GertiTicket/TimeAccountingAdd.pm \
     ${OTRS_HOME}/Custom/Kernel/GenericInterface/Operation/GertiTicket/TimeAccountingAdd.pm
COPY Custom/Kernel/GenericInterface/Operation/GertiTicket/AgentTicketSearch.pm \
     ${OTRS_HOME}/Custom/Kernel/GenericInterface/Operation/GertiTicket/AgentTicketSearch.pm
COPY Custom/Kernel/GenericInterface/Operation/GertiTicket/AgentTicketGet.pm \
     ${OTRS_HOME}/Custom/Kernel/GenericInterface/Operation/GertiTicket/AgentTicketGet.pm
COPY Custom/Kernel/GenericInterface/Operation/GertiTicket/ConfigItemSearch.pm \
     ${OTRS_HOME}/Custom/Kernel/GenericInterface/Operation/GertiTicket/ConfigItemSearch.pm
COPY Custom/Kernel/GenericInterface/Operation/GertiTicket/ConfigItemGet.pm \
     ${OTRS_HOME}/Custom/Kernel/GenericInterface/Operation/GertiTicket/ConfigItemGet.pm
COPY Custom/Kernel/GenericInterface/Operation/GertiTicket/TicketStats.pm \
     ${OTRS_HOME}/Custom/Kernel/GenericInterface/Operation/GertiTicket/TicketStats.pm
RUN set -eux; \
    chown -R otrs:www-data ${OTRS_HOME}/Custom; \
    for m in TicketCreate TicketSearch TicketGet TicketReply FormMeta TimeAccountingSince TimeAccountingAdd AgentTicketSearch AgentTicketGet ConfigItemSearch ConfigItemGet TicketStats ; do \
        perl -I${OTRS_HOME} -I${OTRS_HOME}/Kernel/cpan-lib -I${OTRS_HOME}/Custom \
             -c ${OTRS_HOME}/Custom/Kernel/GenericInterface/Operation/GertiTicket/$m.pm ; \
    done

# ── GertiTicket webservice definition (#1E) + DynamicField helper, baked in.
COPY webservices/GertiTicket.yml ${OTRS_HOME}/webservices/GertiTicket.yml
COPY scripts/ensure-gerti-dynamicfield.pl ${OTRS_HOME}/scripts/ensure-gerti-dynamicfield.pl
RUN chown -R otrs:www-data ${OTRS_HOME}/webservices ${OTRS_HOME}/scripts/ensure-gerti-dynamicfield.pl

# ── Znuny ITSM CMDB add-ons (#1K, R1K): baked for idempotent install at provision.
# Dependency order: GeneralCatalog → ITSMCore → ITSMConfigurationManagement (version 7.2.1).
# Source: https://addons.znuny.com/public/ (NOT download.znuny.org/releases/itsm/ — 404 for 7.2).
# Install at runtime by local path (Admin::Package::Install <name> fails; path install works).
# IMPORTANT: bake to ${OTRS_HOME}/itsm-opm (NOT ${OTRS_HOME}/var/...): /opt/otrs/var is a
# NAMED VOLUME (znuny-var) → anything under var/ in the image is SHADOWED at runtime by the
# volume mount, so var/packages would be empty in the running container. itsm-opm is on the
# image layer, always present.
RUN set -eux; \
    mkdir -p "${OTRS_HOME}/itsm-opm"; \
    for p in GeneralCatalog ITSMCore ITSMConfigurationManagement; do \
      curl -fSL --retry 4 --retry-delay 3 --retry-connrefused --connect-timeout 20 --max-time 240 \
        "https://addons.znuny.com/public/${p}-7.2.1.opm" \
        -o "${OTRS_HOME}/itsm-opm/${p}-7.2.1.opm"; \
    done; \
    chown -R otrs:www-data ${OTRS_HOME}/itsm-opm

COPY scripts/ensure-itsm.sh ${OTRS_HOME}/scripts/ensure-itsm.sh
RUN chmod +x ${OTRS_HOME}/scripts/ensure-itsm.sh && \
    chown otrs:www-data ${OTRS_HOME}/scripts/ensure-itsm.sh

# ── CMDB Computer fields helper (#1L, R1L): idempotent append of Disco/Memoria.
COPY scripts/ensure-cmdb-fields.pl ${OTRS_HOME}/scripts/ensure-cmdb-fields.pl
RUN chown otrs:www-data ${OTRS_HOME}/scripts/ensure-cmdb-fields.pl

COPY entrypoint.sh /usr/local/bin/entrypoint.sh
COPY Config.pm.tmpl ${OTRS_HOME}/Kernel/Config.pm.tmpl
RUN chmod +x /usr/local/bin/entrypoint.sh

EXPOSE 80
WORKDIR ${OTRS_HOME}
ENTRYPOINT ["/usr/local/bin/entrypoint.sh"]
CMD ["web"]
