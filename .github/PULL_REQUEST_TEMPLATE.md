## What this changes and why

## Scope
Files/areas touched. Note anything adjacent you deliberately left alone.

## Verification
- [ ] `python -m compileall src tests`
- [ ] `PYTHONPATH=src python -m unittest discover -s tests`
- [ ] `vocr eval-golden`
- [ ] Manual steps (installer, normal-mode UI, or gate pipeline changes — see `docs/BETA_TESTING.md`):

## Does this touch a safety gate?
(scope guard / secret scanner / review / promote / worktree isolation / none)
If yes, explain how the gate stays enforced, not weakened, by this change.

## Non-goals
What this PR intentionally does not do.
