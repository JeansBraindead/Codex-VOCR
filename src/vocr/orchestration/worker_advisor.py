from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from vocr.guardrails.claims import build_scope_claim, claims_conflict
from vocr.memory.advisor_calibration import AdvisorCalibration
from vocr.models import VocrTask


@dataclass(frozen=True)
class WorkerPlanOption:
    workers: int
    runnable_tasks: int
    speedup_pct: int
    token_overhead_pct: int
    conflict_risk: str
    score: float
    rationale: str
    confidence: str = "heuristic"
    recommended: bool = False


class WorkerParallelismAdvisor:
    def __init__(self, repo_root: str | Path = ".") -> None:
        self.repo_root = Path(repo_root)
        self.calibration = AdvisorCalibration(self.repo_root)

    def options(self, tasks: list[VocrTask]) -> list[WorkerPlanOption]:
        wave = self._claim_compatible_wave([task for task in tasks if not task.dependencies])
        if not wave:
            return [
                WorkerPlanOption(
                    workers=1,
                    runnable_tasks=0,
                    speedup_pct=0,
                    token_overhead_pct=0,
                    conflict_risk="keine freie Task",
                    score=0.0,
                    rationale="Keine dependency-freie, konfliktfreie Task ist bereit.",
                    confidence="heuristic",
                    recommended=True,
                )
            ]

        max_workers = len(wave)
        raw_options = [self._score_option(wave, workers) for workers in range(1, max_workers + 1)]
        best_score = max(option.score for option in raw_options)
        return [
            WorkerPlanOption(
                workers=option.workers,
                runnable_tasks=option.runnable_tasks,
                speedup_pct=option.speedup_pct,
                token_overhead_pct=option.token_overhead_pct,
                conflict_risk=option.conflict_risk,
                score=option.score,
                rationale=option.rationale,
                confidence=option.confidence,
                recommended=option.score == best_score,
            )
            for option in raw_options
        ]

    def message(self, tasks: list[VocrTask]) -> str:
        options = self.options(tasks)
        lines = [
            "Worker-Vorschlag des Visionaers:",
            "Ich vergleiche konfliktfreie Tasks, Scope-Breite, Tests, Kontextgroesse, Reviewlast und Token-Overhead.",
        ]
        for option in options:
            marker = "Empfohlen: " if option.recommended else "Option: "
            lines.append(
                f"- {marker}{option.workers} Worker, {option.runnable_tasks} Tasks parallel, "
                f"ca. {option.speedup_pct}% schneller, ca. +{option.token_overhead_pct}% Token-/Kontext-Overhead, "
                f"Konfliktrisiko {option.conflict_risk}; {option.rationale}"
            )
        return "\n".join(lines)

    def recommended_workers(self, tasks: list[VocrTask]) -> int:
        options = self.options(tasks)
        recommended = next((option for option in options if option.recommended), options[0])
        return recommended.workers

    def _score_option(self, wave: list[VocrTask], workers: int) -> WorkerPlanOption:
        selected = wave[:workers]
        avg_complexity = sum(self._task_complexity(task) for task in selected) / workers
        measured_speedup = self.calibration.measured_speedup(workers)
        speedup_pct = (
            int(round(measured_speedup.value))
            if measured_speedup is not None
            else self._heuristic_speedup_pct(workers)
        )
        measured_durations = [self.calibration.measured_task_duration(task) for task in selected]
        measured_duration_count = sum(item.sample_count for item in measured_durations if item is not None)
        if measured_durations and all(item is not None for item in measured_durations):
            median_seconds = sum(item.value for item in measured_durations if item is not None) / workers
            avg_complexity += min(median_seconds / 30, 4.0)
        token_overhead_pct = int(round(self._token_overhead_pct(selected)))
        review_penalty = max(0, workers - 1) * (6 + avg_complexity * 1.5)
        risk_penalty = self._risk_penalty(selected)
        score = speedup_pct - token_overhead_pct - review_penalty - risk_penalty
        if workers == 1:
            score += 8
        confidence = "measured" if measured_speedup is not None or measured_duration_count >= 5 else "heuristic"
        rationale = self._rationale(
            avg_complexity,
            review_penalty,
            risk_penalty,
            confidence=confidence,
            measured_runs=measured_speedup.sample_count if measured_speedup is not None else measured_duration_count,
        )
        return WorkerPlanOption(
            workers=workers,
            runnable_tasks=workers,
            speedup_pct=speedup_pct,
            token_overhead_pct=token_overhead_pct,
            conflict_risk=self._conflict_risk(selected, avg_complexity, risk_penalty),
            score=round(score, 2),
            rationale=rationale,
            confidence=confidence,
        )

    def _heuristic_speedup_pct(self, workers: int) -> int:
        return int(round((1 - (1 / workers)) * 100)) if workers > 1 else 0

    def _claim_compatible_wave(self, tasks: list[VocrTask]) -> list[VocrTask]:
        selected: list[VocrTask] = []
        selected_claims = []
        for task in sorted(tasks, key=self._task_complexity):
            claim = build_scope_claim(task, self.repo_root)
            if any(claims_conflict(claim, existing) for existing in selected_claims):
                continue
            selected.append(task)
            selected_claims.append(claim)
        return selected

    def _task_complexity(self, task: VocrTask) -> float:
        scope_width = sum(self._scope_cost(item) for item in task.scope)
        test_cost = len(task.tests) * 0.8
        context_cost = len(task.context_pack or "") / 1200
        acceptance_cost = len(task.acceptance_criteria) * 0.5
        return max(1.0, scope_width + test_cost + context_cost + acceptance_cost)

    def _scope_cost(self, scope: str) -> float:
        normalized = scope.replace("\\", "/").strip()
        if normalized in {".", "./", "**", "**/*"}:
            return 8.0
        if "**" in normalized:
            return 3.5
        if "*" in normalized or "?" in normalized or "[" in normalized:
            return 2.5
        if "/" not in normalized and "." not in normalized:
            return 4.0
        return 1.0

    def _token_overhead_pct(self, tasks: list[VocrTask]) -> float:
        duplicated_context = sum(min(len(task.context_pack or ""), 6000) for task in tasks)
        context_penalty = duplicated_context / 900
        complexity_penalty = sum(self._task_complexity(task) for task in tasks) * 1.1
        coordination_penalty = max(0, len(tasks) - 1) * 4
        return coordination_penalty + complexity_penalty + context_penalty

    def _risk_penalty(self, tasks: list[VocrTask]) -> float:
        broad = sum(1 for task in tasks for scope in task.scope if scope.strip() in {".", "./", "**", "**/*"} or "src/**" in scope)
        many_tests = sum(1 for task in tasks if len(task.tests) >= 3)
        return broad * 18 + many_tests * 4

    def _conflict_risk(self, tasks: list[VocrTask], avg_complexity: float, risk_penalty: float) -> str:
        if risk_penalty >= 18 or avg_complexity >= 7:
            return "hoch"
        if len(tasks) >= 4 or avg_complexity >= 4:
            return "mittel"
        return "niedrig"

    def _rationale(
        self,
        avg_complexity: float,
        review_penalty: float,
        risk_penalty: float,
        *,
        confidence: str,
        measured_runs: int,
    ) -> str:
        notes: list[str] = []
        if avg_complexity < 3:
            notes.append("Tasks sind klein genug fuer parallele Bearbeitung")
        elif avg_complexity < 6:
            notes.append("mittlere Task-Komplexitaet begrenzt die sinnvolle Welle")
        else:
            notes.append("breite oder kontextlastige Tasks sprechen fuer weniger Worker")
        if review_penalty > 20:
            notes.append("Reviewlast steigt sichtbar")
        if risk_penalty > 0:
            notes.append("breite Scopes oder viele Tests erhoehen Risiko")
        if confidence == "measured":
            notes.append(f"kalibriert aus {measured_runs} Lauf-Samples")
        else:
            notes.append("Heuristik, noch keine Messdaten")
        return "; ".join(notes) + "."
