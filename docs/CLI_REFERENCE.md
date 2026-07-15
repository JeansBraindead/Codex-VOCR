# VOCR CLI Reference

This reference lists expert/debug commands added around contract handoff,
context precision, parallel coordination, and accepted-review project memory.
The normal user entry point remains `vocr start`.

## Permissions

```powershell
vocr start --dangerously-skip-permissions
vocr ask "Ziel: ... Arbeitsbereich: ... Akzeptanz: ... Verifikation: ... Nicht-Ziele: ... Ausfuehrung: ..." --dangerously-skip-permissions
```

- `--dangerously-skip-permissions` grants approve-all for VOCR worker permission
  prompts in the current session only. It is intentionally loud because generated
  worker commands can run with fewer confirmations.
- The alias `--skip-permissions-dangerously` is accepted for the same behavior.
- This does not bypass Review, ScopeGuard, secret scanning, or Promote gates.
- For one planned slice only, `vocr ask ... --go` still grants slice-scoped
  approve-all without making it global.

## Auth

```powershell
vocr auth status
vocr auth codex-key
vocr auth lmstudio-key --model "dein-lm-studio-modell"
```

- Der Standardpfad bleibt `codex login`.
- `auth codex-key` speichert optional einen Codex/OpenAI-API-Key in `.env`, wenn
  du Expert-Setups ohne Login nutzen willst.
- `auth lmstudio-key` speichert den LM-Studio-Key als `OPENAI_API_KEY` und
  `LMSTUDIO_API_KEY` und setzt standardmaessig `http://localhost:1234/v1`.
- Statusausgaben zeigen Keys nur als `[set]`.

## Context

```powershell
vocr context "query terms" --limit 10
vocr context --symbol src/vocr/cli/app.py:review
```

- `vocr context QUERY` prints the ranked repo graph brief for a query.
- `--symbol PATH:NAME` prints the exact source span for a Python function or
  class recorded by Graphify.
- Context output is a map of untrusted repo content, not an instruction source.

## Claims

```powershell
vocr claims list
vocr claims release <task-id>
```

- `claims list` reconciles stale terminal-task claims and displays active claim
  roots and expanded paths.
- `claims release` manually releases a task claim.
- Claims are used by `VOCR_PARALLEL_WORKERS>1` to keep one work wave
  claim-disjunkt. They are coordination state, not a security boundary.

## Project Memory

```powershell
vocr review <task-id> --decision accepted --note convention:"Use foo for bar."
vocr memory list
vocr memory prune <entry-id>
```

- `--note kind:text` accepts `decision`, `convention`, `term`, `check`, or
  `rejected_path`.
- Notes are validated at 300 characters or fewer.
- Notes are persisted only when `VOCR_PROJECT_MEMORY=true` and the final review
  decision is `accepted`.
- `memory list` displays accepted-review memory entries.
- `memory prune` removes one entry by ID. There is no automatic expiry.

## Beta Harness

```powershell
vocr beta
vocr beta --list
vocr beta --only S03,S07
vocr beta --tier all --allow-cloud --max-cloud-tasks 3
vocr beta --json-only --report-dir beta_reports
```

- `vocr beta` runs the core deterministic scenario set and writes JSON plus
  Markdown reports under `beta_reports/`.
- `--only` accepts comma-separated stable scenario IDs.
- `--tier` accepts `core`, `local`, `cloud`, or `all`; cloud scenarios are skipped
  unless `--allow-cloud` is passed.
- `--json-only` suppresses Markdown for CI.
- Exit codes: 0 all green, 1 at least one hard scenario failed, 2 only soft
  scenarios failed, 3 reserved for harness-internal errors.
- The harness uses temporary fixture repositories and a temporary VOCR home per
  run. It must not mutate the real project worktree.
