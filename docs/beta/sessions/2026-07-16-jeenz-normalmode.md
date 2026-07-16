# VOCR Beta Results - Claude Handoff - 2026-07-16

Status: **GREEN - local final passed**

This file is the cleaned final handoff for the successful Normalmode beta run.
It replaces the earlier running notes with the user-verified final results.

## Environment

- OS/surface: Windows, Normalmode UI
- Test clone: `C:\Users\jeenz\Desktop\Neuer Ordner (2)\Codex-VOCR-test`
- Branch: `main`
- Verified commit: `51774cd fix(beta): accept lm studio reasoning responses`
- Cloud tests: not run yet
- Local LM Studio: reachable at `http://localhost:1234/v1`
- Loaded/visible LM Studio models: 16
- Local-live model used by S22: `gpt-oss-20b`
- Codex auth: logged in via ChatGPT/Codex

## Final Run Summary

Run window: **02:26:24-02:27:35 Europe/Berlin**

| Area | Result | Evidence |
|---|---|---|
| Normalmode startup | PASS | `[02:26:24] Normalmode gestartet.` |
| LM Studio key/status | PASS | key saved, reachability green, 16 models visible |
| ChatGPT/Codex login | PASS | login manually started from Optionen, status confirmed logged in |
| Update from Git | PASS | `git pull --ff-only`, editable install, bootstrap/start scripts all passed |
| Syntax check | PASS | All-in-One Final logged `PASS: Syntax-Check` |
| Unit tests | PASS | All-in-One Final logged `PASS: Unit-Tests` |
| Recommended core beta | PASS | S00-S16, S18, S19, S20 all passed |
| Final staged beta chain | PASS | Smoke, Safety, Workflow, Local-Assist-Mocks, Local-Live all passed |
| Local-live LM Studio | PASS | S21 `/models` passed, S22 `/chat/completions` passed |

## Scenario Coverage

### Recommended Core Beta

All core scenarios passed:

- S00 `pure-cloud-reference`
- S01 `happy-path-gates`
- S02 `injection-containment`
- S03 `scope-breach`
- S04 `secrets-gate`
- S05 `retry-economy`
- S06 `review-contract`
- S07 `ratchet-matrix`
- S08 `baseline-objective`
- S09 `budget-gate`
- S10 `context-quality`
- S11 `prompt-constancy-a-b`
- S12 `embeddings-matrix`
- S13 `local-assist-quadrant`
- S14 `incremental-review`
- S15 `ledger-integrity`
- S16 `robustness-inputs`
- S18 `parallel-claims`
- S19 `project-memory`
- S20 `visionary-worker-plan`

### Final Chain

| Chain step | Scenarios | Result |
|---|---|---|
| 1. Smoke: Installation und Grundpfad | S00, S01, S04 | PASS |
| 2. Safety: Prompt-, Scope-, Secrets- und Ledger-Schutz | S02, S03, S07, S15, S16 | PASS |
| 3. Workflow: Review, Kontext, Budget, Parallelitaet und Memory | S05, S06, S08, S09, S10, S11, S14, S18, S19, S20 | PASS |
| 4. Local-Assist-Mocks: Embeddings und lokale Assistenz-Matrix | S12, S13 | PASS |
| 5. Local-Live: LM Studio API und Chat-Smoke | S21, S22 | PASS |

## Local-Live Details

S21 and S22 are intentionally local-only and do not load, download, or start any model.
They use the already running LM Studio OpenAI-compatible API and the repo `.env`.

- S21 `lmstudio-models-live`: PASS, 16 models visible.
- S22 `lmstudio-chat-live`: PASS against `gpt-oss-20b`.
- S22 accepts GPT-OSS-style reasoning-only responses when `message.content` is empty.

## Final Report Files

Generated under:

`C:\Users\jeenz\Desktop\Neuer Ordner (2)\Codex-VOCR-test\beta_reports`

- `beta_report_final-all-recommended-core_20260716T002726Z.json`
- `beta_report_final-all-chain-01-smoke_20260716T002727Z.json`
- `beta_report_final-all-chain-02-safety_20260716T002728Z.json`
- `beta_report_final-all-chain-03-workflow_20260716T002729Z.json`
- `beta_report_final-all-chain-04-local-mocks_20260716T002729Z.json`
- `beta_report_final-all-chain-05-local-live_20260716T002735Z.json`

Markdown companions exist with the same timestamps.

## Current Interpretation

The local VOCR beta surface is ready for the next phase:

- Normalmode works and gives visible activity/status feedback.
- Update-from-UI works for the test clone.
- Core safety/workflow/project-memory/parallel-claims gates pass.
- Visionary worker-plan recommendation scenario passes.
- Local LM Studio connectivity and a minimal chat-completion smoke pass.
- The local path is green before cloud testing.

## Next Step For Claude

Proceed with **cloud tests only after explicitly enabling cloud**.

Recommended next command/path:

- In Normalmode, keep LM Studio as-is.
- Enable the Cloud checkbox only if the cloud smoke should run.
- Run the final sequence with cloud enabled, or run the targeted cloud scenario S17.

Cloud remains opt-in by design; no cloud path was executed in this green local handoff.
