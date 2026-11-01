#!/usr/bin/env python3
"""Tests for fan speed patches, including atomic dual-file writes."""

from __future__ import annotations

import importlib.util
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = Path(__file__).resolve().parent / "fixtures"


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


apply_patches = load_module("apply_patches", ROOT / "patches" / "apply-patches.py")
apply_fan = load_module("apply_fan_patches", ROOT / "patches" / "apply-fan-patches.py")


class ApplyFanPatchesTests(unittest.TestCase):
    def setUp(self) -> None:
        nodes = (FIXTURES / "nodes_snippet.pm").read_text()
        js = (FIXTURES / "pvemanagerlib_snippet.js").read_text()
        self.nodes_cpu = apply_patches.patch_nodes(nodes)
        self.js_cpu = apply_patches.patch_js(js)

    def test_patch_nodes_adds_fanspeed_api_and_status(self) -> None:
        out = apply_fan.patch_nodes(self.nodes_cpu)
        self.assertIn("PVE_FANSPEED_MOD", out)
        self.assertIn("{ name => 'fanspeedrrddata' }", out)
        self.assertIn("$res->{fanspeed}", out)
        self.assertEqual(out, apply_fan.patch_nodes(out))

    def test_patch_js_adds_fan_store_chart_and_widget(self) -> None:
        out = apply_fan.patch_js(self.js_cpu)
        self.assertIn("PVE_FANSPEED_MOD", out)
        self.assertIn("pve-rrd-fanspeed", out)
        self.assertIn("itemId: 'fanspeed'", out)
        self.assertIn("fanspeedRrdStore", out)
        self.assertIn("fanspeedrrddata", out)
        self.assertIn("fanspeedRrdStore.startUpdate()", out)
        self.assertEqual(out, apply_fan.patch_js(out))

    def test_patch_js_requires_cputemp_first(self) -> None:
        raw_js = (FIXTURES / "pvemanagerlib_snippet.js").read_text()
        with self.assertRaises(RuntimeError):
            apply_fan.patch_js(raw_js)

    def test_main_does_not_write_nodes_when_js_patch_fails(self) -> None:
        """Regression: Nodes.pm must not be mutated if JS patching raises."""
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            nodes_path = tmp_path / "Nodes.pm"
            js_path = tmp_path / "pvemanagerlib.js"
            nodes_path.write_text(self.nodes_cpu)
            # JS lacks required anchors after CPU patch → fan JS patch fails
            js_path.write_text("Ext.define('pve-rrd-node', {\n});\n")
            before = nodes_path.read_text()

            with mock.patch.object(apply_fan, "NODES", nodes_path), mock.patch.object(
                apply_fan, "JS", js_path
            ):
                raised = False
                try:
                    apply_fan.main()
                except Exception:
                    raised = True
                self.assertTrue(raised, "main() should fail when JS cannot be patched")

            self.assertEqual(
                nodes_path.read_text(),
                before,
                "Nodes.pm was written before JS patch validation finished",
            )


if __name__ == "__main__":
    unittest.main()
