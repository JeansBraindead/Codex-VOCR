from __future__ import annotations

import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from typer.testing import CliRunner

from vocr.cli.app import app
from vocr.memory.ledger import MemoryLedger
from vocr.models import AcceptanceCriterion, LedgerEventType, TaskStatus, VocrTask


def make_task(task_id: str, scope: list[str]) -> VocrTask:
    return VocrTask(
        id=task_id,
        slice_id="slice-parallel",
        title=f"Task {task_id}",
        summary="Exercise parallel worker orchestration.",
        scope=scope,
        acceptance_criteria=[AcceptanceCriterion(text="Worker is coordinated")],
        tests=["unit test"],
    )


def append_dispatched(ledger: MemoryLedger, task: VocrTask, root: Path) -> None:
    ledger.append(LedgerEventType.task_created, task)
    ledger.append(
        LedgerEventType.task_dispatched,
        {"task_id": task.id, "branch_name": f"vocr/{task.id}", "worktree_path": str(root)},
    )


class ParallelWorkerTests(unittest.TestCase):
    def test_default_work_ready_uses_serial_path_without_claims_or_sleep(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            vocr_home = root / ".vocr"
            store = MemoryLedger(vocr_home)
            append_dispatched(store, make_task("ta1", ["docs/**"]), root)
            append_dispatched(store, make_task("ta2", ["src/api/**"]), root)
            calls: list[str] = []

            def fake_run_worker(task_id: str, **_: object) -> None:
                calls.append(task_id)

            with patch("vocr.cli.app.run_worker", side_effect=fake_run_worker), patch(
                "vocr.cli.app.time.sleep", side_effect=AssertionError("serial path must not stagger")
            ):
                result = CliRunner().invoke(
                    app,
                    ["work-ready", "--limit", "2"],
                    env={"VOCR_HOME": str(vocr_home)},
                )

            claim_events = [
                event
                for event in MemoryLedger(vocr_home).events()
                if event.type in {LedgerEventType.claim_acquired, LedgerEventType.claim_released}
            ]

        self.assertEqual(result.exit_code, 0, result.output)
        self.assertEqual(calls, ["ta1", "ta2"])
        self.assertEqual(claim_events, [])

    def test_parallel_workers_run_disjoint_tasks_concurrently(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            vocr_home = root / ".vocr"
            store = MemoryLedger(vocr_home)
            append_dispatched(store, make_task("ta1", ["docs/**"]), root)
            append_dispatched(store, make_task("ta2", ["src/api/**"]), root)
            starts: dict[str, float] = {}
            lock = threading.Lock()

            def fake_run_worker(task_id: str, **_: object) -> None:
                with lock:
                    starts[task_id] = time.perf_counter()
                time.sleep(0.05)

            with patch("vocr.cli.app.run_worker", side_effect=fake_run_worker), patch(
                "vocr.cli.app.WARMUP_STAGGER_SECONDS", 0.0
            ):
                result = CliRunner().invoke(
                    app,
                    ["work-ready", "--limit", "2"],
                    env={"VOCR_HOME": str(vocr_home), "VOCR_PARALLEL_WORKERS": "2"},
                )

        self.assertEqual(result.exit_code, 0, result.output)
        self.assertEqual(set(starts), {"ta1", "ta2"})
        self.assertLess(abs(starts["ta1"] - starts["ta2"]), 0.04)

    def test_conflicting_parallel_task_waits_for_next_wave(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            vocr_home = root / ".vocr"
            store = MemoryLedger(vocr_home)
            append_dispatched(store, make_task("ta1", ["docs/**"]), root)
            append_dispatched(store, make_task("ta2", ["docs/readme.md"]), root)
            calls: list[str] = []

            def fake_run_worker(task_id: str, **_: object) -> None:
                calls.append(task_id)

            with patch("vocr.cli.app.run_worker", side_effect=fake_run_worker), patch(
                "vocr.cli.app.WARMUP_STAGGER_SECONDS", 0.0
            ):
                result = CliRunner().invoke(
                    app,
                    ["work-ready", "--limit", "2"],
                    env={"VOCR_HOME": str(vocr_home), "VOCR_PARALLEL_WORKERS": "2"},
                )

        self.assertEqual(result.exit_code, 0, result.output)
        self.assertEqual(calls, ["ta1"])
        self.assertIn("Waiting for claim", result.output)

    def test_parallel_worker_exception_does_not_stop_sibling(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            vocr_home = root / ".vocr"
            store = MemoryLedger(vocr_home)
            append_dispatched(store, make_task("ta1", ["docs/**"]), root)
            append_dispatched(store, make_task("ta2", ["src/api/**"]), root)
            calls: list[str] = []
            lock = threading.Lock()

            def fake_run_worker(task_id: str, **_: object) -> None:
                with lock:
                    calls.append(task_id)
                if task_id == "ta1":
                    raise RuntimeError("boom")

            with patch("vocr.cli.app.run_worker", side_effect=fake_run_worker), patch(
                "vocr.cli.app.WARMUP_STAGGER_SECONDS", 0.0
            ):
                result = CliRunner().invoke(
                    app,
                    ["work-ready", "--limit", "2"],
                    env={"VOCR_HOME": str(vocr_home), "VOCR_PARALLEL_WORKERS": "2"},
                )

        self.assertEqual(result.exit_code, 0, result.output)
        self.assertEqual(set(calls), {"ta1", "ta2"})
        self.assertIn("[T-ta1] Worker failed", result.output)
        self.assertIn("worked=1", result.output)

    def test_parallel_workers_stagger_after_first_submit(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            vocr_home = root / ".vocr"
            store = MemoryLedger(vocr_home)
            append_dispatched(store, make_task("ta1", ["docs/**"]), root)
            append_dispatched(store, make_task("ta2", ["src/api/**"]), root)
            sleeps: list[float] = []

            def fake_sleep(seconds: float) -> None:
                sleeps.append(seconds)

            with patch("vocr.cli.app.run_worker", return_value=None), patch(
                "vocr.cli.app.time.sleep", side_effect=fake_sleep
            ):
                result = CliRunner().invoke(
                    app,
                    ["work-ready", "--limit", "2"],
                    env={"VOCR_HOME": str(vocr_home), "VOCR_PARALLEL_WORKERS": "2"},
                )

        self.assertEqual(result.exit_code, 0, result.output)
        self.assertEqual(sleeps, [20.0])


if __name__ == "__main__":
    unittest.main()
