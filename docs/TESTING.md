# VOCR Testing Guide

Diese Anleitung beschreibt, wie VOCR lokal getestet wird. Ziel ist ein
nachvollziehbares Teststadium: Installation pruefen, CLI pruefen, Graphify
pruefen, Learning pruefen, Secret-Scanner pruefen und den Visionary-Flow ohne
ungewollte Merges testen.

Alle Befehle laufen aus dem Repo-Root:

```powershell
cd C:\Users\jeenz\Desktop\Agent
.\.venv\Scripts\Activate.ps1
```

## 1. Schnelltest

```powershell
vocr test
```

Erfolgskriterien:

- `compileall src tests -> 0`
- `unittest discover -s tests -> 0`
- Ausgabe endet mit `VOCR self-test passed`

Dieser Befehl ist der normale lokale Smoke-Test.

## 2. Manuelle Test-Basis

Falls du die Schritte einzeln laufen lassen willst:

```powershell
python -m compileall src tests
$env:PYTHONPATH="src"; python -m unittest discover -s tests
```

Erfolgskriterium:

- Alle Tests laufen ohne Fehler.

## 3. CLI-Oberflaeche pruefen

```powershell
vocr --help
vocr bootstrap --help
vocr install --help
vocr start --help
vocr gui --help
vocr model --help
vocr worker --help
vocr secrets --help
vocr dispatch-ready --help
vocr work-ready --help
vocr clean --help
```

Erfolgskriterien:

- Keine Tracebacks
- Kommandos werden angezeigt
- `model`, `worker`, `secrets` erscheinen als Untergruppen
- `bootstrap` bietet `--tests`, `--write-scripts` und `--start`
- `install` ist als benutzerfreundlicher Installationsalias verfuegbar
- `start` beschreibt die lokale GUI und bietet `--console`
- `gui` ist als Alias fuer das lokale Fenster verfuegbar

Bootstrap pruefen:

```powershell
Test-Path .\install-vocr.ps1
Test-Path .\start-vocr.ps1
Test-Path .\Start-VOCR.bat
vocr bootstrap --tests --write-scripts --no-start
vocr bootstrap --no-start
```

Erfolgskriterien:

- Die drei Installer-/Startskripte liegen sichtbar im Repo-Root.
- Mehrfaches Ausfuehren bleibt sicher.
- `.venv` wird angelegt oder wiederverwendet.
- `.env` wird nicht ueberschrieben.
- `.vocr/ledger.jsonl` existiert.
- `.vocr/graph.json` existiert.
- `install-vocr.ps1`, `start-vocr.ps1` und `Start-VOCR.bat` existieren nach `--write-scripts`.
- Ein falscher Ordner ohne `pyproject.toml` erzeugt eine klare Repo-Meldung statt eines Pip-Fehlers.
- Fehlendes Git oder zu altes Python wird klar diagnostiziert.

Expertmodus-Kommandos:

```powershell
vocr ask --help
vocr answer --help
vocr reply --help
vocr log --help
vocr inspect --help
vocr diff --help
vocr review --help
vocr check --help
vocr promote --help
vocr ship --help
vocr doctor --help
vocr model --help
vocr worker --help
vocr secrets --help
vocr clean --help
vocr abort --help
```

Erfolgskriterien:

- Alle Kommandos zeigen Hilfe ohne Traceback.
- Expertmodus darf Task-IDs, Clarification-IDs, Slice-IDs, Worktree-Pfade, Ledger-Events, Diffs, Review-Artefakte, Model-Status, Doctor-Details und Promote-Previews anzeigen.
- Normalmodus abstrahiert diese Details weiterhin.

## 4. Normalmodus pruefen

Fenstermodus:

```powershell
vocr start
```

Alias:

```powershell
vocr gui
```

Console-Fallback:

```powershell
vocr start --console
```

Testdialog:

```text
Ich will eine Startshell fuer VOCR.
passt, aber keine Docs erstmal
ja
ja
mit Worktree, aber nicht mergen
Ja, Worktree vorbereiten, aber nichts mergen
```

