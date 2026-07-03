import sys
from pathlib import Path
import unittest

# Add the project root to sys.path so 'src' can be found
project_root = Path(__file__).resolve().parents[0]
sys.path.insert(0, str(project_root / "src"))

# Discover and run all tests in the 'tests' directory
suite = unittest.TestLoader().discover(str(project_root / "tests"))
runner = unittest.TextTestRunner(verbosity=2)
runner.run(suite)
