# VOCR

VOCR ist ein lokaler Python-MVP nach dem Muster **Vision / Organize / Code / Review**.

VOCR ist architektonisch von [VOIT](https://github.com/yesitsfebreeze/voit) inspiriert, insbesondere vom Gedanken, Arbeit ueber klare Phasen, isolierte Worktrees, Scope-Regeln, Review-Gates und Promote-Flows zu strukturieren. VOCR ist eine eigenstaendige Python/Codex-Umsetzung dieser Ideen und kein Fork oder vendored Copy von VOIT.

Der Visionary Agent ist der Single Contact Point fuer den User. Er nimmt Nutzerwuensche entgegen, baut automatisch einen tokenarmen Graphify-Kontext, haelt Ziel und Akzeptanzkriterien fest, zerlegt Arbeit in kleine Tasks, dispatcht bei `--go` in isolierte Git-Worktrees und promotet Aenderungen erst nach Review.

Der normale Einstieg ist `vocr start`: eine einfache Dialogoberflaeche mit Textfeld, in der der User natuerlichsprachlich mit dem Visionaer spricht. Der Visionaer klaert fehlende Informationen, fasst den Intake zusammen, erklaert die Ausfuehrung und wartet auf Freigabe, bevor Tasks oder Worktrees entstehen.

## Setup

Sehr genaue Anleitungen:

- [Installationsanleitung](docs/INSTALLATION.md)
- [Testanleitung](docs/TESTING.md)
- [Normalmodus-Oberflaeche](docs/NORMAL_MODE_SURFACE.md)

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e .
vocr setup
vocr start
```

Einfacher und robuster fuer normale Nutzer:

```powershell
.\install-vocr.ps1
```

Alternativ bei blockierter PowerShell:

```powershell
.\Start-VOCR.bat
```

Die Installer-Skripte liegen sichtbar im Repo-Root: `install-vocr.ps1`,
`start-vocr.ps1` und `Start-VOCR.bat`. Sie wechseln automatisch in ihr eigenes
Repo-Verzeichnis, legen `.venv` bei Bedarf an, installieren VOCR editable,
fuehren Bootstrap/Graphify aus und starten den Normalmodus.

Wenn `install-vocr.ps1` in einem leeren Ordner liegt, klont es das Repo nach
`Codex-VOCR` und fuehrt die Installation dort fort. Ein anderer Zielordner geht
mit `.\install-vocr.ps1 -InstallDir D:\Tools\Codex-VOCR`.

`vocr bootstrap` bleibt der Expert-/CLI-Pfad. Er erkennt, ob er im VOCR-Repo
laeuft, installiert nur neben einem echten `pyproject.toml`, initialisiert
`.vocr`, erzeugt Graphify und respektiert vorhandene `.env`-Werte.

Wenn VOCR bereits global verfuegbar ist, kann auch die CLI aus einem leeren
Ordner clonen:

```powershell
vocr bootstrap --clone --install-dir Codex-VOCR
```

Optional kann VOCR lokale oder Cloud-Modelle fuer den Live-Agent-Pfad nutzen. Der User muss dafuer nicht in `.env` schreiben:

```powershell
vocr model lmstudio --model "dein-lm-studio-modell"
vocr model check --model "dein-lm-studio-modell"
vocr model check --api-key "dein-lm-studio-token"
vocr model list
vocr model status
vocr model off
```

Fuer OpenAI:

```powershell
vocr model openai --model gpt-4.1-mini
```

VOCR schreibt die noetigen Werte in `.env`, beruecksichtigt zusaetzlich gesetzte Prozess-Umgebungsvariablen und zeigt Secrets nur als `[set]`. VOCR bleibt Codex-first: lokale Modelle helfen Vision/Organizer-Pfaden, aber Codex-Worker, Scope, Review und Promote bleiben die Sicherheitslinie.

Wenn LM Studio oder ein lokaler OpenAI-kompatibler Server mit 401 antwortet,
ordnet VOCR das lokal ein: Auth ist im Server vermutlich aktiv oder der
gesetzte Token ist ungueltig. Dann wird der Live-Agent nicht als Erfolg
behandelt; VOCR nutzt den lokalen Fallback und fordert dazu auf, Auth im
LM-Studio-Server zu deaktivieren oder einen gueltigen lokalen Token zu setzen:

```powershell
vocr model lmstudio --model "dein-lm-studio-modell" --api-key "dein-lm-studio-token"
vocr model check --model "dein-lm-studio-modell"
vocr model list --api-key "dein-lm-studio-token"
```

Optional kann `VOCR_CODEX_COMMAND` gesetzt werden. Dann startet `vocr work <task-id>` diesen echten Worker-Befehl im isolierten Worktree und uebergibt den Task-Prompt ueber stdin. Ohne `VOCR_CODEX_COMMAND` nutzt VOCR, wenn vorhanden, `codex exec - --cd <worktree> --sandbox workspace-write`. Bei `approve_all` wird `--ask-for-approval never` gesetzt. Unsandboxed-Ausfuehrung gibt es nur explizit mit `VOCR_CODEX_UNSANDBOXED=true`.

`vocr setup` schreibt zusaetzlich `.vocr/codex-mcp.json` fuer Codex als MCP-Server (`codex mcp-server`). `vocr codex-config` kann diese Datei neu erzeugen.

## Normaler Ablauf

Der User spricht im Normalfall nur mit dem Visionaer:

```powershell
vocr start
```

`vocr start` prueft vor dem Start Repo, Python, Git, `.env`, `.vocr` und Graphify.
Falls etwas Lokales fehlt, wird es idempotent vorbereitet; falls der Ordner
falsch ist, stoppt VOCR mit einer verstaendlichen Meldung.

`vocr start` oeffnet im MVP bewusst eine lokale Tkinter-GUI: Python-stdlib, keine Cloud-Pflicht, keine Frontend-Buildchain, zentrale Texteingabe und kompakter Status. Textual/TUI und lokale Web-GUI bleiben sinnvolle spaetere Upgrades, aber fuer den MVP ist die lokale GUI der kleinste robuste Normalmodus.

Falls kein Fenster verfuegbar ist oder du im Terminal bleiben willst:

```powershell
vocr start --console
```

Im Normalmodus kennt der User keine technischen Rueckfrage-Codes, Task-IDs, Worktrees oder Dispatch-Begriffe. Der Dialog laeuft phasenweise:

1. Wunsch frei beschreiben.
2. Visionaer interpretiert die Absicht und schlaegt einen passenden Rahmen vor.
3. Visionaer setzt genau einen aktiven Intake-Punkt, z.B. Arbeitsbereich.
4. User bestaetigt oder korrigiert diesen Punkt natuerlichsprachlich.
5. Visionaer aktualisiert den Intake-State und fragt den naechsten logisch fehlenden Punkt.
6. Visionaer zeigt ein klares Bestaetigungs-Gate mit Zusammenfassung, internen VOCR-Schritten und Sicherheitsgrenzen.
7. User bestaetigt ausdruecklich oder aendert noch etwas natuerlichsprachlich.
8. Erst danach entstehen Tasks und, falls freigegeben, isolierte Arbeitsbereiche.

Die UI ist dabei nur der Gespraechsraum. Sie bietet keine primaeren Prozess-Buttons fuer Planen, Dispatch, Worktree, Review oder Promote. Der Visionaer schlaegt den naechsten sinnvollen Schritt vor, erklaert die Konsequenzen und wartet auf Bestaetigung oder Korrektur.

Der Intake ist keine Pflichtfeldliste. Auch kurze Initialnachrichten sollen zu einem sinnvollen Vorschlag fuehren:

```text
User: Ich will eine Startshell fuer VOCR.
Visionaer: Ich verstehe: Du willst einen einfacheren Einstieg fuer normale VOCR-Nutzer.
Vermutlich passende Bereiche:
- src/vocr/cli/app.py
- neue Start-/Dialog-Komponente unter src/vocr/ui
- tests
- optional README/docs

Ich schlage als Akzeptanz vor:
- User kann vocr start ausfuehren
- danach oeffnet sich ein normaler Visionaer-Dialog
- User sieht keine technischen Rueckfrage-Codes
- der bestehende Expert-CLI-Flow bleibt erhalten

Verifikation:
- python -m compileall src tests
- python -m unittest discover -s tests

Nicht-Ziele und Risiken:
- keine Aenderungen an Review, Promote oder Worker-Sandboxing

Ausfuehrungsgrenzen:
- Erst planen
- danach optional getrennten Arbeitsbereich vorbereiten
- nie automatisch veroeffentlichen
```

Beispiel:

```text
User: Ich will die Rueckfrage-UX verbessern.
Visionaer: Ich verstehe ... Ich schlage diesen Rahmen vor. Naechster Punkt: Arbeitsbereich. Passt das?
User: Passt, aber keine Docs erstmal.
Visionaer: Okay. Dokumentationsaenderungen sind ausgeschlossen. Naechster Punkt: Akzeptanz. Passt das?
User: ja
Visionaer: Naechster Punkt: Verifikation. Ich schlage compileall und unittest vor. Passt das?
```

Ein normaler Dialog hat genau einen aktiven Intake-Zustand pro Fenster oder Console-Session. Jede User-Antwort bezieht sich automatisch auf die aktuelle Frage; der User muss keine IDs kopieren, keine Rueckfrage auswaehlen und keinen Expert-Befehl eingeben. Wenn der User ein neues Ziel formuliert, startet der Visionaer bewusst einen neuen Intake. Wenn der User fortsetzt, wird der aktuelle Intake fortgefuehrt.

Wenn Informationen fehlen, legt der Visionaer nicht los. Er fragt stattdessen konkret nach und erstellt keine Tasks, keine Worktrees und keine Dispatches. Der Request muss Zielbild, Arbeitsbereich, Akzeptanzkriterien, Verifikation, Nicht-Ziele und Ausfuehrungsgrenzen ausreichend klar machen.

Wenn der Intake vollstaendig ist, zeigt der Visionaer vor jeder Ausfuehrung:

- Ziel
- Arbeitsbereich
- Akzeptanzkriterien
- Verifikation
- Nicht-Ziele
- Ausfuehrungsmodus
- geplante interne VOCR-Schritte
- Sicherheitsgrenzen

Danach fragt er `Soll ich so fortfahren?`. Tasks, Arbeitsbereiche und Dispatches entstehen im Normalmodus erst nach dieser ausdruecklichen Freigabe. Eine Antwort wie `Ja, Worktree vorbereiten, aber nichts mergen` aktualisiert den Ausfuehrungsmodus noch vor dem Start und laesst Review-/Promote-Gates aktiv.

Expertmodus bleibt verfuegbar:

```powershell
vocr ask "Ziel: Baue eine Healthcheck-API im Backend. Arbeitsbereich: FastAPI-App und Tests. Akzeptanz: GET /health liefert 200 und JSON status=ok. Verifikation: pytest oder Syntax-Check. Nicht-Ziele: keine Auth, keine Deployment-Aenderungen. Ausfuehrung: nur planen, Review vor Promote."
vocr ask "Ziel: Baue eine Healthcheck-API im Backend. Arbeitsbereich: FastAPI-App und Tests. Akzeptanz: GET /health liefert 200 und JSON status=ok. Verifikation: pytest oder Syntax-Check. Nicht-Ziele: keine Auth, keine Deployment-Aenderungen. Ausfuehrung: mit go Worktree vorbereiten, Review vor Promote." --go
vocr reply "Ziel: ... Arbeitsbereich: ... Akzeptanz: ... Verifikation: ... Nicht-Ziele: ... Ausfuehrung: ..." --go
```

Was der Visionaer intern macht:

1. Pruefen, ob genug Wissen vorhanden ist.
2. Fehlende Informationen explizit abfragen und stoppen.
3. Erst bei ausreichendem Wissen: Graphify aktualisieren.
4. Tokenarmen Context-Pack fuer die Anfrage erzeugen.
5. VisionSlice mit Ziel, Annahmen und Akzeptanzkriterien speichern.
6. Tasks mit Scope, Nicht-Zielen, Akzeptanzkriterien, Tests und Context-Pack anlegen.
7. Mit `--go`: Approve-All fuer diesen Slice setzen und Tasks in isolierte Worktrees dispatchen.
8. Review und Promote bleiben Gate-gesteuert und werden nicht automatisch uebersprungen.

## Debug- und Admin-Kommandos

Diese Kommandos sind der Expertmodus. Sie sind fuer Inspektion, Reparatur und manuelle Eingriffe gedacht, nicht als normaler User-Flow. Der Expertmodus darf technische Details zeigen: Task-IDs, Clarification-IDs, Slice-IDs, Worktree-Pfade, Ledger-Events, Diffs, Review-Artefakte, Model-Status, Doctor-Details und Promote-Previews.

Bestehende Expert-Kommandos bleiben kompatibel:

```powershell
vocr bootstrap --tests --write-scripts
vocr install
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
vocr dispatch-ready --parallel 4
vocr work <task-id>
vocr work <task-id> --fix --max-retries 2
vocr work-ready --fix --parallel 2
vocr orchestrate --fix --parallel-dispatch 4 --parallel-work 2
vocr afk --max-waves 10
vocr worker doctor
vocr worker profile safe
vocr worker profile unattended
vocr log --limit 30
vocr diff <task-id>
vocr diff <task-id> --full
vocr usage
vocr eval-golden
vocr learn
vocr context "scope review" --learning --limit 10 --budget 1200
vocr compact --keep-last 200
vocr secrets scan
vocr test
vocr clean
vocr clean --artifacts --older-than-days 30
vocr clean --archives --archive-older-than-days 90
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
- Der User spricht im Normalfall nur mit `vocr start`.
- `vocr vision`, `vocr ask`, `vocr reply`, `vocr graphify`, `vocr organize` und `vocr dispatch` bleiben Expert-/Debug-Befehle.
- Technische Rueckfrage-IDs bleiben nur im Expert-/Debugmodus sichtbar.
- Die Normalmodus-UI fuehrt nicht den Prozess; der Visionaer fuehrt ihn dialogisch.
- Der Visionaer fragt fehlende Informationen explizit ab und blockiert Planung, bis der Wissensstand hoch genug ist.
- Der Visionaer darf Rahmen vorschlagen, aber Tasks entstehen erst nach natuerlicher Bestaetigung.
- Der Normalmodus haelt genau einen aktiven Intake-State pro Session und fragt sequenziell den naechsten fehlenden Punkt.
- Natuerliche Antworten wie `ja`, `ohne Docs`, `nimm Docs doch mit rein`, `nur planen` oder `mit Worktree, aber nicht mergen` aktualisieren diesen Intake-State.
- Nach vollstaendigem Intake muss der Normalmodus immer eine menschenlesbare Zusammenfassung zeigen und auf Freigabe warten.
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
- `vocr context --budget N` begrenzt Context-Packs ueber ein ungefaehres Token-Budget statt nur ueber fixe Node-Zahlen.
- Der Live-Agent-Pfad nutzt ein Confidence-Gate: bei hohem deterministischen Vertrauen wird auch mit `--live-agent` kein LLM-Overwrite gestartet.
- Live-Agent-Fan-out ist im MVP kollabiert; Vision/Organizer erzeugen strukturierte Outputs ohne mehrere Specialist-Tool-Calls.
- Worker-Retries bekommen nur Delta-Diffs seit dem vorherigen Versuch.
- `vocr dispatch` erzeugt im isolierten Worktree `.vocr/VOCR_TASK.md` mit Task, Context-Pack und Permission-Modus.
- `vocr dispatch` erzeugt ausserdem `.vocr/scope.json` als maschinenlesbare Scope-Policy; `.vocr/AGENTS.md` verweist darauf, statt Scope-Daten zu duplizieren.
- Scope ist hart: `task.scope` wird in erlaubte Pfad-Globs uebersetzt. Aenderungen ausserhalb werden vor dem Commit blockiert und der Task wird `needs_changes`.
- Der Pre-Commit Secret-Scanner prueft Diffs inklusive neuer untracked Dateien auf Keyword-Secrets, bekannte Token-Muster und Entropie-Hinweise. Treffer blockieren den Commit ohne Secret-Werte auszugeben.
- `vocr secrets scan` scannt den aktuellen Diff manuell. Wenn `gitleaks` installiert ist, nutzt VOCR optional `.gitleaks.toml`, `.gitleaks-baseline.json`, `VOCR_GITLEAKS_CONFIG` und `VOCR_GITLEAKS_BASELINE`.
- `vocr review` sammelt lokale Git-Signale aus dem Worktree und akzeptiert nur mit expliziter Entscheidung.
- `vocr review` erzeugt einfache Diff-Kommentare fuer geaenderte Dateien und riskante Added-Lines.
- `vocr review --export-comments review.md` schreibt Review-Kommentare als Markdown; `--post-pr-comments` postet optional einen PR-Kommentar via GitHub CLI.
- `vocr review --post-pr-review` postet optional einen GitHub PR-Review. Kommentare mit sicherer Datei-/Zeilenposition werden als Inline-Review-Kommentare gesendet; sonst nutzt VOCR einen normalen PR-Review-Kommentar.
- `vocr review` schreibt standardmaessig ein Artefakt nach `.vocr/artifacts/<task-id>/review.md`.
- `vocr review` fuehrt sichere automatische Checks aus, z.B. Syntax-Check. Unbekannte Checks werden als manuell markiert, nicht blind gestartet.
- Akzeptanzkriterien koennen optional ein `check_command` tragen; VOCR fuehrt diese Checks beim Review ueber dieselbe sichere Allowlist aus wie normale Task-Tests.
- Syntax-/Compile-Checks im Task-Worktree kompilieren nur geaenderte Python-Dateien; ohne Python-Diff wird billig uebersprungen.
- `vocr dispatch` blockiert vor dem Worktree, wenn Plan-Invarianten verletzt sind: fehlender Scope, fehlende Verifikation, unbekannte Dependencies oder zyklische Dependencies.
- `vocr work` fuehrt den echten Worker aus und erstellt bei Erfolg automatisch einen Task-Commit, wenn Aenderungen vorhanden sind und der Scope Guard keine Verletzung findet.
- `vocr work --fix --max-retries 2` erlaubt begrenzte Nachbesserungen bis `review_ready`; Promote bleibt trotzdem manuell und review-gated.
- `vocr dispatch-ready` bedient die naechste DAG-Welle parallel und refreshed Graphify genau einmal vor dieser Welle.
- `vocr work-ready` arbeitet dispatchte Tasks parallel in isolierten Worktrees ab; Review und Promote bleiben manuell.
- `vocr orchestrate` / `vocr afk` fuehrt einen ueberwachten Wellen-Loop aus: ready dispatchen, optional worker starten, bounded fixes erlauben, niemals automatisch reviewen/promoten/mergen.
- `vocr worker doctor` und `vocr worker profile ...` konfigurieren Codex-Worker ohne Dateiedits.
- `vocr check --codex-review` kann zusaetzlich `codex exec review` als Review-Signal ausfuehren.
- `vocr ship --preview` zeigt Merge-Preview, `vocr ship --pr` erstellt optional eine Draft-PR via GitHub CLI.
- `vocr promote` fuehrt vor dem Merge einen Preflight aus und blockiert ohne akzeptiertes Review.
- `vocr revert <task-id> --reason "..."` reverted den im Ledger gespeicherten Task-Commit, loggt den Revert und setzt den Task wieder auf `needs_changes`.
- `vocr log`, `vocr diff`, `vocr clean` und `vocr abort` sind Housekeeping-Kommandos fuer Timeline, Task-Diff, verwaiste Worktrees und kontrollierten Abbruch.
- `vocr clean --archives` loescht alte `.vocr/archive`-Segmente dauerhaft per Dateisystem-Unlink; vorher sichern, wenn die Historie erhalten bleiben soll.
- `.vocr/ledger.jsonl` wird append-only mit plattformsicherem Lock geschrieben, damit parallele VOCR-Prozesse keine Ledger-Zeilen zerreissen.
- `vocr usage` zeigt Token-/Provider-Telemetrie pro Task/Slice. Wenn der Worker echte Usage-Daten meldet, werden diese als `actual` angezeigt; sonst nutzt VOCR einen Estimate-Fallback.
- `vocr eval-golden` fuehrt einen LLM-freien Stub-Worker-Gate-Test aus: Dispatch, echtes Usage-Parsing, Promote-vor-Review-Block und Promote-nach-accepted-Review.
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
- Telemetrie-Events protokollieren Provider, Modell, Slice/Task und echte oder geschaetzte Token pro Worker-Lauf.
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

1. PR-Review-Posting gegen einen echten GitHub-Test-PR live validieren.
2. Codex-/Agents-SDK-spezifische Usage-Formate erweitern, sobald neue stabile Felder verfuegbar sind.
3. Reviewer-/Learning-Signale nach echten Beta-Laeufen kalibrieren.
