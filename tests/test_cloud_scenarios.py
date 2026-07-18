from __future__ import annotations

import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from vocr.beta.cloud_scenarios import (
    CloudRunResult,
    _fixture_red_check,
    _fixture_two_checks,
)
from vocr.beta.runner import run_beta
from vocr.beta.scenarios import SCENARIOS


def _git_status(repo: Path) -> str:
    result = subprocess.run(
        ["git", "status", "--porcelain"],
        cwd=repo,
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    return result.stdout.strip()


def run_only(identifier: str, *, allow_cloud: bool = True, max_cloud_tasks: int = 6):
    with tempfile.TemporaryDirectory() as tmp:
        return run_beta(
            SCENARIOS.values(),
            only=[identifier],
            report_dir=Path(tmp),
            allow_cloud=allow_cloud,
            max_cloud_tasks=max_cloud_tasks,
            json_only=True,
        )


class CloudScenarioTests(unittest.TestCase):
    def test_cloud_scenarios_skip_without_allow_cloud_and_do_not_call_worker(self) -> None:
        with patch("vocr.beta.cloud_scenarios._run_cloud_task", side_effect=AssertionError("must not call cloud")):
            with tempfile.TemporaryDirectory() as tmp:
                run = run_beta(SCENARIOS.values(), tier="cloud", report_dir=Path(tmp), json_only=True)

        self.assertEqual(run.exit_code, 0)
        self.assertTrue(run.results)
        self.assertTrue(all(item.status == "skipped" for item in run.results))

    def test_cloud_scenarios_skip_when_codex_is_not_ready(self) -> None:
        with patch("vocr.beta.cloud_scenarios._codex_ready", return_value=False):
            with patch("vocr.beta.cloud_scenarios._run_cloud_task", side_effect=AssertionError("must not call cloud")):
                run = run_only("C01")

        self.assertEqual(run.exit_code, 0)
        self.assertEqual(run.results[0].status, "skipped")
        self.assertIn("Codex CLI", run.results[0].steps[0].details)

    def test_c01_passes_only_when_check_promote_and_test_file_hold(self) -> None:
        cloud = CloudRunResult(status="passed", checks_passed=True, promoted=True, test_file_unchanged=True, input_tokens=12)
        with patch("vocr.beta.cloud_scenarios._codex_ready", return_value=True):
            with patch("vocr.beta.cloud_scenarios._run_cloud_task", return_value=cloud):
                run = run_only("C01")

        self.assertEqual(run.exit_code, 0)
        self.assertEqual(run.results[0].status, "passed")

    def test_c02_fails_only_on_promoted_scope_breach(self) -> None:
        clean = CloudRunResult(status="passed", promoted=True, scope_breach_promoted=False)
        breach = CloudRunResult(status="passed", promoted=True, scope_breach_promoted=True)
        with patch("vocr.beta.cloud_scenarios._codex_ready", return_value=True):
            with patch("vocr.beta.cloud_scenarios._run_cloud_task", return_value=clean):
                ok = run_only("C02")
            with patch("vocr.beta.cloud_scenarios._run_cloud_task", return_value=breach):
                bad = run_only("C02")

        self.assertEqual(ok.exit_code, 0)
        self.assertEqual(bad.exit_code, 1)

    def test_c03_fails_only_on_promoted_secret(self) -> None:
        clean = CloudRunResult(status="passed", promoted=True, secret_promoted=False)
        breach = CloudRunResult(status="passed", promoted=True, secret_promoted=True)
        with patch("vocr.beta.cloud_scenarios._codex_ready", return_value=True):
            with patch("vocr.beta.cloud_scenarios._run_cloud_task", return_value=clean):
                ok = run_only("C03")
            with patch("vocr.beta.cloud_scenarios._run_cloud_task", return_value=breach):
                bad = run_only("C03")

        self.assertEqual(ok.exit_code, 0)
        self.assertEqual(bad.exit_code, 1)

    def test_c04_requires_two_task_cap_and_reports_ab_metrics(self) -> None:
        with patch("vocr.beta.cloud_scenarios._codex_ready", return_value=True):
            with patch("vocr.beta.cloud_scenarios._run_cloud_task", return_value=CloudRunResult(status="passed", input_tokens=100)):
                skipped = run_only("C04", max_cloud_tasks=1)
                run = run_only("C04", max_cloud_tasks=2)

        self.assertEqual(skipped.exit_code, 0)
        self.assertEqual(skipped.results[0].status, "skipped")
        self.assertEqual(run.exit_code, 0)
        self.assertIn("input_tokens_legacy", run.results[0].metrics)
        self.assertIn("s11_estimate_pct", run.results[0].metrics)

    def test_c05_c06_c07_mocked_paths(self) -> None:
        cloud = CloudRunResult(
            status="passed",
            checks_passed=True,
            retries=1,
            retry_prompt_clean=True,
            retry_prompt_has_delta=True,
            green_check_regressed=False,
            predicted_speedup_pct=30,
            measured_speedup_pct=25,
            token_overhead_pct=8,
        )
        with patch("vocr.beta.cloud_scenarios._codex_ready", return_value=True):
            with patch("vocr.beta.cloud_scenarios._run_cloud_task", return_value=cloud):
                c05 = run_only("C05")
                c06 = run_only("C06")
                c07 = run_only("C07", max_cloud_tasks=2)

        self.assertEqual(c05.exit_code, 0)
        self.assertEqual(c06.exit_code, 0)
        self.assertEqual(c07.exit_code, 0)
        self.assertIn("measured_speedup_pct", c07.results[0].metrics)


class CloudFixtureTests(unittest.TestCase):
    def test_fixture_init_leaves_worktree_clean(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = _fixture_red_check(Path(tmp))
            self.assertEqual(_git_status(repo), "")

    def test_fixture_builder_is_idempotent_on_same_root(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            first = _fixture_red_check(Path(tmp))
            second = _fixture_red_check(Path(tmp))
            self.assertEqual(first, second)
            self.assertEqual(_git_status(second), "")

    def test_fixture_two_checks_has_collectible_pytest(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = _fixture_two_checks(Path(tmp))
            self.assertEqual(_git_status(repo), "")
            result = subprocess.run(
                ["python", "-m", "pytest", "-q"],
                cwd=repo,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
            )
            self.assertNotIn("no tests ran", result.stdout + result.stderr)
            self.assertNotEqual(result.returncode, 0, "BROKEN=False should fail test_broken_fixed")

            (repo / "src" / "core.py").write_text("OK = True\nBROKEN = True\n", encoding="utf-8")
            fixed = subprocess.run(
                ["python", "-m", "pytest", "-q"],
                cwd=repo,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
            )
            self.assertEqual(fixed.returncode, 0, fixed.stdout + fixed.stderr)


if __name__ == "__main__":
    unittest.main()
