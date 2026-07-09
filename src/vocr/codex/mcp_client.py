from __future__ import annotations

import os
import shlex
import subprocess
from dataclasses import dataclass
from pathlib import Path

from vocr.models import CodexRunResult, PermissionGrant, PermissionMode, VocrTask
from vocr.orchestration.workflow import render_task_template


@dataclass(slots=True)
class CodexDispatchPayload:
    task_id: str
    worktree_path: str
    prompt: str
    permission_mode: str
    permission_scope: str | None = None


class CodexMcpClient:
    """Adapter boundary for the future Codex CLI MCP server."""

    def __init__(self, command: str | None = None) -> None:
        self.command = command if command is not None else os.getenv("VOCR_CODEX_COMMAND")

    def build_payload(
        self,
        task: VocrTask,
        permission: PermissionGrant | None = None,
    ) -> CodexDispatchPayload:
        if task.worktree_path is None:
            raise ValueError("Task must be dispatched to a worktree before Codex can run.")
        return CodexDispatchPayload(
            task_id=task.id,
            worktree_path=str(task.worktree_path),
            prompt=render_task_template(task),
            permission_mode=(permission.mode.value if permission else PermissionMode.ask_each_time.value),
            permission_scope=(permission.scope if permission else None),
        )

    def write_manifest(
        self,
        task: VocrTask,
        permission: PermissionGrant | None = None,
        filename: str = ".vocr/VOCR_TASK.md",
    ) -> Path:
        payload = self.build_payload(task, permission=permission)
        target = Path(payload.worktree_path) / filename
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(
            "\n".join(
                [
                    f"# VOCR Task {payload.task_id}",
                    "",
                    f"Permission mode: `{payload.permission_mode}`",
                    f"Permission scope: `{payload.permission_scope or 'none'}`",
                    "",
                    "## Prompt",
                    "",
                    payload.prompt,
                ]
            ),
            encoding="utf-8",
        )
        return target

    def run_task(
        self,
        task: VocrTask,
        permission: PermissionGrant | None = None,
        timeout_seconds: int = 3600,
    ) -> CodexRunResult:
        if not self.command:
            raise RuntimeError(
                "VOCR_CODEX_COMMAND is not set. Configure the real Codex CLI/MCP worker command first."
            )
        payload = self.build_payload(task, permission=permission)
        command = shlex.split(self.command)
        if not command:
            raise RuntimeError("VOCR_CODEX_COMMAND is empty.")

        completed = subprocess.run(
            command,
            cwd=payload.worktree_path,
            input=payload.prompt,
            text=True,
            capture_output=True,
            timeout=timeout_seconds,
            check=False,
        )
        return CodexRunResult(
            task_id=task.id,
            command=command,
            exit_code=completed.returncode,
            stdout=completed.stdout,
            stderr=completed.stderr,
        )
