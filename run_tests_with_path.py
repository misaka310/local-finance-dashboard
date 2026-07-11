from __future__ import annotations

import sys
import unittest
from pathlib import Path


def main() -> int:
    project_root = Path(__file__).resolve().parent
    sys.path.insert(0, str(project_root / "src"))
    suite = unittest.TestLoader().discover(str(project_root / "tests"))
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    raise SystemExit(main())
