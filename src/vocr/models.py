from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from uuid import uuid4

from pydantic import BaseModel, Field


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def new_id(prefix: str) -> str:
    return f"{prefix}-{uuid4().hex[:10]}"


class TaskStatus(str, Enum):
    planned = "planned"
    dispatched = "dispatched"
    review_ready = "review_ready"
    accepted = "accepted"
    needs_changes = "needs_changes"
    blocked = "blocked"
    promoted = "promoted"


class ReviewDecision(str, Enum):
    accepted = "accepted"
    needs_changes = "needs_changes"
    blocked = "blocked"


class PermissionMode(str, Enum):
    ask_each_time = "ask_each_time"
    approve_all = "approve_all"


class LedgerEventType(str, Enum):
    setup = "setup"
    clarification_requested = "clarification_requested"
    vision_created = "vision_created"
    task_created = "task_created"
    task_dispatched = "task_dispatched"
    review_recorded = "review_recorded"
    task_promoted = "task_promoted"
    permission_granted = "permission_granted"
    tweak_recorded = "tweak_recorded"
    message = "message"


class AcceptanceCriterion(BaseModel):
    text: str
    verified_by: str = "manual review"


class ClarificationQuestion(BaseModel):
    topic: str
    question: str
    why_needed: str


class ReadinessReport(BaseModel):
    ready: bool
    confidence: float = Field(ge=0.0, le=1.0)
    missing_topics: list[str] = Field(default_factory=list)
    questions: list[ClarificationQuestion] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)


class VisionSlice(BaseModel):
    id: str = Field(default_factory=lambda: new_id("slice"))
    request: str
    goal: str
    assumptions: list[str] = Field(default_factory=list)
    acceptance_criteria: list[AcceptanceCriterion] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=utc_now)


class VocrTask(BaseModel):
    id: str = Field(default_factory=lambda: new_id("task"))
    slice_id: str
    title: str
    summary: str
    scope: list[str]
    non_goals: list[str] = Field(default_factory=list)
    acceptance_criteria: list[AcceptanceCriterion]
    tests: list[str]
    context_query: str | None = None
    context_pack: str | None = None
    status: TaskStatus = TaskStatus.planned
    worktree_path: Path | None = None
    branch_name: str | None = None
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)


class ReviewResult(BaseModel):
    task_id: str
    decision: ReviewDecision
    summary: str
    risks: list[str] = Field(default_factory=list)
    required_changes: list[str] = Field(default_factory=list)
    tests_reviewed: list[str] = Field(default_factory=list)
    git_status: str | None = None
    diff_summary: str | None = None
    created_at: datetime = Field(default_factory=utc_now)


class PermissionGrant(BaseModel):
    id: str = Field(default_factory=lambda: new_id("perm"))
    mode: PermissionMode
    scope: str = "global"
    granted_by: str = "visionary-go"
    reason: str = "User approved unattended VOCR execution."
    created_at: datetime = Field(default_factory=utc_now)


class ScopePolicy(BaseModel):
    task_id: str
    allowed_roots: list[str]
    denied_roots: list[str] = Field(default_factory=lambda: [".git", ".venv", ".vocr/ledger.jsonl"])
    notes: list[str] = Field(default_factory=list)


class TaskPlan(BaseModel):
    tasks: list[VocrTask] = Field(default_factory=list)


class LedgerEvent(BaseModel):
    id: str = Field(default_factory=lambda: new_id("evt"))
    type: LedgerEventType
    payload: dict
    created_at: datetime = Field(default_factory=utc_now)


class BusMessage(BaseModel):
    channel: str
    sender: str
    body: str
    created_at: datetime = Field(default_factory=utc_now)


class GraphNode(BaseModel):
    path: str
    kind: str
    size_bytes: int
    line_count: int
    summary: str
    imports: list[str] = Field(default_factory=list)
    symbols: list[str] = Field(default_factory=list)


class GraphEdge(BaseModel):
    source: str
    target: str
    relation: str


class RepoGraph(BaseModel):
    root: str
    nodes: list[GraphNode] = Field(default_factory=list)
    edges: list[GraphEdge] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=utc_now)

    def context_brief(self, limit: int = 20, query: str | None = None) -> str:
        nodes = self.nodes
        if query:
            terms = [term.lower() for term in query.split() if term.strip()]
            scored: list[tuple[int, GraphNode]] = []
            for node in self.nodes:
                haystack = " ".join(
                    [
                        node.path,
                        node.summary,
                        " ".join(node.imports),
                        " ".join(node.symbols),
                    ]
                ).lower()
                score = sum(1 for term in terms if term in haystack)
                if score:
                    scored.append((score, node))
            nodes = [node for _, node in sorted(scored, key=lambda item: (-item[0], item[1].path))]

        lines = ["VOCR repo graph brief:"]
        if query:
            lines.append(f"Query: {query}")
        for node in nodes[:limit]:
            symbol_text = ", ".join(node.symbols[:6]) or "no symbols"
            lines.append(f"- {node.path}: {node.summary} ({symbol_text})")
        if len(nodes) > limit:
            lines.append(f"- ... {len(nodes) - limit} more matching files omitted")
        if not nodes:
            lines.append("- no matching files")
        return "\n".join(lines)
