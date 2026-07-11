from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class RefactorStructureTests(unittest.TestCase):
    def test_frontend_is_split_and_unimplemented_navigation_is_disabled(self):
        frontend = ROOT / "frontend"
        index = (frontend / "index.html").read_text(encoding="utf-8")
        for filename in (
            "app-core.js",
            "app-assets.js",
            "app-budget.js",
            "app-analysis.js",
            "app-bootstrap.js",
        ):
            self.assertTrue((frontend / filename).is_file(), filename)
            self.assertIn(f'src="/{filename}', index)
        for nav_id in ("navHome", "navTransfer", "navSettings"):
            self.assertRegex(index, rf'<button id="{nav_id}"[^>]* disabled[^>]*>')
        self.assertFalse((frontend / "app.mod.js").exists())
        self.assertFalse((frontend / "app.mod2.js").exists())

    def test_database_facade_and_responsibility_modules_exist(self):
        package = ROOT / "src" / "mfblue"
        for filename in ("db_common.py", "db_schema.py", "db_budget.py", "db_assets.py"):
            self.assertTrue((package / filename).is_file(), filename)
        facade = (package / "db.py").read_text(encoding="utf-8")
        self.assertIn("Compatibility facade", facade)


if __name__ == "__main__":
    unittest.main()
