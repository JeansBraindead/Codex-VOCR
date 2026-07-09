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

Im aktivierten venv:

```powershell
pip install -e .
```

Pruefen:

```powershell
vocr --help
```

Erwartung: Die Hilfe zeigt Kommandos wie `vision`, `model`, `worker`,
`dispatch-ready`, `work-ready`, `learn`, `compact`, `test`.

## 5. Workspace initialisieren

```powershell
vocr setup
```

Erwartung:

- `.vocr/ledger.jsonl` wird angelegt
- `.vocr/codex-mcp.json` wird geschrieben
- Worktree-Root wird vorbereitet

Pruefen:

```powershell
vocr doctor
```

## 6. Lokales Modell mit LM Studio konfigurieren

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

## 7. OpenAI Cloud optional konfigurieren

Nur wenn du den Live-Agent-Pfad ueber OpenAI nutzen willst:

```powershell
vocr model openai --model gpt-4.1-mini
```

VOCR fragt den Key verdeckt ab und schreibt ihn in `.env`. Status zeigt den Key
nicht im Klartext.

```powershell
vocr model status
```

## 8. Codex Worker konfigurieren

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

## 9. Secret Scanner optional erweitern

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

## 10. Installation validieren

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

## 11. Standard-Dateien und Ordner

- `.vocr/ledger.jsonl`: aktueller lokaler Event-Ledger
- `.vocr/graph.json`: Graphify-Index
- `.vocr/learning.json`: verdichtete Learning-Signale
- `.vocr/archive/`: kompaktierte alte Ledger-Segmente
- `.vocr/artifacts/<task-id>/review.md`: Review-Artefakte
- `<repo>.vocr-worktrees/`: isolierte Task-Worktrees neben dem Repo

## 12. Update bestehender Installation

```powershell
cd C:\Users\jeenz\Desktop\Agent
git pull origin main
.\.venv\Scripts\Activate.ps1
pip install -e .
vocr test
```

## 13. Haeufige Probleme

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
