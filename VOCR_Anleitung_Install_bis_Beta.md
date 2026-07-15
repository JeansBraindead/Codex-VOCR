# VOCR — Schritt-für-Schritt: Installation bis zum ersten Beta-Ergebnis
## Windows / PowerShell · Stand: main nach Merge von feat/beta-harness (M2 der Roadmap)

Für Tier core brauchst du **keine API-Keys, kein Codex-Login, kein LM Studio** —
der Kernlauf ist vollständig deterministisch und kostet nichts.

---

## Teil 0 — Voraussetzungen (einmalig prüfen)

Öffne PowerShell und prüfe:

```powershell
git --version
py -3.11 --version
```

Fehlt etwas:

```powershell
winget install Git.Git
winget install Python.Python.3.11
```

Danach PowerShell **neu öffnen** (PATH-Aktualisierung).

---

## Teil 1 — Installation

**Schritt 1: Repo holen** (Ordner deiner Wahl, z. B. `C:\dev`):

```powershell
cd C:\dev
git clone https://github.com/JeansBraindead/Codex-VOCR.git
cd Codex-VOCR
```

Hast du das Repo schon: stattdessen aktualisieren:

```powershell
cd C:\dev\Codex-VOCR
git checkout main
git pull origin main
```

**Schritt 2: Installer ausführen** (legt `.venv` an, installiert VOCR editable,
führt den Bootstrap aus; `-Tests` lässt die Suite gleich mitlaufen, `-NoStart`
verhindert den Autostart des Normalmodus):

```powershell
powershell -ExecutionPolicy Bypass -File .\install-vocr.ps1 -Tests -NoStart
```

`-ExecutionPolicy Bypass` gilt nur für diesen einen Aufruf und ändert nichts
am System. Falls PowerShell trotzdem blockiert: `Start-VOCR.bat` nutzen (macht
dasselbe ohne Policy-Hürde).

**Erwartetes Ende:** `Installation fertig. Starte spaeter mit: .\start-vocr.ps1`
und eine grüne Testsuite.

