#!/usr/bin/env bash
# Regression: refresh .orig whenever current PVE file is unpatched (e.g. after upgrade).
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
INSTALL="${ROOT}/install.sh"

# Contract: must refresh .orig on unpatched files even if a stale .orig already exists.
if grep -qE '\[\[ ! -f "\$\{BACKUP_DIR\}/Nodes\.pm\.orig" \]\] && ! grep' "${INSTALL}"; then
    echo "FAIL: install.sh still skips refreshing .orig when a stale file exists" >&2
    exit 1
fi
if ! grep -qE 'if ! grep -qE .*PVE_CPUTEMP_MOD\|PVE_FANSPEED_MOD.*NODES_PM' "${INSTALL}"; then
    echo "FAIL: install.sh missing unpatched→refresh .orig for Nodes.pm" >&2
    exit 1
fi
if ! grep -qE 'if ! grep -qE .*PVE_CPUTEMP_MOD\|PVE_FANSPEED_MOD.*PVE_JS' "${INSTALL}"; then
    echo "FAIL: install.sh missing unpatched→refresh .orig for pvemanagerlib.js" >&2
    exit 1
fi

# Behavioral model of the intended helper
refresh_orig_if_unpatched() {
    local src="$1"
    local dest="$2"
    if ! grep -qE 'PVE_CPUTEMP_MOD|PVE_FANSPEED_MOD' "${src}"; then
        cp -a "${src}" "${dest}"
    fi
}

tmpdir="$(mktemp -d)"
trap 'rm -rf "${tmpdir}"' EXIT

mkdir -p "${tmpdir}/backup"
echo "OLD_VERSION_CONTENT" >"${tmpdir}/backup/Nodes.pm.orig"
echo "NEW_VERSION_UNPATCHED" >"${tmpdir}/Nodes.pm"

refresh_orig_if_unpatched "${tmpdir}/Nodes.pm" "${tmpdir}/backup/Nodes.pm.orig"

got="$(cat "${tmpdir}/backup/Nodes.pm.orig")"
if [[ "${got}" != "NEW_VERSION_UNPATCHED" ]]; then
    echo "FAIL: expected .orig refreshed to current unpatched file, got: ${got}" >&2
    exit 1
fi

echo "PATCHED PVE_CPUTEMP_MOD" >"${tmpdir}/Nodes.pm"
echo "CLEAN_ORIG" >"${tmpdir}/backup/Nodes.pm.orig"
refresh_orig_if_unpatched "${tmpdir}/Nodes.pm" "${tmpdir}/backup/Nodes.pm.orig"
got="$(cat "${tmpdir}/backup/Nodes.pm.orig")"
if [[ "${got}" != "CLEAN_ORIG" ]]; then
    echo "FAIL: patched file must not overwrite .orig, got: ${got}" >&2
    exit 1
fi

echo "OK: install backup refresh behavior"
