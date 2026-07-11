from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

from vocr.git.worktrees import GitWorktreeManager
from vocr.graph.graphify import GraphStore
from vocr.memory.ledger import MemoryLedger
from vocr.models import ReviewDecision
from vocr.orchestration.readiness import assess_request_readiness
from vocr.orchestration.workflow import (
    create_vision,
    organize_slice,
    promote_task,
    render_review_markdown,
    render_task_template,
    review_task,
)


SERVER_INFO = {"name": "vocr", "version": "0.1.0"}


TOOLS = [
    {
        "name": "vocr_status",
        "description": "Return a compact VOCR ledger status.",
        "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False},
    },
    {
        "name": "vocr_context",
        "description": "Return a token-efficient Graphify context pack.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "limit": {"type": "integer", "minimum": 1, "maximum": 50},
                "budget": {"type": "integer", "minimum": 1, "description": "Approximate token budget for the brief."},
            },
            "additionalProperties": False,
        },
    },
    {
        "name": "vocr_plan",
        "description": "Assess readiness and create plan-only VOCR tasks without dispatch or promote.",
        "inputSchema": {
            "type": "object",
            "properties": {"request": {"type": "string"}},
            "required": ["request"],
            "additionalProperties": False,
        },
    },
    {
        "name": "vocr_review",
        "description": "Run a gated VOCR review for a task. Does not promote.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "task_id": {"type": "string"},
                "decision": {"type": "string", "enum": ["needs_changes", "blocked", "accepted"]},
                "summary": {"type": "string"},
            },
            "required": ["task_id"],
            "additionalProperties": False,
        },
    },
    {
        "name": "vocr_promote_preview",
        "description": "Show merge/PR preview for an accepted task. Never merges.",
        "inputSchema": {
            "type": "object",
            "properties": {"task_id": {"type": "string"}},
            "required": ["task_id"],
            "additionalProperties": False,
        },
    },
    {
        "name": "vocr_promote",
        "description": "Promote an accepted task only when confirm is true. Uses the same gated promote path as the CLI.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "task_id": {"type": "string"},
                "confirm": {"type": "boolean"},
            },
            "required": ["task_id", "confirm"],
            "additionalProperties": False,
        },
    },
]


def serve_stdio(vocr_home: Path | str = ".vocr") -> None:
    server = VocrMcpServer(Path(vocr_home))
    for message, framed in _read_stdio_messages():
        response = server.handle(message)
        if response is not None:
            _write_stdio_response(response, framed=framed)


def _read_stdio_messages() -> Any:
    stream = sys.stdin.buffer
    while True:
        line = stream.readline()
        if not line:
            return
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.lower().startswith(b"content-length:"):
            length = int(stripped.split(b":", 1)[1].strip())
            while True:
                header = stream.readline()
                if header in {b"\r\n", b"\n", b""}:
                    break
            body = stream.read(length)
            yield json.loads(body.decode("utf-8")), True
            continue
        yield json.loads(stripped.decode("utf-8")), False


def _write_stdio_response(response: dict[str, Any], *, framed: bool) -> None:
    body = json.dumps(response)
    if framed:
        encoded = body.encode("utf-8")
        sys.stdout.buffer.write(f"Content-Length: {len(encoded)}\r\n\r\n".encode("ascii"))
        sys.stdout.buffer.write(encoded)
        sys.stdout.buffer.flush()
        return
    sys.stdout.write(body + "\n")
    sys.stdout.flush()


class VocrMcpServer:
    def __init__(self, vocr_home: Path) -> None:
        self.vocr_home = vocr_home

    def handle(self, request: dict[str, Any]) -> dict[str, Any] | None:
        method = request.get("method")
        request_id = request.get("id")
        try:
            if method == "initialize":
                return self._response(
                    request_id,
                    {
                        "protocolVersion": "2024-11-05",
                        "capabilities": {"tools": {}},
                        "serverInfo": SERVER_INFO,
                    },
                )
            if method == "notifications/initialized":
                return None
            if method == "tools/list":
                return self._response(request_id, {"tools": TOOLS})
            if method == "tools/call":
                params = request.get("params", {})
                return self._response(request_id, self._call_tool(params))
            return self._error(request_id, -32601, f"Unknown MCP method: {method}")
        except Exception as exc:
            return self._error(request_id, -32000, str(exc))

    def _call_tool(self, params: dict[str, Any]) -> dict[str, Any]:
        name = params.get("name")
        arguments = params.get("arguments") or {}
        if name == "vocr_status":
            return self._text_result(self._status_text())
        if name == "vocr_context":
            query = arguments.get("query")
            limit = int(arguments.get("limit", 20))
            budget = arguments.get("budget")
            token_budget = int(budget) if budget is not None else None
            store = GraphStore(self.vocr_home)
            if not store.exists():
                graph = store.refresh(".")
                context = graph.context_brief(query=query, limit=limit, token_budget=token_budget)
            else:
                context = store.context_pack(query=query, limit=limit, token_budget=token_budget)
            return self._text_result(context)
        if name == "vocr_plan":
            request = str(arguments.get("request", ""))
            readiness = assess_request_readiness(request)
            if not readiness.ready:
                questions = "\n".join(f"- {item.topic}: {item.question}" for item in readiness.questions)
                return self._text_result(f"VOCR is not ready to plan yet.\n{questions}")
            vision = create_vision(request)
            tasks = organize_slice(vision, vocr_home=str(self.vocr_home))
            task_text = "\n\n".join(render_task_template(task) for task in tasks)
            return self._text_result(f"Vision: {vision.goal}\n\n{task_text}")
        if name == "vocr_review":
            task_id = str(arguments.get("task_id", ""))
            decision_value = arguments.get("decision")
            decision = ReviewDecision(decision_value) if decision_value else None
            summary = arguments.get("summary")
            review = review_task(MemoryLedger(self.vocr_home), task_id, decision=decision, summary=summary)
            return self._text_result(render_review_markdown(review))
        if name == "vocr_promote_preview":
            task_id = str(arguments.get("task_id", ""))
            ledger = MemoryLedger(self.vocr_home)
            task = ledger.get_task(task_id)
            if task is None:
                return self._text_result(f"Task not found: {task_id}")
            if not task.branch_name:
                return self._text_result("Task has no branch to promote.")
            return self._text_result(GitWorktreeManager().merge_preview(task.branch_name))
        if name == "vocr_promote":
            task_id = str(arguments.get("task_id", ""))
            if arguments.get("confirm") is not True:
                return self._text_result(
                    "Promotion not started. Call vocr_promote with confirm=true after an accepted review."
                )
            promote_task(MemoryLedger(self.vocr_home), GitWorktreeManager(), task_id)
            return self._text_result(f"Task promoted: {task_id}")
        raise ValueError(f"Unknown VOCR tool: {name}")

    def _status_text(self) -> str:
        ledger = MemoryLedger(self.vocr_home)
        return "\n".join(
            [
                f"Slices: {len(ledger.slices())}",
                f"Tasks: {len(ledger.tasks())}",
                f"Reviews: {len(ledger.reviews())}",
                f"Telemetry events: {len(ledger.telemetry())}",
            ]
        )

    def _text_result(self, text: str) -> dict[str, Any]:
        return {"content": [{"type": "text", "text": text}]}

    def _response(self, request_id: Any, result: dict[str, Any]) -> dict[str, Any]:
        return {"jsonrpc": "2.0", "id": request_id, "result": result}

    def _error(self, request_id: Any, code: int, message: str) -> dict[str, Any]:
        return {"jsonrpc": "2.0", "id": request_id, "error": {"code": code, "message": message}}
