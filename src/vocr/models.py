from __future__ import annotations

import math
import re
from collections import Counter
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
    aborted = "aborted"
    promoted = "promoted"


class ReviewDecision(str, Enum):
    accepted = "accepted"
    needs_changes = "needs_changes"
    blocked = "blocked"


class PermissionMode(str, Enum):
    ask_each_time = "ask_each_time"
    approve_all = "approve_all"


class NormalModePhase(str, Enum):
    welcome = "welcome"
    intake = "intake"
    confirmation = "confirmation"
    prepared = "prepared"


class LedgerEventType(str, Enum):
    setup = "setup"
    clarification_requested = "clarification_requested"
    clarification_answered = "clarification_answered"
    vision_created = "vision_created"
    task_created = "task_created"
    task_dispatched = "task_dispatched"
    task_worker_ran = "task_worker_ran"
    task_committed = "task_committed"
    task_aborted = "task_aborted"
    task_reverted = "task_reverted"
    review_recorded = "review_recorded"
    task_promoted = "task_promoted"
    telemetry_recorded = "telemetry_recorded"
    permission_granted = "permission_granted"
    tweak_recorded = "tweak_recorded"
    message = "message"


class AcceptanceCriterion(BaseModel):
    text: str
    verified_by: str = "manual review"
    check_command: str | None = None


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


class ProjectIntake(BaseModel):
    """User-approved facts collected by the normal Visionary dialog."""

    goal: str = ""
    workspace: str = ""
    acceptance_criteria: str = ""
    verification: str = ""
    non_goals: str = ""
    execution_bounds: str = ""


class NormalModeStatus(BaseModel):
    goal: str = "Noch nicht geklaert"
    workspace: str = "Noch nicht geklaert"
    acceptance_criteria: str = "Noch nicht geklaert"
    verification: str = "Noch nicht geklaert"
    non_goals: str = "Noch nicht geklaert"
    execution_bounds: str = "Noch nicht geklaert"
    readiness: str = "0/6 geklaert"
    current_step: str = "Ziel verstehen"
    environment_hint: str = "Lokaler Arbeitsbereich wird vorbereitet, wenn du zustimmst."


class ClarificationSession(BaseModel):
    id: str = Field(default_factory=lambda: new_id("clarify"))
    request: str
    report: ReadinessReport
    answers: list[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=utc_now)


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
    dependencies: list[str] = Field(default_factory=list)
    context_query: str | None = None
    context_pack: str | None = None
    status: TaskStatus = TaskStatus.planned
    worktree_path: Path | None = None
    branch_name: str | None = None
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)


class TestRunResult(BaseModel):
    command: str
    status: str
    exit_code: int | None = None
    output: str = ""


class ReviewComment(BaseModel):
    source: str
    body: str
    path: str | None = None
    line: int | None = None


class SecretFinding(BaseModel):
    rule_id: str
    path: str | None = None
    line: int | None = None
    summary: str
    severity: str = "high"


class SecretScanResult(BaseModel):
    findings: list[SecretFinding] = Field(default_factory=list)
    scanners: list[str] = Field(default_factory=list)

    @property
    def blocked(self) -> bool:
        return bool(self.findings)


class ReviewResult(BaseModel):
    task_id: str
    decision: ReviewDecision
    summary: str
    risks: list[str] = Field(default_factory=list)
    required_changes: list[str] = Field(default_factory=list)
    tests_reviewed: list[str] = Field(default_factory=list)
    test_results: list["TestRunResult"] = Field(default_factory=list)
    comments: list[ReviewComment] = Field(default_factory=list)
    git_status: str | None = None
    diff_summary: str | None = None
    diff_files: list[str] = Field(default_factory=list)
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
    allowed_globs: list[str] = Field(default_factory=list)
    denied_roots: list[str] = Field(default_factory=lambda: [".git", ".venv", ".vocr/ledger.jsonl"])
    notes: list[str] = Field(default_factory=list)


