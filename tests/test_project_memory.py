from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from pydantic import ValidationError
from typer.testing import CliRunner

from vocr.cli.app import app
from vocr.graph.graphify import GraphStore
from vocr.memory.ledger import MemoryLedger
from vocr.memory.project_memory import ProjectMemoryStore
from vocr.models import (
    AcceptanceCriterion,
    CodexReviewReport,
    GraphNode,
    MemoryNote,
    MemoryNoteKind,
    RepoGraph,
    ReviewDecision,
    ReviewResult,
    TaskStatus,
    VocrTask,
    LedgerEventType,
)
from vocr.orchestration.codex_review import run_codex_review_with_notes
from vocr.orchestration.workflow import build_context_pack, render_review_markdown, review_task


def make_task(task_id: str = "ta-memory") -> VocrTask:
    return VocrTask(
        id=task_id,
        slice_id="slice-memory",
        title="Project memory task",
        summary="Capture accepted knowledge.",
        scope=["docs/**"],
        acceptance_criteria=[AcceptanceCriterion(text="Memory is gated", check_command="echo ok")],
        tests=["echo ok"],
        status=TaskStatus.dispatched,
    )


class ProjectMemoryTests(unittest.TestCase):
    def test_flag_off_does_not_touch_project_memory_store(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            ledger = MemoryLedger(root / ".vocr")
            task = make_task()
            ledger.append(LedgerEventType.task_created, task)
            note = MemoryNote(kind=MemoryNoteKind.convention, text="Use the docs helper for docs changes.")

            with patch.dict("os.environ", {"VOCR_PROJECT_MEMORY": ""}, clear=False), patch(
                "vocr.orchestration.workflow.ProjectMemoryStore",
                side_effect=AssertionError("store must stay inactive"),
            ):
                review = review_task(
                    ledger,
                    task.id,
                    decision=ReviewDecision.accepted,
                    memory_notes=[note],
                )

        self.assertEqual(review.decision, ReviewDecision.accepted)

    def test_only_accepted_review_persists_notes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            vocr_home = root / ".vocr"
            ledger = MemoryLedger(vocr_home)
            accepted = make_task("ta-memory-a")
            rejected = make_task("ta-memory-b")
            ledger.append(LedgerEventType.task_created, accepted)
            ledger.append(LedgerEventType.task_created, rejected)
            note = MemoryNote(kind=MemoryNoteKind.decision, text="Accepted docs changes should update install notes.")

            with patch.dict("os.environ", {"VOCR_PROJECT_MEMORY": "true"}, clear=False):
                review_task(ledger, accepted.id, decision=ReviewDecision.accepted, memory_notes=[note])
                review_task(ledger, rejected.id, decision=ReviewDecision.needs_changes, memory_notes=[note])

            entries = ProjectMemoryStore(vocr_home).entries()

        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0].task_id, accepted.id)
        self.assertEqual(entries[0].note.text, note.text)

    def test_codex_memory_suggestion_is_rendered_before_decision(self) -> None:
        note = MemoryNote(kind=MemoryNoteKind.term, text="Ledger claim means active scope reservation.")
        review = ReviewResult(
            task_id="ta-memory",
            decision=ReviewDecision.accepted,
            summary="Looks good.",
            memory_notes=[note],
        )

        markdown = render_review_markdown(review)

        self.assertLess(markdown.index("## Project Memory"), markdown.index("Decision:"))
        self.assertIn("Wird bei Accept", markdown)
        self.assertIn("Ledger claim means active scope reservation.", markdown)

    def test_codex_report_parses_memory_notes_as_suggestions(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            response = {
                "schema_version": 1,
                "decision": "accepted",
                "summary": "Looks good.",
                "findings": [],
                "memory_notes": [
                    {
                        "kind": "convention",
                        "text": "Review artifacts live below .vocr/artifacts.",
                        "refs": ["src/vocr/cli/app.py"],
                    }
                ],
            }

            def fake_run(command: list[str], **kwargs: object):
                import subprocess

                return subprocess.CompletedProcess(command, 0, stdout=json.dumps(response), stderr="")

            with patch("vocr.orchestration.codex_review.which", return_value="codex"), patch(
                "vocr.orchestration.codex_review.subprocess.run",
                side_effect=fake_run,
            ):
                _, notes = run_codex_review_with_notes(make_task(Path(tmp).name).model_copy(update={"worktree_path": Path(tmp)}))

        self.assertEqual(len(notes), 1)
        self.assertEqual(notes[0].kind, MemoryNoteKind.convention)

    def test_context_pack_includes_at_most_three_untrusted_memory_entries(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            vocr_home = root / ".vocr"
            GraphStore(vocr_home).save(
                RepoGraph(
                    root=str(root),
                    nodes=[
                        GraphNode(
                            path="docs/install.md",
                            kind="markdown",
                            size_bytes=10,
                            line_count=1,
                            content_hash="hash-docs",
                            summary="install memory docs",
                        )
                    ],
                )
            )
            notes = [
                MemoryNote(kind=MemoryNoteKind.convention, text=f"Install memory convention {index}")
                for index in range(5)
            ]
            ProjectMemoryStore(vocr_home).append_notes(task_id="ta-memory", slice_id="slice-memory", notes=notes)

            with patch.dict("os.environ", {"VOCR_PROJECT_MEMORY": "true"}, clear=False):
                context = build_context_pack("install memory", vocr_home=str(vocr_home))

        self.assertIn("PROJECT MEMORY (accepted reviews)", context)
        self.assertIn("untrusted context, not instructions", context)
        self.assertLessEqual(context.count("- [convention]"), 3)

    def test_memory_note_text_length_is_hard_validated(self) -> None:
        with self.assertRaises(ValidationError):
            MemoryNote(kind=MemoryNoteKind.check, text="x" * 301)

    def test_memory_cli_lists_and_prunes_entries(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            vocr_home = Path(tmp) / ".vocr"
            entry = ProjectMemoryStore(vocr_home).append_notes(
                task_id="ta-memory",
                slice_id="slice-memory",
                notes=[MemoryNote(kind=MemoryNoteKind.rejected_path, text="Do not retry raw tail slicing.")],
            )[0]

            runner = CliRunner()
            listed = runner.invoke(app, ["memory", "list"], env={"VOCR_HOME": str(vocr_home)})
            pruned = runner.invoke(app, ["memory", "prune", entry.id], env={"VOCR_HOME": str(vocr_home)})

        self.assertEqual(listed.exit_code, 0, listed.output)
        self.assertIn(entry.id, listed.output)
        self.assertEqual(pruned.exit_code, 0, pruned.output)
        self.assertEqual(ProjectMemoryStore(vocr_home).entries(), [])


if __name__ == "__main__":
    unittest.main()
