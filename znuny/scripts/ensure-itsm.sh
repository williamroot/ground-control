#!/bin/bash
# ── ensure-itsm.sh — idempotent install of Znuny ITSM CMDB add-ons (#1K, R1K)
# Dependency order: GeneralCatalog → ITSMCore → ITSMConfigurationManagement
# Run as otrs user (or via su otrs -s /bin/bash -c "cd /opt/otrs && bash scripts/ensure-itsm.sh").
# Safe to re-run: already-installed packages are skipped.
set -e
cd /opt/otrs
for spec in \
    "GeneralCatalog:GeneralCatalog-7.2.1.opm" \
    "ITSMCore:ITSMCore-7.2.1.opm" \
    "ITSMConfigurationManagement:ITSMConfigurationManagement-7.2.1.opm"
do
    name="${spec%%:*}"; file="${spec##*:}"
    if bin/otrs.Console.pl Admin::Package::List | grep -qi "$name"; then
        echo "ITSM package $name already installed — skipping"
    else
        bin/otrs.Console.pl Admin::Package::Install "/opt/otrs/var/packages/$file"
    fi
done
echo "ITSM CMDB ensure: done"
