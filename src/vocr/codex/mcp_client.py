from __future__ import annotations

import os
import shlex
import subprocess
from dataclasses import dataclass
from pathlib import Path

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
    ) -> CodexRunResult:
        payload = self.build_payload(task, permission=permission, extra_prompt=extra_prompt)
        command = self._resolve_command(payload, permission)
        if not command:
            raise RuntimeError(
                "No Codex worker command available. Install Codex CLI or set VOCR_CODEX_COMMAND."
            )

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
        if permission and permission.mode == PermissionMode.approve_all:
            command.extend(["--ask-for-approval", "never"])
        elif profile == "unattended":
            command.extend(["--ask-for-approval", "never"])
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
