# VOCR Remaining Test Cycles

This document defines the three remaining beta phases after the green local
Core/Local-Live suite. It is the planning bridge between the current local
handoff and the first controlled cloud runs.

Current verified baseline from July 16, 2026:

- 133 unit tests pass.
- Beta Core passes 20/20 with exit code 0.
- S11 measures 41.3% prompt-token reduction in contract mode: 654 to 384.
- S21 confirms LM Studio model visibility when LM Studio is reachable.
- S22 confirms a small LM Studio chat completion against an already loaded
  model.
- S21/S22 skip cleanly when key or server is unavailable; skip is not fail.
- S17 cloud remains skipped unless `--allow-cloud` is explicit.

Covered today: deterministic logic on throwaway fixtures, including guards,
claim coordination, Project Memory, worker-plan recommendation, and LM Studio
live smoke checks.

Still missing: longer local model qualification, real Codex cloud worker E2E,
and durability testing under repeated or interrupted runs.

## Rules For All Phases

1. Run the phase as one closed cycle: entry check, execution, report.
2. Start with `vocr beta --tier core` green before any local-live or cloud work.
3. Write dated reports with a meaningful `--tag` so phase trends stay separate.
4. On hard failure, save the result and stop. Do not keep retrying until green.
5. Use a test clone, not the active development checkout, for user-flow
   validation.

## Phase L: Local Live Validation

Purpose: prove that local LM Studio capabilities work with a real model and
collect model metrics on the user's hardware before spending cloud quota.

Cost: no cloud tokens, only local GPU time.

Expected duration: about 30 to 60 minutes, depending on model switches.

### Entry

- `vocr beta --tier core` is green.
- LM Studio is running and serving the OpenAI-compatible API on port 1234.
- The repo `.env` contains the LM Studio API key and model selection.
- The intended chat model is already loaded or visible in LM Studio.
- Optional embedding model checks require an embedding-capable model; chat
  models are not assumed to provide embeddings.

### Current Built-In Checks

1. L1: negative control
   - Run with LM Studio unavailable or key missing.
   - Expected: S21/S22 are skipped, not failed.
   - Purpose: prove graceful degradation.

2. L2: model visibility
   - Run `vocr beta --only S21 --tier local --tag local-live-models`.
   - Expected: `/models` is reachable and the selected model is visible when
     configured.
   - Metrics: visible model count and selected model visibility.

3. L3: chat completion smoke
   - Run `vocr beta --only S22 --tier local --tag local-live-chat`.
   - Expected: `/chat/completions` returns an assistant message or reasoning
     content with a normal finish reason.
   - Metrics: completion chars, reasoning chars, finish reason, selected model.

### Next Local Additions

4. L4: structured-output fidelity
   - Add an S22-style local-live case that asks for schema-constrained JSON.
   - Repeat 5 times per model.
   - Measure `json_valid_rate`.
   - A model below about 0.9 valid JSON rate is not suitable for strict VOCR
     JSON contracts.

5. L5: model sweep
   - Repeat L2 to L4 for two or three candidate local models.
   - Use one tag per model.
   - Produce a comparison table for Local Assist suitability.

### Fail Or Stop Criteria

- Low structured-output fidelity marks a model as unsuitable, but is not a VOCR
  product defect by itself.
- Configured LM Studio with hard chat failure means diagnose LM Studio or the
  selected model before continuing.

### Phase L Report

Include:

- model id
- endpoint reachability
- latency if measured
- completion and reasoning chars
- JSON-valid rate once L4 exists
- recommendation: suitable or unsuitable for Local Assist

## Phase C: Cloud End-To-End

Purpose: let VOCR run a real Codex worker under controlled conditions. This is
the first phase that proves the full chain with real cloud execution:
dispatch, worker, guards, review, and promote.

Cost: Codex quota. Start near the beginning of a fresh usage window.

### Entry

- Phase L is complete enough to know the local setup is sane.
- `vocr beta --tier core` is green.
- Codex CLI is installed and logged in through the user-initiated flow.
- The run uses fixture repositories, not the real project as test object.

### Cycle

1. C1: cloud guard negative control
   - Run `vocr beta --tier cloud` without `--allow-cloud`.
   - Expected: S17 skipped, no Codex call.

