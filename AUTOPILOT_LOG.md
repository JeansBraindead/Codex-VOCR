# AUTOPILOT_LOG

## ZUSAMMENFASSUNG

- Branch: `vocr-autopilot-2026-07-10`
- Phasen fertig / angefangen: 0 angefangen; Installer-Fix abgeschlossen; Phase-Spec `VOCR_Phasen_Upgrade.md` fehlt.
- Tasks done / blocked / needs-human: 17 done / 0 blocked / 1 needs-human.
- Commits: 17 auf diesem Branch nach LM-Studio-Endpoint-Fix.
- Beta-ready: sichtbarer Windows-Installer im Repo-Root, Clone-aus-leerem-Ordner, portable Script-Generierung, Bootstrap-Tests und Teststage-Smokes gruen.
- Rollout offen: echte Review durch User, fehlende Phasen-Spec nachreichen, Installer manuell auf Windows doppelklicken, PR-Review-Posting gegen echten Test-PR validieren.
- Claude Review / Resume / Todo: siehe `CLAUDE_REVIEW.md`.
- Phase-4-Status: nicht begonnen; default OFF / review-pending bleibt unveraendert.
- Lokale KI: LM Studio erreichbar, aber `/v1/models` liefert 401 Auth.
- Claude: `claude` CLI aktuell nicht gefunden; Retry bis 20:15 Berlin-Zeit vorgesehen.

## LOG

[19:11] SETUP - Autopilot-Prompt gelesen - Branch-Regeln uebernommen.
[19:12] SETUP - `VOCR_Phasen_Upgrade.md` fehlt - NEEDS_HUMAN - Phasen 0 bis 4 koennen nicht exakt aus Spec abgearbeitet werden.
[19:13] SETUP - LM Studio Check - WARN - `http://localhost:1234/v1/models` liefert 401 Auth.
[19:13] SETUP - Claude Check - WARN - `claude` CLI nicht gefunden; non-blocking Retry bis 20:15.
[19:17] PHASE installer - Sichtbare Windows-Installer - DONE (Score 4/4) - commit pending - lokal: compileall/unittest gruen - Repo enthaelt install-vocr.ps1, start-vocr.ps1 und Start-VOCR.bat.
[19:23] PHASE installer - Clone-Flow fuer leere Ordner - DONE (Score 4/4) - commit pending - lokal: compileall/unittest/PS syntax gruen - install-vocr.ps1 kann ohne pyproject nach Codex-VOCR klonen.
[19:27] PHASE installer - Python-Version im Script hart pruefen - DONE (Score 3/3) - commit pending - lokal: compileall/unittest/PS syntax gruen - Fallback `python` muss jetzt 3.11+ sein.
[19:31] PHASE installer - BAT-Fallback Python 3.11 haerten - DONE (Score 3/3) - commit pending - lokal: compileall/unittest gruen - Start-VOCR.bat nutzt bevorzugt py -3.11 und stoppt bei altem Python.
[19:36] PHASE installer - Native Commands hart auswerten - DONE (Score 4/4) - commit pending - lokal: compileall/unittest/PS syntax gruen - git/pip/bootstrap/start koennen nicht mehr still fehlschlagen.
[19:40] PHASE installer - Start-Script Native Commands hart auswerten - DONE (Score 3/3) - commit pending - lokal: compileall/unittest/PS syntax gruen - start-vocr.ps1 stoppt bei pip/bootstrap/start-Fehlern.
[19:43] PHASE installer - Windows-Skript-Zeilenenden fixieren - DONE (Score 2/2) - commit pending - lokal: compileall/unittest/diff-check gruen - .ps1/.bat sind in .gitattributes auf CRLF gesetzt.
[19:48] PHASE installer - CLI Bootstrap Clone-Option - DONE (Score 4/4) - commit pending - lokal: compileall/unittest/help gruen - `vocr bootstrap --clone --install-dir ...` kann aus leerem Ordner clonen.
[19:54] PHASE housekeeping - Archive-Retention fuer clean - DONE (Score 3/3) - commit pending - lokal: compileall/unittest/diff-check gruen - `vocr clean --archives --archive-older-than-days N` entfernt alte Ledger-Archive.
[resume] PHASE learning - Retry- und Clarification-Signale - DONE (Score 3/3) - commit pending - lokal: compileall/unittest/diff-check gruen - LearningSnapshot zaehlt Rueckfragen, Antworten, Token und Worker-Retries ohne Rohdaten-Bloat.
[resume] PHASE mcp - Confirmed Promote Tool - DONE (Score 3/3) - commit pending - lokal: compileall/unittest/diff-check gruen - MCP kann accepted Tasks nur mit confirm=true ueber denselben Promote-Gate-Pfad promoten.
[resume] PHASE learning - Review-Dauer-Signale - DONE (Score 3/3) - commit pending - lokal: compileall/unittest/diff-check gruen - LearningEntry aggregiert Review- und Accepted-Review-Sekunden aus vorhandenen Timestamps.
[resume] PHASE review - Optionaler GitHub PR-Review - DONE (Score 3/3) - commit pending - lokal: compileall/unittest/help/diff-check gruen - `vocr review --post-pr-review` nutzt Inline-Kommentare mit sicherer Datei-/Zeilenposition und faellt sonst auf normalen PR-Review zurueck.
[resume] PHASE learning - Clarification-Qualitaetsproxy - DONE (Score 3/3) - commit pending - lokal: compileall/unittest/diff-check gruen - LearningSnapshot aggregiert Answer-Rate und offene Rueckfrage-Topics ohne Antwort-Rohtexte.
[resume] TESTSTAGE - Lokale Smoke-Abnahme - DONE (Score 4/4) - commit pending - `vocr test`, `doctor`, `worker doctor`, `graphify`, `learn`, `context --learning` und `secrets scan` gruen.
[resume] PHASE model - LM-Studio/Auth-Diagnose repariert - DONE (Score 4/4) - commit pending - lokal: compileall/unittest/help/diff-check gruen - Model-Status nutzt effektive Env, zeigt `[set]`, `model list/check` senden lokale Tokens nur bei lokaler Base-URL und geben klare 401-Diagnose aus.
[resume] PHASE model - LM-Studio-Endpoint-Fallback und Chat-Smoke - DONE (Score 4/4) - commit pending - lokal: compileall/unittest/help/diff-check gruen - `model list/check` erkennen falsche 200-Antworten, fallbacken auf `/api/v1/models` und `/api/v0/models`; `model check --model` prueft Chat-Completions direkt.
[2026-07-11] REVIEW - Claude-Review nachgereicht - DONE - lokaler Claude-Call uebersprungen; Review in `CLAUDE_REVIEW.md` dokumentiert; Doku-Hinweis zu dauerhaftem `clean --archives` ergaenzt.
[2026-07-11] PHASE 0 - Fundament geschlossen - DONE - Ledger-Lock Windows/POSIX, echtes Worker-Usage-Parsing mit Estimate-Fallback, `vocr eval-golden` Stub-Worker-Gate-Test, compileall/unittest/eval-golden gruen.
[2026-07-11] PHASE 0.5 - Effizienz-Ernte geschlossen - DONE - Confidence-Gate, kollabierter Live-Fan-out, taskgescopte Budget-Context-Packs, Docs-Downweight, persistierte BM25-Tokens, Ledger-Cache, Retry-Delta, konsolidierte Worker-Guidance und scoped compileall; unittest/eval-golden/context/test gruen.
