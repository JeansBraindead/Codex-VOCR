# VOCR — Beta Kickoff Review

Final review closing out the pre-beta sprint. Written to answer, in one
place: is VOCR ready, what's left, did the final sprint execute as planned,
and did the project stay true to its own stated goal (better output, less
cost/input than a non-token-tweaked workflow).

Branch: `vocr-autopilot-2026-07-10`, commit `a83cd94`, 7 commits ahead of
`origin/vocr-autopilot-2026-07-10` (not pushed). Working tree clean.
82/82 unit tests green, `compileall` clean, `eval-golden` green.

## 1. Verdict

**Code-ready, environment-unverified.** Every gate mechanism (scope guard,
review/promote gates, secret scanning, ledger locking) is real, implemented,
and now independently reviewed twice — once by direct code reading across
this session, once by an 8-angle automated review pass against the full
unpushed diff, which caught and fixed two regressions the first pass missed.
What's not yet true: nobody has run VOCR in the actual environment a beta
tester will use it in. That gap, not code quality, is what stands between
"ready" and "shipped." Section 3 lists exactly what closes it.

## 2. What this sprint did

Starting point: an overnight autopilot run had produced 17 commits across
Phases 0-4 (foundation gates, efficiency pass, dispatch hardening, DAG
orchestration, default-off hybrid routing) plus one uncommitted working-tree
diff (dead specialist-agent stub removal, cloud-only hybrid fix, MCP context
budget param) that had never been reviewed or committed.

This session:
- Read the orchestration core, CLI, install scripts, and docs directly
  (not just trusted the autopilot's own log) to build an independent
  readiness assessment.
- Committed the pending WIP diff (`fa456a2`).
- Implemented and verified 8 concrete hardening/efficiency fixes across
  three commits (`2251fb9`, `b231666`): git-version preflight guard, ledger
  lock retry-with-backoff, codex-review timeout guard, a stale/misleading
  CLI message, worktree auto-prune after promote, and the retry loop no
  longer re-sending the full repo context pack on every fix attempt.
- Ran an 8-angle automated code review (`/code-review high`) against the
  **entire unpushed branch** (44 files, ~3700 lines) — not just this
  session's own changes. It found real regressions in this session's own
  fixes (an uncaught-exception path this session's own git-version guard
  introduced into `vocr eval-golden`, and a review-timeout guard that
  silently hid a skipped Codex review instead of surfacing it). Both
  verified against the actual code and fixed (`a847de9`).
- Built `docs/BETA_TESTING.md` and `docs/beta/` — an 11-test-case schedule
  with templates, logging, and a documented cadence for a fresh analysis
  pass over accumulated beta results (`a83cd94`).

The self-correction in step 5 is the important data point: the process
caught its own mistakes before they reached a beta tester, rather than
after.

## 3. Remaining TODOs

### Must resolve before real testers touch it
1. **Real Windows install test.** `install-vocr.ps1`/`Start-VOCR.bat` have
   never been executed by anything — not CI (which runs on `ubuntu-latest`
   only), not this session. This is beta tester T1 (`docs/BETA_TESTING.md`)
   and it is the single largest unverified assumption in the project.
2. **Missing `VOCR_Phasen_Upgrade.md`.** Confirmed absent anywhere on this
   machine. The autopilot ran Phases 0→4 improvised from README/AGENTS.md
   instead of a real spec. You need to either supply it or explicitly bless
   the improvised phase mapping as the record of what "Phase 0-4" means for
   this project going forward.
3. **Confirm the beta host's git version.** The new preflight guard
   requires git ≥ 2.38 for a safe merge preflight; below that, promote now
   fails with a clear message instead of a crash, but it does fail. Check
   before testers hit it.
4. **Real concurrency smoke test.** `vocr orchestrate --parallel-dispatch
   8 --parallel-work 4` (or your advertised parallelism) against a real
   ledger, to confirm the new lock retry-backoff actually holds under load
   rather than just compiling cleanly. This is beta test T6.

### Should resolve soon, not launch-blocking
5. PR-comment/PR-review posting (`--post-pr-comments`/`--post-pr-review`)
   has never run against a real GitHub PR (T8).
6. LM Studio 401 auth issue flagged by the autopilot and never resolved —
   only matters if local-model support is in scope for this beta; VOCR is
   Codex-first, so confirm whether it's in scope at all.
7. UI is 100% hardcoded German with no locale switch — confirm this matches
   the beta audience.

### Backlog, deliberately deferred (see `a847de9` commit message and prior
review notes for full list)
- Hybrid-path (Phase 4) code duplication against `runtime.py` and
  `workflow.py`'s prompt-injection wrapper — real, but Phase 4 stays
  default-off for this beta, so it's not exposed to testers.
