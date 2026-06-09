#!/bin/bash
# ── ensure-itsm.sh — idempotent install of Znuny ITSM CMDB add-ons (#1K, R1K)
# Dependency order: GeneralCatalog → ITSMCore → ITSMConfigurationManagement
# Run as otrs user (or via su otrs -s /bin/bash -c "cd /opt/otrs && bash scripts/ensure-itsm.sh").
# Safe to re-run: already-installed packages are skipped.
#
# IMPORTANT (single-cluster gotcha, #1K e2e): the package METADATA lives in the
# shared Postgres (persists across container recreates), but the package FILES
# (Kernel/System/ITSMConfigItem.pm, GeneralCatalog.pm, …) are written to the
# container's ephemeral layer at install time and are LOST when znuny-web is
# recreated from the image. So "Admin::Package::List shows it installed" does
# NOT mean the files are on disk. After ensuring metadata, we ALWAYS redeploy
# any package whose files are missing/incorrect via Admin::Package::ReinstallAll
# (idempotent: a no-op when everything is correctly deployed).
set -e
cd /opt/otrs
for spec in \
    "GeneralCatalog:GeneralCatalog-7.2.1.opm" \
    "ITSMCore:ITSMCore-7.2.1.opm" \
    "ITSMConfigurationManagement:ITSMConfigurationManagement-7.2.1.opm"
do
    name="${spec%%:*}"; file="${spec##*:}"
    if bin/otrs.Console.pl Admin::Package::List | grep -qi "$name"; then
        echo "ITSM package $name already installed (metadata) — skipping install"
    else
        bin/otrs.Console.pl Admin::Package::Install "/opt/otrs/itsm-opm/$file"
    fi
done

# Redeploy files for any package not correctly deployed on disk (idempotent).
# Covers the single-cluster gotcha above: DB says installed, files were wiped on
# container recreate. No-op when all files are already correctly deployed.
echo "ITSM CMDB: ensuring package files are deployed on disk (ReinstallAll)…"
bin/otrs.Console.pl Admin::Package::ReinstallAll || \
    echo "WARN: ReinstallAll returned non-zero (continuing)"

echo "ITSM CMDB ensure: done"
