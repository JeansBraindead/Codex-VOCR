# VOCR

VOCR ist ein lokaler Python-MVP nach dem Muster **Vision / Organize / Code / Review**.

Der Visionary Agent ist der Single Contact Point fuer den User. Er nimmt Nutzerwuensche entgegen, baut automatisch einen tokenarmen Graphify-Kontext, haelt Ziel und Akzeptanzkriterien fest, zerlegt Arbeit in kleine Tasks, dispatcht bei `--go` in isolierte Git-Worktrees und promotet Aenderungen erst nach Review.

## Setup

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e .
vocr setup
```

Optional: `.env.example` nach `.env` kopieren und `OPENAI_API_KEY` setzen, wenn die Agents live genutzt werden sollen. Mit `VOCR_HOME` kann der lokale Ledger-Pfad angepasst werden. Der aktuelle MVP kann ohne API-Key seine lokale Struktur, Ledger-Operationen und Worktree-Kommandos verwenden.

Optional kann `VOCR_CODEX_COMMAND` gesetzt werden. Dann startet `vocr work <task-id>` diesen echten Worker-Befehl im isolierten Worktree und uebergibt den Task-Prompt ueber stdin. Ohne `VOCR_CODEX_COMMAND` nutzt VOCR, wenn vorhanden, `codex exec - --cd <worktree> --sandbox workspace-write`. Bei `approve_all` wird `--ask-for-approval never` gesetzt. Unsandboxed-Ausfuehrung gibt es nur explizit mit `VOCR_CODEX_UNSANDBOXED=true`.

`vocr setup` schreibt zusaetzlich `.vocr/codex-mcp.json` fuer Codex als MCP-Server (`codex mcp-server`). `vocr codex-config` kann diese Datei neu erzeugen.

## Normaler Ablauf

Der User spricht nur mit dem Visionaer:

```powershell
vocr setup
vocr ask "Ziel: Baue eine Healthcheck-API im Backend. Arbeitsbereich: FastAPI-App und Tests. Akzeptanz: GET /health liefert 200 und JSON status=ok. Verifikation: pytest oder Syntax-Check. Nicht-Ziele: keine Auth, keine Deployment-Aenderungen. Ausfuehrung: nur planen, Review vor Promote."
vocr ask "Ziel: Baue eine Healthcheck-API im Backend. Arbeitsbereich: FastAPI-App und Tests. Akzeptanz: GET /health liefert 200 und JSON status=ok. Verifikation: pytest oder Syntax-Check. Nicht-Ziele: keine Auth, keine Deployment-Aenderungen. Ausfuehrung: mit go Worktree vorbereiten, Review vor Promote." --go
vocr ask "Ziel: Baue eine Healthcheck-API im Backend. Arbeitsbereich: FastAPI-App und Tests. Akzeptanz: GET /health liefert 200 und JSON status=ok. Verifikation: pytest oder Syntax-Check. Nicht-Ziele: keine Auth, keine Deployment-Aenderungen. Ausfuehrung: mit go Worktree vorbereiten, Review vor Promote." --go --live-agent
```

Wenn Informationen fehlen, legt der Visionaer nicht los. Er fragt stattdessen konkret nach und erstellt keine Tasks, keine Worktrees und keine Dispatches. Der Request muss Zielbild, Arbeitsbereich, Akzeptanzkriterien, Verifikation, Nicht-Ziele und Ausfuehrungsgrenzen ausreichend klar machen.

Antworten auf Rueckfragen laufen weiter ueber den Visionaer:

```powershell
vocr reply <clarification-id> "Ziel: ... Arbeitsbereich: ... Akzeptanz: ... Verifikation: ... Nicht-Ziele: ... Ausfuehrung: ..." --go
```

Was `vocr vision` intern macht:

1. Pruefen, ob genug Wissen vorhanden ist.
2. Fehlende Informationen explizit abfragen und stoppen.
3. Erst bei ausreichendem Wissen: Graphify aktualisieren.
4. Tokenarmen Context-Pack fuer die Anfrage erzeugen.
5. VisionSlice mit Ziel, Annahmen und Akzeptanzkriterien speichern.
6. Tasks mit Scope, Nicht-Zielen, Akzeptanzkriterien, Tests und Context-Pack anlegen.
7. Mit `--go`: Approve-All fuer diesen Slice setzen und Tasks in isolierte Worktrees dispatchen.
8. Review und Promote bleiben Gate-gesteuert und werden nicht automatisch uebersprungen.

## Debug- und Admin-Kommandos

Diese Kommandos sind fuer Inspektion, Reparatur und manuelle Eingriffe gedacht, nicht als normaler User-Flow:

```powershell
vocr graphify
vocr context --limit 20
vocr context "git worktree review" --limit 10
vocr go global --all --reason "AFK run approved"
vocr organize <slice-id>
vocr organize <slice-id> --live-agent
vocr dispatch <task-id>
vocr work <task-id>
vocr codex-config
vocr inspect
vocr review <task-id>
vocr check <task-id> --decision accepted --summary "Manual review passed"
vocr ship <task-id>
vocr tweak "Kleine risikoarme Aenderung"
vocr doctor
```

## Designregeln

- Vision haelt Ziel, Annahmen und Akzeptanzkriterien.
- Der User spricht im Normalfall nur mit `vocr vision`.
- Der Visionaer fragt fehlende Informationen explizit ab und blockiert Planung, bis der Wissensstand hoch genug ist.
- Keine halben Annahmen: unklare Details werden nicht erfunden.
- Graphify wird vom Visionaer automatisch aktualisiert und fuer Context-Packs genutzt.
- Organize zerlegt Arbeit in kleine, reviewbare Tasks.
- Code/Codex arbeitet nur in isolierten Git-Worktrees.
- Review entscheidet `accepted`, `needs_changes` oder `blocked`.
- Promote merged nur Tasks mit akzeptiertem Review.
- Tweak ist nur fuer kleine, risikoarme Aenderungen.
- Jeder Task hat Scope, Nicht-Ziele, Akzeptanzkriterien und Tests.
- Secrets werden nicht geloggt.
- Es gibt keine automatische Merge-Operation ohne Review.
- `vocr go ... --all` oder `vocr vision ... --go` setzt eine geloggte Approve-All-Freigabe fuer VOCR-interne Nachfragen. Externe Codex-/OS-Permissions muessen spaeter vom jeweiligen Runner respektiert werden.
- Neue Agents sollen zuerst `vocr context` bzw. `.vocr/graph.json` lesen, nicht blind das ganze Repo. Das reduziert Tokenburn und gibt ihnen eine Karte der relevanten Dateien.
- `vocr dispatch` erzeugt im isolierten Worktree `.vocr/VOCR_TASK.md` mit Task, Context-Pack und Permission-Modus.
- `vocr dispatch` erzeugt ausserdem `.vocr/scope.json` und `.vocr/AGENTS.md` als maschinenlesbare und menschenlesbare Scope-Policy fuer Worker.
- `vocr review` sammelt lokale Git-Signale aus dem Worktree und akzeptiert nur mit expliziter Entscheidung.
- `vocr review` fuehrt sichere automatische Checks aus, z.B. Syntax-Check. Unbekannte Checks werden als manuell markiert, nicht blind gestartet.
- `vocr work` fuehrt den echten Worker aus und erstellt bei Erfolg automatisch einen Task-Commit, wenn Aenderungen vorhanden sind.
- `vocr check --codex-review` kann zusaetzlich `codex exec review` als Review-Signal ausfuehren.
- `vocr ship --preview` zeigt Merge-Preview, `vocr ship --pr` erstellt optional eine Draft-PR via GitHub CLI.
- `vocr promote` fuehrt vor dem Merge einen Preflight aus und blockiert ohne akzeptiertes Review.

## Tests

```powershell
python -m compileall src tests
$env:PYTHONPATH="src"; python -m unittest discover -s tests
```

## Speicherorte

- `.vocr/ledger.jsonl` speichert Events, Slices, Tasks und Reviews.
- `.vocr/ledger.jsonl` bleibt im Repo als lokaler Ablauf-Speicher.
- `.vocr/graph.json` speichert den kompakten Graphify-Index fuer tokenarme Agent-Kontexte.

## Token-effizientes Arbeiten

Vor jeder neuen Agent-Runde:

1. `vocr vision` aktualisiert Graphify automatisch.
2. Der Visionaer erzeugt daraus taskbezogene Context-Packs.
3. Worker-Tasks bekommen ihren Context-Pack automatisch im Task-Template.
4. Debug-Agenten sollen `vocr context "<suchbegriffe>" --limit 10` verwenden, statt breit Dateien zu lesen.
5. Erst danach werden gezielt die wenigen Dateien gelesen, die der Context-Pack nennt.

Das Ziel ist: neue Agents bekommen eine Repo-Karte und nur die naechsten relevanten Dateien, nicht den kompletten Codebestand.
- Der Standard-Ort fuer isolierte Task-Worktrees liegt neben dem Repo: `<repo>.vocr-worktrees/`.
- `src/vocr/codex/mcp_client.py` ist nur die Adapter-Grenze fuer spaetere Codex-CLI/MCP-Anbindung.

## Naechste Schritte

1. Codex CLI als MCP-Server konkret konfigurieren und `VOCR_CODEX_COMMAND` darauf zeigen lassen.
2. Reviewer Agent mit Diff-Kommentaren und optionalen PR-Reviews erweitern.
3. Scope Guard als harte Pre-Write-Schicht fuer Worker erweitern.
4. Promote Gate mit optionalem PR-Modus ausbauen.
5. Graphify um inkrementelle Updates und semantische Summaries erweitern.