class TaskPlan(BaseModel):
    tasks: list[VocrTask] = Field(default_factory=list)


class OrchestrationStep(BaseModel):
    task_id: str
    action: str
    status: str
    detail: str = ""


class OrchestrationWave(BaseModel):
    index: int
    dispatch_task_ids: list[str] = Field(default_factory=list)
    work_task_ids: list[str] = Field(default_factory=list)
    graph_refreshed: bool = False
    steps: list[OrchestrationStep] = Field(default_factory=list)


class OrchestrationRunResult(BaseModel):
    waves: list[OrchestrationWave] = Field(default_factory=list)
    dispatched: int = 0
    worked: int = 0
    promoted: int = 0
    stopped_reason: str = ""


class CodexRunResult(BaseModel):
    task_id: str
    command: list[str]
    exit_code: int
    stdout: str = ""
    stderr: str = ""
    committed: bool = False
    commit_sha: str | None = None
    created_at: datetime = Field(default_factory=utc_now)


class TokenUsage(BaseModel):
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    total_tokens: int | None = None
    prompt_tokens_estimate: int | None = None
    completion_tokens_estimate: int | None = None
    source: str = "estimated"


class RunTelemetry(BaseModel):
    provider: str
    model: str | None = None
    base_url: str | None = None
    slice_id: str | None = None
    task_id: str | None = None
    agent: str
    token_usage: TokenUsage = Field(default_factory=TokenUsage)
    command: list[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=utc_now)


class LearningEntry(BaseModel):
    key: str
    count: int = 0
    files: dict[str, int] = Field(default_factory=dict)
    tests: dict[str, int] = Field(default_factory=dict)
    decisions: dict[str, int] = Field(default_factory=dict)
    risks: dict[str, int] = Field(default_factory=dict)
    estimated_tokens: int = 0
    retry_count: int = 0
    review_seconds_total: int = 0
    accepted_review_seconds_total: int = 0


class LearningSnapshot(BaseModel):
    version: int = 1
    scopes: dict[str, LearningEntry] = Field(default_factory=dict)
    task_titles: dict[str, LearningEntry] = Field(default_factory=dict)
    files: dict[str, LearningEntry] = Field(default_factory=dict)
    clarifications_requested: int = 0
    clarifications_answered: int = 0
    clarification_answer_rate_percent: int = 0
    clarification_topics: dict[str, int] = Field(default_factory=dict)
    updated_at: datetime = Field(default_factory=utc_now)


class CompactResult(BaseModel):
    original_events: int
    kept_events: int
    archived_events: int
    archive_path: str | None = None
    learning_path: str | None = None


class GoldenEvalStep(BaseModel):
    name: str
    passed: bool
    detail: str = ""


class GoldenEvalResult(BaseModel):
    passed: bool
    steps: list[GoldenEvalStep] = Field(default_factory=list)


class ReplayEvent(BaseModel):
    created_at: datetime
    type: str
    task_id: str | None = None
    detail: str


class SliceReplay(BaseModel):
    slice_id: str
    goal: str = ""
    events: list[ReplayEvent] = Field(default_factory=list)
    files_touched: list[str] = Field(default_factory=list)
    decisions: dict[str, str] = Field(default_factory=dict)
    token_total: int = 0
    token_by_source: dict[str, int] = Field(default_factory=dict)


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
    content_hash: str
    summary: str
    imports: list[str] = Field(default_factory=list)
    symbols: list[str] = Field(default_factory=list)
    search_tokens: list[str] = Field(default_factory=list)


class GraphEdge(BaseModel):
    source: str
    target: str
    relation: str


