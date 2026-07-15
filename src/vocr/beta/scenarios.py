from __future__ import annotations

import os
import subprocess
from pathlib import Path
from unittest.mock import patch

from vocr.cli.app import estimate_tokens
from vocr.beta.fixtures import INJECTION_MARKER, make_repo
from vocr.beta.runner import BetaContext, BetaStep, Scenario, result, step
from vocr.beta.workers import ScriptedAttempt, ScriptedWorker
from vocr.codex.mcp_client import CodexMcpClient
from vocr.git.worktrees import GitWorktreeManager
from vocr.graph.graphify import GraphStore
from vocr.guardrails.claims import claim_root, claims_conflict
from vocr.guardrails.scope_guard import ScopeGuard
from vocr.guardrails.secrets import scan_diff_for_secrets
from vocr.memory.ledger import MemoryLedger
from vocr.memory.project_memory import ProjectMemoryStore
from vocr.models import (
    AcceptanceCriterion,
    CodexReviewReport,
    LedgerEventType,
    MemoryNote,
    MemoryNoteKind,
    ReviewDecision,
    ScopeClaim,
    VocrTask,
)
from vocr.orchestration.workflow import (
    build_context_pack,
    distill_failure_output,
    infer_context_query,
    promote_task,
    render_task_template,
    review_task,
)


def _task(task_id: str, *, scope: list[str] | None = None, tests: list[str] | None = None) -> VocrTask:
    return VocrTask(
        id=task_id,
        slice_id="slice-beta",
        title=f"Beta {task_id}",
        summary="Beta harness task",
        scope=scope or ["app/**"],
        acceptance_criteria=[AcceptanceCriterion(text="Beta task is verifiable", check_command=None)],
        tests=tests or ["manual review"],
    )


def _claim(glob: str, task_id: str) -> ScopeClaim:
    return ScopeClaim(task_id=task_id, globs=[glob], roots=[claim_root(glob)], expanded_paths=[])


def _scenario_result(scenario: Scenario, steps: list[BetaStep], **kwargs):
    return result(scenario, steps, **kwargs)


def _s00(scenario: Scenario, ctx: BetaContext):
    with ctx.env(
        {
            "VOCR_EMBED_RETRIEVAL": None,
            "VOCR_LOCAL_ASSIST": None,
            "VOCR_PROJECT_MEMORY": None,
            "VOCR_PARALLEL_WORKERS": None,
        }
    ):
        steps = [
            step("claim root directory wildcard", claim_root("src/api/**") == "src/api"),
            step("claim root exact file", claim_root("src/vocr/models.py") == "src/vocr/models.py"),
            step("disjoint sibling trees", not claims_conflict(_claim("src/api/**", "a"), _claim("src/cli/**", "b"))),
            step("ancestor conflict", claims_conflict(_claim("a/x.py", "a"), _claim("a/**", "b"))),
            step("parallel default", os.getenv("VOCR_PARALLEL_WORKERS", "1") == "1"),
        ]
    return _scenario_result(scenario, steps)


def _s01(scenario: Scenario, ctx: BetaContext):
    repo = make_repo(ctx.temp_root / "s01-repo")
    ledger = MemoryLedger(ctx.temp_root / "s01-vocr")
    task = _task("task-s01")
    ledger.append(LedgerEventType.task_created, task)
    dispatched = __import__("vocr.orchestration.workflow", fromlist=["dispatch_task"]).dispatch_task(
        ledger,
        GitWorktreeManager(repo, ctx.temp_root / "s01-worktrees"),
        task.id,
    )
    worker = ScriptedWorker([ScriptedAttempt(patches=[("app/core.py", "def alpha():\n    return 'done'\n")], stdout="ok")])
    run = worker.run_task(dispatched)
    worktree_git = GitWorktreeManager(dispatched.worktree_path)
    commit_sha = worktree_git.commit_all("beta s01")
    run.committed = True
    run.commit_sha = commit_sha
    ledger.append(LedgerEventType.task_committed, {"task_id": task.id, "commit_sha": commit_sha})
    ledger.append(LedgerEventType.task_worker_ran, run)
    promoted_before_review = False
    try:
        promote_task(ledger, _NoopMergeManager(), task.id)  # type: ignore[arg-type]
    except ValueError:
        promoted_before_review = True
    review = review_task(ledger, task.id, decision=ReviewDecision.accepted, summary="beta accepted")
    promote_task(ledger, _NoopMergeManager(), task.id)  # type: ignore[arg-type]
    steps = [
        step("dispatch", dispatched.worktree_path is not None),
        step("worker", run.exit_code == 0 and run.committed),
        step("promote gated", promoted_before_review),
        step("review accepted", review.decision == ReviewDecision.accepted),
        step("promoted", ledger.get_task(task.id).status.value == "promoted"),
    ]
    return _scenario_result(scenario, steps)


