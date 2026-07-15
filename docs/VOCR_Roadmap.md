# VOCR — Roadmap
## Lineare Reihenfolge aller Arbeitspakete, Stand nach Gesprächen 1–5

Diese Roadmap sortiert alles, was wir erarbeitet haben, in eine ausführbare Reihenfolge.
Grundprinzip der Sortierung: **erst bauen, was Messungen ermöglicht — dann messen —
dann auf Basis der Zahlen entscheiden.** Keine Bauch-Entscheidung über lokale Features,
bevor echte Zahlen auf deiner Hardware vorliegen.

---

## Bestandsaufnahme — was existiert bereits

**Fertige Artefakte (Bauaufträge, kein Code):**
- `VOCR_Phasenplan_Final.md` — Contract-Handoff + Token-Ökonomie + **Parallelisierung
  (Scope-Claims + Parallel-Waves)** + **Projektgedächtnis**, 16 Phasen (0–15).
- `VOCR_Beta_Testsequenz_Prompt.md` — Prüfstand `vocr beta`, 18 Szenarien (S00–S17),
  inkl. Addendum M (Modell-Matrix-Anschluss) und Dual-Mode-Pflicht.
  **Offen: 3 neue Szenarien für Claims/Parallel/Memory (S18–S20) vor M1 ergänzen.**
- `LLM_Profiler_Bauauftrag.md` — Standalone-Werkzeug `llm-profiler`, 9 Phasen.
- (`VOCR_Contract_Handoff_Prompt.md` v1 und `VOCR_Phasenplan_v2.md` — **überholt durch
  Final, ignorieren**.)

**Offene Entscheidungen — jetzt beantwortet:**
- Lokaler Modus wird **nicht vorab gekickt**, sondern nach Messung entschieden.
- Pre-Dispatch-Validierung ist ein **Kandidat**, kein beschlossenes Feature.
- Werkzeug-Reihenfolge: **VOCR baut den Profiler selbst** (nicht Profiler zuerst extern).

**Leitplanken, die über alles gelten:**
- Cloud-first, Hybrid nur auf Wunsch (v2 Regel 9).
- Lokale Modelle nur trusted Input + nicht-autoritativer Output (Trust-Matrix).
- Nichts wird gemergt ohne dein Go; alle neuen Verhalten default-off.

---

## MEILENSTEIN 0 — Fundament: v2 umsetzen
**Ziel:** Der Contract-Handoff und die Token-Ökonomie stehen im Code.
**Werkzeug:** Codex oder Claude Code, Input = `VOCR_Phasenplan_v2.md`.
**Kosten:** Cloud-Kontingent (Coding-Sessions über mehrere 5h-Fenster).

**Schritte:**
1. Plan am Stück übergeben; die STOP-Gates zerlegen ihn in freigabepflichtige Phasen.
2. Realistische Taktung auf Plus: eine große Phase (1, 2, 7) pro 5h-Fenster, kleine
   (4, 6) mehrere zusammen. Bei Limit-Hit: Fenster abwarten, `git status`, „setze
   Phase N fort" — die Akzeptanzkriterien sind die Wiedereinstiegs-Checkliste.
3. **Block A (0–3)** ist Pflicht-Fundament (Contract, Review, Ratchet).
   **Block B (4–9)** ist die Token-Ökonomie.
   **Block C (10–11, lokal/embed)** kann man hier schon mitbauen ODER bis nach der
   Messung (Meilenstein 3) aufschieben — beides ist konsistent, da default-off.
   **Empfehlung:** Block C mitbauen, weil der Beta-Test (M1) und die Messung (M3) die
   Flags sonst nicht prüfen können.

**Abschluss:** Default-Lauf verhält sich identisch zu `main`; alle v2-Flags existieren,
default-off. **Kein Merge — nur Branch.**

