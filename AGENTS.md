# VOCR Project Guidance

This repo contains the VOCR MVP: Vision / Organize / Code / Review.

Reference architecture: VOCR is inspired by `yesitsfebreeze/voit` at
https://github.com/yesitsfebreeze/voit. Do not copy VOIT code or assets into
this repo without explicit license review and attribution in the touched files.

- Keep changes small and reviewable.
- The user-facing contact point is the Visionary flow: `vocr vision`.
- Treat `graphify`, `context`, `organize`, and `dispatch` as internal/debug commands unless the user explicitly asks for them.
- `vocr hybrid-vision`/`vocr hybrid-plan` are an experimental, default-off Phase 4 path (`VOCR_HYBRID_ENABLED=true`). They never run as part of `vocr vision`/`vocr ask`/`vocr organize`, and both are cloud-only: a local model never authors VisionSlice/TaskPlan content, whether because the input is untrusted repo context (`hybrid-plan`) or because the output is authoritative planning regardless of how trusted the input text is (`hybrid-vision`).
- The Visionary must ask clarification questions and stop before planning when goal, scope, acceptance criteria, verification, non-goals, or execution bounds are unclear.
- Do not turn assumptions into tasks. Missing information must remain a question.
- Do not log secrets or write fake credentials.
- Codex worker execution must stay behind the adapter boundary until MCP is implemented.
- Worktree operations belong in `src/vocr/git/worktrees.py`.
- Durable workflow state belongs in `.vocr/ledger.jsonl` through `MemoryLedger`.
- Promotion must require an accepted review.
- For token efficiency, read `.vocr/graph.json` or run `vocr context` before broad file reads.
- Prefer targeted file reads from the graph over scanning the whole repository.
- Worker handoff belongs in `.vocr/VOCR_TASK.json` inside the isolated worktree; `.vocr/VOCR_TASK.md` is the human-readable mirror.
- Untrusted repo context belongs in `.vocr/CONTEXT_PACK.txt`, physically separate from the task contract.
- Worker scope policy belongs in `.vocr/scope.json` inside the isolated worktree.
- `VOCR_PROMPT_MODE=contract` must keep the worker prompt prefix task-independent; volatile task data belongs in the JSON contract and context file.
- `VOCR_LOCAL_ASSIST` may only expand trusted task title/goal into search terms. It must not author plans, contracts, reviews, or project memory.
- `VOCR_PARALLEL_WORKERS` may run only claim-disjunkt tasks in parallel. Claims coordinate workers, but ScopeGuard and accepted review are still the safety gates.
- `VOCR_PROJECT_MEMORY` persists only compact notes from accepted reviews; retrieved memory remains untrusted context.
- `vocr beta` is the deterministic beta harness. It must run scenarios in temporary fixture repositories with isolated VOCR homes; scenario IDs (`S00` etc.) are stable report/trend references.
- `approve_all` removes VOCR-internal permission prompts only; keep promote review-gated.
- Prefer simple Python 3.11 code and Pydantic models over framework-heavy abstractions.