Erfolgskriterien:

- `vocr start` nutzt die lokale Tkinter-GUI als kleinste robuste MVP-Oberflaeche.
- Es gibt keine Cloud-Pflicht und keine Frontend-Buildchain fuer den Normalmodus.
- Eine kurze Initialnachricht reicht fuer einen sinnvollen Vorschlag.
- Der Visionaer erkennt die Absicht als einfacheren Einstieg fuer normale VOCR-Nutzer.
- Der Vorschlag nennt Scope, Akzeptanz, Verifikation, Nicht-Ziele und Ausfuehrungsgrenzen.
- Der Visionaer schlaegt zuerst logisch passende naechste Schritte vor.
- Der User kann den Rahmen natuerlichsprachlich bestaetigen oder korrigieren.
- Der Normalmodus haelt genau einen aktiven Intake-State pro Session.
- Antworten wie `ja`, `ohne Docs`, `nimm Docs doch mit rein`, `nur planen` und `mit Worktree, aber nicht mergen` aktualisieren den aktuellen Intake-Punkt.
- Wenn der User ein neues Ziel formuliert, startet der Visionaer bewusst einen neuen Intake.
- Nach vollstaendigem Intake erscheint ein Bestaetigungs-Gate mit Ziel, Arbeitsbereich, Akzeptanz, Verifikation, Nicht-Zielen, Ausfuehrungsmodus, geplanten internen VOCR-Schritten und Sicherheitsgrenzen.
- Tasks, Worktrees und Dispatches entstehen erst nach ausdruecklicher natuerlicher Freigabe.
- Im Normalmodus erscheint kein technischer Rueckfrage-Code.
- Der User muss keine ID kopieren, merken oder eingeben.
- Jede Antwort bezieht sich automatisch auf die aktuelle Visionaer-Frage.
- Interne Aktionen wie Dispatch, Worktree, Review oder Promote werden nicht als primaere UI-Steuerung angeboten.
- Vor `Bestaetigen` werden keine Tasks und keine Worktrees erzeugt.
- Nach `Bestaetigen` wird nur die freigegebene Vorbereitung ausgefuehrt.
- Bei `nur planen` entstehen keine Worktrees.

## 5. Doctor-Pruefung

```powershell
vocr doctor
vocr worker doctor
vocr model status
vocr model check
```

Erfolgskriterien:

- Ledger-Pfad wird angezeigt
- Git repository ist `yes`
- Worktree root wird angezeigt
- Codex CLI ist `yes` oder nachvollziehbar `missing`
- Model-Status zeigt keine Secrets im Klartext

## 6. Graphify testen

```powershell
vocr graphify
vocr context "scope review" --limit 10
```

Erfolgskriterien:

- `.vocr/graph.json` wird geschrieben
- Ausgabe zeigt `Files indexed`
- Context zeigt relevante Dateien
- Es gibt keine breiten Datei-Dumps

Mit Learning:

```powershell
vocr learn
vocr context "scope review" --learning --limit 10 --budget 1200
```

Erfolgskriterien:

- `.vocr/learning.json` wird geschrieben
- Learning Brief wird angezeigt
- Falls Signale existieren, werden Learning Rank Boosts angezeigt

## 7. Secret Scanner testen

Sauberer Diff:

```powershell
vocr secrets scan
```

Erfolgskriterium:

- Keine Findings
- Exit-Code 0

Blockier-Test ohne echten Secret-Wert dauerhaft abzulegen:

```powershell
$tmp = New-TemporaryFile
Set-Content -Path $tmp -Value "OPENAI_API_KEY=sk-testsecretvalue1234567890"
git diff --no-index NUL $tmp
Remove-Item $tmp
```

Der eigentliche Scanner wird in den Unit-Tests gegen so einen Diff geprueft.
Lege keine echten Secrets im Repo ab.

## 8. Model-Konfiguration testen

Ohne LM Studio:

