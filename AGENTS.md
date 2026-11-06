# AGENTS.md — ai-dev-pipeline v7 (skill)

Essential rules only. The full reference (command surface, YAML vocabulary, data contracts,
template catalog, troubleshooting) is [docs/agents-reference.md](docs/agents-reference.md); its
`§` numbers are the ones other docs cite. Read the section you need, not the whole file.

## What this repo is

The Claude Code skill of the AI Dev Pipeline: the pipelines (`templates/`), the generic sub-agents
(`agents/`: analyzer, planner, executor, reviewer), the slash commands, the hooks and the driver
procedure. The `aidp` binary compiles a template into a deterministic JavaScript script run by
Claude Code's `Workflow` tool; sub-agents do the work and return schema-validated JSON. Run output
lands in an Obsidian vault (`<vault>/Pipelines/<repo>/<feature>/<run_id>/`), never in the target
repo.

Three repositories make the pipeline:

| Repository | Holds |
|---|---|
| this one (`AlexisVuk/ai-dev-pipeline-skill`) | templates, agents, commands, hooks, `SKILL.md`, user docs |
| aidp (`AlexisVuk/ai-dev-pipeline-v7`, at `AIDP_SRC`, default `C:/CODE/Tools/aidp`) | the Rust workspace, the JSON schemas, the gateway docs, the install scripts |
| `AlexisVuk/aidp-e2e` | end-to-end tests: the installed binary against this skill, no mock |

| Path | Holds |
|---|---|
| `SKILL.md` | The driver procedure, loaded when the skill triggers; `min_aidp_version` in its frontmatter |
| `commands/` | The `/…-v7` slash commands |
| `templates/` | Pipelines (`version: 5`), `flows/`, `recipes/`; `templates/legacy/` is an archive, not discovered |
| `agents/` | The four generic sub-agents |
| `hooks/` | Hook examples merged by `rtk aidp setup merge-hooks` |
| `docs/agents-reference.md` | The full reference |
| `setup.ps1` / `setup.sh` | What `/pipeline-setup-v7` runs |

## Driving a pipeline run

Follow `SKILL.md`. The rules that must never bend:

- Set `AIDP_SKILL_ROOT` to this skill's directory for every `aidp` call.
- Pick the template and every enum input through `AskUserQuestion`; never infer them.
- The driver runs `aidp` and the `Workflow` tool only: no `Edit`/`Write`/other `Bash`, no
  planning, coding or reviewing itself. Never hand-edit an emitted `workflow.js`: fix the template
  and re-emit.
- Track both ids: `run_id` (from `rtk aidp run init`) and the Workflow `runId` (for `resumeFromRunId`).
- On every Workflow result, first write the unwrapped result object to
  `<run_dir>/workflow-result.json`, then `rtk aidp run reconcile --run <run_id> --from <that file>`.
- Branch on `status` (reference §6):
  - `done`: reconcile, print `rtk aidp run summary --run <run_id>`, give the vault `run_dir`.
  - `awaiting_gate`: `rtk aidp run record-resume --workflow-run-id <runId> --pending-gate <stage>`
    **before** asking; on approval, `--approved-gate <stage>`, re-emit, resume with
    `args.approved_gates: [<stage>]`.
  - `awaiting_plan`: record the runId, re-run `rtk aidp workflow emit`, resume. Not an error.
  - `paused`: record the runId first, then relay `envelope.summary` and its questions; stop.
- Never create or edit a vault `_*.md` note: `aidp` generates them.
- Never edit `status:`/`autopilot:` in a `TODO/**` note by hand; use `rtk aidp ticket status`.

## Changing templates, agents or commands

- Run `rtk aidp validate <path>` on every template touched and on every template that composes it;
  `rtk aidp validate --all` before opening the PR.
- Pipeline-level `policy:` does not survive `uses:`: put a fragment's rules on its stages.
- A template that needs a field or behavior the binary does not have yet waits for the aidp
  release that adds it; raise `min_aidp_version` in `SKILL.md` in the same change.
- A behavior change the driver can see needs its doc update in the same change: `SKILL.md`,
  `docs/agents-reference.md`, `USER-GUIDE.md`.
- No ticket or PR references (`LOC-xx`, `#nn`) in new template text or docs.
- A change to the stage vocabulary, the schemas or the emitter is an aidp change: launch `dev-aidp`
  from the aidp repository (reference §13.5).

## Git and pull requests

- Work on a branch, open a PR against `master`; never commit to `master`.
- GitHub auto-merge is disabled on this repo: wait for the checks, then merge by hand.
- On a PR under review, address review comments before chasing CI.
- Commit messages follow Conventional Commits.

## Where to look

| Need | Reference section |
|---|---|
| Every `aidp` subcommand and flag | §3 |
| Result statuses, gates, resume | §5, §6 |
| Pipeline YAML fields, `plan_tasks`, composition | §7, §7.1 |
| Sub-agents, scopes, vault layout, knowledge base | §8 |
| Reply envelope and artifact schemas | §9 |
| Scope verification, tool restriction, CI autopilot hooks | §10 |
| Template catalog and fragments | §12 |
| Developing aidp itself, `min_aidp_version` | §13.5 |
| Setup and common failures | §14 |
| File map | §15 |
