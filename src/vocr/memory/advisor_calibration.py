from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from statistics import median

from vocr.memory.ledger import MemoryLedger
from vocr.memory.learning import LearningStore, _terms
from vocr.models import LedgerEventType, VocrTask


@dataclass(frozen=True)
class CalibrationValue:
    value: float
    sample_count: int


class AdvisorCalibration:
    def __init__(self, repo_root: str | Path = ".") -> None:
        self.repo_root = Path(repo_root)
        self.vocr_home = self.repo_root / ".vocr"
        self.ledger = MemoryLedger(self.vocr_home)
        self.learning = LearningStore(self.vocr_home)

    def measured_task_duration(self, task: VocrTask) -> CalibrationValue | None:
        if not self.learning.exists():
            return None
        snapshot = self.learning.load()
        task_terms = set(_terms(" ".join([task.title, *task.scope])))
        if not task_terms:
            return None
        samples: list[float] = []
        for entry in [*snapshot.scopes.values(), *snapshot.task_titles.values()]:
            entry_terms = set(_terms(entry.key))
            if not entry_terms.intersection(task_terms):
                continue
            samples.extend(entry.duration_samples)
        if len(samples) < 5:
            return None
        return CalibrationValue(value=median(samples), sample_count=len(samples))

    def measured_speedup(self, worker_count: int) -> CalibrationValue | None:
        if worker_count <= 1 or not self.ledger.path.exists():
            return None
        serial_by_task_count: dict[int, list[float]] = {}
        parallel_events: list[tuple[int, float]] = []
        for event in self.ledger.events():
            if event.type != LedgerEventType.wave_executed:
                continue
            payload = event.payload
            task_count = int(payload.get("task_count") or 0)
            wall_seconds = float(payload.get("wall_seconds") or 0.0)
            event_workers = int(payload.get("worker_count") or 1)
            if task_count <= 0 or wall_seconds <= 0:
                continue
            if event_workers == 1:
                serial_by_task_count.setdefault(task_count, []).append(wall_seconds)
            elif event_workers == worker_count:
                parallel_events.append((task_count, wall_seconds))

        speedups: list[float] = []
        for task_count, parallel_seconds in parallel_events:
            serial_samples = serial_by_task_count.get(task_count)
            if not serial_samples:
                continue
            serial_seconds = median(serial_samples)
            if serial_seconds <= 0:
                continue
            speedups.append(max(0.0, min(95.0, (1 - (parallel_seconds / serial_seconds)) * 100)))

        if len(speedups) < 3:
            return None
        return CalibrationValue(value=median(speedups), sample_count=len(speedups))
