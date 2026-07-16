# VOCR Roadmap

Stand: 2026-07-16, nach gruenem lokalen Normalmode-Handoff.

Aktueller Nachweis:

- [Beta Handoff](beta/sessions/2026-07-16-jeenz-normalmode.md)
- Local final: green
- Cloud: noch nicht ausgefuehrt, bewusst opt-in

## Leitprinzip

Erst messen, dann entscheiden. Lokale Features bleiben nur, wenn sie in echten
Laeufen messbar helfen. Cloud bleibt die autoritative Worker-Schicht; lokale
Modelle duerfen nur trusted Input unterstuetzen und keine Plaene, Reviews oder
Promote-Entscheidungen autoritativ erzeugen.

## M0 - Lokalen Stand Stabil Halten

Status: **erledigt fuer aktuellen Handoff**

Erreicht:

- Normalmode mit sichtbarem Aktivitaetslog.
- Update-Button im Beta-Reiter.
- Final-All-in-One-Sequenz.
- Core-Beta S00-S16, S18-S20 und S23 gruen.
- Local-Live S21/S22 gegen LM Studio gruen.
- Visionary Worker Advisor fuer optimale Worker-Empfehlungen.
- Claim-Koordination fuer parallele, disjunkte Wellen.

Pflege:

- Nach jedem Patch `compileall`, Unit-Tests und relevante Beta-Szenarien.
- Wenn ein echter Lauf eine neue Fehlerklasse zeigt, als neues Beta-Szenario
  ergaenzen.

## M1 - Cloud-E2E

Ziel: opt-in Cloud-Nachweis nach lokal gruenem Stand.

Vorgehen:

1. In Normalmode Cloud-Checkbox bewusst aktivieren.
2. Finale Testsequenz oder gezielt C00/C01/C02/C03/C05/C06 starten.
3. Token-/Kostenhinweise dokumentieren.
4. Ergebnis in `docs/beta/sessions/` als neuen Handoff oder Nachtrag erfassen.

Akzeptanz:

- Lokaler Teil bleibt gruen.
- C00-C06 liefern klare Aussage: pass, skip mit Begruendung oder fail mit Diagnose.
- Keine Cloud-Ausfuehrung ohne explizites Opt-in.

## M2 - Erster Echter VOCR-Lauf

Ziel: VOCR an einem realen, nicht-trivialen Projekt verwenden.

Kandidat: LLM-Profiler oder ein kleines reales Repo-Feature.

Messpunkte:

- Qualitaet der Visionary-Klaerung.
- Task-Schnitt.
- Worker-Parallelitaet und Claim-Konflikte.
- Token-/Kontext-Overhead pro Worker-Option.
- Retry- und Review-Muster.
- Project Memory aus accepted Reviews.

Regel:

Wenn ein systematischer Fehler sichtbar wird, wird er als neues Beta-Szenario
erfasst, bevor die naechste grosse Welle kommt.

## M3 - Lokale Modelle Bewerten

Ziel: Herausfinden, ob Local Assist mehr bringt als es Komplexitaet kostet.

Basis:

- S21/S22 zeigen nur Erreichbarkeit und minimalen Chat-Smoke.
- Fuer echte Entscheidung braucht es A/B-Messungen in realen VOCR-Laeufen.

Entscheidungskriterien:

- messbare Token-/Retry-Ersparnis
- keine Injection-Ausweitung
- keine autoritative lokale Planung/Review/Promotion
- nachvollziehbare Latenz auf der lokalen Hardware

## M4 - Profilierung Und Betriebsprofile

Ziel: spaeter Profile wie `free`, `go`, `pro` aus echten Daten ableiten.

Keine Schwellwerte raten. Erst LearningStore/Telemetry aus echten Laeufen
auswerten, dann Profile konfigurieren.

Moegliche Hebel:

- Token-Budget-Modus
- Retry-Toleranz
- Slice-/Task-Groesse
- Local Assist an/aus
- Parallelitaets-Empfehlung konservativ oder durchsatzorientiert

## Nicht-Ziele

- Kein automatischer Merge ohne accepted Review.
- Kein Cloud-Run ohne explizites Opt-in.
- Kein lokales Modell als autoritativer Planner, Reviewer oder Promoter.
- Kein Feature behalten, das in Messungen keinen sinnvollen Nutzen zeigt.
