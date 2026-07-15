from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from vocr.models import CodexRunResult, VocrTask


@dataclass(slots=True)
class ScriptedAttempt:
    patches: list[tuple[str, str]] = field(default_factory=list)
    exit_code: int = 0
    stdout: str = ""
    stderr: str = ""


class ScriptedWorker:
    """Small in-process stand-in for CodexMcpClient.run_task()."""

    def __init__(self, attempts: list[ScriptedAttempt] | None = None) -> None:
        self.attempts = attempts or [ScriptedAttempt(stdout="scripted worker ok")]
        self.calls = 0

    def run_task(self, task: VocrTask, **_: object) -> CodexRunResult:
        if task.worktree_path is None:
            raise ValueError("Task must have worktree_path before ScriptedWorker can run.")
        attempt = self.attempts[min(self.calls, len(self.attempts) - 1)]
        self.calls += 1
        root = Path(task.worktree_path)
        for relpath, content in attempt.patches:
            target = root / relpath
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content, encoding="utf-8")
        return CodexRunResult(
            task_id=task.id,
            command=["scripted-worker"],
            exit_code=attempt.exit_code,
            stdout=attempt.stdout,
            stderr=attempt.stderr,
        )
