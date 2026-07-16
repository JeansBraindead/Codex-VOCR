# Contributing to VOCR

Thanks for considering a contribution. VOCR's core promise is that work is
scoped, reviewed, and promoted only after gates pass — that applies to
contributions from outside just as much as it applies to the agents VOCR
orchestrates. Read this before opening a PR; it's short.

## Before you start

- For anything beyond a small fix, open an issue first describing the goal,
  scope, and acceptance criteria — the same shape VOCR itself asks for from
  a user request. It saves everyone a rewritten PR.
- Read [`AGENTS.md`](AGENTS.md) — it's the exhaustive rule set the codebase
  is held to (not just a suggestion list for AI agents; the same rules apply
  to human contributors).
- Read [`docs/THREAT_MODEL.md`](docs/THREAT_MODEL.md) if your change touches
  scope enforcement, secret scanning, review, or promote — those are the
  parts of VOCR that exist specifically to be hard to accidentally weaken.

## Dev setup

```powershell
git clone https://github.com/JeansBraindead/Codex-VOCR.git
cd Codex-VOCR
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e .
python -m compileall src tests
$env:PYTHONPATH="src"; python -m unittest discover -s tests
```

All tests should pass on a clean checkout before you start. If they don't,
that's a bug worth its own issue before anything else.

## Conventions

- **Python 3.11+, Pydantic models over framework-heavy abstractions.** Match
  the existing style in `src/vocr/models.py` rather than introducing a new
  pattern.
- **Keep changes small and reviewable.** A bug fix doesn't need surrounding
  cleanup bundled in; a one-shot script doesn't need a new abstraction layer.
- **Worktree operations belong in `src/vocr/git/worktrees.py`.** Don't shell
  out to git elsewhere.
- **Durable workflow state belongs in `.vocr/ledger.jsonl`, through
  `MemoryLedger`.** Don't invent a second persistence mechanism.
- **Never log secrets or write fake credentials**, including in tests.
- **Promotion must require an accepted review.** If you're touching
  `promote_task`, `preflight_merge`, or the MCP `vocr_promote` tool, the
  bar for review is higher, not lower.
- **Prefer targeted reads over full-repo scans.** Run `vocr context "<query>"`
  or read `.vocr/graph.json` before reading broadly — this is the same
  token-efficiency discipline VOCR asks of the agents it dispatches.
- **New CLI commands or config should stay off by default if experimental**,
  matching the pattern used for `VOCR_HYBRID_ENABLED`.

## Tests

Every change needs to keep these green:

```powershell
python -m compileall src tests
$env:PYTHONPATH="src"; python -m unittest discover -s tests
vocr beta --tier core
```

Add tests alongside the change, not after. If you're fixing a bug, add the
regression test that would have caught it.

## Commit style

This repo uses [Conventional Commits](https://www.conventionalcommits.org/):
`feat(scope): ...`, `fix(scope): ...`, `docs(scope): ...`, `chore(scope): ...`.
Look at recent `git log` output for the exact tone — commit messages here
explain *why*, not just *what*, especially for anything touching a safety
gate.

## Pull requests

- Keep the diff focused on the stated goal; note explicit non-goals if
  something adjacent looked tempting to fix too.
- State what you ran to verify it (`compileall`/`unittest`/`vocr beta`, plus
  any manual steps for UI or installer changes — see
  [`docs/BETA_TESTING.md`](docs/BETA_TESTING.md) for the manual test catalog
  if you're touching install, normal mode, or the gate pipeline).
- Expect review before merge, same as VOCR expects of the code it dispatches.
  There is no fast path around that, for anyone.

## Reporting a bug or requesting a feature

Use the issue templates — they ask for the same goal/scope/acceptance shape
VOCR itself relies on, so please fill them in rather than deleting the
sections.

## Security

If you find something that lets scope, review, or promote be bypassed, or
that could leak a secret, please open an issue describing the concern before
attaching a working exploit or repro to a public thread, so it can be
assessed first.
