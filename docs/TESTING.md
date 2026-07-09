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

## 4. Doctor-Pruefung

```powershell
vocr doctor
vocr worker doctor
vocr model status
```

Erfolgskriterien:

- Ledger-Pfad wird angezeigt
- Git repository ist `yes`
- Worktree root wird angezeigt
- Codex CLI ist `yes` oder nachvollziehbar `missing`
- Model-Status zeigt keine Secrets im Klartext

## 5. Graphify testen

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
vocr context "scope review" --learning --limit 10
```

Erfolgskriterien:

- `.vocr/learning.json` wird geschrieben
- Learning Brief wird angezeigt
- Falls Signale existieren, werden Learning Rank Boosts angezeigt

## 6. Secret Scanner testen

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

## 7. Model-Konfiguration testen

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
vocr model list
vocr model lmstudio --model "modellname-aus-list"
vocr model status
```

Erfolgskriterien:

- `model list` zeigt Modelle
- `model status` zeigt Provider `local-openai-compatible`
- API-Key wird nur als `[set]` gezeigt

Zuruecksetzen:

```powershell
vocr model off
```

## 8. Visionary Readiness testen

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

## 9. Plan-only Flow testen

```powershell
vocr ask "Ziel: Dokumentiere VOCR Setup. Arbeitsbereich: README.md und docs. Akzeptanz: Installation und Testablauf sind beschrieben. Verifikation: Syntax-Check. Nicht-Ziele: keine Code-Aenderung. Ausfuehrung: nur planen, Review vor Promote." --plan-only
vocr inspect
```

Erfolgskriterien:

- Slice wird erstellt
- Task wird erstellt
- Kein Worktree wird dispatcht
- `vocr inspect` zeigt Slice und Task

## 10. Worktree Dispatch testen

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

## 11. DAG Ready Commands testen

Wenn mehrere Tasks existieren:

```powershell
vocr dispatch-ready
vocr work-ready --limit 1
```

Erfolgskriterien:

- `dispatch-ready` nimmt nur Tasks ohne offene Dependencies
- `work-ready` nimmt nur dispatchte Tasks
- Keine Promotion passiert automatisch

## 12. Review testen

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

## 13. Promote-Gate testen

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

## 14. Learning und Compact testen

```powershell
vocr learn
vocr usage
vocr compact --keep-last 200
```

Erfolgskriterien:

- `.vocr/learning.json` existiert
- alte Ledger-Events werden bei Bedarf nach `.vocr/archive/` geschrieben
- `.vocr/ledger.jsonl` bleibt kleiner

## 15. Housekeeping testen

```powershell
vocr clean
vocr clean --artifacts --older-than-days 30
```

Erfolgskriterien:

- Git Worktree Prune laeuft
- Alte Artefakte werden nur geloescht, wenn `--artifacts` gesetzt ist

## 16. MCP Smoke testen

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

## 17. Abnahmekriterien fuer Teststadium

VOCR ist lokal testbereit, wenn diese Befehle erfolgreich sind:

```powershell
vocr test
vocr doctor
vocr worker doctor
vocr graphify
vocr learn
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
