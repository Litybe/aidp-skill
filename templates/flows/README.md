# Flow definitions

This directory holds ticket workflow definitions read by the flow engine
(`rtk aidp flow ...`). They are validated against `schema/flow.schema.json`.

They are not v7 pipelines: they carry no `stages:` and must not be run with
`rtk aidp run`. `rtk aidp pipeline list` must not discover them.

## Definitions

- `perso-delivery.yaml` (legacy Desktop route): the delivery flow of a local ticket in a personal GitHub repo with no CI: worktree, branch, `dev-unity` (the `unity-issue-workflow` agents: implement and open the draft PR; the in-Editor playtest is off by default), `review-unity` (GitHub review), `fix-review-unity` (fixes), PR ready, human merge, cleanup. No `ci` block. Start it with `POST /api/tickets/:key/flow` and the body `{"flow": "perso-delivery"}`.
- `game-code.yaml`, `game-art.yaml`, `game-map.yaml`: the DEV lane. Worktree (the default workspace), several in parallel (`dispatcher.slots`). Claim, `git.worktree`, `git.branch`, produce (`unity-implement` / `art-produce` / `map-produce`; the ticket `track`, `standard` or `bug`, reaches the pipelines from the daemon), loop review <-> fix (2 rounds), then STOP: `ticket.to_test` (label `aidp:to-test`, ticket phase `to-test`), `worktree.remove`, the flow ends `done`. The Unity stages of `game-code` verify headless in the worktree: Unity in batchmode, compile gate C1 and EditMode suite C8 (`templates/recipes/unity-verify.md`), never PlayMode.
- `game-test-code.yaml`: the TEST lane of the `code` route, the `test_flow` of `routing.yaml`, started by the dispatcher once the issue is `to-test`. Default workspace (a worktree, `git.worktree` then `git.branch` on the branch the dev flow pushed), no Editor, no `unity-editor` resource: loop `unity-test` (headless: batchmode compile gate C1 + EditMode suite C8, PR comment with the « À tester à la main en PlayMode » check-list) <-> `unity-fix` with `report_from: test` (2 rounds), `gh.pr_ready`, label `awaiting-merge`, an issue comment, `worktree.remove`, `done`. No human step and no merge in the flow: the human plays the PlayMode check-list and merges on GitHub; the dispatcher moves the ticket to `done` when it sees the PR merged. A test flow occupies a dev slot (`dispatcher.slots`), not the `test_slots` lane.
- `game-test-art.yaml`, `game-test-map.yaml`: the TEST lanes of the `art` and `map` routes, unchanged: `workspace: project` (see below), `git.checkout`, loop test (`art-import` / `map-test`) <-> fix with `report_from: test` (2 rounds), PR ready, `git.restore`, human merge, `done`. They still need the Editor open on the main checkout and hold the `unity-editor` resource; `art-import` and `map-test` commit and push the `.meta` files the Editor generates.
- `game-doc.yaml`: `doc-write`, `doc-review` <-> `doc-fix`; worktree, up to the merge, no Unity.

The `game-*` flows share phases (Préparation, Réalisation, Revue, Passage en test, Test Unity, Merge, Nettoyage) and label the issue with `gh.issue_label` (`in-progress`, `review`, `to-test`, `testing`, `awaiting-merge`, `done`, `blocked`). They need the daemon features `gh.issue_label`, `gh.issue_comment`, `gh.pr_ready`, `ticket.to_test`, the step key `resource`, the `{{ }}` templates in `with` and the outputs `steps.<id>.outputs.{verdict,passed,...}` (C9); `aidp flow validate` on a daemon without them reports exactly those. `routing.yaml` gives each route a `test_flow:` next to its `flow:`.

Workspace of `game-test-art` and `game-test-map` (`workspace: project`): no worktree. Every step runs in the main checkout of the project, where the Unity Editor is open.
- `checkout` (`git.checkout`) is the first step. Dirty checkout: output `blocked: true`, then `checkout_label` (`aidp:blocked`), `checkout_comment` (the file list) and `fail` (business, `blocked: dirty-checkout`). Clean: `git switch` to the issue branch (the one the dev flow pushed).
- Lock: the run holds the project's `unity-editor` resource from `checkout` until `restore` (`git.restore`, placed before the human merge approval); a second test flow waits `waiting_external` on its `checkout`. When the run ends `escalated`, `failed` or cancelled the daemon runs `git.restore` itself. `git.restore` returns to the base branch only when the checkout is clean; otherwise it leaves it and comments on the issue. Stages never switch branch (`unity-verify.md`: `blocked: unity-branch`).

Daemon facts the flows rely on:


- Pipeline inputs: for a GitHub-mirrored ticket the daemon passes `issue` (the number), `track`, `route` and `feature` to every `pipeline` step itself; no `with: { issue: ... }` is needed. A flow `inputs.track` would not be the ticket track, so none is declared.
- Loops: `max` is a literal 2 (the schema wants a u32) kept equal to `settings.max_*_rounds`. A loop ended by `max` alone escalates the run at once and nothing after it runs, so each `until` also stops on `!(steps.<loop>.iteration < settings.max_*_rounds)`; the steps after the loop then run when the result is not good: label `blocked`, then `fail` with `with: { kind: business, message }`, which ends the run `escalated` (a plain `fail` would end it `failed`, a technical error).
- The last round: a `need-fix` verdict (or a failed test) of the last round is followed by its fix, then no new review; the issue is `blocked` and a human looks.
- Comments: `gh.issue_comment` `with.body` takes `{{ steps.<id>.outputs.<key> }}` (rendered when the step starts; a missing key gives an empty text), `cost_footer: true` appends the cost line.

Always name the flow when you start one: the flow the daemon starts when the request names none
(`ticket-delivery`) is no longer part of this skill.
