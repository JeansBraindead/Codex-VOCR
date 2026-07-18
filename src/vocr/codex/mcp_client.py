from __future__ import annotations

import os
import shlex
import subprocess
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from vocr.codex.config import codex_available
from vocr.models import BaselineCheck, CodexRunResult, PermissionGrant, PermissionMode, TaskContract, VocrTask
from vocr.orchestration.workflow import (
    normalize_check_command,
    render_contract_task_prompt,
    render_legacy_task_template,
    render_task_template,
)


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
        extra_prompt: str | None = None,
    ) -> CodexDispatchPayload:
        """Build the worker prompt.

        In contract mode the stable prefix is byte-identical across tasks; volatile
        bounded-retry context is appended only at the end.
        """
        if task.worktree_path is None:
            raise ValueError("Task must be dispatched to a worktree before Codex can run.")
        if os.getenv("VOCR_PROMPT_MODE", "legacy").lower() == "contract":
            prompt = render_contract_task_prompt(include_context_pack=extra_prompt is None)
        else:
            prompt = render_task_template(task)
        if extra_prompt:
            prompt = f"{prompt}\n\n## Bounded retry context\n\n{extra_prompt}"
        return CodexDispatchPayload(
            task_id=task.id,
            worktree_path=str(task.worktree_path),
            prompt=prompt,
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
        baseline_checks = _collect_baseline_checks(task) if _baseline_checks_enabled() else []
        contract_path = target.parent / "VOCR_TASK.json"
        contract_path.write_text(
            TaskContract.from_task(task, baseline_checks=baseline_checks).model_dump_json(indent=2),
            encoding="utf-8",
        )
        if task.context_pack:
            context_path = target.parent / "CONTEXT_PACK.txt"
            context_path.write_text(task.context_pack, encoding="utf-8")
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
                    render_legacy_task_template(task),
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
        extra_prompt: str | None = None,
        on_output: Callable[[str], None] | None = None,
    ) -> CodexRunResult:
        payload = self.build_payload(task, permission=permission, extra_prompt=extra_prompt)
        command = self._resolve_command(payload, permission)
        if not command:
            raise RuntimeError(
                "No Codex worker command available. Install Codex CLI or set VOCR_CODEX_COMMAND."
            )

        try:
            proc = subprocess.Popen(
                command,
                cwd=payload.worktree_path,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                errors="replace",
                bufsize=1,
            )
        except OSError as exc:
            return CodexRunResult(
                task_id=task.id,
                command=command,
                exit_code=1,
                stdout="",
                stderr=f"Worker could not be started: {exc}",
            )

        def _write_stdin() -> None:
            # Writing on a separate thread avoids a classic pipe deadlock:
            # a large prompt could fill the stdin buffer before Codex starts
            # reading it, while Codex's own stdout buffer fills up because we
            # have not started draining it yet.
            try:
                if proc.stdin is not None:
                    proc.stdin.write(payload.prompt)
                    proc.stdin.close()
            except (BrokenPipeError, OSError):
                pass

        threading.Thread(target=_write_stdin, daemon=True).start()

        timed_out = threading.Event()

        def _kill_on_timeout() -> None:
            timed_out.set()
            proc.kill()

        timer = threading.Timer(timeout_seconds, _kill_on_timeout)
        timer.start()
        collected: list[str] = []
        try:
            with proc:
                if proc.stdout is not None:
                    for line in proc.stdout:
                        stripped = line.rstrip("\n")
                        collected.append(stripped)
                        if on_output:
                            on_output(stripped)
                exit_code = proc.wait()
        finally:
            timer.cancel()

        if timed_out.is_set():
            collected.append(f"[vocr] Worker timed out after {timeout_seconds}s and was killed.")
            exit_code = 124

        return CodexRunResult(
            task_id=task.id,
            command=command,
            exit_code=exit_code,
            stdout="\n".join(collected),
            stderr="",
        )

    def _resolve_command(
        self,
        payload: CodexDispatchPayload,
        permission: PermissionGrant | None,
    ) -> list[str]:
        if self.command:
            return shlex.split(self.command)
        if not codex_available():
            return []

        command = [
            "codex",
            "exec",
            "-",
            "--cd",
            payload.worktree_path,
            "--sandbox",
            "workspace-write",
            "--color",
            "never",
        ]
        profile = os.getenv("VOCR_CODEX_PROFILE", "safe").lower()
        if profile == "unsandboxed" or os.getenv("VOCR_CODEX_UNSANDBOXED", "").lower() in {"1", "true", "yes"}:
            command.append("--dangerously-bypass-approvals-and-sandbox")
        return command


def _baseline_checks_enabled() -> bool:
    return os.getenv("VOCR_BASELINE_CHECKS", "").strip().lower() in {"1", "true", "yes", "on"}


def _collect_baseline_checks(task: VocrTask) -> list[BaselineCheck]:
    checks: list[BaselineCheck] = []
    for check in task.tests:
        command = normalize_check_command(check)
        if command is None:
            checks.append(
                BaselineCheck(
                    command=check,
                    status="manual",
                    summary="No safe automatic command mapped for this check.",
                )
            )
            continue
        command_text = " ".join(command)
        try:
            completed = subprocess.run(
                command,
                cwd=task.worktree_path,
                text=True,
                encoding="utf-8",
                errors="replace",
                capture_output=True,
                check=False,
                timeout=300,
            )
        except (subprocess.TimeoutExpired, OSError) as exc:
            checks.append(BaselineCheck(command=command_text, status="error", summary=_summarize_check_output(str(exc))))
            continue
        output = "\n".join(part for part in [completed.stdout.strip(), completed.stderr.strip()] if part)
        checks.append(
            BaselineCheck(
                command=command_text,
                status="passed" if completed.returncode == 0 else "failed",
                summary=_summarize_check_output(output or f"exit_code={completed.returncode}"),
            )
        )
    return checks


def _summarize_check_output(text: str, max_chars: int = 200) -> str:
    summary = " ".join(text.split())
    if len(summary) <= max_chars:
        return summary
    return summary[: max_chars - 3].rstrip() + "..."
