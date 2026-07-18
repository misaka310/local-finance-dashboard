from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from mfblue.server import resolve_static_path


class StaticPathResolutionTests(unittest.TestCase):
    def test_resolves_root_and_nested_files_inside_frontend(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            frontend = Path(temp_dir) / "frontend"
            nested = frontend / "assets" / "app.js"
            nested.parent.mkdir(parents=True)
            nested.write_text("console.log('ok')", encoding="utf-8")
            (frontend / "index.html").write_text("ok", encoding="utf-8")

            self.assertEqual(resolve_static_path("/", frontend), (frontend / "index.html").resolve())
            self.assertEqual(resolve_static_path("/assets/app.js", frontend), nested.resolve())

    def test_rejects_parent_traversal_and_same_prefix_sibling(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            frontend = root / "frontend"
            sibling = root / "frontend_backup"
            frontend.mkdir()
            sibling.mkdir()
            (sibling / "secret.txt").write_text("secret", encoding="utf-8")

            self.assertIsNone(resolve_static_path("/../frontend_backup/secret.txt", frontend))
            self.assertIsNone(resolve_static_path("/../../outside.txt", frontend))

    def test_normalizes_dot_segments_without_rejecting_valid_paths(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            frontend = Path(temp_dir) / "frontend"
            asset = frontend / "assets" / "app.js"
            asset.parent.mkdir(parents=True)
            asset.write_text("ok", encoding="utf-8")

            self.assertEqual(resolve_static_path("/assets/../assets/app.js", frontend), asset.resolve())


if __name__ == "__main__":
    unittest.main()