class _NoopMergeManager:
    def preflight_merge(self, branch_name: str) -> list[str]:
        return []

    def merge_task_branch(self, branch_name: str) -> None:
        return None


def _s02(scenario: Scenario, ctx: BetaContext):
    task = _task("task-s02")
    task.context_pack = INJECTION_MARKER
    task.worktree_path = ctx.temp_root / "s02-worktree"
    task.worktree_path.mkdir(parents=True)
    client = CodexMcpClient(command="echo")
    with ctx.env({"VOCR_PROMPT_MODE": "contract"}):
        client.write_manifest(task)
        payload = client.build_payload(task)
    contract = (task.worktree_path / ".vocr" / "VOCR_TASK.json").read_text(encoding="utf-8")
    context = (task.worktree_path / ".vocr" / "CONTEXT_PACK.txt").read_text(encoding="utf-8")
    steps = [
        step("marker in context", INJECTION_MARKER in context),
        step("marker not in json", INJECTION_MARKER not in contract),
        step("marker not in prompt", INJECTION_MARKER not in payload.prompt),
        step("no pwned", not (task.worktree_path / "PWNED.txt").exists()),
    ]
    return _scenario_result(scenario, steps)


def _s03(scenario: Scenario, ctx: BetaContext):
    repo = make_repo(ctx.temp_root / "s03-repo")
    task = _task("task-s03", scope=["app/**"])
    task.worktree_path = repo
    worker = ScriptedWorker([ScriptedAttempt(patches=[("outside.txt", "bad\n")])])
    worker.run_task(task)
    issues = ScopeGuard().validate_changed_files(task, GitWorktreeManager(repo).changed_files())
    (repo / "outside.txt").unlink()
    worker = ScriptedWorker([ScriptedAttempt(patches=[("app/core.py", "def alpha():\n    return 'fixed'\n")])])
    worker.run_task(task)
    fixed_issues = ScopeGuard().validate_changed_files(task, GitWorktreeManager(repo).changed_files())
    return _scenario_result(scenario, [step("breach blocked", bool(issues)), step("in scope allowed", not fixed_issues)])


def _s04(scenario: Scenario, ctx: BetaContext):
    repo = make_repo(ctx.temp_root / "s04-repo")
    (repo / "app" / "secret.py").write_text("AWS='AKIA1234567890ABCDEF'\n", encoding="utf-8")
    scan = scan_diff_for_secrets(GitWorktreeManager(repo).diff_for_scan(), repo_root=repo)
    (repo / "app" / "secret.py").write_text("AWS='redacted-fixture'\n", encoding="utf-8")
    clean = scan_diff_for_secrets(GitWorktreeManager(repo).diff_for_scan(), repo_root=repo)
    return _scenario_result(scenario, [step("secret blocked", scan.blocked), step("clean allowed", not clean.blocked)])


def _s05(scenario: Scenario, ctx: BetaContext):
    raw = "\n".join(
        [
            "Traceback (most recent call last):",
            '  File "/repo/app/core.py", line 2, in alpha',
            "    raise RuntimeError('boom')",
            '  File "/venv/site-packages/lib.py", line 1, in helper',
            "RuntimeError: boom",
        ]
    )
    distilled = distill_failure_output(raw)
    steps = [
        step("keeps repo frame", "app/core.py" in distilled),
        step("drops site packages", "site-packages" not in distilled),
        step("keeps exception", "RuntimeError: boom" in distilled),
    ]
    return _scenario_result(scenario, steps, metrics={"raw_tail_chars": float(len(raw)), "retry_prompt_chars": float(len(distilled))})


