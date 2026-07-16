from __future__ import annotations

import base64
import json
import tempfile
import unittest
import inspect
import urllib.error
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from typer.testing import CliRunner

from vocr.cli.app import app
from vocr.beta.scenarios import SCENARIOS
from vocr.memory.ledger import MemoryLedger
from vocr.memory.learning import LearningStore
from vocr.models import (
    AcceptanceCriterion,
    LedgerEventType,
    LearningEntry,
    LearningSnapshot,
    NormalModePhase,
    PermissionGrant,
    PermissionMode,
    VocrTask,
)
from vocr.orchestration.worker_advisor import WorkerParallelismAdvisor
from vocr.ui.normal_mode import (
    NormalModeController,
    beta_next_test_chain,
    codex_login_status,
    final_all_in_one_labels,
    final_local_test_command_plan,
    launch_console_mode,
    launch_normal_mode,
    lmstudio_reachability_status,
    model_auth_status,
    normal_mode_update_command_plan,
    normal_mode_surface_decision,
    open_codex_login_shell,
    open_expert_shell,
)


def assert_no_normal_mode_debug_ids(testcase: unittest.TestCase, message: str) -> None:
    testcase.assertNotIn("Clarification ID", message)
    testcase.assertNotIn("Clarification-IDs", message)
    testcase.assertNotIn("clarify-", message)
    testcase.assertNotIn("vocr answer", message)


