# VOCR Installation Guide

Diese Anleitung beschreibt eine saubere lokale Installation von VOCR auf Windows
mit PowerShell. VOCR ist Codex-first. Lokale Modelle ueber LM Studio sind
optional und werden ueber `vocr model ...` konfiguriert, nicht durch manuelles
Editieren von `.env`.

## 1. Voraussetzungen

Pruefe zuerst diese Werkzeuge:

```powershell
python --version
git --version
```

Erwartung:

- Python 3.11 oder neuer
- Git installiert
- PowerShell
- Optional: Codex CLI fuer echte Worker-Laeufe
- Optional: LM Studio fuer lokale OpenAI-kompatible Modelle
- Optional: GitHub CLI `gh` fuer PR-Funktionen
- Optional: `gitleaks` fuer zusaetzliches Secret-Scanning

Wenn mehrere Python-Versionen installiert sind, nutze explizit den Python 3.11+
Launcher oder Pfad, z.B.:

```powershell
py -3.11 --version
```

## 2. Repository holen

```powershell
cd C:\Users\jeenz\Desktop
git clone https://github.com/JeansBraindead/Codex-VOCR.git Agent
cd C:\Users\jeenz\Desktop\Agent
```

Wenn das Repo bereits existiert:

```powershell
cd C:\Users\jeenz\Desktop\Agent
git pull origin main
```

## 3. Virtuelle Python-Umgebung erstellen

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
```

Wenn PowerShell die Aktivierung blockiert:

```powershell
Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
.\.venv\Scripts\Activate.ps1
```

## 4. VOCR installieren

Normaler Windows-Weg:

```powershell
.\install-vocr.ps1
```

Wenn PowerShell blockiert oder du doppelklicken willst:

```powershell
.\Start-VOCR.bat
```

Die sichtbaren Installer-Dateien liegen direkt im Repo-Root:

- `install-vocr.ps1`: installiert und startet VOCR.
- `start-vocr.ps1`: prueft die Umgebung und startet VOCR erneut.
- `Start-VOCR.bat`: Fallback fuer blockierte PowerShell ExecutionPolicy.

Wenn du nur `install-vocr.ps1` in einem leeren Ordner hast, kann es VOCR selbst
klonen:

```powershell
.\install-vocr.ps1
```

Standardziel ist `.\Codex-VOCR`. Ein eigener Zielordner geht so:

```powershell
.\install-vocr.ps1 -InstallDir D:\Tools\Codex-VOCR
```

Expert-Weg im aktivierten venv:

```powershell
pip install -e .
vocr --help
```

## 5. Robuster Bootstrap

```powershell
vocr bootstrap --tests --write-scripts
```

Erwartung:

- VOCR bestaetigt Python 3.11+.
- VOCR bestaetigt Git.
- `.env` wird aus `.env.example` erzeugt, falls sie fehlt.
- Eine vorhandene `.env` wird nicht ueberschrieben.
- `.venv` wird angelegt oder wiederverwendet.
- `pip install -e .` laeuft nur, wenn `pyproject.toml` im VOCR-Repo vorhanden ist.
- `.vocr/ledger.jsonl` wird angelegt
- `.vocr/codex-mcp.json` wird geschrieben
- `.vocr/graph.json` wird erzeugt oder aktualisiert
- Optional laufen `compileall` und `unittest`
- Windows-Helfer werden erzeugt:
  - `install-vocr.ps1`
  - `start-vocr.ps1`
  - `Start-VOCR.bat`

Wenn du den Normalmodus danach direkt starten willst:

```powershell
vocr bootstrap --start
```

Oder getrennt:

```powershell
vocr bootstrap
vocr start
```

`vocr install` ist ein Installationsalias, der die Windows-Helfer standardmaessig schreibt:

```powershell
vocr install --tests
```

Wenn `vocr` bereits global verfuegbar ist und du in einem leeren Ordner stehst:

```powershell
vocr bootstrap --clone --install-dir Codex-VOCR
```

Wenn PowerShell wegen ExecutionPolicy blockiert, nutze den `.bat`-Fallback:

```powershell
.\Start-VOCR.bat
```

Der Bootstrap ist idempotent. Mehrfaches Ausfuehren respektiert vorhandene
`.venv`, `.vocr`, `.env` und `graph.json`.

Pruefen:

```powershell
vocr doctor
```

## 6. Normalmodus starten

Der normale Einstieg ist der Visionaer-Dialog:

```powershell
vocr start
```

Erwartung:

- Ein ruhiges lokales Tkinter-Fenster oeffnet sich.
- Links ist der Dialog mit dem Visionaer.
- Unten ist das Textfeld fuer freie Eingaben.
- Rechts steht der kompakte Projektstatus.
- Der Visionaer schlaegt den naechsten sinnvollen Schritt vor und fragt fehlende Informationen ab.
- Der User bestaetigt oder korrigiert natuerlichsprachlich.
- Pro Fenster oder Console-Session gibt es genau einen aktiven Intake-Zustand.
- Jede Antwort bezieht sich automatisch auf die aktuelle Visionaer-Frage.
- Ein neues Ziel startet bewusst einen neuen Intake.
- Der User sieht keine technischen Rueckfrage-Codes und muss keine IDs eingeben.
- Nach vollstaendigem Intake zeigt der Visionaer eine Zusammenfassung mit internen Schritten und Sicherheitsgrenzen.
- Tasks, Arbeitsbereiche und Dispatches entstehen erst nach ausdruecklicher Freigabe.
- Interne Schritte wie Dispatch, Worktree, Review oder Promote werden nicht als primaere Bedienbuttons gezeigt.
- Vor deiner ausdruecklichen Bestaetigung entstehen keine Tasks oder Worktrees.

Warum Tkinter im MVP:

- Python-stdlib, keine neue Runtime-Abhaengigkeit
- keine Cloud-Pflicht
- keine Frontend-Buildchain
- testbarer Controller ohne GUI-Automation
- Textual/TUI und lokale Web-GUI bleiben spaetere Optionen, falls mehr Oberflaechenkomfort noetig wird

Falls kein Fenster verfuegbar ist:

```powershell
vocr start --console
```

Der Console-Modus ist derselbe Normalmodus, nur ohne Fenster.

Alias fuer das lokale Fenster:

```powershell
vocr gui
```

## 7. Lokales Modell mit LM Studio konfigurieren

Nur noetig, wenn `--live-agent` lokal laufen soll.

1. LM Studio starten.
2. Modell laden.
3. In LM Studio den lokalen Server starten.
4. Standard-URL ist meistens `http://localhost:1234/v1`.

