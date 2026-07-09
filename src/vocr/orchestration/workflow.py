from __future__ import annotations

import subprocess
import sys

from vocr.guardrails.scope_guard import ScopeGuard
from vocr.git.worktrees import GitWorktreeManager
from vocr.graph.graphify import GraphStore, RepoGraphBuilder
from vocr.memory.ledger import MemoryLedger
from vocr.models import (
    AcceptanceCriterion,
    LedgerEventType,
    ReviewDecision,
    ReviewResult,
    TaskStatus,
    TestRunResult,
    VisionSlice,
    VocrTask,
)
from vocr.orchestration.readiness import parse_request_sections


def create_vision(request: str) -> VisionSlice:
    sections = parse_request_sections(request)
    goal = sections.get("ziel", request.strip())
    acceptance = _split_items(sections.get("akzeptanz", ""))
    if not acceptance:
        acceptance = ["Work is split into small, reviewable tasks.", "No task is promoted before review acceptance."]
    return VisionSlice(
        request=request,
        goal=goal,
        assumptions=[
            "MVP vision created locally from explicit user-provided sections.",
            "No missing information is assumed; readiness gate must pass first.",
        ],
        acceptance_criteria=[
            AcceptanceCriterion(text=item, verified_by="vocr review")
            for item in acceptance
        ],
    )


def organize_slice(slice_item: VisionSlice, *, vocr_home: str = ".vocr") -> list[VocrTask]:
    sections = parse_request_sections(slice_item.request)
    context_query = infer_context_query(slice_item.goal)
    context_pack = build_context_pack(context_query, vocr_home=vocr_home)
    scope = _split_items(sections.get("arbeitsbereich", ""))
    non_goals = _split_items(sections.get("nicht_ziele", ""))
    tests = _split_items(sections.get("verifikation", ""))
    return [
        VocrTask(
            slice_id=slice_item.id,
            title="Implement first scoped slice",
            summary=f"Implement the smallest useful part of: {slice_item.goal}",
            scope=scope or [
                "Use only the explicitly requested repo area.",
                "Keep changes inside the task worktree.",
            ],
            non_goals=non_goals or ["Do not expand beyond the accepted VisionSlice."],
            acceptance_criteria=slice_item.acceptance_criteria,
            tests=tests or ["Run the verification explicitly approved in the VisionSlice."],
            context_query=context_query,
            context_pack=context_pack,
        )
    ]


def _split_items(text: str) -> list[str]:
    if not text.strip():
        return []
    normalized = text.replace("\n", ";")
    raw_items = []
    for chunk in normalized.split(";"):
        raw_items.extend(part.strip() for part in chunk.split(" / "))
    return [item.strip(" -.,") for item in raw_items if item.strip(" -.,")]


def infer_context_query(text: str) -> str:
    terms = [
        word.strip(".,:;!?()[]{}\"'").lower()
        for word in text.split()
        if len(word.strip(".,:;!?()[]{}\"'")) >= 4
    ]
    seen: list[str] = []
    for term in terms:
        if term not in seen:
            seen.append(term)
    return " ".join(seen[:5]) or "repo"


def build_context_pack(query: str, *, limit: int = 12, vocr_home: str = ".vocr") -> str:
    store = GraphStore(vocr_home)
    if not store.exists():
        store.save(RepoGraphBuilder(".").build())
    return store.context_pack(query=query, limit=limit)


def render_task_template(task: VocrTask) -> str:
    def bullets(items: list[str]) -> str:
        return "\n".join(f"- {item}" for item in items)

    criteria = [item.text for item in task.acceptance_criteria]
    return f"""VOCR Task: {task.title}

Task ID: {task.id}
Slice ID: {task.slice_id}

Summary:
{task.summary}

Scope:
{bullets(task.scope)}

Non-goals:
{bullets(task.non_goals)}

Acceptance criteria:
{bullets(criteria)}

Tests / verification:
{bullets(task.tests)}

Token-efficient context pack:
{task.context_pack or "Run `vocr graphify` and `vocr context` before broad file reads."}
"""


def dispatch_task(ledger: MemoryLedger, manager: GitWorktreeManager, task_id: str) -> VocrTask:
    task = ledger.get_task(task_id)
    if task is None:
        raise ValueError(f"Task not found: {task_id}")
    info = manager.create_for_task(task_id)
    ledger.append(
        LedgerEventType.task_dispatched,
        {
            "task_id": task.id,
            "branch_name": info.branch_name,
            "worktree_path": str(info.path),
        },
    )
    task.status = TaskStatus.dispatched
    task.branch_name = info.branch_name
    task.worktree_path = info.path
    return task


