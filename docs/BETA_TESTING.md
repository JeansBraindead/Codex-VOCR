# VOCR Beta Testing

This guide describes the current beta path for VOCR. The normal test surface is
the `Beta-Test` tab in Normalmode.

## Current Go/No-Go Source

The latest green handoff is:

`docs/beta/sessions/2026-07-16-jeenz-normalmode.md`

Use that file as the current local go/no-go source until a newer session file
replaces it.

The remaining local-live, cloud, and soak cycles are tracked in:

`docs/BETA_TEST_CYCLES_L_C_S.md`

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
| Workflow/Parallelitaet/Memory | S05, S06, S08, S09, S10, S11, S14, S18, S19, S20, S23 |
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
- optional hard cloud E2E gates C00, C01, C02, C03, C05, C06 when Cloud is explicitly enabled

S21/S22 do not load, start, or download any model. They only use the already
running LM Studio OpenAI-compatible API and the repo `.env`. With key/server
available they pass live; without key/server they skip cleanly.

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
| S18 | core | parallel claims |
| S19 | core | project memory |
| S20 | core | visionary worker plan |
| S21 | local | LM Studio `/models` live check |
| S22 | local | LM Studio `/chat/completions` live smoke |
| S23 | core | advisor calibration fallback |
| C00 | cloud | cloud guard without flag |
| C01 | cloud | real Codex E2E red-to-green |
| C02 | cloud | live ScopeGuard gate |
| C03 | cloud | live Secret Scan gate |
| C04 | cloud | manual prompt A/B measurement |
| C05 | cloud | live retry economy |
| C06 | cloud | live baseline objective |
| C07 | cloud | manual Advisor live calibration |

## CLI Equivalents

```powershell
vocr beta
vocr beta --only S03,S07
vocr beta --only S21,S22 --tier local
vocr beta --only C00,C01,C02,C03,C05,C06 --allow-cloud --max-cloud-tasks 6
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

## Automatisiert vs. Manuell

**Automatisiert:** Core + Local-Live + harte Cloud-Gates laufen ueber den
All-in-One-Button (`start_final_all_in_one`) bzw. die gestaffelte Kette
(`beta_next_test_chain`): S00-S20, S23 as Core, S21/S22 conditionally when
Local-Live is requested, and with the Cloud checkbox enabled the hard gates
C00, C01, C02, C03, C05, C06. None of this needs a per-step human judgment
call, so it is safe to chain.

**Manuell:** These cases stay out of the automated chain on purpose, because
they either spend real Codex quota or hand back a number a human has to
interpret instead of a clean pass/fail:

- C04 (Prompt-A/B) and C07 (Advisor-live calibration) — see "Cloud Tests"
  below for the exact invocation.
- Phase S: Soak/Chaos (long unattended runs, crash-recovery, parallel-load) —
  see `docs/BETA_TEST_CYCLES_L_C_S.md`. This phase is fire-and-forget by
  design and is driven from that guide, not auto-chained.

## Cloud Tests

Cloud remains opt-in.

Only enable the Cloud checkbox, or run `--allow-cloud`, when the user has
explicitly decided to spend cloud quota. The current local green handoff did not
run cloud.

Chainable hard gates:

```powershell
vocr beta --only C00,C01,C02,C03,C05,C06 --allow-cloud --max-cloud-tasks 6 --tag cloud-gates
```

Manual measurement cases:

```powershell
vocr beta --only C04 --allow-cloud --max-cloud-tasks 2 --tag cloud-ab
vocr beta --only C07 --allow-cloud --max-cloud-tasks 2 --tag cloud-advisor
```

C04 compares real legacy versus contract token use against the S11 estimate of
41.3%. C07 compares Advisor estimates against live worker timing/overhead.
Run these near the start of a fresh quota window and keep both halves of each
measurement; a half A/B is not comparable.