class NormalModeTests(unittest.TestCase):
    def _task(self, task_id: str, scope: list[str], dependencies: list[str] | None = None) -> VocrTask:
        return VocrTask(
            id=task_id,
            slice_id="slice-normal-test",
            title=f"Task {task_id}",
            summary="Test task",
            scope=scope,
            acceptance_criteria=[AcceptanceCriterion(text="done")],
            tests=["unit"],
            dependencies=dependencies or [],
        )

    def test_normal_mode_collects_intake_without_exposing_internal_ids(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            controller = NormalModeController(Path(tmp))

            first = controller.receive(
                "Ich moechte eine kleine lokale Oberflaeche bauen, "
                "die Projektideen mit dem Visionaer klaert."
            )

            self.assertEqual(first.phase, NormalModePhase.intake)
            self.assertIn("Ich schlage diesen Rahmen vor", first.message)
            self.assertIn("Arbeitsbereich", first.message)
            assert_no_normal_mode_debug_ids(self, first.message)

            execution = controller.receive("passt, aber keine Docs erstmal")

            self.assertIn("Dokumentationsaenderungen sind ausgeschlossen", execution.message)
            self.assertEqual(execution.phase, NormalModePhase.intake)
            self.assertIn("Naechster Punkt: Akzeptanz", execution.message)
            self.assertIn("keine Dokumentationsaenderungen", execution.status.non_goals)
            assert_no_normal_mode_debug_ids(self, execution.message)

            acceptance = controller.receive("ja")
            self.assertIn("Naechster Punkt: Verifikation", acceptance.message)

            verification = controller.receive("ja")
            self.assertIn("Naechster Punkt: Ausfuehrungsgrenzen", verification.message)

            confirmation = controller.receive("nur planen")
            self.assertEqual(confirmation.phase, NormalModePhase.confirmation)
            self.assertIn("Soll ich so fortfahren", confirmation.message)
            self.assertNotIn("task-", confirmation.message)
            self.assertNotIn("slice-", confirmation.message)

            prepared = controller.receive("Bestaetigen")

            self.assertEqual(prepared.phase, NormalModePhase.prepared)
            self.assertEqual(prepared.prepared_tasks, 1)
            self.assertEqual(prepared.prepared_worktrees, 0)
            self.assertIn("kleine, pruefbare Schritte", prepared.message)

    def test_start_command_is_available_for_normal_users(self) -> None:
        result = CliRunner().invoke(app, ["start", "--help"])

        self.assertEqual(result.exit_code, 0)
        self.assertIn("local GUI Visionary conversation", result.output)
        self.assertIn("console", result.output)
        self.assertIn("terminal fallback", result.output)
        self.assertIn("DANGEROUS", result.output)
        self.assertIn("approve-all", result.output)

        with tempfile.TemporaryDirectory() as tmp:
            with patch("vocr.cli.app.prepare_start_or_exit", return_value=SimpleNamespace(repo_root=Path(tmp))):
                with patch("vocr.cli.app.open_normal_mode") as open_normal_mode:
                    console_result = CliRunner().invoke(app, ["start", "--console"])

        self.assertEqual(console_result.exit_code, 0, console_result.output)
        open_normal_mode.assert_called_once_with(Path(tmp), console_only=True, session_permission=None)

    def test_start_uses_dangerous_permissions_for_current_session_only(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            with patch("vocr.cli.app.prepare_start_or_exit", return_value=SimpleNamespace(repo_root=root)):
                with patch("vocr.cli.app.open_normal_mode") as open_normal_mode:
                    result = CliRunner().invoke(app, ["start", "--console", "--dangerously-skip-permissions"])

            self.assertEqual(result.exit_code, 0, result.output)
            self.assertIn("WARNUNG", result.output)
            self.assertIn("Approve-all", result.output)
            _, kwargs = open_normal_mode.call_args
            self.assertEqual(kwargs["console_only"], True)
            self.assertEqual(kwargs["session_permission"].mode, PermissionMode.approve_all)
            self.assertEqual(kwargs["session_permission"].scope, "global")
            grant = MemoryLedger(root / ".vocr").active_permission("global")
            self.assertIsNone(grant)

    def test_normal_opening_explains_dangerous_permission_option(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            controller = NormalModeController(root)

            opening = controller.opening_message()

            self.assertNotIn("codex login", opening.message)
            self.assertIn("dangerously-skip-permissions", opening.message)
            self.assertIn("riskanter", opening.message)

            ledger = MemoryLedger(root / ".vocr")
            ledger.init()
            ledger.append(
                LedgerEventType.permission_granted,
                PermissionGrant(mode=PermissionMode.approve_all, scope="global", reason="test"),
            )
            active_opening = NormalModeController(root, session_permission=PermissionGrant(mode=PermissionMode.approve_all, scope="global")).opening_message()

            self.assertIn("Approve-all ist fuer diese Session aktiv", active_opening.message)
            self.assertIn("Promote-Gates bleiben aktiv", active_opening.message)

            persistent_opening = NormalModeController(root).opening_message()

            self.assertIn("persistenter Approve-all-Grant", persistent_opening.message)

    def test_expert_mode_menu_opens_shell_in_repo(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            with patch("vocr.ui.normal_mode.subprocess.Popen") as popen:
                open_expert_shell(root)

            args, kwargs = popen.call_args
            self.assertEqual(kwargs["cwd"], str(root.resolve()))
            self.assertIn("powershell", args[0][0])
            self.assertIn("-NoExit", args[0])
            self.assertIn("vocr --help", args[0][-1])

    def test_codex_login_menu_opens_login_shell_in_repo(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            with patch("vocr.ui.normal_mode.subprocess.Popen") as popen:
                open_codex_login_shell(root)

            args, kwargs = popen.call_args
            self.assertEqual(kwargs["cwd"], str(root.resolve()))
            self.assertIn("powershell", args[0][0])
            self.assertIn("-NoExit", args[0])
            self.assertIn("codex login", args[0][-1])

    def test_codex_login_status_reports_chatgpt_identity_without_tokens(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            auth_path = Path(tmp) / "auth.json"
            payload = {"name": "Ada User", "email": "ada@example.test"}
            encoded_payload = base64.urlsafe_b64encode(json.dumps(payload).encode("utf-8")).decode("ascii").rstrip("=")
            auth_path.write_text(
                json.dumps({"tokens": {"id_token": f"header.{encoded_payload}.signature"}}),
                encoding="utf-8",
            )
            completed = SimpleNamespace(returncode=0, stdout="Logged in using ChatGPT\n", stderr="")

            with patch("vocr.ui.normal_mode.subprocess.run", return_value=completed):
                status = codex_login_status(auth_path)

        self.assertIn("eingeloggt via ChatGPT", status)
        self.assertIn("Ada User", status)
        self.assertIn("ada@example.test", status)
        self.assertNotIn("signature", status)

    def test_codex_login_status_reports_logged_out(self) -> None:
        completed = SimpleNamespace(returncode=1, stdout="", stderr="Not logged in")

        with patch("vocr.ui.normal_mode.subprocess.run", return_value=completed):
            status = codex_login_status(Path("missing-auth.json"))

        self.assertEqual(status, "ChatGPT/Codex: nicht eingeloggt")

    def test_model_auth_status_confirms_lmstudio_without_showing_secret(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / ".env").write_text(
                "\n".join(
                    [
                        "LMSTUDIO_API_KEY=super-secret-local-key",
                        "OPENAI_BASE_URL=http://localhost:1234/v1",
                        "OPENAI_MODEL=local-test-model",
                    ]
                )
                + "\n",
                encoding="utf-8",
            )

            status = model_auth_status(root)

        self.assertIn("LM Studio: Key gesetzt", status)
        self.assertIn("http://localhost:1234/v1", status)
        self.assertIn("local-test-model", status)
        self.assertNotIn("super-secret-local-key", status)

    def test_model_auth_status_reports_missing_key(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            status = model_auth_status(Path(tmp))

        self.assertEqual(status, "API-Key: nicht gesetzt")

    def test_lmstudio_reachability_status_reports_green_without_secret(self) -> None:
        class FakeResponse:
            def __enter__(self):
                return self

            def __exit__(self, *_):
                return None

            def read(self) -> bytes:
                return b'{"data":[{"id":"local-test-model"}]}'

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / ".env").write_text(
                "\n".join(
                    [
                        "LMSTUDIO_API_KEY=super-secret-local-key",
                        "OPENAI_BASE_URL=http://localhost:1234/v1",
                        "OPENAI_MODEL=local-test-model",
                    ]
                )
                + "\n",
                encoding="utf-8",
            )

            with patch("vocr.ui.normal_mode.urllib.request.urlopen", return_value=FakeResponse()) as urlopen:
                status = lmstudio_reachability_status(root)

            request = urlopen.call_args.args[0]

        self.assertIn("gruen", status)
        self.assertIn("erreichbar", status)
        self.assertNotIn("super-secret-local-key", status)
        self.assertEqual(request.headers["Authorization"], "Bearer super-secret-local-key")

    def test_lmstudio_reachability_status_reports_auth_failure(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / ".env").write_text("LMSTUDIO_API_KEY=bad\nOPENAI_BASE_URL=http://localhost:1234/v1\n", encoding="utf-8")
            error = urllib.error.HTTPError("http://localhost:1234/v1/models", 401, "Unauthorized", hdrs=None, fp=None)

            with patch("vocr.ui.normal_mode.urllib.request.urlopen", side_effect=error):
                status = lmstudio_reachability_status(root)

        self.assertEqual(status, "LM Studio Ampel: rot - API-Key/Auth abgelehnt")
        self.assertNotIn("bad", status)

    def test_lmstudio_reachability_status_reports_model_mismatch(self) -> None:
        class FakeResponse:
            def __enter__(self):
                return self

            def __exit__(self, *_):
                return None

            def read(self) -> bytes:
                return b'{"data":[{"id":"other-model"}]}'

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / ".env").write_text("LMSTUDIO_API_KEY=k\nOPENAI_MODEL=expected-model\n", encoding="utf-8")

            with patch("vocr.ui.normal_mode.urllib.request.urlopen", return_value=FakeResponse()):
                status = lmstudio_reachability_status(root)

        self.assertIn("gelb", status)
        self.assertIn("expected-model", status)

    def test_beta_next_test_chain_is_deterministic_and_core_by_default(self) -> None:
        chain = beta_next_test_chain()
        scenario_ids = [scenario_id for step in chain for scenario_id in step.only]
        core_ids = [scenario.id for scenario in SCENARIOS.values() if scenario.tier == "core"]

        self.assertEqual(
            [step.tag for step in chain],
            ["chain-01-smoke", "chain-02-safety", "chain-03-workflow", "chain-04-local-mocks"],
        )
        self.assertEqual(set(scenario_ids), set(core_ids))
        self.assertEqual(len(scenario_ids), len(set(scenario_ids)))
        self.assertIn("S18", scenario_ids)
        self.assertIn("S20", scenario_ids)
        self.assertIn("S23", scenario_ids)
        self.assertNotIn("S17", scenario_ids)
        self.assertNotIn("C00", scenario_ids)
        self.assertTrue(all(step.tier == "core" for step in chain))
        self.assertFalse(any(step.allow_cloud for step in chain))

    def test_beta_next_test_chain_adds_cloud_only_when_requested(self) -> None:
        chain = beta_next_test_chain(include_cloud=True)
        cloud_step = chain[-1]

        self.assertEqual(cloud_step.only, ("C00", "C01", "C02", "C03", "C05", "C06"))
        self.assertEqual(cloud_step.tier, "cloud")
        self.assertTrue(cloud_step.allow_cloud)
        self.assertEqual(cloud_step.max_cloud_tasks, 6)
        self.assertNotIn("C04", cloud_step.only)
        self.assertNotIn("C07", cloud_step.only)

    def test_beta_next_test_chain_adds_local_live_only_when_requested(self) -> None:
        chain = beta_next_test_chain(include_local_live=True)
        local_step = chain[-1]

        self.assertEqual(local_step.only, ("S21", "S22"))
        self.assertEqual(local_step.tier, "local")
        self.assertFalse(local_step.allow_cloud)

    def test_update_button_plan_uses_fast_forward_pull_and_refreshes_install(self) -> None:
        plan = normal_mode_update_command_plan()
        flattened = [" ".join(command) for _, command in plan]

        self.assertIn("git pull --ff-only", flattened[0])
        self.assertTrue(any("-m pip install -e ." in command for command in flattened))
        self.assertTrue(any("-m vocr.main bootstrap --no-start --write-scripts" in command for command in flattened))

    def test_final_all_in_one_labels_cover_previous_automated_checks(self) -> None:
        labels = " ".join(final_all_in_one_labels())
        cloud_labels = " ".join(final_all_in_one_labels(include_cloud=True))
        gate_commands = [" ".join(command) for _, command in final_local_test_command_plan()]

        self.assertIn("Update", labels)
        self.assertIn("Syntax", labels)
        self.assertIn("Unit-Tests", labels)
        self.assertIn("ChatGPT/Codex", labels)
        self.assertIn("LM Studio", labels)
        self.assertIn("S21/S22", labels)
        self.assertIn("Core-Beta", labels)
        self.assertIn("Core-Beta-Kette", labels)
        self.assertNotIn("S17", labels)
        self.assertIn("C00-C03", cloud_labels)
        self.assertIn("C06", cloud_labels)
        self.assertNotIn("S17", cloud_labels)
        self.assertTrue(any("-m compileall src tests" in command for command in gate_commands))
        self.assertTrue(any("-m unittest discover -s tests" in command for command in gate_commands))

    def test_gui_activity_bridge_lives_in_gui_launcher(self) -> None:
        gui_source = inspect.getsource(launch_normal_mode)
        console_source = inspect.getsource(launch_console_mode)

        self.assertIn("controller_activity: dict", gui_source)
        self.assertIn("controller_activity[\"handler\"] = controller_activity_handler", gui_source)
        self.assertNotIn("controller_activity: dict", console_source)

    def test_normal_mode_surface_decision_uses_local_gui_without_buildchain(self) -> None:
        decision = normal_mode_surface_decision()

        self.assertEqual(decision["selected"], "tkinter-gui")
        self.assertEqual(decision["fallback"], "console")
        self.assertIn("no_cloud_dependency", decision["constraints"])
        self.assertIn("no_frontend_buildchain", decision["constraints"])
        self.assertIn("single_textbox_dialog", decision["constraints"])
        self.assertIn("Textual/TUI", " ".join(decision["deferred"]))
        self.assertIn("Local web GUI", " ".join(decision["deferred"]))

    def test_visionary_proposes_next_step_and_accepts_natural_correction(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            controller = NormalModeController(Path(tmp))

            proposal = controller.receive("Ich will die Clarification-UX verbessern.")

            self.assertIn("Ich verstehe", proposal.message)
            self.assertIn("src/vocr/ui", proposal.message)
            self.assertIn("src/vocr/cli", proposal.message)
            self.assertIn("Naechster Punkt: Arbeitsbereich", proposal.message)

            next_step = controller.receive("Passt, aber keine Docs erstmal.")

            self.assertIn("Dokumentationsaenderungen sind ausgeschlossen", next_step.message)
            self.assertEqual(next_step.phase, NormalModePhase.intake)
            self.assertIn("Naechster Punkt: Akzeptanz", next_step.message)
            self.assertIn("keine Dokumentationsaenderungen", next_step.status.non_goals)
            self.assertNotIn("Dispatch", next_step.message)
            self.assertNotIn("Worktree", next_step.message)

    def test_short_initial_message_gets_contextual_complete_intake_proposal(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            controller = NormalModeController(Path(tmp))

            proposal = controller.receive("Ich will eine Startshell fuer VOCR.")

            self.assertIn("einfacheren Einstieg fuer normale VOCR-Nutzer", proposal.message)
            self.assertIn("src/vocr/cli/app.py", proposal.message)
            self.assertIn("neue Start-/Dialog-Komponente", proposal.message)
            self.assertIn("User kann vocr start ausfuehren", proposal.message)
            self.assertIn("User sieht keine technischen Rueckfrage-Codes", proposal.message)
            self.assertIn("python -m compileall src tests", proposal.message)
            self.assertIn("keine Aenderungen an Review, Promote oder Worker-Sandboxing", proposal.message)
            self.assertIn("Erst planen", proposal.message)
            self.assertEqual(proposal.status.readiness, "1/6 geklaert")
            assert_no_normal_mode_debug_ids(self, proposal.message)

            next_step = controller.receive("Passt.")

            self.assertEqual(next_step.phase, NormalModePhase.intake)
            self.assertIn("Naechster Punkt: Akzeptanz", next_step.message)
            self.assertIn("src/vocr/cli/app.py", next_step.status.workspace)
            assert_no_normal_mode_debug_ids(self, next_step.message)

            confirmation = controller.receive("alles passt")

            self.assertEqual(confirmation.phase, NormalModePhase.confirmation)
            self.assertEqual(confirmation.status.readiness, "6/6 geklaert")
            self.assertIn("Soll ich so fortfahren", confirmation.message)
            assert_no_normal_mode_debug_ids(self, confirmation.message)

    def test_sequential_intake_updates_current_state_without_creating_tasks(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            controller = NormalModeController(root)

            proposal = controller.receive("Ich will eine Startshell fuer VOCR.")
            self.assertIn("Naechster Punkt: Arbeitsbereich", proposal.message)

            scope = controller.receive("Nimm Docs doch mit rein.")
            self.assertIn("Arbeitsbereich erweitert um README/docs", scope.message)
            self.assertIn("README/docs", scope.status.workspace)
            self.assertIn("Naechster Punkt: Akzeptanz", scope.message)

            acceptance = controller.receive("ja")
            self.assertIn("Naechster Punkt: Verifikation", acceptance.message)

            verification = controller.receive("ja")
            self.assertIn("Naechster Punkt: Nicht-Ziele", verification.message)

            risks = controller.receive("ja")
            self.assertIn("Naechster Punkt: Ausfuehrungsgrenzen", risks.message)

            execution = controller.receive("mit Worktree, aber nicht mergen")
            self.assertEqual(execution.phase, NormalModePhase.confirmation)
            self.assertIn("getrennten Arbeitsbereich", execution.message)
            self.assertIn("Zusammenfassung", execution.message)
            self.assertIn("Ich werde intern", execution.message)
            self.assertIn("Sicherheitsgrenzen", execution.message)
            self.assertFalse((root / ".vocr" / "ledger.jsonl").exists())

    def test_confirmation_gate_summarizes_and_waits_before_creating_work(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            controller = NormalModeController(root)

            controller.receive("Ich will eine Startshell fuer VOCR.")
            controller.receive("ja")
            controller.receive("ja")
            controller.receive("ja")
            controller.receive("ja")
            gate = controller.receive("nur planen")

            self.assertEqual(gate.phase, NormalModePhase.confirmation)
            self.assertIn("Ich habe jetzt genug Informationen", gate.message)
            self.assertIn("Ziel:", gate.message)
            self.assertIn("Arbeitsbereich:", gate.message)
            self.assertIn("Akzeptanz:", gate.message)
            self.assertIn("Verifikation:", gate.message)
            self.assertIn("Nicht-Ziele:", gate.message)
            self.assertIn("Ausfuehrungsmodus:", gate.message)
            self.assertIn("Ich werde intern:", gate.message)
            self.assertIn("einen VisionSlice anlegen", gate.message)
            self.assertIn("Sicherheitsgrenzen:", gate.message)
            self.assertIn("kein automatischer Promote oder Merge", gate.message)
            self.assertIn("Worktree-Isolation bleibt aktiv", gate.message)
            self.assertFalse((root / ".vocr" / "ledger.jsonl").exists())

            prepared = controller.receive("Ja, Worktree vorbereiten, aber nichts mergen.")

            self.assertEqual(prepared.phase, NormalModePhase.prepared)
            self.assertEqual(prepared.prepared_tasks, 1)
            self.assertIn("Automatischer Promote/Merge ist ausgeschlossen", prepared.message)
            self.assertTrue((root / ".vocr" / "ledger.jsonl").exists())

    def test_normal_mode_reports_internal_activity_during_prepare(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            events: list[str] = []
            controller = NormalModeController(Path(tmp), on_activity=events.append)

            controller.receive("Ich will eine Startshell fuer VOCR.")
            controller.receive("ja")
            controller.receive("ja")
            controller.receive("ja")
            controller.receive("ja")
            controller.receive("nur planen")
            prepared = controller.receive("Bestaetigen")

            self.assertEqual(prepared.phase, NormalModePhase.prepared)
            self.assertTrue(any("Ledger" in event for event in events))
            self.assertTrue(any("Repository-Graph" in event for event in events))
            self.assertTrue(any("VisionSlice" in event for event in events))
            self.assertTrue(any("Task" in event for event in events))

    def test_visionary_worker_plan_recommends_balanced_parallelism(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            tasks = [
                self._task("ta1", ["docs/**"]),
                self._task("ta2", ["src/api/**"]),
                self._task("ta3", ["src/cli/**"]),
                self._task("ta4", ["tests/**"]),
                self._task("ta5", ["README.md"]),
            ]

            options = WorkerParallelismAdvisor(root).options(tasks)
            message = WorkerParallelismAdvisor(root).message(tasks)

            self.assertEqual([option.workers for option in options], list(range(1, len(options) + 1)))
            self.assertEqual(len([option for option in options if option.recommended]), 1)
            self.assertGreater(options[-1].speedup_pct, options[0].speedup_pct)
            self.assertGreater(options[-1].token_overhead_pct, options[0].token_overhead_pct)
            self.assertTrue(all(option.confidence == "heuristic" for option in options))
            self.assertEqual(options[1].speedup_pct, 50)
            self.assertEqual(WorkerParallelismAdvisor(root).recommended_workers(tasks), 2)
            self.assertIn("Worker-Vorschlag des Visionaers", message)
            self.assertIn("Empfohlen:", message)
            self.assertIn("Heuristik", message)

    def test_visionary_worker_plan_uses_measured_speedup_when_available(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            ledger = MemoryLedger(root / ".vocr")
            for _ in range(3):
                ledger.append(
                    LedgerEventType.wave_executed,
                    {"worker_count": 1, "task_count": 2, "worked_count": 2, "wall_seconds": 10.0, "mode": "serial"},
                )
                ledger.append(
                    LedgerEventType.wave_executed,
                    {"worker_count": 2, "task_count": 2, "worked_count": 2, "wall_seconds": 7.0, "mode": "parallel"},
                )
            tasks = [
                self._task("ta1", ["docs/**"]),
                self._task("ta2", ["src/api/**"]),
            ]

            options = WorkerParallelismAdvisor(root).options(tasks)
            measured = next(option for option in options if option.workers == 2)
            message = WorkerParallelismAdvisor(root).message(tasks)

            self.assertEqual(measured.speedup_pct, 30)
            self.assertEqual(measured.confidence, "measured")
            self.assertIn("kalibriert aus 3 Lauf-Samples", measured.rationale)
            self.assertIn("kalibriert aus 3 Lauf-Samples", message)

    def test_visionary_worker_plan_uses_measured_duration_when_available(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            LearningStore(root / ".vocr").save(
                LearningSnapshot(
                    task_titles={
                        "task:task ta1": LearningEntry(
                            key="task:task ta1",
                            count=5,
                            duration_samples=[30.0, 32.0, 34.0, 36.0, 38.0],
                        )
                    }
                )
            )
            tasks = [self._task("ta1", ["docs/**"])]

            options = WorkerParallelismAdvisor(root).options(tasks)

            self.assertEqual(options[0].confidence, "measured")
            self.assertIn("kalibriert aus 5 Lauf-Samples", options[0].rationale)

    def test_visionary_worker_plan_respects_scope_conflicts_and_dependencies(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            tasks = [
                self._task("ta1", ["docs/**"]),
                self._task("ta2", ["docs/readme.md"]),
                self._task("ta3", ["src/api/**"], dependencies=["ta1"]),
            ]

            options = WorkerParallelismAdvisor(root).options(tasks)

            self.assertEqual([option.workers for option in options], [1])
            self.assertEqual(options[0].runnable_tasks, 1)
            self.assertTrue(options[0].recommended)

    def test_visionary_worker_plan_reduces_parallelism_for_broad_context_heavy_tasks(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            large_context = "context " * 1200
            tasks = [
                self._task("ta1", ["src/**"]),
                self._task("ta2", ["docs/**"]),
                self._task("ta3", ["tests/**"]),
            ]
            for task in tasks:
                task.context_pack = large_context
                task.tests = ["unit", "integration", "manual review"]

            options = WorkerParallelismAdvisor(root).options(tasks)
            recommended = next(option for option in options if option.recommended)

            self.assertLess(recommended.workers, len(options))
            self.assertEqual(options[-1].conflict_risk, "hoch")

    def test_new_goal_resets_active_intake(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            controller = NormalModeController(Path(tmp))

            controller.receive("Ich will eine Startshell fuer VOCR.")
            response = controller.receive("Ich will Graphify tokenaermer machen.")

            self.assertIn("Ich starte dafuer einen neuen Intake", response.message)
            self.assertIn("tokenaermer", response.status.goal)
            self.assertIn("src/vocr/graph", response.message)
            self.assertIn("Naechster Punkt: Arbeitsbereich", response.message)

    def test_normal_mode_sanitizes_accidental_clarification_debug_text(self) -> None:
        controller = NormalModeController(".")

        message = controller._normal_mode_text(
            'Clarification ID: clarify-abc123. Antworte mit `vocr answer clarify-abc123 "Details"`.'
        )
        controller.intake.goal = "Bitte nutze clarify-hidden123"
        status = controller.status()

        assert_no_normal_mode_debug_ids(self, message)
        self.assertIn("antworte einfach hier im Dialog", message)
        assert_no_normal_mode_debug_ids(self, status.goal)

    def test_expert_cli_still_shows_clarification_ids(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            result = CliRunner().invoke(
                app,
                ["ask", "Baue eine API"],
                env={"VOCR_HOME": str(Path(tmp) / ".vocr")},
            )

        self.assertEqual(result.exit_code, 0)
        self.assertIn("Clarification ID:", result.output)
        self.assertIn("vocr answer", result.output)

    def test_expert_cli_go_flow_keeps_existing_behavior(self) -> None:
        request = (
            "Ziel: Baue eine Healthcheck-API. "
            "Arbeitsbereich: src und tests. "
            "Akzeptanz: GET /health liefert 200. "
            "Verifikation: Syntax-Check. "
            "Nicht-Ziele: keine Auth. "
            "Ausfuehrung: nur planen, Review vor Promote."
        )
        with tempfile.TemporaryDirectory() as tmp:
            result = CliRunner().invoke(
                app,
                ["ask", request, "--go", "--no-dispatch"],
                env={"VOCR_HOME": str(Path(tmp) / ".vocr")},
            )

        self.assertEqual(result.exit_code, 0)
        self.assertIn("Approve-all is active", result.output)
        self.assertIn("Created task", result.output)

    def test_expert_cli_can_use_dangerous_permissions_for_current_run(self) -> None:
        request = (
            "Ziel: Baue eine Healthcheck-API. "
            "Arbeitsbereich: src und tests. "
            "Akzeptanz: GET /health liefert 200. "
            "Verifikation: Syntax-Check. "
            "Nicht-Ziele: keine Auth. "
            "Ausfuehrung: nur planen, Review vor Promote."
        )
        with tempfile.TemporaryDirectory() as tmp:
            vocr_home = Path(tmp) / ".vocr"
            result = CliRunner().invoke(
                app,
                ["ask", request, "--plan-only", "--dangerously-skip-permissions"],
                env={"VOCR_HOME": str(vocr_home)},
            )

            self.assertEqual(result.exit_code, 0, result.output)
            self.assertIn("WARNUNG", result.output)
            self.assertIn("Approve-all is active for this session only", result.output)
            grant = MemoryLedger(vocr_home).active_permission("global")
            self.assertIsNone(grant)

    def test_expert_cli_commands_remain_available(self) -> None:
        command_help = [
            ["ask", "--help"],
            ["answer", "--help"],
            ["reply", "--help"],
            ["log", "--help"],
            ["inspect", "--help"],
            ["diff", "--help"],
            ["review", "--help"],
            ["check", "--help"],
            ["promote", "--help"],
            ["ship", "--help"],
            ["doctor", "--help"],
            ["model", "--help"],
            ["auth", "--help"],
            ["worker", "--help"],
            ["secrets", "--help"],
            ["clean", "--help"],
            ["abort", "--help"],
        ]

        for command in command_help:
            with self.subTest(command=" ".join(command)):
                result = CliRunner().invoke(app, command)
                self.assertEqual(result.exit_code, 0, result.output)

    def test_expert_reply_without_id_uses_latest_open_clarification(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            env = {"VOCR_HOME": str(Path(tmp) / ".vocr")}
            first = CliRunner().invoke(app, ["ask", "Baue eine API"], env=env)
            second = CliRunner().invoke(
                app,
                [
                    "reply",
                    "Ziel: Baue eine API. Arbeitsbereich: src. Akzeptanz: API antwortet. "
                    "Verifikation: Syntax-Check. Nicht-Ziele: keine Auth. Ausfuehrung: nur planen.",
                ],
                env=env,
            )

        self.assertEqual(first.exit_code, 0)
        self.assertIn("Clarification ID:", first.output)
        self.assertEqual(second.exit_code, 0, second.output)
        self.assertIn("Created slice", second.output)


if __name__ == "__main__":
    unittest.main()
