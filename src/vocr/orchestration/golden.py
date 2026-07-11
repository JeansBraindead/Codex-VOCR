from __future__ import annotations

import subprocess
import tempfile
from pathlib import Path

from vocr.codex.stub_worker import StubWorker
from vocr.git.worktrees import GitWorktreeManager
from vocr.memory.ledger import MemoryLedger
from vocr.models import (
    AcceptanceCriterion,
    GoldenEvalResult,
    GoldenEvalStep,
    LedgerEventType,
    ReviewDecision,
    RunTelemetry,
    VocrTask,
)
from vocr.orchestration.workflow import dispatch_task, promote_task, render_task_template, review_task
from vocr.telemetry import extract_token_usage


def run_golden_eval() -> GoldenEvalResult:
    steps: list[GoldenEvalStep] = []
    with tempfile.TemporaryDirectory() as tmp:
        repo = Path(tmp) / "repo"
        repo.mkdir()
        _git(repo, "init")
        _git(repo, "config", "user.email", "vocr@example.invalid")
        _git(repo, "config", "user.name", "VOCR Golden Eval")
        (repo / "README.md").write_text("# golden\n", encoding="utf-8")
        _git(repo, "add", "README.md")
        _git(repo, "commit", "-m", "initial")

        ledger = MemoryLedger(Path(tmp) / ".vocr")
        task = VocrTask(
            id="task-golden",
            slice_id="slice-golden",
            title="Golden gate task",
            summary="LLM-free gate evaluation task.",
            scope=["README.md"],
            acceptance_criteria=[AcceptanceCriterion(text="Gate behavior is enforced.")],
            tests=["Manual golden gate check"],
        )
        ledger.append(LedgerEventType.task_created, task)
        dispatched = dispatch_task(
            ledger,
            GitWorktreeManager(repo_root=repo, worktree_root=Path(tmp) / "worktrees"),
            task.id,
        )
        steps.append(GoldenEvalStep(name="dispatch", passed=dispatched.worktree_path is not None))

        prompt = render_task_template(dispatched)
        worker_result = StubWorker().run(dispatched, prompt)
        usage = extract_token_usage(worker_result.stdout)
        if usage is None:
            raise RuntimeError("Stub worker did not emit parseable token usage.")
        ledger.append(
            LedgerEventType.telemetry_recorded,
            RunTelemetry(
                provider="stub-worker",
                model="none",
                slice_id=dispatched.slice_id,
                task_id=dispatched.id,
                agent="stub-worker",
                command=worker_result.command,
                token_usage=usage,
            ),
        )
        ledger.append(LedgerEventType.task_worker_ran, worker_result)
        steps.append(
            GoldenEvalStep(
                name="actual-token-metering",
                passed=usage is not None and usage.source == "actual" and bool(usage.total_tokens),
            )
        )

        try:
            promote_task(ledger, GitWorktreeManager(repo_root=repo), task.id)
            blocked_before_review = False
        except ValueError:
            blocked_before_review = True
        steps.append(GoldenEvalStep(name="promote-before-review-blocked", passed=blocked_before_review))

        review = review_task(
            ledger,
            task.id,
            decision=ReviewDecision.accepted,
            summary="Golden eval accepted deterministic stub output.",
        )
        steps.append(GoldenEvalStep(name="accepted-review", passed=review.decision == ReviewDecision.accepted))

        promote_task(ledger, GitWorktreeManager(repo_root=repo), task.id)
        promoted = ledger.get_task(task.id)
        steps.append(
            GoldenEvalStep(
                name="promote-after-review-allowed",
                passed=promoted is not None and promoted.status.value == "promoted",
            )
        )

    return GoldenEvalResult(passed=all(step.passed for step in steps), steps=steps)


def _git(repo: Path, *args: str) -> None:
    result = subprocess.run(["git", *args], cwd=repo, text=True, capture_output=True, check=False)
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or result.stdout.strip())
