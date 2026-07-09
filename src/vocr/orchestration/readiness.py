from __future__ import annotations

from vocr.models import ClarificationQuestion, ReadinessReport


SECTION_ALIASES = {
    "ziel": ["ziel:", "zielbild:", "goal:"],
    "arbeitsbereich": ["arbeitsbereich:", "scope:", "bereich:", "dateien:"],
    "akzeptanz": ["akzeptanz:", "akzeptanzkriterien:", "done:", "erfolg:"],
    "verifikation": ["verifikation:", "tests:", "checks:", "pruefung:", "prüfung:"],
    "nicht_ziele": ["nicht-ziele:", "nichtziele:", "out-of-scope:", "non-goals:"],
    "ausfuehrung": ["ausfuehrung:", "ausführung:", "permissions:", "go:", "review:"],
}


def parse_request_sections(request: str) -> dict[str, str]:
    lowered = request.lower()
    positions: list[tuple[int, str, str]] = []
    for section, aliases in SECTION_ALIASES.items():
        for alias in aliases:
            index = lowered.find(alias)
            if index >= 0:
                positions.append((index, section, alias))
                break

    if not positions:
        return {}

    sections: dict[str, str] = {}
    ordered = sorted(positions, key=lambda item: item[0])
    for offset, (start, section, alias) in enumerate(ordered):
        content_start = start + len(alias)
        content_end = ordered[offset + 1][0] if offset + 1 < len(ordered) else len(request)
        value = request[content_start:content_end].strip(" .;\n\t")
        if value:
            sections[section] = value
    return sections


def assess_request_readiness(request: str) -> ReadinessReport:
    text = request.strip()
    lowered = text.lower()
    sections = parse_request_sections(text)
    questions: list[ClarificationQuestion] = []

    def missing(topic: str, question: str, why_needed: str) -> None:
        questions.append(
            ClarificationQuestion(
                topic=topic,
                question=question,
                why_needed=why_needed,
            )
        )

    if len(text.split()) < 18 and "ziel" not in sections:
        missing(
            "zielbild",
            "Was soll am Ende konkret funktionieren und fuer wen?",
            "Ein kurzer Wunsch reicht nicht, um Scope und Erfolg ohne Interpretation festzulegen.",
        )

    if "arbeitsbereich" not in sections and not _has_any(lowered, ["datei", "file", "modul", "repo", "projekt", "cli", "api", "frontend", "backend", "ui"]):
        missing(
            "arbeitsbereich",
            "Welche Bereiche, Dateien, Module oder Nutzerflaechen sind betroffen?",
            "Der Visionaer braucht eine Eingrenzung, damit Worker nicht das falsche Gebiet anfassen.",
        )

    if "akzeptanz" not in sections and not _has_any(lowered, ["akzeptanz", "fertig", "done", "erfolg", "kriter", "soll ", "muss ", "wenn "]):
        missing(
            "akzeptanzkriterien",
            "Woran erkenne ich eindeutig, dass die Aufgabe fertig ist?",
            "Ohne Done-Kriterien muesste VOCR Erfolg erfinden.",
        )

    if "verifikation" not in sections and not _has_any(lowered, ["test", "pruef", "check", "syntax", "pytest", "compile", "verifiz"]):
        missing(
            "verifikation",
            "Wie soll die Aenderung verifiziert werden, oder welche Checks sind erlaubt?",
            "Worker und Reviewer brauchen einen konkreten Nachweis statt Bauchgefuehl.",
        )

    if "nicht_ziele" not in sections and not _has_any(lowered, ["nicht", "kein", "keine", "scope", "nur", "ohne", "dont", "do not"]):
        missing(
            "nicht-ziele",
            "Was ist ausdruecklich nicht Teil der Aufgabe?",
            "Nicht-Ziele verhindern, dass Agents den Auftrag ausweiten.",
        )

    if "ausfuehrung" not in sections and not _has_any(lowered, ["permission", "go", "afk", "review", "merge", "promote", "worktree"]):
        missing(
            "ausfuehrungsgrenzen",
            "Darf VOCR nur planen, oder mit --go auch Worktrees vorbereiten und bis zum Review vorarbeiten?",
            "Der Visionaer muss wissen, wie weit er ohne weitere Rueckfrage gehen darf.",
        )

    missing_topics = [question.topic for question in questions]
    confidence = max(0.0, min(1.0, 1.0 - (len(questions) * 0.16)))
    return ReadinessReport(
        ready=not questions,
        confidence=confidence,
        missing_topics=missing_topics,
        questions=questions,
        notes=[
            "VOCR blocks execution until missing information is answered.",
            "No assumptions are converted into tasks while readiness is false.",
        ],
    )


def _has_any(text: str, needles: list[str]) -> bool:
    return any(needle in text for needle in needles)
