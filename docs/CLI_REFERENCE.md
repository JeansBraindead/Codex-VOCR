# VOCR CLI Reference

This reference lists expert/debug commands added around contract handoff,
context precision, parallel coordination, and accepted-review project memory.
The normal user entry point remains `vocr start`.

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
