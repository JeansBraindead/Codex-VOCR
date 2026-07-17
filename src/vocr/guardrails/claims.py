from __future__ import annotations

import re
from pathlib import Path

from vocr.guardrails.scope_guard import ScopeGuard, _looks_like_path
from vocr.models import ClaimConflict, ScopeClaim, VocrTask


_EXTENSION_GLOB_RE = re.compile(r"^\*\.[A-Za-z0-9]+$")


def claim_root(glob: str) -> str:
    normalized = glob.strip().replace("\\", "/").lstrip("./")
    if _EXTENSION_GLOB_RE.match(normalized):
        # A bare extension glob like "*.md" has no path prefix at all; it is
        # not a whole-repo claim and must not collide with every other root.
        return f"filetype:{normalized.lower()}"
    wildcard_positions = [pos for pos in (normalized.find(char) for char in "*?[") if pos >= 0]
    if not wildcard_positions:
        return normalized.rstrip("/") or "."

    prefix = normalized[: min(wildcard_positions)]
    if prefix.endswith("/"):
        return prefix.rstrip("/") or "."
    if "/" in prefix:
        return prefix.rsplit("/", 1)[0] or "."
    return "."


def expand_scope_paths(repo_root: Path | str, globs: list[str]) -> set[str]:
    root = Path(repo_root)
    paths: set[str] = set()
    for pattern in globs:
        normalized = pattern.replace("\\", "/").lstrip("/")
        if not _looks_like_path(normalized):
            continue
        for path in root.glob(normalized):
            if path.is_file():
                paths.add(path.relative_to(root).as_posix())
    return paths


def build_scope_claim(task: VocrTask, repo_root: Path | str) -> ScopeClaim:
    globs = [item.replace("\\", "/") for item in ScopeGuard().scope_to_globs(task.scope)]
    roots = sorted({claim_root(item) for item in globs})
    expanded_paths = sorted(expand_scope_paths(repo_root, globs))
    return ScopeClaim(task_id=task.id, globs=globs, roots=roots, expanded_paths=expanded_paths)


def claims_conflict(a: ScopeClaim, b: ScopeClaim) -> bool:
    for left in a.roots:
        for right in b.roots:
            if _roots_overlap(left, right):
                return True
    return bool(set(a.expanded_paths).intersection(b.expanded_paths))


def claim_conflicts(candidate: ScopeClaim, active: list[ScopeClaim]) -> list[ClaimConflict]:
    conflicts: list[ClaimConflict] = []
    for existing in active:
        if claims_conflict(candidate, existing):
            conflicts.append(
                ClaimConflict(
                    task_id=candidate.task_id,
                    conflicting_task_id=existing.task_id,
                    reason="scope claim overlaps existing active claim",
                )
            )
    return conflicts


def _roots_overlap(left: str, right: str) -> bool:
    left = left.replace("\\", "/").strip("/") or "."
    right = right.replace("\\", "/").strip("/") or "."
    if left.startswith("filetype:") or right.startswith("filetype:"):
        # Filetype claims only collide with an identical filetype or with an
        # explicit whole-repo root, never with an unrelated directory root.
        return left == right or left == "." or right == "."
    if left == "." or right == ".":
        return True
    return left == right or left.startswith(f"{right}/") or right.startswith(f"{left}/")
