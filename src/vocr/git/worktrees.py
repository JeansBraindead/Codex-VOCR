from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass
from pathlib import Path
from shutil import which


class GitWorktreeError(RuntimeError):
    pass


MIN_GIT_VERSION_FOR_MERGE_TREE = (2, 38)


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

    def revert_commit(self, commit_sha: str) -> str:
        self.ensure_git_repo()
        result = self._git("revert", "--no-edit", commit_sha)
        if result.returncode != 0:
            raise GitWorktreeError(result.stderr.strip() or result.stdout.strip())
        sha_result = self._git("rev-parse", "HEAD")
        if sha_result.returncode != 0:
            raise GitWorktreeError(sha_result.stderr.strip() or sha_result.stdout.strip())
        return sha_result.stdout.strip()

    def merge_preview(self, branch_name: str) -> str:
        self.ensure_git_repo()
        stat = self._git("diff", "--stat", f"HEAD...{branch_name}")
        log = self._git("log", "--oneline", f"HEAD..{branch_name}")
        return "\n".join(
            part
            for part in [
                "Commits:",
                log.stdout.strip() or "no new commits",
                "",
                "Diff stat:",
                stat.stdout.strip() or "no diff",
            ]
            if part is not None
        )

    def create_pull_request(self, branch_name: str, title: str, body: str, draft: bool = True) -> str:
        if which("gh") is None:
            raise GitWorktreeError("GitHub CLI `gh` is not available for PR creation.")
        command = ["gh", "pr", "create", "--head", branch_name, "--title", title, "--body", body]
        if draft:
            command.append("--draft")
        result = subprocess.run(command, cwd=self.repo_root, text=True, capture_output=True, check=False)
        if result.returncode != 0:
            raise GitWorktreeError(result.stderr.strip() or result.stdout.strip())
        return result.stdout.strip()

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

    def diff(self, base_ref: str | None = None) -> str:
        result = self._diff_against_base("", base_ref=base_ref)
        committed = "" if result is None else result.stdout.strip()
        uncommitted = self._git("diff")
        parts = []
        if committed:
            parts.append(committed)
        if uncommitted.returncode == 0 and uncommitted.stdout.strip():
            parts.append(uncommitted.stdout.strip())
        return "\n\n".join(parts) or "no diff"

    def diff_for_scan(self, base_ref: str | None = None) -> str:
        parts = [self.diff(base_ref=base_ref)]
        untracked = self._git("ls-files", "--others", "--exclude-standard")
        if untracked.returncode == 0:
            for line in untracked.stdout.splitlines():
                rel = line.strip().replace("\\", "/")
                if not rel:
                    continue
                path = self.repo_root / rel
                if not path.is_file() or path.stat().st_size > 200_000:
                    continue
                text = path.read_text(encoding="utf-8", errors="ignore")
                added = "\n".join(f"+{item}" for item in text.splitlines())
                parts.append(f"diff --git a/{rel} b/{rel}\n+++ b/{rel}\n@@ -0,0 +1 @@\n{added}")
        return "\n\n".join(part for part in parts if part and part != "no diff") or "no diff"

    def branch_diff_stat(self, base_ref: str | None = None) -> str:
        result = self._diff_against_base("--stat", base_ref=base_ref)
        if result is None:
            return "no committed diff base found"
        return result.stdout.strip() or "no committed diff"

    def branch_diff_files(self, base_ref: str | None = None) -> list[str]:
        result = self._diff_against_base("--name-only", base_ref=base_ref)
        if result is None:
            return []
        return [line.strip().replace("\\", "/") for line in result.stdout.splitlines() if line.strip()]

    def _diff_against_base(self, mode: str, base_ref: str | None = None) -> subprocess.CompletedProcess[str] | None:
        candidates = [item for item in [base_ref, "main", "master", "HEAD~1"] if item]
        for candidate in candidates:
            args = ["diff"]
            if mode:
                args.append(mode)
            args.append(f"{candidate}...HEAD")
            result = self._git(*args)
            if result.returncode == 0:
                return result
            args = ["diff"]
            if mode:
                args.append(mode)
            args.extend([candidate, "HEAD"])
            result = self._git(*args)
            if result.returncode == 0:
                return result
        return None

    def changed_files(self) -> list[str]:
        result = self._git("status", "--porcelain")
        if result.returncode != 0:
            return []
        files: list[str] = []
        for line in result.stdout.splitlines():
            if not line.strip():
                continue
            path = line[3:].strip()
            if " -> " in path:
                path = path.split(" -> ", 1)[1]
            files.append(path.replace("\\", "/"))
        return files

    def has_changes(self) -> bool:
        return self.status_porcelain() != "clean"

    def commit_all(self, message: str) -> str:
        self.ensure_git_repo()
        if not self.has_changes():
            raise GitWorktreeError("No changes to commit.")
        add_result = self._git("add", "--all")
        if add_result.returncode != 0:
            raise GitWorktreeError(add_result.stderr.strip() or add_result.stdout.strip())
        commit_result = self._git("commit", "-m", message)
        if commit_result.returncode != 0:
            raise GitWorktreeError(commit_result.stderr.strip() or commit_result.stdout.strip())
        sha_result = self._git("rev-parse", "HEAD")
        if sha_result.returncode != 0:
            raise GitWorktreeError(sha_result.stderr.strip() or sha_result.stdout.strip())
        return sha_result.stdout.strip()

    def branch_exists(self, branch_name: str) -> bool:
        result = self._git("rev-parse", "--verify", branch_name)
        return result.returncode == 0

    def git_version(self) -> tuple[int, int] | None:
        result = self._git("--version")
        if result.returncode != 0:
            return None
        match = re.search(r"(\d+)\.(\d+)", result.stdout)
        if not match:
            return None
        return (int(match.group(1)), int(match.group(2)))

    def preflight_merge(self, branch_name: str) -> list[str]:
        self.ensure_git_repo()
        issues: list[str] = []
        if self.status_porcelain() != "clean":
            issues.append("main worktree is not clean")
        if not self.branch_exists(branch_name):
            issues.append(f"branch does not exist: {branch_name}")

        version = self.git_version()
        if version is not None and version < MIN_GIT_VERSION_FOR_MERGE_TREE:
            raise GitWorktreeError(
                "Merge preflight needs git >= "
                f"{'.'.join(map(str, MIN_GIT_VERSION_FOR_MERGE_TREE))} for the two-argument "
                f"`git merge-tree` real-merge mode; found {'.'.join(map(str, version))}. "
                "Upgrade git before promoting."
            )

        if not issues:
            result = self._git("merge-tree", "HEAD", branch_name)
            output = result.stdout + result.stderr
            if result.returncode != 0:
                issues.append(output.strip() or "merge-tree preflight failed")
            elif "<<<<<<<" in output or "changed in both" in output:
                issues.append("merge preflight reports possible conflicts")
        return issues

    def remove_worktree(self, path: Path | str, *, force: bool = False) -> None:
        self.ensure_git_repo()
        command = ["worktree", "remove"]
        if force:
            command.append("--force")
        command.append(str(path))
        result = self._git(*command)
        if result.returncode != 0:
            raise GitWorktreeError(result.stderr.strip() or result.stdout.strip())

    def prune_worktrees(self) -> str:
        self.ensure_git_repo()
        result = self._git("worktree", "prune")
        if result.returncode != 0:
            raise GitWorktreeError(result.stderr.strip() or result.stdout.strip())
        return result.stdout.strip() or "git worktree prune complete"

    def doctor(self) -> dict[str, str]:
        result = self._git("rev-parse", "--is-inside-work-tree")
        return {
            "git_repo": "yes" if result.returncode == 0 else "no",
            "worktree_root": str(self.worktree_root),
        }
