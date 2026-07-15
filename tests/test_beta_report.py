from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from vocr.beta.report import write_reports
from vocr.beta.runner import ScenarioResult


class BetaReportTests(unittest.TestCase):
    def test_write_reports_creates_json_and_markdown(self) -> None:
        result = ScenarioResult(id="S00", title="reference", tier="core", hard=True, status="passed", duration_s=0.1)

        with tempfile.TemporaryDirectory() as tmp:
            json_path, md_path = write_reports([result], Path(tmp), json_only=False)
            payload = json.loads(json_path.read_text(encoding="utf-8"))

            self.assertEqual(payload["verdict"], "BESTANDEN")
            self.assertTrue(md_path.exists())


if __name__ == "__main__":
    unittest.main()
