# Beta Session - 2026-07-16 - jeenz

Environment: Windows, PowerShell, fresh test clone under Desktop test folder
VOCR commit: 6e05d4c plus follow-up UI fixes
Duration: 01:16-ongoing

## Tests run

| Test | Result | Notes |
|---|---|---|
| T1 fresh install | pass | Fresh separate folder install completed: `Bootstrap complete. Start with: vocr start`; installer reported `[VOCR] Installation fertig`. Working repo was not used for this test. |
| T2 normal-mode startup | pass | `.\start-vocr.ps1` opened Normalmode; activity log showed `[01:39:50] Normalmode gestartet.` |
| T12.1 no forced login on start | pass | No startup login prompt reported after user-initiated-login patch. |
| T12.2 ChatGPT/Codex login via Optionen | pass | User manually started login from Optionen; UI reported `[01:40:25] ChatGPT/Codex: eingeloggt via ChatGPT (Jeenz Chris / jeenzchris@gmail.com)`. |
| T12.3 LM Studio key save feedback | pass | Retest showed visible status line after key save: `LM Studio: Key gesetzt, http://localhost:1234/v1`. A duplicate status line was observed and fixed in follow-up. |
| T12.4 LM Studio reachability ampel | pass | User first clicked reachability before entering the key; the ampel correctly showed `gelb - kein API-Key gesetzt`. After key save, the check returned `gruen - erreichbar, 16 Modell(e)`. |
| T12.5 Beta standard test from UI | pass | Normalmode Beta log showed 20 selected scenarios, all passed: S00-S16, S18, S19, S20. |
| T13 Beta next-test chain design | pass-pending-fresh-ui-click | Beta tab now offers a multi-step next-test chain: Smoke, Safety, Workflow/Parallelitaet/Memory, Local-Assist-Mocks, plus optional Cloud-Smoke only when cloud is explicitly enabled. Local chain smoke passed: 3 + 5 + 10 + 2 scenarios, all exit 0. |
| T14 All-in-One final sequence | pass-pending-fresh-ui-click | Beta tab now includes update, syntax, full unit tests, ChatGPT/Codex login status, LM Studio reachability, recommended core beta and the final staged core chain in one run. S17 stays opt-in via the cloud checkbox. Local implementation validation passed: 127 unit tests, recommended core beta 20 scenarios exit 0, staged core chain 3 + 5 + 10 + 2 scenarios exit 0. |

## Issues found

### Issue: LM Studio key save had no clear visual confirmation

- Severity: Minor
- Test case: T12.3
- VOCR commit: observed before `bcb3b50`
- Steps to reproduce:
  1. Open Normalmode.
  2. Use Optionen to enter LM Studio API key.
  3. Observe UI after save.
- Expected: Visible status/confirmation in the normal status surface.
- Actual: No clear visual confirmation was visible.
- Status: Fixed in `bcb3b50`; verified in fresh test clone at 01:51.

### Issue: LM Studio status confirmation was logged twice

- Severity: Cosmetic
- Test case: T12.3/T12.4
- VOCR commit: observed after `6e05d4c`
- Steps to reproduce:
  1. Open Normalmode.
  2. Use Optionen to enter LM Studio API key.
  3. Observe the activity log after save.
- Expected: One visible status confirmation for the saved LM Studio key.
- Actual: The status line `LM Studio: Key gesetzt, http://localhost:1234/v1` appeared twice.
- Status: Fixed in follow-up patch after this session entry.

### Follow-up: Beta tab needed a guided next-test chain

- Severity: UX/Testability
- Test case: T13
- Request: The Beta tab should not leave the user guessing which test to run next.
- Implementation: Added `Naechste Testkette starten` with staged deterministic core checks and an opt-in cloud ending.
- Status: Implemented and locally validated; needs fresh-clone UI click retest after pull/reinstall.

### Follow-up: Claude handoff needs one all-in-one final button

- Severity: UX/Testability
- Test case: T14
- Request: The user needs one final run that includes all previous automated checks before starting cloud tests.
- Implementation: Added `Finale lokale Testsequenz starten` and `Update aus Git holen` in the Beta tab.
- Scope: Update/install refresh, compileall, full unittest, Codex login status, LM Studio reachability, recommended core beta, staged final core chain; optional S17 only with cloud checkbox.
- Status: Implemented and locally validated; needs fresh-clone UI click retest after pull/reinstall.

## Free-form observations

- Normalmode activity logging is now visible and useful during Beta.
- ChatGPT/Codex login should remain user-initiated from Optionen, not prompted at startup.
- LM Studio key must not be overwritten by future patches unless the user explicitly changes it.
- LM Studio reachability now gives a useful before/after signal: yellow before key, green with model count after key.
- The next manual retest should use `Update aus Git holen`, restart VOCR if the UI changed, then run `Finale lokale Testsequenz starten` once without cloud and verify the final reports under `beta_reports/`.
