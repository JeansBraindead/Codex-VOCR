from __future__ import annotations

import subprocess
import tempfile
import unittest
from pathlib import Path

from vocr.beta.fixtures import INJECTION_MARKER, make_repo


class BetaFixtureTests(unittest.TestCase):
    def test_make_repo_creates_deterministic_git_fixture(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = make_repo(Path(tmp) / "repo")
            head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=root, text=True, capture_output=True, check=False)

            self.assertEqual(head.returncode, 0, head.stderr)
            self.assertIn(INJECTION_MARKER, (root / "docs" / "notes.md").read_text(encoding="utf-8"))
            self.assertTrue((root / "checks" / "green_check.sh").exists())


if __name__ == "__main__":
    unittest.main()
