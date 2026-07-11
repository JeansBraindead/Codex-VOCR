from __future__ import annotations

import subprocess
from shutil import which
from pathlib import Path

from vocr.models import ReviewComment, VocrTask


def run_codex_review(task: VocrTask, base_ref: str | None = None, timeout_seconds: int = 900) -> ReviewComment | None:
    if task.worktree_path is None or which("codex") is None:
        return None

    command = ["codex", "exec", "review", "--color", "never"]
    if base_ref:
        command.extend(["--base", base_ref])
    else:
        command.append("--uncommitted")
    command.append("-")

    prompt = (
        "Review this VOCR task precisely. Focus only on bugs, failed acceptance criteria, "
        "scope drift, missing tests, and security risk. Be concise.\n\n"
        f"Task: {task.title}\n"
        f"Scope: {task.scope}\n"
        f"Non-goals: {task.non_goals}\n"
        f"Acceptance: {[item.text for item in task.acceptance_criteria]}\n"
    )
    try:
        completed = subprocess.run(
            command,
            cwd=Path(task.worktree_path),
            input=prompt,
            text=True,
            capture_output=True,
            timeout=timeout_seconds,
            check=False,
        )
    except (subprocess.TimeoutExpired, OSError):
        return None
    body = "\n".join(part for part in [completed.stdout.strip(), completed.stderr.strip()] if part).strip()
    if not body:
        return None
    return ReviewComment(source="codex-review", body=body[-4000:])