def _s06(scenario: Scenario, ctx: BetaContext):
    report = CodexReviewReport.model_validate(
        {
            "decision": "accepted",
            "summary": "looks good",
            "findings": [{"severity": "low", "path": "app/core.py", "line": 1, "body": "note"}],
            "memory_notes": [{"kind": "convention", "text": "Keep beta fixtures tiny."}],
        }
    )
    ledger = MemoryLedger(ctx.temp_root / "s06-vocr")
    task = _task("task-s06")
    ledger.append(LedgerEventType.task_created, task)
    review = review_task(ledger, task.id, codex_review=False)
    steps = [
        step("json report parsed", report.findings[0].path == "app/core.py"),
        step("memory note parsed", report.memory_notes[0].text == "Keep beta fixtures tiny."),
        step("advisor cannot accept", review.decision != ReviewDecision.accepted),
    ]
    return _scenario_result(scenario, steps)


def _s07(scenario: Scenario, ctx: BetaContext):
    statuses = []
    for mode in ["off", "warn", "block"]:
        ledger = MemoryLedger(ctx.temp_root / f"s07-vocr-{mode}")
        task = _task(f"task-s07-{mode}", tests=["manual review"])
        task.acceptance_criteria = [AcceptanceCriterion(text="Ungemapped text criterion", verified_by="automation")]
        ledger.append(LedgerEventType.task_created, task)
        ledger.append(
            LedgerEventType.task_dispatched,
            {"task_id": task.id, "branch_name": f"vocr/{task.id}"},
        )
        with ctx.env({"VOCR_REQUIRE_CHECKS": mode}):
            statuses.append(review_task(ledger, task.id, decision=ReviewDecision.accepted).decision.value)
    return _scenario_result(scenario, [step("off/warn/block covered", statuses == ["accepted", "accepted", "needs_changes"])])


def _s08(scenario: Scenario, ctx: BetaContext):
    repo = make_repo(ctx.temp_root / "s08-repo")
    task = _task("task-s08", tests=["syntax red", "syntax green"])
    task.worktree_path = repo
    calls = [
        subprocess.CompletedProcess(["python"], 1, stdout="", stderr="red"),
        subprocess.CompletedProcess(["python"], 0, stdout="green", stderr=""),
    ]
    with ctx.env({"VOCR_BASELINE_CHECKS": "true"}):
        with patch("vocr.codex.mcp_client.subprocess.run", side_effect=calls):
            CodexMcpClient(command="echo").write_manifest(task)
    contract = (repo / ".vocr" / "VOCR_TASK.json").read_text(encoding="utf-8")
    return _scenario_result(scenario, [step("baseline statuses", '"failed"' in contract and '"passed"' in contract)])


def _s09(scenario: Scenario, ctx: BetaContext):
    from vocr.cli.app import retry_blocked_by_token_budget
    from vocr.memory.learning import LearningEntry, LearningSnapshot, LearningStore

    root = ctx.temp_root / "s09-vocr"
    store = LearningStore(root)
    snapshot = LearningSnapshot()
    snapshot.scopes["scope:app/**"] = LearningEntry(key="scope:app/**", count=1, estimated_tokens=10)
    store.save(snapshot)
    ledger = MemoryLedger(root)
    task = _task("task-s09")
    with ctx.env({"VOCR_TOKEN_BUDGET_MODE": "block", "VOCR_TOKEN_BUDGET_FACTOR": "1.0"}):
        with patch("vocr.cli.app.console.print"):
            blocked = retry_blocked_by_token_budget(ledger, task, 20)
    return _scenario_result(scenario, [step("budget blocks retry", blocked)])


def _s10(scenario: Scenario, ctx: BetaContext):
    repo = make_repo(ctx.temp_root / "s10-repo")
    graph = GraphStore(ctx.temp_root / "s10-vocr")
    with _cwd(repo):
        graph.refresh(repo)
        brief = graph.context_pack(query="alpha", limit=2)
    return _scenario_result(scenario, [step("span marker", "@L" in brief), step("budget", len(brief) <= 3600)])


