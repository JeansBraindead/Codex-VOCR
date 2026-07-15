from __future__ import annotations

import json
import subprocess
from pathlib import Path
from shutil import which

from pydantic import ValidationError

from vocr.models import CodexReviewReport, MemoryNote, ReviewComment, TaskContract, VocrTask


def run_codex_review(
    task: VocrTask,
    base_ref: str | None = None,
    timeout_seconds: int = 900,
) -> list[ReviewComment]:
    comments, _ = run_codex_review_with_notes(task, base_ref=base_ref, timeout_seconds=timeout_seconds)
    return comments


def run_codex_review_with_notes(
    task: VocrTask,
    base_ref: str | None = None,
    timeout_seconds: int = 900,
) -> tuple[list[ReviewComment], list[MemoryNote]]:
    if task.worktree_path is None or which("codex") is None:
        return [], []

    command = _review_command(base_ref)
    prompt = _review_prompt(task)
    first_body = _run_review_command(command, task.worktree_path, prompt, timeout_seconds)
    if not first_body:
        return [], []

    report, error = _parse_review_report(first_body)
    if report is None:
        retry_prompt = _retry_prompt(error or "Response did not match CodexReviewReport JSON schema.")
        retry_body = _run_review_command(command, task.worktree_path, retry_prompt, timeout_seconds)
        if retry_body:
            report, _ = _parse_review_report(retry_body)
            if report is not None:
                return _report_to_comments(report), report.memory_notes
            return [ReviewComment(source="codex-review-unstructured", body=retry_body[-4000:])], []
        return [ReviewComment(source="codex-review-unstructured", body=first_body[-4000:])], []

    return _report_to_comments(report), report.memory_notes


def _review_command(base_ref: str | None) -> list[str]:
    command = ["codex", "exec", "review", "--color", "never"]
    if base_ref:
        command.extend(["--base", base_ref])
    else:
        command.append("--uncommitted")
    command.append("-")
    return command


def _review_prompt(task: VocrTask) -> str:
    contract_json = TaskContract.from_task(task).model_dump_json(indent=2)
    schema = {
        "schema_version": 1,
        "decision": "accepted | needs_changes | blocked",
        "summary": "short review summary",
        "findings": [
            {
                "severity": "low | medium | high",
                "path": "repo-relative path or null",
                "line": "line number or null",
                "body": "specific finding",
            }
        ],
        "memory_notes": [
            {
                "kind": "decision | convention | term | check | rejected_path",
                "text": "optional compact project memory note, max 300 chars",
                "refs": ["optional repo-relative files or task ids"],
            }
        ],
    }
    return "\n".join(
        [
            "Review this VOCR task precisely.",
            "Focus only on bugs, failed acceptance criteria, scope drift, missing tests, and security risk.",
            "Reply only with one JSON object matching this compact CodexReviewReport schema.",
            "Do not include prose, Markdown, or code fences.",
            "",
            "Schema:",
            json.dumps(schema, separators=(",", ":")),
            "",
            "Task contract JSON:",
            contract_json,
            "",
            "The decision field is advisory only and never accepts or promotes the task.",
        ]
    )


def _retry_prompt(error: str) -> str:
    return "\n".join(
        [
            "Your previous review response was invalid.",
            "Return only a valid JSON object matching CodexReviewReport.",
            "Do not include prose, Markdown, or code fences.",
            "",
            "Validation error:",
            error[:2000],
        ]
    )


def _run_review_command(
    command: list[str],
    worktree_path: Path,
    prompt: str,
    timeout_seconds: int,
) -> str:
    completed = subprocess.run(
        command,
        cwd=Path(worktree_path),
        input=prompt,
        text=True,
        capture_output=True,
        timeout=timeout_seconds,
        check=False,
    )
    return "\n".join(part for part in [completed.stdout.strip(), completed.stderr.strip()] if part).strip()


def _parse_review_report(body: str) -> tuple[CodexReviewReport | None, str | None]:
    try:
        return CodexReviewReport.model_validate_json(_strip_json_fence(body)), None
    except ValidationError as exc:
        return None, str(exc)


def _strip_json_fence(body: str) -> str:
    text = body.strip()
    if not text.startswith("```"):
        return text
    lines = text.splitlines()
    if lines and lines[0].strip().startswith("```"):
        lines = lines[1:]
    if lines and lines[-1].strip() == "```":
        lines = lines[:-1]
    return "\n".join(lines).strip()


def _report_to_comments(report: CodexReviewReport) -> list[ReviewComment]:
    comments = [
        ReviewComment(
            source="codex-review",
            body=f"Advisor decision: {report.decision.value}. {report.summary}",
        )
    ]
    for finding in report.findings:
        comments.append(
            ReviewComment(
                source="codex-review",
                path=finding.path,
                line=finding.line,
                body=f"[{finding.severity.value}] {finding.body}",
            )
        )
    return comments
