from __future__ import annotations

import unittest

from vocr.orchestration.readiness import assess_request_readiness, parse_request_sections


GOOD_REQUEST = (
    "Ziel: Baue eine Healthcheck-API im Backend. "
    "Arbeitsbereich: FastAPI-App; Tests. "
    "Akzeptanz: GET /health liefert 200; JSON status=ok. "
    "Verifikation: Syntax-Check. "
    "Nicht-Ziele: keine Auth; keine Deployment-Aenderungen. "
    "Ausfuehrung: mit go Worktree vorbereiten; Review vor Promote."
)


class ReadinessTests(unittest.TestCase):
    def test_vague_request_is_blocked(self) -> None:
        report = assess_request_readiness("Baue eine Healthcheck API")

        self.assertFalse(report.ready)
        self.assertIn("akzeptanzkriterien", report.missing_topics)
        self.assertGreaterEqual(len(report.questions), 1)

    def test_structured_request_is_ready(self) -> None:
        report = assess_request_readiness(GOOD_REQUEST)

        self.assertTrue(report.ready)
        self.assertEqual(report.questions, [])

    def test_parse_request_sections(self) -> None:
        sections = parse_request_sections(GOOD_REQUEST)

        self.assertEqual(sections["ziel"], "Baue eine Healthcheck-API im Backend")
        self.assertIn("FastAPI-App", sections["arbeitsbereich"])
        self.assertIn("GET /health", sections["akzeptanz"])


if __name__ == "__main__":
    unittest.main()
