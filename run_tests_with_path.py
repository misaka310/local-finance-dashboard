from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path


class GitHubActionsTestResult(unittest.TextTestResult):
    """Emit failure details as GitHub annotations while preserving normal unittest output."""

    def _emit_annotation(self, test: unittest.case.TestCase, err: tuple[type[BaseException], BaseException, object], kind: str) -> None:
        if os.environ.get("GITHUB_ACTIONS", "").lower() != "true":
            return
        test_id = test.id()
        details = f"{test_id}\n{self._exc_info_to_string(err, test)}"
        escaped = details.replace("%", "%25").replace("\r", "%0D").replace("\n", "%0A")
        print(f"::error title=Python test {kind}::{escaped}")

    def addFailure(self, test: unittest.case.TestCase, err: tuple[type[BaseException], BaseException, object]) -> None:
        super().addFailure(test, err)
        self._emit_annotation(test, err, "failure")

    def addError(self, test: unittest.case.TestCase, err: tuple[type[BaseException], BaseException, object]) -> None:
        super().addError(test, err)
        self._emit_annotation(test, err, "error")


def main() -> int:
    project_root = Path(__file__).resolve().parent
    sys.path.insert(0, str(project_root / "src"))
    suite = unittest.TestLoader().discover(str(project_root / "tests"))
    result = unittest.TextTestRunner(verbosity=2, resultclass=GitHubActionsTestResult).run(suite)
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    raise SystemExit(main())
