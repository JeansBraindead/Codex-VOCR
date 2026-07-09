from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from vocr.graph.graphify import GraphStore, RepoGraphBuilder
from vocr.guardrails.scope_guard import ScopeGuard
from vocr.memory.ledger import sanitize_payload
from vocr.models import AcceptanceCriterion, VocrTask
from vocr.orchestration.workflow import create_vision, organize_slice

GOOD_REQUEST = (
    "Ziel: Baue eine Healthcheck-API im Backend. "
    "Arbeitsbereich: FastAPI-App; Tests. "
    "Akzeptanz: GET /health liefert 200; JSON status=ok. "
    "Verifikation: Syntax-Check. "
    "Nicht-Ziele: keine Auth; keine Deployment-Aenderungen. "
    "Ausfuehrung: mit go Worktree vorbereiten; Review vor Promote."
)


class WorkflowTests(unittest.TestCase):
    def test_vision_and_task_use_explicit_sections(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = GraphStore(Path(tmp) / ".vocr")
            store.save(RepoGraphBuilder(".").build())

            vision = create_vision(GOOD_REQUEST)
            task = organize_slice(vision, vocr_home=str(Path(tmp) / ".vocr"))[0]

        self.assertEqual(vision.goal, "Baue eine Healthcheck-API im Backend")
        self.assertEqual([item.text for item in vision.acceptance_criteria], ["GET /health liefert 200", "JSON status=ok"])
        self.assertEqual(task.scope, ["FastAPI-App", "Tests"])
        self.assertEqual(task.non_goals, ["keine Auth", "keine Deployment-Aenderungen"])
        self.assertEqual(task.tests, ["Syntax-Check"])
        self.assertIn("VOCR repo graph brief", task.context_pack or "")

    def test_sanitize_payload_redacts_secret_patterns(self) -> None:
        payload = {"message": "key sk-testsecret123456789", "api_key": "plain"}

        self.assertEqual(
            sanitize_payload(payload),
            {"message": "key [redacted]", "api_key": "[redacted]"},
        )

    def test_scope_guard_blocks_files_outside_declared_scope(self) -> None:
        task = VocrTask(
            slice_id="slice-test",
            title="Docs only",
            summary="Update docs",
            scope=["docs"],
            acceptance_criteria=[AcceptanceCriterion(text="Docs updated")],
            tests=["Syntax-Check"],
        )

        guard = ScopeGuard()

        self.assertEqual(guard.validate_changed_files(task, ["docs/guide.md"]), [])
        self.assertTrue(guard.validate_changed_files(task, ["src/vocr/main.py"]))

    def test_graph_context_uses_bm25_and_import_neighbors(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            package = root / "src" / "sample"
            package.mkdir(parents=True)
            (package / "__init__.py").write_text("", encoding="utf-8")
            (package / "api.py").write_text(
                "from sample.service import health_status\n\ndef health():\n    return health_status()\n",
                encoding="utf-8",
            )
            (package / "service.py").write_text(
                "def health_status():\n    return {'status': 'ok'}\n",
                encoding="utf-8",
            )

            graph = RepoGraphBuilder(root).build()
            brief = graph.context_brief(query="health api", limit=2)

        self.assertIn("src/sample/api.py (seed)", brief)
        self.assertIn("src/sample/service.py", brief)


if __name__ == "__main__":
    unittest.main()