```powershell
vocr model status
```

Mit LM Studio:

1. LM Studio starten.
2. Modell laden.
3. Local Server starten.
4. Dann:

```powershell
vocr model check --model "modellname-aus-list"
vocr model check --api-key "test-token"
vocr model list
vocr model lmstudio --model "modellname-aus-list"
vocr model status
```

Erfolgskriterien:

- `model check` erreicht den lokalen OpenAI-kompatiblen Endpoint
- `model list` zeigt Modelle
- `model status` zeigt Provider `local-openai-compatible`
- API-Key wird nur als `[set]` gezeigt

401/Auth-Diagnose:

```powershell
vocr model list --base-url http://localhost:1234/v1
vocr model check --base-url http://localhost:1234/v1 --model "modellname-aus-list"
vocr model check --base-url http://localhost:1234/v1 --api-key "test-token"
vocr ask "Ziel: Teste lokalen Live-Agent. Arbeitsbereich: src. Akzeptanz: klare Diagnose. Verifikation: unittest. Nicht-Ziele: kein Merge. Ausfuehrung: nur planen." --live-agent --plan-only
```

Erfolgskriterien bei aktivierter/ungueltiger LM-Studio-Auth:

- Ausgabe nennt LM Studio oder lokalen OpenAI-kompatiblen Provider.
- Ausgabe erklaert, dass API-Key/Auth abgelehnt wurde.
- Ausgabe empfiehlt Auth im LM-Studio-Server zu deaktivieren oder einen gueltigen LM-Studio-Token zu setzen.
- Der Fehler wird nicht als erfolgreicher Live-Agent-Lauf gewertet.
- Der lokale Fallback bleibt moeglich.

Zuruecksetzen:

```powershell
vocr model off
```

## 9. Visionary Readiness im Expertmodus testen

Vage Anfrage:

```powershell
vocr ask "Baue eine Healthcheck API"
```

Erfolgskriterien:

- VOCR startet keine Tasks
- VOCR erstellt keine Worktrees
- VOCR fragt nach fehlenden Informationen
- Eine Clarification-ID wird angezeigt

Antwort ohne ID:

```powershell
vocr reply "Ziel: Baue eine Healthcheck-API. Arbeitsbereich: src und tests. Akzeptanz: GET /health liefert 200. Verifikation: Syntax-Check. Nicht-Ziele: keine Auth. Ausfuehrung: nur planen, Review vor Promote."
```

Erfolgskriterium:

- VOCR nutzt die letzte offene Rueckfrage automatisch

## 10. Plan-only Flow testen

```powershell
vocr ask "Ziel: Dokumentiere VOCR Setup. Arbeitsbereich: README.md und docs. Akzeptanz: Installation und Testablauf sind beschrieben. Verifikation: Syntax-Check. Nicht-Ziele: keine Code-Aenderung. Ausfuehrung: nur planen, Review vor Promote." --plan-only
vocr inspect
```

Erfolgskriterien:

- Slice wird erstellt
- Task wird erstellt
- Kein Worktree wird dispatcht
- `vocr inspect` zeigt Slice und Task

## 11. Worktree Dispatch testen

Nur ausfuehren, wenn das Repo sauber ist:

```powershell
git status --short
```

Erwartung: keine Ausgabe.

Dann:

```powershell
vocr ask "Ziel: Dokumentiere einen Testhinweis. Arbeitsbereich: docs. Akzeptanz: docs enthalten den Hinweis. Verifikation: Syntax-Check. Nicht-Ziele: keine Code-Aenderung. Ausfuehrung: mit go Worktree vorbereiten, Review vor Promote." --go
vocr inspect
```

Erfolgskriterien:

- Task wird dispatcht
- Worktree entsteht neben dem Repo unter `<repo>.vocr-worktrees/`
- Im Worktree existieren:
  - `.vocr/VOCR_TASK.md`
  - `.vocr/scope.json`
  - `.vocr/AGENTS.md`

