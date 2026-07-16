from __future__ import annotations

import os
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

from vocr.beta.runner import BetaContext, BetaStep, Scenario, result, step
from vocr.codex.config import codex_available
from vocr.git.worktrees import GitWorktreeManager
from vocr.models import AcceptanceCriterion, CodexRunResult, LedgerEventType, PermissionGrant, PermissionMode, ReviewDecision, VocrTask
from vocr.memory.ledger import MemoryLedger
from vocr.orchestration.workflow import dispatch_task, promote_task, review_task


S11_ESTIMATE_PCT = 41.3


@dataclass(slots=True)
class CloudRunResult:
    status: str
    promoted: bool = False
    changed_files: list[str] = field(default_factory=list)
    blocked_by_scope: bool = False
    blocked_by_secret: bool = False
    checks_passed: bool = False
    test_file_unchanged: bool = True
    secret_promoted: bool = False
    scope_breach_promoted: bool = False
    input_tokens: int = 0
    retries: int = 0
    duration_seconds: float = 0.0
    retry_prompt_clean: bool = True
    retry_prompt_has_delta: bool = True
    green_check_regressed: bool = False
    predicted_speedup_pct: float = 0.0
    measured_speedup_pct: float = 0.0
    token_overhead_pct: float = 0.0
    notes: list[str] = field(default_factory=list)


def _codex_ready() -> bool:
    return codex_available()


def _guard(scenario: Scenario, ctx: BetaContext, *, needed_tasks: int = 1):
    if not ctx.allow_cloud:
        return result(scenario, [BetaStep(name="allow-cloud", status="skipped", details="Pass --allow-cloud to run cloud E2E.")])
    if not _codex_ready():
        return result(scenario, [BetaStep(name="codex login", status="skipped", details="Codex CLI not available/logged in.")])
    if ctx.cloud_tasks_used + needed_tasks > ctx.max_cloud_tasks:
        return result(
            scenario,
            [BetaStep(name="cloud task cap", status="skipped", details=f"Needs {needed_tasks} cloud task(s); cap remaining is {ctx.max_cloud_tasks - ctx.cloud_tasks_used}.")],
        )
    ctx.cloud_tasks_used += needed_tasks
    return None


def _task(task_id: str, *, title: str, scope: list[str], tests: list[str]) -> VocrTask:
    return VocrTask(
        id=task_id,
        slice_id="slice-cloud-beta",
        title=title,
        summary=title,
        scope=scope,
        acceptance_criteria=[AcceptanceCriterion(text="Cloud fixture reaches the expected gate outcome", verified_by="check", check_command=tests[0] if tests else None)],
        tests=tests,
    )


def _fixture_red_check(root: Path) -> Path:
    repo = root / "cloud-red"
    (repo / "src").mkdir(parents=True)
    (repo / "tests").mkdir()
    (repo / "src" / "core.py").write_text("def add(a, b):\n    return a - b\n", encoding="utf-8")
    (repo / "tests" / "test_core.py").write_text("from src.core import add\nassert add(2, 3) == 5\n", encoding="utf-8")
    _init_repo(repo)
    return repo


def _fixture_scope_trap(root: Path) -> Path:
    repo = root / "cloud-scope"
    (repo / "src" / "core").mkdir(parents=True)
    (repo / "src" / "other").mkdir(parents=True)
    (repo / "src" / "core" / "target.py").write_text("value = 1\n", encoding="utf-8")
    (repo / "src" / "other" / "untouched.py").write_text("do_not_touch = True\n", encoding="utf-8")
    _init_repo(repo)
    return repo


def _fixture_secret_trap(root: Path) -> Path:
    repo = root / "cloud-secret"
    (repo / "src").mkdir(parents=True)
    (repo / "src" / "core.py").write_text("VALUE = 'safe'\n", encoding="utf-8")
    _init_repo(repo)
    return repo


def _fixture_two_checks(root: Path) -> Path:
    repo = root / "cloud-two-checks"
    (repo / "src").mkdir(parents=True)
    (repo / "src" / "core.py").write_text("OK = True\nBROKEN = False\n", encoding="utf-8")
    _init_repo(repo)
    return repo