- `CodexMcpClient` naming (it's a subprocess wrapper, not real MCP) —
  documentation debt, not a functional bug.
- Dependency versions in `pyproject.toml` are floor-only (`>=`) — worth
  pinning for the beta freeze window, not urgent.

## 4. Phase-driven workflow — status against the plan

| Phase | Status |
|---|---|
| A — Decisions (commit WIP, bless phase order, confirm audience/scope) | WIP diff committed. Phase-spec and audience/local-model-scope decisions **still open** — items 2, 6, 7 above. |
| B — Correctness + efficiency fixes | Done (`2251fb9`, `b231666`), then corrected after review (`a847de9`). |
| C — Real-environment validation | **Not started.** This is items 1, 3, 4, 5 above — the actual highest-value remaining work. |
| D — Polish | Partially done incidentally (stale message, docstring, naming notes) via the review pass; not exhaustively worked. |
| E — Efficiency evidence | Not done as a standalone number-capture exercise; see §5 for what the review pass surfaced instead. |
| F — Beta packaging | Done: `docs/BETA_TESTING.md` + `docs/beta/` logging/review-cadence package (`a83cd94`). |
| G — Go/no-go | This document. Verdict: **go for controlled beta, conditional on Phase C.** |

## 5. Token efficiency, output quality, and philosophy alignment

Your standing goal: better output, less cost/input than a non-token-tweaked
workflow or competitors. Re-assessed after this session's changes, not just
re-asserted from the original review:

**Confirmed real, not aspirational** (verified by reading the code, not the
docs, both in the original review and again during the code-review pass):
graphify's BM25-ranked context packs with hard token budgets, the
learning-boosted ranking feedback loop, the zero-LLM-token deterministic
readiness/confidence gate, the collapsed single-call live-agent path (and
this session's commit `fa456a2` proved that collapse was actually followed
through in code, not just decided in docs, by deleting the 10 dead
specialist-agent stub files that would have been the old multi-call path).

**Improved this session, with a real number now available:** the retry loop
in `execute_worker_task` (`app.py`) previously re-sent the full ~900+ token
context pack on every retry attempt (up to 3x per task with default
settings) even though the worker already had it in
`.vocr/VOCR_TASK.md`/`.vocr/scope.json` in its own worktree. That's now
suppressed on attempts after the first, and — importantly — the review pass
confirmed this was correctly wired end-to-end (both the actual prompt sent
and the token telemetry estimate now reflect the smaller retry prompt,
instead of the estimate silently overcounting). This is the one lever in
the whole codebase that scales with `retries × parallel workers × task
count`, so it was worth prioritizing over the other cleanup findings.

**Still the honest gap:** there is still no benchmark artifact anywhere in
the repo comparing "graphify + budget + learning" against a naive
full-repo-dump baseline. The architecture is real and defensible; the
comparative number that would let you say "N% fewer tokens than a
non-tweaked workflow" to a skeptical tester or a competitor doesn't exist
yet. That's a ~30-minute add once real testers generate real retry-worthy
tasks (capture `vocr usage`/`vocr replay` before/after on one task), not a
redesign — it just hasn't happened because nothing has run against a real
worker yet (see Phase C).

**On output quality specifically:** this remains the weaker half of the
claim. `eval-golden` is a gate-mechanics test (dispatch, promote-before/
after-review) — it proves the safety net catches bad output, it doesn't
measure output quality itself. Nothing in the codebase scores whether a
Codex-produced diff is *better* than what a naive prompt would produce,
only whether it passed review. That's consistent with VOCR's actual design
philosophy (safety through gates, not through claimed model superiority),
but if "better output" is a claim you want to make externally, it needs its
own evidence, separate from "safer output," which is well-evidenced.

**Philosophy alignment verdict, unchanged from the original review and
reinforced by this session:** on track. The codebase does what the docs
claim, the self-correcting review pass is itself evidence of the process
working as designed (catch problems before promotion, never trust a single
pass), and the one efficiency gap found was fixed rather than left as a
known issue.

## 6. Kickoff decision

Go for a **controlled beta** — real testers, using `docs/BETA_TESTING.md`'s
schedule, starting with T1 (fresh install) since it's the one thing in this
entire review that has never actually run. Do not treat this document as
clearance for a public/unattended rollout until Phase C's four items are
closed and logged in `docs/beta/sessions/`.
