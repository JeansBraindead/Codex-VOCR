# VOCR Project Guidance

This repo contains the VOCR MVP: Vision / Organize / Code / Review.

- Keep changes small and reviewable.
- The user-facing contact point is the Visionary flow: `vocr vision`.
- Treat `graphify`, `context`, `organize`, and `dispatch` as internal/debug commands unless the user explicitly asks for them.
- The Visionary must ask clarification questions and stop before planning when goal, scope, acceptance criteria, verification, non-goals, or execution bounds are unclear.
- Do not turn assumptions into tasks. Missing information must remain a question.
- Do not log secrets or write fake credentials.
- Codex worker execution must stay behind the adapter boundary until MCP is implemented.
- Worktree operations belong in `src/vocr/git/worktrees.py`.
- Durable workflow state belongs in `.vocr/ledger.jsonl` through `MemoryLedger`.
- Promotion must require an accepted review.
- For token efficiency, read `.vocr/graph.json` or run `vocr context` before broad file reads.
- Prefer targeted file reads from the graph over scanning the whole repository.
- Worker handoff belongs in `.vocr/VOCR_TASK.md` inside the isolated worktree.
- Worker scope policy belongs in `.vocr/scope.json` inside the isolated worktree.
- `approve_all` removes VOCR-internal permission prompts only; keep promote review-gated.
- Prefer simple Python 3.11 code and Pydantic models over framework-heavy abstractions.