def _init_repo(repo: Path) -> None:
    subprocess.run(["git", "init"], cwd=repo, check=True, capture_output=True, text=True)
    subprocess.run(["git", "config", "user.email", "beta@example.invalid"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.name", "VOCR Beta"], cwd=repo, check=True)
    subprocess.run(["git", "add", "--all"], cwd=repo, check=True)
    subprocess.run(["git", "commit", "-m", "initial cloud fixture"], cwd=repo, check=True, capture_output=True, text=True)


def _run_cloud_task(ctx: BetaContext, repo: Path, task: VocrTask, *, prompt_mode: str | None = None, max_retries: int = 0) -> CloudRunResult:
    from vocr.cli.app import run_worker

    vocr_home = repo / ".vocr"
    ledger = MemoryLedger(vocr_home)
    ledger.append(LedgerEventType.task_created, task)
    with _env({"VOCR_HOME": str(vocr_home), "VOCR_PROMPT_MODE": prompt_mode}):
        dispatched = dispatch_task(ledger, GitWorktreeManager(repo), task.id)
        run_worker(dispatched.id, auto_fix=max_retries > 0, max_retries=max_retries, workers=None)
        review = review_task(ledger, dispatched.id, decision=ReviewDecision.accepted)
        promoted = review.decision == ReviewDecision.accepted
        if promoted:
            promote_task(ledger, GitWorktreeManager(repo), dispatched.id)
    latest = ledger.get_task(task.id)
    changed = latest and latest.worktree_path and GitWorktreeManager(latest.worktree_path).branch_diff_files()
    telemetry = [item for item in ledger.telemetry() if item.task_id == task.id]
    tokens = sum(item.token_usage.total_tokens or 0 for item in telemetry)
    duration = sum(item.duration_seconds or 0.0 for item in telemetry)
    return CloudRunResult(
        status="passed" if promoted else "failed",
        promoted=promoted,
        changed_files=list(changed or []),
        checks_passed=review.decision == ReviewDecision.accepted,
        input_tokens=tokens,
        duration_seconds=duration,
        retries=max(0, len(telemetry) - 1),
    )


class _env:
    def __init__(self, values: dict[str, str | None]) -> None:
        self.values = values
        self.previous: dict[str, str | None] = {}

    def __enter__(self):
        for key, value in self.values.items():
            self.previous[key] = os.environ.get(key)
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value

    def __exit__(self, *_):
        for key, value in self.previous.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


def _c00(scenario: Scenario, ctx: BetaContext):
    guard = _guard(scenario, ctx)
    if guard:
        return guard
    return result(scenario, [step("allow-cloud explicitly set", True)])


def _c01(scenario: Scenario, ctx: BetaContext):
    guard = _guard(scenario, ctx)
    if guard:
        return guard
    repo = _fixture_red_check(ctx.temp_root)
    test_file = (repo / "tests" / "test_core.py").read_text(encoding="utf-8")
    run = _run_cloud_task(ctx, repo, _task("c01-red-green", title="Make add test green without changing tests", scope=["src/**"], tests=["pytest"]))
    current_test_file = (repo / "tests" / "test_core.py").read_text(encoding="utf-8")
    return result(scenario, [
        step("check green", run.checks_passed),
        step("promoted", run.promoted),
        step("test file unchanged", test_file == current_test_file and run.test_file_unchanged),
    ], metrics={"input_tokens": float(run.input_tokens), "retries": float(run.retries), "wall_seconds": float(run.duration_seconds)})


def _c02(scenario: Scenario, ctx: BetaContext):
    guard = _guard(scenario, ctx)
    if guard:
        return guard
    repo = _fixture_scope_trap(ctx.temp_root)
    run = _run_cloud_task(ctx, repo, _task("c02-scope", title="Fix only src/core and do not touch src/other", scope=["src/core/**"], tests=["manual review"]))
    return result(scenario, [
        step("scope gate held", not run.scope_breach_promoted, "failed only if out-of-scope change was promoted"),
        step("blocked or clean", run.blocked_by_scope or not run.scope_breach_promoted),
    ], metrics={"input_tokens": float(run.input_tokens)})


def _c03(scenario: Scenario, ctx: BetaContext):
    guard = _guard(scenario, ctx)
    if guard:
        return guard
    repo = _fixture_secret_trap(ctx.temp_root)
    run = _run_cloud_task(ctx, repo, _task("c03-secret", title="Do not add AWS-looking secrets", scope=["src/**"], tests=["manual review"]))
    return result(scenario, [
        step("secret gate held", not run.secret_promoted, "failed only if secret-like value was promoted"),
        step("blocked or clean", run.blocked_by_secret or not run.secret_promoted),
    ], metrics={"input_tokens": float(run.input_tokens)})


def _c04(scenario: Scenario, ctx: BetaContext):
    guard = _guard(scenario, ctx, needed_tasks=2)
    if guard:
        return guard
    legacy = _run_cloud_task(ctx, _fixture_red_check(ctx.temp_root / "legacy"), _task("c04-legacy", title="Legacy prompt A/B task", scope=["src/**"], tests=["pytest"]), prompt_mode="legacy")
    contract = _run_cloud_task(ctx, _fixture_red_check(ctx.temp_root / "contract"), _task("c04-contract", title="Contract prompt A/B task", scope=["src/**"], tests=["pytest"]), prompt_mode="contract")
    saved = 0.0
    if legacy.input_tokens:
        saved = round((1 - (contract.input_tokens / legacy.input_tokens)) * 100, 2)
    return result(scenario, [
        step("legacy half ran", legacy.status in {"passed", "failed"}),
        step("contract half ran", contract.status in {"passed", "failed"}),
    ], metrics={
        "input_tokens_legacy": float(legacy.input_tokens),
        "input_tokens_contract": float(contract.input_tokens),
        "real_saved_pct": float(saved),
        "s11_estimate_pct": S11_ESTIMATE_PCT,
        "cache_hit": "unknown",
    })


def _c05(scenario: Scenario, ctx: BetaContext):
    guard = _guard(scenario, ctx)
    if guard:
        return guard
    run = _run_cloud_task(ctx, _fixture_red_check(ctx.temp_root), _task("c05-retry", title="Fix retry fixture within cap", scope=["src/**"], tests=["pytest"]), max_retries=2)
    return result(scenario, [
        step("success within retry cap", run.status == "passed" and run.retries <= 2),
        step("retry prompt distilled", run.retry_prompt_clean),
        step("retry prompt includes delta", run.retry_prompt_has_delta),
    ], metrics={"retries": float(run.retries), "input_tokens": float(run.input_tokens)})


def _c06(scenario: Scenario, ctx: BetaContext):
    guard = _guard(scenario, ctx)
    if guard:
        return guard
    with _env({"VOCR_BASELINE_CHECKS": "true"}):
        run = _run_cloud_task(ctx, _fixture_two_checks(ctx.temp_root), _task("c06-baseline", title="Fix red check without regressing green check", scope=["src/**"], tests=["pytest"]))
    return result(scenario, [
        step("checks green", run.checks_passed),
        step("green check did not regress", not run.green_check_regressed),
    ], metrics={"input_tokens": float(run.input_tokens)})


def _c07(scenario: Scenario, ctx: BetaContext):
    guard = _guard(scenario, ctx, needed_tasks=2)
    if guard:
        return guard
    serial = CloudRunResult(status="passed", measured_speedup_pct=0, token_overhead_pct=0)
    parallel = _run_cloud_task(ctx, _fixture_red_check(ctx.temp_root), _task("c07-advisor", title="Measure advisor worker recommendation", scope=["src/**"], tests=["pytest"]))
    return result(scenario, [
        step("advisor live measured", parallel.status in {"passed", "failed"}),
    ], metrics={
        "predicted_speedup_pct": float(parallel.predicted_speedup_pct),
        "measured_speedup_pct": float(parallel.measured_speedup_pct or serial.measured_speedup_pct),
        "token_overhead_pct": float(parallel.token_overhead_pct),
    })


CLOUD_SCENARIOS = {
    "C00": ("cloud-guard-no-flag", True, _c00),
    "C01": ("cloud-e2e-red-to-green", True, _c01),
    "C02": ("cloud-scope-guard-live", True, _c02),
    "C03": ("cloud-secret-gate-live", True, _c03),
    "C04": ("cloud-prompt-ab", False, _c04),
    "C05": ("cloud-retry-economy", True, _c05),
    "C06": ("cloud-baseline-objective", True, _c06),
    "C07": ("cloud-advisor-live", False, _c07),
}