Modelle anzeigen:

```powershell
vocr model list
```

Falls dein LM-Studio-Server auf einem anderen Port laeuft:

```powershell
vocr model list --base-url http://localhost:1234/v1
```

Lokales Modell setzen:

```powershell
vocr model lmstudio --model "dein-modellname-aus-model-list"
```

Status pruefen:

```powershell
vocr model status
```

Erwartung:

- Provider: `local-openai-compatible`
- `OPENAI_BASE_URL`: `http://localhost:1234/v1`
- `OPENAI_MODEL`: dein Modell
- `OPENAI_API_KEY`: `[set]`

Live-Modell wieder deaktivieren:

```powershell
vocr model off
```

### LM Studio meldet 401/Auth

Wenn `vocr model list`, `vocr ask --live-agent` oder `vocr organize --live-agent`
bei lokalem LM Studio einen 401/Auth-Fehler melden, bedeutet das normalerweise:

- Auth ist im LM-Studio-Server aktiviert.
- Oder `OPENAI_API_KEY` enthaelt einen Token, den LM Studio nicht akzeptiert.

Dann gilt:

```powershell
vocr model status
```

Pruefe, ob `OPENAI_BASE_URL` auf deinen lokalen Server zeigt, z.B.
`http://localhost:1234/v1`. Danach entweder Auth im LM-Studio-Server
deaktivieren oder VOCR mit einem gueltigen lokalen Token konfigurieren:

