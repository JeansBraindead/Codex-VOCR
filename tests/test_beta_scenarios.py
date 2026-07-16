from __future__ import annotations

import tempfile
import unittest
from unittest.mock import patch
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

    def test_s11_reports_prompt_token_savings(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run = run_beta(SCENARIOS.values(), only=["S11"], report_dir=Path(tmp), json_only=True)

        self.assertEqual(run.exit_code, 0)
        result = run.results[0]
        self.assertFalse(result.hard)
        self.assertEqual(result.status, "passed")
        self.assertIn("prompt_tokens_legacy", result.metrics)
        self.assertIn("prompt_tokens_contract", result.metrics)
        self.assertIn("prompt_tokens_saved_pct", result.metrics)
        self.assertGreater(result.metrics["prompt_tokens_saved_pct"], 0)

    def test_s20_reports_worker_advisor_metrics(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run = run_beta(SCENARIOS.values(), only=["S20"], report_dir=Path(tmp), json_only=True)

        self.assertEqual(run.exit_code, 0)
        result = run.results[0]
        self.assertEqual(result.status, "passed")
        self.assertIn("recommended_workers", result.metrics)
        self.assertIn("speedup_pct_recommended", result.metrics)
        self.assertEqual(result.metrics["confidence"], "heuristic")

    def test_s23_locks_advisor_heuristic_fallback(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run = run_beta(SCENARIOS.values(), only=["S23"], report_dir=Path(tmp), json_only=True)

        self.assertEqual(run.exit_code, 0)
        result = run.results[0]
        self.assertEqual(result.status, "passed")
        self.assertEqual(result.metrics["recommended_workers"], 2.0)
        self.assertEqual(result.metrics["confidence"], "heuristic")

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

    def test_local_live_scenarios_skip_without_key(self) -> None:
        with tempfile.TemporaryDirectory() as tmp, patch.dict("os.environ", {"LMSTUDIO_API_KEY": "", "OPENAI_API_KEY": ""}, clear=False):
            with patch("vocr.beta.scenarios.read_env_file", return_value={}):
                run = run_beta(SCENARIOS.values(), only=["S21", "S22"], report_dir=Path(tmp), json_only=True)

        self.assertEqual(run.exit_code, 0)
        self.assertEqual([item.status for item in run.results], ["skipped", "skipped"])

    def test_local_live_chat_uses_existing_model_without_loading(self) -> None:
        class FakeResponse:
            def __init__(self, payload: bytes, status: int = 200) -> None:
                self.payload = payload
                self.status = status

            def __enter__(self):
                return self

            def __exit__(self, *_):
                return None

            def read(self) -> bytes:
                return self.payload

        def fake_urlopen(request, timeout=20):  # noqa: ANN001
            self.assertEqual(timeout, 20)
            self.assertEqual(request.headers["Authorization"], "Bearer local-key")
            url = request.full_url
            if url.endswith("/models"):
                return FakeResponse(b'{"data":[{"id":"gpt-loaded"}]}')
            if url.endswith("/chat/completions"):
                body = request.data.decode("utf-8")
                self.assertIn('"model": "gpt-loaded"', body)
                self.assertIn('"max_tokens": 8', body)
                return FakeResponse(b'{"choices":[{"message":{"content":"vocr-local-ok"}}]}')
            raise AssertionError(url)

        env = {
            "LMSTUDIO_API_KEY": "local-key",
            "OPENAI_BASE_URL": "http://localhost:1234/v1",
            "OPENAI_MODEL": "gpt-loaded",
        }
        with tempfile.TemporaryDirectory() as tmp, patch.dict("os.environ", env, clear=False):
            with patch("vocr.beta.scenarios.read_env_file", return_value={}):
                with patch("vocr.beta.scenarios.urllib.request.urlopen", side_effect=fake_urlopen):
                    run = run_beta(SCENARIOS.values(), only=["S21", "S22"], report_dir=Path(tmp), json_only=True)

        self.assertEqual(run.exit_code, 0)
        self.assertEqual([item.status for item in run.results], ["passed", "passed"])

    def test_local_live_chat_accepts_reasoning_only_response(self) -> None:
        class FakeResponse:
            status = 200

            def __init__(self, payload: bytes) -> None:
                self.payload = payload

            def __enter__(self):
                return self

            def __exit__(self, *_):
                return None

            def read(self) -> bytes:
                return self.payload

        def fake_urlopen(request, timeout=20):  # noqa: ANN001
            if request.full_url.endswith("/models"):
                return FakeResponse(b'{"data":[{"id":"gpt-oss-20b"}]}')
            return FakeResponse(
                b'{"choices":[{"message":{"content":"","reasoning":"thinking signal"},"finish_reason":"length"}]}'
            )

        env = {
            "LMSTUDIO_API_KEY": "local-key",
            "OPENAI_BASE_URL": "http://localhost:1234/v1",
            "OPENAI_MODEL": "gpt-oss-20b",
        }
        with tempfile.TemporaryDirectory() as tmp, patch.dict("os.environ", env, clear=False):
            with patch("vocr.beta.scenarios.read_env_file", return_value={}):
                with patch("vocr.beta.scenarios.urllib.request.urlopen", side_effect=fake_urlopen):
                    run = run_beta(SCENARIOS.values(), only=["S22"], report_dir=Path(tmp), json_only=True)

        self.assertEqual(run.exit_code, 0)
        self.assertEqual(run.results[0].status, "passed")
        self.assertGreater(run.results[0].metrics["reasoning_chars"], 0)

    def test_local_live_models_reports_unexpected_endpoint_payload(self) -> None:
        class FakeResponse:
            status = 200

            def __enter__(self):
                return self

            def __exit__(self, *_):
                return None

            def read(self) -> bytes:
                return b'{"error":"Unexpected endpoint or method. Returning 200 anyway"}'

        env = {
            "LMSTUDIO_API_KEY": "local-key",
            "OPENAI_BASE_URL": "http://localhost:1234/v1",
        }
        with tempfile.TemporaryDirectory() as tmp, patch.dict("os.environ", env, clear=False):
            with patch("vocr.beta.scenarios.read_env_file", return_value={}):
                with patch("vocr.beta.scenarios.urllib.request.urlopen", return_value=FakeResponse()):
                    run = run_beta(SCENARIOS.values(), only=["S21"], report_dir=Path(tmp), json_only=True)

        self.assertEqual(run.exit_code, 2)
        self.assertEqual(run.results[0].status, "failed")
        self.assertIn("Unexpected endpoint", run.results[0].steps[0].details)

    def test_local_live_prefers_repo_env_over_process_env(self) -> None:
        class FakeResponse:
            status = 200

            def __enter__(self):
                return self

            def __exit__(self, *_):
                return None

            def read(self) -> bytes:
                return b'{"data":[{"id":"repo-model"}]}'

        def fake_urlopen(request, timeout=20):  # noqa: ANN001
            self.assertEqual(request.headers["Authorization"], "Bearer repo-key")
            return FakeResponse()

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "repo"
            root.mkdir()
            (root / ".env").write_text("LMSTUDIO_API_KEY=repo-key\nOPENAI_BASE_URL=http://localhost:1234/v1\n", encoding="utf-8")
            with patch.dict("os.environ", {"LMSTUDIO_API_KEY": "wrong-process-key"}, clear=False):
                with patch("vocr.beta.scenarios.urllib.request.urlopen", side_effect=fake_urlopen):
                    run = run_beta(SCENARIOS.values(), only=["S21"], report_dir=Path(tmp) / "reports", json_only=True, repo_root=root)

        self.assertEqual(run.exit_code, 0)
        self.assertEqual(run.results[0].status, "passed")


if __name__ == "__main__":
    unittest.main()
