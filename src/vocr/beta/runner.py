from __future__ import annotations

import os
import tempfile
import traceback
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from time import perf_counter
from typing import Callable, Iterable, Literal

from pydantic import BaseModel, Field


class BetaStep(BaseModel):
    name: str
    status: str
    details: str = ""


class ScenarioResult(BaseModel):
    id: str
    title: str
    tier: str
    hard: bool
    status: str
    duration_s: float
    steps: list[BetaStep] = Field(default_factory=list)
    metrics: dict[str, float | str] = Field(default_factory=dict)
    notes: list[str] = Field(default_factory=list)


@dataclass(slots=True)
class Scenario:
    id: str
    title: str
    tier: str
    hard: bool
    run: Callable[["BetaContext"], ScenarioResult]


@dataclass(slots=True)
class BetaContext:
    temp_root: Path
    report_dir: Path
    repo_root: Path
    allow_cloud: bool = False
    max_cloud_tasks: int = 3
    cloud_tasks_used: int = 0

    @contextmanager
    def env(self, values: dict[str, str | None]):
        with set_env(values):
            yield


class BetaRun(BaseModel):
    status: str
    exit_code: int
    created_at: str
    results: list[ScenarioResult]
    report_json: str | None = None
    report_markdown: str | None = None


BetaProgressEvent = Literal["selected", "start", "finish", "report"]
BetaProgressCallback = Callable[[BetaProgressEvent, Scenario | ScenarioResult | list[Scenario] | tuple[Path | None, Path | None]], None]


@contextmanager
def set_env(values: dict[str, str | None]):
    previous = {key: os.environ.get(key) for key in values}
    try:
        for key, value in values.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        yield
    finally:
        for key, value in previous.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


def run_beta(
    scenarios: Iterable[Scenario],
    *,
    tier: str = "core",
    only: list[str] | None = None,
    report_dir: Path | str = "beta_reports",
    allow_cloud: bool = False,
    max_cloud_tasks: int = 3,
    json_only: bool = False,
    tag: str | None = None,
    repo_root: Path | str | None = None,
    on_progress: BetaProgressCallback | None = None,
) -> BetaRun:
    from vocr.beta.report import write_reports

    selected = select_scenarios(scenarios, tier=tier, only=only, allow_cloud=allow_cloud)
    if on_progress:
        on_progress("selected", selected)
    report_path = Path(report_dir)
    results: list[ScenarioResult] = []
    with tempfile.TemporaryDirectory(prefix="vocr-beta-") as tmp:
        ctx = BetaContext(
            temp_root=Path(tmp),
            report_dir=report_path,
            repo_root=Path(repo_root).resolve() if repo_root else Path.cwd().resolve(),
            allow_cloud=allow_cloud,
            max_cloud_tasks=max_cloud_tasks,
        )
        for scenario in selected:
            if on_progress:
                on_progress("start", scenario)
            scenario_result = _run_one(scenario, ctx)
            results.append(scenario_result)
            if on_progress:
                on_progress("finish", scenario_result)
    exit_code = beta_exit_code(results)
    status = "passed" if exit_code == 0 else "failed"
    report_json, report_markdown = write_reports(results, report_path, json_only=json_only, tag=tag)
    if on_progress:
        on_progress("report", (report_json, report_markdown))
    return BetaRun(
        status=status,
        exit_code=exit_code,
        created_at=datetime.now(timezone.utc).isoformat(),
        results=results,
        report_json=str(report_json) if report_json else None,
        report_markdown=str(report_markdown) if report_markdown else None,
    )


def select_scenarios(
    scenarios: Iterable[Scenario],
    *,
    tier: str,
    only: list[str] | None,
    allow_cloud: bool,
) -> list[Scenario]:
    wanted = {item.strip().upper() for item in only or [] if item.strip()}
    selected: list[Scenario] = []
    for scenario in scenarios:
        if wanted and scenario.id.upper() not in wanted:
            continue
        if not wanted:
            if tier == "core" and scenario.tier != "core":
                continue
            if tier == "local" and scenario.tier not in {"core", "local"}:
                continue
            if tier == "cloud" and scenario.tier != "cloud":
                continue
            if tier == "all" and scenario.tier == "cloud" and not allow_cloud:
                continue
        if scenario.tier == "cloud" and not allow_cloud:
            selected.append(_skipped_cloud_scenario(scenario))
        else:
            selected.append(scenario)
    return selected


def beta_exit_code(results: list[ScenarioResult]) -> int:
    hard_failed = any(result.hard and result.status == "failed" for result in results)
    soft_failed = any(not result.hard and result.status == "failed" for result in results)
    if hard_failed:
        return 1
    if soft_failed:
        return 2
    return 0


def _run_one(scenario: Scenario, ctx: BetaContext) -> ScenarioResult:
    start = perf_counter()
    try:
        result = scenario.run(ctx)
    except Exception as exc:  # noqa: BLE001 - harness must capture scenario failures.
        result = ScenarioResult(
            id=scenario.id,
            title=scenario.title,
            tier=scenario.tier,
            hard=scenario.hard,
            status="failed",
            duration_s=0.0,
            steps=[BetaStep(name="exception", status="failed", details=str(exc))],
            notes=[traceback.format_exc()],
        )
    result.duration_s = round(perf_counter() - start, 4)
    return result


def _skipped_cloud_scenario(scenario: Scenario) -> Scenario:
    def run(_: BetaContext) -> ScenarioResult:
        return ScenarioResult(
            id=scenario.id,
            title=scenario.title,
            tier=scenario.tier,
            hard=scenario.hard,
            status="skipped",
            duration_s=0.0,
            steps=[BetaStep(name="allow-cloud", status="skipped", details="Pass --allow-cloud to run.")],
        )

    return Scenario(scenario.id, scenario.title, scenario.tier, scenario.hard, run)


def step(name: str, ok: bool, details: str = "") -> BetaStep:
    return BetaStep(name=name, status="passed" if ok else "failed", details=details)


def result(
    scenario: Scenario,
    steps: list[BetaStep],
    *,
    metrics: dict[str, float | str] | None = None,
    notes: list[str] | None = None,
) -> ScenarioResult:
    failed = any(item.status == "failed" for item in steps)
    skipped = steps and all(item.status == "skipped" for item in steps)
    return ScenarioResult(
        id=scenario.id,
        title=scenario.title,
        tier=scenario.tier,
        hard=scenario.hard,
        status="skipped" if skipped else ("failed" if failed else "passed"),
        duration_s=0.0,
        steps=steps,
        metrics=metrics or {},
        notes=notes or [],
    )