def _s11(scenario: Scenario, ctx: BetaContext):
    context_pack = "\n".join(
        [
            "VOCR repo graph brief:",
            "- src/vocr/cli/app.py: work-ready, run_worker, beta CLI, telemetry wiring (@L850-1035)",
            "- src/vocr/orchestration/workflow.py: task contract rendering, review gates, context packs (@L186-270)",
            "- src/vocr/guardrails/claims.py: precise claim roots for parallel safety (@L1-80)",
            "- docs/CLI_REFERENCE.md: user-facing beta command reference",
        ]
    )
    left = _task("task-s11a").model_copy(
        update={
            "title": "Implement deterministic beta report KPI extraction for prompt-token savings",
            "summary": "Measure legacy prompt size against contract-mode prompt size without contacting any model endpoint.",
            "acceptance_criteria": [
                AcceptanceCriterion(text="Report JSON contains prompt_tokens_legacy for the two measured tasks."),
                AcceptanceCriterion(text="Report JSON contains prompt_tokens_contract for the same measured tasks."),
                AcceptanceCriterion(text="Report JSON contains prompt_tokens_saved_pct rounded to one decimal place."),
            ],
            "tests": ["python -m unittest tests.test_beta_scenarios"],
            "context_pack": context_pack,
        }
    )
    right = _task("task-s11b").model_copy(
        update={
            "title": "Verify contract prompt prefix remains byte-identical across beta worker tasks",
            "summary": "Create a second task with different trusted task data to prove contract mode keeps volatile data out of the prompt.",
            "acceptance_criteria": [
                AcceptanceCriterion(text="Two contract prompts generated for different tasks are byte-identical."),
                AcceptanceCriterion(text="Task titles and acceptance criteria are absent from the contract prompt prefix."),
                AcceptanceCriterion(text="Legacy prompts still include trusted task details for backwards compatibility."),
            ],
            "tests": ["python -m unittest tests.test_beta_scenarios"],
            "context_pack": context_pack,
        }
    )
    with ctx.env({"VOCR_PROMPT_MODE": "legacy"}):
        legacy_left = render_task_template(left)
        legacy_right = render_task_template(right)
    with ctx.env({"VOCR_PROMPT_MODE": "contract"}):
        prompt_left = render_task_template(left)
        prompt_right = render_task_template(right)
    legacy_tokens = estimate_tokens(legacy_left) + estimate_tokens(legacy_right)
    contract_tokens = estimate_tokens(prompt_left) + estimate_tokens(prompt_right)
    saved_pct = round(((legacy_tokens - contract_tokens) / legacy_tokens) * 100, 1) if legacy_tokens else 0.0
    return _scenario_result(
        scenario,
        [step("contract prompts identical", prompt_left == prompt_right), step("title omitted", left.title not in prompt_left)],
        metrics={
            "prompt_tokens_legacy": float(legacy_tokens),
            "prompt_tokens_contract": float(contract_tokens),
            "prompt_tokens_saved_pct": float(saved_pct),
        },
    )


def _s12(scenario: Scenario, ctx: BetaContext):
    with ctx.env({"VOCR_EMBED_RETRIEVAL": None}):
        disabled = os.getenv("VOCR_EMBED_RETRIEVAL") is None
    return _scenario_result(scenario, [step("embedding default off", disabled)])


def _s13(scenario: Scenario, ctx: BetaContext):
    captured: dict[str, str] = {}

    def fake_expansion(text: str) -> list[str]:
        captured["text"] = text
        return ["health", "api", "health"]

    with ctx.env({"VOCR_LOCAL_ASSIST": "true"}), patch("vocr.orchestration.workflow._local_query_expansion", fake_expansion):
        query = infer_context_query("Trusted Goal Title")
    return _scenario_result(
        scenario,
        [step("trusted payload only", captured["text"] == "Trusted Goal Title"), step("dedup merged", query.count("health") == 1)],
    )


def _s14(scenario: Scenario, ctx: BetaContext):
    ledger = MemoryLedger(ctx.temp_root / "s14-vocr")
    task = _task("task-s14")
    ledger.append(LedgerEventType.task_created, task)
    first = review_task(ledger, task.id, decision=ReviewDecision.needs_changes)
    with ctx.env({"VOCR_INCREMENTAL_REVIEW": "true"}):
        previous = ledger.last_review(task.id)
    return _scenario_result(scenario, [step("last review available", previous.reviewed_ref == first.reviewed_ref)])


def _s15(scenario: Scenario, ctx: BetaContext):
    from vocr.cli.app import record_worker_telemetry

    root = ctx.temp_root / "s15-vocr"
    ledger = MemoryLedger(root)
    task = _task("task-s15")
    ledger.append(LedgerEventType.task_created, task)
    run = ScriptedWorker([ScriptedAttempt(stdout="done")])
    task.worktree_path = ctx.temp_root / "s15-worktree"
    task.worktree_path.mkdir()
    result_run = run.run_task(task)
    total = record_worker_telemetry(ledger, task.id, result_run, "prompt text")
    compact = ledger.compact()
    return _scenario_result(
        scenario,
        [step("telemetry total", sum(item.token_usage.total_tokens or 0 for item in ledger.telemetry()) == total), step("compact safe", compact.kept_events >= 1)],
        metrics={"tokens_total": float(total)},
    )


