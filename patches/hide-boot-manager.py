#!/usr/bin/env python3
"""Hide Boot Mode and Manager Version in StatusView; keep CPU temp + fan rows."""

from __future__ import annotations

import sys
from pathlib import Path

JS = Path("/usr/share/pve-manager/js/pvemanagerlib.js")
MARKER = "PVE_HIDE_BOOT_MANAGER"

BOOT_AND_VERSION = """        {
            colspan: 2,
            title: gettext('Boot Mode'),
            printBar: false,
            textField: 'boot-info',
            renderer: (boot) => {
                if (boot.mode === 'legacy-bios') {
                    return 'Legacy BIOS';
                } else if (boot.mode === 'efi') {
                    return `EFI${boot.secureboot ? ' (Secure Boot)' : ''}`;
                }
                return Proxmox.Utils.unknownText;
            },
            value: '',
        },
        {
            itemId: 'version',
            colspan: 2,
            printBar: false,
            title: gettext('Manager Version'),
            textField: 'pveversion',
            value: '',
        },
"""


def main() -> int:
    text = JS.read_text()
    if MARKER in text and "title: gettext('Boot Mode')" not in text[
        text.find("alias: 'widget.pveNodeStatus'") : text.find("alias: 'widget.pveNodeStatus'")
        + 4000
    ]:
        print("Already applied.")
        return 0

    if BOOT_AND_VERSION not in text:
        # Already removed?
        idx = text.find("alias: 'widget.pveNodeStatus'")
        chunk = text[idx : idx + 4000] if idx >= 0 else ""
        if "title: gettext('Boot Mode')" not in chunk and "title: gettext('Manager Version')" not in chunk:
            print("Boot Mode / Manager Version already absent from StatusView.")
            return 0
        raise RuntimeError("Boot Mode / Manager Version block not found")

    text = text.replace(
        BOOT_AND_VERSION,
        f"        // {MARKER}: removed Boot Mode + Manager Version for layout\n",
        1,
    )

    for old, new in (
        ("height: 410, // PVE_CPUTEMP_MOD PVE_FANSPEED_MOD", "height: 360, // PVE_CPUTEMP_MOD PVE_FANSPEED_MOD"),
        ("height: 380, // PVE_CPUTEMP_MOD", "height: 360, // PVE_CPUTEMP_MOD"),
    ):
        if old in text:
            text = text.replace(old, new, 1)
            break

    JS.write_text(text)

    idx = text.find("alias: 'widget.pveNodeStatus'")
    chunk = text[idx : idx + 4000]
    if "title: gettext('Boot Mode')" in chunk or "title: gettext('Manager Version')" in chunk:
        raise RuntimeError("removal verification failed")
    print("Removed Boot Mode and Manager Version from StatusView.")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:  # noqa: BLE001
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(1)
