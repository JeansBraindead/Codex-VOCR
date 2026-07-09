# VOCR

VOCR ist ein lokaler Python-MVP nach dem Muster **Vision / Organize / Code / Review**.

VOCR ist architektonisch von [VOIT](https://github.com/yesitsfebreeze/voit) inspiriert, insbesondere vom Gedanken, Arbeit ueber klare Phasen, isolierte Worktrees, Scope-Regeln, Review-Gates und Promote-Flows zu strukturieren. VOCR ist eine eigenstaendige Python/Codex-Umsetzung dieser Ideen und kein Fork oder vendored Copy von VOIT.

Der Visionary Agent ist der Single Contact Point fuer den User. Er nimmt Nutzerwuensche entgegen, baut automatisch einen tokenarmen Graphify-Kontext, haelt Ziel und Akzeptanzkriterien fest, zerlegt Arbeit in kleine Tasks, dispatcht bei `--go` in isolierte Git-Worktrees und promotet Aenderungen erst nach Review.

## Setup

Sehr genaue Anleitungen:

- [Installationsanleitung](docs/INSTALLATION.md)
- [Testanleitung](docs/TESTING.md)

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e .
vocr setup
```

Optional kann VOCR lokale oder Cloud-Modelle fuer den Live-Agent-Pfad nutzen. Der User muss dafuer nicht in `.env` schreiben:

```powershell
vocr model lmstudio --model "dein-lm-studio-modell"
vocr model list
vocr model status
vocr model off
```

Fuer OpenAI:

```powershell
vocr model openai --model gpt-4.1-mini
```

VOCR schreibt die noetigen Werte in `.env`, zeigt Secrets aber nur als `[set]`. VOCR bleibt Codex-first: lokale Modelle helfen Vision/Organizer-Pfaden, aber Codex-Worker, Scope, Review und Promote bleiben die Sicherheitslinie.

Optional kann `VOCR_CODEX_COMMAND` gesetzt werden. Dann startet `vocr work <task-id>` diesen echten Worker-Befehl im isolierten Worktree und uebergibt den Task-Prompt ueber stdin. Ohne `VOCR_CODEX_COMMAND` nutzt VOCR, wenn vorhanden, `codex exec - --cd <worktree> --sandbox workspace-write`. Bei `approve_all` wird `--ask-for-approval never` gesetzt. Unsandboxed-Ausfuehrung gibt es nur explizit mit `VOCR_CODEX_UNSANDBOXED=true`.

`vocr setup` schreibt zusaetzlich `.vocr/codex-mcp.json` fuer Codex als MCP-Server (`codex mcp-server`). `vocr codex-config` kann diese Datei neu erzeugen.

## Normaler Ablauf

Der User spricht nur mit dem Visionaer:

```powershell
vocr setup
vocr model lmstudio --model "dein-lokales-modell"
vocr model status
vocr ask "Ziel: Baue eine Healthcheck-API im Backend. Arbeitsbereich: FastAPI-App und Tests. Akzeptanz: GET /health liefert 200 und JSON status=ok. Verifikation: pytest oder Syntax-Check. Nicht-Ziele: keine Auth, keine Deployment-Aenderungen. Ausfuehrung: nur planen, Review vor Promote."
vocr ask "Ziel: Baue eine Healthcheck-API im Backend. Arbeitsbereich: FastAPI-App und Tests. Akzeptanz: GET /health liefert 200 und JSON status=ok. Verifikation: pytest oder Syntax-Check. Nicht-Ziele: keine Auth, keine Deployment-Aenderungen. Ausfuehrung: mit go Worktree vorbereiten, Review vor Promote." --go
vocr ask "Ziel: Baue eine Healthcheck-API im Backend. Arbeitsbereich: FastAPI-App und Tests. Akzeptanz: GET /health liefert 200 und JSON status=ok. Verifikation: pytest oder Syntax-Check. Nicht-Ziele: keine Auth, keine Deployment-Aenderungen. Ausfuehrung: mit go Worktree vorbereiten, Review vor Promote." --go --live-agent
```

Wenn Informationen fehlen, legt der Visionaer nicht los. Er fragt stattdessen konkret nach und erstellt keine Tasks, keine Worktrees und keine Dispatches. Der Request muss Zielbild, Arbeitsbereich, Akzeptanzkriterien, Verifikation, Nicht-Ziele und Ausfuehrungsgrenzen ausreichend klar machen.

Antworten auf Rueckfragen laufen weiter ueber den Visionaer:

```powershell
vocr reply <clarification-id> "Ziel: ... Arbeitsbereich: ... Akzeptanz: ... Verifikation: ... Nicht-Ziele: ... Ausfuehrung: ..." --go
vocr reply "Ziel: ... Arbeitsbereich: ... Akzeptanz: ... Verifikation: ... Nicht-Ziele: ... Ausfuehrung: ..." --go
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
vocr model status
vocr model list
vocr model local --model "dein-modell" --base-url http://localhost:1234/v1
vocr model openai --model gpt-4.1-mini
vocr model off
vocr context --limit 20
vocr context "git worktree review" --limit 10
vocr go global --all --reason "AFK run approved"
vocr organize <slice-id>
vocr organize <slice-id> --live-agent
vocr dispatch <task-id>
vocr dispatch-ready
vocr work <task-id>
vocr work <task-id> --fix --max-retries 2
vocr work-ready --fix
vocr worker doctor
vocr worker profile safe
vocr worker profile unattended
vocr log --limit 30
vocr diff <task-id>
vocr diff <task-id> --full
vocr usage
vocr learn
vocr context "scope review" --learning --limit 10
vocr compact --keep-last 200
vocr secrets scan
vocr test
vocr clean
vocr clean --artifacts --older-than-days 30
vocr abort <task-id> --reason "Nicht mehr benoetigt"
vocr serve-mcp
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
- Scope ist hart: `task.scope` wird in erlaubte Pfad-Globs uebersetzt. Aenderungen ausserhalb werden vor dem Commit blockiert und der Task wird `needs_changes`.
- Der Pre-Commit Secret-Scanner prueft Diffs inklusive neuer untracked Dateien auf Keyword-Secrets, bekannte Token-Muster und Entropie-Hinweise. Treffer blockieren den Commit ohne Secret-Werte auszugeben.
- `vocr secrets scan` scannt den aktuellen Diff manuell. Wenn `gitleaks` installiert ist, nutzt VOCR optional `.gitleaks.toml`, `.gitleaks-baseline.json`, `VOCR_GITLEAKS_CONFIG` und `VOCR_GITLEAKS_BASELINE`.
- `vocr review` sammelt lokale Git-Signale aus dem Worktree und akzeptiert nur mit expliziter Entscheidung.
- `vocr review` erzeugt einfache Diff-Kommentare fuer geaenderte Dateien und riskante Added-Lines.
- `vocr review --export-comments review.md` schreibt Review-Kommentare als Markdown; `--post-pr-comments` postet optional einen PR-Kommentar via GitHub CLI.
- `vocr review` schreibt standardmaessig ein Artefakt nach `.vocr/artifacts/<task-id>/review.md`.
- `vocr review` fuehrt sichere automatische Checks aus, z.B. Syntax-Check. Unbekannte Checks werden als manuell markiert, nicht blind gestartet.
- `vocr work` fuehrt den echten Worker aus und erstellt bei Erfolg automatisch einen Task-Commit, wenn Aenderungen vorhanden sind und der Scope Guard keine Verletzung findet.
- `vocr work --fix --max-retries 2` erlaubt begrenzte Nachbesserungen bis `review_ready`; Promote bleibt trotzdem manuell und review-gated.
- `vocr dispatch-ready` und `vocr work-ready` bedienen vorbereitete DAG-Tasks, deren Dependencies erfuellt sind.
- `vocr worker doctor` und `vocr worker profile ...` konfigurieren Codex-Worker ohne Dateiedits.
- `vocr check --codex-review` kann zusaetzlich `codex exec review` als Review-Signal ausfuehren.
- `vocr ship --preview` zeigt Merge-Preview, `vocr ship --pr` erstellt optional eine Draft-PR via GitHub CLI.
- `vocr promote` fuehrt vor dem Merge einen Preflight aus und blockiert ohne akzeptiertes Review.
- `vocr log`, `vocr diff`, `vocr clean` und `vocr abort` sind Housekeeping-Kommandos fuer Timeline, Task-Diff, verwaiste Worktrees und kontrollierten Abbruch.
- `vocr usage` zeigt geschaetzte Token-/Provider-Telemetrie pro Task/Slice.
- `vocr learn` verdichtet lokale Ledger-, Review- und Telemetrie-Signale in `.vocr/learning.json`.
- `vocr compact` aktualisiert Learning und archiviert alte Ledger-Events unter `.vocr/archive/`, damit `.vocr/ledger.jsonl` klein bleibt.
- `vocr test` fuehrt Syntax- und Unit-Test-Smoke lokal aus.
- `vocr serve-mcp` startet einen minimalen MCP-Server fuer Status, Graphify-Kontext, VOCR-Planung, Review und Promote-Preview. MCP merged nicht.

## Tests

```powershell
python -m compileall src tests
$env:PYTHONPATH="src"; python -m unittest discover -s tests
```

## Speicherorte

- `.vocr/ledger.jsonl` speichert Events, Slices, Tasks und Reviews.
- `.vocr/ledger.jsonl` bleibt im Repo als lokaler Ablauf-Speicher.
- `.vocr/graph.json` speichert den kompakten Graphify-Index fuer tokenarme Agent-Kontexte.
- `.vocr/learning.json` speichert verdichtete lokale Signale statt Rohprompts oder grosser Diffs.
- `.vocr/archive/` enthaelt kompaktierte alte Ledger-Segmente.
- Telemetrie-Events protokollieren Provider, Modell, Slice/Task und geschaetzte Token pro Worker-Lauf.
- `docs/THREAT_MODEL.md` beschreibt Prompt-Injection-Grenzen, Scope Guard und Secret-Scanning.

## Token-effizientes Arbeiten

Vor jeder neuen Agent-Runde:

1. `vocr vision` aktualisiert Graphify automatisch.
2. Graphify rankt per BM25, zieht 1-Hop-Import-Nachbarn relevanter Dateien dazu und nutzt vorhandene Content-Hashes fuer inkrementelle Rebuilds.
3. Das Learning-Overlay boostet bekannte Scope/Datei/Test-Signale direkt im Graphify-Ranking.
4. Der Visionaer erzeugt daraus taskbezogene Context-Packs.
5. Worker-Tasks bekommen ihren Context-Pack automatisch im Task-Template.
6. Context-Packs sind als untrusted Repo-Inhalt markiert und duerfen keine Instruktionen ueberschreiben.
7. Debug-Agenten sollen `vocr context "<suchbegriffe>" --learning --limit 10` verwenden, statt breit Dateien zu lesen.
8. Erst danach werden gezielt die wenigen Dateien gelesen, die der Context-Pack nennt.

Das Ziel ist: neue Agents bekommen eine Repo-Karte und nur die naechsten relevanten Dateien, nicht den kompletten Codebestand.
- Der Standard-Ort fuer isolierte Task-Worktrees liegt neben dem Repo: `<repo>.vocr-worktrees/`.
- `src/vocr/codex/mcp_client.py` ist nur die Adapter-Grenze fuer spaetere Codex-CLI/MCP-Anbindung.

## Referenz und Attribution

- Referenzarchitektur: [yesitsfebreeze/voit](https://github.com/yesitsfebreeze/voit)
- VOCR uebernimmt keine VOIT-Dateien, sondern nutzt VOIT als Architektur-Inspiration fuer Vision/Organize/Worker/Review/Promote-artige Abläufe.
- Falls VOCR spaeter VOIT-Code oder Assets uebernimmt, muss die jeweilige Lizenz und Attribution separat im betroffenen Codepfad dokumentiert werden.

## Naechste Schritte

1. Reviewer Agent mit echten inline PR-Review-Kommentaren erweitern.
2. Echte Token-Usage aus Agents SDK/Codex auslesen, sobald stabil verfuegbar.
3. MCP-Server um explizit bestaetigte Promote-Aktionen erweitern, weiterhin streng gate-gesteuert.
4. Learning-Signale um Erfolgsdauer, Retry-Anzahl und Clarification-Qualitaet erweitern.
5. Housekeeping-Retention fuer `.vocr/archive/` und Artefakte feiner konfigurierbar machen.
