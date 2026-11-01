#!/usr/bin/env python3
"""Parse lm-sensors JSON for CPU package temperature and max fan RPM."""

from __future__ import annotations

import glob
from typing import Any


def input_temp(entry: Any) -> float | None:
    if not isinstance(entry, dict):
        return None
    if "temp1_input" in entry and isinstance(entry["temp1_input"], (int, float)):
        return float(entry["temp1_input"])
    for subkey, value in entry.items():
        if subkey.endswith("_input") and isinstance(value, (int, float)):
            return float(value)
    return None


def parse_sensors(data: dict[str, Any]) -> tuple[float | None, float | None]:
    """Return (cpu_temp_c, max_fan_rpm) from `sensors -j` object."""
    temp: float | None = None
    fan: float | None = None

    for chip, payload in data.items():
        if not isinstance(payload, dict):
            continue
        if temp is None and any(x in chip for x in ("coretemp", "k10temp", "zenpower")):
            for key in ("Package id 0", "Tctl", "Tdie"):
                value = input_temp(payload.get(key))
                if value is not None:
                    temp = value
                    break
            if temp is None:
                for entry in payload.values():
                    value = input_temp(entry)
                    if value is not None:
                        temp = value
                        break
        for _label, entry in payload.items():
            if not isinstance(entry, dict):
                continue
            for subkey, value in entry.items():
                if (
                    subkey.startswith("fan")
                    and subkey.endswith("_input")
                    and isinstance(value, (int, float))
                ):
                    if value > 0 and (fan is None or value > fan):
                        fan = float(value)

    return temp, fan


def read_hwmon_fan_max() -> float | None:
    fan: float | None = None
    for path in sorted(glob.glob("/sys/class/hwmon/hwmon*/fan*_input")):
        try:
            with open(path, encoding="utf-8") as fh:
                value = float(fh.read().strip())
        except (OSError, ValueError):
            continue
        if value > 0 and (fan is None or value > fan):
            fan = value
    return fan


def format_sample(temp: float | None, fan: float | None) -> str:
    temp_s = f"{temp:.2f}" if temp is not None else ""
    fan_s = f"{fan:.0f}" if fan is not None else ""
    return f"{temp_s} {fan_s}"


def sample_from_sensors_json(raw: str) -> tuple[float | None, float | None]:
    import json

    try:
        data = json.loads(raw) if raw else {}
    except json.JSONDecodeError:
        data = {}
    if not isinstance(data, dict):
        data = {}
    temp, fan = parse_sensors(data)
    if fan is None:
        fan = read_hwmon_fan_max()
    return temp, fan


def main() -> None:
    import subprocess
    import sys

    try:
        raw = subprocess.check_output(
            ["sensors", "-j"], stderr=subprocess.DEVNULL, text=True
        )
    except (OSError, subprocess.CalledProcessError):
        raw = ""
    temp, fan = sample_from_sensors_json(raw)
    sys.stdout.write(format_sample(temp, fan) + "\n")


if __name__ == "__main__":
    main()
