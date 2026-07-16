# VOCR Beta Testing

This guide describes the current beta path for VOCR. The normal test surface is
the `Beta-Test` tab in Normalmode.

## Current Go/No-Go Source

The latest green handoff is:

`docs/beta/sessions/2026-07-16-jeenz-normalmode.md`

Use that file as the current local go/no-go source until a newer session file
replaces it.

## Before Testing

Use a test clone, not the active development checkout, when validating the
installed user flow.

Recommended Windows start:

```powershell
powershell -ExecutionPolicy Bypass -File .\install-vocr.ps1 -Tests -NoStart
.\start-vocr.ps1
```

In Normalmode:

1. Open `Optionen`.
2. Start ChatGPT/Codex login if needed.
3. Set the LM Studio API key if local-live checks are in scope.
4. Press `LM Studio Erreichbarkeit pruefen`.

Expected before the final local run:

- ChatGPT/Codex status is logged in.
- LM Studio Ampel is green.
- `/models` reports the loaded/visible models.

## Primary Beta Buttons

### Update Aus Git Holen

Runs:

- `git pull --ff-only`
- editable install refresh
- bootstrap/start-script refresh

If UI code changed, restart VOCR after this button finishes.

### Empfohlenen Standardtest Starten

The cheap deterministic regression:

- tier `core`
- no cloud
- all core scenarios
- reports under `beta_reports/`

### Nur Beta-Testkette Starten

Runs the staged deterministic core chain:

| Step | Scenarios |
|---|---|
| Smoke | S00, S01, S04 |
| Safety | S02, S03, S07, S15, S16 |
| Workflow/Parallelitaet/Memory | S05, S06, S08, S09, S10, S11, S14, S18, S19, S20 |
| Local-Assist-Mocks | S12, S13 |

### Finale Lokale Testsequenz Starten

Use this before handing the repo to another reviewer or before starting cloud
tests.

It runs:

- update/install refresh
- syntax check
- full unit tests
- ChatGPT/Codex login status
- LM Studio reachability
- recommended core beta
- staged core beta chain
- local-live LM Studio checks S21/S22

S21/S22 do not load, start, or download any model. They only use the already
running LM Studio OpenAI-compatible API and the repo `.env`.

## Scenario Catalog

| ID | Tier | Purpose |
|---|---|---|
| S00 | core | pure cloud-reference state |
| S01 | core | happy-path gates |
| S02 | core | injection containment |
| S03 | core | scope breach |
| S04 | core | secrets gate |
| S05 | core | retry economy |
| S06 | core | review contract |
| S07 | core | ratchet matrix |
| S08 | core | baseline objective |
| S09 | core | budget gate |
| S10 | core | context quality |
| S11 | core | prompt constancy A/B |
| S12 | core | embeddings flag matrix |
| S13 | core | local-assist mock quadrant |
| S14 | core | incremental review |
| S15 | core | ledger integrity |
| S16 | core | robustness inputs |
| S17 | cloud | opt-in cloud smoke |
| S18 | core | parallel claims |
| S19 | core | project memory |
| S20 | core | visionary worker plan |
| S21 | local | LM Studio `/models` live check |
| S22 | local | LM Studio `/chat/completions` live smoke |

## CLI Equivalents

```powershell
vocr beta
vocr beta --only S03,S07
vocr beta --only S21,S22 --tier local
vocr beta --tier all --allow-cloud
```

For code-level gates:

```powershell
python -m compileall src tests
$env:PYTHONPATH="src"; python -m unittest discover -s tests
```

## Logging Results

Write final handoffs under:

`docs/beta/sessions/`

For the current phase, prefer one cleaned handoff file over a long raw scratch
log. Include:

- commit
- environment
- Normalmode status
- LM Studio status
- Codex login status
- scenario coverage
- report file names
- remaining cloud/non-cloud distinction

## Cloud Tests

Cloud remains opt-in.

Only enable the Cloud checkbox, or run `--allow-cloud`, when the user has
explicitly decided to spend cloud quota. The current local green handoff did not
run cloud.