class RepoGraph(BaseModel):
    root: str
    nodes: list[GraphNode] = Field(default_factory=list)
    edges: list[GraphEdge] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=utc_now)

    def context_brief(
        self,
        limit: int = 20,
        query: str | None = None,
        learning_boosts: dict[str, float] | None = None,
        token_budget: int | None = None,
    ) -> str:
        nodes = self.nodes
        ranked_paths: list[str] = []
        if query:
            nodes = self._rank_nodes_bm25(query, learning_boosts=learning_boosts)
            ranked_paths = [node.path for node in nodes]
            nodes = self._expand_with_neighbors(nodes, limit=limit)
        nodes = self._apply_context_budget(nodes, limit=limit, token_budget=token_budget)

        lines = ["VOCR repo graph brief:"]
        if query:
            lines.append(f"Query: {query}")
        if token_budget is not None:
            lines.append(f"Token budget: {token_budget}")
        for node in nodes:
            symbol_text = ", ".join(node.symbols[:6]) or "no symbols"
            marker = ""
            if query:
                marker = " (seed)" if node.path in ranked_paths[:limit] else " (1-hop)"
            lines.append(f"- {node.path}{marker}: {node.summary} ({symbol_text})")
        if not nodes:
            lines.append("- no matching files")
        return "\n".join(lines)

    def _apply_context_budget(
        self,
        nodes: list["GraphNode"],
        *,
        limit: int,
        token_budget: int | None,
    ) -> list["GraphNode"]:
        if token_budget is None:
            return nodes[:limit]
        selected: list[GraphNode] = []
        used = 0
        for node in nodes:
            cost = max(8, len(node.path + node.summary + " ".join(node.symbols[:6])) // 4)
            if selected and used + cost > token_budget:
                break
            selected.append(node)
            used += cost
            if len(selected) >= limit:
                break
        return selected

    def _rank_nodes_bm25(
        self,
        query: str,
        learning_boosts: dict[str, float] | None = None,
    ) -> list[GraphNode]:
        query_terms = _tokenize(query)
        if not query_terms:
            return self.nodes

        documents = [(node, node.search_tokens or _tokenize(_node_search_text(node))) for node in self.nodes]
        if not documents:
            return []
        average_length = sum(len(tokens) for _, tokens in documents) / max(len(documents), 1)
        document_frequency: Counter[str] = Counter()
        for _, tokens in documents:
            document_frequency.update(set(tokens))

        scored: list[tuple[float, GraphNode]] = []
        for node, tokens in documents:
            if not tokens:
                continue
            frequencies = Counter(tokens)
            score = 0.0
            for term in query_terms:
                if frequencies[term] == 0:
                    continue
                idf = math.log(1 + (len(documents) - document_frequency[term] + 0.5) / (document_frequency[term] + 0.5))
                denominator = frequencies[term] + 1.2 * (1 - 0.75 + 0.75 * (len(tokens) / max(average_length, 1)))
                score += idf * ((frequencies[term] * 2.2) / denominator)
            if learning_boosts:
                score += learning_boosts.get(node.path, 0.0)
            score *= _path_weight(node.path)
            if score > 0:
                scored.append((score, node))
        return [node for _, node in sorted(scored, key=lambda item: (-item[0], item[1].path))]

    def _expand_with_neighbors(self, ranked: list[GraphNode], *, limit: int) -> list[GraphNode]:
        by_path = {node.path: node for node in self.nodes}
        selected: dict[str, GraphNode] = {}
        seeds = ranked[:limit]
        for node in seeds:
            selected[node.path] = node
        seed_paths = set(selected)
        for edge in self.edges:
            if edge.source in seed_paths and edge.target in by_path:
                selected.setdefault(edge.target, by_path[edge.target])
            if edge.target in seed_paths and edge.source in by_path:
                selected.setdefault(edge.source, by_path[edge.source])
        return list(selected.values())


def _tokenize(text: str) -> list[str]:
    return [token.lower() for token in re.findall(r"[A-Za-z0-9]+", text.replace("_", " ")) if len(token) > 1]


def _node_search_text(node: GraphNode) -> str:
    return " ".join([node.path, node.summary, " ".join(node.imports), " ".join(node.symbols)])


def _path_weight(path: str) -> float:
    lowered = path.lower()
    if lowered.endswith(".md") or lowered.startswith("docs/"):
        return 0.72
    return 1.0
