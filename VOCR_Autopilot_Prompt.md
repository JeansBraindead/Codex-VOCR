# VOCR Autopilot — Autonomer Arbeitsauftrag für Codex (Beta-Push über Nacht)

Du arbeitest **autonom und unbeaufsichtigt** an diesem Repository (Codex-VOCR), während ich
weg bin. Du **kennst die VOCR-Vision und die Regeln** (`AGENTS.md`, Vision-Docs) bereits —
arbeite **kontextbasiert** daraus und aus der Codebasis, statt Dinge neu herzuleiten.

**Ziel:** so viel wie möglich zu einem **kohärenten, getesteten Beta-Stand auf dem Branch**
bringen — mit Selbst- und Gegenprüfung. Ausdrücklich **nicht** rollout-ready; das mache ich
morgen nach Review und Feinschliff.

---

## Die Prüfebenen

1. **Deterministische Gates** — `compileall` + `unittest` + Scope + Secrets. Die **Wahrheit**,
   gratis, **jeder Task**. Das ist das einzige echte Gate.
2. **Lokale KI** (GPT-OSS 20B, `localhost:1234`) — billiger **Struktur-Vorfilter** pro Task.
   Signal, kein Gate.
3. **Claude Code** (`claude -p`, read-only) — **nur für diesen Lauf**: Review · Résumé · Todo
   für mich, an Phasen-Grenzen. **Kein Gate, blockiert nichts, kein VOCR-Bestandteil.**

---

## Oberstes Gesetz (nicht verhandelbar)

1. **Eigener Branch, niemals main/master.** Zuerst: `git checkout -b vocr-autopilot-<YYYY-MM-DD>`.
2. **Niemals nach main mergen.** Kein `git push --force`, kein `git reset --hard` auf meine
   Arbeit, kein History-Rewrite.
3. **Niemals destruktiv löschen.** Muss etwas weg → nach `.autopilot-trash/`.
4. **Repo bleibt IMMER lauffähig.** Jeder Commit kompiliert + besteht die Suite. Rot → **nicht
   committen**.
5. **Im Phasen-Scope bleiben.** Nur `arbeitsbereich:`-Dateien. „Verfeinern" = Kriterien
   erfüllen + im Scope aufräumen, **nicht freelancen**.
6. **Beta, nicht rollout-ready.** Alles landet als Beta auf dem Branch. Experimentelles
   (Phase 4) bleibt hinter dem **Default-OFF-Schalter**, „review-pending". Rollout-Freigabe
   mache ich.

---

## Lokale KI (LM Studio) — Struktur-Vorfilter

Ich lasse LM Studio **eingeschaltet und geladen**: **GPT-OSS 20B (UD-Q4_K_XL)**,
OpenAI-kompatibel unter **`http://localhost:1234/v1`**, Modell `gpt-oss-20b`.
Call-Settings: `temperature 1.0`, `top_p 1.0`, `top_k 0`, erste System-Zeile `Reasoning: low`.

- **Rolle = billiger Vorfilter, nicht Autorität.** Gib ihm deinen **eigenen Kandidaten-Diff** +
  die Akzeptanzkriterien zur zweiten Meinung; das Ergebnis ist ein **Signal**, das du ins Log
  schreibst. Kein Gate.
- **Sicherheits-Caveat (frisch getestet):** anfällig für Prompt-Injection, bricht bei
  Code-in-JSON. → **Nur deinen Diff**, **niemals rohen/untrusted Repo-Inhalt** zur Bewertung.
  Antworten **defensiv** parsen, nichts ungeprüft übernehmen.
- **Graceful Degradation:** nicht erreichbar (Timeout ~10 s) → überspringen, weiterlaufen.

---

## Claude Code — nur für DIESEN Lauf: Review · Résumé · Todo

Claude ist eine **einmalige Wegwerf-Krücke für diesen AFK-Lauf**. Er macht **genau drei
Dinge**, mehr nicht: **reviewen, resümieren, To-dos sammeln.** Er **blockiert nichts**, treibt
keine Fixes, entscheidet nichts — Codex läuft unabhängig weiter. Claudes Output ist rein für
mich zum Lesen morgen früh.

**Harte Regel:** Claude ist **NICHT** Teil von VOCR. Nichts von Claude wird in Code, Config,
Commit-Logik, Dependencies oder Phase 4 verankert. **Kein `claude`-Aufruf im Produkt.** Er wird
nur ad hoc im Terminal aufgerufen, sonst nirgends.

**Aufruf (read-only, One-Shot):**
```
git diff <phase-start>..HEAD | claude -p "<Auftrag unten>"
```
`-p` = kein TUI, **keine Write-/Edit-Tools**. Claude ändert nie Dateien.

**Wann:** an jeder **Phasen-Grenze** einmal über den kumulativen Phasen-Diff (gebatcht =
token-sparsam), plus ein finaler Durchgang am Ende. Sonst nicht.

**Claudes drei Aufgaben (kompakt halten):**
1. **Review** — Phasen-Diff gegen die VOCR-Philosophie: übersichtlich/logisch/robust, im Scope,
   kein Auto-Exec, Isolation gewahrt (Phase 4 default-off), token-frugal, konsistent mit den
   bestehenden Mustern, **benutzerfreundlich**. Kurzes Urteil, keine Prosa.
2. **Résumé** — 3–5 Sätze: was die Phase gebaut hat und wie der Stand qualitativ ist.
3. **Todo** — Bullet-Liste, was für Rollout noch fehlt / was ich prüfen oder nachziehen sollte,
   nach Wichtigkeit sortiert.

