from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
import subprocess
import sys
import tempfile
import time
import unittest
import os
from pathlib import Path
from unittest.mock import patch

from typer.testing import CliRunner

from vocr.agents.runtime import diagnose_live_agent_error
from vocr.cli.app import (
    app,
    fetch_model_list,
    fetch_model_catalog,
    fetch_chat_completion,
    chat_completion_endpoint,
    model_list_endpoints,
    build_pr_review_comments,
    clean_archives,
    clean_artifacts,
    diff_delta,
    _local_api_key,
    latest_open_clarification,
    record_worker_telemetry,
    write_review_artifact,
)
from vocr.graph.graphify import GraphStore, RepoGraphBuilder
from vocr.config.env_file import provider_from_env, read_env_file, read_model_env, redact_env, update_env_file
from vocr.guardrails.scope_guard import ScopeGuard
from vocr.guardrails.secrets import _gitleaks_command, scan_diff_for_secrets
from vocr.memory.ledger import sanitize_payload
from vocr.memory.ledger import MemoryLedger
from vocr.memory.learning import LearningStore
from vocr.mcp.server import VocrMcpServer
from vocr.models import (
    AcceptanceCriterion,
    CodexRunResult,
    LedgerEventType,
    LearningEntry,
    LearningSnapshot,
    ReviewDecision,
    ReviewComment,
    ReviewResult,
    RunTelemetry,
    TaskStatus,
    TokenUsage,
    VocrTask,
)
from vocr.orchestration.golden import run_golden_eval
from vocr.orchestration.workflow import (
    create_vision,
    dispatch_task,
    normalize_check_command,
    organize_slice,
    revert_task,
    run_task_checks,
    validate_task_plan,
)

GOOD_REQUEST = (
    "Ziel: Baue eine Healthcheck-API im Backend. "
    "Arbeitsbereich: FastAPI-App; Tests. "
    "Akzeptanz: GET /health liefert 200; JSON status=ok. "
    "Verifikation: Syntax-Check. "
    "Nicht-Ziele: keine Auth; keine Deployment-Aenderungen. "
    "Ausfuehrung: mit go Worktree vorbereiten; Review vor Promote."
)