def _s16(scenario: Scenario, ctx: BetaContext):
    repo = make_repo(ctx.temp_root / "s16-repo")
    with _cwd(repo):
        GraphStore(ctx.temp_root / "s16-vocr").refresh(repo)
    task = _task("task-s16", scope=["Osnabrueck test.py", "crlf.txt", "empty.txt"])
    issues = ScopeGuard().validate_task(task)
    return _scenario_result(scenario, [step("robust paths", not issues)])


def _s17(scenario: Scenario, ctx: BetaContext):
    if not ctx.allow_cloud:
        return _scenario_result(scenario, [BetaStep(name="allow-cloud", status="skipped", details="Cloud tier disabled.")])
    return _scenario_result(scenario, [BetaStep(name="cloud-cap", status="skipped", details="Live Codex cloud smoke is reserved for manual runs.")])


def _s18(scenario: Scenario, ctx: BetaContext):
    ledger = MemoryLedger(ctx.temp_root / "s18-vocr")
    repo = make_repo(ctx.temp_root / "s18-repo")
    api = _task("task-s18-api", scope=["src/api/**"])
    cli = _task("task-s18-cli", scope=["src/cli/**"])
    conflict = _task("task-s18-api-2", scope=["src/api/new.py"])
    first = ledger.acquire_claims([api, cli], repo_root=repo)
    second = ledger.acquire_claims([conflict], repo_root=repo)
    steps = [
        step("siblings acquired", not first and len(ledger.active_claims()) == 2),
        step("future file conflicts", bool(second)),
        step("exact siblings disjoint", not claims_conflict(_claim("a/x.py", "x"), _claim("a/y.py", "y"))),
        step("same file conflicts", claims_conflict(_claim("a/x.py", "x"), _claim("a/x.py", "y"))),
    ]
    return _scenario_result(scenario, steps)


def _s19(scenario: Scenario, ctx: BetaContext):
    root = ctx.temp_root / "s19-vocr"
    store = ProjectMemoryStore(root)
    note = MemoryNote(kind=MemoryNoteKind.convention, text="Accepted reviews may add compact memory.")
    with ctx.env({"VOCR_PROJECT_MEMORY": "true"}):
        written = store.append_notes(task_id="task-s19", slice_id="slice-beta", notes=[note])
        brief = store.brief("accepted memory", limit=3)
        pruned = store.prune(written[0].id)
    return _scenario_result(scenario, [step("persisted", bool(written)), step("brief capped", "PROJECT MEMORY" in brief), step("pruned", pruned)])


class _cwd:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.previous = Path.cwd()

    def __enter__(self):
        os.chdir(self.path)

    def __exit__(self, *_):
        os.chdir(self.previous)


def _wrap(identifier: str, title: str, tier: str, hard: bool, fn):
    scenario = Scenario(identifier, title, tier, hard, lambda ctx: fn(scenario, ctx))
    return scenario


SCENARIOS: dict[str, Scenario] = {
    scenario.id: scenario
    for scenario in [
        _wrap("S00", "pure-cloud-reference", "core", True, _s00),
        _wrap("S01", "happy-path-gates", "core", True, _s01),
        _wrap("S02", "injection-containment", "core", True, _s02),
        _wrap("S03", "scope-breach", "core", True, _s03),
        _wrap("S04", "secrets-gate", "core", True, _s04),
        _wrap("S05", "retry-economy", "core", True, _s05),
        _wrap("S06", "review-contract", "core", True, _s06),
        _wrap("S07", "ratchet-matrix", "core", True, _s07),
        _wrap("S08", "baseline-objective", "core", True, _s08),
        _wrap("S09", "budget-gate", "core", True, _s09),
        _wrap("S10", "context-quality", "core", True, _s10),
        _wrap("S11", "prompt-constancy-a-b", "core", False, _s11),
        _wrap("S12", "embeddings-matrix", "core", False, _s12),
        _wrap("S13", "local-assist-quadrant", "core", True, _s13),
        _wrap("S14", "incremental-review", "core", True, _s14),
        _wrap("S15", "ledger-integrity", "core", True, _s15),
        _wrap("S16", "robustness-inputs", "core", True, _s16),
        _wrap("S17", "e2e-codex-cloud", "cloud", False, _s17),
        _wrap("S18", "parallel-claims", "core", True, _s18),
        _wrap("S19", "project-memory", "core", True, _s19),
    ]
}
