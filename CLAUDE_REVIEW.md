# CLAUDE_REVIEW

Start: 2026-07-10 19:13 Europe/Berlin
Branch: `vocr-autopilot-2026-07-10`

Claude ist fuer diesen Lauf nur ein externes, read-only Review-Signal.
Claude ist kein VOCR-Produktbestandteil und kein Gate.

## Verfuegbarkeit

- [19:13] `claude -p "ok"` konnte nicht laufen: CLI nicht gefunden.
- Retry bis 20:15 Europe/Berlin vorgesehen.
- [19:17] Retry fuer Installer-Diff uebersprungen: CLI nicht gefunden.
- [19:23] Retry fuer Installer-Clone-Diff uebersprungen: CLI nicht gefunden.
- [19:27] Retry fuer Installer-Python-Version-Diff uebersprungen: CLI nicht gefunden.
- [19:31] Retry fuer BAT-Fallback-Diff uebersprungen: CLI nicht gefunden.
- [19:36] Retry fuer Native-Command-Diff uebersprungen: CLI nicht gefunden.
- [19:40] Retry fuer Start-Script-Diff uebersprungen: CLI nicht gefunden.
- [19:48] Retry fuer CLI-Clone-Diff uebersprungen: CLI nicht gefunden.
- [19:54] Retry fuer Archive-Retention-Diff uebersprungen: CLI nicht gefunden.
- [resume] Retry fuer Learning-Signale-Diff uebersprungen: CLI nicht gefunden.
- [resume] Retry fuer MCP-Promote-Diff uebersprungen: CLI nicht gefunden.
- [resume] Retry fuer Learning-Review-Dauer-Diff uebersprungen: CLI nicht gefunden.
- [resume] Retry fuer PR-Review-Diff uebersprungen: CLI nicht gefunden.
- [resume] Retry fuer Clarification-Qualitaetsproxy-Diff uebersprungen: CLI nicht gefunden.
- [resume] Finaler Retry nach Teststage-Smoke uebersprungen: CLI nicht gefunden.

## Reviews

## 2026-07-11 - Extern nachgereichter Claude-Review

Status: Review vom User bereitgestellt; lokaler `claude` CLI-Call bleibt uebersprungen.

### Befund

- Scope/Phasenspec: `VOCR_Phasen_Upgrade.md` fehlt im Repo. Codex hat das korrekt als `NEEDS_HUMAN` geloggt, aber die strikte Phasenfolge aus dem Autopilot-Auftrag ist dadurch nicht nachweisbar.
- Isolation/Gates: `vocr_promote` im MCP-Server verlangt `confirm=true` und nutzt denselben `promote_task`-Pfad wie die CLI. Kein Gate-Bypass.
- Robustheit: Installer-/Bootstrap-Clone schuetzt belegte Fremdordner. LM-Studio-Discovery faellt sauber ueber `/v1/models`, `/api/v1/models`, `/api/v0/models` und erkennt Fake-200-Antworten.
- Tests: `pip install -e .`, `compileall` und 55 Unit-Tests liefen im Review-Kontext gruen.
- Hinweis: `clean --archives` loescht Ledger-Archive dauerhaft per `unlink()`, ohne Trash-Fallback.

### TODO

- Fehlende `VOCR_Phasen_Upgrade.md` nachreichen oder bestaetigen, dass die improvisierte Phasenreihenfolge akzeptiert ist.
- Installer-Skripte auf echtem Windows per Doppelklick/PowerShell manuell verifizieren.
- `--post-pr-review` gegen einen echten Test-PR validieren.
- LM-Studio Auth, Endpoint-Fallback und Chat-Smoke gegen einen echten laufenden Server mit passendem Token gegenzeichnen.
- Hinweis zu dauerhaftem `clean --archives` in Doku aufnehmen.
- Optional spaeter: echte Claude-Reviews pro Phase nachholen, falls die Phasengrenzen separat auditiert werden sollen.
