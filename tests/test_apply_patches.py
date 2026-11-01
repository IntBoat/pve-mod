#!/usr/bin/env python3
"""Tests for CPU temperature patch transforms (pure functions)."""

from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = Path(__file__).resolve().parent / "fixtures"


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


apply_patches = load_module("apply_patches", ROOT / "patches" / "apply-patches.py")


class ApplyPatchesTests(unittest.TestCase):
    def setUp(self) -> None:
        self.nodes = (FIXTURES / "nodes_snippet.pm").read_text()
        self.js = (FIXTURES / "pvemanagerlib_snippet.js").read_text()

    def test_patch_nodes_injects_marker_child_api_and_status(self) -> None:
        out = apply_patches.patch_nodes(self.nodes)
        self.assertIn("PVE_CPUTEMP_MOD", out)
        self.assertIn("{ name => 'cputemprrddata' }", out)
        self.assertIn("name => 'cputemprrddata'", out)
        self.assertIn("$res->{cputemp}", out)
        # idempotent
        self.assertEqual(out, apply_patches.patch_nodes(out))

    def test_patch_js_adds_model_widget_chart_and_removes_boot_manager(self) -> None:
        out = apply_patches.patch_js(self.js)
        self.assertIn("PVE_CPUTEMP_MOD", out)
        self.assertIn("pve-rrd-cputemp", out)
        self.assertIn("itemId: 'cputemp'", out)
        self.assertIn("cputempRrdStore", out)
        self.assertIn("cputemprrddata", out)
        chunk_start = out.find("alias: 'widget.pveNodeStatus'")
        chunk = out[chunk_start : chunk_start + 4000]
        self.assertNotIn("title: gettext('Boot Mode')", chunk)
        self.assertNotIn("title: gettext('Manager Version')", chunk)
        self.assertEqual(out, apply_patches.patch_js(out))

    def test_patch_js_requires_known_anchors(self) -> None:
        with self.assertRaises(RuntimeError):
            apply_patches.patch_js("no anchors here")


if __name__ == "__main__":
    unittest.main()
