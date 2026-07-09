from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Iterable

from pydantic import BaseModel

from vocr.models import (
    LedgerEvent,
    LedgerEventType,
    PermissionGrant,
    PermissionMode,
    ReviewResult,
    TaskStatus,
    VisionSlice,
    VocrTask,
)


SECRET_KEYWORDS = {"api_key", "apikey", "secret", "token", "password", "credential"}
SECRET_PATTERNS = [
    re.compile(r"sk-[A-Za-z0-9_-]{12,}"),
]


def sanitize_payload(value: object) -> object:
    if isinstance(value, dict):
        sanitized: dict[str, object] = {}
        for key, item in value.items():
            lowered = key.lower().replace("-", "_")
            if any(keyword in lowered for keyword in SECRET_KEYWORDS):
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

    def init(self) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        self.path.touch(exist_ok=True)

    def append(self, event_type: LedgerEventType, payload: BaseModel | dict) -> LedgerEvent:
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
            elif event.type == LedgerEventType.review_recorded:
                review = ReviewResult.model_validate(event.payload)
                if review.task_id in task_map:
                    task_map[review.task_id].status = TaskStatus(review.decision.value)
            elif event.type == LedgerEventType.task_promoted:
                task_id = event.payload["task_id"]
                if task_id in task_map:
                    task_map[task_id].status = TaskStatus.promoted
        return list(task_map.values())

    def reviews(self) -> list[ReviewResult]:
        return [
            ReviewResult.model_validate(event.payload)
            for event in self.events()
            if event.type == LedgerEventType.review_recorded
        ]

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

    def dump_json(self) -> str:
        return json.dumps([event.model_dump(mode="json") for event in self.events()], indent=2)
