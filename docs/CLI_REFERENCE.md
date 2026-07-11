# VOCR CLI Reference

This is the full expert/debug command surface. Most people never need this
page — the normal entry point is `vocr start` (see the [README](../README.md)).
Everything here is for inspection, repair, manual intervention, or CI/scripting.

> Commands here show technical detail (task IDs, worktree paths, ledger
> events, diffs, review artifacts, promote previews) that the normal-mode UI
> deliberately hides from regular users.

## Setup

| Command | What it does |
|---|---|
| `vocr bootstrap --tests --write-scripts` | Idempotent setup: confirms Python 3.11+/git, creates `.env` from `.env.example` (never overwrites an existing one), creates/reuses `.venv`, installs editable, initializes `.vocr/ledger.jsonl`, writes `.vocr/codex-mcp.json`, builds `.vocr/graph.json`. |
| `vocr install` | Editable install shortcut. |
| `vocr doctor` | Environment health check: repo, Python, git, `.env`, `.vocr`, graphify. |
| `vocr codex-config` | Regenerates `.vocr/codex-mcp.json` (Codex-as-MCP-server config). |

## Model configuration

VOCR is Codex-first; local/cloud models are optional and only assist the
Vision/Organizer paths. Codex worker execution, scope, review, and promote
remain the actual safety line regardless of model config.

| Command | What it does |
|---|---|
| `vocr model lmstudio --model <name>` | Point at a local LM Studio (or OpenAI-compatible) endpoint. |
| `vocr model check --model <name>` | Probes the endpoint; falls back across `/v1/models`, `/api/v1/models`, `/api/v0/models`; detects fake-200 responses; tests chat completion directly. |
| `vocr model openai --model gpt-4.1-mini` | Configure a cloud OpenAI-compatible model. |
| `vocr model list` / `vocr model status` | Show configured/available models. Secrets always print as `[set]`, never in plaintext. |
| `vocr model off` | Disable model-assisted paths; falls back to the deterministic pipeline. |

If a local server returns 401, VOCR treats that as "auth is on, or your token
is wrong" — it does not silently treat that as success, and falls back to
the deterministic path.

## Context / Graphify (debug)

| Command | What it does |
|---|---|
| `vocr graphify` | Rebuilds `.vocr/graph.json`: BM25-searchable repo index with import-graph edges, incremental via content hashing. |
| `vocr context "<query>" --limit 10` | Prints a compact, ranked context brief instead of reading the whole repo. |
| `vocr context "<query>" --learning --limit 10 --budget 1200` | Same, boosted by past review/scope success signals, capped to an approximate token budget. |

## Vision → Organize → Dispatch → Work (the core pipeline)

The normal entry point wraps all of this in a guided conversation. These are
the same steps available directly, for scripting or debugging:

| Command | What it does |
|---|---|
| `vocr ask "<structured request>"` | Plan-only Visionary pass: asks clarifying questions if goal/scope/acceptance/verification/non-goals/execution bounds are unclear; never guesses. |
| `vocr ask "..." --go` | Same, plus dispatch to isolated worktrees once approved. |
| `vocr reply "<answer>" --go` | Answer a pending clarification. |
| `vocr organize <slice-id>` | Break an approved VisionSlice into small, scoped, reviewable tasks. |
| `vocr dispatch <task-id>` | Create an isolated git worktree for a task; writes `.vocr/VOCR_TASK.md` (task + context pack) and `.vocr/scope.json` (machine-readable scope policy) into it. Blocks before creating the worktree if plan invariants are violated (missing scope, missing verification, unknown/cyclic dependencies). |
| `vocr work <task-id>` | Runs the real Codex worker in the dispatched worktree; commits automatically on success if the scope guard and secret scanner both pass. |
| `vocr work <task-id> --fix --max-retries 2` | Allows bounded auto-fix retries. Retries resend only scope, failing checks, and the delta diff since the last attempt — not the full repo context pack again. |
| `vocr dispatch-ready --parallel 4` | Dispatches the next ready DAG wave in parallel; refreshes graphify once per wave. |
| `vocr work-ready --fix --parallel 2` | Works dispatched tasks in parallel. Review and promote stay manual regardless. |
| `vocr orchestrate --fix --parallel-dispatch 4 --parallel-work 2` | Supervised wave loop: dispatch → work → bounded fixes. Never reviews, promotes, or merges automatically. |
| `vocr afk --max-waves 10` | Same loop, bounded by wave count, for unattended runs. |
| `vocr worker doctor` / `vocr worker profile safe\|unattended` | Inspect/configure the Codex worker without editing files by hand. |

## Review, promote, ship