*Manueller Weg (falls du den Installer nicht willst):*

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e .
```

---

## Teil 2 — Verifikation (dasselbe Gate wie in meinem Review)

**Schritt 3: Kompilierbarkeit + Testsuite:**

```powershell
.\.venv\Scripts\python.exe -m compileall src
.\.venv\Scripts\python.exe -m unittest discover -s tests
```

**Erwartet:** keine Compile-Fehler, `Ran 101 tests … OK` (Stand heute; nach
künftigen Commits entsprechend mehr). Ist hier etwas rot → **stoppen**, Ausgabe
sichern, nicht weitermachen.

---

## Teil 3 — Der Beta-Lauf (Tier core, kostet nichts)

**Schritt 4: Szenario-Katalog ansehen** (Orientierung, optional):

```powershell
.\.venv\Scripts\vocr.exe beta --list
```

**Schritt 5: Voller Kernlauf:**

```powershell
.\.venv\Scripts\vocr.exe beta --tier core
echo "Exit-Code: $LASTEXITCODE"
```

**Erwartet:** 19 Zeilen `passed` (S00–S16, S18, S19; S17 erscheint nicht — cloud-Tier
ohne `--allow-cloud`), zwei Report-Pfade, **Exit-Code 0**.
Exit-Bedeutung: `0` = alles grün · `1` = hartes Szenario rot (Referenzzustand
verletzt — Ausgabe sichern) · `2` = nur weiche Szenarien rot.

**Schritt 6: Report lesen:**

```powershell
Get-ChildItem .\beta_reports\
notepad .\beta_reports\beta_report_<zeitstempel>.md
```

Der Markdown-Report zeigt **Verdikt** (BESTANDEN/DURCHGEFALLEN) und die
Szenario-Tabelle mit Hart/Weich-Spalte. Das JSON daneben ist die maschinen-
lesbare Fassung (für Trends und dein späteres Modell-Sweep-Framework).

**Schritt 7: Gezielte Wiederholung** (Beispiel — nur Claims + Parallelität):

```powershell
.\.venv\Scripts\vocr.exe beta --only S18,S03
```

Das ist ab jetzt dein Alltagswerkzeug: nach **jeder** Änderung am Code einmal
`vocr beta --tier core` — 30 Sekunden, null Kosten, und du weißt, ob die
Pipeline noch hält.

---

## Teil 4 — Optional: Tier local (LM Studio, S12/S13 live)

Nur wenn du die lokalen Flags live testen willst. LM Studio aus = Szenarien
werden sauber „skipped", **kein** Fail.

**Schritt 8: LM Studio vorbereiten:** Server starten (Standardport 1234),
zwei Modelle verfügbar machen: dein Chat-Modell (GPT-OSS 20B) **und** ein
Embedding-Modell (z. B. nomic-embed-text als GGUF — das Chat-Modell kann keine
Embeddings). Modell-IDs anzeigen:

```powershell
curl http://localhost:1234/v1/models
```

**Schritt 9: Env setzen (gilt nur für diese PowerShell-Sitzung) und laufen lassen:**

```powershell
$env:VOCR_EMBED_BASE_URL = "http://localhost:1234/v1"
$env:VOCR_EMBED_MODEL    = "<embedding-modell-id aus Schritt 8>"
$env:VOCR_LOCAL_BASE_URL = "http://localhost:1234/v1"
$env:VOCR_LOCAL_MODEL    = "<chat-modell-id aus Schritt 8>"
.\.venv\Scripts\vocr.exe beta --tier local
```

Danach Fenster schließen oder Variablen löschen — der Referenzzustand
(alles aus) bleibt dein Normalfall:

```powershell
Remove-Item Env:VOCR_EMBED_BASE_URL, Env:VOCR_EMBED_MODEL, Env:VOCR_LOCAL_BASE_URL, Env:VOCR_LOCAL_MODEL
```

---

## Teil 5 — Optional: Tier cloud (S17) — **kostet Codex-Kontingent**

Nur mit eingerichtetem, eingeloggtem Codex CLI. Maximal 3 echte Tasks
(Default-Cap):

```powershell
.\.venv\Scripts\vocr.exe beta --tier cloud --allow-cloud --max-cloud-tasks 3
```

Empfehlung: erst am **Anfang** eines frischen 5h-Fensters, nicht an der Kante.
Für M2 der Roadmap ist dieser Schritt **nicht nötig** — Tier core reicht.

---

## Teil 6 — Ergebnis-Einordnung & bekannte Lücken

**Was du nach Teil 3 hast:** den Beweis, dass die komplette v3-Pipeline
(Contract, Guards, Ratchet, Budget, Claims, Parallel-Kopplung, Memory-Gating)
auf deiner Maschine hält — als Verdikt mit Szenario-Status, reproduzierbar.

**Zwei Lücken aus meinem Review, ehrlich benannt:**
1. **S11 misst nichts:** Das Szenario prüft die Byte-Konstanz des
   Contract-Prompts, schreibt aber keine Token-Metriken ins JSON
   (`"metrics": {}`). Die eigentliche M2-Zahl — Prompt-Token legacy vs.
   contract in Prozent — fehlt damit noch.
2. **Report ist minimal:** Verdikt + Tabelle, aber ohne den in B5
   spezifizierten KPI-Block, Modus-Block (Cloud vs. Hybrid getrennt) und
   Trendvergleich zum Vorlauf.
Beides sind kleine Nachrüstungen am Harness, kein Umbau. Sag Bescheid, dann
schreibe ich den Fix-Prompt dafür — danach liefert Schritt 5 die Zahlen von
selbst.

---

## Troubleshooting

| Symptom | Ursache / Lösung |
|---|---|
| `vocr` nicht gefunden | Vollen Pfad nutzen: `.\.venv\Scripts\vocr.exe`, oder venv aktivieren: `.\.venv\Scripts\Activate.ps1` |
| PowerShell blockiert Skripte | `-ExecutionPolicy Bypass` beim Aufruf mitgeben oder `Start-VOCR.bat` nutzen |
| `Python 3.11+ wurde nicht gefunden` | `winget install Python.Python.3.11`, PowerShell neu öffnen |
| Tests rot in Teil 2 | Stoppen, komplette Ausgabe sichern — nicht mit rotem Fundament weitermachen |
| Tier local: alles „skipped" | LM Studio-Server läuft nicht oder Env-Variablen fehlen (Schritt 9) |
| Exit-Code 1 beim Beta-Lauf | Hartes Szenario verletzt — Report-MD + Konsolenausgabe sichern, Szenario-ID nennen |
