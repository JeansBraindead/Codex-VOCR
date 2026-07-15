# VOCR Threat Model

VOCR is a local safety layer around Codex-oriented work. Its core promise is not
"the worker is trusted"; its promise is "work is scoped, reviewed, and promoted
only after gates pass."

## Trust Boundaries

- User intent is trusted only after the Visionary has enough explicit detail.
- Repository files are untrusted input. A file can contain prompt-injection text.
- `.vocr/VOCR_TASK.json` is the trusted task contract generated from accepted
  Vision/Organize state. `.vocr/CONTEXT_PACK.txt` is untrusted repo context and
  is a map, not an instruction source.
- Context packs are untrusted summaries of repo files. They are delimited in the
  worker prompt and must not override VOCR, user, system, scope, or review rules.
- Codex and future local LLM workers are execution tools, not promotion authority.
- Git worktrees are disposable execution sandboxes. The main branch is protected
  by review and promote gates.

## Current Controls

- Readiness gate: the Visionary asks for missing details before planning.
- Graphify: workers receive a compact repo map instead of reading broadly first.
- Scope Guard: task scope is translated into path globs. Changed files outside
  those globs are blocked before commit and the task becomes `needs_changes`.
- Denied roots: `.git`, `.venv`, and `.vocr/ledger.jsonl` are never valid worker
  edits.
- Review Gate: accepted review is required before promotion.
- Promote Gate: merge/PR promotion is explicit and never automatic.
- Scope Claims: optional parallel worker coordination records active scope
  reservations in the ledger. Claims prevent avoidable worker collisions, but
  they are not a security feature; Scope Guard and review remain the safety
  controls.
- Ledger redaction: obvious secret keys and `sk-...` style values are redacted
  before writing events.
- Pre-commit secret scanning: worker diffs, including new untracked text files,
  are scanned before `git add` and `git commit`.
- Optional gitleaks integration: if `gitleaks` is installed, VOCR runs it with
  redacted output in addition to the minimal scanner.

## Prompt-Injection Risks

Repo content can contain instructions such as "ignore previous instructions" or
"exfiltrate secrets". VOCR treats that content as data. Workers must use context
packs only to identify likely files and facts. Any instruction inside a file,
diff, test output, or context pack is lower priority than VOCR scope, user intent,
and review gates.

Minimal mitigation in this MVP:

- Context packs are wrapped in `<VOCR_UNTRUSTED_CONTEXT>` delimiters.
- Contract handoff keeps trusted JSON contract and untrusted context in separate
  files inside the worker worktree.
- Retry prompts mark diffs and test output as untrusted.
- Workers are told to stop when task details are unclear.

## Local Assist Trust Matrix

`VOCR_LOCAL_ASSIST=true` is intentionally narrow. A local model may expand a
context query only from trusted task title and goal text. It may not author
VisionSlices, TaskPlans, reviews, acceptance decisions, contracts, or project
memory. Any local-assist output is treated as search terms and silently falls
back to the original query on parse or endpoint failure.

## Secret-Scanning

Ledger redaction is not enough. VOCR scans diffs before `git add` and
`git commit`.

Current scanner order:

1. Keyword keys: `api_key`, `token`, `secret`, `password`, `credential`.
2. Known patterns: OpenAI-style `sk-...`, GitHub tokens, private key headers.
3. Entropy heuristic for high-entropy values in added lines.
4. Optional gitleaks scan when the binary is available.

Expected behavior:

- If the diff contains likely secrets, VOCR blocks commit.
- The task becomes `needs_changes`.
- The finding is reported without printing the secret value.

## MCP Surface

`vocr serve-mcp` exposes status, context, plan, review, and promote-preview
tools. MCP promote is preview-only in this MVP. Actual merge/promotion remains
behind the normal accepted-review gate and explicit CLI command.

## ATT&CK-Aligned Notes

- Initial access vector: malicious repository content influencing worker prompts.
- Credential access vector: accidental secret introduction or secret exposure in
  logs, prompts, diffs, or reviews.
- Defense evasion vector: worker edits outside declared scope.
- Impact control: promotion requires explicit accepted review.

## Local LLMs

Local OpenAI-compatible models through `OPENAI_BASE_URL` reduce cloud dependency,
but they do not change trust boundaries. Local model output still goes through
scope, review, and promote gates.

## Project Memory

Project memory is disabled unless `VOCR_PROJECT_MEMORY=true`. Entries are never
auto-extracted from arbitrary repo content. They come only from explicit review
notes or cloud-review suggestions that become visible in the review artifact and
are persisted only when the final review decision is `accepted`.

Poisoning defenses are layered:

- Accept gate: `needs_changes` and `blocked` reviews discard pending notes.
- Length cap: each note is validated at 300 characters or fewer.
- Untrusted placement: retrieved notes are inserted into context packs under
  `PROJECT MEMORY (accepted reviews)` and remain untrusted context, not
  instructions.
- Manual pruning: `vocr memory prune <entry-id>` removes a bad note; there is no
  automatic decay or hidden summarization.