| Command | What it does |
|---|---|
| `vocr review <task-id>` | Collects local git signals, runs safe automatic checks (e.g. syntax/compile on changed Python files only), and writes `.vocr/artifacts/<task-id>/review.md`. |
| `vocr review <task-id> --codex-review` | Adds `codex exec review` as an additional review signal. |
| `vocr review <task-id> --export-comments review.md` | Writes review comments as Markdown. |
| `vocr review <task-id> --post-pr-comments` / `--post-pr-review` | Optionally posts comments or an inline review to a GitHub PR via `gh`. |
| `vocr check <task-id> --decision accepted --summary "..."` | Records a manual review decision. |
| `vocr promote <task-id>` | Runs a merge preflight, then merges — only with an accepted review. Requires git ≥ 2.38 for the merge preflight check. |
| `vocr ship --preview` / `vocr ship --pr` | Shows a merge preview, or opens a draft PR via `gh`. |
| `vocr revert <task-id> --reason "..."` | Reverts the ledger-recorded task commit and resets the task to `needs_changes`. |
| `vocr tweak "<small, low-risk change>"` | For small changes only — not a bypass of the pipeline above. |

Promotion never happens automatically. There is no code path that merges
without an explicit accepted review.

## Learning, usage, replay, evaluation

| Command | What it does |
|---|---|
| `vocr learn` | Compresses ledger/review/telemetry signals into `.vocr/learning.json` (no raw prompts or large diffs stored). |
| `vocr compact --keep-last 200` | Refreshes learning and archives old ledger events to `.vocr/archive/`. |
| `vocr usage` | Token/provider telemetry per task/slice — shows `actual` when the worker reports real usage, otherwise an `estimated` fallback. |
| `vocr replay <slice-id>` | Reconstructs a slice's timeline from the ledger: ordered events, files touched, last decision per task, token cost by actual/estimated. Read-only. |
| `vocr eval-golden` | LLM-free stub-worker gate test: dispatch, real usage parsing, promote-before-review-blocked, promote-after-accepted-allowed. |

## Housekeeping

| Command | What it does |
|---|---|
| `vocr log --limit 30` | Timeline of ledger events. |
| `vocr diff <task-id>` / `vocr diff <task-id> --full` | Task diff. |
| `vocr clean` | Prunes orphaned worktrees. |
| `vocr clean --artifacts --older-than-days 30` | Removes old review artifacts. |
| `vocr clean --archives --archive-older-than-days 90` | **Permanently deletes** old ledger archive segments via filesystem unlink — back up first if you need the history. |
| `vocr abort <task-id> --reason "..."` | Cleanly stops a task. |
| `vocr secrets scan` | Manually scans the current diff for secrets; uses `gitleaks` if installed. |
| `vocr test` | Local syntax + unit test smoke. |

## MCP server

| Command | What it does |
|---|---|
| `vocr serve-mcp` | Minimal MCP server exposing status, graphify context, planning, review, and promote-preview. `vocr_promote` requires `confirm=true` and uses the same gate as the CLI. **MCP never merges without that confirmation.** |

## Hybrid routing (experimental, Phase 4, default-off)

Gated behind `VOCR_HYBRID_ENABLED=true`. Never called by `vocr vision`/
`vocr ask`/`vocr organize` — this wraps the deterministic pipeline instead of
forking it, and falls back to it on any failure.

| Command | What it does |
|---|---|
| `vocr hybrid-vision "<request>"` | Cloud-only VisionSlice creation (one attempt). |
| `vocr hybrid-plan <slice-id>` | Cloud-only task planning over repo context. |

Both are cloud-only, always — a local model never authors VisionSlice/TaskPlan
content in VOCR, whether because the input is untrusted repo context
(`hybrid-plan`) or because the output is authoritative planning regardless of
how trustworthy the input text looks (`hybrid-vision`). See
[`docs/THREAT_MODEL.md`](THREAT_MODEL.md) for the full reasoning.

## Deeper documentation

The following guides are detailed and currently written in German:

- [`docs/INSTALLATION.md`](INSTALLATION.md) — step-by-step Windows install guide.
- [`docs/TESTING.md`](TESTING.md) — manual test walkthroughs for every feature.
- [`docs/THREAT_MODEL.md`](THREAT_MODEL.md) — trust boundaries, prompt-injection handling, secret scanning.
- [`docs/NORMAL_MODE_SURFACE.md`](NORMAL_MODE_SURFACE.md) — why the normal-mode UI is a local Tkinter GUI, not a web app.
- [`docs/BETA_TESTING.md`](BETA_TESTING.md) — the beta test schedule, templates, and logging process.