**→ Danach: gemeinsame Durchsprache** (von dir gewünscht: „nachdem ich v2 drin habe
nochmal alles durchgehen"). Erst dann Meilenstein 1.

---

## MEILENSTEIN 1 — Prüfstand bauen: `vocr beta`
**Ziel:** Ein wiederverwendbares Testinstrument, das die v2-Zusagen prüft — für den
gesamten Beta-Zyklus, nicht einmalig.
**Werkzeug:** Codex/Claude Code, Input = `VOCR_Beta_Testsequenz_Prompt.md`.
**Kosten:** Einmalig Cloud-Kontingent (Coding-Session).

**Schritte:**
1. Setzt v2 voraus — Phase B0 verifiziert das und hält an, falls v2 fehlt.
2. Bauen bis inkl. B5 (Report + Trend). B6 (Tier local/cloud) und B7 (Doku) danach.
3. Kernstück ist der ScriptedWorker + Mocks — deshalb kostet **Tier core keinen
   Kontingent** und wird zum täglichen Instrument.

**Abschluss:** `vocr beta` läuft; erzeugt Markdown+JSON-Report mit Verdikt, KPIs, Trend.

---

## MEILENSTEIN 2 — Erste Prüfung + Baseline-Zahlen
**Ziel:** Beweisen, dass die v2-Pipeline hält — und die **sicheren Cloud-Sparhebel**
mit echten Zahlen belegen. Kostet fast nichts.

**Schritte:**
1. `vocr beta` (Tier core) — voller Herz-und-Nieren-Check, **null Kontingent**.
   Muss grün sein, insbesondere S00 (reiner Cloud-Referenzzustand).
2. **Baseline-Messung der sicheren Hebel** aus den weichen Szenarien ablesen:
   - S11: reale Prompt-Token-Ersparnis `legacy` vs. `contract` (Prefix-Caching).
   - (Optional erweitern: A/B mit/ohne Span-Kontext [P7], mit/ohne inkrementelles
     Review [P9], um deren realen Anteil zu sehen.)
3. **Erwartung:** Diese Cloud-Hebel liegen zweistellig. Das ist die Vergleichsbasis,
   gegen die sich lokale 1–2 % später messen lassen müssen.

**Abschluss:** Belastbare Prozentzahlen für die sicheren Sparhebel. Pipeline verifiziert.

---

## MEILENSTEIN 3 — Erstes echtes VOCR-Projekt: den Profiler bauen lassen
**Ziel:** VOCR benutzt sich selbst, um das Werkzeug zu bauen, das später seine eigenen
lokalen Entscheidungen misst. Sauberer Bootstrap (VOCR-Local ist noch default-off).
**Werkzeug:** VOCR selbst (Cloud-Worker), Input = `LLM_Profiler_Bauauftrag.md` als
**Vision-Input**.
**Kosten:** Cloud-Kontingent (erster produktiver VOCR-Lauf).

**Schritte:**
1. Den Profiler-Bauauftrag nicht als Einzeiler geben, sondern als durchdachte Spec in
   VOCRs Vision/Organize-Schritt einspeisen — VOCR zerlegt die 9 Phasen in eigene
   Slices/Tasks.
2. **Doppelter Testwert:** Du siehst gleichzeitig, ob VOCR gut *plant* (Organize) und
   gut *baut* (Worker/Review) — am realen, nicht-trivialen Projekt.
3. Ergebnis: ein lauffähiges `llm-profiler`-Repo, standalone, provider-agnostisch.

**Arbeitsmodus M3 — die Iterationsschleife (WICHTIG):**
M3 ist der eigentliche **Findungslauf** — hier tauchen die Probleme auf, die kein
Beta-Szenario vorhersieht (schlecht geschnittene Tasks, überraschende Retry-Muster,
zu dünner Kontext, kaputte Contracts). Der Beta-Test *sichert* bekannte Eigenschaften;
M3 *findet* die unbekannten. Reihenfolge pro Zyklus:

1. **Lauf** — eine Slice/Task-Welle durch VOCR schicken.
2. **Auswerten** — Ledger, Telemetrie, Review-Ergebnisse lesen. Was ist gescheitert,
   was hat unnötig Tokens gekostet, wo hat der Worker exploriert statt gezielt zu
   arbeiten?
3. **Diagnose** — Ursache benennen (Task zu groß? Kontext falsch? Contract-Lücke?).
   Nicht raten — die konkrete Stelle im Artefakt/Ledger zeigen.
4. **Fix** — entweder Konfiguration (Flag, Slice-Größe) oder Code-Patch über einen
   kleinen Auftrag an Codex.
5. **Regressionswächter setzen (der entscheidende Schritt):** War die Ursache ein
   **systematischer** Fehler (nicht bloß ein Einzelfall), dann ein **neues
   Beta-Szenario** formulieren, das genau diesen Fehler künftig abfängt (S22, S23, …).
   So wächst die Suite mit jedem echten Lauf — der Test lernt aus der Realität, statt
   statisch zu bleiben.
6. **Nachtesten** — `vocr beta --tier core` beweist, dass der Fix nichts anderes
   gebrochen hat; erst dann nächste Welle.

**Merke:** Der Beta-Test läuft **einmal pro Änderung** (deterministisch — Wiederholung
ohne Codeänderung bringt null neue Information). Die Iteration hängt an *Änderungen*,
nicht an Durchläufen. Mehrfachläufe sind nur bei den nicht-deterministischen
Live-Szenarien (S20/S21, echtes Modell) sinnvoll — dort ist Varianz echt und bereits
über Median/Wiederholungen eingeplant.

**Abschluss:** Der Profiler existiert als echtes Werkzeug, gebaut durch VOCR — **und**
die Beta-Suite ist um die real aufgetretenen Fehlerklassen gewachsen.

---

## MEILENSTEIN 4 — Modelle vermessen
**Ziel:** Herausfinden, welches lokale Modell für welche Rolle taugt — und die Zahlen
sammeln, die die aufgeschobenen Entscheidungen beantworten.
**Werkzeug:** `llm-profiler` (lokal, LM Studio / llama.cpp).
**Kosten:** Kein Cloud-Kontingent — nur GPU-Zeit auf der 5080.

**Schritte:**
1. Kandidaten-GGUFs durch den Profiler schicken (Karussell: Liste abends, Reports
   morgens). Achse 5 (Injection-Resistenz) ist hier besonders wichtig.
2. `match vocr_local_assist` → welches Modell wäre überhaupt geeignet?
3. Ergebnis ist eine **Fähigkeitsdatenbank** — auch für alle Zukunftsprojekte
   wiederverwendbar (neues Projekt = neues Profil schreiben, sofort ranken).

**Abschluss:** Belastbares Modell→Rolle-Mapping auf deiner Hardware.

---

## MEILENSTEIN 5 — Die aufgeschobenen Entscheidungen treffen (mit Zahlen)
**Ziel:** Jetzt — und erst jetzt — über die lokalen Features entscheiden, auf Basis von
Messungen statt Bauchgefühl.

**Entscheidung A — Lokalen Modus behalten oder kicken?**
- Gezieltes A/B im Beta-Test: dieselbe Task-Wave mit/ohne `VOCR_LOCAL_ASSIST`, reale
  Worker-Token aus der Telemetrie vergleichen.
- Regel: Bringt es < ~2 % und existiert ein injection-resistentes Modell nicht →
  **kicken** (deine eigene Doktrin: Features müssen sich rechtfertigen). Bringt es
  spürbar mehr → behalten, Flag bleibt opt-in.

**Entscheidung B — Pre-Dispatch-Validierung bauen?**
- Das ist der einzige lokale Kandidat mit *Brocken*-Potenzial: lokales Modell prüft den
  **trusted Task-Contract** VOR dem Cloud-Start auf Ausführbarkeit (Scope-Widersprüche,
  fehlende Dateien, Kriterien vs. non-goals). Narrensicher (trusted Input,
  nicht-autoritativer Output) und spart potenziell einen ganzen überflüssigen
  Cloud-Aufruf — die Lücke, die v2 offen lässt (v2 fängt Retry-*Ketten*, nicht den
  kaputten *ersten* Aufruf).
- Messung: A/B mit/ohne lokalem Contract-Check, eingesparte Retry-Sessions in der
  Telemetrie zählen. Effekt hängt davon ab, wie oft dein Organize kaputte Tasks baut —
  genau das ist jetzt messbar.
- Entscheidung: rechnet es sich → als neue v2-Phase spezifizieren und bauen; nicht →
  verwerfen.

**Abschluss:** Klare, begründete Entscheidungen. Lokale Komplexität existiert nur da,
wo sie sich in Zahlen rechtfertigt.

---

## MEILENSTEIN 6 — Abo-Profile (Free / Go / Pro)
**Ziel:** VOCR mit `--profile free|go|pro` starten; das Profil bündelt die v2-Flags zu
einer kohärenten Betriebsdisziplin, die zum jeweiligen Kontingent passt.
**Voraussetzung:** **Daten aus dem LearningStore.** Erst nach mehreren echten Läufen
(ab M3) enthält `LearningEntry` reale `estimated_tokens`/`retry_count`-Verteilungen —
die Schwellenwerte werden **abgelesen, nicht geraten.**
**Kosten:** Gering — im Kern eine Config-Phase (eine YAML pro Tier + `--profile`-Option).

**Was ein Profil kann — und was nicht (ehrlich):**
- **Kann:** Verhalten steuern (Budget-Faktor, Retry-Toleranz, Slice-Größe, ob
  Local-Assist an ist, warn vs. block). Bündelt bestehende v2-Flags zu einer Haltung.
- **Kann nicht:** Das Abo-Limit von außen abfragen oder den Verbrauch einer einzelnen
  Session vorhersagen (Codex-Limits sind grobe Spannen über drei Meter, keine
  programmierbaren Zahlen). Ein Profil senkt Verbrauch und pausiert früher — es
  **ersetzt** das Limit nicht; Rückfall bleibt „Fenster abwarten / Credits".

**Profil-Skizzen (Schwellen erst aus LearningStore-Daten festlegen):**
- **Free/Go — „jeder Token zählt":** `VOCR_TOKEN_BUDGET_MODE=block`, niedriger Faktor
  (Retries früh stoppen, an Mensch zurückgeben), kleine Slices, `INCREMENTAL_REVIEW=true`,
  Local-Assist an *falls* M5 es rechtfertigt.
- **Pro — „Durchsatz":** höherer Faktor oder `warn`, größere Slices, Local-Assist eher
  aus (1–2 % lohnen bei reichlich Kontingent nicht).

**Einziger echter Neubau:** Die **Slice-Größe** im Organize-Schritt ist in v2 nicht
parametrisiert — ein Profil, das „kleine Tasks für Free, große für Pro" steuert, braucht
diesen Hebel als eigene kleine Phase. Alle anderen Profil-Bestandteile (Budget-Mode,
Faktor, Incremental-Review, Local-Assist) existieren bereits.

**Grenze im Blick:** Profile entstehen aus **deinen** Mustern (Hardware, Projekttypen).
Ideal für dich als Einzelnutzer; für fremde Nutzer bräuchten sie eigene Sammelphasen
oder konservativere Defaults. Kein Thema jetzt — nur relevant, falls VOCR je weitergegeben
wird.

**Abschluss:** Datenbasierte Abo-Profile als Ernte aus allem davor — kein Ratespiel.

---

## Überblick als Sequenz

```
M0  v2 bauen ........................ Cloud-Kontingent ... [dann Durchsprache]
M1  vocr beta bauen ................. Cloud-Kontingent (einmalig)
M2  prüfen + Baseline messen ........ ~gratis (Tier core)
M3  Profiler via VOCR bauen ......... Cloud-Kontingent (1. echtes Projekt)
M4  Modelle vermessen ............... gratis (nur GPU)
M5  lokale Features entscheiden ..... datenbasiert
M6  Abo-Profile (Free/Go/Pro) ....... Config + 1 kleiner Neubau (Slice-Größe)
```

**Kritischer Pfad:** M0 → M1 → M3 sind die kontingentkostenden Bauschritte.
M2, M4 sind quasi gratis. M5 ist reine Entscheidung. M6 erntet die gesammelten
LearningStore-Daten und ist überwiegend Config.

**Zwei Schleifen, nicht verwechseln:**
- *Regressionswächter* (Beta-Test): läuft **pro Änderung**, sichert bekannte
  Eigenschaften, ein Durchlauf reicht (deterministisch). Ausgelöst von Commits.
- *Findungsschleife* (M3): läuft **pro produktivem Lauf**, deckt unbekannte Probleme
  auf, speist neue Fehlerklassen als Beta-Szenarien zurück. Ausgelöst von echten
  VOCR-Läufen. Die Auswertungs-Iteration, nach der du gefragt hast, sitzt hier.

**Zwei natürliche Pausenpunkte**, an denen du innehalten und neu bewerten kannst, ohne
etwas zu verlieren: nach M0 (Durchsprache, von dir gewünscht) und nach M2 (Baseline-
Zahlen liegen vor — spätestens hier ist klar, ob lokal sich überhaupt lohnt).

---

## Was NICHT auf der Roadmap steht (bewusst)

- **Kein Merge** irgendwo automatisch — jede Promotion ist deine Entscheidung.
- **Keine lokale Rolle über den erlaubten Quadranten hinaus** — Diff-/Check-Output-
  Zusammenfassung bleibt verboten (untrusted).
- **Kein LLM-Judge** im Profiler — Bewertung ~90 % deterministisch, Rest opt-in Blind-A/B.
- **Kein Gesamtscore** im Profiler — Profil + Mapping, kein Ranking.