## 12. DAG Ready Commands testen

Wenn mehrere Tasks existieren:

```powershell
vocr dispatch-ready
vocr work-ready --limit 1
```

Erfolgskriterien:

- `dispatch-ready` nimmt nur Tasks ohne offene Dependencies
- `work-ready` nimmt nur dispatchte Tasks
- Keine Promotion passiert automatisch

## 13. Review testen

```powershell
vocr review <task-id>
```

Erwartung ohne manuelle Entscheidung:

- Entscheidung ist `needs_changes`
- Hinweis auf manuelle Review-Entscheidung
- Review-Artefakt entsteht unter `.vocr/artifacts/<task-id>/review.md`

Mit Entscheidung:

```powershell
vocr review <task-id> --decision accepted --summary "Manual review passed"
```

Erfolgskriterien:

- Akzeptiert nur, wenn Checks, Scope und Secret-Scan sauber sind
- Bei Problemen wird auf `needs_changes` heruntergestuft

## 14. Promote-Gate testen

Preview:

```powershell
vocr ship <task-id> --preview
```

Erfolgskriterium:

- Diff-/Commit-Preview wird angezeigt
- Kein Merge passiert

Echter Promote nur nach akzeptiertem Review:

```powershell
vocr ship <task-id>
```

Erfolgskriterien:

- Ohne accepted Review blockiert VOCR
- Mit accepted Review fuehrt VOCR Merge-Preflight aus
- Merge passiert erst danach

## 15. Learning und Compact testen

```powershell
vocr learn
vocr usage
vocr eval-golden
vocr compact --keep-last 200
```

Erfolgskriterien:

- `.vocr/learning.json` existiert
- `vocr usage` zeigt eine `Source`-Spalte fuer `actual` oder `estimated`
- `vocr eval-golden` meldet PASS fuer Stub-Worker, Token-Metering und Promote-Gates
- alte Ledger-Events werden bei Bedarf nach `.vocr/archive/` geschrieben
- `.vocr/ledger.jsonl` bleibt kleiner

## 16. Housekeeping testen

```powershell
vocr clean
vocr clean --artifacts --older-than-days 30
vocr clean --archives --archive-older-than-days 90
```

Erfolgskriterien:

- Git Worktree Prune laeuft
- Alte Artefakte werden nur geloescht, wenn `--artifacts` gesetzt ist
- Alte Ledger-Archive werden nur geloescht, wenn `--archives` gesetzt ist; das Loeschen ist dauerhaft und nutzt keinen Papierkorb.

## 17. MCP Smoke testen

```powershell
'{"jsonrpc":"2.0","id":1,"method":"tools/list"}' | python -m vocr.main serve-mcp
```

Erfolgskriterien:

- JSON-RPC Antwort
- Tools enthalten:
  - `vocr_status`
  - `vocr_context`
  - `vocr_plan`
  - `vocr_review`
  - `vocr_promote_preview`
  - `vocr_promote`

## 18. Abnahmekriterien fuer Teststadium

VOCR ist lokal testbereit, wenn diese Befehle erfolgreich sind:

```powershell
vocr test
vocr doctor
vocr worker doctor
vocr graphify
vocr learn
vocr eval-golden
vocr context "scope review" --learning --limit 10
vocr secrets scan
```

Und diese Regeln gelten:

- Keine echten Secrets werden ausgegeben.
- Kein Merge passiert ohne accepted Review.
- Worker laufen nur in isolierten Worktrees.
- Scope-Verletzungen blockieren Commits.
- Secret-Funde blockieren Commits.
- Learning speichert verdichtete Signale, keine Rohprompts oder grossen Diffs.
- Golden-Eval prueft den LLM-freien Stub-Worker und blockierten Promote vor accepted Review.
- Context-Packs respektieren `--budget` und ranken Code vor Docs, wenn beides aehnlich relevant ist.
- Bei hohem deterministischen Vertrauen wird `--live-agent` nicht fuer einen LLM-Overwrite genutzt.