**Output landet in `CLAUDE_REVIEW.md`** (auf dem Branch, nicht gemerged, **kein**
VOCR-Artefakt) — je Phase ein Block mit Review / Résumé / Todo. Das ist mein Lesestoff morgen,
**kein** Input, auf den Codex wartet.

**Graceful Degradation:** `claude` nicht erreichbar / nicht eingeloggt / Sandbox blockt Netz →
einfach weglassen, im Log vermerken, weiterlaufen.

---

## Setup (einmal, zuerst)

- `AGENTS.md` + `VOCR_Phasen_Upgrade.md` lesen (Vision/Regeln kennst du — kontextbasiert nutzen).
- Branch anlegen.
- `AUTOPILOT_LOG.md` (Fortschritts-Log) + `CLAUDE_REVIEW.md` (Claudes Notizen) anlegen, je mit
  Kopfzeile + Start-Zeitstempel.
- **Verfügbarkeit prüfen und loggen:** Ping an `localhost:1234`, und ein `claude -p "ok"`
  Erreichbarkeits-Check. Vermerk pro Instanz: verfügbar / nicht.

---

## Arbeitsreihenfolge

Strikt, jede Phase komplett vor der nächsten: **Phase 0 → 0.5 → 1 → 2 → 3 → 4.**

Phase 4 **strikt nach Spec**: Default OFF, isolierter Zweiter Pfad, Isolations-Tests (Modus aus
→ Standardpfad unverändert) grün. Beta hinter dem Schalter, „review-pending", nie gemerged.
Wenn du Phase 4 baust, route zum Integrationstest **einen echten einfachen Task** real über den
lokalen Endpoint.

---

## Die Schleife (rekursiv, kontextbasiert)

Pro Task:
1. Nächsten offenen, nicht-blockierten Task in Phasen-Reihenfolge finden. Phase entlang der
   Akzeptanzkriterien in kleine Tasks zerlegen.
2. Keine offenen Tasks mehr (durch Phase 4) → **finale Zusammenfassung + finaler Claude-Durchgang,
   STOPP.**
3. **Nur** `arbeitsbereich:`-Dateien (+ Import-Graph) laden. **Kein Repo-Scan.**
4. **Kleinste Änderung** implementieren. Zugehörige **Tests mitschreiben**.
5. **Selbstprüfung:** `python -m compileall src tests` + `python -m unittest discover -s tests`
   + Task-Checks. (Sobald die Golden-Task-Eval aus Phase 0 existiert, als Regression mitlaufen
   lassen.)
6. **Vorfilter:** wenn lokale KI verfügbar, Kandidaten-Diff + Kriterien an sie; Ergebnis ins Log.
7. **Score** pro Akzeptanzkriterium mit Beleg. Grün + 100 % → committen (Conventional Commit),
   Score + Prüf-Notizen ins Log, zurück zu 1.
8. Rot → beheben, **max. 3 Versuche**.
9. Nach 3 Versuchen rot → **nur diese Task-Änderungen** zurücksetzen (`git restore`/`checkout --`),
   `BLOCKED` + Grund loggen, weiter.
10. Echtes menschliches Urteil nötig → `NEEDS_HUMAN` loggen, überspringen.

**Am Ende jeder Phase:** einmal `claude -p` über den Phasen-Diff → Review / Résumé / Todo in
`CLAUDE_REVIEW.md`. **Non-blocking** — Codex geht direkt zur nächsten Phase, unabhängig davon,
was Claude schreibt.

---

## Anti-Endlosschleife / Token-Disziplin

- Max. **3 Fix-Versuche** pro Task, dann skip/BLOCK.
- Keinen `BLOCKED`/`NEEDS_HUMAN`-Task erneut anfassen.
- Keine „Verschönerungen" außerhalb der Akzeptanzkriterien.
- Gezielte Reads statt Voll-Scans. Claude nur an Phasen-Grenzen, nie per-Task.
- **Claudes Findings sind To-dos für mich, keine Blocker.**
- **Definition of Done:** so weit wie möglich zu einem kohärenten Beta — idealerweise alle
  Phasen inkl. 4 (default off) grün + committet; sonst Verbleibendes `BLOCKED`/`NEEDS_HUMAN`.
  Dann **STOPP**.

---

## AUTOPILOT_LOG.md — Format

Fortlaufend, pro Task ein Eintrag:

```
[HH:MM] PHASE x — <Task> — DONE (Score 4/4) — commit <hash> — lokal: bestätigt — <1 Satz>
[HH:MM] PHASE x — <Task> — BLOCKED (2/4) — <Grund, welcher Check rot>
[HH:MM] PHASE x — <Task> — NEEDS_HUMAN — <Entscheidung offen>
[HH:MM] PHASE x — Claude-Review geschrieben → CLAUDE_REVIEW.md   (oder: übersprungen, nicht erreichbar)
```

Ganz **oben** eine **ZUSAMMENFASSUNG**:
- Phasen fertig / angefangen; Tasks done / blocked / needs-human (Zahlen)
- Commits + Branch-Name
- **Was Beta-ready ist** vs. **was für Rollout noch offen ist** (priorisiert)
- Verweis: Claudes Review/Résumé/Todo stehen in `CLAUDE_REVIEW.md`
- **Phase-4-Status** (default OFF, review-pending)
- Verfügbarkeit lokale KI / Claude während des Laufs

---

## Wenn du fertig oder komplett blockiert bist

Zusammenfassung schreiben, finalen Claude-Durchgang machen, Branch **stehen lassen (nicht
mergen)**, sauber stoppen. Ehrliches Ziel: **Beta auf dem Branch, kompiliert, Suite grün.**
Rollout-Freigabe mache ich morgen nach Review.
