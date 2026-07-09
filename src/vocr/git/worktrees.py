from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path


class GitWorktreeError(RuntimeError):
    pass


@dataclass(slots=True)
class WorktreeInfo:
    task_id: str
    branch_name: str
    path: Path


class GitWorktreeManager:
    def __init__(self, repo_root: Path | str = ".", worktree_root: Path | str | None = None) -> None:
        self.repo_root = Path(repo_root)
        if worktree_root is None:
            resolved_root = self.repo_root.resolve()
            self.worktree_root = resolved_root.parent / f"{resolved_root.name}.vocr-worktrees"
        else:
            self.worktree_root = Path(worktree_root)

    def _git(self, *args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            ["git", *args],
            cwd=self.repo_root,
            text=True,
            capture_output=True,
            check=False,
        )

    def ensure_git_repo(self) -> None:
        result = self._git("rev-parse", "--show-toplevel")
        if result.returncode != 0:
            raise GitWorktreeError("VOCR needs a git repository for worktree operations.")

    def create_for_task(self, task_id: str) -> WorktreeInfo:
        self.ensure_git_repo()
        self.worktree_root.mkdir(parents=True, exist_ok=True)
        branch_name = f"vocr/{task_id}"
        path = self.worktree_root / task_id
        result = self._git("worktree", "add", "-b", branch_name, str(path))
        if result.returncode != 0:
            raise GitWorktreeError(result.stderr.strip() or result.stdout.strip())
        return WorktreeInfo(task_id=task_id, branch_name=branch_name, path=path)

    def merge_task_branch(self, branch_name: str) -> None:
        self.ensure_git_repo()
        result = self._git("merge", "--no-ff", branch_name)
        if result.returncode != 0:
            raise GitWorktreeError(result.stderr.strip() or result.stdout.strip())

    def status_porcelain(self) -> str:
        result = self._git("status", "--porcelain")
        if result.returncode != 0:
            return result.stderr.strip() or result.stdout.strip()
        return result.stdout.strip() or "clean"

    def diff_stat(self) -> str:
        result = self._git("diff", "--stat")
        if result.returncode != 0:
            return result.stderr.strip() or result.stdout.strip()
        return result.stdout.strip() or "no uncommitted diff"

    def branch_exists(self, branch_name: str) -> bool:
        result = self._git("rev-parse", "--verify", branch_name)
        return result.returncode == 0

    def preflight_merge(self, branch_name: str) -> list[str]:
        self.ensure_git_repo()
        issues: list[str] = []
        if self.status_porcelain() != "clean":
            issues.append("main worktree is not clean")
        if not self.branch_exists(branch_name):
            issues.append(f"branch does not exist: {branch_name}")

        if not issues:
            result = self._git("merge-tree", "HEAD", branch_name)
            output = result.stdout + result.stderr
            if result.returncode != 0:
                issues.append(output.strip() or "merge-tree preflight failed")
            elif "<<<<<<<" in output or "changed in both" in output:
                issues.append("merge preflight reports possible conflicts")
        return issues

    def doctor(self) -> dict[str, str]:
        result = self._git("rev-parse", "--is-inside-work-tree")
        return {
            "git_repo": "yes" if result.returncode == 0 else "no",
            "worktree_root": str(self.worktree_root),
        }
