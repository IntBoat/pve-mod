#!/usr/bin/env bash
# Install PVE Summary CPU temperature + fan speed monitoring.
set -euo pipefail

[[ $EUID -eq 0 ]] || { echo "Must run as root"; exit 1; }

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKUP_DIR="/root/backup/pve-mod"
STAMP="$(date +%Y%m%d_%H%M%S)"
NODES_PM="/usr/share/perl5/PVE/API2/Nodes.pm"
PVE_JS="/usr/share/pve-manager/js/pvemanagerlib.js"

mkdir -p "${BACKUP_DIR}"

echo "[pve-mod] Installing dependencies..."
DEBIAN_FRONTEND=noninteractive apt-get install -y rrdtool lm-sensors >/dev/null

echo "[pve-mod] Configuring ITE Super-IO fan sensors (it87)..."
install -m 0644 "${SCRIPT_DIR}/modprobe/it87-fans.conf" /etc/modprobe.d/it87-fans.conf
install -m 0644 "${SCRIPT_DIR}/modprobe/it87.conf" /etc/modules-load.d/it87.conf
modprobe it87 force_id=0x8628 2>/dev/null || true

echo "[pve-mod] Installing collector..."
install -m 0755 "${SCRIPT_DIR}/bin/pve-sensors-update" /usr/local/sbin/pve-sensors-update
# Compat symlink for earlier deployments
ln -sfn /usr/local/sbin/pve-sensors-update /usr/local/sbin/pve-cputemp-update
install -m 0644 "${SCRIPT_DIR}/systemd/pve-sensors-update.service" /etc/systemd/system/pve-sensors-update.service
install -m 0644 "${SCRIPT_DIR}/systemd/pve-sensors-update.timer" /etc/systemd/system/pve-sensors-update.timer

# Migrate old timer name if present
if systemctl list-unit-files | grep -q '^pve-cputemp-update.timer'; then
    systemctl disable --now pve-cputemp-update.timer 2>/dev/null || true
    rm -f /etc/systemd/system/pve-cputemp-update.timer /etc/systemd/system/pve-cputemp-update.service
fi

/usr/local/sbin/pve-sensors-update || true

systemctl daemon-reload
systemctl enable --now pve-sensors-update.timer

echo "[pve-mod] Backing up PVE files..."
if [[ ! -f "${BACKUP_DIR}/Nodes.pm.orig" ]] && ! grep -qE 'PVE_CPUTEMP_MOD|PVE_FANSPEED_MOD' "${NODES_PM}"; then
    cp -a "${NODES_PM}" "${BACKUP_DIR}/Nodes.pm.orig"
fi
if [[ ! -f "${BACKUP_DIR}/pvemanagerlib.js.orig" ]] && ! grep -qE 'PVE_CPUTEMP_MOD|PVE_FANSPEED_MOD' "${PVE_JS}"; then
    cp -a "${PVE_JS}" "${BACKUP_DIR}/pvemanagerlib.js.orig"
fi
cp -a "${NODES_PM}" "${BACKUP_DIR}/Nodes.pm.${STAMP}"
cp -a "${PVE_JS}" "${BACKUP_DIR}/pvemanagerlib.js.${STAMP}"

echo "[pve-mod] Applying CPU temperature patches..."
python3 "${SCRIPT_DIR}/patches/apply-patches.py"

echo "[pve-mod] Applying fan speed patches..."
python3 "${SCRIPT_DIR}/patches/apply-fan-patches.py"

perl -c "${NODES_PM}"

echo "[pve-mod] Restarting pveproxy/pvedaemon..."
systemctl restart pvedaemon pveproxy

echo "[pve-mod] Done."
echo "  - Hard-reload the PVE web UI (clear cache)"
echo "  - Backups: ${BACKUP_DIR}"
echo "  - Uninstall: ${SCRIPT_DIR}/uninstall.sh"