2. C2: minimal real E2E
   - Run one trivial deterministic task with `--allow-cloud` and a small cloud
     task cap.
   - Verify worker execution, ScopeGuard, Secret Scan, Review, and review-gated
     promotion on a real diff.

3. C3: prompt-mode A/B
   - Run the same small task once in legacy mode and once in contract mode.
   - Compare real Codex token use against the S11 estimate.

4. C4: retry reality
   - Run one intentionally harder task with a strict cap.
   - Verify retry summaries, delta-diff context, and budget behavior.

5. C-Adv: advisor token calibration
   - Record the Advisor recommendation before the real wave starts:
     `recommended_workers`, estimated speedup, and estimated token/context
     overhead.
   - Compare the recommendation with the real Codex outcome.
   - Purpose: calibrate the token-overhead part with actual Codex numbers, not
     only local heuristics.

### Hard Stops

- ScopeGuard, Secret Scan, review, or promote gates failing on a real diff.
- Quota exhaustion before both sides of C3 are available. Save partial results
  and continue in the next window.

### Phase C Report

Include:

- real tokens by task and mode
- retries
- review outcome
- guard evidence
- deviation from S11 prompt-token estimate
- Advisor recommendation versus real token and wall-time outcome
- final decision: ready or not ready for first real project trial

## Phase S: Soak And Chaos

Purpose: prove durability over repeated and interrupted runs. This phase is
mostly local and mock-driven, with optional small cloud slices after C passes.

### Entry

- Phase C has at least one clean E2E run.
- `vocr beta --tier core` is green.

### Cycle

1. S-Soak: repeat Core
   - Run `vocr beta --tier core` repeatedly, for example 50 times.
   - Expected: identical green results.
   - Any drift is a flakiness finding.

2. S-Parallel: claim-safe concurrency
   - Run waves with many disjoint claims and a few conflicting claims.
   - Test worker settings such as 2, 4, and 8.
   - Expected: disjoint work overlaps, conflicting work serializes, ledger stays
     valid.

3. S-Crash: recovery
   - Interrupt a wave mid-run.
   - Restart and verify stale claims are released, no task dispatches twice, and
     the ledger remains parseable.

4. S-Lock: competing claims
   - Let two processes attempt the same scope claim.
   - Expected: exactly one wins.

5. S-Memory: memory over time
   - Run many accepted reviews.
   - Verify Project Memory stays bounded and remains untrusted context.

6. S-Cal: advisor speedup calibration
   - After the parallel runs, compare measured wall time per worker setting
     against the Advisor's predicted `speedup_pct`.
   - Record prediction error by worker count.
   - Expected direction: with enough samples, Advisor confidence can move from
     `heuristic` toward `measured`, and prediction error should shrink.

### Hard Stops

- Any Soak drift before Phase S parallel/crash tests start.
- Ledger corruption after crash or parallel pressure.
- Duplicate dispatch after restart.

### Phase S Report

Include:

- run count and failures
- worker count versus wall time
- ledger integrity result
- crash recovery evidence
- duplicate-dispatch check
- Project Memory growth behavior
- Advisor speedup prediction error and confidence source

## Advisor Calibration Loop

The Advisor starts as a heuristic. Phase S feeds it measured wall-time and
speedup data; Phase C feeds it real Codex token-overhead data. Calibration is
therefore not a one-time switch. It improves as real runs accumulate, and every
report should show whether a recommendation came from `heuristic` or
`measured` confidence.

## Recommended Order

```text
Green local baseline
  -> Phase L: local live model qualification
  -> Phase C: real Codex cloud E2E
  -> Phase S: soak, crash, and concurrency durability
```

L comes before C because local model qualification costs no cloud quota. C comes
before S because one real E2E should be clean before repeated or interrupted
runs. S is the confidence gate for unattended sessions and broader project use.

## Deliberately Out Of Scope

- No new Core scenarios just to increase count. Add Core coverage when real
  failures reveal a missing invariant.
- No automatic model download or loading in LM Studio.
- No hidden cloud execution. Cloud always requires `--allow-cloud` or an
  explicit UI choice.
- No claim that Local Assist is fully model-qualified until L4/L5 exist and pass.
