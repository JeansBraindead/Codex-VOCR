# Beta Session - 2026-07-16 - jeenz

Environment: Windows, PowerShell, fresh test clone under Desktop test folder
VOCR commit: 6e05d4c
Duration: 01:16-ongoing

## Tests run

| Test | Result | Notes |
|---|---|---|
| T1 fresh install | pass | Fresh separate folder install completed: `Bootstrap complete. Start with: vocr start`; installer reported `[VOCR] Installation fertig`. Working repo was not used for this test. |
| T2 normal-mode startup | pass | `.\start-vocr.ps1` opened Normalmode; activity log showed `[01:39:50] Normalmode gestartet.` |
| T12.1 no forced login on start | pass | No startup login prompt reported after user-initiated-login patch. |
| T12.2 ChatGPT/Codex login via Optionen | pass | User manually started login from Optionen; UI reported `[01:40:25] ChatGPT/Codex: eingeloggt via ChatGPT (Jeenz Chris / jeenzchris@gmail.com)`. |
| T12.3 LM Studio key save feedback | fail-fixed-pending-retest | User entered LM Studio API key but saw no visual confirmation. Fixed in `bcb3b50 feat(ui): show model auth status`; needs retest in fresh test clone after pull/reinstall. |
| T12.4 LM Studio reachability ampel | not-run | Added in `6e05d4c feat(ui): check lm studio reachability`; needs retest. |
| T12.5 Beta standard test from UI | pass | Normalmode Beta log showed 20 selected scenarios, all passed: S00-S16, S18, S19, S20. |

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
- Status: Fixed in `bcb3b50`; pending retest.

## Free-form observations

- Normalmode activity logging is now visible and useful during Beta.
- ChatGPT/Codex login should remain user-initiated from Optionen, not prompted at startup.
- LM Studio key must not be overwritten by future patches unless the user explicitly changes it.
- Next priority is retesting the LM Studio status and reachability ampel in the same fresh test clone.
