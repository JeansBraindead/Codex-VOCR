from __future__ import annotations

import json
import os
import re
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Iterable

from pydantic import BaseModel

from vocr.models import (
    ClarificationSession,
    CompactResult,
    LedgerEvent,
    LedgerEventType,
    PermissionGrant,
    PermissionMode,
    ClaimConflict,
    ReviewResult,
    RunTelemetry,
    ScopeClaim,
    TaskStatus,
    VisionSlice,
    VocrTask,
)
from vocr.guardrails.claims import build_scope_claim, claim_conflicts


STALE_LOCK_SECONDS = 30.0

SECRET_KEYWORDS = {"api_key", "apikey", "secret", "token", "password", "credential"}
SAFE_KEYWORDS = {
    "token_usage",
    "prompt_tokens",
    "completion_tokens",
    "total_tokens",
    "estimated_tokens",
    "prompt_tokens_estimate",
    "completion_tokens_estimate",
}
SECRET_PATTERNS = [
    re.compile(r"sk-[A-Za-z0-9_-]{12,}"),
]


def sanitize_payload(value: object) -> object:
    if isinstance(value, dict):
        sanitized: dict[str, object] = {}
        for key, item in value.items():
            lowered = key.lower().replace("-", "_")
            if lowered in SAFE_KEYWORDS:
                sanitized[key] = sanitize_payload(item)
            elif any(keyword in lowered for keyword in SECRET_KEYWORDS):
                sanitized[key] = "[redacted]"
            else:
                sanitized[key] = sanitize_payload(item)
        return sanitized
    if isinstance(value, list):
        return [sanitize_payload(item) for item in value]
    if isinstance(value, str):
        sanitized = value
        for pattern in SECRET_PATTERNS:
            sanitized = pattern.sub("[redacted]", sanitized)
        return sanitized
    return value


