---
description: Run the three Unity pipelines of ai-dev-pipeline-v7 on one GitHub issue, in order — dev-unity (plan, implement, draft PR, playtest in the Unity Editor), review-unity (Unity review of the whole issue on the PR), fix-review-unity (fix the review comments, playtest again, PR ready). Usage — /run-unity-dev-pipeline <issue>.
argument-hint: "<issue number>"
---

Run the three Unity pipelines of **ai-dev-pipeline-v7** on GitHub issue `$1`, one after the other,
each with the skill's normal procedure. Activate the **ai-dev-pipeline-v7** skill and follow its
`SKILL.md` « Procedure » for every run (steps 3 to 6: `run start`, `Workflow`, write
`workflow-result.json`, `run reconcile`, gates, `awaiting_plan`, pauses, exit 127). You are a thin
driver: all real work happens inside the Workflow sub-agents.

## Arguments
- `$1` = the GitHub issue number (`42` or `#42`; strip the `#`). Missing or not a number:
  `AskUserQuestion` for it. Never guess.

## Before the first run
1. Use `AIDP_SKILL_ROOT` from the user environment for every `aidp` call (`D:\AIDP\skill` in the
   gamedev profile; bash prefix, or `$env:AIDP_SKILL_ROOT` in PowerShell, when it is unset).
2. The current directory must be the Unity project (it holds `Assets/` and `ProjectSettings/`).
   Otherwise stop and say so.
3. `rtk aidp vault status --format json-compact` once: warn if no vault is configured, then go on.
4. Tell the user in one line: the PlayMode test is manual (the PR body section « Test manuel en
   PlayMode »), so the playtest stages are skipped by default (`playtest: false`). Only when the user
   asks for `playtest: true`: the legacy playtest drives the Unity Editor through the Unity MCP and,
   for real input in the Game view, through computer use — it will ask them to grant access to the
   Unity Editor; refusing only skips the scenarios that need it.

Every run uses the same inputs `--input issue=<n> --input feature=issue-<n>` and `--target issue-<n>`,
so the three runs land in the same vault feature folder.

## 1. `dev-unity`
`rtk aidp run start --pipeline dev-unity --target issue-<n> --input issue=<n> --input feature=issue-<n>`,
then drive it to the end per `SKILL.md`.
- `done` → read `<run_dir>/report/state.json` (or the `report` stage's outputs): the PR number. Go to 2.
- Paused at `playtest_fix` (the playtest still fails after the correction rounds) →
  `AskUserQuestion`: « Le playtest échoue encore après 2 tours de correction. Lancer quand même la
  review ? » → *Lancer la review (recommandé)* / *Arrêter*. The review will report the failing
  criteria as blocking comments.
- Any other pause, `blocked` or `failed` → relay the envelope (stage, summary, follow-ups) and the
  `rtk aidp run summary --run <run_id>`, then stop: the next pipelines need a PR in good shape.

## 2. `review-unity`
`rtk aidp run start --pipeline review-unity --target issue-<n> --input issue=<n> --input pr=<pr> --input feature=issue-<n>`,
then drive it to the end. On `done`, read `<run_dir>/verdict/verdict.json`. Relay in one line the
review URL and the verdict (comments by severity, criteria done / total). Go to 3 in every case:
`fix-review-unity` also handles « nothing to fix » (it skips straight to marking the PR ready).
`blocked` / `failed` → relay and stop.

## 3. `fix-review-unity`
`rtk aidp run start --pipeline fix-review-unity --target issue-<n> --input issue=<n> --input pr=<pr> --input feature=issue-<n>`,
then drive it to the end. On `done`, read `<run_dir>/ready/state.json`.
- `another_round_advised: true` (fixes or playtest failures since the last review) →
  `AskUserQuestion`: « Refaire un tour review → corrections ? » → *Oui, un tour de plus* / *Non,
  s'arrêter là*. Yes: run 2 then 3 again (the round numbers are computed from the PR). At most two
  extra rounds; then stop and say so.

## End
Print one short report:
- the PR link and its state (draft / ready), never merged — the human merges;
- dev-unity: plan written, criteria covered, batchmode verification, playtest rounds and result;
- review-unity: review URL, comments by severity, criteria done / total;
- fix-review-unity: threads fixed / left open, playtest after fixes, PR marked ready or why not;
- the manual actions left in the Unity Editor;
- the three run dirs (vault paths) and `run_id`s.

## Rules
- Run the pipelines strictly in this order, one at a time; never start the next while one is
  running or paused.
- Do NOT call `Edit`, `Write`, `MultiEdit`, or non-`aidp` `Bash` yourself, except writing
  `<run_dir>/workflow-result.json` and reading the `state.json` / `verdict.json` files named above.
  Never hand-edit a `workflow.js`.
- Never merge the PR, never push, never answer a gate or a question for the user.