```powershell
vocr model local --model "dein-modellname" --base-url http://localhost:1234/v1 --api-key "dein-lm-studio-token"
```

VOCR behandelt diesen Fehler nicht als erfolgreichen Live-Agent-Lauf. Der
deterministische lokale Fallback bleibt aktiv, bis die lokale Auth passt.

## 8. OpenAI Cloud optional konfigurieren

Nur wenn du den Live-Agent-Pfad ueber OpenAI nutzen willst:

```powershell
vocr model openai --model gpt-4.1-mini
```

VOCR fragt den Key verdeckt ab und schreibt ihn in `.env`. Status zeigt den Key
nicht im Klartext.

```powershell
vocr model status
```

## 9. Codex Worker konfigurieren

VOCR kann ohne Codex CLI planen, graphifizieren, lernen, reviewen und testen.
Fuer echte Worker-Ausfuehrung wird Codex CLI empfohlen.

Worker-Status:

```powershell
vocr worker doctor
```

Profile:

```powershell
vocr worker profile safe
vocr worker profile unattended
vocr worker profile unsandboxed
```

Bedeutung:

- `safe`: Standard, Codex bleibt konservativ.
- `unattended`: fuer freigegebene AFK-Laeufe, setzt Approval-Verhalten lockerer.
- `unsandboxed`: nur bewusst verwenden, weil Sandbox umgangen werden kann.

Optional eigenen Worker-Befehl setzen:

```powershell
vocr worker profile safe --command "codex exec -"
```

## 10. Secret Scanner optional erweitern

Minimaler Scanner ist eingebaut. Optional kann `gitleaks` installiert werden.
Wenn vorhanden, nutzt VOCR automatisch:

- `.gitleaks.toml`
- `.gitleaks-baseline.json`
- `VOCR_GITLEAKS_CONFIG`
- `VOCR_GITLEAKS_BASELINE`

Manueller Scan:

```powershell
vocr secrets scan
```

Erwartung bei sauberem Diff: keine Findings, Exit-Code 0.

## 11. Installation validieren

```powershell
vocr test
```

Erwartung:

- `compileall` endet mit Exit-Code 0
- Unit-Tests enden mit Exit-Code 0
- Ausgabe endet mit `VOCR self-test passed`

Zusaetzlich:

```powershell
vocr graphify
vocr context "scope review" --learning --limit 10
vocr learn
vocr compact --keep-last 200
```

## 12. Standard-Dateien und Ordner

- `.vocr/ledger.jsonl`: aktueller lokaler Event-Ledger
- `.vocr/graph.json`: Graphify-Index
- `.vocr/learning.json`: verdichtete Learning-Signale
- `.vocr/archive/`: kompaktierte alte Ledger-Segmente
- `.vocr/artifacts/<task-id>/review.md`: Review-Artefakte
- `<repo>.vocr-worktrees/`: isolierte Task-Worktrees neben dem Repo

## 13. Update bestehender Installation

```powershell
cd C:\Users\jeenz\Desktop\Agent
git pull origin main
.\.venv\Scripts\Activate.ps1
pip install -e .
vocr test
```

## 14. Haeufige Probleme

### `vocr` wird nicht gefunden

Aktiviere das venv erneut:

```powershell
.\.venv\Scripts\Activate.ps1
pip install -e .
```

### LM Studio reagiert nicht

Pruefe:

```powershell
vocr model list --base-url http://localhost:1234/v1
```

Wenn das fehlschlaegt:

- Ist LM Studio gestartet?
- Ist ein Modell geladen?
- Ist der Local Server aktiv?
- Stimmt der Port?

### Codex Worker fehlt

```powershell
vocr worker doctor
```

Wenn `Codex CLI` als `missing` erscheint, kannst du weiterhin planen und
reviewen, aber `vocr work` kann keinen echten Codex-Worker starten.

### Secret Scan blockiert Commit

```powershell
vocr secrets scan
```

VOCR zeigt Regel, Pfad und Zeile, aber nicht den Secret-Wert. Entferne den Fund
oder lege spaeter bewusst eine gitleaks-Baseline an.
