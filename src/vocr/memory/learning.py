from __future__ import annotations

from pathlib import Path

from vocr.memory.ledger import MemoryLedger
from vocr.models import LearningEntry, LearningSnapshot, ReviewDecision


class LearningStore:
    def __init__(self, root: Path | str = ".vocr") -> None:
        self.root = Path(root)
        self.path = self.root / "learning.json"

    def exists(self) -> bool:
        return self.path.exists()

    def load(self) -> LearningSnapshot:
        if not self.path.exists():
            return LearningSnapshot()
        return LearningSnapshot.model_validate_json(self.path.read_text(encoding="utf-8"))

    def save(self, snapshot: LearningSnapshot) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        self.path.write_text(snapshot.model_dump_json(indent=2), encoding="utf-8")

    def refresh(self, ledger: MemoryLedger) -> LearningSnapshot:
        snapshot = build_learning_snapshot(ledger)
        self.save(snapshot)
        return snapshot

    def brief(self, query: str | None = None, limit: int = 10) -> str:
        snapshot = self.load()
        terms = _terms(query or "")
        lines = ["VOCR learning brief:"]

        def score(entry: LearningEntry) -> int:
            haystack = " ".join([entry.key, *entry.files, *entry.tests, *entry.risks]).lower()
            return sum(1 for term in terms if term in haystack) if terms else entry.count

        entries = [*snapshot.scopes.values(), *snapshot.task_titles.values(), *snapshot.files.values()]
        ranked = [entry for entry in entries if score(entry) > 0]
        ranked.sort(key=lambda item: (-score(item), -item.count, item.key))
        for entry in ranked[:limit]:
            files = _top_items(entry.files, 4)
            tests = _top_items(entry.tests, 3)
            decisions = _top_items(entry.decisions, 3)
            lines.append(
                f"- {entry.key}: count={entry.count}; files={files or '-'}; "
                f"tests={tests or '-'}; decisions={decisions or '-'}; token_est={entry.estimated_tokens}"
            )
        if not ranked:
            lines.append("- no learning signals yet")
        return "\n".join(lines)

    def file_boosts(self, query: str | None = None, max_boost: float = 2.5) -> dict[str, float]:
        snapshot = self.load()
        terms = _terms(query or "")
        boosts: dict[str, float] = {}

        def entry_matches(entry: LearningEntry) -> bool:
            if not terms:
                return True
            haystack = " ".join([entry.key, *entry.files, *entry.tests, *entry.risks]).lower()
            return any(term in haystack for term in terms)

        for entry in [*snapshot.scopes.values(), *snapshot.task_titles.values(), *snapshot.files.values()]:
            if not entry_matches(entry):
                continue
            accepted = entry.decisions.get(ReviewDecision.accepted.value, 0)
            needs_changes = entry.decisions.get(ReviewDecision.needs_changes.value, 0)
            risk_multiplier = 1.0 + min(needs_changes, 3) * 0.15
            success_multiplier = 1.0 + min(accepted, 3) * 0.1
            for path, count in entry.files.items():
                boosts[path] = boosts.get(path, 0.0) + min(count * 0.35 * risk_multiplier * success_multiplier, max_boost)
        return {path: min(score, max_boost) for path, score in boosts.items()}


def build_learning_snapshot(ledger: MemoryLedger) -> LearningSnapshot:
    snapshot = LearningSnapshot()
    tasks = {task.id: task for task in ledger.tasks()}
    telemetry_by_task: dict[str, int] = {}
    for item in ledger.telemetry():
        if not item.task_id:
            continue
        usage = item.token_usage
        total = usage.total_tokens or (usage.prompt_tokens_estimate or 0) + (
            usage.completion_tokens_estimate or 0
        )
        telemetry_by_task[item.task_id] = telemetry_by_task.get(item.task_id, 0) + total

    for review in ledger.reviews():
        task = tasks.get(review.task_id)
        if task is None:
            continue
        files = review.diff_files
        tests = review.tests_reviewed
        risks = review.required_changes + review.risks
        token_total = telemetry_by_task.get(task.id, 0)

        for scope in task.scope:
            _apply_signal(
                _entry(snapshot.scopes, f"scope:{scope.lower()}"),
                files,
                tests,
                review.decision.value,
                risks,
                token_total,
            )
        _apply_signal(
            _entry(snapshot.task_titles, f"task:{task.title.lower()}"),
            files,
            tests,
            review.decision.value,
            risks,
            token_total,
        )
        for path in files:
            _apply_signal(
                _entry(snapshot.files, f"file:{path}"),
                files,
                tests,
                review.decision.value,
                risks,
                token_total,
            )
    return snapshot


def _entry(target: dict[str, LearningEntry], key: str) -> LearningEntry:
    if key not in target:
        target[key] = LearningEntry(key=key)
    return target[key]


def _apply_signal(
    entry: LearningEntry,
    files: list[str],
    tests: list[str],
    decision: str,
    risks: list[str],
    token_total: int,
) -> None:
    entry.count += 1
    entry.estimated_tokens += token_total
    _count_many(entry.files, files)
    _count_many(entry.tests, tests)
    _count_many(entry.decisions, [decision])
    if decision != ReviewDecision.accepted.value:
        _count_many(entry.risks, [risk[:120] for risk in risks])


def _count_many(target: dict[str, int], values: list[str]) -> None:
    for value in values:
        if value:
            target[value] = target.get(value, 0) + 1


def _top_items(values: dict[str, int], limit: int) -> str:
    items = sorted(values.items(), key=lambda item: (-item[1], item[0]))[:limit]
    return ", ".join(f"{key}({count})" for key, count in items)


def _terms(query: str) -> list[str]:
    return [term.strip().lower() for term in query.split() if term.strip()]
