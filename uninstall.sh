#!/usr/bin/env bash
# Remove PVE Summary CPU temperature + fan speed monitoring patches.
set -euo pipefail

[[ $EUID -eq 0 ]] || { echo "Must run as root"; exit 1; }

BACKUP_DIR="/root/backup/pve-mod"
# Also accept legacy backup path
[[ -d "${BACKUP_DIR}" ]] || BACKUP_DIR="/root/backup/pve-cputemp"

NODES_PM="/usr/share/perl5/PVE/API2/Nodes.pm"
PVE_JS="/usr/share/pve-manager/js/pvemanagerlib.js"

systemctl disable --now pve-sensors-update.timer 2>/dev/null || true
systemctl disable --now pve-cputemp-update.timer 2>/dev/null || true
rm -f /etc/systemd/system/pve-sensors-update.timer
rm -f /etc/systemd/system/pve-sensors-update.service
rm -f /etc/systemd/system/pve-cputemp-update.timer
rm -f /etc/systemd/system/pve-cputemp-update.service
rm -f /usr/local/sbin/pve-sensors-update
rm -f /usr/local/sbin/pve-cputemp-update
rm -f /usr/local/sbin/pve_sensors_parse.py
systemctl daemon-reload

if [[ -f "${BACKUP_DIR}/Nodes.pm.orig" ]]; then
    cp -a "${BACKUP_DIR}/Nodes.pm.orig" "${NODES_PM}"
    echo "Restored ${NODES_PM}"
else
    echo "WARNING: ${BACKUP_DIR}/Nodes.pm.orig missing; left Nodes.pm unchanged"
fi

if [[ -f "${BACKUP_DIR}/pvemanagerlib.js.orig" ]]; then
    cp -a "${BACKUP_DIR}/pvemanagerlib.js.orig" "${PVE_JS}"
    echo "Restored ${PVE_JS}"
else
    echo "WARNING: ${BACKUP_DIR}/pvemanagerlib.js.orig missing; left pvemanagerlib.js unchanged"
fi

systemctl restart pvedaemon pveproxy
echo "Uninstall complete."
echo "  RRD kept under /var/lib/rrdcached/db/pve-mod-cputemp/ and pve-mod-fanspeed/"
echo "  it87 module config left in /etc/modprobe.d/it87-fans.conf"
