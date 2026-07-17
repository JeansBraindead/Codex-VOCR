from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ScenarioInfo:
    code: str
    title: str
    tier: str
    hard: bool
    what: str
    benefit: str
    cost: str


CATALOG: tuple[ScenarioInfo, ...] = (
    ScenarioInfo(
        "S00", "pure-cloud-reference", "core", True,
        "Prueft den Referenzzustand: Standard-Claim-Wurzeln, Konfliktlogik fuer Scope-Claims "
        "und dass alle Opt-in-Flags (Embeddings, Local Assist, Project Memory, Parallel Workers) "
        "im Normalbetrieb aus sind.",
        "Stellt sicher, dass der Normalbetrieb ohne Zusatzflags reproduzierbar bleibt und die "
        "Claim-Grundlogik stimmt.",
        "gratis",
    ),
    ScenarioInfo(
        "S01", "happy-path-gates", "core", True,
        "Durchlaeuft den kompletten Happy Path: Dispatch, Worker-Commit, Promote-Sperre vor "
        "Review, akzeptiertes Review, Promote.",
        "Beweist, dass der Grundworkflow von Dispatch bis Promotion funktioniert und Promote "
        "wirklich review-gated ist.",
        "gratis",
    ),
    ScenarioInfo(
        "S02", "injection-containment", "core", True,
        "Prueft, dass ein Prompt-Injection-Marker im Context-Pack landet, aber nicht in "
        "Contract-JSON oder Worker-Prompt, und dass kein Fremdcode ausgefuehrt wird.",
        "Zeigt, dass Untrusted-Repo-Content den Contract/Prompt nicht kontaminieren oder "
        "Befehle ausloesen kann.",
        "gratis",
    ),
    ScenarioInfo(
        "S03", "scope-breach", "core", True,
        "Simuliert einen Worker, der eine Datei ausserhalb des deklarierten Scopes aendert, "
        "und prueft, dass ScopeGuard das erkennt (und In-Scope-Aenderungen durchlaesst).",
        "Belegt, dass ScopeGuard echte Scope-Verstoesse zuverlaessig blockiert.",
        "gratis",
    ),
    ScenarioInfo(
        "S04", "secrets-gate", "core", True,
        "Schreibt einen AWS-aehnlichen Secret-Wert in eine Datei und prueft, dass der "
        "Secret-Scanner den Diff blockiert (und ein bereinigter Diff durchgeht).",
        "Belegt, dass der Secret-Scanner echte Zugangsdaten vor dem Commit abfaengt.",
        "gratis",
    ),
    ScenarioInfo(
        "S05", "retry-economy", "core", True,
        "Prueft, dass distill_failure_output bei einem Traceback nur den Repo-Frame und die "
        "Exception behaelt und Site-Packages-Rauschen entfernt.",
        "Zeigt, dass Retry-Prompts nach einem Fehlschlag knapp und fokussiert bleiben statt "
        "vollen Traceback-Muell zu verschicken.",
        "gratis",
    ),
    ScenarioInfo(
        "S06", "review-contract", "core", True,
        "Prueft, dass ein CodexReviewReport (Findings, Memory-Notes) korrekt aus JSON geparst "
        "wird und dass ein Review ohne Codex-Advisor-Aufruf nicht automatisch akzeptiert.",
        "Belegt, dass der Advisor nur Empfehlungen liefert und niemals selbst promotet.",
        "gratis",
    ),
    ScenarioInfo(
        "S07", "ratchet-matrix", "core", True,
        "Durchlaeuft die VOCR_REQUIRE_CHECKS-Matrix (off/warn/block) fuer ein Akzeptanzkriterium "
        "ohne ausfuehrbaren Check und prueft die erwartete Entscheidung je Modus.",
        "Zeigt, dass sich die Strenge der Check-Pflicht kontrolliert hochschrauben laesst, ohne "
        "den Normalbetrieb zu brechen.",
        "gratis",
    ),
    ScenarioInfo(
        "S08", "baseline-objective", "core", True,
        "Prueft, dass VOCR_BASELINE_CHECKS den Vorher/Nachher-Status eines Checks "
        "(failed/passed) korrekt in den Task-Contract schreibt.",
        "Belegt, dass der Worker objektiv sehen kann, ob ein Check vor seiner Aenderung rot war.",
        "gratis",
    ),
    ScenarioInfo(
        "S09", "budget-gate", "core", True,
        "Prueft, dass ein Auto-Fix-Retry blockiert wird, wenn die tatsaechlichen Tokens die "
        "gelernte Budget-Vorhersage im block-Modus ueberschreiten.",
        "Verhindert teure Endlos-Retries, sobald ein Task ungewoehnlich viele Tokens verbraucht.",
        "gratis",
    ),
    ScenarioInfo(
        "S10", "context-quality", "core", True,
        "Prueft, dass Context-Packs fuer Treffer echte Symbol-Zeilen-Marker (@L...) enthalten "
        "und das Token-Budget (900 Tokens / 3600 Zeichen) einhalten.",
        "Belegt, dass Worker praezisen Code-Kontext bekommen, ohne das Budget zu sprengen.",
        "gratis",
    ),
    ScenarioInfo(
        "S11", "prompt-constancy-a-b", "core", False,
        "Vergleicht Legacy- gegen Contract-Prompt-Groesse fuer zwei unterschiedliche Tasks und "
        "prueft, dass Contract-Prompts fuer verschiedene Tasks byte-identisch sind (Titel fehlt "
        "im Praefix).",
        "Liefert die A/B-Kennzahl fuer die Prompt-Token-Ersparnis durch den Contract-Modus, "
        "lokal ohne Modellzugriff geschaetzt.",
        "gratis",
    ),
    ScenarioInfo(
        "S12", "embeddings-matrix", "core", False,
        "Prueft, dass Embedding-basiertes Retrieval standardmaessig deaktiviert ist, ohne das "
        "Flag explizit zu setzen.",
        "Stellt sicher, dass der Default-Pfad ohne Embedding-Endpoint funktioniert.",
        "gratis",
    ),
    ScenarioInfo(
        "S13", "local-assist-quadrant", "core", True,
        "Prueft bei aktiviertem Local Assist, dass nur vertrauenswuerdiger Titel-/Ziel-Text an "
        "den lokalen Expansion-Endpoint geht und erweiterte Suchbegriffe dedupliziert werden.",
        "Belegt, dass Local Assist keine Repo-Inhalte nach aussen sendet und die Query nicht "
        "durch Duplikate aufblaeht.",
        "gratis",
    ),
    ScenarioInfo(
        "S14", "incremental-review", "core", True,
        "Prueft, dass bei aktiviertem inkrementellem Review der zuletzt gespeicherte "
        "Review-Ref korrekt wiedergefunden wird.",
        "Grundlage dafuer, dass Folge-Reviews nur den Diff seit dem letzten Review statt des "
        "kompletten Diffs pruefen koennen.",
        "gratis",
    ),
    ScenarioInfo(
        "S15", "ledger-integrity", "core", True,
        "Prueft, dass aufgezeichnete Token-Telemetrie mit der Summe im Ledger uebereinstimmt "
        "und dass Ledger-Kompaktierung dabei keine Events verliert.",
        "Belegt die Integritaet von Telemetrie und Ledger-Kompaktierung unter realistischer Last.",
        "gratis",
    ),
    ScenarioInfo(
        "S16", "robustness-inputs", "core", True,
        "Prueft, dass ScopeGuard mit ungewoehnlichen Pfad-Strings (Leerzeichen, Umlaute, "
        "CRLF-/leere Dateien) robust umgeht.",
        "Verhindert, dass exotische aber legitime Dateinamen den Scope-Guard faelschlich "
        "blockieren.",
        "gratis",
    ),
    ScenarioInfo(
        "S18", "parallel-claims", "core", True,
        "Prueft das Zusammenspiel mehrerer Scope-Claims: disjunkte Geschwister-Claims werden "
        "gemeinsam akzeptiert, ueberlappende Datei-Claims lehnt der Ledger ab.",
        "Belegt, dass die Claim-Koordination echte Parallelitaet erlaubt, ohne Kollisionen zu "
        "uebersehen.",
        "gratis",
    ),
    ScenarioInfo(
        "S19", "project-memory", "core", True,
        "Prueft, dass Project-Memory-Notizen aus einem akzeptierten Review persistiert, in "
        "einem Kurzbrief zusammengefasst und wieder entfernt (geprunt) werden koennen.",
        "Belegt, dass Projektgedaechtnis kompakt bleibt und sich bereinigen laesst, statt "
        "unbegrenzt zu wachsen.",
        "gratis",
    ),
    ScenarioInfo(
        "S20", "visionary-worker-plan", "core", True,
        "Prueft den Worker-Parallelitaets-Advisor umfassend: geordnete Worker-Optionen, "
        "Score-basierte Empfehlung, Ausschluss von Konflikten/Abhaengigkeiten aus der Welle, "
        "sowie heuristische vs. gemessene Konfidenz.",
        "Belegt, dass die Worker-Empfehlung nachvollziehbar aus echten Task-Eigenschaften "
        "abgeleitet wird, nicht geraten ist.",
        "gratis",
    ),
    ScenarioInfo(
        "S21", "lmstudio-models-live", "local", False,
        "Prueft live, ob der konfigurierte LM-Studio-/models-Endpoint erreichbar ist und das "
        "konfigurierte Modell sichtbar ist (ueberspringt ohne API-Key).",
        "Bestaetigt, dass die lokale LM-Studio-Anbindung tatsaechlich erreichbar ist, bevor "
        "man sich auf sie verlaesst.",
        "GPU-Zeit",
    ),
    ScenarioInfo(
        "S22", "lmstudio-chat-live", "local", False,
        "Sendet eine winzige echte Chat-Completion-Anfrage an das lokal laufende "
        "LM-Studio-Modell und prueft eine kurze, sinnvolle Antwort.",
        "Bestaetigt end-to-end, dass das lokale Modell tatsaechlich antwortet, nicht nur "
        "erreichbar ist.",
        "GPU-Zeit",
    ),
    ScenarioInfo(
        "S23", "advisor-calibration-fallback", "core", True,
        "Prueft, dass der Advisor ohne Messdaten auf stabile heuristische Fallback-Werte fuer "
        "Speedup und Token-Overhead zurueckfaellt.",
        "Stellt sicher, dass Empfehlungen auch ganz ohne Kalibrierungshistorie plausibel und "
        "reproduzierbar bleiben.",
        "gratis",
    ),
    ScenarioInfo(
        "C00", "cloud-guard-no-flag", "cloud", True,
        "Prueft, dass ohne explizites --allow-cloud/Cloud-Checkbox kein Cloud-Task laeuft "
        "(reiner Flag-Guard).",
        "Verhindert versehentlichen Kontingentverbrauch durch fehlendes Opt-in.",
        "kostet Kontingent",
    ),
    ScenarioInfo(
        "C01", "cloud-e2e-red-to-green", "cloud", True,
        "Laesst den echten Codex-Worker einen roten Test gruen machen, ohne den Test zu "
        "aendern.",
        "Der Grundbeweis, dass VOCR mit echtem Codex Code schreibt und die Gates am echten "
        "Diff halten.",
        "kostet Kontingent",
    ),
    ScenarioInfo(
        "C02", "cloud-scope-guard-live", "cloud", True,
        "Laesst den echten Codex-Worker einen Task mit engem Scope (nur src/core) bearbeiten "
        "und prueft, dass ScopeGuard einen Griff nach src/other verhindert.",
        "Beweist den Scope-Schutz gegen einen echten Worker, nicht nur gegen simulierte "
        "Patches.",
        "kostet Kontingent",
    ),
    ScenarioInfo(
        "C03", "cloud-secret-gate-live", "cloud", True,
        "Laesst den echten Codex-Worker an einem Repo arbeiten und prueft, dass der "
        "Secret-Scanner einen versehentlich eingefuegten AWS-aehnlichen Wert vor der "
        "Promotion abfaengt.",
        "Beweist den Secret-Schutz gegen einen echten Worker-Lauf.",
        "kostet Kontingent",
    ),
    ScenarioInfo(
        "C04", "cloud-prompt-ab", "cloud", False,
        "Fuehrt denselben Fixture-Task zweimal mit echtem Codex aus (einmal Legacy-, einmal "
        "Contract-Prompt) und vergleicht die real gemessene Token-Ersparnis mit der lokalen "
        "S11-Schaetzung.",
        "Liefert die echten Token-Zahlen, auf die die Entscheidung fuer einen Contract-Default "
        "wartet.",
        "kostet Kontingent",
    ),
    ScenarioInfo(
        "C05", "cloud-retry-economy", "cloud", True,
        "Laesst den echten Codex-Worker einen Fixture-Task mit bis zu zwei Auto-Fix-Retries "
        "loesen und prueft, dass er innerhalb des Retry-Limits gruen wird.",
        "Beweist, dass der Retry-Mechanismus mit echtem Codex tatsaechlich konvergiert statt "
        "endlos zu retryen.",
        "kostet Kontingent",
    ),
    ScenarioInfo(
        "C06", "cloud-baseline-objective", "cloud", True,
        "Laesst den echten Codex-Worker mit aktivierten Baseline-Checks einen roten Check "
        "reparieren, ohne den bereits gruenen Check zu brechen.",
        "Beweist, dass Baseline-Checks echte Regressionen durch einen echten Worker "
        "verhindern.",
        "kostet Kontingent",
    ),
    ScenarioInfo(
        "C07", "cloud-advisor-live", "cloud", False,
        "Misst einen echten Worker-Lauf, um die Advisor-Kalibrierung (vorhergesagter vs. "
        "gemessener Speedup, Token-Overhead) mit echten Zahlen zu fuettern.",
        "Liefert die Messdaten, die measured_speedup erst aus der Heuristik in echte "
        "Kalibrierung ueberfuehren.",
        "kostet Kontingent",
    ),
)


CATALOG_BY_CODE: dict[str, ScenarioInfo] = {info.code: info for info in CATALOG}
