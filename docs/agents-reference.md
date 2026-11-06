# ai-dev-pipeline v7 — full agent-facing reference

> **Audience: AI agents (Claude).** This is the operational contract for driving the
> `ai-dev-pipeline-v7` skill. `SKILL.md` is the short procedure loaded at trigger time;
> `README.md` is for humans; `AGENTS.md` holds the essential rules. This file is the full reference: read it when you need the
> *why*, the exact field semantics, the data contracts, or the failure-mode handling.
>
> **Two repositories.** This skill holds the templates, agents, commands and hooks. The `aidp`
> binary, its JSON schemas and its own docs live in the aidp repository
> ([AlexisVuk/ai-dev-pipeline-v7](https://github.com/AlexisVuk/ai-dev-pipeline-v7)), checked out at `AIDP_SRC` (default `C:/CODE/Tools/aidp`).
> Below, a `crates/` or `schema/` path, and a `docs/` path other than this file, belongs to that
> repository.
>
> **One-sentence model:** `aidp` (a Rust binary) compiles a YAML pipeline into a deterministic
> JavaScript **Workflow** script; you run that script with the `Workflow` tool; sub-agents do all
> the real work and return schema-validated JSON. **You are a thin driver — you do not improvise.**

---

## 0. TL;DR for the driving agent

```
0. aidp vault status --format json-compact         → where the output will land (warn if unconfigured)
1. aidp pipeline list --format json-compact        → AskUserQuestion to pick a template (never infer)
2. (read its inputs) AskUserQuestion for enum inputs → build --inputs JSON
3. aidp run init   --pipeline <path> --target <id> [--inputs <json>]   → capture aidp run_id + run_dir
4. aidp workflow emit --run <run_id>                → capture the printed workflow.js path
5. Workflow { scriptPath }                          → capture the Workflow runId + result object
6. Branch on result.status: done | awaiting_gate | awaiting_plan | paused  (see §6)
   awaiting_plan → re-run `aidp workflow emit` (it compiles the tail from plan.json), then resume
```

**Set `AIDP_SKILL_ROOT` to this skill's directory for every `aidp` call** so v7 templates are
discovered instead of v4's. On this machine: `~/.claude/skills/ai-dev-pipeline-v7`.
- PowerShell: `$env:AIDP_SKILL_ROOT = "<v7 skill root>"`
- bash: prefix each call → `AIDP_SKILL_ROOT=<v7 skill root> aidp ...`

Gateway-launched sessions also get `AIDP_BIN` (absolute `aidp` path). If an `aidp` call exits 127
mid-run, retry through `"$AIDP_BIN"`; if that fails, stop and report the run dir and the
`record-resume` to replay (SKILL.md "Exit 127", §14).

**v7's one structural change: output lives in an Obsidian vault**, at
`<vault>/Pipelines/<repo>/<feature>/<run_id>/`, not in the repo's `.aidp/`. `aidp` generates the index
notes (`_*.md`) that link runs, stages, features and repos. See §8 for the layout and resolution rules.
Never write or edit a `_*.md` yourself.

---

## 1. Mental model

| Layer | Role | You touch it? |
|---|---|---|
| **`aidp` binary** | Single source of truth. Discovers templates, validates, initializes run state, builds the knowledge graph, **emits the Workflow script**, computes summaries. | Yes — you run a handful of subcommands. |
| **`workflow.js` (emitted)** | Deterministic JS that calls `agent()` / `parallel()` / loops, one block per stage. | **Never** hand-edit. Fix the template and re-emit. |
| **`Workflow` tool** | Executes the script in the background, schema-validates each sub-agent reply, accounts tokens, supports `parallel()`, worktree isolation, and cached resume. | Yes — you invoke it and read its result object. |
| **Sub-agents** (analyzer/planner/executor/reviewer) | Do the actual work: read, plan, write code, review. | No — they are spawned *by the Workflow*, not by you. |
| **You (driver)** | Pick template + inputs, run `aidp`, invoke `Workflow`, relay gates/blockers to the user. | This is your entire job. |

The point of v7 over v4: the orchestration loop is **deterministic JS**, not an LLM "dumb driver"
re-deciding each step. That removes every v4 fragility tied to LLM step-piloting (see §13).

---

## 2. When to invoke this skill

- `/run-pipeline-v7 <template> [target]`
- "lance la pipeline v7 …", "run pipeline v7 …", "ai-dev-pipeline-v7"
- Any v4-style request where the user explicitly wants the **v7 (Workflow) engine** — e.g. for
  benchmarking v4 vs v7.

Do **not** invoke for generic dev work the user did not route through the pipeline.

---

## 3. The `aidp` command surface (what the driver runs)

These are the only commands you run during a v7 run. Always with `AIDP_SKILL_ROOT` set (§0).

**Global flags.** `--workspace-root`, `--vault`, `--no-vault`, `--format` and `-v` are declared once and
accepted before or after the verb. `--vault` works on the read commands too: `run state|summary|reconcile|
verify|record-resume`, `progress`, `gate approve|abort|pending`, `scope resolve|check|verify`,
`workflow emit|plan-status`, `cost show|counterfactual`, `status`. `--format` has four values:
`json-compact`, `json-pretty`, `ndjson` (one JSON value per line, one line per array element) and `text`.
`run summary`, `run state`, `run reconcile` and `progress` default to `text` and accept `--format json-*`.
Enumerated flags (`ticket --type|--priority|--source|--track`, `git outcomes --overlap|--window`,
`--input k=v`, `gateway --bind`) are validated at parse time (exit 2). See `docs/migration-LOC-39.md`
and `docs/adr/loc-39-cli-flag-contract.md`.

| Command | Purpose | You capture |
|---|---|---|
| `aidp pipeline list` | List discoverable templates. | template ids + paths |
| `aidp pipeline show <id>` | Full resolved pipeline (inspect `inputs:`). | input specs |
| `aidp vault status` | Where the Obsidian vault resolves and how it was found (`source`), plus repo/run counts, the `repo_segment` this workspace maps to, any `ambiguity`, and how many pre-v7 runs are still in-repo. Run it before a run. | vault root + source |
| `aidp run start --pipeline <path> --target <id> [--inputs <json>\|--inputs-file <path>] [--input k=v ...] [--approve-gate <stage> ...] [--vault <path>\|--no-vault]` | One-shot `run init` + first `workflow emit`, with gate pre-approval baked in before that first emit. `--approve-gate` is repeatable; the literal `*` pre-approves every stage that *declares* a `gate:` (present and neither `false` nor `null`), whatever the run's track — declaration, not evaluation. Without `--approve-gate` the list comes from `AIDP_AUTO_APPROVE_GATES` (comma-separated, e.g. `"pr,plan"` or `"*"`) — the flag replaces the environment, it never merges with it; a name no stage declares is a `warning:` on stderr, not an error. `--inputs-file <path>` reads the inputs JSON from a file instead of argv, on the same path as `--inputs` (conflicts with it) — it exists for shell quoting (accented ticket bodies mangled through argv; a file carries ASCII-escaped `\uXXXX` JSON losslessly), and is how the autonomous ticket dispatcher launches a run; `--input k=v` still layers on top of either. The envelope also carries `warnings` (LOC-33): init-time problems — an unevaluable `when:`/`gate` expression, an undeclared `--input` key — that no longer go to stderr and no longer stop the run; the driver must relay a non-empty `warnings` list to the user. | run_id, run dir, script path, `gates`, `auto_approved_gates`, `warnings` |
| `aidp run init --pipeline <path> --target <id> [--inputs <json>] [--vault <path>\|--no-vault]` | Create run state, build knowledge graph, allocate `run_id`. Prints `run_id` on **stdout**, and `run_dir:` / `vault:` on **stderr** — relay the run dir, it is in the vault. | **`run_id`**, run dir |
| `aidp workflow emit --run <run_id>` | Compile the run into `workflow.js`. With a `plan_tasks:` stage this is called **twice**: pass 1 stops at that stage, pass 2 (after the planner wrote `plan.json`) compiles the tasks + the tail. Prints the phase on stderr as a JSON line identified by its `phase` key among the other stderr lines (§10.2). | **script path** |
| `aidp workflow plan-status --run <run_id>` | Report the plan-driven stages: compiled or awaiting, and the scheduled task graph (waves, concurrency, orderings inserted for write conflicts). | task schedule |
| `aidp run exec <template> --target <id> --inputs-file <path> [--foreground]` | Run a pipeline natively in the gateway daemon: one session per stage, no Workflow session (`POST /api/runs`). Writes the same run-state plus `mode: "native"`. See `docs/native-execution.md`. | run id |
| `aidp run plan-exec --run <run_id>` | Write the pass's typed execution plan to `<run_dir>/execution-plan.json` and print its path. Read-only: the plan is recomputed from the pipeline and run state, never stored in run-state. Workflow mode does not need it; see `docs/native-execution.md`. | plan path |
| `aidp run reconcile --run <run_id> --from <result.json>` | Fold the Workflow result back into run-state (status/tokens/outputs) so summaries are truthful. Run before `summary` on a v7 `done`. | reconciled summary |
| `aidp run record-resume --run <run_id> [--workflow-run-id <runId>] [--pending-gate <stage>] [--approved-gate <stage>] [--from-result <file>]` | Persist the resume anchor: the Workflow `runId`, the gate awaiting approval, or an approval. `--from-result <file>` rebuilds `workflow_run_id` and `pending_gate` from a saved `workflow-result.json` when the driver could not call `aidp` at the end of the pass (§6); explicit flags win. | resume anchor |
| `aidp run summary [--run <run_id>] [--format text\|json-compact\|json-pretty\|ndjson]` | Human-readable run summary (Markdown by default) (print at end / on abort). Without `--run`, summarises the run in flight and prints nothing when there is none. | — |
| `aidp doctor` | Health-check the install (binary, templates, hooks, schemas, **vault**). Its `aidp_on_path` check verifies that the first `aidp` on PATH is the running, up-to-date release binary. Exits 6 on a failed check. Its `providers` check verifies each configured agent provider's binary is present and answers `--version` (`docs/providers.md`). | status |

Vault maintenance (not part of a run): `aidp vault init --vault <path>` creates the skeleton, creates
`.obsidian/` if missing, and pins the path in `~/.aidp/config.json`; `aidp vault reindex` regenerates
every `_*.md` for every run in the vault (use after upgrading `aidp`, or if notes were hand-edited).

**Findings merge** (called by the reviewer synthesis stage itself, not by you): `aidp findings merge
--input <p> --input <p> ... --out <p> [--label <axe>=<p>] [--format json]` recomputes
`severity_counts` and derives `has_blocking_findings` from the merged findings rather than trusting a
model's summary — `templates/review.yaml`'s synthesis stage runs it as part of its own work (§9.2).
You never invoke it yourself.

**Skill rules check** (called by the `review` synthesis stage and dev-aidp's `rereview`, not by you):
`aidp skill-rules check [--base <ref>] [--repo <dir>] [--diff-file <path>] [--skill <name>]... --out <path> [--run-id <id>]`
scans the **added lines** of the branch diff (merge-base of `--base`, default `master`, and HEAD; or a
unified diff read from `--diff-file`) against the mechanical rules each skill declares. Today
`rust-dev-aidp` has two: no `//` line comment other than `///` and `//!`, and no ticket key, both on added
`.rs` lines. `--skill` (repeatable) restricts the check to those skills; `--repo` picks the repository to
diff. It writes a `findings.json` of `blocking` findings with file and line, prints the output path on
stdout and exits 0 whether or not violations exist. The synthesis stage merges it as axis `skill_rules`
through `aidp findings merge --label skill_rules=<file>` (§9.2).

**Agent registry setup** (one-time, not part of a run): `aidp setup agents [--dest <dir>] [--force]`
writes the restricted `agentType`s (§10) into `~/.claude/agents/` — refuses to overwrite an existing
file without `--force`, since that registry is shared with the user's other agents.

> **Two distinct IDs — do not conflate them:**
> - **`run_id`** — returned by `aidp run init` (format `YYYYMMDD-HHMMSS-xxxx`). Used for
>   `aidp workflow emit --run` and `aidp run summary --run`.
> - **`runId`** — returned by the **`Workflow` tool**. Used for `resumeFromRunId` on resume.
> They are different values from different systems. Track both.

v7 ships its **own** management commands (all `-v7` suffixed): `/pipeline-setup-v7`,
`/pipeline-doctor-v7`, `/pipeline-status-v7`, `/pipeline-resume-v7`, `/pipeline-validate-v7`,
`/pipeline-new-v7`, `/agent-new-v7` — plus the entry point `/run-pipeline-v7`.

**CI autopilot** (`aidp ci`, §10.1) — not part of a run, but the thing that *starts* one:
`aidp ci status|signals|dispatch|watch|ack|reset|config`, plus the hook handler
`aidp ci hook post-tool|stop|prompt|session-start` (reads the hook JSON on stdin, answers on stdout,
exit 2 to make the session act). `aidp sonar config|gate|issues|hotspots|measures|report|rule` is its
SonarQube half, also called directly by the `sonar-fix` stages.

**Exit codes.** Every `aidp` subcommand returns one of eight codes (`aidp_core::ExitStatus`): 0 success,
1 internal error, 2 reserved for hook wake (`aidp ci hook post-tool|stop`), 3 not found, 4 policy
refusal (including a vault leak caught by `scope verify` / `run reconcile`), 5 upstream failure, 6
negative verdict (`doctor`, `cost anomaly`, `scope verify`, `dev check --strict`), 7 a CLI usage fault.
`aidp mongo` and `aidp sqs` propagate their child process's own exit code instead. See
`docs/exit-codes.md` for the full table and the migration notes from the previous, inconsistent codes.

> **Why an HTTP client and not the SonarQube MCP server.** `aidp ci` runs as a **subprocess** spawned
> by a Claude Code hook, and a subprocess has no MCP client — so the probe that *triggers* the pipeline
> can only be an HTTP call. Same constraint in cron/headless runs. Sub-agents inside a stage *can* use
> an MCP, and `sonar-issues-collect-aidp` prefers one when it is connected; the `sonar-issues.json`
> contract is identical either way. Note that the MCP server is a separate deployable
> (`sonarsource/sonarqube-mcp`, stdio or `SONARQUBE_TRANSPORT=http`) — SonarQube Server hosts no `/mcp`
> endpoint itself.

**Project stack** — `aidp project stack [PATH]` detects the stack of a workspace (default `.`) and prints `{path, stack}` with `stack` one of `csharp|lambda-ts|angular|rust|ts-node|unknown`. It is read-only and separate from `stack: auto` at run init, which is unchanged. A missing directory exits 3. `aidp gh pr-comment <repo> <n> --body-file <path|->` posts a PR comment (`-` reads stdin) and emits `{id,url}`; it shares its implementation with `gh comment-create`.

**Dev-test runners** (called by *sub-agents* inside the `run-tests-dev` / `test-us-e2e` stages, not by
the driver): `aidp http send|run-file`, `aidp mongo run-file|eval`,
`aidp sqs send`, `aidp gh workflow-run --watch` (deploy), `aidp gh pr-status` (read-only merge gate, exits 0 whatever the verdict), `aidp gh squad-repos|squad-prs` (squad PR inbox, read-only), `aidp gh pr-comments <pr> [--repo]` (a PR's review comments split into points: `##` to `####` headings, else top-level items; code blocks never split; id `<commentId>#<i>`; `bot` flag from `*[bot]` and `ci.bot_authors`; the summary marker `<!-- aidp:pr-comments-summary -->` is excluded) and `aidp gh pr-review-threads --all` (adds `comments[]`, `lastBy`, `addressed` `direct|indirect|no` as advisory only, `waitingOnReviewer`, `startLine`), `aidp gh pr-detail|pr-files|pr-file-diff` (read a PR in full), `aidp gh comment-create|comment-edit|comment-delete|review-comment-create|review-comment-edit|review-comment-delete|review-submit` and `aidp gh run-rerun --failed` (PR write actions), `aidp sonar report --pr <n> --envelope`, `aidp gh pr-ready|pr-update-branch|pr-merge|thread-reply|thread-resolve` and `pr-create --draft` (PR actions, `docs/gateway-api.md` "PR actions — Lot 13a"), and `aidp dev target-show|check`. All read
non-secret connection config from `.aidp/dev-target.json` and secrets from `AIDP_DEV_*` env. See the
`dev-target-config`, `dev-test-runner`, and `deploy-dev` skills.

**Gateway daemon** (`aidp gateway`) — not part of a v7 run: a separate resident process, started and
queried directly, not one the driver invokes. Its HTTP contract is `docs/gateway-api.md`. The
daemon reads `AIDP_UI_TOKEN` (off-loopback callers get `401` without it; distinct from
`AIDP_HOOK_TOKEN`) and `AIDP_READ_ONLY` (refuses mutating verbs outside `/api/hooks`), and
`aidp gateway <cmd>` sends `AIDP_UI_TOKEN` when set. **LOC-25:** that gate now runs before a single
body byte is read, and `AIDP_MAX_BODY_BYTES` (default 8 MiB) bounds the request body — anything
larger gets `413`, and a non-empty body that is not valid JSON gets `400 {"error":"invalid JSON body"}`;
see [Request body bound — LOC-25](https://github.com/AlexisVuk/ai-dev-pipeline-v7/blob/master/docs/gateway-api.md#request-body-bound--loc-25) for the full rules.
**LOC-26:** a mutating request whose `Origin` is not in `AIDP_ALLOWED_ORIGINS` gets `403` even from
loopback, CORS echoes only allowed origins, tokens are read from headers only (no `?token=`), SSE uses
single-use tokens and webhooks accept a `X-Hub-Signature-256` HMAC — see
[Access policy — LOC-26](https://github.com/AlexisVuk/ai-dev-pipeline-v7/blob/master/docs/gateway-api.md#access-policy--loc-26).
**LOC-29:** Ctrl-C on `aidp gateway serve` calls `ServeHandle::stop()` (children killed, sessions
marked `orphaned`); in-flight request threads are capped by `AIDP_MAX_INFLIGHT_REQUESTS` (default
256, `503` beyond it — distinct from LOC-25's `413`); bus subscriptions and SSE streams are bounded,
and a stalled SSE client is disconnected with one `overflow` bus event; every outbound HTTP call uses
a shared ureq agent with explicit connect/read/write timeouts, and a test forbids ureq free functions
in `crates/*/src/`; `POST /api/dispatcher/tick` runs the local tick, and any tick can answer
`{"mode":"busy"}`; the automations scheduler never overlaps two runs of one automation
(`automation.skipped`, `skipped: "already running"`); `GET /api/health` gains a `threads` object and
caches its probes; `tokio` is gone from the dependency tree — see
[Concurrency and resource bounds — LOC-29](https://github.com/AlexisVuk/ai-dev-pipeline-v7/blob/master/docs/gateway-api.md#concurrency-and-resource-bounds--loc-29).
Gateway HTTP errors go through `ApiError`, a typed enum mapped to a status and a body of
`{"error": <message>, "code": <slug>}`: `NotFound` → 404, `Conflict` → 409, `Unauthorized` → 401,
`Config`/`ShuttingDown` → 503, `Upstream` → 502, `Io` → 500, and an untyped validation failure → 400.
`POST /api/tickets/sync` without `AIDP_JIRA_BASE` set is now a `Config` 503 naming the missing
variable, where it used to be a plain 400. See
[Error responses](https://github.com/AlexisVuk/ai-dev-pipeline-v7/blob/master/docs/gateway-api.md#error-responses) for the full status table.
The daemon resolves the vault with `aidp_core::vault::resolve_global` (`AIDP_VAULT`, then
`~/.aidp/config.json`, no auto-detection) and honours the disable values of `aidp run init`
(`off|none|0|false|-`, case-insensitive): `/api/status` reports `vault: null`, `/api/dispatcher/plan`
answers mode `no-vault`, `/api/tickets` answers `503`, and no directory is created. LOC-34: the home
directory resolves everywhere through `aidp_core::vault::home_dir` (`USERPROFILE`, then `HOME`; Sonar
follows it now) and program lookup through `aidp_core::program::resolve_program` (doctor's
`aidp_on_path` and `external_binaries` agree on a `.cmd` install). The gateway deserializes
`run-state.json` into `aidp_core::RunState`; an incomplete file is skipped.
The daemon spawns `claude` without any shell
(Windows included — LOC-24 removed the `cmd /C` hop) and honours `AIDP_CLAUDE_BIN` as the
executable override. It exports `AIDP_BIN` (the `aidp` binary's absolute path; a user-set value is
kept) and a PATH prefixed with that directory to every session, and refuses a launch with `503`
`code: config` when the binary is missing. `POST /api/sessions` validates `permissionMode`, `effort` and `model` (`400` on
failure), and the dispatcher path is validated identically, so a `config.yaml` typo fails the launch
loudly. Since **Lot 6a**, a session launch can chain
off a previous one via `contextFrom` (a gateway session id): the daemon injects that session's run
summary and artefacts into the new session's opening prompt — see
[Launch chaining — Lot 6a](https://github.com/AlexisVuk/ai-dev-pipeline-v7/blob/master/docs/gateway-api.md#launch-chaining--lot-6a) for the full rules
(resolution timing, graceful degradation, the anti-loop refusal, and budget inheritance). While a
headless session runs a pipeline through the `Workflow` tool, the daemon tails its journal and
publishes a `session.workflow_progress` bus event per sub-agent start/finish/failure — see
`docs/gateway-api.md` for the payload.

| Command | Purpose | You capture |
|---|---|---|
| `aidp gateway serve` | Start the resident daemon (sessions, automations, HTTP API + SSE). | — |
| `aidp gateway sessions` | List sessions the daemon is tracking. | session ids + status |
| `aidp gateway start` | Start a new session (pipeline or free prompt) in the daemon. `--context-from <sessionId>` chains it off a previous session — see [Launch chaining — Lot 6a](https://github.com/AlexisVuk/ai-dev-pipeline-v7/blob/master/docs/gateway-api.md#launch-chaining--lot-6a). | session id |
| `aidp gateway presets list` | List saved session presets. | preset ids |
| `aidp gateway presets add <file.json>` | Save a preset from a JSON file. | preset id |
| `aidp gateway presets rm <id>` | Delete a saved preset. | — |
| `aidp gateway presets start <id>` | Start a session from a saved preset. | session id |
| `aidp gateway queue list` | List launches queued behind a running session (one session per project). | queue entry ids |
| `aidp gateway queue promote <id>` | Make a queued launch the next one out for its project. | — |
| `aidp gateway queue cancel <id>` | Drop a queued launch. | — |
| `aidp gateway worktrees list [--project <id>]` | List the ticket worktrees under `<vault>/Pipelines/` (`GET /api/worktrees`). | worktree rows |
| `aidp gateway worktrees prune [--dry-run]` | Save then remove the worktrees of done, cancelled or unknown tickets (`POST /api/health/cleanup`); `--dry-run` only lists them. | removed / failed |

**Worktrees.** The daemon runs each dispatched or manually started ticket in
`<vault>/Pipelines/<repo>/<KEY>/.worktree` on `feat/<KEY>`. Admission is per workspace: one live
session per worktree or per checkout, not one per project. `ui` sessions stay on the checkout, so
they no longer block the dispatcher. `dispatcher.max_worktrees_per_project` (default 3) caps live
worktrees; the dispatcher skips with `worktree-cap` or `branch-checked-out-elsewhere`. A merged or
cancelled ticket's worktree is saved under `refs/aidp-wip/<KEY>-<sha12>`, then removed. See
`docs/gateway-api.md` and `docs/tickets.md`. On Windows, `aidp doctor`'s `git_longpaths` check warns
(non-blocking) when global `core.longpaths` is not `true`.

**PR status (Lot 12a).** The daemon serves a read-only merge gate at `GET /api/prs/status?repo=&number=`
(20 s cache) and `GET /api/tickets/:key/pr`. A GitHub webhook delivery on one of six PR events drops
the cache entry and publishes `pr.status`. See
[PR endpoints — Lot 12a](https://github.com/AlexisVuk/ai-dev-pipeline-v7/blob/master/docs/gateway-api.md#pr-endpoints--lot-12a).

**PR inbox (Lot 25a).** The daemon lists the open PRs of the whole squad, sorted into lanes by what the
viewer has to do, at `GET /api/prs` (2 min cache, refreshed by webhook or `POST /api/prs/refresh`).
Local seen/ignored marks live in `~/.aidp/gateway/pr-marks.json`. The squad is configured under the
`squad` key of `~/.aidp/config.json`. See [PR inbox — Lot 25a](https://github.com/AlexisVuk/ai-dev-pipeline-v7/blob/master/docs/gateway-api.md#pr-inbox--lot-25a).

**PR detail (Lot 26a).** The daemon serves one PR in full (header, files, per-file diff, comments, review threads, checks, Sonar gate) and accepts comment, review and CI-rerun actions through the `aidp gh` verbs listed below. Drafts and per-file viewed marks persist in `~/.aidp/gateway/pr-drafts.json` and `~/.aidp/gateway/pr-viewed.json`. See [PR detail — Lot 26a](https://github.com/AlexisVuk/ai-dev-pipeline-v7/blob/master/docs/gateway-api.md#pr-detail--lot-26a).

**PR attention (Lot 28a).** The daemon computes seven PR signals (`new_comment`, `changes_requested`,
`ci_red`, `sonar_red`, `conflict`, `mergeable`, `review_requested`) on squad refresh, GitHub webhook
and CI heartbeat. Each new one is deduplicated by fingerprint in `~/.aidp/gateway/pr-attention.json`,
creates a `pr.attention` inbox entry and bus event, and is served at `GET /api/prs/attention`. Toggle
signals under `notifications.pr` in `~/.aidp/config.json`. See
[PR attention — Lot 28a](https://github.com/AlexisVuk/ai-dev-pipeline-v7/blob/master/docs/gateway-api.md#pr-attention--lot-28a).

**Native runs.** The daemon executes a v7 run itself (`aidp-gateway/src/native_runs/`): one session per stage, started by `POST /api/runs` or `aidp run exec`, with gates in the inbox and bus events `run.started`, `run.stage_changed`, `run.waiting_gate`, `run.ended`. Workflow mode is unchanged. See `docs/native-execution.md` and `docs/gateway-api.md` ("Runs natifs").

**Free sessions.** `aidp gateway start --workspace project|ticket:<KEY>|scratch:<name>|path:<dir>` starts a
session outside a pipeline run (also `workspace`, `external` resume and reply `attachments` on the HTTP API). `path:` workspaces must lie under
`AIDP_ALLOWED_ROOTS` (default: registered projects and the vault). Sessions in `plan` permission mode run on a
read-only lane (ceiling 3) beside a writer; a writer on a busy workspace queues as `workspace-busy`. See
`docs/gateway-api.md`.

**Local tickets** (`aidp ticket`) — no pipeline stage calls it, but it is not free of sessions: the
gateway's dispatcher starts sessions from the tickets in `TODO/`, under a slot ceiling, a
one-session-per-project rule, and a token-budget verdict. The verbs, on one command:
`new|list|show|render|edit|status|route|cancel|log|reindex|sync|start|plan|dispatch|budget|adopt`.
Four guardrails shape what the dispatcher launches: a default JQL limited to open sprints
(`sprint in openSprints()`), a `waiting-on:<KEY>` skip while Jira blockers are unfinished
(`jira.finished_statuses`), adoption of an existing PR at launch time or by hand with
`aidp ticket adopt <KEY> --pr <url|number>` (`POST /api/tickets/:key/adopt`), and an epic context
block in the dispatched prompt. Tickets
live as Markdown notes at
`<vault>/TODO/<service>/<KEY>.md`, with generated `_TODO.md` (board) and `_<service>.md`
(per-service)
indexes regenerated on every call. See `docs/tickets.md` for the full command surface and note format.
`aidp jira issue-edit <KEY> --field "<name|id>" --value "<text>"` sets one Jira text field; the
dispatcher uses it for the release watch (`docs/tickets.md#release-watch`).

**Ticket flows** (`aidp flow`) — the per-ticket workflow engine, run by the daemon, not by a pipeline stage:
`validate|show|list|start|status|approve|verdict|retry|skip|pause|resume|abort`. `validate` and `show`
are local; the others go through the daemon client, like `aidp ticket start`. Definitions live in
`templates/flows/` (validated by `schema/flow.schema.json`), which is **not** a pipeline directory:
`aidp pipeline list` does not read it. See `docs/flows.md` and the `Flows — Lot 29a` section of
`docs/gateway-api.md`.

**Flow action verbs.** The flow engine's actions are also plain `aidp` verbs, each printing one JSON
object on stdout. Business refusals exit 6 (negative verdict); a transport or configuration error
keeps its usual code (`docs/exit-codes.md`).

| Command | JSON output | Exit |
|---|---|---|
| `aidp jira issue-assign <KEY> --me` | `{key, assignee, changed}`: assigns the issue to the current user, `changed` is false when already assigned | 0 |
| `aidp jira issue-transition <KEY> (--transition-id <id> \| --to-status <name>)` | `{key, transition, status}`: exactly one of the two flags; `--to-status` resolves the transition by target status | 0, missing transition 6 |
| `aidp gh copilot-review <repo> <n>` | `{requested, reviewer}`: asks Copilot for a review of the PR | 0, Copilot unavailable 6 |
| `aidp gh deployment-approve <run_id> [--repo <owner/name>]` | `{approved, changed}`: approves the pending environment deployment of the run | 0, approval refused 6 |
| `aidp flow ci-watch --pr <n> [--repo <owner/name>]` | `{green, checks, sonar}`: waits for every check of the head commit, then reads the Sonar gate | 0 (red CI included, `green: false`), timeout 6 |
| `aidp flow deploy-dev --ref <ref> [--approve]` | `{ref, run_id, status, approvers}`: deploys to dev and handles the environment approval | 0, blocked on approval or failed run 6 |
| `aidp flow notify-teams --pr <url>` | `{notified, skipped}`: posts the Teams card unless the repository disabled it | 0 |
| `aidp flow git-branch <KEY>` | `{branch, created}`: creates `fix/<KEY>` for a bug, `feat/<KEY>` otherwise, when absent | 0, foreign commits on the remote branch 6 |
| `aidp flow jira-comment <KEY> --body-file <path>` | `{key, target}`: comments on the Jira issue, or writes a report file next to a local ticket note | 0 |

The composite verbs read `.aidp/flow.json` in the repository, merged over the `flow` key of
`~/.aidp/config.json`: CI workflows and Sonar project, `deploy` workflow and environment, `teams`
(`enabled`, default true), `copilot` (`enabled`, default false) and `caps.worktrees` (default 3).

### Local review verbs

| Command | stdout | Exit |
|---|---|---|
| `aidp gh review-post <repo> <n> --findings <file> --pass <n> --run <id>` | `{posted, review_id, threads[{finding_id, thread_id, path, line}]}`: one `COMMENT` review, one inline comment per in-diff finding, out-of-diff findings in the review body with their location. Idempotent per run and pass. | 0, 4, 5, 7 |
| `aidp gh thread-reopen <threadId> --body-file -` | `{thread_id, replied, unresolved}`: replies, then unresolves the thread | 0, 5 |
| `aidp gh pr-fix <repo> <n> --threads <ids> [--points <ids>] [--note-file -]` | `{session_id, workspace, workspace_kind, threads, dropped_threads}`: starts an autonomous fix session through `POST /api/prs/fix` (`docs/gateway-api.md`) | 0, 5, 6 |

Templates never write to GitHub: the workflow calls these two verbs. Contract in
`docs/adr/local-review-marker-contract.md`.

---

## 4. ABSOLUTE RULES (the driver MUST obey)

1. **MUST NOT** call `Edit`, `Write`, `MultiEdit`, or any non-`aidp` `Bash` yourself during a run.
   All real work happens inside the Workflow's sub-agents. No hook enforces this live — see §10 for the
   after-the-fact verification that covers stage writes.
2. **MUST NOT** hand-edit the emitted `workflow.js`. If something is wrong, fix the **template** and
   re-run `aidp workflow emit`.
3. **MUST NOT** plan, analyse, write code, or review yourself — that is sub-agent work inside the Workflow.
4. **MUST NOT** invent stages, reorder them, or skip the gate/resume protocol. The emitted script is the
   only source of truth.
5. **MUST** pick the template via `AskUserQuestion` — never infer it.
6. **MUST** accumulate the full list of approved gates across resumes (see §6).
7. **MUST NOT** edit `status:` or `autopilot:` in a `TODO/**` note; use `aidp ticket status`. Other
   frontmatter keys stay hand-editable, but `key:`/`service:` must be a single safe path component
   (no `/`, `\`, `:`, no `..`, not empty, never starting with `_`/`.`, no control character, none of
   `[`, `]`, `|`, `#` or a backtick, and not a Windows reserved device name like `CON`/`NUL`/`COM1`)
   or `aidp ticket` refuses the note and drops it from `list` — see `docs/tickets.md`.

---

## 5. Run lifecycle (the procedure, in detail)

**Step 1 — Pick template.** `aidp pipeline list --format json-compact`. Present choices via
`AskUserQuestion`. Never infer.

**Step 2 — Collect inputs.** Inspect the chosen pipeline's `inputs:` (call `aidp pipeline show <id>`
if needed). For every input with `kind: enum` and a `values` list, use `AskUserQuestion` (the
`default` is the recommended/first option). Build the `--inputs` JSON from the answers; **omit** inputs
left at their default.

**Step 3 — Init run.** `aidp run init --pipeline <path> --target <id> [--inputs <json>]`. Capture
`run_id`. (This also builds/refreshes the knowledge graph when enabled — see §11.)

**Step 4 — Compile.** `aidp workflow emit --run <run_id>`. Capture the printed **script path**
(`workflow.js`).

**Step 5 — Run the Workflow.** Invoke the `Workflow` tool with `{ scriptPath: "<script path>" }`.
On the **first** call do **NOT** pass `resumeFromRunId`. Capture the returned `runId` and the final
**result object**.

**Step 6 — Handle the result object.** See §6.

---

## 6. Result-object state machine (Workflow tool return)

The `Workflow` result is one of four shapes. Branch on `status`:

> **All four shapes below can also carry `guard_findings`.** The emitted script's own guard scans the
> free-text crossing a stage recollement (`fanin`, `taskin`, `taskUp`, `up`) against one shared pattern
> table (`guard::scan()` on the Rust side, the same table emitted as the `__guard(txt, src)` JS helper).
> A suspect block is wrapped in `<<<UNTRUSTED_UPSTREAM source="..." flagged="...">>> ... <<<END_UNTRUSTED>>>`
> and labeled as data, **never stripped** — the stage's own result stands exactly as documented below.
> A non-empty `guard_findings` is therefore **neither a pause nor an error**; `aidp run reconcile` folds
> it into `run-state.json` under the same key.
> Since LOC-27 the same framing also covers rendered stage input values and the free-text fields
> of a CI autopilot directive.

> **Write first, on every shape.** Before any other step, write the result object verbatim to
> `<run_dir>/workflow-result.json`. This is plumbing exempt from Rule #1 and needs no `aidp` call, so it
> succeeds even when `aidp` is unavailable. Write the unwrapped result object: when a background
> `Workflow` returns an envelope, write its `.result` (`reconcile` silently reports 0/N on the envelope).
> Then run `aidp run reconcile --from <that file>`, then the branch's `record-resume`.
> `record-resume --from-result` reads either shape.

### `{ status: "done", ... }`
Run completed. With `workflow-result.json` already written, run
`aidp run reconcile --run <run_id> --from <that file>` (folds per-stage status, tokens, and outputs
back into `run-state.json` — the emitted script runs in the Workflow runtime and never re-saves state
itself, so without this `summary`/`status` report 0/N), then print the reconciled summary and stop.

`reconcile` is not `done`-only: every early return (`awaiting_gate`, `awaiting_plan`, `paused`) now
carries the full `results` map for stages already finished, so the same `workflow-result.json` +
`aidp run reconcile` step applies there too — fold what has completed before branching further, so
`run-state.json` (and `last_workflow_status`) stay accurate even on a stop short of `done`.

### `{ status: "awaiting_gate", gate: "<stage>", ... }`
A gate needs human approval. This return also carries `results`, the envelopes of every stage that
already finished — reconcile them (see the `done` branch above) before proceeding. Do this even for a
gate hit early in the run: because `reconcile` reads `results` and nothing else, a gate return reports
the stages actually completed (and paid for in tokens) so far, not 0/N — skipping `reconcile` here is
what makes a legitimate in-progress run look like it did nothing.

**FIRST, before asking, write `workflow-result.json` (see "Write first" above), then persist the resume anchor:**
```
rtk aidp run record-resume --run <run_id> --workflow-run-id <runId> --pending-gate <stage>
```
This records the Workflow `runId` **and** marks `<stage>` as the run's `pending_gate` *before* any
decision — so if the run is left un-approved (the user defers, or the session/context ends), a later
`/pipeline-resume-v7` re-proposes this exact gate instead of losing the anchor and re-running the whole
pipeline. **This is the fix for the "resume re-runs everything" bug** (WI-P1-7): the anchor used to be
saved only on approval, so an un-approved pause dropped it.

Then `AskUserQuestion`: *"Approve stage `<stage>`?"* → **approve** / **abort**.
- **approve** → (1) `aidp run record-resume --run <run_id> --workflow-run-id <runId> --approved-gate <stage>`
  (persists the approval and **clears** `pending_gate`); (2) `aidp workflow emit --run <run_id>`
  (re-bakes the approved gates into `__approved`); (3) re-invoke:
  ```
  { scriptPath, resumeFromRunId: "<runId>", args: { approved_gates: ["<stage>"] } }
  ```
  Only the latest gate is needed in `args` — prior approvals are baked in (WI-P1-3). The already-run
  prefix replays from cache (the agent() calls are unchanged); execution continues past the gate.
  **Repeat from Step 6** with the new result.
- **abort** → stop; print `aidp run summary --run <run_id>` (it shows `awaiting gate: <stage>`). The
  runId + pending gate stay persisted, so resume re-proposes the gate.

> ✅ The "accumulate ALL gates" footgun is gone: `aidp run record-resume` persists approvals and
> `aidp workflow emit` bakes them into `__approved`, so passing only the latest gate is sufficient.
> ✅ An un-approved gate is no longer lost: it is persisted as `pending_gate` the moment it is proposed,
> so resume re-proposes it rather than re-executing every prior stage.
> ✅ A gate pre-approved at `run start` (via `--approve-gate` or `AIDP_AUTO_APPROVE_GATES`) is baked into
> `__approved` before the run's first `workflow emit` — this whole `awaiting_gate` branch is never reached
> for it, not even on the first `Workflow` call. An autonomous session with no human to ask relies on
> exactly that. It also changes what the `run start` envelope's `gates` key means: it now lists only the
> gates still awaiting approval (this pass's gates minus the pre-approved ones), alongside a new
> `auto_approved_gates` key naming what was baked in — both match the old `gates` value when nothing was
> pre-approved.

**When `aidp` is unavailable after the pass.** If the pass ends and no `aidp` call can run
(binary missing, session ending), `workflow-result.json` is the only record of the anchor. Recover it later:

- `aidp run record-resume --run <run_id> --from-result <run_dir>/workflow-result.json` rebuilds
  `workflow_run_id` and `pending_gate` from that file. It accepts the bare result object or a background
  `Workflow`'s `{result:{...}}` envelope. Only `status: awaiting_gate` yields a pending gate. Explicit
  flags win over the file, an approved gate is never re-opened, and a missing or malformed file is an error.
- `/pipeline-resume-v7`, finding `workflow_run_id` null and the file present, calls `--from-result` and
  re-proposes the recovered gate instead of re-running everything.
- The run note shows `anchor_persisted: false` with a warning callout, and the gateway run payload serves
  `status: paused` with `currentGate.anchorPersisted: false`, `workflowRunId` and `resumeCommand` for
  such a run.

> ✅ A gate stop survives a pass that ended without any `aidp` call: the anchor and the gate come back
> from `workflow-result.json`.
> ⚠️ Limit: `resumeFromRunId` prefix caching only replays within the same session. A cross-session
> recovery restores the anchor and the gate but may re-execute the prefix; approved gates are still
> never re-asked, since `__approved` carries them. A run that predates this and has no result file stays
> unrecoverable.

### `{ status: "awaiting_plan", at: "<stage>", producer: "<planner stage>", plan_path: "<file>" }`
The run reached a **plan-driven** stage (`plan_tasks:`, §7.1). Its tasks — and everything after it — are
compiled from the planner's `plan.json`, which only exists now that the planner has run. A normal,
expected stop: **not** an error, **not** a gate (no `approved_gates` value passes it).

1. `aidp run record-resume --run <run_id> --workflow-run-id <runId>` — persist the resume anchor first,
   exactly as for a gate, so the stop survives a lost transcript.
2. `aidp workflow emit --run <run_id>` — `aidp` loads the plan, validates the task graph, inserts an
   ordering wherever two tasks would write the same file, and compiles the tasks + the tail. The phase is
   printed on **stderr** (`{"phase":"plan_compiled",...}`); stdout stays the script path.
   - **If this command fails, the plan is malformed.** The message names the stage and the offending
     field. The fix is to re-run the planner stage (or fix the template/prompt) — never to hand-edit
     `plan.json` or `workflow.js`.
3. `aidp workflow plan-status --run <run_id> --format json-pretty` — optional, cheap, and worth showing
   the user: it *is* the run's real execution plan (tasks, waves, concurrency, every inserted ordering
   and why).
4. Re-invoke `Workflow` with `{ scriptPath, resumeFromRunId: "<runId>" }` — plus
   `args: { approved_gates: [...] }` if a gate was approved earlier in this run. The cached prefix
   replays; only the newly-compiled tasks and tail execute. Then re-enter this state machine.

> Only one extra round-trip per plan-driven stage, and it is deterministic: the same plan always compiles
> to the same schedule.

### `{ status: "paused", at: "<stage>", envelope: {...} }`
A sub-agent returned `blocked`/`failed`, or asked questions — or, for a **non-plan-task** stage,
`needs_review` (see the exemptions below).
- An `at` of `"<stage>#<task_id>"` is one **plan task** of a plan-driven stage (§7.1), not the stage
  itself: its siblings may well have succeeded, and any task depending on it was skipped with a synthetic
  `failed` envelope. Only `blocked`/`failed`/`ask_user_questions` produce this pause — a task's
  `needs_review` does not (see below). `aidp workflow plan-status` / `aidp run state` show which tasks
  completed.
- Relay `envelope.ask_user_questions` (if any) via `AskUserQuestion`.
- Surface `envelope.summary`.
- Stop unless the user resolves the blocker. **v7 v1 does not auto-resume mid-stage questions** —
  re-run after the user supplies what's missing.

> **`needs_review` never pauses on a reviewer — or on one plan task.** Three halves, engine and
> contract, saying the same thing:
> - **Contract** (`agents/reviewer.md`): every reviewer returns `status: "completed"` with
>   `signals.has_blocking_findings: true`. Blocking findings are a *signal*, never a halt. `needs_review`
>   and `blocked` are reserved for a review that could not be **produced** (ambiguous scope needing a
>   human, missing target, unwritten upstream artifact).
> - **Engine, reviewers** (`workflow_emit::soft_pause_stages`): every `agent: reviewer` stage is emitted
>   with the soft check, so a reviewer that drifts from the contract still cannot strand the run.
>   `blocked`, `failed` and `ask_user_questions` stay hard, so a reviewer keeps a way to stop for a human.
> - **Engine, plan tasks** (`workflow_emit::emit_plan_stage`): every task's per-task checkpoint is also
>   soft — a task deferring `shared_files` work to `follow_ups`, or otherwise flagging a concern about its
>   own slice with `needs_review`, is normal plan-task behavior (§7.1), and reconciling exactly that is
>   the merge sub-agent's job. It always sees every task's full envelope (`status` included) via
>   `taskin()`, so it decides whether the stage as a whole should still pause. `blocked`, `failed` and
>   `ask_user_questions` stay hard per task — a task that is genuinely stuck still stops the run for a
>   human. The **merge dispatch's own envelope** keeps the ordinary hard checkpoint (it is not a
>   reviewer), so an unresolved `needs_review` the merge agent cannot reconcile still halts the run —
>   just one step later, at the stage itself instead of at the task — **unless a correction loop
>   repairs that stage** (next point).
> - **Engine, stages a correction loop repairs** (`workflow_emit::loop_reviewed_stages`): when a
>   loop's body re-produces the output its `when:` reads, two kinds of stage get the soft check too.
>   The first is every stage a reviewer of that loop's source reads directly, reached through the
>   composed review's axes: `implement` in `dev-aidp` and `dev-lambda-ts`, `tests__tests_suite` in
>   `dev-csharp`. A stage further up (`dev-csharp`'s `implement`) keeps its hard checkpoint. The second is every non-reviewer body stage:
>   `replan`, `refix`. A red `cargo test` or `dotnet test` reported as `needs_review` is exactly what
>   the review and the loop exist to fix, so the run goes on. The emitted `__REVIEWED` set names these
>   stages. `up()` hands their `summary`/`signals`/`follow_ups` to the downstream reviewers under
>   *Unresolved upstream problems*, and the correctness axis must file each one as a `blocking`
>   finding, even one that also fails on master. The human checkpoint is the loop's exhaustion guard
>   (`at: "<loop name>"`), plus the `pr` gate. `blocked`, `failed` and `ask_user_questions` still halt
>   immediately.
>
> This covers the loop-free pipelines (`audit`, `review`) that the earlier loop-anchored exemption
> structurally could not: with no `loop` to attach to, any rubric dimension could halt one step before
> `verify`/`report`. That mattered because **the pause is not a gate** — `args.approved_gates` and
> `record-resume --approved-gate` cannot reopen it, and resume replays the cached envelope and pauses
> identically. Non-reviewers (analyzer, planner, executor) keep the hard checkpoint outside of a plan
> task's per-task check.
>
> - **A skills downgrade never pauses.** An executor reply capped at `needs_review` only because it did
>   not load its declared skills (`signals.skills_downgraded`) is soft everywhere; the work stands and
>   the missing skills are reported (§9.1).
>
> For correction loops: the source stage referenced by a `type: loop`'s `when:` condition is exempted
> from the immediate harness-gap pause, whether or not the loop body re-produces the referenced output.
> That stage drives the loop condition, and pausing it would strand the run one step before the
> machinery built to consume it. The loop's post-loop exhaustion guard (`did not converge`) is emitted
> only when a body stage does re-produce the output — because a loop with no producer cannot refresh
> the condition, and emitting a guard would pause every iteration instead of allowing the loop to run
> to completion.
>
> The human checkpoint for a correction loop sits on its far side: if the loop exits with its signal
> still true, the run pauses at `at: "<loop name>"` carrying the reviewer's envelope. So
> `at: "correction_loop"` means *the corrections did not converge* — read `envelope.outputs.findings`
> for what is left.

---

## 7. Pipeline anatomy (YAML vocabulary)

Templates live in `templates/*.yaml`, validated against `schema/pipeline.schema.json`
(`version` accepts `4` or `5`; v7 templates declare `version: 5`).

### Top-level keys
| Key | Meaning |
|---|---|
| `version` | `5` for this skill. |
| `id` | Template id (e.g. `dev`). Same ids as v4 → iso-scenario benchmarking. |
| `description` | One-line purpose. |
| `kind` | **Lot T.** `pipeline` (the default when omitted) = runnable on its own via `run init`/`/run-pipeline-v7`. `fragment` = a composition brick meant only for another template's `uses:` — never launched standalone (today: `review`, `dev-discovery`, `knowledge-read`, `knowledge-update`, `dev-tests-csharp-split`, §12). |
| `policy` | **Lot T.** Imperative/prohibitive rules for the pipeline as a whole, injected into **every** stage's prompt under "## Règles non négociables (pipeline)" (`prompt.rs`). Doctrine belongs here, not stuffed into `description:` or a YAML comment. The schema caps it at 10 rules of 300 characters each. See the composition trap in "Composite stages" below before putting `policy:` on a `kind: fragment` template. |
| `inputs` | Map of input name → spec (see below). |
| `settings` | Run-wide settings (see below). |
| `stages` | Ordered list of stage objects. |

### Input spec
```yaml
jira_key: { required: true, kind: string }
track:    { required: true, kind: enum, values: [quick, standard, deep], default: standard, description: "Run depth: quick skips the study and the plan gate, standard does both, deep also gates the plan for human review." }
publish:  { required: false, kind: bool, default: false }
```
`kind` ∈ `string | enum | bool | …`. For `enum`, the driver must `AskUserQuestion` over `values`
(default = recommended) — an input's own `description:` is what the driver shows in that question, so
give one to every input a run might have to ask about. Referenced in stages as `{{ inputs.<name> }}`.

### Settings
| Setting | Meaning |
|---|---|
| `max_correction_iterations` | Cap on the review→fix→re-review loop (typical `2`). |
| `knowledge_graph` | Graphify config: `enabled`, `refresh` (`lazy`/`always`/`never`), `code_only`, `cache_dir`, `include`/`exclude`, `graphify_bin`. **LOC-27:** `graphify_bin` must be a bare program name, resolved on `PATH` only (never the cwd); an explicit path comes only from the user env var `AIDP_GRAPHIFY_BIN`. `cache_dir` must be relative and stay under the workspace. **Non-blocking** — degrades to Grep/Read if absent (§11). |
| `pr_draft` | bool. When true, the `pr` stage opens the PR as a draft (`rtk aidp gh pr-create --draft`); `rtk aidp gh pr-ready` marks it ready later. |
| `on_item_failure` | `pause`\|`continue`, default **`pause`** — the default preserves today's behavior. In `continue`, a failed fan-out shard or plan task no longer stops the stage; unfinished items are named to the merge sub-agent instead of pausing the run. |
| `resolve_policy` | `never`\|`fixed`\|`fixed_and_not_relevant`, default **`fixed_and_not_relevant`**. Used by `pr-comments`: `fix` threads are resolved, `wontfix`/`obsolete` threads are resolved with a reason, `reply_only` threads stay open. Resolution runs `rtk aidp gh thread-resolve` after the push and the reply; a failed reply is never resolved. Applies to CI-autopilot runs too. |
| `budget_floor_tokens` | Token floor that `pool(n, floor)` checks against `bud()` before dispatching a fan-out shard, a plan task, or an adjacent parallel group — below it, the item renders `{status:"cancelled"}` instead of being dispatched (§7.1, §9.2). **No numeric default is fixed by this lot** — it is declared elsewhere; consult that declaration before quoting a number. `bud()` counts **output tokens only** and is measured to undercount real billable cost by a factor of 31–87×, so this floor sits on roughly 1–3% of actual cost. Never present it as a cost measure. |
| `providers` | object | Optional map of role (`analyzer`/`planner`/`executor`/`reviewer`) to provider id, second in the provider resolution order (`docs/providers.md`). Absent: the config default applies. |
| `tool_enforcement` | `strict`\|`off`, default **`off`** — the default preserves today's behavior: every stage's `agentType` is emitted as the bare role, unchanged. In `strict`, `analyzer`/`planner`/`reviewer` stages get a restricted `agentType`; `executor` is never restricted, at any scope (§10). |

### Stage fields
| Field | Type | Meaning |
|---|---|---|
| `name` | string (**required**) | Stage id, unique within the pipeline. **LOC-27:** must match `^[A-Za-z0-9][A-Za-z0-9_.-]{0,63}$` — it becomes a directory name. |
| `description` | string | **Lot T.** Prose telling the sub-agent what this stage does, rendered as-is in its prompt right after the templated "Execute the `<stage>` stage of pipeline `<id>`" line. Also what the driver shows for its own `AskUserQuestion` when a stage needs to ask something. Keeps description, not doctrine — see `policy` for imperative rules. |
| `policy` | string[] | **Lot T.** Imperative/prohibitive rules scoped to this stage, rendered under "## Règles non négociables (stage)" — after the pipeline-level ones, before the rest of the prompt. Capped at 10 rules of 300 characters by the schema. |
| `agent` | string | Which sub-agent runs the stage. Convention: `analyzer` / `planner` / `executor` / `reviewer` (§8) — **not** enum-enforced by the schema. |
| `provider` | string | Optional agent provider id for this stage; wins over `settings.providers.<role>`, the launch override and `providers.default` in `~/.aidp/config.json`. An unknown id is refused. See `docs/providers.md`. |
| `model` | `sonnet`\|`opus`\|`haiku`\|`fable` | Model family for this stage's sub-agent (`opus` = Opus 5.5, `fable` = Fable 5.1). Costed by `cost::tier` against `crates/aidp-core/assets/model-prices.json`, where Opus 5.5 (`opus-5-5`) and Fable (`fable`) have their own rows. **Omitting it does NOT mean "inherit the session model"** — the emitter always writes a `model:` in the compiled script, resolved by `AgentRole::default_model` (`workflow_emit.rs`): `opus` for a `planner`, `sonnet` for every other role. (Corrected in Lot T — this line used to claim the omitted value falls back to the session's own model, which stopped being true the moment the emitter started always resolving one.) |
| `skills` | string[] | Absolute-resolvable SKILL ids the sub-agent loads and follows — **this is how a generic agent is specialized** (§8). **Choice rule:** a skill declared on a stage must carry at least one rule that applies to that stage's deliverable (a Rust-conventions skill on a stage that only writes a plan does not qualify). A procedure skill on its own stage, such as `git-branch-setup`, is fine. A guard test holds a denylist of skill and stage pairs that break the rule. |
| `skills_by` | object | **Lot T.** Per-value refinement of `skills`, keyed by one declared input: `{ input: <name>, map: { <value>: [skill, ...] }, default: [skill, ...] }`. Resolved **at run init**, not at emission: `SkillsBy::resolve` appends the picked bucket (or `default` when the input's value is absent or unmapped) after `skills`, de-duplicating by keeping the **first** occurrence of each skill and otherwise preserving order — order is load-bearing, since `prompt.rs` writes one bullet per skill in that exact order. The resolved list is written straight into `effective-pipeline.yaml`'s `skills:`, and the `skills_by:` key itself does not survive into it. Do not confuse this with `plan_tasks.skills_by_kind` (§7.1) — same-sounding, different mechanism, resolved at **emission** against a task's `kind`, not at init against an input. **Stack auto-detection:** an input named `stack` left at `auto` (the default in `dev`, `dev-composed`, `dev-from-audit`, `gha-fix`, `sonar-fix`, `pr-comments`) is replaced at run init, before `skills_by` reads it, by what `stack::detect` finds in the workspace — `lambda-ts` (`serverless.*` + `package.json` at the root), `csharp` (`*.sln` at the root or `*.csproj` ≤ 2 levels down), `rust` (`Cargo.toml` at the root or one level down), else `generic`, whose bucket is each stage's former multi-stack list. An explicit `--inputs '{"stack":"csharp"}'` wins; a detected value outside the template's `values:` fails the init. |
| `needs` | string[] | Upstream stage dependencies. Stages with **no `needs` between them** become a `parallel()` block (§9). |
| `inputs` | object | Templated map fed to the sub-agent, e.g. `{ context: "{{ stages.discover.outputs.context }}" }`. |
| `outputs` | string[] \| object[] | Declared artifact filenames the sub-agent must produce in its stage dir. |
| `with` | object | Stage-mode params, e.g. planner `{ mode: feature }` (§8). |
| `when` | string\|bool | Conditional execution. Expression over `inputs`/`stages`/`settings`. Supports `in`, `==`, `not`/`and`/`or`, `> < >= <=`, `default()`. |
| `gate` | string\|bool\|object | Human approval point. `true`, or an expression (e.g. `"{{ inputs.track == 'deep' }}"`). Compiles to an `awaiting_gate` return (§6). |
| `scope` | object | Write permissions for `executor` stages (§10). `{ mode: production\|tests\|stage_dir_only\|repo_wide\|custom, allowed/denied/... }`. |
| `knowledge` | bool \| `service`\|`feature`\|`all` | **v7 only.** Write this stage's artefacts to the per-project knowledge base `<vault>/Knowledge/<repo>/` instead of the run folder, and tell the agent to update the existing notes in place. Picks the **layer**: `service` = the transverse notes at the base root (architecture, events, data, domain, operations) — what the service *is*; `feature` = `Knowledge/<repo>/Features/<slug>.md`, **one note per business feature** — how a business capability actually works, the granularity an agent implementing a ticket needs; `all` (and the legacy `true`) = both. A `feature` stage's `stage_dir` is `Features/` itself, so `scope: stage_dir_only` keeps it out of the transverse notes, and `aidp` injects the note contract plus the **pre-computed** create-or-update decision (§10.1). That output becomes an input every later research/planning stage reads first. |
| `isolation` | `worktree` | **v7 only.** Run this stage's sub-agent in an isolated git worktree (collision-free parallel writes). Opt-in; only for parallel mutators (§9). |
| `fan_out` | object | **v7 only.** Shard this stage over opaque labels: `items:` (static) **or** `from:` (an upstream array signal, e.g. `{{ stages.plan.signals.shards }}`), plus `max`, `merge_hint`, and `fold` (bool, default **`true`** — the default preserves today's behavior: an overflow queue folds into the last shard). At `fold: false`, `max` becomes a **concurrency** cap instead of a **sharding** cap, while remaining a hard cap on the number of items. N parallel sub-agents + a merge sub-agent. The *model* decides the split. |
| `plan_tasks` | object | **v7 only.** Compile this stage from an upstream planner's `plan.json` task graph: `from:` (the artifact ref), `max` (concurrency cap, default 4), `kinds` (which task kinds this stage claims), `merge_hint`. *`aidp`* decides the split, from the tasks' declared write sets (§7.1). Mutually exclusive with `fan_out`. |
| `merge_findings` | object | **v7 only.** `{ from: [<stage>, ...], out: <path> }` — injects a contract into this stage's prompt directing it to run `rtk aidp findings merge` itself (§9.2) before writing its own `findings.json`/`summary.md`, rather than hand-aggregating four dimensions' worth of findings. Absent ⇒ no such contract is injected (today's behavior). Declared today only on `templates/review.yaml`'s synthesis stage. |
| `on_harness_gap` | `pause`\|`continue` | **v7 only.** Default **`continue`** — the default preserves today's behavior (no new pause point). When a stage's `signals.unevaluated_checks > 0`, `pause` compiles the ordinary paused-stage checkpoint (§6) instead of letting the run proceed past a control nobody could actually run; `signals.has_harness_gap` is a diagnostic/display field only. Set to `pause` only on `templates/review.yaml`'s synthesis stage. That fragment takes an optional `tests_evidence` input (default empty) that a composing pipeline sets to say how the tests check is judged when its reviewers cannot run the tests (`pr-review` points it at the PR's CI). |
| `tools` | object | **v7 only.** `{ allow: [...], deny: [...] }` — an explicit tool allowlist/denylist that overrides the `toolset.rs` matrix (§10) for this stage outright, regardless of `settings.tool_enforcement`. Absent ⇒ the matrix decides as usual. |
| `type` | `loop`\|`pipeline` | Composite stage (see below). |

### 7.1 Plan-driven stages (`plan_tasks:`) — the plan compiles the workflow

A stage carrying `plan_tasks:` describes **no work of its own**. Its shape comes from the planner's
`plan.json` (`schema/plan.schema.json`, `aidp-plan.v1`): *one object per task to realize*, each with its
own `prompt`/`instructions`, its `needs` (real data dependencies) and its **`files`** — the task's write
set. `rtk aidp workflow emit` reads that graph and compiles the stage:

```yaml
  - name: plan
    agent: planner
    outputs: [plan.json, plan.md]          # plan.json = machine contract, plan.md = narrative
  - name: implement
    agent: executor                        # default role/model for every task
    needs: [plan]
    scope: { mode: repo_wide }             # tasks cover production code AND tests
    plan_tasks:
      from: "{{ stages.plan.outputs.plan }}"
      max: 4                               # concurrency cap (never folds tasks together)
      # kinds: [code, infra]               # optional: split the plan across two stages
      merge_hint: "Build, run the full suite once, …"
    outputs: [changed-files.json]
```

What `aidp` (not the model) decides:

| Decision | Rule |
|---|---|
| Ordering | Declared `needs` become edges. **Any two otherwise-concurrent tasks whose `files` intersect get an extra edge in plan order** — a shared working tree can never be raced. Each insertion is recorded in `plan-schedule.json` / run-state and `log()`ged with the offending file. |
| Parallelism | A task starts as soon as *its own* dependencies resolve (**no wave barrier**), bounded by `max` and by the graph's width. `waves` are reported for humans only. |
| Shared files | The plan's `shared_files` belong to **no** task: each task describes the change it needs in `follow_ups`, and the merge sub-agent applies them all once. |
| Merge | With ≥2 tasks, a final merge sub-agent (the stage's own `agent`/`model`) applies the deferred shared-file work, builds, runs the suite, and produces the stage's declared outputs + envelope. **One task short-circuits the merge** — the task itself owns the stage's outputs, so a single-task plan costs exactly what a plain stage costs. A task's own `needs_review` never skips the merge (§6) — only `blocked`/`failed`/`ask_user_questions` do; the merge agent sees every task's envelope and decides whether the stage still needs a human. |
| Validation | Unknown `needs`, duplicate ids, cycles, a non-JSON plan, an unknown `kind`: `emit` **fails loudly**, naming the stage and the fix. The plan is machine input — a malformed one means re-running the planner. |

**`mutex_after` vs `deps` — an inserted ordering edge is not a dependency.** The write-conflict edge in
the Ordering row above is exposed on `ScheduledTask`, `TaskState` and `ScheduleState` as `mutex_after`,
a field distinct from `deps`. Scheduling itself is unchanged by this split — waves and topological
order still fold both kinds of edge internally, so parallelism and ordering are exactly what they were
before. What changes is **failure propagation**: a real `deps` edge (a declared `needs`) still cancels
a successor when its predecessor fails; a `mutex_after` edge (only a shared-file lock) no longer does.
A task whose sole predecessor relationship is a mutex edge now runs even when that predecessor failed —
with a "File lock — predecessor failed" warning injected into its prompt, telling it to check the
shared files' state before editing them, since the predecessor may have left them half-written.

**Two-pass compilation.** The plan does not exist when the run is first compiled, so:

1. pass 1 — `emit` stops at the stage; the script returns `{ status: "awaiting_plan", at, producer, plan_path }` and **nothing after it is compiled**;
2. pass 2 — after the planner ran, `emit` again → the tasks and the rest of the pipeline. Resume with
   `resumeFromRunId`: every `agent()` call before the stage is unchanged, so the prefix replays from
   cache and only the new tail runs.

The contract itself (the JSON shape and the five rules that make a plan executable) is **injected by the
emitter into the producer's prompt** — templates and personas never restate it, so it cannot drift.
`plan_tasks:` is rejected inside a loop body (a two-pass stage cannot re-compile per iteration).

**Native execution (gateway daemon).** In native mode the daemon schedules the tasks itself:

- Tasks with disjoint write sets run in parallel, the others in plan order. The cap is
  `min(plan_tasks.max, settings.max_parallel)`; the default 3 applies when neither is set.
- Each task is checked against its own `files`, by per-task git status plus content hash. An
  out-of-scope write is restored and the task fails. `shared_files` are written only by the merge.
- Two concurrent tasks that write the same file both fail.
- `on_item_failure: pause` stops launching tasks and waits for the running ones. `continue` lets the
  merge see every task state.
- Sessions of one run share the run worktree through the optional `StartRequest` field
  `shared_writer_group`; sessions of other runs stay serialized per workspace.
- After a daemon crash, running rows go through recovery. A resume reruns every row that is not `Done`.

Per-task envelopes are recorded under `results["<stage>#<task_id>"]`; `rtk aidp run reconcile` folds them into
`run-state.plan_schedules[<stage>].tasks[]`, and `rtk aidp run state` prints the task table.

### Composite stages
- **`type: loop`** — a correction loop. Fields: `when` (entry condition, e.g.
  `"{{ stages.review.outputs.findings.has_blocking_findings }}"`), `max_iterations`, and `body:` (a
  list of inner stages). Compiles to a JS `while` driven by the loop signal.
- **`type: pipeline`** + **`uses: <id|path>`** — inline another pipeline as one stage
  (composition/reuse). Child inputs fed via `with:`; child outputs re-exposed via
  `outputs: [{ name: report, from: report.audit-report }]`. Inner stages are namespaced
  (e.g. `qa__explore`). See `templates/dev-composed.yaml`. **LOC-48:** its entry stage forces its
  own Workflow pass (`workflow_emit`'s `awaiting_composite`) only if crossing it without stopping
  would push the current pass's accumulated stage count over `settings.max_stages_per_pass`
  (default 10) — a composite small enough to fit is merged straight into the surrounding pass
  instead. See SKILL.md's "Composite stages" section for the full contract.

**Composition trap (verified, Lot T): pipeline-level `policy:` does not survive `uses:`.**
`compose::expand` builds `out` as `pipe.clone()` — the **parent's own** top-level fields (`id`, `kind`,
`policy`, `description`, `inputs`, `settings`) pass through untouched, and only `out.stages` is replaced
by the flattened stage list. `expand_inner` recurses into a `uses:`-referenced child only to pull its
**stages** (`child_flat`, namespaced and inlined) — it never reads the child `Pipeline` value's own
top-level `policy`/`kind`/`description` at all, so a fragment's pipeline-level `policy:` is silently
discarded the instant something composes it. A template meant to be pulled in via `uses:` (any `kind:
fragment`, e.g. `review` or `dev-discovery`) must therefore put its non-negotiable rules on the
**stage's** `policy:`, which IS namespaced and inlined with the rest of the stage — never on the
fragment's own top-level `policy:`.

---

## 8. The four generic sub-agents

All four are **generic**; their behavior is set by the `skills` list and stage params. All emit the
**`agent-reply.v4` envelope** (§9.1). All call `AskUserQuestion` directly when blocked and log it in
`ask_user_questions[]`.

| Agent | role | default scope | Does | Does NOT |
|---|---|---|---|---|
| **analyzer** | research | `stage_dir_only` | Reads code/docs/tickets, explores, synthesizes. | Write code, create tickets, push, produce final user artifacts. |
| **planner** | research | `stage_dir_only` | Produces ordered, testable plans / decompositions. | Implement the plan; write outside stage dir. |
| **executor** | produce | `production` | **The only agent that changes the world** — code, tests, tickets, Confluence, PRs, Teams, releases. | Review its own work; write outside `scope`; use MCP when a CLI exists; inline secrets/PII. |
| **reviewer** | review | `stage_dir_only` | Audits an artifact → structured `findings.json` (+ `summary.md`). | Apply fixes; pad findings; re-review unchanged code. |

**Run artifact layout (v7 — the Obsidian vault).** Everything a pipeline *produces* is written to a
vault, not to the target repo:

```
<vault>/Pipelines/<repo>/<feature>/<run_id>/          one run
<vault>/Pipelines/<repo>/<feature>/<stage>/           shared research (ticket root)
<vault>/Knowledge/<repo>/                             durable project knowledge — transverse layer
<vault>/Knowledge/<repo>/Features/<slug>.md           durable project knowledge — feature layer
```

Artefacts land in one of **four** scopes, widest first:

| Scope | Path | Declared by | Holds |
|---|---|---|---|
| project (transverse) | `Knowledge/<repo>/` (the base root, no per-stage subfolder) | `knowledge: service` (or `true`) | what stays true about the *service*: architecture, events in/out, data stores, domain vocabulary, operations |
| project (feature) | `Knowledge/<repo>/Features/<slug>.md` | `knowledge: feature` (or `true`) | one note per **business feature**: its rules and thresholds, its flow, the files carrying it, its edge cases and invariants |
| ticket | `Pipelines/<repo>/<feature>/<stage>/` | an `analyzer` stage or a discover/study/explore/research name | research about one ticket, reused by every run of it |
| run | `Pipelines/<repo>/<feature>/<run_id>/<stage>/` | the default | this run's own output |

**Why two project layers.** The transverse layer is read cold and must stay small; a business feature
needs the opposite — every rule, threshold and file path, in detail. Folded into one `domain.md` those
two goals fight, and the transverse note loses: it either stays vague or grows into a dump nobody
reads. Split, an agent implementing a ticket opens **one** feature note and gets the closest thing the
base holds to a spec for its work.

The knowledge base is also an **input**: every research and planning stage's prompt lists the
transverse notes, lists the feature notes *with their names and aliases*, and names the one feature
note matching the current run. A `knowledge:` stage is told to **update those notes in place** — never
to add a parallel document, and never to write run- or ticket-specific narrative there.

Reusable sub-pipelines close the loop, composed with `type: pipeline` / `uses:`:

| Template | Position | Does |
|---|---|---|
| `knowledge-init` | **standalone pipeline**, once per service | bootstraps a base from nothing: 6 parallel read-only scans (structure ‖ events ‖ data ‖ domain ‖ operations ‖ business features) → gated `write_knowledge` (transverse, `knowledge: service`) → `write_features` (`knowledge: feature`, `fan_out` one sub-agent per feature) → `verify` audits every claim against the code → `correct` applies it (`knowledge: true`, both layers) |
| `knowledge-read` | first stage of discovery | distils the base into `knowledge_context.md` for this run — starting with the feature note of the work at hand — ending with what the base does **not** answer, which is the question list the other discovery stages must close |
| `knowledge-update` | last stage of discovery | **two** stages: `knowledge_update` (`knowledge: service`) folds service-level findings into the transverse notes, then `knowledge_feature_update` (`knowledge: feature`) creates or updates the note of the feature the run worked on. Both `scope: stage_dir_only` ⇒ each can write its own layer and nothing else |

`knowledge-read` / `knowledge-update` are already wired into `dev-discovery` (hence every `dev-*`
pipeline), `study`, `tech-doc` and `func-doc`. `knowledge-init` is run by hand on a service that has
no base yet — `/run-pipeline-v7 knowledge-init .` — and is safe to re-run: it reads the existing notes
first and updates them in place. It declares `feature: { default: knowledge-init }` because it has no
ticket; `run::init` honours a template's declared `feature` default so such a run gets its own folder
instead of the shared `_no-ticket` bucket.
`knowledge-update` declares **no outputs** on purpose: its product is the updated base, and a report
file would be run residue sitting permanently in it. What changed goes in the agent summary.

#### 10.1 Create-or-update: resolved by `aidp`, not by the agent

A feature note is only useful if a run reliably finds the *existing* note for a feature it modifies.
Instructed in prose to do that, an agent forks the base into `auto-exclusion.md`, `autoexclusion.md`,
`auto-exclusion-v2.md` — and a forked base is worse than no base. So the decision is a computation:

```bash
rtk aidp knowledge resolve --name "Auto-exclusion temporaire" --name SQIPI-1234
```

Each existing note is scored against each query — exact name/alias/slug → `1.00`, a Jira key listed in
the note's `tickets:` → `0.95`, otherwise word overlap (Dice, plus containment for multi-word queries),
with accents folded and stopwords dropped. The verdict is `update` (≥ 0.78, with the file to edit),
`ambiguous` (≥ 0.42, with the candidates to read), `create` (with the exact path to write, named
after the feature and never after a ticket), or `supersede` — the best-matching note is itself
superseded, so its score is capped at `0.50` (still a candidate, never an update target) and the
target is the note named by that note's `superseded_by`. Every `knowledge: feature` stage receives that verdict
**already computed** in its prompt, derived from the run's own `feature` / `jira_keys` / `topic`
inputs — so the agent is told the filename rather than choosing it.

One caveat is reported explicitly: when every query was a bare ticket key, the result carries
`weak: true`, because "no note lists SQIPI-1234" is true of every ticket on its first run and is *not*
evidence the feature is new. The instruction then tells the agent to re-resolve with the business name
it read from the ticket, and to obey that second verdict.

Resolution reads the notes' frontmatter, so `aliases:` and `tickets:` are what keep it accurate:

```yaml
---
aidp: knowledge-feature
feature: Auto-exclusion temporaire du joueur
slug: auto-exclusion-temporaire        # identical to the filename stem
aliases: [self-exclusion, timeout joueur]
area: Responsible gaming
status: active
tickets: [SQIPI-1234, SQIPI-1300]
files: [src/SelfExclusion/SelfExclusionService.cs, src/SelfExclusion/SelfExclusionRepository.cs]
updated: 2026-08-27
tags: [aidp/knowledge-feature]
---
```

A note with no frontmatter at all still resolves, on its filename and H1 — the base must stay editable
with a plain text editor. Other commands: `rtk aidp knowledge list` (both layers, as JSON),
`rtk aidp knowledge path`, `rtk aidp knowledge index` (regenerate `_<repo>.md` / `Features/_Features.md` /
`_Knowledge.md` after a hand edit; `rtk aidp vault reindex` does it too). Inside a stage none of them need
a flag: `$AIDP_RUN` is exported by the prompt and locates the run's own base.

`<repo>` is the git `origin` remote's repository name (falling back to the workspace directory name),
so two checkouts of one repo group together. `<feature>` is the `feature` input, else the ticket list,
else the single `target`/`jira_key`, else `_no-ticket` — the same value that names the `feat/<feature>`
branch, so every run for one feature shares a root and a branch. Most stages write into their per-run
stage dir; **research stages** (discovery/study — any `analyzer` stage, or a
`discover`/`study`/`explore`/`research` name) instead persist at the **ticket root**, shared across
runs: their prompt tells them to read and reuse prior research before redoing it. Downstream
`needs`/`{{ stages.*.outputs.* }}` references resolve to whichever dir the producing stage actually
wrote to, so refs stay correct.

**Vault resolution** (`crate::vault::resolve`), first hit wins: `--vault <path>` → `AIDP_VAULT`
(`off`/`none`/`0` disables) → `~/.aidp/config.json` `{"vault": …}` → auto-detection (nearest directory
holding `.obsidian/`, testing each ancestor *and its immediate children*, so a vault sitting beside the
repos is found; ties prefer one named `AIDP` and are reported in `ambiguity`). No hit ⇒ the legacy
`<workspace>/.aidp/pipelines/<feature>/<run_id>/` layout, byte-for-byte unchanged. The resolved root is
persisted in `run-state.json#/vault_root` and never re-resolved for that run.

**Generated notes.** `run::save` — the single funnel for every state mutation — calls
`obsidian::refresh`, which rewrites (only when the bytes changed) a dashboard, a repo MOC, a feature
MOC, a run note and one note per stage. Every generated note is `_<folder-name>.md`: the `_` prefix
sorts it first and guarantees it can never collide with a declared output (templates declare `plan.md`
for a stage named `plan`). Links are **vault-absolute** wikilinks
(`[[Pipelines/repo/F/run/plan/_plan|plan]]`) because stage folder names repeat across runs. Sub-agents
are told these conventions in their prompt and are forbidden from writing any `_`-prefixed file.

**Nothing aidp writes stays in the repo** — not even the per-repo state that belongs to no single
run. The CI autopilot's marker and dedup ledger live in `<vault>/Pipelines/<repo>/.state/`
(`run-in-flight`, `ci-autopilot.state.json`), dot-prefixed so Obsidian and the note generators both
look past them. An older binary's copy under `<repo>/.aidp/` is moved there on first touch, and the
folder is deleted once nothing of ours is left in it.

**What stays in the repo is only what you put there**, which aidp reads and never creates:
`.aidp/dev-target.json` and `.aidp/sonar.json` (connection config), `.aidp/ci-autopilot.json`
(per-repo autopilot config, written only by an explicit `rtk aidp ci config --save`) and
`.aidp/pipeline/flow/` (project-local templates). Those are inputs, not output. Without a vault the
run is in legacy mode altogether and the state falls back to `.aidp/` — there is nowhere else for it
to go. Pre-v7 runs stay in `.aidp/pipelines/` and are not migrated; v7 no longer has a load/resume
path for them.

### planner modes (`with.mode`)
`feature` (requirements+study → impl plan) · `correction` (reviewer findings → remediation plan) ·
`architectural_brief` (high-level design before feature planning) · `decomposition` (epic/PRD → stories).

### executor scope modes
`production` (app source, excludes tests/docs) · `tests` (tests + fixtures only) ·
`stage_dir_only` (artifacts that don't touch the repo: docs/tickets/notifications) ·
`repo_wide` (rare; explicit allowlist) · `custom` (explicit `allowed:` globs).

### Specialization-via-skills (executor examples)
| Skills loaded | Agent becomes |
|---|---|
| `dotnet-engineering`, `aws-serverless` | a .NET / Lambda developer |
| `git-push`, `writing-clearly-and-concisely` | a PR opener |
| `create-ticket`, `ticket-decomposition`, `writing-clearly-and-concisely` | a Jira author |
| `confluence-microservices`, `event-architecture` | a Confluence publisher |
| `teams-pr-notification` | a Teams poster |
| `generating-release-message` | a release author |

> Sub-agents prefer `aidp` subcommands for external systems (`rtk aidp gh pr-create`, `rtk aidp jira issue
> create`, `rtk aidp confluence page create`, `rtk aidp teams notify`); MCP is a fallback only. `rtk aidp jira`
> builds an authenticated request and now sends that same request instead of discarding its
> headers, so this recommendation holds against Jira Cloud; it also offers the read verbs
> `issue-search`, `transitions-list` and `issue-comment`.

---

## 9. Data contracts (schemas)

All in `schema/`. The Workflow `agent({schema})` call validates each reply at the tool-call layer — a
malformed reply triggers an automatic retry, **not** brittle text parsing. The schema **names** (e.g.
`agent-reply.v4`) are shared with v4 for envelope compatibility, but v7 carries its own copies.

### 9.1 Sub-agent reply envelope — `agent-reply.v4.schema.json`
Every sub-agent returns this object:
```jsonc
{
  "status": "completed | blocked | needs_review | failed",   // required
  "summary": "one-paragraph plain text (≤1200 chars). NO artifact bodies inlined.", // required
  "outputs": { "<declared-name>": "<ABSOLUTE PATH or string ID>" },  // name → string ONLY
  "follow_ups": ["..."],
  "ask_user_questions": [{ "id": "...", "question": "...", "options": ["..."], "recommended": "...", "answer": "..." }],  // options, recommended and answer are optional
  "assumptions": [{ "choice": "...", "reason": "...", "rejected": "...", "question_id": "...", "question": "..." }],
  "scope_violations": ["path"],  // self-declared by the sub-agent — nothing verifies this one
  "skills_loaded": [{ "name": "...", "applied_rule": "..." }],  // required when the stage declares skills
  "metrics": { "tool_calls": 0, "duration_ms": 0, "tokens_used": 0 }
}
```
> **Critical executor rule:** `outputs` values are **strings only** — an absolute file path
> (e.g. `"/abs/changed-files.json"`) or an external ID (`"pr_url": "https://…"`). **Never** arrays,
> objects, or inline content. To convey a list, write a JSON file and point `outputs.<name>` at it.

> **`skills_loaded` (LOC-52):** a stage declaring `skills:` gets a prompt section ordering one
> `Skill("<name>")` call per skill as its first tool calls (a full `Read` of the listed SKILL.md is the
> fallback), and a reply schema (`REPLY_SKILLS` / `REPLY_REVIEWER_SKILLS`) requiring `skills_loaded`.
> The emitted `safeAgent` then checks every declared skill is named with a non-empty `applied_rule`.
> **LOC-65:** a read-only role (analyzer, planner, reviewer) missing one first gets one re-dispatch with
> a reminder, then becomes a `failed` envelope (`signals.skills_not_loaded`) — an ordinary hard pause
> (§6). An executor is never re-dispatched (`skillsRetry: false`), since it may already have pushed,
> published or created tickets, and its reply is **kept**: a `completed` reply is capped at
> `needs_review` with `signals.skills_not_loaded` (the missing names) and `signals.skills_downgraded`;
> a `needs_review` reply keeps its status and gains `skills_not_loaded`. An original `failed` or
> `blocked` reply is untouched. That downgrade alone never pauses the run: `isPause` is soft for it in
> plan tasks, reviewers, loop-repaired stages and plain sequential stages alike. The merge of a
> `plan_tasks` stage and the downstream reviewers see the signal through `taskin()` / `up()`, so a
> review may file a finding. `rtk aidp run reconcile` stores the list per stage in `run-state.json`
> (`skills_not_loaded`) and `rtk aidp run summary` prints it as a warning. `dispatch()`'s
> `max_stage_retries` never retries a skills failure either. A plan task is held only to the skills its `skills_by_kind` left in its prompt. Upstream,
> `rtk aidp validate` exits 1 on any declared skill `skills::resolve` cannot find (`skills`, every
> `skills_by` bucket, every `skills_by_kind` list), naming the stage and the skill; with no skill root
> at all (a hermetic HOME, a CI runner) it only warns.

> **Native autonomy:** in an autonomous native run, a reply may carry `assumptions[]` (choice, reason,
> rejected alternative, optional `question_id` and `question` for auto-answered questions) and, for
> `gha-fix`, `sonar-fix` and `pr-comments`, `signals.escalations` (`{id, decision, reason}`). `run-state.json` stores `autonomous` and the aggregated `assumptions`. A stage blocked
> twice fails with reason `blocked-twice`. Workflow mode is unchanged. See `docs/native-execution.md`.

> **Note on `scope_violations`:** this envelope field is self-reported by the sub-agent, unverified —
> no hook has ever checked it. A second, independently-computed `scope_violations` also lives in
> `run-state.json` (§10), written by `rtk aidp run reconcile` from an actual git diff. The two are unrelated
> — different producer, different granularity — don't conflate them.

### 9.2 Artifact schemas (quick reference)
| Artifact | Schema | Produced by | Key fields |
|---|---|---|---|
| `plan.json` | `plan.schema.json` (`aidp-plan.v1`) | planner (stage declaring it) | The **executable plan** §7.1: `tasks[]{id, title, kind code\|tests\|docs\|infra\|chore, prompt, instructions[], needs[], **files[]** (write set), reads[], verification, acceptance[], jira_keys[], risk?}` (the role/model/skills come from the consuming stage, never from a task), plus `summary`, `shared_files[]` (task-forbidden, merge-owned), `risks[]`, `open_questions[]`. `rtk aidp workflow emit` schedules it; a violation fails the compilation. |
| `findings.json` | `findings.schema.json` | reviewer | `has_blocking_findings`, `severity_counts{blocking,major,minor,info}`, `findings[]{id `^F-…`, severity, category, file?, line?, title, suggestion?}`, `checks[]{id `^C-…`, name, status: pass\|fail\|skip, harness_gap?, evidence?, finding_ids[]}`. |
| `verify.json` | `verify.schema.json` | reviewer (`verify-review`) | Verdict per previous finding plus the findings new in this pass: `previous[]{finding_id, verdict, thread_id?}` where `verdict` is `fixed` or `reopen`, and `new_findings[]` (same shape as `findings[]`). The workflow posts `new_findings` with `review-post` and reopens the `reopen` threads with `thread-reopen`. |
| `changed-files.json` | `changed-files.schema.json` | executor (code/tests) | `plan_file`, `changes[]{file, action created\|modified\|deleted, summary}`, `new_dependencies`, `deferred_test_work`, `build_status`, `lint_status`. |
| `options.json` | `options.schema.json` | analyzer (study) | `options[]{id, title, pros, cons, risks, fit_score, trade_offs, sources}`, `criteria[]`, `recommended_option_id`. |
| `promotion-report.json` | `promotion-report.schema.json` | `operator` stage † | `promotions[]{id `^P-…`, kind adr\|prd\|…, candidate_path, target_path, action promote\|skip\|edit, human_decision}`. Agent proposes; human decides. |
| `requirements.functional-only.json` | `requirements.functional-only.schema.json` | analyzer | `summary`, `user_story?`, `acceptance_criteria[]{id `^AC-…`, statement}` — **no tech keywords** (those belong to the architectural brief). |
| `run-manifest.json` | `run-manifest.schema.json` | executor (`build_test_kit`) / planner (`ensure_manifest`) | Machine-readable dev-test contract: `scenarios[]{id `^SC-…`, steps[]{order, phase setup\|trigger\|verify\|cleanup, kind http\|mongo\|sqs, artifact, expect}}`, `kit_dir`. |
| `test-run-result.json` (`results/SC-x.json`) | `test-run-result.schema.json` | executor (`run_scenarios`) | Per-scenario dev run: `status pass\|fail\|error`, `steps[]{kind, phase, observed, expected, status, evidence}`. |
| `test-report.json` / `results.json` | `test-report.schema.json` | reviewer (`evaluate`) | Aggregate verdict: `totals{total,passed,failed,error}`, `has_blocking_findings` (true if any scenario fail/error), `scenarios[]{scenario_id, status, failed_steps[]}`. |
| `dev-target.json` | `dev-target.schema.json` | user (one-time) | Non-secret dev connection config at `.aidp/dev-target.json`: `http.base_url`, `mongo.uri_env`, `sqs.queues`, `deploy.workflow`. Secrets in `AIDP_DEV_*` env. |
| run state | `run-state.schema.json` | `aidp` | Canonical run snapshot — matches the `RunState` struct exactly (pinned by a round-trip test): `run_id`, `pipeline_id`, `run_dir`, `plan[]` (topo layers), `stages[]{name, status, started_at, finished_at, duration_ms, tokens_used, stage_dir, outputs, usage{input, output, cache_creation, cache_read, model, agent_type, pinned_model, complexity_bucket, cost_usd, pricing_version, tool_calls, source: "jsonl"\|"budget"\|"unavailable"}}`, `loops{}`, `plan_schedules{<stage>: {waves[][], max_parallel, serializations[]{before,after,files[]}, warnings[], tasks[]{id,kind,wave,deps[],files[],status,tokens_used}}}` (how `aidp` parallelised each plan-driven stage), optional `knowledge_graph{status fresh\|reused\|skipped\|failed}`, optional `skills_not_loaded` per stage (LOC-65: declared skills an executor did not load), optional `init_warnings` (LOC-33: the
`warnings` list from `run start`/`run init`, persisted so a later `run state`/`summary` can still show
what was flagged at init time), top-level `last_workflow_status` (the raw status string of the last Workflow result folded in — `"done"`, `"paused"`, `"awaiting_gate"`, …), top-level aggregated `cost{total_usd, pricing_version, ...}` (see `RunCost`). Summaries derive from it. `usage.source` names where the counters came from — a number without a source is untrustworthy, and a silent zero is never emitted. `usage`, `cost` and `last_workflow_status` are all Lot-1 additions, `#[serde(default, skip_serializing_if = "Option::is_none")]` on every one — a `run-state.json` written before Lot 1 simply lacks them, and `pipeline-resume-v7` reads such a file exactly as before. |

A finding may carry an optional `location` (free text, such as `src/a.rs:12` or a symbol) for findings
that sit outside the PR diff. `review-post` prints it in the review body, since GitHub accepts inline
comments only on diff lines.

Severity ladder (reviewer): `blocking` (must fix before merge) · `major` (should fix; non-blocking only
with explicit override) · `minor` (improvement) · `info` (stylistic). These four are the only
schema-valid `severity` enum values. (`reviewer.md` prose also uses "nit" informally for the lowest
tier, but `nit` is **not** a valid enum value — emit `info`.)

`checks[].status` is **three-way, not binary**, and the states are not interchangeable: `pass` means
the check actually ran and came back green; `fail` means it ran and found something (`finding_ids`
must be non-empty); `skip` means the reviewer could not run the check at all, and `harness_gap` must
then be a non-null string explaining why. A check a reviewer did not run is always `skip` — never
`pass`. `rtk aidp findings merge` (`findings.rs`, called by a `merge_findings:` stage, §7) recomputes
`severity_counts` from `findings[]` instead of trusting a merged summary, and derives
`has_blocking_findings = severity_counts.blocking > 0` itself. The reviewer envelope schema now
requires `signals.unevaluated_checks` alongside `signals.has_blocking_findings`, and accepts an
optional `signals.has_harness_gap`.

> † `operator` is a specialised executor-type stage (`with.operation: promotion`) named by the promotion
> schema; it is **not** one of the four generic sub-agents in §8. It only proposes promotions — the
> human decides via `AskUserQuestion`.

---

## 10. Scope enforcement & hooks

Scope is not enforced live — no hook blocks an out-of-scope `Edit`/`Write` while a stage runs.
`hooks/settings.example.json` (merge into `~/.claude/settings.json` via `rtk aidp setup merge-hooks`, done
by `/pipeline-setup-v7`) ships a single hook:

| Hook | Matcher | Effect |
|---|---|---|
| **Stop** | — | Writes the run summary. |

Two earlier guard hooks — one blocking the main orchestrator's own edits, one checking each sub-agent
write against its stage's scope as it happened — were removed for good: both were gated on
`AIDP_RUN`/`AIDP_STAGE` being non-empty, but those variables are only ever written into a sub-agent's
**prompt text**, never into the hook's process environment, so the guard condition could never be
satisfied and neither hook ever fired (full history: `SKILL.md`'s `hooks/` entry).

Scope is checked **after the fact**, at reconciliation: `rtk aidp run reconcile` diffs the paths git says
the run actually changed against the declared `scope` of every stage that succeeded, and records the
offenders in `run-state.json` under `scope_violations`. `rtk aidp scope verify --run <id>` replays that same
check on demand and is the command that exits non-zero on a violation — this is **detection, not
prevention**: the out-of-scope file is already written by the time the violation is observed. A stage
run under `isolation: worktree` is inspected separately (its own tree, its own diff); any stage the
verifier could not reach is **named** in the report rather than passed over in silence.

**LOC-27 hardening.** `path_under` normalizes paths lexically (`..`, `.`, separators) before comparing,
so `src/../secrets` cannot pass as `src/`. `production` and `tests` modes are anchored to the workspace
root. An invalid `allowed`/`denied` glob is an error, never silently ignored.

**Other LOC-27 input bounds.** Knowledge slugs are validated by `aidp_core::safe_name::check` (`:` is
refused, as are separators and `..`). A `uses:` direct path must lie under a composition root. Pipeline
and `plan.json` files are capped at 1 MiB; a larger file is refused at load.

If a sub-agent's write lands outside scope, it must **adapt within scope — never bypass** — even though
nothing stops the write as it happens.

### Tool restriction per stage (`toolset.rs`)

A second, independent mechanism — not a replacement for the post-hoc check above, and not enforced
unless turned on. `settings.tool_enforcement: strict|off`, default **`off`**: in `off`, nothing
changes — a stage's `agentType` is emitted as the bare role (`executor`, `reviewer`, …), exactly as
today. In `strict`, `analyzer`, `planner` and `reviewer` stages get a specialized `agentType`
(`aidp-analyzer-ro`, `aidp-planner-ro`, `aidp-reviewer-ro`) carrying an allowlist
`[Read, Grep, Glob, Bash, TodoWrite]` and a denylist `[Edit, Write, MultiEdit, NotebookEdit]`, resolved
from `~/.claude/agents/` — written there by `rtk aidp setup agents [--dest <dir>] [--force]`, which refuses
to overwrite an existing file without `--force` (that registry is shared with the user's other agents).
**`executor` is never restricted, at any scope** — restricting the only agent that changes the world
would break every run. A stage's own `tools: { allow: [...], deny: [...] }` (§7) overrides the matrix
outright.

`rtk aidp doctor`'s `agent_toolsets` check is the entry condition for `strict`: it goes red if a template
can emit an `agentType` whose registry file is missing or carries no `tools:` line, and `rtk aidp workflow
emit` refuses to emit in `strict` while that check is red.

**Say the limit honestly, every time this comes up: `Bash` stays in the read-only allowlist.** The
restriction blocks the *editing tools* — `Edit`, `Write`, `MultiEdit`, `NotebookEdit` — not writing via
a shell command. The real write boundary is still the post-hoc `rtk aidp scope verify` described above,
not this allowlist; do not describe `strict` as preventing an out-of-scope write.

### 10.0 Flow-owned tickets

`dispatcher.launch` is `session` (default) or `flow`. With `flow`, the daemon delivers a ticket through the `ticket-delivery` flow (`docs/flows.md`), and a PR whose ticket has an active flow is never handled by a session or by the CI autopilot. The driver may see the skip reason `owned-by-flow` in `rtk aidp ci dispatch` and in the dispatcher's `lastPlan.skipped`; it is not an error. With `flow` and no flow engine attached, the dispatcher reports `flow-unavailable` instead. A local ticket can be delivered on demand by the `local-delivery` flow (no Jira, no DEV deployment): `POST /api/tickets/:key/flow` with `{"flow": "local-delivery"}`.

### 10.1 CI autopilot hooks (`hooks/ci-events.example.json`)

A **second, independent** hook set. The one above *guards* a running pipeline; this one *starts* one.
Merged the same way (`rtk aidp setup merge-hooks`, idempotent, installed by `/pipeline-setup-v7`).

Claude Code has no "CI failed" event — hooks fire on Claude's lifecycle, not GitHub's. `rtk aidp ci`
bridges that: it probes the PR in flight, fingerprints each problem on
`(kind, repo, pr, head_sha, detail)` so it fires exactly once, and speaks the hook protocol itself, so
`settings.json` holds one-liners and there is no per-OS command variant.

| Hook | Matcher | Effect |
|---|---|---|
| **PostToolUse** | `Bash`, `asyncRewake: true` | After a `rtk git push` / `rtk gh pr create` / `rtk gh run rerun`, polls the checks **in the background** for up to `watch_timeout_seconds` (default 1800) and **wakes the session on exit 2** when the build goes red. Silent, instant no-op for any other Bash call. |
| **Stop** | — | At the end of a turn, exits 2 with the directive if a signal is pending, so the fix run starts unprompted. |
| **UserPromptSubmit** | — | Cache-only (never hits the network); its stdout becomes context, so an un-woken session still knows the PR is red. |

Signal → pipeline: `gha` → `gha-fix`, `sonar` → `sonar-fix`, `comments` → `pr-comments`.
When woken, the driver invokes the **`ci-autopilot`** skill, which reads `rtk aidp ci dispatch` and runs
those pipelines one at a time through the normal v7 protocol (§5). **The autopilot decides whether to
start a run; it never decides whether to push** — every one of those pipelines gates its push/reply
stage.

The dispatch plan (`dispatch_plan` in `aidp-integrations::ci`) also resolves the Jira ticket key from
the PR's own branch (`/pr/head_ref`, e.g. `feat/SQIPI-5694` → `SQIPI-5694`) and adds it to each
`plan[].inputs` as an explicit `feature`; `target` stays the PR number, so `gha-fix` / `sonar-fix` /
`pr-comments` still fix the right PR. `run::feature_key()` prefers that explicit `feature` over
`target`/`jira_key`, so the fix run is filed under `<vault>/Pipelines/<repo>/<TICKET>/<run_id>/`
beside the ticket's own dev runs instead of a PR-numbered bucket. A branch naming no ticket keeps the
PR-number folder, and nothing already on disk moves.

The `rtk aidp ci status` envelope carries a `pr_error` key alongside `checks_error`/`threads_error`/
`sonar_error`, set when `gh` is missing, unauthenticated, or rate-limited — distinct from `skipped`,
which means the PR probe ran and found nothing to act on.

Which PR is probed: the current branch's, else — when that is missing, draft, merged or on an ignored
branch — the caller's own open PRs via `rtk gh pr list --author @me`, plus any the autopilot has recorded
in `state.watched`. Worktrees are the reason: an isolated stage pushes from
`<repo>/.claude/worktrees/<name>`, whose branch stops being checked out the moment the worktree is
removed. State and config are therefore anchored at the **main** worktree
(`rtk git rev-parse --git-common-dir`), not at the cwd. `ci::workspace_root` resolves the repo without
changing the process cwd (`git`/`gh` run with an explicit working directory), which is what makes it
safe inside the daemon. A recovered signal carries `recovered_from` /
`recovered_pr`, and the directive warns that the PR's branch is not checked out — a `fix` stage run on
the wrong tree is the failure mode that matters here.

Loop and collision guards, all four of them:
- `stop_hook_active` from the hook input — a Stop hook never re-enters its own continuation;
- `max_notifications` (default 1) — one unhandled signal wakes the session once, then goes quiet;
- **acked ≠ notified** — being told about a problem does not mark it solved, so `rtk aidp ci dispatch`
  still returns a signal the hook already announced. Only `rtk aidp ci ack` (or a successful push stage)
  retires one;
- `run-in-flight` (in the repo's vault state dir, `<vault>/Pipelines/<repo>/.state/`) — written by
  `rtk aidp workflow emit`, removed by `rtk aidp run reconcile`; while it exists the autopilot will not start
  a second pipeline over the same working tree. Deliberately **not** the old `.aidp/active-run`: that
  marker used to arm the now-removed guard hooks (§10), which would then have blocked the driver's
  own post-run `workflow-result.json` write. A marker older than
  `run_marker_stale_after_seconds` (6h) is reported as stale and ignored, so an abandoned run cannot
  silence the autopilot for good.

Config: `.aidp/ci-autopilot.json` per repo, or `~/.aidp/config.json` → `"ci"` — config is yours, so
it stays in the repo. The repo file still wins for ordinary fields, but **`auto_dispatch` needs the user
config** (LOC-27): only `~/.aidp/config.json` `ci.auto_dispatch: true` enables it, so a cloned repo
cannot start pipelines on its own. State: `<vault>/Pipelines/<repo>/.state/ci-autopilot.state.json` — state is
ours, so it does not.
Off switches: `rtk aidp ci config --enable false --save` (everything) or `--auto-dispatch false` (report,
never start). Sonar needs `SONAR_HOST_URL`/`SONAR_TOKEN`; without them that one signal degrades to
nothing and `rtk aidp ci status` says why under `errors.sonar`.

---

### 10.2 Logging and stderr

Logs go to stderr only, through one subscriber built in `aidp-cli`.

- **Filter:** `RUST_LOG`, then `AIDP_LOG`, default `warn`. `-v`/`-vv`/`-vvv` raise it to `info`/`debug`/`trace`.
- **Format:** JSON lines when stderr is not a terminal (keys `level`, `timestamp`, `target`, `fields`); human format on a terminal.
- **Gateway:** `rtk aidp gateway serve` also writes daily-rolling JSON logs to `<state_dir>/logs/`, where `state_dir` is `$AIDP_GATEWAY_DIR` or `~/.aidp/gateway`. A per-request access log records method, path, status and duration. The path omits the query string except whitelisted params. No token is ever recorded.
- **Spans:** log events carry `run_id`, `ticket_key` and `session_id` in the dispatcher, at session start and in `run reconcile`.
- **Session to run link:** sessions carry a `workflow_run_id` captured from the `run start` JSON, and runs are resolved by it rather than by start-time proximity.
- **Redaction:** webhook URLs, mongo URIs and sensitive response headers are redacted in outputs.

**Arbitration on stderr sharing.** Stdout stays the machine contract: bare `run_id`, bare script path, JSON. Phase JSON stays on stderr and is identified by its `phase` key. Log lines are identified by their `level` key. `warning:` prose lines and phase JSON remain plain `eprintln` output, not logs, so the default output is unchanged. Consumers filter stderr line by line, by key, and never `JSON.parse` it whole.

Rejected alternatives:
- A dedicated file descriptor: not portable, and it changes the driver.
- Phase JSON on stdout behind `--format`: breaks the bare-path contract.

## 11. Knowledge graph (Graphify)

When `settings.knowledge_graph.enabled: true`, `rtk aidp run init` builds/refreshes a workspace graph
once and injects `graph_json` + `graph_report` **absolute paths** into every sub-agent prompt, so
analysis stages query the graph instead of bulk Grep+Read. **Non-blocking:** if the `graphify` CLI is
absent, status becomes `skipped`/`failed` and the run proceeds with Grep/Read fallback. `refresh`:
`lazy` (cache hit when fresh) / `always` / `never`. Setup auto-installs via `pip install graphifyy`
when missing (bootstrap step 5).
**LOC-27:** `graphify_bin` is a bare program name looked up on `PATH` (the cwd is never searched); set
`AIDP_GRAPHIFY_BIN` in your own environment to point at an explicit path. `cache_dir` must be relative
and resolve under the workspace.

**Conditional skill.** `graphify-context` is dropped at compile time from every stage (the prompt's
`Skill(...)` list, the agent options and the expected `skills_loaded`) when the run has no knowledge
graph, so no stage is asked to load a skill that has nothing to query. `rtk aidp workflow emit` prints one
compile warning per stage it was dropped from.

---

## 12. Template catalog

All `version: 5`, ids matching v4 (iso-scenario benchmark). `target` semantics depend on the template.
The park counts **40 discoverable ids** (`rtk aidp pipeline list`, binary rebuilt from this worktree) —
this table plus the "Fragments" and dual-use notes right after it account for every one of them; treat
a catalog entry naming an id `pipeline list` does not return, or an id `pipeline list` returns that no
entry here names, as a bug in the catalog, not in the park.

| id | target / key inputs | Flow (gates **bold**) | Notes |
|---|---|---|---|
| `dev` | `jira_keys[]`, `feature?`, `track` quick\|standard\|deep, `stack` auto\|generic\|rust\|csharp\|lambda-ts (**Lot T**, `auto` since LOC-52) | discover (composed) → **plan** (gate if `deep`, writes `plan.json`) → **implement** (`plan_tasks`: N tasks in parallel + merge) → review (composed) → correction_loop → **pr** | Flagship, **plan-driven** (§7.1): the plan's tasks cover production code AND tests, so there is no separate `tests` stage. **Lot T (R-DUP-1):** `stack` drives `implement`'s `skills_by`; since LOC-52 it defaults to `auto` (detected at run init, see `skills_by` in §7), and `csharp` / `rust` narrow it to their own set — `generic` reproduces today's multi-stack skill set (C#/.NET, Lambda TS, xUnit, Reqnroll) byte for byte, `lambda-ts` narrows it to exactly `templates/dev-lambda-ts.yaml`'s set (`lambda-ts-dev-aidp`, `aws-serverless`, `feature-testing-aidp`) — run with `--inputs '{"stack":"lambda-ts"}'`. `dev-lambda-ts` itself is unchanged and still the template to use when the run should never even offer the C#/.NET path. Needs the extra `awaiting_plan` emit+resume round-trip. |
| `dev-csharp` | as `dev` | discover (composed) → **plan** (gate if `deep`) → **implement** (`plan_tasks`, kinds `code/docs/infra/chore`) → tests (composed: `tests_unit` ‖ `tests_reqnroll` → `tests_suite`) → review (composed) → correction_loop → **pr** | **Plan-driven** (§7.1), C#/.NET. `implement` claims the plan's PRODUCTION kinds only — which is also what the planner *plans*, since the plan contract injected into `plan`'s prompt lists exactly the kinds a `plan_tasks:` stage claims — and test writing is a phase of its own, composed from `dev-tests-csharp-split`: xUnit and Reqnroll in two dedicated stages grouped into one `parallel()` block, then `tests_suite` registers a bootstrapped test project in the .sln, runs the whole `rtk dotnet test` suite once and consolidates changed-files.json. A BDD scenario needs the complete feature wired and building, which a per-task test slice cannot give it — hence a phase after `implement` rather than test tasks inside the plan. `review` needs `tests`, which resolves to the terminal `tests_suite`, so the dimensions read one write set plus test-report.md. The 3 context reads and the 4 review dimensions still each fan out into one `parallel()` block. |
| `dev-lambda-ts` | as `dev` | same | **Plan-driven** (§7.1) with Lambda/TS stack skills; the merge step owns `serverless.yml` entries and shared types. |
| `dev-model-mix` | `jira_keys[]`, `track` | discover → **plan** (gate if `deep`) → **implement** (`plan_tasks`) → review → correction_loop → **pr** (**no** `study`) | **Plan-driven** (§7.1) model mix: `plan` on `opus`, `pr` on `haiku`, tasks on `sonnet`. `id: dev-model-mix` itself dates from an earlier fix (WI-P2-7, resolving a collision with `id: dev`); Lot T (R-ID-1) closed the resulting id/filename mismatch by renaming the FILE from `templates/devPlan.yaml` to `templates/dev-model-mix.yaml` — content untouched, `id:` unchanged, purely a `rtk git mv` so the filename stops lying about the id. |
| `dev-from-audit` | + `audit_report` (path) | as `dev`, audit report threaded into discover/study/plan | **Plan-driven** (§7.1). Implement using a prior audit; tests are tasks of the plan, so the .NET-only `dev-tests-csharp` composition is gone (the merge step still runs `rtk dotnet test`). |
| `dev-from-audit-lambda-ts` | + `audit_report` (path) | as `dev-from-audit` | **Plan-driven** (§7.1) Lambda/TS variant: `implement` carries `lambda-ts-dev-aidp` + `aws-serverless`, and the plan's `tests` tasks replace the inline jest fan-out. |
| `dev-composed` | `jira_keys[]`, `target_path` | plan → **implement** (`plan_tasks`) → qa (`type: pipeline` → `audit`) → **pr** | Demonstrates pipeline composition, now on top of a plan-driven `implement`. |
| `audit` | `target_path` | explore → [dim_correctness ‖ dim_security ‖ dim_perf ‖ dim_maintainability] → verify → **report** | 4 dims run in `parallel()`; adversarial `verify` refutes blocking findings before the gated report. |
| `study` | `topic`, `scope_paths?` | explore → **synthesize** → publish* | `publish` conditional on `inputs.publish` (`when:`, **not** a human gate); `synthesize` is gated. |
| `tech-doc` | `service_path`, `publish` | discover → review → **publish*** | Event-architecture / microservice doc → Confluence. |
| `func-doc` | `feature`, `jira_key?` | gather → write → **review** | User stories / parcours / edge cases. |
| `discovery` | `brief` | gather → **ideate** → stories_optional* | PRD/brief → backlog; tickets optional. |
| `ticket-create` | `source`, `project_key`, `parent_epic?` | analyze → **decompose** → create → review | Epic/PRD → Jira stories. |
| `gha-fix` | `pr?` (target), `feature?` (ticket key, set by the autopilot), `run_id?`, `track`, `stack?` auto\|generic\|rust\|csharp\|lambda-ts (LOC-52, default `auto`: picks the fix/tests language skills) | collect → **plan** (writes `plan.json`) → **fix** (`plan_tasks`: N tasks in parallel + merge) → verify → review → correction_loop → **push_and_watch** | Makes a red GitHub Actions run green. **Plan-driven** (§7.1): each task carries a source change and its tests, so there is no separate `tests` stage; needs the extra `awaiting_plan` emit+resume round-trip. `collect` trims the failing job logs to the real error and classifies by root cause; `plan` separates FLAKY / INFRA / SECRET (which code cannot fix) from real defects and forbids symptom fixes (deleting the test, `continue-on-error`, lowering a threshold); `verify` re-runs the failing command locally; `push_and_watch` waits for the new run's verdict instead of assuming it. Dispatched by the CI autopilot (§10.1); a CI-dispatched run files under the ticket key when the PR's branch names one. |
| `sonar-fix` | `pr?` (target), `feature?` (ticket key, set by the autopilot), `scope` new_code\|gate_only\|all_issues, `track`, `stack?` auto\|generic\|rust\|csharp\|lambda-ts (LOC-52, default `auto`: picks the fix/tests language skills) | collect → **plan** → [fix → tests] → review → correction_loop → **push_and_recheck** | Clears a red SonarQube gate honestly. `collect` reads `rtk aidp sonar report` plus the *rule* behind each issue; `plan` refuses every way of gaming the gate (`NOSONAR`, new exclusions, lowered thresholds, assertion-free tests) and turns a coverage condition into named test behaviours; `review` re-reads the diff for exactly those moves; `push_and_recheck` waits for the re-analysis and reports the real gate. False positives are handed to a human — the pipeline never mutates Sonar state. Dispatched by the CI autopilot (§10.1); a CI-dispatched run files under the ticket key when the PR's branch names one. |
| `pr-comments` | `selection?` (point ids to process; absent means every point), `pr?` (target, else auto-detected from the current branch), `feature?` (ticket key, set by the autopilot), `track`, `stack?` auto\|generic\|rust\|csharp\|lambda-ts (LOC-52, default `auto`: picks the fix/tests language skills) | collect → **plan** (gate, writes `plan.json`) → **fix** (`plan_tasks`: N tasks in parallel + merge) → **commit_and_reply** (gate) | **Plan-driven** (§7.1): one task per group of fixes sharing files, each carrying its tests, so there is no separate `tests` stage; needs the extra `awaiting_plan` emit+resume round-trip. Processes a GitHub PR's review comments end-to-end: classify each thread → plan one fix per comment → apply → commit/push → reply per-thread with the decision taken. Two gates: the plan (before any code moves) and the commit/reply itself (before anything reaches the PR). A CI-dispatched run files under the ticket key when the PR's branch names one. | Thread resolution follows `settings.resolve_policy` (default `fixed_and_not_relevant`, see Settings).
| `pr-review` | `pr` (target), `pass?` (default 1), `track` | collect → review → synthesis, then the workflow posts `new_findings` | Reviews a PR locally and writes `findings.json`. The agents only read; the workflow posts the findings with `rtk aidp gh review-post` (§3). Findings may carry a `location` (§9.2). The reviewers never run the tests: `resolve` writes `ci-status.json` (`rtk aidp gh pr-status`) and the composed `review` gets a `tests_evidence` rule (`with:`), so `C-tests-run` is judged from the PR's CI and left out when the PR has no CI check — `on_harness_gap: pause` then fires only while CI is still running. |
| `verify-review` | `pr`, `pass` (2 or 3), `previous_run` (run id of the prior pass) | load previous findings → verify → synthesis, then the workflow posts and reopens | Re-checks the previous pass's findings against the new diff and writes `verify.json` (§9.2). New findings go out with `rtk aidp gh review-post`, `reopen` threads with `rtk aidp gh thread-reopen`. The loop ends when clean, or after pass 3 with status `escalated`. |
| `test-scenarios` | `ticket_id` | analyze_us → [design_scenarios ‖ identify_test_data] → build_test_kit → write_test_plan | Designs an executable dev test kit (http/mongo/sqs artifacts + `run-manifest.json`). Does **not** run anything. |
| `run-tests-dev` | `ticket_id`, `kit_dir`, `deploy?`, `branch?` | prepare_dev → **deploy_dev*** → ensure_manifest → run_scenarios (fan-out/scenario) → **evaluate** | Executes a kit on **dev** via the `rtk aidp http\|mongo\|sqs` runners + `gh` deploy; emits pass/fail `test-report.md`. |
| `test-us-e2e` | `ticket_id`, `deploy?`, `branch?` | design (`type: pipeline` → `test-scenarios`) → run (`type: pipeline` → `run-tests-dev`) | End-to-end US auto-test: design the kit, then run it on dev. The "test-scenarios finished → tests on dev" chain. |
| `gdpr-anonymisation-test` | `layers?` (local\|dev\|both), `local_real_service?`, `ticket_id?`, `harness_dir?`, `local_scenarios?`, `include_flip_unreachable?`, `dev_env?`, `player_count?`, `with_money?`, `check_datadog?`, `teardown_harness?` | preflight → [charter ‖ local_up*] → [local_run* ‖ local_fixture*] → local_real_scrub* → local_flip_switch* → **dev_fixture*** → dev_anonymize* → verify_saga* → **report** → teardown* | Tests the GDPR anonymisation feature on two layers, adding no test code to any service repo: the `fraud-gdpr-e2e` LocalStack harness (skill `fraud-gdpr-local-e2e` — event contract, real orchestrator handlers/publisher/Flip, 7 simulated services) and a real dev/stage2 player provisioned → closed → anonymised (skill `create-test-user` — the actual saga). With `local_real_service`, one simulator is replaced by the real .NET service and the erasure itself is asserted against the local Mongo seeded by `create-test-user-local` — without a seeded document a real service acks SUCCESS having scrubbed nothing. `dev_fixture` is the single gate that authorises touching a shared environment. |
| `fraud-stack-test` | `ticket_id?`, `service?`, `stack_dir?`, `service_repo?`, `scenarios?`, `change_context?`, `author_scenarios?`, `rebuild?` (auto/always/never), `teardown?` | preflight -> [charter || stack_up] -> author_scenarios* -> run_suite -> **report** -> teardown* | Runs the local Fraud stack's non-regression suite (skill `fraud-stack-local`) against a Fraud microservice running **for real** in Docker with zero external calls - 6 WireMock named after the real services, LocalStack for SNS/SQS/DynamoDB, MongoDB for persistence. Standalone it is the squad's regression net; composed (`uses: fraud-stack-test`) after an implementation stage, `service_repo` makes it **recompile from the working tree**, so it proves an uncommitted change before review. Writes nothing into a service repo - scenarios, mocks and fixtures belong to the stack. Deliberately no `fan_out:`: the scenarios share one stack, one Mongo and one set of WireMock stubs reset between each, so shards would overwrite each other. |
| `dev-csharp-fraud-stack` | as `dev-csharp`, plus `service`, `service_repo`, `stack_dir?`, `author_scenarios?` | discover (composed) -> **plan** (gate if `deep`) -> **implement** (`plan_tasks`) -> local_stack (`type: pipeline` -> `fraud-stack-test`, **gated report**) -> review (composed) -> quality_gate -> correction_loop (replan -> refix -> **retest_stack** -> rereview) -> **pr** | `dev-csharp` with a quality gate: the service is recompiled from the run's working tree and the local suite replayed against it, between implementation and review. The review reads the verdict; `quality_gate` merges review findings and stack results into one signal, and the correction loop fires on either - its `retest_stack` step rebuilds and replays each iteration, so the pipeline fixes the regression it just caught. `service_repo` must be a **WSL** path (`/mnt/c/...`): the docker CLI lives in WSL while the run's workspace is a Windows path, and nothing converts between them. |
| `dev-angular` | `jira_keys[]`, `feature?`, `track` | discover (composed) → **plan** (gate if `deep`) → **implement** (`plan_tasks`, `isolation: worktree` per task) → review (composed) → correction_loop → **pr** | **Plan-driven** (§7.1), Betclic Angular v22 front-end. Components/services AND their Jest tests are tasks of the plan; the merge step owns module/route registrations, shared services and barrel exports. **R-DUP-1** keeps it a template of its own rather than an axis of `dev`: `implement` declares `isolation: worktree` (per-task git worktrees), a structural difference with no `*_by` selector. |
| `dev-lambda-tsgit` | **`jira_keys[]` OR `prompt`** (+ `feature?`, `track`) | discover (composed, dual demand mode) → **plan** (gate if `deep`) → **implement** (`plan_tasks`) → review (composed) → correction_loop → **pr** | **Plan-driven** (§7.1), Lambda TypeScript, dual Jira/prompt demand mode like `dev-csharp` (USER-GUIDE §6 "Jira ou prompt"). **R-DUP-1** keeps it apart from `dev-lambda-ts`: besides the demand-mode input contract itself differing in required-ness, its composed `discover` stage's `with:` carries a `discover.with.prompt` mapping `dev-lambda-ts` does not declare — a residual divergence with no `*_by` selector. |
| `dev-local` | `feature_file` (path to a local `.txt`), `target_path?` (default `.`), `track` | [discover_feature ‖ discover_code] → discover → study* → **plan** (gate if `deep`) → **implement** → review (composed) → correction_loop → summary | Purely local: no Jira, no Confluence, no git, no PR — the feature spec is a local text file, and the run ends on a `summary` stage instead of `pr`. Context-gathering is inline (2-way fan-out over the feature file + code graph), not composed from `dev-discovery`, since there is no Jira/Confluence leg to share with the other `dev-*` templates. |
| `dev-unity` | `issue?`, `prompt?`, `feature?`, `playtest?`, `mark_ready?` (ignored) | prepare → plan → implement → playtest → playtest_fix (fix_playtest → retest, 2 rounds max) → report | Plan (planner + `unity-csharp-dev`, `plan.md`), implementation and draft PR (`unity-issue-implementer`), test in the Unity Editor (`unity-playtester`: Unity MCP + computer use, `references/unity-playtest.md`). Leaves the PR in draft. First of the three pipelines chained by `/run-unity-dev-pipeline` and by the `perso-delivery` flow. |
| `review-unity` | `issue?`, `pr?`, `feature?` | prepare → review → verdict | Unity review (`unity-pr-reviewer`, opus): completeness of the whole issue (CA-n, T-n, manual actions, playtest evidence) then code; one GitHub review — inline comments when changes are needed, the full verification report otherwise. |
| `fix-review-unity` | `issue?`, `pr?`, `feature?`, `playtest?`, `mark_ready?` | prepare → fix → playtest → ready | Fixes the open review threads (`unity-review-fixer`), playtests again (`unity-playtester`), marks the PR ready when nothing blocking is left. Stages return at once when nothing is open. |
| `dev-aidp` | `prompt`, `feature`, `track` | prepare_branch → [read_rust ‖ read_surface ‖ read_docs] → discover → study* → **plan** (gate if `deep`) → **implement** → verify → review → correction_loop → **pr** | Meta: develops `aidp` itself, launched from a checkout of the aidp repository (crates, schemas, test fixtures, docs); it reads this skill at `$AIDP_SKILL_ROOT` and never writes it. Not a Betclic service, so demand is always `prompt` + `feature` (both required — nothing else could name the branch or the vault folder). `verify` runs `rtk cargo fmt --all -- --check` / `rtk cargo clippy` / `rtk cargo test` before review (§13.5). Cargo runs with `CARGO_TARGET_DIR=$HOME/.cargo-dev-aidp` (pipeline `policy:`), so a run never touches the repository's `target/` or the installed `aidp`. |
| `dev-aidp-viewer` | `prompt`, `feature`, `track` | prepare_branch → [read_client ‖ read_server ‖ read_docs] → discover → study* → **plan** (gate if `deep`) → **implement** → verify → review → correction_loop → **pr** | Meta, sibling of `dev-aidp`: develops `aidp-viewer` (React/Tailwind client + thin Express proxy + shared types). One rule shapes every stage: THE VIEWER DISPLAYS, THE DAEMON DECIDES — business rules stay in the Rust daemon. **R-DUP-1** keeps `dev-aidp` / `dev-aidp-viewer` two templates although their stage lists are near-identical clones: their axis of variation is *which repo and stages* each reads and builds (`read_rust`/`read_surface` vs `read_client`/`read_server`), not their content — cloning the shape is accepted here precisely because that axis has no selector to key off. |
| `dev-flow` | `jira_keys[]` or `prompt`, `feature?`, `stack`, `track`, `pr` (`draft`\|`ready`\|`none`, default `draft`), `branch_ready` (default `true`) | [prepare_branch if `branch_ready` is false] → discover (composed) → **plan** (gate if `deep`) → **implement** → tests (one composite chosen by `stack` with `when:`) → review → correction_loop → **push_pr** | Generic dev flow for any supported stack. The test composite is `dev-tests-csharp-split` (csharp), `dev-tests-jest` (lambda-ts), `dev-tests-vitest` (ts-node, angular) or `dev-tests-cargo` (rust). `push_pr` commits, pushes and opens the PR (draft or ready; none skips it), and the PR body carries a Hypothèses section listing the assumptions the run made. A `stack` left out is filled at run init with the stack `rtk aidp project stack` detects in the workspace; `stack: unknown` (given or detected) is refused at run init. |
| `correction-after-test-dev` | `jira_keys[]`, `prompt` (DEV test report then ticket body), `feature?`, `stack`, `track` | discover (composed) → **plan** → **implement** → tests (per `stack`) → review → correction_loop → **push_comment** | Fixes bugs reported by a DEV test run on an existing branch. It never creates a branch and never opens a PR: it pushes to the current branch and comments the existing PR. A `stack` left out is detected at run init like `dev-flow`'s; `stack: unknown` is refused at run init. |
| `test-csharp` | `jira_keys[]`, `feature?`, `track` | discover (composed) → **plan** (gate if `deep`) → tests (`plan_tasks`) → review (composed) → correction_loop → **pr** | Tests-only variant of `dev-csharp`: no production `code` stage — `tests` is the plan's sole deliverable, unit (xUnit) and integration/functional (Reqnroll BDD) tests for an EXISTING feature. Bootstraps a Reqnroll suite from scratch (packages, `reqnroll.json`, `Support/` harness) when the repo has none yet. |
| `study-to-jira` | `topic` | study → **decompose** → review → create_tickets | Étude → tickets Jira: investigates a topic, decomposes the recommendation into Jira stories, reviews the split, then creates the tickets via `rtk aidp jira`. |
| `refacto-pr-lambda-ts` | `pr?` (target), `base_ref?` (default `origin/master`), `include_modernization?`, `mutation_threshold?` (0-100, default 60), `track` | scope_diff → baseline → [scan_smells ‖ scan_conformity ‖ scan_modernization] → **plan** (gate in `standard`/`deep`) → safety_net → refactor (`plan_tasks`) → [verify_health ‖ verify_behavior] → verdict → correction_loop → **push** | Refactors ONLY the code a PR's diff touches, pushed to that PR's own branch (never a new branch, never a new PR). `safety_net` writes characterization tests and proves their mutation sensitivity (Stryker, scoped to the diff's zones) BEFORE `refactor` runs — a zone under `mutation_threshold` is `blocked`, not refactored. Cardinal contract: zero observable behavior change; any drift goes to backlog rather than being "fixed" in place. See USER-GUIDE §6 for the full rationale. |
| `cartography-fraud` | `service`, `repo_path`, `runtime?` csharp\|lambda-ts (default csharp) | [scan_topology ‖ scan_http ‖ scan_data ‖ scan_config ‖ scan_blockers ‖ scan_gaps] → [write_cartography ‖ write_descriptor] → review | Maps everything a Fraud microservice touches OUTSIDE its own process, plus a draft `ServiceDescriptor` for `localstack/fraud-stack`. Read-only against the service repo — every artifact lands in the run folder, and a human copies the reviewed output into `fraud-stack` by hand. No gate: `review` audits every claim against the code and writes `findings.json`, but nothing here writes to the service repo for a gate to protect. |
| `datadog-dashboard-fraud` | `action` create\|update, `dashboard_id?`, `objective`, `dashboard_title?` | discover_existing → plan_widgets → draft_dashboard_json → **review_guardrail** | Squad-Fraud-only Datadog dashboard drafting: produces `dashboard.json` + `apply-guide.md` for a human to apply manually. Carries a pipeline-level **`policy:`** (§7) stating the Datadog MCP calls here are read-only, dry-run only; `review_guardrail` (on `opus` — a false negative here is expensive in prod) blocks any dashboard not tagged `team:fraud` before the gate. |
| `knowledge-init` | `.` (repo root) or a service path | [scan_structure ‖ scan_events ‖ scan_data ‖ scan_domain ‖ scan_ops ‖ scan_features] → **write_knowledge** (gate) → write_features (`fan_out`, one sub-agent per feature) → verify → correct | Bootstraps a service's knowledge base from nothing, run once before any other pipeline touches that service. Full detail (including why it declares `feature: { default: knowledge-init }`) in §10.1's "Reusable sub-pipelines" table — repeated here only so the catalog names every discoverable id. |
| `dev-exemple` | `target`, `inputs` | collect -> plan -> implementation | Minimal example template for native runs (`rtk aidp run exec dev-exemple`); also runnable through the Workflow driver. |

`*` = conditional stage (`when:`). Extend the catalog with `/pipeline-new-v7`.

### Fragments (`kind: fragment`) — composition bricks, never launched alone

Five ids declare `kind: fragment` (§7): `rtk aidp pipeline list` still discovers them (a fragment is a normal
YAML file in `templates/`), but running one directly produces a pipeline whose stages exist only to be
`uses:`-inlined into something else, so `run init --pipeline <id>` on one of these is a mistake, not a
workflow. Reference below is where each is documented in full — not re-derived here.

| id | Composed by (`uses:`, verified via `grep`) | Does | Documented in |
|---|---|---|---|
| `dev-discovery` | `dev`, `dev-angular`, `dev-csharp`, `dev-csharp-fraud-stack`, `dev-lambda-ts`, `dev-lambda-tsgit`, `test-csharp` | Context-gathering: DEMAND (Jira and/or prompt, dual-mode) ‖ Confluence ‖ code graph → synthesize → study* (skipped in `quick`). Extracted from `dev-csharp` so it is a `type: pipeline` composition, not a copy-pasted stage block. `dev-from-audit(-lambda-ts)`, `dev-model-mix`, `dev-composed`, `dev-csharp-short` and `dev-local` each keep their own inline discover stages instead (a genuinely different shape in `dev-local`'s case — no Jira/Confluence leg at all). | §6 "Jira ou prompt", `templates/dev-discovery.yaml` |
| `review` | `dev`, `dev-aidp`, `dev-aidp-viewer`, `dev-angular`, `dev-csharp`, `dev-csharp-fraud-stack`, `dev-from-audit`, `dev-from-audit-lambda-ts`, `dev-lambda-ts`, `dev-lambda-tsgit`, `dev-local`, `test-csharp` | The 4 rubric dimensions (correctness ‖ security ‖ perf ‖ maintainability) in parallel → synthesis → `findings.json` (with `has_blocking_findings`) + `summary.md`. `dev-model-mix` and `dev-composed` do not compose it (the latter's `qa` leg composes `audit` instead); `dev-csharp-short` has no review stage at all. | `templates/review.yaml`, referenced throughout §12 as "review (composed)" |
| `knowledge-read` | `dev-discovery` (hence every `dev-*` that composes it), `study`, `tech-doc`, `func-doc` | First stage of discovery: distils the project knowledge base into `knowledge_context.md`, ending with the question list the rest of discovery must still close. | §10.1 "Reusable sub-pipelines" table |
| `knowledge-update` | same callers as `knowledge-read` | Last stage of discovery: folds the run's findings back into the transverse notes (`knowledge_update`) and the feature note (`knowledge_feature_update`). Declares no outputs on purpose — its product IS the updated base. | §10.1 "Reusable sub-pipelines" table |
| `dev-tests-csharp-split` | `dev-csharp` (after `implement`); any other C#/.NET `dev-*` can compose it the same way | The composable C# test-writing phase: `tests_unit` ‖ `tests_reqnroll` → `tests_suite` (registers the test project in the `.sln`, runs `rtk dotnet test` once, consolidates `changed-files.json`). Superseded `dev-tests-csharp`'s label-based `fan_out:` for new compositions. | "`dev-tests-csharp-split`" prose further below in this section |
| `dev-tests-jest` | `dev-flow`, `correction-after-test-dev` (`stack: lambda-ts`) | One executor stage writes and runs Jest tests, same input and output names as `dev-tests-csharp-split`. | — |
| `dev-tests-vitest` | `dev-flow`, `correction-after-test-dev` (`stack: ts-node`, `angular`) | Same contract with Vitest. | — |
| `dev-tests-cargo` | `dev-flow`, `correction-after-test-dev` (`stack: rust`) | Same contract with `rtk cargo nextest`. | — |

### Dual-use pipelines — discoverable AND composable, no `kind:` needed

`audit`, `fraud-stack-test`, `run-tests-dev` and `test-scenarios` are meant to run BOTH ways: standalone
(they have their own row above, with their own gates and outputs) and inlined via `uses:` into another
pipeline (`dev-composed` → `audit`; `dev-csharp-fraud-stack` → `fraud-stack-test`; `test-us-e2e` →
`test-scenarios` then `run-tests-dev`). `kind: pipeline` already permits both uses — it is the default,
so none of the four declares a `kind:` key at all. `kind: fragment` is reserved for a template that
would be **wrong** to run alone, which is not true of any of these four.

Not in the table, because it is not discoverable: **`templates/legacy/`** is the archive of templates
retired from the active park — a template is never deleted, it is `rtk git mv`'d here unchanged (same
`id`, same content) the moment it no longer belongs among the discoverable ones. `aidp` skips any
pipeline under a `legacy/` directory (`pipeline::ARCHIVE_DIR`) so an archived `id` cannot collide with a
live one; it stays loadable by explicit path (`rtk aidp validate templates/legacy/<file>.yaml`). Lot T
(R-ARC-1) is what created the directory: it holds exactly one file today, `dev-tests-csharp.yaml`,
archived because it had become an orphan — zero `uses:` references anywhere in `templates/` — once
`dev-tests-csharp-split` (below) superseded it for new compositions. See `templates/legacy/README.md`.

One template deliberately keeps a label-based `fan_out:` — it is not plan work: `run-tests-dev` (one
shard per test scenario). `dev-tests-csharp` used to be the other one, sharding by test category; it is
the sole occupant of `templates/legacy/` above, not a live, discoverable template any more.

**`dev-tests-csharp-split`** is the composable C# test phase in use: the same deliverable as
`dev-tests-csharp` with the two categories as two *stages* (`tests_unit` ‖ `tests_reqnroll`) instead
of two shards, plus the `tests_suite` merge stage that owns the shared solution files, the single
full-solution `rtk dotnet test`, and the consolidated changed-files.json. Both writers are `needs`-free,
so they are the sub-pipeline's entry points: the composing stage's `needs` cascades onto both and the
emitter groups them into one `parallel()` block (verified on the emitted script, not just by
reading). `dev-csharp` composes it after `implement`; any other C# dev template can do the same by
adding a `type: pipeline` stage and narrowing its `plan_tasks.kinds` to the production kinds, so the
plan stops producing test tasks the phase would write twice. `dev-csharp-short` stays a plain
two-stage engine demo (prose plan, no task graph). `gdpr-anonymisation-test` deliberately has **no**
`fan_out:` even though it runs a scenario list: its scenarios share one LocalStack, one runner and one
global `.state/simulator-control.json` re-read on every poll, so shards would overwrite each other's
simulator modes.

### R-DUP-1 — what counts as a duplicate template, and what does not

Migrating `templates/dev.yaml` to a `stack` input (`skills_by`, §7/§12 above) made it tempting to read
every other `dev-*` variant as "the same template, parameterizable away" and fold it in. R-DUP-1 draws
the line the migration actually has to respect, in two clauses:

**(a) An input-contract difference is not a duplicate.** Two templates whose stage bodies match are not
duplicates of each other if their `inputs:` contracts differ in required-ness or in defaults — a
selector (`skills_by`, `plan_tasks.kinds`, …) can route *content*, but it cannot make an input optional
that the other template requires, or vice versa, without changing what a caller is allowed to omit.

**(b) A divergence with no `*_by` selector is not a duplicate either.** Two templates are not duplicates
merely because their only residual difference is small, if that difference sits on a field no selector
in this pipeline format (`skills_by`, `plan_tasks.skills_by_kind`, `plan_tasks.kinds`, a `when:`) can
route: `isolation:` (worktree vs none), `plan_tasks.merge_hint` (prose, not data), `plan_tasks.kinds`
(which task kinds a stage claims), or the plain presence/absence of a stage. Collapsing these would
require inventing a NEW selector axis per field — at which point the "simplification" is a bigger
surface than the templates it replaces.

**Applied to today's park:**
- `dev-angular` stays its own template: its `implement` declares `isolation: worktree`, clause (b).
- `dev-lambda-tsgit` stays its own template: its input contract makes `jira_keys`/`prompt` both
  optional with the pipeline choosing between them (clause a), AND its composed `discover` stage passes
  a `discover.with.prompt` mapping `dev-lambda-ts` does not declare (clause b) — two independent reasons,
  either alone would keep it separate.
- `dev-csharp` stays its own template: it has a `tests` stage `dev`/`dev-lambda-ts` do not, narrows
  `implement`'s `plan_tasks.kinds` to the production kinds, and `review.needs` points at `tests` instead
  of `implement` — three clause-(b) divergences with no selector between them.
- `dev-aidp` and `dev-aidp-viewer` remain TWO templates, and cloning one into the other is the accepted
  shape here: their axis of variation is the identity of the stages themselves (`read_rust`/
  `read_surface` reading the Rust workspace vs `read_client`/`read_server` reading the viewer's
  TypeScript client+server) — content, not a parameter — so R-DUP-1 does not ask for a `service`-style
  input to unify them; there is nothing a selector could route between "the Rust crate" and "the React
  client" without becoming a second copy of the stage list it was meant to replace.

`dev`'s own `stack` axis (`generic` / `lambda-ts`) is what R-DUP-1 DOES apply to: the two buckets are
the same stage list with only their `skills_by`-routed skill set differing — clauses (a) and (b) both
stay satisfied because nothing about `inputs:` required-ness or an unselectable field diverges between
them.

**One composite output reference per expression.** `rtk aidp pipeline expand` rewrites
`stages.<composite>.outputs.<alias>` to the namespaced inner stage, but only the **first** such
reference in a given string. `when: "{{ stages.a.outputs.x or stages.b.outputs.y }}"` therefore
leaves `b` unresolved and evaluates false in silence (measured on `dev-csharp-fraud-stack`).
Separate strings are fine - two inputs each referencing a different composite both resolve.
`dev-csharp-fraud-stack` works around it with a plain `quality_gate` stage merging the two
verdicts into one signal; worth fixing in the expander, since the workaround is not discoverable
from the failure.

---

## 13. v7 vs v4 — why v7 is more robust

| Concern | v4 | v7 |
|---|---|---|
| Orchestration loop | LLM "dumb driver" calls `orchestrate next` each step | deterministic JS Workflow script |
| Sub-agent reply | free-text `reply.md` → `rtk aidp reply parse` (brittle) | `agent({schema})` schema-validated |
| Token capture | driver passes `--last-tokens` from JSONL (race-prone) | Workflow runtime accounting |
| Independent stages | strictly sequential | `parallel()` fan-out |
| Executor write isolation | reactive PostToolUse scope-check | proactive `isolation: 'worktree'` (opt-in) |
| Resume | manual re-drive | native `resumeFromRunId` (cached prefix) |
| Gates | `ask_user` action in the loop | `awaiting_gate` return + resume with `args.approved_gates` |
| Artefact location | `<repo>/.aidp/pipelines/<feature>/<run_id>/` | `<vault>/Pipelines/<repo>/<feature>/<run_id>/`, with generated Obsidian notes; durable service doc in `<vault>/Knowledge/<repo>/` — transverse notes plus one note per business feature under `Features/` |

Every v4 fragility tied to LLM step-piloting disappears *by construction*. v7 runs its **own `aidp`
binary**, built from the aidp repository (same codebase lineage as v4, including the
`rtk aidp workflow emit` subcommand) — v4 does not need to be installed.

### 13.1 v7 vs v6 — the vault

The engine is v6's, unchanged. What v7 adds:

| Concern | v6 | v7 |
|---|---|---|
| Where artefacts live | in the target repo, `.aidp/pipelines/` | in an Obsidian vault, `Pipelines/<repo>/<feature>/<run_id>/` |
| Reading a past run | open files in the repo tree | linked notes: frontmatter properties, backlinks, graph, full-text search |
| Cross-repo view | none — one `.aidp/` per repo | one vault; `_Pipelines.md` lists every repo and the recent runs |
| Repo dimension | implicit (the repo you were in) | explicit path segment, from the git `origin` remote |
| Agent summaries / follow-ups | only in the Workflow result file | folded into `run-state.json` and rendered in the notes |
| Repo cleanliness | run artefacts in the working tree | only config + hook markers remain in the repo |
| Sub-agent guidance | "write your outputs here" | plus vault conventions: frontmatter, vault-absolute wikilinks, `_*` reserved |

Backwards compatibility is total: pre-v7 runs stay in `.aidp/pipelines/`, remain loadable, resumable
and listed by `rtk aidp status`; with no vault configured, v7 behaves exactly like v6.

---

## 13.5. Developing aidp itself

Rust formatting (`rustfmt.toml`), reproducing the CI gate, the fast build and test loop, and branch
protection are concerns of the aidp repository: they moved with the code to its
[`docs/development.md`](https://github.com/AlexisVuk/ai-dev-pipeline-v7/blob/master/docs/development.md). To change `aidp`, launch `dev-aidp`
from a checkout of the aidp repository, with `AIDP_SKILL_ROOT` pointing at this skill (§12). Its
checks run `rtk cargo run -p aidp-cli -- validate --all` against this skill, so an emitter change that
breaks a real template is caught there. The end-to-end suite, which runs the installed binary
against this skill with no mock, lives in [AlexisVuk/aidp-e2e](https://github.com/AlexisVuk/aidp-e2e).

`SKILL.md` declares `min_aidp_version` in its frontmatter: the oldest `aidp` this skill works with.
Raise it in the same change as a template or driver rule that needs a newer binary. `rtk aidp doctor`
reports an older binary as a red `skill_compat` check.

## 14. Prerequisites, setup & troubleshooting

**Prereq:** `aidp` (with the `workflow` subcommand) installed in `~/.aidp/bin/` (override with
`AIDP_INSTALL_DIR`) and on `PATH`, at least as recent as `min_aidp_version` in `SKILL.md`. It is built
from **the aidp repository**, checked out at `AIDP_SRC` (default `C:/CODE/Tools/aidp`) — no
dependency on ai-dev-pipeline-v4.

**Setup:** run `/pipeline-setup-v7`. It runs this skill's `setup.ps1` / `setup.sh`, which first runs the
aidp repository's `bootstrap`: `rtk cargo build --release -p aidp-cli`, then a copy of the binary (never a
link) made atomically (`.new`, then rename) into `~/.aidp/bin/`, which is prepended to PATH; any old
`target/release` entry is removed. The setup script then merges the hooks, copies the slash commands,
optionally installs `graphify` and runs `rtk aidp doctor`. Then `/pipeline-doctor-v7`.

**Update:** pull the aidp repository, re-run `/pipeline-setup-v7`, then open a new session. A cargo build
alone does not change the `aidp` on PATH. On Windows, an `aidp` still in use makes the install fail with an explicit `rtk aidp is in use`
error.

**Common failures**
| Symptom | Likely cause | Fix |
|---|---|---|
| v4 templates show up, not v7 | `AIDP_SKILL_ROOT` unset/wrong, or an old v4 `aidp` earlier on PATH | Set it to this skill's dir before every `aidp` call (§0); re-run `/pipeline-setup-v7` so `~/.aidp/bin` is prepended to PATH. |
| `aidp: command not found` | the stable install dir (`~/.aidp/bin`) is not on PATH | Open a new terminal after setup, or re-run `/pipeline-setup-v7`. |
| `aidp` exits 127 or vanishes mid-run | PATH still points at a `target/release` folder, which cargo rewrites | Re-run `/pipeline-setup-v7`: it installs into `~/.aidp/bin` and migrates PATH. Then restart the session. |
| Setup fails with `rtk aidp is in use` | another session, the gateway or a hook is running `aidp` (Windows) | Close it, then re-run `/pipeline-setup-v7`. |
| The `aidp` on PATH lacks a change you just built | builds no longer update the installed copy | Re-run `/pipeline-setup-v7`. |
| `workflow emit` unknown subcommand | binary built without `workflow` | Rebuild via `/pipeline-setup-v7`. |
| `aidp` exits 127 mid-run (`command not found`) | PATH or binary lost after launch | Retry the call via `"$AIDP_BIN"` (PowerShell `& $env:AIDP_BIN`) and keep using it. If `AIDP_BIN` is unset or fails, stop and report the run dir, `run_id`, Workflow `runId` and the `rtk aidp run record-resume ...` to replay, then `/pipeline-resume-v7 <run_id>` (SKILL.md "Exit 127"). |
| Run stalls after approving a gate | passed only the latest gate | Resume with **all** approved gates in `args.approved_gates` (§6). |
| Resume re-runs the **whole** pipeline instead of re-proposing a pending gate | the resume anchor (`workflow_run_id`) was not persisted because the gate was never approved | Fixed (WI-P1-7): record the runId + `--pending-gate` the moment a gate is proposed, *before* asking (§6). `/pipeline-resume-v7` reads `pending_gate` and re-proposes that gate. For runs paused before this fix, `workflow_run_id` may still be null → run `rtk aidp run record-resume --run <id> --from-result <run_dir>/workflow-result.json` when that file exists; without it the one-time full re-run is unavoidable. |
| Run paused at a gate but run-state has no `workflow_run_id`/`pending_gate` (`aidp` was unavailable when the pass ended) | the driver could not call `record-resume` at the end of the pass, so the anchor was never persisted | `rtk aidp run record-resume --run <id> --from-result <run_dir>/workflow-result.json`, then `/pipeline-resume-v7` (§6). The run note flags such a run with `anchor_persisted: false`. Across sessions the cached prefix may re-execute; approved gates are not re-asked. |
| Resume re-runs the **whole** pipeline after a plain `paused` result (a stage's sub-agent came back `blocked`/`failed`/asked questions — a review-stage `harness_gap` pause is the most common case) — not a gate at all | WI-P1-7 only covered the *gate* branch; the driver's `paused` branch (SKILL.md §6, `commands/run-pipeline-v7.md`, `commands/pipeline-resume-v7.md`) never called `rtk aidp run record-resume`, so `state.workflow_run_id` stayed null for this branch even though `record_resume()` has always supported being called with just `--workflow-run-id` and no gate | Fixed: the `paused` branch in all three driver docs now calls `rtk aidp run record-resume --run <run_id> --workflow-run-id <runId>` (no `--pending-gate`/`--approved-gate`) as its first action, before diagnosing or relaying the failure. `/pipeline-resume-v7` then finds a non-null `workflow_run_id` and can `resumeFromRunId` instead of falling back to a full re-run. For runs paused before this fix, `workflow_run_id` may still be null → the one-time full re-run is unavoidable, same caveat as WI-P1-7, except that an existing `workflow-result.json` lets `record-resume --from-result` restore the anchor. |
| Run pauses at a reviewer stage (`review`, one parallel review axis, an `audit` dimension) with `needs_review`, never reaching `correction_loop` / `verify` / `report` | Two independent causes: (a) the emitter halted on `needs_review` for reviewers it could not prove a loop consumed — which was *every* reviewer in the loop-free `audit`/`review` templates; (b) the reviewer agent returned `needs_review` *because* it found blocking findings | Fixed on both sides (§6). (a) `soft_pause_stages` now emits the soft check for **every** `agent: reviewer` stage, loop-fed or not; `blocked`/`failed`/`ask_user_questions` stay hard. (b) `agents/reviewer.md` mandates `status: "completed"` + `signals.has_blocking_findings: true`, reserving `needs_review`/`blocked` for a review that could not be produced. Verify on any template with `rtk grep 'isPause(results\[' workflow.js` — every reviewer must show `, true)`. |
| `rtk aidp run summary --run <id>` prints a doubled path (`…/<run_dir>/.aidp/pipelines/<id>/run-state.json`) | `--workspace-root` defaults to cwd, and the command was run from inside the run dir (or any subdir) | Fixed: run lookup walks up the ancestors to find the owning `.aidp/pipelines`. Works from anywhere in the workspace now. |
| A stage wrote outside its declared `scope` | nothing blocks it live — the write already landed | Check `rtk aidp scope verify --run <id>` (non-zero on a violation) or the reconciled `scope_violations` in `run-state.json`; fix by hand, no hook will catch it for you (§10). |
| `rtk aidp doctor` red on `aidp_on_path` (`absent` / `target_build` / `mismatch` / `older_than_running` / `older_than_sources`) | The `aidp` first on PATH is missing, a `target/debug` or worktree build, a different binary from the running one, or older than the running binary or the Rust sources. Running `rtk aidp doctor` from `rtk cargo run` or a worktree build is red by design. | Run `/pipeline-setup-v7` to rebuild and put `~/.aidp/bin` first on PATH, then open a new terminal. |
| `rtk aidp doctor` red on `skill_compat` | The installed `aidp` is older than the `min_aidp_version` declared in `SKILL.md`. | Pull the aidp repository, then re-run `/pipeline-setup-v7`. |
| Error naming `AIDP_SKILL_ROOT` when listing or resolving a template | the binary was moved or installed away from the skill, and it no longer falls back to the source tree it was built from | Set `AIDP_SKILL_ROOT` to this skill's directory (§0) before every `aidp` call. |
| A pipeline id resolves against the wrong workspace | before, the process cwd decided; now `--workspace-root` does, for `validate`, `pipeline expand`, `run init` and `run start` | Pass `--workspace-root <path>` explicitly when running from another directory. |
| Knowledge-graph `skipped`/`failed` | `graphify` CLI missing | Non-blocking; `pip install graphifyy` to re-enable acceleration. |
| Run artefacts landed in the repo's `.aidp/pipelines/`, not the vault | no vault resolved — `AIDP_VAULT=off`, `--no-vault`, or nothing found by auto-detection | `rtk aidp vault status` shows `configured: false`. Pin it: `rtk aidp vault init --vault <path>`. Not an error: the legacy layout is supported. |
| Artefacts went to the *wrong* vault | several vaults in reach and auto-detection picked one | `rtk aidp vault status` reports `ambiguity`. Pin the right one with `rtk aidp vault init --vault <path>` (writes `~/.aidp/config.json`, which beats auto-detection). |
| Notes are stale / a `_*.md` was deleted or hand-edited | generated notes are rewritten only when `run::save` runs | `rtk aidp vault reindex` regenerates them all from `run-state.json`. |
| A sub-agent's artifact vanished | it wrote a `_`-prefixed file, which the next `refresh` overwrote | Prompts forbid this. If a template asks for such an output, rename it — `_*` is reserved. |
| Obsidian shows no links between notes | the artifact used a bare `[[note]]` wikilink | Links must be vault-absolute (`[[Pipelines/repo/F/run/stage/note\|alias]]`); stage folder names repeat across runs, so bare names are ambiguous. |

---

## 15. File map

```
ai-dev-pipeline-v7/     # this skill (repository AlexisVuk/ai-dev-pipeline-skill)
├── SKILL.md            # short trigger-time procedure (loaded each session); declares min_aidp_version
├── README.md           # human onboarding (FR)
├── USER-GUIDE.md       # full user guide (FR)
├── AGENTS.md           # essential rules, loaded by every agent in this repo
├── docs/agents-reference.md  # ← this file: full agent-facing reference
├── commands/           # full v7 command set: run-pipeline-v7, pipeline-setup-v7,
│                       #   pipeline-doctor-v7, pipeline-status-v7, pipeline-resume-v7,
│                       #   pipeline-validate-v7, pipeline-new-v7, agent-new-v7
├── agents/             # the 4 generic sub-agents (analyzer/planner/executor/reviewer)
├── templates/          # v7 pipelines (version: 5) — see §12
│   ├── flows/          #   ticket flows (`aidp flow`)
│   ├── recipes/        #   autonomous-session recipes
│   └── legacy/         #   archive of retired templates (same id, content unchanged);
│                       #   excluded from discovery, runnable by explicit path (§12)
├── hooks/              # settings.example.json: single Stop hook (run summary) — no live guard hook;
│                       #   ci-events.example.json: the CI autopilot hooks (§10.1)
└── setup.ps1 / .sh     # what /pipeline-setup-v7 runs: aidp bootstrap, hooks, commands, doctor
```

The `aidp` workspace, its JSON schemas (`schema/`, §9), the install scripts and the docs of the
gateway, tickets, flows and providers live in the aidp repository; its file map is in that
repository's [`docs/development.md`](https://github.com/AlexisVuk/ai-dev-pipeline-v7/blob/master/docs/development.md). `/pipeline-setup-v7`
installs the binary into `~/.aidp/bin/`.

Output does **not** live here. It lives in the vault:

```
<vault>/                              e.g. C:/CODE/AIDP
├── .obsidian/                        Obsidian's own config
└── Pipelines/
    ├── _Pipelines.md                 dashboard — every repo, 25 most recent runs
    └── <repo>/                       from the git origin remote
        ├── _<repo>.md                repo MOC — every feature
        └── <feature>/
            ├── _<feature>.md         feature MOC — every run + shared research
            ├── <research-stage>/     shared across runs (analyzer / discover / study / explore)
            │   ├── _<stage>.md       generated stage note
            │   └── …                 the agent's artefacts
            └── <run_id>/
                ├── _<run_id>.md      generated run note (stage table, inputs, gates, follow-ups)
                ├── run-state.json    the canonical run snapshot
                ├── effective-pipeline.yaml, workflow.js, plan-schedule.json, workflow-result.json
                └── <stage>/
                    ├── _<stage>.md   generated stage note
                    └── …             the agent's artefacts
```
The two source files behind it: `crates/aidp-core/src/vault.rs` (resolution + layout) and
`obsidian.rs` (note generation).

---

## 16. Quick rules recap (paste-ready checklist)

- [ ] `AIDP_SKILL_ROOT` set for every `aidp` call.
- [ ] `aidp vault status` checked before the run; `configured: false` or an `ambiguity` relayed to the user.
- [ ] Template chosen via `AskUserQuestion`, never inferred.
- [ ] Enum inputs collected via `AskUserQuestion`; defaults omitted from `--inputs`.
- [ ] Tracked both IDs: `run_id` (aidp) and `runId` (Workflow).
- [ ] First `Workflow` call has **no** `resumeFromRunId`.
- [ ] Write `workflow-result.json` (the unwrapped result object) before any `aidp` call, on every branch.
- [ ] Cold-start resume: when `workflow_run_id` is null and `workflow-result.json` exists, run `aidp run record-resume --from-result` before `/pipeline-resume-v7` proposes anything.
- [ ] On `awaiting_gate`: **first** persist the anchor (`record-resume --workflow-run-id --pending-gate`) before asking; on approve, resume with the latest approved gate (prior ones are baked in).
- [ ] A gate pre-approved via `--approve-gate` / `AIDP_AUTO_APPROVE_GATES` at `run start` never surfaces as `awaiting_gate` — `auto_approved_gates` in the `run start` envelope is what confirms which ones were baked in.
- [ ] On `awaiting_plan`: persist the anchor, re-run `aidp workflow emit` (it compiles the tail from `plan.json`), optionally show `plan-status`, resume with `resumeFromRunId`. Not a gate, not an error.
- [ ] On `paused`: **first** persist the anchor (`record-resume --workflow-run-id`, no gate flags — otherwise the next resume re-runs everything), **then** relay envelope, stop until the user resolves it. `at: "<stage>#<task>"` = one plan task.
- [ ] Never `Edit`/`Write`/non-`aidp` `Bash`; never hand-edit `workflow.js`; never plan/code/review yourself.
- [ ] Never create or edit a `_*.md` note in the vault — `aidp` owns them.
- [ ] Always finish with `aidp run summary --run <run_id>`, and give the user the vault `run_dir`.
```
