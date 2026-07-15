from __future__ import annotations

import tempfile
import unittest
import os
import subprocess
from pathlib import Path
from unittest.mock import patch

from typer.testing import CliRunner

from vocr.agents.runtime import diagnose_live_agent_error
from vocr.cli.app import app, clean_artifacts, latest_open_clarification, write_review_artifact
from vocr.codex.mcp_client import CodexMcpClient
from vocr.graph.graphify import GraphStore, RepoGraphBuilder
from vocr.config.env_file import provider_from_env, read_env_file, redact_env, update_env_file
from vocr.guardrails.scope_guard import ScopeGuard
from vocr.guardrails.secrets import _gitleaks_command, scan_diff_for_secrets
from vocr.memory.ledger import sanitize_payload
from vocr.memory.ledger import MemoryLedger
from vocr.memory.learning import LearningStore
from vocr.mcp.server import VocrMcpServer
from vocr.models import (
    AcceptanceCriterion,
    CodexRunResult,
    GraphNode,
    RepoGraph,
    LedgerEventType,
    LearningEntry,
    LearningSnapshot,
    ReviewDecision,
    ReviewResult,
    RunTelemetry,
    TaskStatus,
    TaskContract,
    TokenUsage,
    VocrTask,
)
from vocr.orchestration.workflow import create_vision, distill_failure_output, organize_slice, render_task_template, review_task

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

    def test_live_agent_local_401_cli_prints_auth_diagnosis_and_falls_back(self) -> None:
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
        self.assertIn("LM Studio hat die Anfrage wegen API-Key/Auth abgelehnt", result.output)
        self.assertIn("lokaler Fallback aktiv", result.output)
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

    def test_graph_builder_records_top_level_symbol_spans_and_brief_markers(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            module = root / "sample.py"
            module.write_text(
                "\n".join(
                    [
                        "import os",
                        "",
                        "def alpha():",
                        "    return os.name",
                        "",
                        "class Beta:",
                        "    def method(self):",
                        "        return True",
                        "",
                        "async def gamma():",
                        "    return 1",
                    ]
                )
                + "\n",
                encoding="utf-8",
            )

            graph = RepoGraphBuilder(root).build()
            node = graph.nodes[0]
            brief = graph.context_brief(query="alpha beta gamma", limit=1)

        self.assertEqual([span.name for span in node.symbol_spans], ["def alpha", "class Beta", "def gamma"])
        self.assertEqual((node.symbol_spans[0].start, node.symbol_spans[0].end), (3, 4))
        self.assertEqual((node.symbol_spans[1].start, node.symbol_spans[1].end), (6, 8))
        self.assertIn("def alpha@L3-4", brief)
        self.assertIn("class Beta@L6-8", brief)

    def test_old_graph_json_without_symbol_spans_still_loads(self) -> None:
        graph = RepoGraph.model_validate(
            {
                "root": "C:/tmp/repo",
                "nodes": [
                    {
                        "path": "sample.py",
                        "kind": "py",
                        "size_bytes": 10,
                        "line_count": 1,
                        "content_hash": "hash",
                        "summary": "Python module: def alpha",
                        "imports": [],
                        "symbols": ["def alpha"],
                    }
                ],
                "edges": [],
            }
        )

        self.assertEqual(graph.nodes[0].symbol_spans, [])
        self.assertIn("def alpha", graph.context_brief())

    def test_context_symbol_prints_exact_span_lines(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            vocr_home = root / ".vocr"
            module = root / "sample.py"
            module.write_text(
                "\n".join(
                    [
                        "def alpha():",
                        "    return 1",
                        "",
                        "def beta():",
                        "    value = 2",
                        "    return value",
                    ]
                )
                + "\n",
                encoding="utf-8",
            )
            GraphStore(vocr_home).save(RepoGraphBuilder(root).build())

            result = CliRunner().invoke(
                app,
                ["context", "--symbol", "sample.py:beta"],
                env={"VOCR_HOME": str(vocr_home)},
            )

        self.assertEqual(result.exit_code, 0, result.output)
        self.assertEqual(result.output.strip(), "def beta():\n    value = 2\n    return value")

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

    def test_organize_slice_builds_per_task_context_queries_and_packs(self) -> None:
        request = (
            "Ziel: Improve project surfaces. "
            "Arbeitsbereich: src; docs. "
            "Akzeptanz: Changes are focused. "
            "Verifikation: Syntax-Check. "
            "Tasks: Payment API; Install Docs."
        )
        with tempfile.TemporaryDirectory() as tmp:
            vocr_home = Path(tmp) / ".vocr"
            GraphStore(vocr_home).save(
                RepoGraph(
                    root=tmp,
                    nodes=[
                        GraphNode(
                            path="src/payments/api.py",
                            kind="py",
                            size_bytes=10,
                            line_count=1,
                            content_hash="api",
                            summary="payment api charge refund endpoint",
                            symbols=["def charge"],
                        ),
                        GraphNode(
                            path="docs/install.md",
                            kind="md",
                            size_bytes=10,
                            line_count=1,
                            content_hash="docs",
                            summary="install docs setup guide",
                        ),
                    ],
                )
            )

            tasks = organize_slice(create_vision(request), vocr_home=str(vocr_home))

        self.assertEqual(len(tasks), 2)
        self.assertNotEqual(tasks[0].context_query, tasks[1].context_query)
        self.assertNotEqual(tasks[0].context_pack, tasks[1].context_pack)
        self.assertIn("payment", tasks[0].context_query or "")
        self.assertIn("install", tasks[1].context_query or "")
        self.assertIn("src/payments/api.py", tasks[0].context_pack or "")
        self.assertIn("docs/install.md", tasks[1].context_pack or "")

    def test_organize_slice_single_task_keeps_goal_context_available(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            vocr_home = Path(tmp) / ".vocr"
            GraphStore(vocr_home).save(
                RepoGraph(
                    root=tmp,
                    nodes=[
                        GraphNode(
                            path="src/slice.py",
                            kind="py",
                            size_bytes=10,
                            line_count=1,
                            content_hash="health",
                            summary="implement first scoped slice healthcheck endpoint",
                            symbols=["def implement_slice"],
                        )
                    ],
                )
            )

            tasks = organize_slice(create_vision(GOOD_REQUEST), vocr_home=str(vocr_home))

        self.assertEqual(len(tasks), 1)
        self.assertIn("implement first scoped slice", tasks[0].context_query or "")
        self.assertIn("src/slice.py", tasks[0].context_pack or "")

    def test_codex_manifest_writes_contract_and_separate_context_pack(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            worktree = Path(tmp)
            task = VocrTask(
                id="task-contract",
                slice_id="slice-contract",
                title="Update handoff",
                summary="Write the contract handoff files.",
                scope=["src/vocr/codex/mcp_client.py"],
                non_goals=["Do not change promotion."],
                acceptance_criteria=[AcceptanceCriterion(text="Contract JSON exists")],
                tests=["python -m compileall src"],
                dependencies=["task-parent"],
                context_pack="UNTRUSTED_MARKER: repo context only",
                worktree_path=worktree,
            )

            manifest_path = CodexMcpClient(command="codex").write_manifest(task)
            contract_path = worktree / ".vocr" / "VOCR_TASK.json"
            context_path = worktree / ".vocr" / "CONTEXT_PACK.txt"
            contract_text = contract_path.read_text(encoding="utf-8")
            context_text = context_path.read_text(encoding="utf-8")
            contract = TaskContract.model_validate_json(contract_text)

        self.assertEqual(manifest_path.name, "VOCR_TASK.md")
        self.assertEqual(contract.task_id, task.id)
        self.assertEqual(contract.dependencies, ["task-parent"])
        self.assertEqual(context_text, "UNTRUSTED_MARKER: repo context only")
        self.assertNotIn("UNTRUSTED_MARKER", contract_text)

    def test_contract_prompt_mode_is_byte_identical_and_excludes_task_content(self) -> None:
        task_one = VocrTask(
            id="task-one",
            slice_id="slice-contract",
            title="First volatile title",
            summary="First summary",
            scope=["src/one.py"],
            acceptance_criteria=[AcceptanceCriterion(text="First unique criterion")],
            tests=["python -m compileall src"],
        )
        task_two = VocrTask(
            id="task-two",
            slice_id="slice-contract",
            title="Second volatile title",
            summary="Second summary",
            scope=["src/two.py"],
            acceptance_criteria=[AcceptanceCriterion(text="Second unique criterion")],
            tests=["python -m unittest discover -s tests"],
        )

        with patch.dict(os.environ, {"VOCR_PROMPT_MODE": "contract"}):
            prompt_one = render_task_template(task_one)
            prompt_two = render_task_template(task_two)

        self.assertEqual(prompt_one, prompt_two)
        self.assertIn(".vocr/VOCR_TASK.json", prompt_one)
        self.assertIn(".vocr/scope.json", prompt_one)
        self.assertIn(".vocr/CONTEXT_PACK.txt", prompt_one)
        self.assertIn("baseline_checks", prompt_one)
        self.assertNotIn(task_one.title, prompt_one)
        self.assertNotIn("First unique criterion", prompt_one)
        self.assertNotIn(task_two.title, prompt_two)
        self.assertNotIn("Second unique criterion", prompt_two)

    def test_baseline_checks_flag_off_does_not_run_subprocess_and_leaves_contract_empty(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            worktree = Path(tmp)
            task = VocrTask(
                id="task-baseline-off",
                slice_id="slice-baseline",
                title="No baseline by default",
                summary="Do not run checks unless the flag is on.",
                scope=["src"],
                acceptance_criteria=[AcceptanceCriterion(text="Contract exists")],
                tests=["Syntax-Check"],
                worktree_path=worktree,
            )

            with patch.dict(os.environ, {"VOCR_BASELINE_CHECKS": ""}, clear=False), patch(
                "vocr.codex.mcp_client.subprocess.run",
                side_effect=AssertionError("baseline subprocess should not run"),
            ):
                CodexMcpClient(command="codex").write_manifest(task)
            contract = TaskContract.model_validate_json(
                (worktree / ".vocr" / "VOCR_TASK.json").read_text(encoding="utf-8")
            )

        self.assertEqual(contract.baseline_checks, [])

    def test_baseline_checks_flag_on_records_failed_and_manual_checks_without_blocking(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            worktree = Path(tmp)
            task = VocrTask(
                id="task-baseline-on",
                slice_id="slice-baseline",
                title="Collect baseline",
                summary="Record baseline checks in the contract.",
                scope=["src"],
                acceptance_criteria=[AcceptanceCriterion(text="Contract has baseline")],
                tests=["Syntax-Check", "manual smoke"],
                worktree_path=worktree,
            )

            def fake_run(command: list[str], **_: object) -> subprocess.CompletedProcess[str]:
                return subprocess.CompletedProcess(command, 1, stdout="line one\n" + ("x" * 250), stderr="")

            with patch.dict(os.environ, {"VOCR_BASELINE_CHECKS": "true"}), patch(
                "vocr.codex.mcp_client.subprocess.run",
                side_effect=fake_run,
            ):
                manifest_path = CodexMcpClient(command="codex").write_manifest(task)
            contract = TaskContract.model_validate_json(
                (worktree / ".vocr" / "VOCR_TASK.json").read_text(encoding="utf-8")
            )

        self.assertEqual(manifest_path.name, "VOCR_TASK.md")
        self.assertEqual([item.status for item in contract.baseline_checks], ["failed", "manual"])
        self.assertLessEqual(len(contract.baseline_checks[0].summary), 200)
        self.assertEqual(contract.baseline_checks[1].command, "manual smoke")

    def test_distill_failure_output_keeps_repo_traceback_and_exception_without_site_packages(self) -> None:
        text = "\n".join(
            [
                "noise before",
                "Traceback (most recent call last):",
                '  File "C:\\Users\\jeenz\\Desktop\\Agent\\.venv\\Lib\\site-packages\\pkg\\runner.py", line 10, in run',
                "    call()",
                '  File "C:\\Users\\jeenz\\Desktop\\Agent\\src\\vocr\\cli\\app.py", line 802, in run_worker',
                "    raise ValueError('boom')",
                "ValueError: boom",
            ]
        )

        distilled = distill_failure_output(text, max_chars=1200)

        self.assertIn("Traceback (most recent call last):", distilled)
        self.assertIn("src\\vocr\\cli\\app.py", distilled)
        self.assertIn("ValueError: boom", distilled)
        self.assertNotIn("site-packages", distilled)

    def test_distill_failure_output_uses_error_window_without_traceback(self) -> None:
        text = "\n".join(["line 1", "line 2", "FAILED: build target", "line 4", "line 5", "line 6"])

        distilled = distill_failure_output(text, max_chars=1200)

        self.assertIn("line 1", distilled)
        self.assertIn("FAILED: build target", distilled)
        self.assertIn("line 5", distilled)
        self.assertNotIn("line 6", distilled)

    def test_distill_failure_output_falls_back_to_exact_tail_slice(self) -> None:
        text = "abcdefghijklmnopqrstuvwxyz"

        self.assertEqual(distill_failure_output(text, max_chars=10), text[-10:])

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

    def test_require_checks_off_keeps_generic_tests_escape_hatch(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ledger = MemoryLedger(Path(tmp) / ".vocr")
            task = VocrTask(
                id="task-check-off",
                slice_id="slice-checks",
                title="Manualish criterion",
                summary="Keep old behavior when the ratchet is off.",
                scope=["docs"],
                acceptance_criteria=[AcceptanceCriterion(text="Docs explain setup", verified_by="vocr review")],
                tests=["manual review"],
                status=TaskStatus.dispatched,
            )
            ledger.append(LedgerEventType.task_created, task)

            with patch.dict(os.environ, {"VOCR_REQUIRE_CHECKS": "off"}):
                review = review_task(ledger, task.id, decision=ReviewDecision.accepted)

        self.assertEqual(review.decision, ReviewDecision.accepted)
        self.assertEqual(review.required_changes, [])

    def test_require_checks_warn_adds_risk_without_blocking_promotion_gate(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ledger = MemoryLedger(Path(tmp) / ".vocr")
            task = VocrTask(
                id="task-check-warn",
                slice_id="slice-checks",
                title="Warn missing checks",
                summary="Warn for criteria that have no executable check.",
                scope=["docs"],
                acceptance_criteria=[AcceptanceCriterion(text="Docs explain setup", verified_by="vocr review")],
                tests=["manual review"],
                status=TaskStatus.dispatched,
            )
            ledger.append(LedgerEventType.task_created, task)

            with patch.dict(os.environ, {"VOCR_REQUIRE_CHECKS": "warn"}):
                review = review_task(ledger, task.id, decision=ReviewDecision.accepted)

        self.assertEqual(review.decision, ReviewDecision.accepted)
        self.assertEqual(review.required_changes, [])
        self.assertTrue(any("Kriterium ohne ausfuehrbaren Check" in risk for risk in review.risks))

    def test_require_checks_block_downgrades_text_criterion_even_with_generic_tests(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ledger = MemoryLedger(Path(tmp) / ".vocr")
            task = VocrTask(
                id="task-check-block",
                slice_id="slice-checks",
                title="Block missing checks",
                summary="Block criteria that have no executable check.",
                scope=["docs"],
                acceptance_criteria=[AcceptanceCriterion(text="Docs explain setup", verified_by="vocr review")],
                tests=["manual review"],
                status=TaskStatus.dispatched,
            )
            ledger.append(LedgerEventType.task_created, task)

            with patch.dict(os.environ, {"VOCR_REQUIRE_CHECKS": "block"}):
                review = review_task(ledger, task.id, decision=ReviewDecision.accepted)

        self.assertEqual(review.decision, ReviewDecision.needs_changes)
        self.assertTrue(any("Kriterium ohne ausfuehrbaren Check" in item for item in review.required_changes))

    def test_require_checks_block_accepts_executable_or_manual_mapped_criteria(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ledger = MemoryLedger(Path(tmp) / ".vocr")
            task = VocrTask(
                id="task-check-ok",
                slice_id="slice-checks",
                title="Executable criteria",
                summary="Executable or explicit manual coverage is allowed.",
                scope=["docs"],
                acceptance_criteria=[
                    AcceptanceCriterion(
                        text="Compile succeeds",
                        verified_by="automation",
                        check_command="python -m compileall src",
                    ),
                    AcceptanceCriterion(text="Copy reviewed", verified_by="manual"),
                ],
                tests=["manual review"],
                status=TaskStatus.dispatched,
            )
            ledger.append(LedgerEventType.task_created, task)

            with patch.dict(os.environ, {"VOCR_REQUIRE_CHECKS": "block"}):
                review = review_task(ledger, task.id, decision=ReviewDecision.accepted)

        self.assertEqual(review.decision, ReviewDecision.accepted)
        self.assertEqual(review.required_changes, [])

    def test_learning_store_aggregates_reviews_without_raw_diff(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / ".vocr"
            ledger = MemoryLedger(root)
            task = VocrTask(
                id="task-learn",
                slice_id="slice-learn",
                title="Docs update",
                summary="Update docs",
                scope=["docs"],
                acceptance_criteria=[AcceptanceCriterion(text="Docs updated")],
                tests=["Syntax-Check"],
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
                LedgerEventType.review_recorded,
                ReviewResult(
                    task_id=task.id,
                    decision=ReviewDecision.needs_changes,
                    summary="Needs docs fix",
                    required_changes=["Clarify setup"],
                    tests_reviewed=["Syntax-Check"],
                    diff_files=["README.md"],
                ),
            )
            learning = LearningStore(root)
            snapshot = learning.refresh(ledger)

        self.assertIn("scope:docs", snapshot.scopes)
        self.assertEqual(snapshot.scopes["scope:docs"].files["README.md"], 1)
        self.assertEqual(snapshot.scopes["scope:docs"].estimated_tokens, 42)

    def test_learning_store_predicts_task_tokens_from_matching_terms(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / ".vocr"
            LearningStore(root).save(
                LearningSnapshot(
                    scopes={
                        "scope:docs": LearningEntry(key="scope:docs", count=2, estimated_tokens=80),
                        "scope:api": LearningEntry(key="scope:api", count=1, estimated_tokens=200),
                    },
                    task_titles={
                        "task:budget retry": LearningEntry(key="task:budget retry", count=1, estimated_tokens=20)
                    },
                )
            )
            task = VocrTask(
                id="tb-budget",
                slice_id="slice-budget",
                title="Budget Retry",
                summary="Exercise token budget prediction.",
                scope=["docs"],
                acceptance_criteria=[AcceptanceCriterion(text="Budget checked")],
                tests=["manual review"],
            )

            prediction = LearningStore(root).predict_task_tokens(task)

        self.assertEqual(prediction, 30)

    def test_token_budget_warn_records_message_but_keeps_auto_retry(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            vocr_home = Path(tmp) / ".vocr"
            worktree = Path(tmp) / "worktree"
            worktree.mkdir()
            ledger = MemoryLedger(vocr_home)
            task = VocrTask(
                id="tb-budget-warn",
                slice_id="slice-budget",
                title="Budget Retry",
                summary="Warn but keep retrying.",
                scope=["docs"],
                acceptance_criteria=[AcceptanceCriterion(text="Budget warning recorded")],
                tests=["manual review"],
                status=TaskStatus.dispatched,
                worktree_path=worktree,
            )
            ledger.append(LedgerEventType.task_created, task)
            LearningStore(vocr_home).save(
                LearningSnapshot(task_titles={"task:budget retry": LearningEntry(key="task:budget retry", count=1, estimated_tokens=1)})
            )
            calls: list[str | None] = []

            def fake_run(*_: object, **kwargs: object) -> CodexRunResult:
                calls.append(kwargs.get("extra_prompt"))
                return CodexRunResult(task_id=task.id, command=["codex"], exit_code=1, stderr="x" * 200)

            with patch.dict(
                os.environ,
                {"VOCR_HOME": str(vocr_home), "VOCR_TOKEN_BUDGET_MODE": "warn", "VOCR_TOKEN_BUDGET_FACTOR": "1.0"},
            ), patch("vocr.cli.app.CodexMcpClient.run_task", side_effect=fake_run), patch(
                "vocr.cli.app.GitWorktreeManager.diff",
                return_value="",
            ):
                result = CliRunner().invoke(
                    app,
                    ["run", task.id, "--fix", "--max-retries", "1", "--no-commit"],
                    env={
                        "VOCR_HOME": str(vocr_home),
                        "VOCR_TOKEN_BUDGET_MODE": "warn",
                        "VOCR_TOKEN_BUDGET_FACTOR": "1.0",
                    },
                )
            messages = [event.payload.get("message", "") for event in MemoryLedger(vocr_home).events() if event.type == LedgerEventType.message]

        self.assertEqual(result.exit_code, 0, result.output)
        self.assertEqual(len(calls), 2)
        self.assertIsNotNone(calls[1])
        self.assertTrue(any("token budget exceeded" in message for message in messages))

    def test_token_budget_block_stops_auto_retry_after_exceeded_attempt(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            vocr_home = Path(tmp) / ".vocr"
            worktree = Path(tmp) / "worktree"
            worktree.mkdir()
            ledger = MemoryLedger(vocr_home)
            task = VocrTask(
                id="tb-budget-block",
                slice_id="slice-budget",
                title="Budget Retry",
                summary="Block further retries.",
                scope=["docs"],
                acceptance_criteria=[AcceptanceCriterion(text="Budget block recorded")],
                tests=["manual review"],
                status=TaskStatus.dispatched,
                worktree_path=worktree,
            )
            ledger.append(LedgerEventType.task_created, task)
            LearningStore(vocr_home).save(
                LearningSnapshot(task_titles={"task:budget retry": LearningEntry(key="task:budget retry", count=1, estimated_tokens=1)})
            )
            calls: list[str | None] = []

            def fake_run(*_: object, **kwargs: object) -> CodexRunResult:
                calls.append(kwargs.get("extra_prompt"))
                return CodexRunResult(task_id=task.id, command=["codex"], exit_code=1, stderr="x" * 200)

            with patch.dict(
                os.environ,
                {"VOCR_HOME": str(vocr_home), "VOCR_TOKEN_BUDGET_MODE": "block", "VOCR_TOKEN_BUDGET_FACTOR": "1.0"},
            ), patch("vocr.cli.app.CodexMcpClient.run_task", side_effect=fake_run), patch(
                "vocr.cli.app.GitWorktreeManager.diff",
                side_effect=AssertionError("block mode should not build retry diff"),
            ):
                result = CliRunner().invoke(
                    app,
                    ["run", task.id, "--fix", "--max-retries", "2", "--no-commit"],
                    env={
                        "VOCR_HOME": str(vocr_home),
                        "VOCR_TOKEN_BUDGET_MODE": "block",
                        "VOCR_TOKEN_BUDGET_FACTOR": "1.0",
                    },
                )
            messages = [event.payload.get("message", "") for event in MemoryLedger(vocr_home).events() if event.type == LedgerEventType.message]

        self.assertEqual(result.exit_code, 0, result.output)
        self.assertEqual(len(calls), 1)
        self.assertTrue(any("token budget exceeded" in message for message in messages))

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


if __name__ == "__main__":
    unittest.main()
