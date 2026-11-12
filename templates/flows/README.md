# Flow definitions

This directory holds ticket workflow definitions read by the flow engine
(`rtk aidp flow ...`). They are validated against `schema/flow.schema.json`.

They are not v7 pipelines: they carry no `stages:` and must not be run with
`rtk aidp run`. `rtk aidp pipeline list` must not discover them.

## Definitions

- `perso-delivery.yaml`: the delivery flow of a local ticket in a personal GitHub repo with no CI: worktree, branch, `dev-unity` (the `unity-issue-workflow` agents: implement and open the draft PR, playtest in the Unity Editor), `review-unity` (GitHub review), `fix-review-unity` (fixes), PR ready, human merge, cleanup. No `ci` block. Start it with `POST /api/tickets/:key/flow` and the body `{"flow": "perso-delivery"}`.
- `game-code.yaml`, `game-art.yaml`, `game-map.yaml`: the DEV lane. Worktree (the default workspace), several in parallel (`dispatcher.slots`). Claim, `git.worktree`, `git.branch`, produce (`unity-implement` / `art-produce` / `map-produce`; the ticket `track`, `standard` or `bug`, reaches the pipelines from the daemon), loop review <-> fix (2 rounds; each fix pipeline runs `prepare` -> `plan` (opus, read only, `fix-plan.json`) -> `fix`, which follows the plan), then STOP: `ticket.to_test` (label `aidp:to-test`, ticket phase `to-test`), `worktree.remove`, the flow ends `done`. No compile gate and no test in these stages (`verification.compile = "deferred"`).
- `game-test-code.yaml`: the TEST lane of code issues, the `test_flow` of the route in `routing.yaml`, started by the dispatcher once the issue is `to-test` and the lane of its project is free (`dispatcher.test_slots`, 1). `workspace: project` (see below): `git.checkout`, `unity.refresh`, loop `unity-test` <-> fix with `report_from: test` (2 rounds), PR ready, `git.restore`, human merge, `done`. The only test flow that uses the Unity Editor: the Editor tests are kept for the issues that change code.
- `game-test-art.yaml`, `game-test-map.yaml`: the HEADLESS test lane, same `test_flow` role and same dispatcher rules. Worktree (the default workspace, like the dev lane), NO Unity Editor, no `workspace: project`, no `git.checkout` / `unity.refresh` / `git.restore`, no `unity-editor` resource. Steps: `git.worktree`, `git.branch`, loop test (`art-headless` / `map-headless`) <-> fix (`art-fix` / `map-fix`, `report_from: test`, 2 rounds), PR ready, label `awaiting-merge`, human merge, `done`, `worktree.remove`. The test stage commits and pushes the `.meta` files that `scripts/unity_meta.py` creates (hence `pushes: true`).
- `game-doc.yaml`: `doc-write`, `doc-review` <-> `doc-fix`; worktree, up to the merge, no Unity.

The `game-*` flows share phases (Préparation, Réalisation, Revue, Passage en test, Test Unity, Merge, Nettoyage) and label the issue with `gh.issue_label` (`in-progress`, `review`, `to-test`, `testing`, `awaiting-merge`, `done`, `blocked`). They need the daemon features `gh.issue_label`, `gh.issue_comment`, `gh.pr_ready`, `ticket.to_test`, `unity.refresh` (`game-test-code`), the step key `resource`, the `{{ }}` templates in `with` and the outputs `steps.<id>.outputs.{verdict,passed,...}` (C9); `aidp flow validate` on a daemon without them reports exactly those. `routing.yaml` gives each route a `test_flow:` next to its `flow:`.

