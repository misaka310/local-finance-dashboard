from __future__ import annotations

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class PublicDemoTests(unittest.TestCase):
    def test_build_public_demo_creates_synthetic_single_page_site(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            output = Path(temp_dir) / "site" / "index.html"
            completed = subprocess.run(
                [sys.executable, "scripts/build_public_demo.py", "--output", str(output)],
                cwd=ROOT,
                text=True,
                capture_output=True,
                check=False,
            )

            self.assertEqual(completed.returncode, 0, completed.stderr)
            self.assertTrue(output.exists())
            self.assertTrue((output.parent / ".nojekyll").exists())

            html = output.read_text(encoding="utf-8")
            self.assertIn("Local Finance Dashboard — 合成データデモ", html)
            self.assertIn("合成データの公開デモ", html)
            self.assertIn("スーパーマーケット", html)
            self.assertIn("全世界株式インデックス", html)
            self.assertIn('id="mfblue-data"', html)
            self.assertNotIn("synthetic public demo data", html)
            self.assertNotIn("/api/", html)

    def test_root_exposes_only_clear_user_entrypoints(self) -> None:
        primary_sample = (ROOT / "start_sample_dashboard.cmd").read_text(encoding="utf-8")
        primary_launch = (ROOT / "launch_dashboard.cmd").read_text(encoding="utf-8")

        self.assertIn("scripts\\01_setup.ps1", primary_sample)
        self.assertIn("scripts\\04_run_app.ps1", primary_launch)
        self.assertFalse((ROOT / "start_sample_mfblue.cmd").exists())
        self.assertFalse((ROOT / "launch_mfblue.cmd").exists())
        self.assertFalse((ROOT / "launch_mfblue_with_codex_analysis.bat").exists())


if __name__ == "__main__":
    unittest.main()
