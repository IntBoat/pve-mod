#!/usr/bin/env python3
"""Ensure CPU patcher validates JS before writing Nodes.pm."""

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


apply_patches = load_module("apply_patches_atomic", ROOT / "patches" / "apply-patches.py")


class ApplyPatchesAtomicTests(unittest.TestCase):
    def test_main_does_not_write_nodes_when_js_patch_fails(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            nodes_path = tmp_path / "Nodes.pm"
            js_path = tmp_path / "pvemanagerlib.js"
            nodes_path.write_text((FIXTURES / "nodes_snippet.pm").read_text())
            js_path.write_text("not a pve ui bundle")
            before = nodes_path.read_text()

            with mock.patch.object(apply_patches, "NODES", nodes_path), mock.patch.object(
                apply_patches, "JS", js_path
            ):
                raised = False
                try:
                    apply_patches.main()
                except Exception:
                    raised = True
                self.assertTrue(raised)

            self.assertEqual(nodes_path.read_text(), before)


if __name__ == "__main__":
    unittest.main()