def review_task(
    ledger: MemoryLedger,
    task_id: str,
    *,
    decision: ReviewDecision | None = None,
    summary: str | None = None,
) -> ReviewResult:
    task = ledger.get_task(task_id)
    if task is None:
        review = ReviewResult(
            task_id=task_id,
            decision=ReviewDecision.blocked,
            summary="Task was not found in the ledger.",
            risks=["Cannot review a missing task."],
        )
        ledger.append(LedgerEventType.review_recorded, review)
        return review

    issues = ScopeGuard().validate_task(task)
    if task.status not in {TaskStatus.dispatched, TaskStatus.review_ready, TaskStatus.needs_changes}:
        issues.append(f"Task status is {task.status.value}; expected dispatched or review_ready.")

    git_status = None
    diff_summary = None
    if task.worktree_path:
        worktree_git = GitWorktreeManager(task.worktree_path)
        git_status = worktree_git.status_porcelain()
        uncommitted_diff = worktree_git.diff_stat()
        committed_diff = worktree_git.branch_diff_stat()
        diff_summary = f"Committed diff:\n{committed_diff}\n\nUncommitted diff:\n{uncommitted_diff}"
        changed_files = sorted(set(worktree_git.changed_files() + worktree_git.branch_diff_files()))
        issues.extend(ScopeGuard().validate_changed_files(task, changed_files))
        if decision == ReviewDecision.accepted and git_status != "clean":
            issues.append("Worktree has uncommitted changes; commit or discard them before accepted review.")

    test_results = run_task_checks(task)
    failed_checks = [result for result in test_results if result.status == "failed"]
    if failed_checks:
        issues.extend(f"Check failed: {result.command}" for result in failed_checks)

    if decision is None:
        decision = ReviewDecision.needs_changes
        issues.append("Manual review decision is required before a task can be accepted.")

    if decision == ReviewDecision.accepted and issues:
        decision = ReviewDecision.needs_changes

    review_summary = summary or (
        "Manual review accepted the task."
        if decision == ReviewDecision.accepted
        else "Review requires changes before promotion."
    )
    review = ReviewResult(
        task_id=task.id,
        decision=decision,
        summary=review_summary,
        risks=issues,
        required_changes=issues,
        tests_reviewed=task.tests,
        test_results=test_results,
        git_status=git_status,
        diff_summary=diff_summary,
        diff_files=changed_files if task.worktree_path else [],
    )
    ledger.append(LedgerEventType.review_recorded, review)
    return review


def promote_task(ledger: MemoryLedger, manager: GitWorktreeManager, task_id: str) -> None:
    task = ledger.get_task(task_id)
    if task is None:
        raise ValueError(f"Task not found: {task_id}")
    if task.status != TaskStatus.accepted:
        raise ValueError("Promote requires an accepted review.")
    if not task.branch_name:
        raise ValueError("Task has no branch to merge.")
    preflight_issues = manager.preflight_merge(task.branch_name)
    if preflight_issues:
        raise ValueError("Promote preflight failed: " + "; ".join(preflight_issues))
    manager.merge_task_branch(task.branch_name)
    ledger.append(LedgerEventType.task_promoted, {"task_id": task.id, "branch_name": task.branch_name})


def run_task_checks(task: VocrTask) -> list[TestRunResult]:
    results: list[TestRunResult] = []
    cwd = task.worktree_path
    for check in task.tests:
        command = normalize_check_command(check)
        if command is None:
            results.append(
                TestRunResult(
                    command=check,
                    status="manual",
                    output="No safe automatic command mapped for this check.",
                )
            )
            continue
        completed = subprocess.run(
            command,
            cwd=cwd,
            text=True,
            capture_output=True,
            check=False,
            timeout=300,
        )
        output = "\n".join(part for part in [completed.stdout.strip(), completed.stderr.strip()] if part)
        results.append(
            TestRunResult(
                command=" ".join(command),
                status="passed" if completed.returncode == 0 else "failed",
                exit_code=completed.returncode,
                output=output[-2000:],
            )
        )
    return results


def normalize_check_command(check: str) -> list[str] | None:
    lowered = check.lower()
    if "compile" in lowered or "syntax" in lowered:
        return [sys.executable, "-m", "compileall", "src"]
    if lowered.strip() in {"pytest", "python -m pytest"} or "pytest" in lowered:
        return [sys.executable, "-m", "pytest"]
    return None
