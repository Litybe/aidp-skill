# Flow definitions

This directory holds ticket workflow definitions read by the flow engine
(`rtk aidp flow ...`). They are validated against `schema/flow.schema.json`.

They are not v7 pipelines: they carry no `stages:` and must not be run with
`rtk aidp run`. `rtk aidp pipeline list` must not discover them.

## Definitions

- `perso-delivery.yaml`: the delivery flow of a local ticket in a personal GitHub repo with no CI: worktree, branch, `dev-unity` (the `unity-issue-workflow` agents: implement and open the draft PR, playtest in the Unity Editor), `review-unity` (GitHub review), `fix-review-unity` (fixes), PR ready, human merge, cleanup. No `ci` block. Start it with `POST /api/tickets/:key/flow` and the body `{"flow": "perso-delivery"}`.
- `game-code.yaml`, `game-art.yaml`, `game-map.yaml`: the DEV lane. Worktree (the default workspace), several in parallel (`dispatcher.slots`). Claim, `git.worktree`, `git.branch`, produce (`unity-implement` / `art-produce` / `map-produce`; the ticket `track`, `standard` or `bug`, reaches the pipelines from the daemon), loop review <-> fix (2 rounds), then STOP: `ticket.to_test` (label `aidp:to-test`, ticket phase `to-test`), `worktree.remove`, the flow ends `done`. No compile gate and no test in these stages (`verification.compile = "deferred"`).
- `game-test-code.yaml`, `game-test-art.yaml`, `game-test-map.yaml`: the TEST lane, the `test_flow` of the route in `routing.yaml`, started by the dispatcher once the issue is `to-test` and the lane of its project is free (`dispatcher.test_slots`, 1). `workspace: project` (see below): `git.checkout`, loop test (`unity-test` / `art-import` / `map-test`) <-> fix with `report_from: test` (2 rounds), PR ready, `git.restore`, human merge, `done`. `art-import` and `map-test` commit and push the `.meta` files the Editor generates.
- `game-doc.yaml`: `doc-write`, `doc-review` <-> `doc-fix`; worktree, up to the merge, no Unity.

The `game-*` flows share phases (Préparation, Réalisation, Revue, Passage en test, Test Unity, Merge, Nettoyage) and label the issue with `gh.issue_label` (`in-progress`, `review`, `to-test`, `testing`, `awaiting-merge`, `done`, `blocked`). They need the daemon features `gh.issue_label`, `gh.issue_comment`, `gh.pr_ready`, `ticket.to_test`, `unity.refresh` (test flows), the step key `resource`, the `{{ }}` templates in `with` and the outputs `steps.<id>.outputs.{verdict,passed,...}` (C9); `aidp flow validate` on a daemon without them reports exactly those. `routing.yaml` gives each route a `test_flow:` next to its `flow:`.

Workspace of the three `game-test-*` flows (`workspace: project`): no worktree. Every step runs in the main checkout of the project, where the Unity Editor is open.
- `checkout` (`git.checkout`) is the first step. Dirty checkout: output `blocked: true`, then `checkout_label` (`aidp:blocked`), `checkout_comment` (the file list) and `fail` (business, `blocked: dirty-checkout`). Clean: `git switch` to the issue branch (the one the dev flow pushed).
- `refresh` (`unity.refresh`) comes right after: `aidp flow unity-refresh` drops one compile gate request (C1) in the checkout and waits for the result, so the editor's reimport and recompilation of the new branch end before the test stage. Outputs `ok`, `errors`, `warnings`, `duration_ms`, `request_id`. Compile errors are not a stop (the test stage reports them). No Unity project or no editor open on the checkout: the step is skipped (`reason`: `not-a-unity-project` / `unity-editor-closed`) and the test stage decides. Editor silent (no result in 600 s, or a heartbeat `.aidp/editor/heartbeat.json` older than 30 s outside a domain reload): `blocked: true`, then `refresh_label`, `refresh_comment` (the message, with the last heartbeat) and `fail` (business, `blocked: unity-editor`).
- Lock: the run holds the project's `unity-editor` resource from `checkout` until `restore` (`git.restore`, placed before the human merge approval); a second test flow waits `waiting_external` on its `checkout`. When the run ends `escalated`, `failed` or cancelled the daemon runs `git.restore` itself. `git.restore` returns to the base branch only when the checkout is clean; otherwise it leaves it and comments on the issue. Stages never switch branch (`unity-verify.md`: `blocked: unity-branch`).

Daemon facts the flows rely on:


- Pipeline inputs: for a GitHub-mirrored ticket the daemon passes `issue` (the number), `track`, `route` and `feature` to every `pipeline` step itself; no `with: { issue: ... }` is needed. A flow `inputs.track` would not be the ticket track, so none is declared.
- Loops: `max` is a literal 2 (the schema wants a u32) kept equal to `settings.max_*_rounds`. A loop ended by `max` alone escalates the run at once and nothing after it runs, so each `until` also stops on `!(steps.<loop>.iteration < settings.max_*_rounds)`; the steps after the loop then run when the result is not good: label `blocked`, then `fail` with `with: { kind: business, message }`, which ends the run `escalated` (a plain `fail` would end it `failed`, a technical error).
- The last round: a `need-fix` verdict (or a failed test) of the last round is followed by its fix, then no new review; the issue is `blocked` and a human looks.
- Comments: `gh.issue_comment` `with.body` takes `{{ steps.<id>.outputs.<key> }}` (rendered when the step starts; a missing key gives an empty text), `cost_footer: true` appends the cost line.

Always name the flow when you start one: the flow the daemon starts when the request names none
(`ticket-delivery`) is no longer part of this skill.