class MemoryLedger:
    def __init__(self, root: Path | str = ".vocr") -> None:
        self.root = Path(root)
        self.path = self.root / "ledger.jsonl"
        self.lock_path = self.root / "ledger.jsonl.lock"

    def init(self) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        self.path.touch(exist_ok=True)

    def append(self, event_type: LedgerEventType, payload: BaseModel | dict) -> LedgerEvent:
        with self._ledger_lock():
            return self._append_unlocked(event_type, payload)

    def _append_unlocked(self, event_type: LedgerEventType, payload: BaseModel | dict) -> LedgerEvent:
        self.init()
        data = payload.model_dump(mode="json") if isinstance(payload, BaseModel) else payload
        data = sanitize_payload(data)
        event = LedgerEvent(type=event_type, payload=data)
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(event.model_dump_json() + "\n")
        return event

    def events(self) -> Iterable[LedgerEvent]:
        if not self.path.exists():
            return []
        items: list[LedgerEvent] = []
        with self.path.open("r", encoding="utf-8") as handle:
            for line in handle:
                if line.strip():
                    items.append(LedgerEvent.model_validate_json(line))
        return items

    def slices(self) -> list[VisionSlice]:
        return [
            VisionSlice.model_validate(event.payload)
            for event in self.events()
            if event.type == LedgerEventType.vision_created
        ]

    def tasks(self) -> list[VocrTask]:
        return self._tasks_from_events(list(self.events()))

    def _tasks_from_events(self, events: Iterable[LedgerEvent]) -> list[VocrTask]:
        task_map: dict[str, VocrTask] = {}
        for event in events:
            if event.type == LedgerEventType.task_created:
                task = VocrTask.model_validate(event.payload)
                task_map[task.id] = task
            elif event.type == LedgerEventType.task_dispatched:
                task_id = event.payload["task_id"]
                if task_id in task_map:
                    task = task_map[task_id]
                    task.status = TaskStatus.dispatched
                    task.branch_name = event.payload.get("branch_name")
                    worktree_path = event.payload.get("worktree_path")
                    task.worktree_path = Path(worktree_path) if worktree_path else None
            elif event.type == LedgerEventType.task_worker_ran:
                task_id = event.payload["task_id"]
                if task_id in task_map and event.payload.get("exit_code") == 0:
                    task_map[task_id].status = TaskStatus.review_ready
            elif event.type == LedgerEventType.task_committed:
                task_id = event.payload["task_id"]
                if task_id in task_map:
                    task_map[task_id].status = TaskStatus.review_ready
            elif event.type == LedgerEventType.review_recorded:
                review = ReviewResult.model_validate(event.payload)
                if review.task_id in task_map:
                    task_map[review.task_id].status = TaskStatus(review.decision.value)
            elif event.type == LedgerEventType.task_promoted:
                task_id = event.payload["task_id"]
                if task_id in task_map:
                    task_map[task_id].status = TaskStatus.promoted
            elif event.type == LedgerEventType.task_aborted:
                task_id = event.payload["task_id"]
                if task_id in task_map:
                    task_map[task_id].status = TaskStatus.aborted
        return list(task_map.values())

    def reviews(self) -> list[ReviewResult]:
        return [
            ReviewResult.model_validate(event.payload)
            for event in self.events()
            if event.type == LedgerEventType.review_recorded
        ]

    def last_review(self, task_id: str) -> ReviewResult | None:
        matches = [review for review in self.reviews() if review.task_id == task_id]
        return matches[-1] if matches else None

    def telemetry(self) -> list[RunTelemetry]:
        return [
            RunTelemetry.model_validate(event.payload)
            for event in self.events()
            if event.type == LedgerEventType.telemetry_recorded
        ]

    def clarification_sessions(self) -> list[ClarificationSession]:
        sessions: dict[str, ClarificationSession] = {}
        for event in self.events():
            if event.type == LedgerEventType.clarification_requested:
                session = ClarificationSession.model_validate(event.payload)
                sessions[session.id] = session
            elif event.type == LedgerEventType.clarification_answered:
                session_id = event.payload.get("session_id")
                answer = event.payload.get("answer")
                if session_id in sessions and answer:
                    sessions[session_id].answers.append(str(answer))
        return list(sessions.values())

    def get_clarification(self, session_id: str) -> ClarificationSession | None:
        return next((item for item in self.clarification_sessions() if item.id == session_id), None)

    def permission_grants(self) -> list[PermissionGrant]:
        return [
            PermissionGrant.model_validate(event.payload)
            for event in self.events()
            if event.type == LedgerEventType.permission_granted
        ]

    def active_permission(self, scope: str | None = None) -> PermissionGrant | None:
        candidates = [
            grant
            for grant in self.permission_grants()
            if grant.mode == PermissionMode.approve_all
            and (grant.scope == "global" or (scope is not None and grant.scope == scope))
        ]
        return candidates[-1] if candidates else None

    def active_claims(self) -> list[ScopeClaim]:
        return self._active_claims_from_events(list(self.events()))

    def _active_claims_from_events(self, events: Iterable[LedgerEvent]) -> list[ScopeClaim]:
        claims: dict[str, ScopeClaim] = {}
        released: set[str] = set()
        for event in events:
            if event.type == LedgerEventType.claim_acquired:
                claim = ScopeClaim.model_validate(event.payload)
                claims[claim.task_id] = claim
                released.discard(claim.task_id)
            elif event.type == LedgerEventType.claim_released:
                task_id = str(event.payload.get("task_id", ""))
                released.add(task_id)
        return [claim for task_id, claim in claims.items() if task_id not in released]

    def acquire_claims(self, tasks: list[VocrTask], repo_root: Path | str = ".") -> list[ClaimConflict]:
        conflicts: list[ClaimConflict] = []
        with self._ledger_lock():
            active = self.active_claims()
            for task in tasks:
                claim = build_scope_claim(task, repo_root)
                task_conflicts = claim_conflicts(claim, active)
                if task_conflicts:
                    conflicts.extend(task_conflicts)
                    continue
                self._append_unlocked(LedgerEventType.claim_acquired, claim)
                active.append(claim)
        return conflicts

    def release_claim(self, task_id: str) -> None:
        self.append(LedgerEventType.claim_released, {"task_id": task_id})

    def reconcile_stale_claims(self) -> list[str]:
        terminal = {
            TaskStatus.accepted,
            TaskStatus.blocked,
            TaskStatus.aborted,
            TaskStatus.promoted,
        }
        tasks = {task.id: task for task in self.tasks()}
        released: list[str] = []
        for claim in self.active_claims():
            task = tasks.get(claim.task_id)
            if task is not None and task.status in terminal:
                self.release_claim(claim.task_id)
                released.append(claim.task_id)
        return released

    def get_slice(self, slice_id: str) -> VisionSlice | None:
        return next((item for item in self.slices() if item.id == slice_id), None)

    def get_task(self, task_id: str) -> VocrTask | None:
        return next((item for item in self.tasks() if item.id == task_id), None)

    @contextmanager
    def _ledger_lock(self, timeout_seconds: float = 5.0):
        self.root.mkdir(parents=True, exist_ok=True)
        deadline = time.monotonic() + timeout_seconds
        fd: int | None = None
        while fd is None:
            try:
                fd = os.open(str(self.lock_path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            except FileExistsError:
                stale_age = self._lock_age_seconds()
                if stale_age is not None and stale_age >= STALE_LOCK_SECONDS and self._take_over_stale_lock(stale_age):
                    continue
                if time.monotonic() >= deadline:
                    raise TimeoutError(f"Timed out waiting for ledger lock: {self.lock_path}")
                time.sleep(0.02)
        try:
            yield
        finally:
            os.close(fd)
            try:
                self.lock_path.unlink()
            except FileNotFoundError:
                pass

    def _lock_age_seconds(self) -> float | None:
        try:
            mtime = self.lock_path.stat().st_mtime
        except FileNotFoundError:
            return None
        return max(0.0, time.time() - mtime)

    def _take_over_stale_lock(self, age_seconds: float) -> bool:
        try:
            self.lock_path.unlink()
        except (FileNotFoundError, PermissionError, OSError):
            return False
        self._append_unlocked(
            LedgerEventType.message,
            {
                "message": "Stale ledger lock takeover",
                "lock_path": str(self.lock_path),
                "age_seconds": round(age_seconds, 2),
            },
        )
        return True

    def dump_json(self) -> str:
        return json.dumps([event.model_dump(mode="json") for event in self.events()], indent=2)

    def compact(self, *, keep_last: int = 200) -> CompactResult:
        self.init()
        events = list(self.events())
        if len(events) <= keep_last:
            return CompactResult(
                original_events=len(events),
                kept_events=len(events),
                archived_events=0,
            )

        archive_dir = self.root / "archive"
        archive_dir.mkdir(parents=True, exist_ok=True)
        archive_path = archive_dir / f"ledger-{events[0].created_at.strftime('%Y%m%d%H%M%S')}-{events[-keep_last - 1].created_at.strftime('%Y%m%d%H%M%S')}.jsonl"

        tail = events[-keep_last:]
        head = events[:-keep_last]
        forwarded_ids = self._essential_forwarding_ids(events)

        forwarded = [event for event in head if event.id in forwarded_ids]
        archived = [event for event in head if event.id not in forwarded_ids]
        kept = forwarded + tail

        with archive_path.open("w", encoding="utf-8") as handle:
            for event in archived:
                handle.write(event.model_dump_json() + "\n")
        with self.path.open("w", encoding="utf-8") as handle:
            for event in kept:
                handle.write(event.model_dump_json() + "\n")
        return CompactResult(
            original_events=len(events),
            kept_events=len(kept),
            archived_events=len(archived),
            archive_path=str(archive_path),
        )

    def _essential_forwarding_ids(self, events: list[LedgerEvent]) -> set[str]:
        """Event ids that must survive compaction so non-terminal tasks and
        active claims stay reachable via tasks()/active_claims(), even if the
        events that created them fall outside the keep_last window."""
        terminal_statuses = {
            TaskStatus.accepted,
            TaskStatus.blocked,
            TaskStatus.aborted,
            TaskStatus.promoted,
        }
        active_claim_task_ids = {claim.task_id for claim in self._active_claims_from_events(events)}
        live_task_ids = {
            task.id
            for task in self._tasks_from_events(events)
            if task.status not in terminal_statuses
        }
        forward_task_ids = live_task_ids | active_claim_task_ids

        latest_claim_event_id: dict[str, str] = {}
        for event in events:
            if event.type == LedgerEventType.claim_acquired:
                task_id = event.payload.get("task_id")
                if task_id:
                    latest_claim_event_id[task_id] = event.id

        forwarded_ids: set[str] = set()
        for event in events:
            if event.type == LedgerEventType.task_created:
                if event.payload.get("id") in forward_task_ids:
                    forwarded_ids.add(event.id)
            elif event.type == LedgerEventType.claim_acquired:
                task_id = event.payload.get("task_id")
                if task_id in active_claim_task_ids and latest_claim_event_id.get(task_id) == event.id:
                    forwarded_ids.add(event.id)
        return forwarded_ids
