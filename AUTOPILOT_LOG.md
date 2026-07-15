# VOCR Autopilot Log

## Contract-Handoff Phases

- Phase 0 (`bed07f6`): Baseline captured without code changes; gates established on the venv test path.
- Phase 1 (`9038d5a`): Added task contract handoff with `.vocr/VOCR_TASK.json`, separated context pack, and stable contract prompt mode.
- Phase 2 (`d47c302`): Added structured Codex review reports with schema validation, retry, and unstructured fallback.
- Phase 3 (`7b51175`): Added check ratchet modes through `VOCR_REQUIRE_CHECKS`.
- Phase 4 (`70d54fb`): Switched organize context from slice-wide copy to per-task context queries.
- Phase 5 (`0e1b881`): Added optional baseline checks in task contracts without blocking dispatch.
- Phase 6 (`22a1172`): Replaced raw retry tails with bounded failure distillates.
- Phase 7 (`24539fe`): Added Python symbol spans and `vocr context --symbol`.
- Phase 8 (`bc83fa1`): Added predictive retry token budget warnings/blocking from LearningStore history.
- Phase 9 (`6bd146b`): Added optional incremental Codex review base refs while deterministic gates stay full-diff.
- Phase 10 (`1cc3944`): Added default-off embedding retrieval with BM25 fallback.
- Phase 11 (`23da69a`): Added default-off local query expansion for trusted task title and goal text.
- Phase 12 (`7cb5780`): Added inert scope claims in the ledger with list/release support.
- Phase 13 (`585703c`): Added optional parallel `work-ready` waves for claim-disjunkt tasks.
- Phase 14 (`d34c2bc`): Added default-off accepted-review project memory and manual prune/list commands.
- Phase 15 (this commit): Added final docs, threat model updates, CLI reference, and rollout summary.
