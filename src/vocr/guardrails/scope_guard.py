from __future__ import annotations

from pathlib import Path

from vocr.models import ScopePolicy, VocrTask


class ScopeGuard:
    def validate_task(self, task: VocrTask) -> list[str]:
        issues: list[str] = []
        if not task.scope:
            issues.append("Task has no scope.")
        if not task.acceptance_criteria:
            issues.append("Task has no acceptance criteria.")
        if not task.tests:
            issues.append("Task has no tests or verification steps.")
        return issues

    def path_allowed(self, task: VocrTask, path: Path) -> bool:
        if not task.worktree_path:
            return False
        try:
            path.resolve().relative_to(task.worktree_path.resolve())
        except ValueError:
            return False
        return True

    def build_worker_policy(self, task: VocrTask) -> ScopePolicy:
        allowed_root = str(task.worktree_path) if task.worktree_path else "DISPATCH_REQUIRED"
        return ScopePolicy(
            task_id=task.id,
            allowed_roots=[allowed_root],
            notes=[
                "Worker writes must stay inside the isolated task worktree.",
                "Promotion still requires accepted review.",
            ],
        )

    def write_worker_policy(self, task: VocrTask, filename: str = ".vocr/scope.json") -> Path:
        if task.worktree_path is None:
            raise ValueError("Task must have a worktree before writing scope policy.")
        target = task.worktree_path / filename
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(self.build_worker_policy(task).model_dump_json(indent=2), encoding="utf-8")
        return target

    def validate_changed_files(self, task: VocrTask, changed_files: list[str]) -> list[str]:
        policy = self.build_worker_policy(task)
        issues: list[str] = []
        denied = [item.replace("\\", "/").rstrip("/") for item in policy.denied_roots]
        for changed in changed_files:
            normalized = changed.replace("\\", "/").lstrip("/")
            for denied_root in denied:
                if normalized == denied_root or normalized.startswith(f"{denied_root}/"):
                    issues.append(f"Changed file is denied by scope policy: {normalized}")
        return issues
