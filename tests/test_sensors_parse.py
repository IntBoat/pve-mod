#!/usr/bin/env python3
"""Tests for sensor JSON → CPU temp / fan RPM parsing (high-risk collector logic)."""

from __future__ import annotations

import importlib.util
import unittest
import unittest.mock
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


sensors = load_module("pve_sensors_parse", ROOT / "bin" / "pve_sensors_parse.py")


class SensorsParseTests(unittest.TestCase):
    def test_coretemp_package_and_max_fan(self) -> None:
        data = {
            "coretemp-isa-0000": {
                "Package id 0": {"temp1_input": 61.0},
                "Core 0": {"temp2_input": 55.0},
            },
            "it8628-isa-0a30": {
                "fan1": {"fan1_input": 0.0},
                "fan2": {"fan2_input": 5578.0},
                "fan3": {"fan3_input": 1200.0},
            },
        }
        temp, fan = sensors.parse_sensors(data)
        self.assertEqual(temp, 61.0)
        self.assertEqual(fan, 5578.0)

    def test_k10temp_tctl(self) -> None:
        data = {"k10temp-pci-00c3": {"Tctl": {"temp1_input": 72.5}}}
        temp, fan = sensors.parse_sensors(data)
        self.assertEqual(temp, 72.5)
        self.assertIsNone(fan)

    def test_empty(self) -> None:
        temp, fan = sensors.parse_sensors({})
        self.assertIsNone(temp)
        self.assertIsNone(fan)

    def test_format_sample_line(self) -> None:
        self.assertEqual(sensors.format_sample(61.0, 5578.0), "61.00 5578")
        self.assertEqual(sensors.format_sample(None, 100.0), " 100")
        self.assertEqual(sensors.format_sample(40.0, None), "40.00 ")
        self.assertEqual(sensors.format_sample(None, None), " ")

    def test_sample_from_invalid_json(self) -> None:
        with unittest.mock.patch.object(sensors, "read_hwmon_fan_max", return_value=None):
            temp, fan = sensors.sample_from_sensors_json("not-json")
        self.assertIsNone(temp)
        self.assertIsNone(fan)


if __name__ == "__main__":
    unittest.main()
