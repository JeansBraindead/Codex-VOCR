from __future__ import annotations

import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch

from vocr.git.worktrees import WorktreeInfo
from vocr.guardrails.claims import build_scope_claim, claim_root, claims_conflict, expand_scope_paths
from vocr.memory.ledger import MemoryLedger
from vocr.models import AcceptanceCriterion, LedgerEventType, ScopeClaim, TaskStatus, VocrTask
from vocr.orchestration.workflow import dispatch_task, promote_task


def make_task(task_id: str, scope: list[str]) -> VocrTask:
    return VocrTask(
        id=task_id,
        slice_id="slice-claims",
        title=f"Task {task_id}",
        summary="Exercise scope claims.",
        scope=scope,
        acceptance_criteria=[AcceptanceCriterion(text="Claim is handled")],
        tests=["manual review"],
    )


class ClaimTests(unittest.TestCase):
    def test_claim_root_keeps_exact_files_and_directory_wildcard_roots(self) -> None:
        self.assertEqual(claim_root("src/api/**"), "src/api")
        self.assertEqual(claim_root("src/vocr/models.py"), "src/vocr/models.py")
        self.assertEqual(claim_root("src/api/mod*.py"), "src/api")
        self.assertEqual(claim_root("src/**/models.py"), "src")
        self.assertEqual(claim_root("mod*.py"), ".")

    def test_claim_conflict_distinguishes_disjoint_roots_and_exact_files(self) -> None:
        api = ScopeClaim(task_id="ta1", globs=["src/api/**"], roots=[claim_root("src/api/**")], expanded_paths=[])
        cli = ScopeClaim(task_id="ta2", globs=["src/cli/**"], roots=[claim_root("src/cli/**")], expanded_paths=[])
        x_file = ScopeClaim(task_id="ta3", globs=["a/x.py"], roots=[claim_root("a/x.py")], expanded_paths=[])
        y_file = ScopeClaim(task_id="ta4", globs=["a/y.py"], roots=[claim_root("a/y.py")], expanded_paths=[])
        a_tree = ScopeClaim(task_id="ta5", globs=["a/**"], roots=[claim_root("a/**")], expanded_paths=[])
        same_x_file = ScopeClaim(task_id="ta6", globs=["a/x.py"], roots=[claim_root("a/x.py")], expanded_paths=[])

        self.assertFalse(claims_conflict(api, cli))
        self.assertFalse(claims_conflict(x_file, y_file))
        self.assertTrue(claims_conflict(x_file, a_tree))
        self.assertTrue(claims_conflict(x_file, same_x_file))

    def test_claim_conflict_catches_overlapping_globs_and_disjoint_trees(self) -> None:
        first = ScopeClaim(task_id="ta1", globs=["src/api/**"], roots=[claim_root("src/api/**")], expanded_paths=[])
        second = ScopeClaim(task_id="ta2", globs=["src/**/models.py"], roots=[claim_root("src/**/models.py")], expanded_paths=[])
        third = ScopeClaim(task_id="ta3", globs=["docs/**"], roots=[claim_root("docs/**")], expanded_paths=[])
        future_file = ScopeClaim(task_id="ta4", globs=["src/api/new.py"], roots=[claim_root("src/api/new.py")], expanded_paths=[])

        self.assertTrue(claims_conflict(first, second))
        self.assertTrue(claims_conflict(first, future_file))
        self.assertFalse(claims_conflict(first, third))

    def test_expand_scope_paths_uses_real_tree(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "src" / "api").mkdir(parents=True)
            (root / "src" / "api" / "models.py").write_text("x = 1\n", encoding="utf-8")

            paths = expand_scope_paths(root, ["src/**/*.py"])

        self.assertEqual(paths, {"src/api/models.py"})

    def test_concurrent_claim_acquire_allows_only_one_winner(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "src").mkdir()
            (root / "src" / "main.py").write_text("x = 1\n", encoding="utf-8")
            ledger_a = MemoryLedger(root / ".vocr")
            ledger_b = MemoryLedger(root / ".vocr")
            results: list[list] = []

            def acquire(ledger: MemoryLedger, task_id: str) -> None:
                results.append(ledger.acquire_claims([make_task(task_id, ["src/**"])], repo_root=root))

            first = threading.Thread(target=acquire, args=(ledger_a, "ta1"))
            second = threading.Thread(target=acquire, args=(ledger_b, "ta2"))
            first.start()
            second.start()
            first.join()
            second.join()

            active = MemoryLedger(root / ".vocr").active_claims()

        self.assertEqual(len(active), 1)
        self.assertEqual(sum(1 for item in results if not item), 1)
        self.assertEqual(sum(1 for item in results if item), 1)

    def test_release_and_stale_reconcile_clear_active_claims(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            ledger = MemoryLedger(root / ".vocr")
            task = make_task("ta1", ["docs/**"])
            ledger.append(LedgerEventType.task_created, task)
            self.assertEqual(ledger.acquire_claims([task], repo_root=root), [])

            ledger.release_claim(task.id)
            after_release = ledger.active_claims()
            ledger.acquire_claims([task], repo_root=root)
            ledger.append(LedgerEventType.task_aborted, {"task_id": task.id})
            released = ledger.reconcile_stale_claims()

        self.assertEqual(after_release, [])
        self.assertEqual(released, [task.id])

    def test_dispatch_default_does_not_emit_claim_events(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ledger = MemoryLedger(Path(tmp) / ".vocr")
            task = make_task("ta1", ["docs/**"])
            ledger.append(LedgerEventType.task_created, task)

            class FakeManager:
                def create_for_task(self, task_id: str) -> WorktreeInfo:
                    return WorktreeInfo(task_id=task_id, branch_name=f"vocr/{task_id}", path=Path(tmp) / "worktree")

            dispatch_task(ledger, FakeManager(), task.id)  # type: ignore[arg-type]
            claim_events = [
                event
                for event in ledger.events()
                if event.type in {LedgerEventType.claim_acquired, LedgerEventType.claim_released}
            ]

        self.assertEqual(claim_events, [])

    def test_promote_releases_claim_after_merge(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            ledger = MemoryLedger(root / ".vocr")
            task = make_task("ta1", ["docs/**"])
            ledger.append(LedgerEventType.task_created, task)
            ledger.append(LedgerEventType.task_dispatched, {"task_id": task.id, "branch_name": "vocr/ta1", "worktree_path": str(root)})
            ledger.append(LedgerEventType.review_recorded, {"task_id": task.id, "decision": "accepted", "summary": "ok"})
            ledger.acquire_claims([task], repo_root=root)

            class FakeManager:
                def preflight_merge(self, branch_name: str) -> list[str]:
                    return []

                def merge_task_branch(self, branch_name: str) -> None:
                    return None

            promote_task(ledger, FakeManager(), task.id)  # type: ignore[arg-type]

        self.assertEqual(MemoryLedger(root / ".vocr").active_claims(), [])


if __name__ == "__main__":
    unittest.main()
