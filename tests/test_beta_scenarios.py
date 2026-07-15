from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from typer.testing import CliRunner

from vocr.beta.runner import run_beta
from vocr.beta.scenarios import SCENARIOS
from vocr.cli.app import app


class BetaScenarioTests(unittest.TestCase):
    def test_core_smoke_scenarios_pass(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run = run_beta(SCENARIOS.values(), only=["S00", "S02", "S18"], report_dir=Path(tmp), json_only=True)

        self.assertEqual(run.exit_code, 0)
        self.assertEqual([item.status for item in run.results], ["passed", "passed", "passed"])

    def test_cli_lists_scenarios(self) -> None:
        result = CliRunner().invoke(app, ["beta", "--list"])

        self.assertEqual(result.exit_code, 0, result.output)
        self.assertIn("S00", result.output)
        self.assertIn("S19", result.output)

    def test_cli_runs_selected_scenarios(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            result = CliRunner().invoke(app, ["beta", "--only", "S00", "--report-dir", tmp, "--json-only"])

        self.assertEqual(result.exit_code, 0, result.output)
        self.assertIn("S00 pure-cloud-reference: passed", result.output)


if __name__ == "__main__":
    unittest.main()