Workspace of `game-test-code` (`workspace: project`): no worktree. Every step runs in the main checkout of the project, where the Unity Editor is open.
- `checkout` (`git.checkout`) is the first step. Dirty checkout: output `blocked: true`, then `checkout_label` (`aidp:blocked`), `checkout_comment` (the file list) and `fail` (business, `blocked: dirty-checkout`). Clean: `git switch` to the issue branch (the one the dev flow pushed).
- `refresh` (`unity.refresh`) comes right after: `aidp flow unity-refresh` drops one compile gate request (C1) in the checkout and waits for the result, so the editor's reimport and recompilation of the new branch end before the test stage. Outputs `ok`, `errors`, `warnings`, `duration_ms`, `request_id`. Compile errors are not a stop (the test stage reports them). No Unity project or no editor open on the checkout: the step is skipped (`reason`: `not-a-unity-project` / `unity-editor-closed`) and the test stage decides. Editor silent (no result in 600 s, or a heartbeat `.aidp/editor/heartbeat.json` older than 30 s outside a domain reload): `blocked: true`, then `refresh_label`, `refresh_comment` (the message, with the last heartbeat) and `fail` (business, `blocked: unity-editor`).
- Lock: the run holds the project's `unity-editor` resource from `checkout` until `restore` (`git.restore`, placed before the human merge approval); a second test flow waits `waiting_external` on its `checkout`. When the run ends `escalated`, `failed` or cancelled the daemon runs `git.restore` itself. `git.restore` returns to the base branch only when the checkout is clean; otherwise it leaves it and comments on the issue. Stages never switch branch (`unity-verify.md`: `blocked: unity-branch`).

Workspace of `game-test-art` and `game-test-map` (headless): a worktree per ticket, like the dev lane, so the main checkout and the Unity Editor are never touched and a test lane run does not hold `unity-editor`.
- `git.worktree` (`worktrees ensure`) then `git.branch`. Caveat verified in the gateway code: `worktree.remove` of the dev flow deletes the local branch `feat/GH-<n>`; `git.worktree` then creates it again from the default branch, and `git.branch` finds the local ref and does not switch to `origin/feat/GH-<n>`. The first stage (`prepare`) of `art-headless` / `map-headless` therefore runs `git fetch origin <branch>` and `git merge --ff-only origin/<branch>` (not fast-forwardable: `blocked: branch-diverged`). A fix in the gateway (`git.branch` or `ensure` resetting a fresh branch to `origin/<branch>`) would make that step redundant.
- The tests run no Unity: file checks (PNG, `.aseprite`, `.ldtk`), Aseprite MCP lint / `unity_validate`, `pixellab_fidelity.py`, the scripts of the `ldtk`, `map-world-design`, `map-room-design` skills. A criterion that needs Unity is reported `deferred` and never fails the test.
- `.meta`: `scripts/unity_meta.py` creates the missing `.meta` of the files added by the PR (`.png`, `.aseprite`, new folders) from a real `.meta` of the base branch, with a new GUID and the project import settings; an existing `.meta` is only checked. The test commits and pushes them on the PR branch.
- `worktree.remove` (`on_error: warn`) ends the flow, as in the dev lane.

Daemon facts the flows rely on:


- Pipeline inputs: for a GitHub-mirrored ticket the daemon passes `issue` (the number), `track`, `route` and `feature` to every `pipeline` step itself; no `with: { issue: ... }` is needed. A flow `inputs.track` would not be the ticket track, so none is declared.
- Loops: `max` is a literal 2 (the schema wants a u32) kept equal to `settings.max_*_rounds`. A loop ended by `max` alone escalates the run at once and nothing after it runs, so each `until` also stops on `!(steps.<loop>.iteration < settings.max_*_rounds)`; the steps after the loop then run when the result is not good: label `blocked`, then `fail` with `with: { kind: business, message }`, which ends the run `escalated` (a plain `fail` would end it `failed`, a technical error).
- The last round: a `need-fix` verdict (or a failed test) of the last round is followed by its fix, then no new review; the issue is `blocked` and a human looks.
- Comments: `gh.issue_comment` `with.body` takes `{{ steps.<id>.outputs.<key> }}` (rendered when the step starts; a missing key gives an empty text), `cost_footer: true` appends the cost line.

Always name the flow when you start one: the flow the daemon starts when the request names none
(`ticket-delivery`) is no longer part of this skill.

## Forced moves (`entries:`)

A ticket can be forced by hand to any board column (`POST /api/tickets/:key/force`, the board's « Forcer vers… », daemon
7.11.0 or newer). For `review`, `testing` and `merge` the daemon restarts the route's flow from the entry of that name: the
top-level steps before `step` are skipped (reason `forced`), the `keep` steps still run, and `outputs` are assumed for the
skipped steps so the conditions after `step` hold. Every flow declares the entries it can land on:

