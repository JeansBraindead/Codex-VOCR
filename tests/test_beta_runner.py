from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

from vocr.beta.runner import BetaContext, Scenario, ScenarioResult, beta_exit_code, run_beta, set_env


class BetaRunnerTests(unittest.TestCase):
    def test_set_env_restores_previous_values(self) -> None:
        os.environ["VOCR_BETA_TEST"] = "before"

        with set_env({"VOCR_BETA_TEST": "during", "VOCR_BETA_EMPTY": "x"}):
            self.assertEqual(os.environ["VOCR_BETA_TEST"], "during")
            self.assertEqual(os.environ["VOCR_BETA_EMPTY"], "x")

        self.assertEqual(os.environ["VOCR_BETA_TEST"], "before")
        self.assertNotIn("VOCR_BETA_EMPTY", os.environ)
        os.environ.pop("VOCR_BETA_TEST", None)

    def test_run_beta_captures_scenario_exceptions(self) -> None:
        def boom(ctx: BetaContext) -> ScenarioResult:
            raise RuntimeError("boom")

        scenario = Scenario("SX", "boom", "core", True, boom)
        with tempfile.TemporaryDirectory() as tmp:
            run = run_beta([scenario], report_dir=Path(tmp), json_only=True)
            report_exists = Path(run.report_json).exists()

        self.assertEqual(run.exit_code, 1)
        self.assertEqual(run.results[0].status, "failed")
        self.assertTrue(report_exists)

    def test_run_beta_reports_progress_events(self) -> None:
        def ok(ctx: BetaContext) -> ScenarioResult:
            return ScenarioResult(id="S1", title="ok", tier="core", hard=True, status="passed", duration_s=0)

        events: list[str] = []
        scenario = Scenario("S1", "ok", "core", True, ok)
        with tempfile.TemporaryDirectory() as tmp:
            run = run_beta(
                [scenario],
                report_dir=Path(tmp),
                json_only=True,
                on_progress=lambda event, payload: events.append(event),
            )

        self.assertEqual(run.exit_code, 0)
        self.assertEqual(events, ["selected", "start", "finish", "report"])

    def test_exit_code_distinguishes_soft_failures(self) -> None:
        self.assertEqual(
            beta_exit_code([ScenarioResult(id="S", title="soft", tier="core", hard=False, status="failed", duration_s=0)]),
            2,
        )


if __name__ == "__main__":
    unittest.main()
