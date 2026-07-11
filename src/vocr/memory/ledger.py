from __future__ import annotations

from contextlib import contextmanager
import json
import os
import re
from pathlib import Path
import threading
from typing import Iterable

from pydantic import BaseModel

from vocr.models import (
    ClarificationSession,
    CompactResult,
    LedgerEvent,
    LedgerEventType,
    PermissionGrant,
    PermissionMode,
    ReviewResult,
    RunTelemetry,
    TaskStatus,
    VisionSlice,
    VocrTask,
)


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
_THREAD_LOCKS: dict[Path, threading.RLock] = {}
_THREAD_LOCKS_GUARD = threading.Lock()

if os.name == "nt":
    import msvcrt
else:
    import fcntl


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
        self.lock_path = self.root / "ledger.lock"
        self._events_cache: list[LedgerEvent] | None = None
        self._events_cache_stat: tuple[int, int] | None = None

    def init(self) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        self.path.touch(exist_ok=True)

    def append(self, event_type: LedgerEventType, payload: BaseModel | dict) -> LedgerEvent:
        data = payload.model_dump(mode="json") if isinstance(payload, BaseModel) else payload
        data = sanitize_payload(data)
        event = LedgerEvent(type=event_type, payload=data)
        with self._locked():
            self.path.touch(exist_ok=True)
            with self.path.open("a", encoding="utf-8") as handle:
                handle.write(event.model_dump_json() + "\n")
            self._events_cache = None
            self._events_cache_stat = None
        return event

    def events(self) -> Iterable[LedgerEvent]:
        with self._locked():
            return self._read_events_unlocked()

    def _read_events_unlocked(self) -> list[LedgerEvent]:
        if not self.path.exists():
            return []
        stat = self.path.stat()
        cache_stat = (stat.st_mtime_ns, stat.st_size)
        if self._events_cache is not None and self._events_cache_stat == cache_stat:
            return list(self._events_cache)
        items: list[LedgerEvent] = []
        with self.path.open("r", encoding="utf-8") as handle:
            for line in handle:
                if line.strip():
                    items.append(LedgerEvent.model_validate_json(line))
        self._events_cache = items
        self._events_cache_stat = cache_stat
        return items

    def slices(self) -> list[VisionSlice]:
        return [
            VisionSlice.model_validate(event.payload)
            for event in self.events()
            if event.type == LedgerEventType.vision_created
        ]

    def tasks(self) -> list[VocrTask]:
        task_map: dict[str, VocrTask] = {}
        for event in self.events():
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
            elif event.type == LedgerEventType.task_reverted:
                task_id = event.payload["task_id"]
                if task_id in task_map:
                    task_map[task_id].status = TaskStatus.needs_changes
        return list(task_map.values())

    def reviews(self) -> list[ReviewResult]:
        return [
            ReviewResult.model_validate(event.payload)
            for event in self.events()
            if event.type == LedgerEventType.review_recorded
        ]

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

    def get_slice(self, slice_id: str) -> VisionSlice | None:
        return next((item for item in self.slices() if item.id == slice_id), None)

    def get_task(self, task_id: str) -> VocrTask | None:
        return next((item for item in self.tasks() if item.id == task_id), None)

    def latest_task_commit(self, task_id: str) -> str | None:
        commit_sha: str | None = None
        for event in self.events():
            if event.type == LedgerEventType.task_committed and event.payload.get("task_id") == task_id:
                value = event.payload.get("commit_sha")
                if value:
                    commit_sha = str(value)
            elif event.type == LedgerEventType.task_reverted and event.payload.get("task_id") == task_id:
                commit_sha = None
        return commit_sha

    def dump_json(self) -> str:
        return json.dumps([event.model_dump(mode="json") for event in self.events()], indent=2)

    def compact(self, *, keep_last: int = 200) -> CompactResult:
        with self._locked():
            self.path.touch(exist_ok=True)
            return self._compact_unlocked(keep_last=keep_last)

    def _compact_unlocked(self, *, keep_last: int) -> CompactResult:
        events = self._read_events_unlocked()
        if len(events) <= keep_last:
            return CompactResult(
                original_events=len(events),
                kept_events=len(events),
                archived_events=0,
            )

        archive_dir = self.root / "archive"
        archive_dir.mkdir(parents=True, exist_ok=True)
        archive_path = archive_dir / f"ledger-{events[0].created_at.strftime('%Y%m%d%H%M%S')}-{events[-keep_last - 1].created_at.strftime('%Y%m%d%H%M%S')}.jsonl"
        archived = events[:-keep_last]
        kept = events[-keep_last:]
        with archive_path.open("w", encoding="utf-8") as handle:
            for event in archived:
                handle.write(event.model_dump_json() + "\n")
        with self.path.open("w", encoding="utf-8") as handle:
            for event in kept:
                handle.write(event.model_dump_json() + "\n")
        self._events_cache = None
        self._events_cache_stat = None
        return CompactResult(
            original_events=len(events),
            kept_events=len(kept),
            archived_events=len(archived),
            archive_path=str(archive_path),
        )

    @contextmanager
    def _locked(self):
        self.root.mkdir(parents=True, exist_ok=True)
        lock_path = self.lock_path.resolve()
        with _thread_lock(lock_path):
            with lock_path.open("a+b") as handle:
                if handle.tell() == 0 and lock_path.stat().st_size == 0:
                    handle.write(b"\0")
                    handle.flush()
                handle.seek(0)
                _lock_file(handle)
                try:
                    yield
                finally:
                    _unlock_file(handle)


@contextmanager
def _thread_lock(path: Path):
    with _THREAD_LOCKS_GUARD:
        lock = _THREAD_LOCKS.setdefault(path, threading.RLock())
    with lock:
        yield


def _lock_file(handle) -> None:
    if os.name == "nt":
        msvcrt.locking(handle.fileno(), msvcrt.LK_LOCK, 1)
    else:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)


def _unlock_file(handle) -> None:
    if os.name == "nt":
        handle.seek(0)
        msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
    else:
        fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