| Flow | `review` | `testing` | `merge` |
|---|---|---|---|
| `game-code`, `game-art`, `game-map` | `review_loop`, keeps worktree and branch | | |
| `game-doc`, `game-bug-code`, `game-bug-map` | `review_loop` | | `ready`, keeps worktree and branch |
| `game-bug-art` | `review_loop` | | `ready`, assumes `review.verdict: done` |
| `game-test-code` | | `test_label`, keeps checkout and refresh with their guards | `ready`, assumes `test.passed: true` |
| `game-test-art`, `game-test-map` | | `test_label`, keeps worktree and branch | `ready`, assumes `test.passed: true` |
| `perso-delivery` | `review` | | `ready` |

A new step a condition after an entry reads must get its assumed output in that entry.

## Merge conflict fallback

Every flow that merges (`game-test-*`, `game-bug-*`, `game-doc`, `perso-delivery`) wraps `gh.merge` in a `merge_loop` (`max: 2`,
`settings.max_merge_rounds: 2`). When the PR conflicts with its base and nothing else closes its gate, `gh.merge` no longer fails: it
ends with `merged: false`, `conflict: true` (daemon 7.7.0 or newer; an older daemon still fails the step, as before). The next round
runs `merge-conflict` (`templates/merge-conflict.yaml`, one stage on Sonnet at effort `low`): it merges `origin/<base>` into the PR
branch in its own temporary worktree (never the flow's checkout, never a rebase or a force push), resolves the conflicted files, pushes,
then `gh.merge` runs again on the new head. Still not merged: label `blocked` (`merge_blocked`) and run `escalated` (`merge_escalate`).
The step id stays `merge`, so the ticket goes `done` only on a real merge.

## Bug tickets (failed test)

`game-test-code`, `game-test-art` and `game-test-map` (version 2) have no fix loop any more. A failed test (`passed == false`) runs `bug.create`: bug issue labelled `bug` and `bug:code|art|map`, title `fix(GH-<n>): <summary>`, sub-issue of the ticket, marker `<!-- aidp:bug parent=<n> base=feat/GH-<n> -->` in its body. The ticket goes back to `to-test` and waits (open blocker `waiting-on:GH-<bug>`); the run ends `done`. Before `bug.create` (version 3 of the test flows) the read-only pipeline `bug-write` writes the body: « Issue de base » (parent and PR summary, links), « Description du bug » (expected and obtained values, product defect against environment failure), « Plan à adopter » (files, types, assets, steps), « Critères d'acceptation » (CA-n tied to the scenario or test that proves them, at least « le test qui a échoué passe » and « aucun autre critère du parent ne régresse »). The daemon keeps the marker first and folds the raw report in `<details>` at the end; if `bug-write` fails the bug is created with the raw report alone (`bug.create` needs the daemon with `--body-file`). The bug flows read these sections: their CA-n are the criteria. A test without verdict (neither true nor false) blocks the issue. A 4th bug (`capped`, cap 3) labels the ticket `blocked` and ends the run `escalated`.

- `game-bug-code.yaml`, `game-bug-art.yaml`, `game-bug-map.yaml`: claim, worktree, branch `fix/GH-<bug>` from `origin/feat/GH-<parent>`, produce/implement, review <-> fix loop (2 rounds), then AUTOMATIC merge into `feat/GH-<parent>` when the verdict is `done` (`gh.pr_ready`, `gh.merge`), `done`, `gh.issue_close`. Not `done`: label `blocked`, run `escalated`, nothing merged.
- The pipelines (`unity-*`, `art-*`, `map-*`) take the input `base_branch` (filled from the ticket) and pass it as `context.baseBranch`: the PR targets that branch, never `main`.
- When the bug is closed the parent is free: the dispatcher starts the test flow again. The PR of the parent toward `main` stays a human merge.
- `routing.yaml` (Vault, patch by hand): rules at the top `labels: [bug:code] -> pixelhood-bug-code`, `bug:art -> pixelhood-bug-art`, `bug:map -> pixelhood-bug-map`; repos `pixelhood-bug-code: { route: code, flow: game-bug-code, track: bug }`, `pixelhood-bug-art: { route: art, flow: game-bug-art }`, `pixelhood-bug-map: { route: map, flow: game-bug-map }`, without `test_flow`. An existing `pixelhood-bug` entry stays for bugs filed by hand.
- Needs the daemon actions `bug.create` and `gh.issue_close`, and GitHub sub-issues enabled on the repo.
