# VOCR Beta Testing — Schedule, Test Catalog, Templates

This document governs beta testing of VOCR after the pre-rollout hardening
pass (see `AUTOPILOT_LOG.md`, `CLAUDE_REVIEW.md`, and the commits tagged
`fix(beta)`/`fix(worker)` on this branch). It answers three questions for
every tester: **what** to test, **how** to test it, and **how often**.

Results are logged as structured session files under `docs/beta/sessions/`
and periodically rolled up into `docs/beta/SUMMARY.md` by a dedicated
analysis pass (see "Review cadence" at the end of this document).

## 0. Before every session (cheap, automatic, no exceptions)

Run this before any manual testing. If it fails, stop and log it as a
Blocker — nothing below is meaningful on a red baseline.

```powershell
python -m compileall src tests
$env:PYTHONPATH="src"; python -m unittest discover -s tests
vocr eval-golden
vocr doctor
```

Record the git commit (`git rev-parse --short HEAD`) in your session log —
every issue must be traceable to an exact commit.

## 1. Schedule

| Cadence | Test cases | Why |
|---|---|---|
| **Every session** (§0 + §2) | Pre-flight checks, normal-mode smoke | Cheapest, catches regressions immediately |
| **Daily**, first 5 days | §3 full CLI loop, §4 scope guard, §5 secret scanning | These are the safety gates the whole product promise rests on; needs the tightest feedback loop early |
| **2x/week**, ongoing | §3, §4, §5 (reduced), §7 revert | Keep confidence without re-testing everything daily once stable |
| **Weekly** | §6 parallel/load, §10 housekeeping | Slower to run, lower change frequency |
| **Once per environment** (new machine/OS image) | §1 fresh install | Only needs re-verification when the environment changes |
| **Once, then only when touched** | §8 PR posting, §9 model config, §11 hybrid path | Expensive or requires external accounts; re-run only if the relevant code changes |

If a session finds a Blocker or Major issue anywhere, re-run that specific
test case daily until it's confirmed fixed, regardless of the table above.

## 2. Test catalog

Each entry: goal, exact steps, pass criteria. Use the short code (e.g. `T1`)
in session logs and bug reports.

### T1 — Fresh install (Windows)
**Goal:** confirm a brand-new user can get from zero to a working `vocr start`.
**Steps:**
1. Use a genuinely empty folder (or fresh VM/user profile if available).
2. Double-click `Start-VOCR.bat` (do not run it from an already-activated venv).
3. Separately, in a second clean folder, run `.\install-vocr.ps1` from PowerShell.
**Pass criteria:** `.venv` created, VOCR installed editable, `.env` created from
`.env.example`, `.vocr/` initialized with `graph.json`/`ledger.jsonl`, normal-mode
window opens with no unhandled exception printed to the console.

### T2 — Normal-mode conversation flow
**Goal:** confirm the Visionary intake dialog works end to end for a non-technical user.
**Steps:**
1. `vocr start` (GUI) — describe a small wish in one short sentence.
2. Answer each follow-up question the Visionary asks (goal, scope, acceptance,
   verification, non-goals, execution bounds) in natural language, including at
   least one correction (e.g. "ohne Docs").
3. Confirm the pre-execution summary gate appears and lists all six sections
   before anything is created.
4. Say "nur planen" (plan only) at the gate; confirm no worktree is created.
5. Repeat with `vocr start --console` to confirm the terminal fallback works identically.
**Pass criteria:** no technical IDs/codes shown to the user; exactly one active
intake point at a time; nothing executes before explicit confirmation; console
fallback behaves the same as the GUI.

### T3 — Full expert CLI loop (vision → promote)
**Goal:** confirm the safety-gated pipeline works end to end.
**Steps:**
```powershell
vocr ask "Ziel: ... Arbeitsbereich: ... Akzeptanz: ... Verifikation: ... Nicht-Ziele: ... Ausfuehrung: mit go Worktree vorbereiten, Review vor Promote." --go
vocr work <task-id>
vocr review <task-id>
vocr check <task-id> --decision accepted --summary "beta test"
vocr promote <task-id>
```
Then attempt `vocr promote <other-task-id>` on a task that has **not** been
reviewed, to confirm it is rejected.
**Pass criteria:** promote before accepted review fails with a clear error;
promote after accepted review succeeds; after promote, confirm the worktree
directory under `<repo>.vocr-worktrees/<task-id>` is gone (new auto-prune
behavior) — if it's still present, log as a regression.

### T4 — Scope guard enforcement
**Goal:** confirm out-of-scope edits are blocked before commit.
**Steps:** dispatch a task with a narrow scope (e.g. one file), manually edit a
different tracked file inside the worktree, then run `vocr work <task-id>`.
**Pass criteria:** commit is blocked, task becomes `needs_changes`, the specific
out-of-scope file is named in the output.

### T5 — Secret scanning
**Goal:** confirm secrets never reach a commit or the console unredacted.
**Steps:** inside a dispatched task's worktree, add a line matching
`sk-` + 20 random chars, or `api_key = "..."`, to a tracked file. Run
`vocr work <task-id>`.
**Pass criteria:** commit blocked, task becomes `needs_changes`, the actual
secret value never appears in console output, `.vocr/ledger.jsonl`, or any
printed diff.