class WorkflowTests(unittest.TestCase):
    def test_local_openai_compatible_401_gets_lm_studio_auth_diagnosis(self) -> None:
        class LocalAuthError(Exception):
            status_code = 401

        diagnosis = diagnose_live_agent_error(
            LocalAuthError("401 Unauthorized"),
            provider="local-openai-compatible",
            base_url="http://localhost:1234/v1",
        )

        self.assertIn("LM Studio hat die Anfrage wegen API-Key/Auth abgelehnt", diagnosis)
        self.assertIn("Auth im LM-Studio-Server aktiv", diagnosis)
        self.assertIn("gueltigen LM-Studio-API-Token", diagnosis)
        self.assertIn("lokalen Fallback", diagnosis)

    def test_live_agent_high_confidence_cli_skips_local_401_path(self) -> None:
        class LocalAuthError(Exception):
            status_code = 401

        async def fail_with_401(_: str):
            raise LocalAuthError("401 Unauthorized")

        with tempfile.TemporaryDirectory() as tmp:
            env = {
                "VOCR_HOME": str(Path(tmp) / ".vocr"),
                "OPENAI_BASE_URL": "http://localhost:1234/v1",
                "OPENAI_API_KEY": "bad-local-token",
                "OPENAI_MODEL": "local-model",
            }
            with patch("vocr.cli.app.live_agents_available", return_value=True), patch(
                "vocr.cli.app.create_live_vision",
                fail_with_401,
            ):
                result = CliRunner().invoke(app, ["ask", GOOD_REQUEST, "--live-agent", "--plan-only"], env=env)

        self.assertEqual(result.exit_code, 0, result.output)
        self.assertIn("Deterministic confidence high", result.output)
        self.assertIn("Created slice", result.output)

    def test_live_agent_is_skipped_for_high_confidence_request(self) -> None:
        async def should_not_run(_: str):
            raise AssertionError("live agent should not run for high-confidence request")

        with tempfile.TemporaryDirectory() as tmp, patch(
            "vocr.cli.app.live_agents_available",
            return_value=True,
        ), patch("vocr.cli.app.create_live_vision", should_not_run):
            result = CliRunner().invoke(
                app,
                ["ask", GOOD_REQUEST, "--live-agent", "--plan-only"],
                env={"VOCR_HOME": str(Path(tmp) / ".vocr")},
            )

        self.assertEqual(result.exit_code, 0, result.output)
        self.assertIn("Deterministic confidence high", result.output)
        self.assertIn("Created slice", result.output)

    def test_vision_and_task_use_explicit_sections(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = GraphStore(Path(tmp) / ".vocr")
            store.save(RepoGraphBuilder(".").build())

            vision = create_vision(GOOD_REQUEST)
            task = organize_slice(vision, vocr_home=str(Path(tmp) / ".vocr"))[0]

        self.assertEqual(vision.goal, "Baue eine Healthcheck-API im Backend")
        self.assertEqual([item.text for item in vision.acceptance_criteria], ["GET /health liefert 200", "JSON status=ok"])
        self.assertEqual(task.scope, ["FastAPI-App", "Tests"])
        self.assertEqual(task.non_goals, ["keine Auth", "keine Deployment-Aenderungen"])
        self.assertEqual(task.tests, ["Syntax-Check"])
        self.assertIn("VOCR repo graph brief", task.context_pack or "")

    def test_sanitize_payload_redacts_secret_patterns(self) -> None:
        payload = {"message": "key sk-testsecret123456789", "api_key": "plain"}

        self.assertEqual(
            sanitize_payload(payload),
            {"message": "key [redacted]", "api_key": "[redacted]"},
        )

    def test_ledger_append_is_parallel_safe(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ledger = MemoryLedger(Path(tmp) / ".vocr")

            def append(index: int) -> str:
                return ledger.append(LedgerEventType.message, {"index": index}).id

            with ThreadPoolExecutor(max_workers=8) as pool:
                ids = list(pool.map(append, range(80)))

            events = list(ledger.events())

        self.assertEqual(len(events), 80)
        self.assertEqual(len(set(ids)), 80)
        self.assertEqual(sorted(event.payload["index"] for event in events), list(range(80)))

    def test_scope_guard_blocks_files_outside_declared_scope(self) -> None:
        task = VocrTask(
            slice_id="slice-test",
            title="Docs only",
            summary="Update docs",
            scope=["docs"],
            acceptance_criteria=[AcceptanceCriterion(text="Docs updated")],
            tests=["Syntax-Check"],
        )

        guard = ScopeGuard()

        self.assertEqual(guard.validate_changed_files(task, ["docs/guide.md"]), [])
        self.assertTrue(guard.validate_changed_files(task, ["src/vocr/main.py"]))

    def test_worker_agents_file_points_to_single_scope_policy(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            task = VocrTask(
                slice_id="slice-test",
                title="Docs only",
                summary="Update docs",
                scope=["docs"],
                acceptance_criteria=[AcceptanceCriterion(text="Docs updated")],
                tests=["Syntax-Check"],
                worktree_path=Path(tmp),
            )
            path = ScopeGuard().write_worker_agents_file(task)
            text = path.read_text(encoding="utf-8")

        self.assertIn(".vocr/VOCR_TASK.md", text)
        self.assertIn(".vocr/scope.json", text)
        self.assertNotIn("Allowed globs:", text)
        self.assertNotIn("Non-goals:", text)

    def test_retry_prompt_uses_incremental_diff_delta(self) -> None:
        previous = "diff --git a/a.py b/a.py\n+old"
        current = "diff --git a/a.py b/a.py\n+old\n+new"

        self.assertEqual(diff_delta(previous, current), "+new")

    def test_compile_check_targets_changed_python_files_only(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            subprocess.run(["git", "init"], cwd=root, check=True, capture_output=True)
            subprocess.run(["git", "config", "user.email", "vocr@example.invalid"], cwd=root, check=True)
            subprocess.run(["git", "config", "user.name", "VOCR Test"], cwd=root, check=True)
            (root / "src").mkdir()
            (root / "src" / "a.py").write_text("print('a')\n", encoding="utf-8")
            subprocess.run(["git", "add", "."], cwd=root, check=True)
            subprocess.run(["git", "commit", "-m", "initial"], cwd=root, check=True, capture_output=True)
            (root / "src" / "a.py").write_text("print('changed')\n", encoding="utf-8")
            task = VocrTask(
                slice_id="slice-test",
                title="Compile",
                summary="Compile",
                scope=["src"],
                acceptance_criteria=[AcceptanceCriterion(text="Compiles")],
                tests=["Syntax-Check"],
                worktree_path=root,
            )

            command = normalize_check_command("Syntax-Check", task=task)

        self.assertEqual(command[:3], [sys.executable, "-m", "py_compile"])
        self.assertEqual(command[3:], ["src/a.py"])

    def test_graph_context_uses_bm25_and_import_neighbors(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            package = root / "src" / "sample"
            package.mkdir(parents=True)
            (package / "__init__.py").write_text("", encoding="utf-8")
            (package / "api.py").write_text(
                "from sample.service import health_status\n\ndef health():\n    return health_status()\n",
                encoding="utf-8",
            )
            (package / "service.py").write_text(
                "def health_status():\n    return {'status': 'ok'}\n",
                encoding="utf-8",
            )

            graph = RepoGraphBuilder(root).build()
            brief = graph.context_brief(query="health api", limit=2)

        self.assertIn("src/sample/api.py (seed)", brief)
        self.assertIn("src/sample/service.py", brief)

    def test_graph_context_uses_budget_and_downweights_docs(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "docs").mkdir()
            (root / "docs" / "feature.md").write_text("# feature api ranking\n", encoding="utf-8")
            (root / "src").mkdir()
            (root / "src" / "feature.py").write_text("def feature_api():\n    return True\n", encoding="utf-8")

            graph = RepoGraphBuilder(root).build()
            brief = graph.context_brief(query="feature api", limit=5, token_budget=50)

        self.assertIn("Token budget: 50", brief)
        self.assertLess(brief.index("src/feature.py"), brief.index("docs/feature.md"))
        self.assertTrue(all(node.search_tokens for node in graph.nodes))

    def test_secret_scanner_blocks_added_secret_values(self) -> None:
        diff = "\n".join(
            [
                "diff --git a/.env b/.env",
                "+++ b/.env",
                "@@ -0,0 +1 @@",
                "+OPENAI_API_KEY=sk-testsecretvalue1234567890",
            ]
        )

        result = scan_diff_for_secrets(diff)

        self.assertTrue(result.blocked)
        self.assertIn("vocr-minimal", result.scanners)
        self.assertTrue(any(finding.rule_id == "keyword_assignment" for finding in result.findings))

    def test_gitleaks_command_uses_repo_config_and_baseline(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / ".gitleaks.toml").write_text("title = 'test'\n", encoding="utf-8")
            (root / ".gitleaks-baseline.json").write_text("[]\n", encoding="utf-8")

            command = _gitleaks_command(root)

        self.assertIn("--config", command)
        self.assertIn("--baseline-path", command)

    def test_organize_slice_creates_sequential_task_dependencies(self) -> None:
        request = (
            GOOD_REQUEST
            + " Tasks: Graphify Ranking; Scope Guard; README Update."
        )
        with tempfile.TemporaryDirectory() as tmp:
            store = GraphStore(Path(tmp) / ".vocr")
            store.save(RepoGraphBuilder(".").build())
            vision = create_vision(request)
            tasks = organize_slice(vision, vocr_home=str(Path(tmp) / ".vocr"))

        self.assertEqual([task.title for task in tasks], ["Graphify Ranking", "Scope Guard", "README Update"])
        self.assertEqual(tasks[0].dependencies, [])
        self.assertEqual(tasks[1].dependencies, [tasks[0].id])
        self.assertEqual(tasks[2].dependencies, [tasks[1].id])

    def test_organize_slice_supports_parallel_task_groups(self) -> None:
        request = (
            GOOD_REQUEST
            + " Tasks: Backend API || Backend Tests; README Update."
        )
        with tempfile.TemporaryDirectory() as tmp:
            store = GraphStore(Path(tmp) / ".vocr")
            store.save(RepoGraphBuilder(".").build())
            vision = create_vision(request)
            tasks = organize_slice(vision, vocr_home=str(Path(tmp) / ".vocr"))

        self.assertEqual([task.title for task in tasks], ["Backend API", "Backend Tests", "README Update"])
        self.assertEqual(tasks[0].dependencies, [])
        self.assertEqual(tasks[1].dependencies, [])
        self.assertEqual(set(tasks[2].dependencies), {tasks[0].id, tasks[1].id})

    def test_plan_invariants_block_dependency_cycles_before_dispatch(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / ".vocr"
            ledger = MemoryLedger(root)
            first = VocrTask(
                id="task-a",
                slice_id="slice-plan",
                title="A",
                summary="A",
                scope=["docs"],
                acceptance_criteria=[AcceptanceCriterion(text="A done")],
                tests=["Syntax-Check"],
                dependencies=["task-b"],
            )
            second = VocrTask(
                id="task-b",
                slice_id="slice-plan",
                title="B",
                summary="B",
                scope=["docs"],
                acceptance_criteria=[AcceptanceCriterion(text="B done")],
                tests=["Syntax-Check"],
                dependencies=["task-a"],
            )
            ledger.append(LedgerEventType.task_created, first)
            ledger.append(LedgerEventType.task_created, second)

            class NoCreateManager:
                def create_for_task(self, task_id: str):
                    raise AssertionError("worktree must not be created for invalid plan")

            issues = validate_task_plan(ledger.tasks(), target_task_id=first.id)
            with self.assertRaisesRegex(ValueError, "dependency cycle"):
                dispatch_task(ledger, NoCreateManager(), first.id)  # type: ignore[arg-type]

        self.assertTrue(any("dependency cycle" in issue for issue in issues))

    def test_plan_invariants_require_scope_and_coverage(self) -> None:
        task = VocrTask(
            id="task-invalid-plan",
            slice_id="slice-plan",
            title="Invalid",
            summary="Invalid",
            scope=[],
            acceptance_criteria=[AcceptanceCriterion(text="Visible result")],
            tests=[],
        )

        issues = validate_task_plan([task])

        self.assertTrue(any("Task has no scope" in issue for issue in issues))
        self.assertTrue(any("no executable check or verification mapping" in issue for issue in issues))

    def test_acceptance_criterion_can_run_executable_check(self) -> None:
        task = VocrTask(
            id="task-check",
            slice_id="slice-check",
            title="Criterion check",
            summary="Criterion check",
            scope=["src"],
            acceptance_criteria=[
                AcceptanceCriterion(text="Source compiles", check_command="Syntax-Check"),
            ],
            tests=[],
        )

        issues = validate_task_plan([task])
        results = run_task_checks(task)

        self.assertEqual(issues, [])
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].status, "passed")

    def test_revert_task_uses_recorded_commit_and_logs_event(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ledger = MemoryLedger(Path(tmp) / ".vocr")
            task = VocrTask(
                id="task-revert",
                slice_id="slice-revert",
                title="Revert",
                summary="Revert",
                scope=["docs"],
                acceptance_criteria=[AcceptanceCriterion(text="Docs updated")],
                tests=["Syntax-Check"],
            )
            ledger.append(LedgerEventType.task_created, task)
            ledger.append(LedgerEventType.task_committed, {"task_id": task.id, "commit_sha": "abc123"})

            class FakeManager:
                def __init__(self) -> None:
                    self.reverted: list[str] = []

                def revert_commit(self, commit_sha: str) -> str:
                    self.reverted.append(commit_sha)
                    return "def456"

            manager = FakeManager()

            revert_sha = revert_task(ledger, manager, task.id, reason="test revert")  # type: ignore[arg-type]
            current = ledger.get_task(task.id)

        self.assertEqual(manager.reverted, ["abc123"])
        self.assertEqual(revert_sha, "def456")
        self.assertIsNotNone(current)
        self.assertEqual(current.status, TaskStatus.needs_changes)
        self.assertIsNone(ledger.latest_task_commit(task.id))

    def test_mcp_server_lists_vocr_tools(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            server = VocrMcpServer(Path(tmp) / ".vocr")
            response = server.handle({"jsonrpc": "2.0", "id": 1, "method": "tools/list"})

        tool_names = {tool["name"] for tool in response["result"]["tools"]}
        self.assertIn("vocr_status", tool_names)
        self.assertIn("vocr_context", tool_names)
        self.assertIn("vocr_plan", tool_names)
        self.assertIn("vocr_review", tool_names)
        self.assertIn("vocr_promote_preview", tool_names)
        self.assertIn("vocr_promote", tool_names)

    def test_mcp_promote_requires_confirm_and_uses_gate(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / ".vocr"
            ledger = MemoryLedger(root)
            task = VocrTask(
                id="task-promote",
                slice_id="slice-promote",
                title="Promote me",
                summary="Ready to promote",
                scope=["docs"],
                acceptance_criteria=[AcceptanceCriterion(text="Docs updated")],
                tests=["Syntax-Check"],
                status=TaskStatus.accepted,
                branch_name="vocr/task-promote",
            )
            ledger.append(LedgerEventType.task_created, task)
            server = VocrMcpServer(root)

            blocked = server.handle(
                {
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": "tools/call",
                    "params": {"name": "vocr_promote", "arguments": {"task_id": task.id, "confirm": False}},
                }
            )
            with patch("vocr.mcp.server.promote_task") as promote:
                promoted = server.handle(
                    {
                        "jsonrpc": "2.0",
                        "id": 2,
                        "method": "tools/call",
                        "params": {"name": "vocr_promote", "arguments": {"task_id": task.id, "confirm": True}},
                    }
                )

        self.assertIn("Promotion not started", blocked["result"]["content"][0]["text"])
        promote.assert_called_once()
        self.assertIn("Task promoted", promoted["result"]["content"][0]["text"])

    def test_golden_eval_checks_stub_worker_and_promote_gate(self) -> None:
        result = run_golden_eval()

        self.assertTrue(result.passed)
        self.assertEqual(
            [step.name for step in result.steps],
            [
                "dispatch",
                "actual-token-metering",
                "promote-before-review-blocked",
                "accepted-review",
                "promote-after-review-allowed",
            ],
        )

    def test_env_file_helpers_configure_local_model_without_printing_secret(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            env_path = Path(tmp) / ".env"
            update_env_file(
                {
                    "OPENAI_BASE_URL": "http://localhost:1234/v1",
                    "OPENAI_MODEL": "local-model",
                    "OPENAI_API_KEY": "lm-studio",
                },
                env_path,
            )
            values = read_env_file(env_path)

        self.assertEqual(provider_from_env(values), "local-openai-compatible")
        self.assertEqual(values["OPENAI_MODEL"], "local-model")
        self.assertEqual(redact_env(values)["OPENAI_API_KEY"], "[set]")

    def test_model_env_includes_process_values(self) -> None:
        with tempfile.TemporaryDirectory() as tmp, patch.dict(
            os.environ,
            {"OPENAI_API_KEY": "process-token", "OPENAI_MODEL": "process-model"},
            clear=False,
        ):
            env_path = Path(tmp) / ".env"
            update_env_file({"OPENAI_MODEL": "file-model"}, env_path)

            values = read_model_env(env_path)

        self.assertEqual(values["OPENAI_API_KEY"], "process-token")
        self.assertEqual(values["OPENAI_MODEL"], "process-model")

    def test_model_status_shows_process_key_redacted(self) -> None:
        result = CliRunner().invoke(app, ["model", "status"], env={"OPENAI_API_KEY": "process-token"})

        self.assertEqual(result.exit_code, 0, result.output)
        self.assertIn("openai", result.output)
        self.assertIn("[set]", result.output)
        self.assertNotIn("process-token", result.output)

    def test_worker_telemetry_uses_actual_usage_when_worker_reports_it(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / ".vocr"
            ledger = MemoryLedger(root)
            task = VocrTask(
                id="task-usage",
                slice_id="slice-usage",
                title="Usage",
                summary="Usage",
                scope=["docs"],
                acceptance_criteria=[AcceptanceCriterion(text="Usage recorded")],
                tests=[],
            )
            ledger.append(LedgerEventType.task_created, task)
            result = CodexRunResult(
                task_id=task.id,
                command=["stub"],
                exit_code=0,
                stdout='{"usage":{"prompt_tokens":11,"completion_tokens":3,"total_tokens":14}}',
            )

            record_worker_telemetry(ledger, task.id, result, "prompt text")
            telemetry = ledger.telemetry()[0]

        self.assertEqual(telemetry.token_usage.source, "actual")
        self.assertEqual(telemetry.token_usage.prompt_tokens, 11)
        self.assertEqual(telemetry.token_usage.completion_tokens, 3)
        self.assertEqual(telemetry.token_usage.total_tokens, 14)

    def test_usage_command_shows_actual_token_source(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / ".vocr"
            ledger = MemoryLedger(root)
            ledger.append(
                LedgerEventType.telemetry_recorded,
                RunTelemetry(
                    provider="stub-worker",
                    model="none",
                    slice_id="slice-usage",
                    task_id="task-usage",
                    agent="stub-worker",
                    token_usage=TokenUsage(prompt_tokens=5, completion_tokens=2, total_tokens=7, source="actual"),
                ),
            )

            result = CliRunner().invoke(app, ["usage"], env={"VOCR_HOME": str(root)})

        self.assertEqual(result.exit_code, 0, result.output)
        self.assertIn("actual", result.output)
        self.assertIn("Total tokens", result.output)
        self.assertIn("7", result.output)

    def test_model_check_accepts_one_shot_api_key_without_printing_it(self) -> None:
        with patch(
            "vocr.cli.app.fetch_model_catalog",
            return_value=({"data": [{"id": "local-model"}]}, "http://localhost:1234/api/v1/models"),
        ) as fetch:
            result = CliRunner().invoke(app, ["model", "check", "--api-key", "local-token"])

        self.assertEqual(result.exit_code, 0, result.output)
        fetch.assert_called_once_with("http://localhost:1234/v1", api_key="local-token")
        self.assertIn("Models visible: 1", result.output)
        self.assertNotIn("local-token", result.output)

    def test_model_check_uses_chat_completion_when_model_is_given(self) -> None:
        with patch("vocr.cli.app.fetch_chat_completion", return_value={"choices": []}) as chat:
            result = CliRunner().invoke(
                app,
                ["model", "check", "--model", "local-model", "--api-key", "local-token"],
            )

        self.assertEqual(result.exit_code, 0, result.output)
        chat.assert_called_once_with("http://localhost:1234/v1", model="local-model", api_key="local-token")
        self.assertIn("Local chat endpoint reachable", result.output)
        self.assertIn("local-model", result.output)
        self.assertNotIn("local-token", result.output)

    def test_fetch_model_list_sends_bearer_token_when_configured(self) -> None:
        class FakeResponse:
            def __enter__(self):
                return self

            def __exit__(self, *_):
                return False

            def read(self) -> bytes:
                return b'{"data":[{"id":"local-model"}]}'

        captured = {}

        def fake_urlopen(request, timeout):
            captured["authorization"] = request.get_header("Authorization")
            captured["timeout"] = timeout
            return FakeResponse()

        with patch("urllib.request.urlopen", fake_urlopen):
            payload = fetch_model_list("http://localhost:1234/v1/models", api_key="lm-token")

        self.assertEqual(payload["data"][0]["id"], "local-model")
        self.assertEqual(captured["authorization"], "Bearer lm-token")
        self.assertEqual(captured["timeout"], 5)

    def test_fetch_chat_completion_sends_bearer_token_to_chat_endpoint(self) -> None:
        class FakeResponse:
            def __enter__(self):
                return self

            def __exit__(self, *_):
                return False

            def read(self) -> bytes:
                return b'{"choices":[{"message":{"content":"ok"}}]}'

        captured = {}

        def fake_urlopen(request, timeout):
            captured["url"] = request.full_url
            captured["authorization"] = request.get_header("Authorization")
            captured["timeout"] = timeout
            return FakeResponse()

        with patch("urllib.request.urlopen", fake_urlopen):
            payload = fetch_chat_completion("http://localhost:1234/v1", model="local-model", api_key="lm-token")

        self.assertEqual(payload["choices"][0]["message"]["content"], "ok")
        self.assertEqual(captured["url"], "http://localhost:1234/v1/chat/completions")
        self.assertEqual(captured["authorization"], "Bearer lm-token")
        self.assertEqual(captured["timeout"], 20)

    def test_chat_completion_endpoint_normalizes_root_and_v1_base_urls(self) -> None:
        self.assertEqual(chat_completion_endpoint("http://localhost:1234"), "http://localhost:1234/v1/chat/completions")
        self.assertEqual(
            chat_completion_endpoint("http://localhost:1234/v1"),
            "http://localhost:1234/v1/chat/completions",
        )

    def test_model_catalog_falls_back_to_lmstudio_native_models_endpoint(self) -> None:
        class FakeResponse:
            def __init__(self, body: bytes):
                self.body = body

            def __enter__(self):
                return self

            def __exit__(self, *_):
                return False

            def read(self) -> bytes:
                return self.body

        seen = []

        def fake_urlopen(request, timeout):
            seen.append(request.full_url)
            if request.full_url == "http://localhost:1234/v1/models":
                return FakeResponse(b"Unexpected endpoint or method. Returning 200 anyway")
            return FakeResponse(b'{"data":[{"id":"lmstudio-model"}]}')

        with patch("urllib.request.urlopen", fake_urlopen):
            payload, endpoint = fetch_model_catalog("http://localhost:1234/v1")

        self.assertEqual(payload["data"][0]["id"], "lmstudio-model")
        self.assertEqual(endpoint, "http://localhost:1234/api/v1/models")
        self.assertEqual(
            seen,
            ["http://localhost:1234/v1/models", "http://localhost:1234/api/v1/models"],
        )

    def test_model_list_endpoints_include_openai_and_lmstudio_native_paths(self) -> None:
        self.assertEqual(
            model_list_endpoints("http://localhost:1234/v1"),
            [
                "http://localhost:1234/v1/models",
                "http://localhost:1234/api/v1/models",
                "http://localhost:1234/api/v0/models",
            ],
        )

    def test_local_model_check_does_not_send_cloud_key_to_default_localhost(self) -> None:
        self.assertIsNone(_local_api_key({"OPENAI_API_KEY": "cloud-key"}, None))
        self.assertEqual(
            _local_api_key({"OPENAI_BASE_URL": "http://localhost:1234/v1", "OPENAI_API_KEY": "lm-token"}, None),
            "lm-token",
        )
        self.assertEqual(_local_api_key({"OPENAI_API_KEY": "lm-token"}, "http://localhost:1234/v1"), "lm-token")

    def test_learning_store_aggregates_reviews_without_raw_diff(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / ".vocr"
            ledger = MemoryLedger(root)
            created_at = datetime(2026, 7, 10, 12, 0, tzinfo=timezone.utc)
            task = VocrTask(
                id="task-learn",
                slice_id="slice-learn",
                title="Docs update",
                summary="Update docs",
                scope=["docs"],
                acceptance_criteria=[AcceptanceCriterion(text="Docs updated")],
                tests=["Syntax-Check"],
                created_at=created_at,
            )
            ledger.append(LedgerEventType.task_created, task)
            ledger.append(
                LedgerEventType.telemetry_recorded,
                RunTelemetry(
                    provider="codex-cli",
                    task_id=task.id,
                    slice_id=task.slice_id,
                    agent="codex-worker",
                    token_usage=TokenUsage(total_tokens=42),
                ),
            )
            ledger.append(
                LedgerEventType.telemetry_recorded,
                RunTelemetry(
                    provider="codex-cli",
                    task_id=task.id,
                    slice_id=task.slice_id,
                    agent="codex-worker",
                    token_usage=TokenUsage(total_tokens=8),
                ),
            )
            ledger.append(
                LedgerEventType.clarification_requested,
                {
                    "id": "clarify-learning",
                    "request": "needs detail",
                    "report": {
                        "ready": False,
                        "confidence": 0.5,
                        "questions": [
                            {
                                "topic": "scope",
                                "question": "Which files are in scope?",
                                "why_needed": "Scope controls worker writes.",
                            }
                        ],
                        "missing_topics": ["verification"],
                        "notes": [],
                    },
                    "answers": [],
                },
            )
            ledger.append(
                LedgerEventType.clarification_answered,
                {"session_id": "clarify-learning", "answer": "details"},
            )
            ledger.append(
                LedgerEventType.review_recorded,
                ReviewResult(
                    task_id=task.id,
                    decision=ReviewDecision.accepted,
                    summary="Docs fix accepted",
                    tests_reviewed=["Syntax-Check"],
                    diff_files=["README.md"],
                    created_at=created_at + timedelta(seconds=90),
                ),
            )
            learning = LearningStore(root)
            snapshot = learning.refresh(ledger)

        self.assertIn("scope:docs", snapshot.scopes)
        self.assertEqual(snapshot.scopes["scope:docs"].files["README.md"], 1)
        self.assertEqual(snapshot.scopes["scope:docs"].estimated_tokens, 50)
        self.assertEqual(snapshot.scopes["scope:docs"].retry_count, 1)
        self.assertEqual(snapshot.scopes["scope:docs"].review_seconds_total, 90)
        self.assertEqual(snapshot.scopes["scope:docs"].accepted_review_seconds_total, 90)
        self.assertEqual(snapshot.clarifications_requested, 1)
        self.assertEqual(snapshot.clarifications_answered, 1)
        self.assertEqual(snapshot.clarification_answer_rate_percent, 100)
        self.assertEqual(snapshot.clarification_topics, {"scope": 1, "verification": 1})

    def test_ledger_compact_archives_old_events(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ledger = MemoryLedger(Path(tmp) / ".vocr")
            for index in range(30):
                ledger.append(LedgerEventType.message, {"message": f"event {index}"})
            result = ledger.compact(keep_last=20)

            remaining = list(ledger.events())

        self.assertEqual(result.archived_events, 10)
        self.assertEqual(len(remaining), 20)
        self.assertIsNotNone(result.archive_path)

    def test_clean_archives_removes_only_old_jsonl_segments(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            old_home = os.environ.get("VOCR_HOME")
            os.environ["VOCR_HOME"] = str(Path(tmp) / ".vocr")
            try:
                archive_root = Path(tmp) / ".vocr" / "archive"
                archive_root.mkdir(parents=True)
                old_archive = archive_root / "old.jsonl"
                new_archive = archive_root / "new.jsonl"
                ignored = archive_root / "notes.txt"
                old_archive.write_text("old\n", encoding="utf-8")
                new_archive.write_text("new\n", encoding="utf-8")
                ignored.write_text("keep\n", encoding="utf-8")
                old_time = time.time() - 10 * 24 * 60 * 60
                os.utime(old_archive, (old_time, old_time))

                removed = clean_archives(older_than_days=5)
                old_exists = old_archive.exists()
                new_exists = new_archive.exists()
                ignored_exists = ignored.exists()
            finally:
                if old_home is None:
                    os.environ.pop("VOCR_HOME", None)
                else:
                    os.environ["VOCR_HOME"] = old_home

        self.assertEqual(removed, 1)
        self.assertFalse(old_exists)
        self.assertTrue(new_exists)
        self.assertTrue(ignored_exists)

    def test_learning_boosts_graph_context_ranking(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            vocr_home = root / ".vocr"
            (root / "README.md").write_text("# Setup\n", encoding="utf-8")
            src = root / "src"
            src.mkdir()
            (src / "main.py").write_text("def run():\n    return True\n", encoding="utf-8")
            learning = LearningStore(vocr_home)
            learning.save(
                LearningSnapshot(
                    scopes={
                        "scope:docs": LearningEntry(
                            key="scope:docs",
                            count=3,
                            files={"README.md": 3},
                            decisions={"needs_changes": 2},
                        )
                    }
                )
            )
            graph_store = GraphStore(vocr_home)
            graph_store.refresh(root)

            context = graph_store.context_pack(query="docs", limit=1)

        self.assertIn("README.md", context)

    def test_latest_open_clarification_skips_answered_sessions(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ledger = MemoryLedger(Path(tmp) / ".vocr")
            session_one = {
                "id": "clarify-one",
                "request": "one",
                "report": {"ready": False, "confidence": 0.5, "questions": [], "missing_topics": [], "notes": []},
                "answers": [],
            }
            session_two = {
                "id": "clarify-two",
                "request": "two",
                "report": {"ready": False, "confidence": 0.5, "questions": [], "missing_topics": [], "notes": []},
                "answers": [],
            }
            ledger.append(LedgerEventType.clarification_requested, session_one)
            ledger.append(LedgerEventType.clarification_answered, {"session_id": "clarify-one", "answer": "done"})
            ledger.append(LedgerEventType.clarification_requested, session_two)

            latest = latest_open_clarification(ledger)

        self.assertIsNotNone(latest)
        self.assertEqual(latest.id, "clarify-two")

    def test_review_artifact_and_clean_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            old_home = os.environ.get("VOCR_HOME")
            os.environ["VOCR_HOME"] = str(Path(tmp) / ".vocr")
            try:
                review = ReviewResult(
                    task_id="task-artifact",
                    decision=ReviewDecision.needs_changes,
                    summary="Needs changes",
                )
                path = write_review_artifact(review)

                removed = clean_artifacts(older_than_days=1)
                exists = path.exists()
            finally:
                if old_home is None:
                    os.environ.pop("VOCR_HOME", None)
                else:
                    os.environ["VOCR_HOME"] = old_home

        self.assertTrue(exists)
        self.assertEqual(removed, 0)

    def test_pr_review_payload_uses_only_safe_inline_comments(self) -> None:
        review = ReviewResult(
            task_id="task-review",
            decision=ReviewDecision.needs_changes,
            summary="Needs changes",
            comments=[
                ReviewComment(source="vocr-diff-review", path="src/app.py", line=12, body="Check this line."),
                ReviewComment(source="vocr-review", path="README.md", body="File-level note."),
            ],
        )

        comments = build_pr_review_comments(review)

        self.assertEqual(
            comments,
            [
                {
                    "path": "src/app.py",
                    "line": 12,
                    "side": "RIGHT",
                    "body": "vocr-diff-review: Check this line.",
                }
            ],
        )


if __name__ == "__main__":
    unittest.main()
