from __future__ import annotations

import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from vocr.memory.ledger import MemoryLedger
from vocr.models import AcceptanceCriterion, LedgerEventType, ReviewComment, ReviewDecision, TaskStatus, VocrTask
from vocr.orchestration.codex_review import run_codex_review
from vocr.orchestration import workflow


class CodexReviewTests(unittest.TestCase):
    def _task(self, worktree: Path | None = None) -> VocrTask:
        return VocrTask(
            id="task-review",
            slice_id="slice-review",
            title="Review target",
            summary="Change the review path.",
            scope=["src/app.py"],
            non_goals=["Do not change docs."],
            acceptance_criteria=[AcceptanceCriterion(text="Review catches bugs")],
            tests=["manual review"],
            status=TaskStatus.dispatched,
            worktree_path=worktree,
        )

    def test_valid_json_review_returns_structured_comments_and_clean_prompt(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            response = {
                "schema_version": 1,
                "decision": "needs_changes",
                "summary": "One bug found.",
                "findings": [
                    {
                        "severity": "high",
                        "path": "src/app.py",
                        "line": 12,
                        "body": "Possible None access.",
                    }
                ],
            }
            captured: dict[str, str] = {}

            def fake_run(command: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
                captured["input"] = str(kwargs["input"])
                return subprocess.CompletedProcess(command, 0, stdout=json.dumps(response), stderr="")

            with patch("vocr.orchestration.codex_review.which", return_value="codex"), patch(
                "vocr.orchestration.codex_review.subprocess.run",
                side_effect=fake_run,
            ):
                comments = run_codex_review(self._task(Path(tmp)))

        self.assertEqual(len(comments), 2)
        self.assertEqual(comments[0].source, "codex-review")
        self.assertIn("Advisor decision: needs_changes", comments[0].body)
        self.assertEqual(comments[1].path, "src/app.py")
        self.assertEqual(comments[1].line, 12)
        self.assertIn("[high]", comments[1].body)
        self.assertIn('"scope"', captured["input"])
        self.assertNotIn("Scope: [", captured["input"])
        self.assertNotIn("['src/app.py']", captured["input"])

    def test_invalid_review_retries_once_then_falls_back_to_unstructured_blob(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            calls: list[str] = []

            def fake_run(command: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
                calls.append(str(kwargs["input"]))
                body = "not json" if len(calls) == 1 else "still not json"
                return subprocess.CompletedProcess(command, 0, stdout=body, stderr="")

            with patch("vocr.orchestration.codex_review.which", return_value="codex"), patch(
                "vocr.orchestration.codex_review.subprocess.run",
                side_effect=fake_run,
            ):
                comments = run_codex_review(self._task(Path(tmp)))

        self.assertEqual(len(calls), 2)
        self.assertIn("Validation error:", calls[1])
        self.assertEqual(len(comments), 1)
        self.assertEqual(comments[0].source, "codex-review-unstructured")
        self.assertEqual(comments[0].body, "still not json")

    def test_advisory_accepted_decision_does_not_accept_review_result(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ledger = MemoryLedger(Path(tmp) / ".vocr")
            task = self._task()
            ledger.append(LedgerEventType.task_created, task)
            advisor_comments = [
                ReviewComment(
                    source="codex-review",
                    body="Advisor decision: accepted. Looks good.",
                )
            ]

            with patch("vocr.orchestration.workflow.run_codex_review_with_notes", return_value=(advisor_comments, [])):
                review = workflow.review_task(ledger, task.id, codex_review=True)

        self.assertEqual(review.decision, ReviewDecision.needs_changes)
        self.assertIn("Manual review decision is required", "\n".join(review.required_changes))
        self.assertEqual(review.comments[-1].body, "Advisor decision: accepted. Looks good.")


if __name__ == "__main__":
    unittest.main()