### T6 — Parallel orchestration / ledger load
**Goal:** stress-test the ledger lock fix under real concurrency.
**Steps:** create a slice with 6-10 small independent tasks, run:
```powershell
vocr orchestrate --fix --parallel-dispatch 8 --parallel-work 4
```
**Pass criteria:** no crash, no `OSError`/`TimeoutError` from the ledger lock,
`.vocr/ledger.jsonl` remains valid JSONL afterward (`vocr log` reads it cleanly).
If a `TimeoutError` does surface, log it — that's the new bounded-retry error
message, and it means contention exceeded the retry budget.

### T7 — Revert
**Goal:** confirm revert is safe and observable.
**Steps:** promote a task, then `vocr revert <task-id> --reason "beta test revert"`.
**Pass criteria:** the commit is reverted, task status returns to `needs_changes`,
`vocr log` shows the revert event.

### T8 — PR posting (once, disposable repo only)
**Goal:** validate `--post-pr-comments`/`--post-pr-review`/`vocr ship --pr`
against a real GitHub PR — this has never been tested against a live PR.
**Steps:** use a throwaway test repo, open a small PR, run
`vocr review <task-id> --post-pr-comments` and `--post-pr-review` against it.
**Pass criteria:** comments/review appear correctly on the PR; inline comments
land on the right file/line when position is safe, otherwise fall back to a
normal PR comment; no secret or internal path leaks into the PR text.

### T9 — Model configuration
**Goal:** confirm local/cloud model switching and secret masking.
**Steps:** `vocr model status`, `vocr model lmstudio --model ...`,
`vocr model check --model ...`, `vocr model openai --model gpt-4.1-mini`,
`vocr model off`.
**Pass criteria:** API keys always show as `[set]`, never plaintext; a 401 from
a local server produces the documented clear diagnosis, not a raw stack trace.

### T10 — Housekeeping
**Goal:** confirm cleanup commands are safe.
**Steps:** `vocr clean`, `vocr clean --archives --archive-older-than-days 90`,
`vocr abort <task-id> --reason "..."`, `vocr log --limit 30`, `vocr diff <task-id>`.
**Pass criteria:** orphaned worktrees pruned; `--archives` clearly warns it is
a permanent delete before/while running; abort stops a task cleanly and logs it.

### T11 — Hybrid path (only if `VOCR_HYBRID_ENABLED=true` is in scope for this beta)
**Goal:** confirm the default-off isolation and cloud-only routing.
**Steps:** with the flag unset, confirm `vocr vision`/`vocr ask`/`vocr organize`
behave identically to before. With the flag set and `OPENAI_API_KEY` present,
run `vocr hybrid-vision "..."` and `vocr hybrid-plan <slice-id>`.
**Pass criteria:** without the flag, zero behavior change anywhere else; with
the flag, both commands route to cloud only (never local), and fall back to
the deterministic path cleanly if the cloud call fails.

## 3. Templates

### 3a. Session log
Create one file per session at `docs/beta/sessions/YYYY-MM-DD-<tester>.md`
using this template:

```markdown
# Beta Session — YYYY-MM-DD — <tester>

Environment: <OS build, Python version, git version>
VOCR commit: <git rev-parse --short HEAD>
Duration: <start>–<end>

## Tests run
| Test | Result | Notes |
|---|---|---|
| T1 | pass/fail/partial/skipped | |

## Issues found
(one block per issue, using the Issue template below; or "none")

## Free-form observations
- ...
```

### 3b. Issue report
One block per issue, inside the session log or filed separately for Blockers:

```markdown
### Issue: <short title>

- Severity: Blocker / Major / Minor / Cosmetic
- Test case: <T-code>
- VOCR commit: <sha>
- Steps to reproduce:
  1. ...
- Expected:
- Actual:
- Log/ledger excerpt (redact any secret-looking value before pasting):
  ```
  ...
  ```
```

Severity guide: **Blocker** = unsafe (gate bypassed, secret leaked, data
loss) or the product is unusable. **Major** = a documented feature doesn't
work as described. **Minor** = works but confusing/rough. **Cosmetic** =
wording/formatting only.

## 4. Review cadence — analysis agent pass

After every **3 new session files**, or every **48 hours of active beta
testing**, whichever comes first, run an analysis pass over the accumulated
logs. This is a separate, fresh review — don't let the tester grade their
own session.

Trigger it with this prompt (to Claude, or any capable analysis agent, with
repo access):

```
Read every file in docs/beta/sessions/ that is not yet referenced in
docs/beta/SUMMARY.md. For each, extract test results and issues. Then:
1. Identify recurring failures (same test case or symptom across
   multiple sessions).
2. Rank open issues by severity, then by how many sessions hit them.
3. Cross-check docs/BETA_TESTING.md's test catalog (T1-T11) against what
   was actually run — call out any test case no session has covered yet.
4. Append (do not overwrite) a new dated entry to docs/beta/SUMMARY.md
   using the template at the top of that file, ending with a clear
   go / no-go / go-with-caveats recommendation for continued rollout.
```

Treat `docs/beta/SUMMARY.md` as the single source of truth for "is VOCR
beta-healthy right now" — read it before making any go/no-go call.
