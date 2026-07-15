from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from vocr.beta.workers import ScriptedAttempt, ScriptedWorker
from vocr.models import AcceptanceCriterion, VocrTask


class BetaWorkerTests(unittest.TestCase):
    def test_scripted_worker_writes_patches_and_returns_codex_result(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            task = VocrTask(
                id="task-beta",
                slice_id="slice-beta",
                title="Beta",
                summary="Beta",
                scope=["app/**"],
                acceptance_criteria=[AcceptanceCriterion(text="ok")],
                tests=["manual"],
                worktree_path=root,
            )
            worker = ScriptedWorker([ScriptedAttempt(patches=[("app/core.py", "x = 1\n")], stdout="done")])

            result = worker.run_task(task)
            patched = (root / "app" / "core.py").read_text(encoding="utf-8")

        self.assertEqual(result.exit_code, 0)
        self.assertEqual(result.command, ["scripted-worker"])
        self.assertEqual(patched, "x = 1\n")


if __name__ == "__main__":
    unittest.main()
