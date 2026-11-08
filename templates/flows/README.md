# Flow definitions

This directory holds ticket workflow definitions read by the flow engine
(`rtk aidp flow ...`). They are validated against `schema/flow.schema.json`.

They are not v7 pipelines: they carry no `stages:` and must not be run with
`rtk aidp run`. `rtk aidp pipeline list` must not discover them.

## Definitions

- `perso-delivery.yaml`: the delivery flow of a local ticket in a personal GitHub repo with no CI: worktree, branch, `dev-unity` (the `unity-issue-workflow` agents: implement and open the draft PR, playtest in the Unity Editor), `review-unity` (GitHub review), `fix-review-unity` (fixes), PR ready, human merge, cleanup. No `ci` block. Start it with `POST /api/tickets/:key/flow` and the body `{"flow": "perso-delivery"}`.
- `game-code.yaml`: Unity code issue to merged PR. `git.checkout` (main checkout, no worktree), claim, `unity-implement` (the ticket `track`, `standard` or `bug`, reaches it from the daemon), loop `unity-review` <-> `unity-fix` (2 rounds), loop `unity-test` <-> `unity-fix` with `report_from: test` (2 rounds), PR ready, `git.restore`, human merge, `done`. `workspace: project` (see below).
- `game-art.yaml`: same shape with `art-produce`, `art-review` <-> `art-fix`, then `art-import` (the Unity test, `resource: unity-editor`) <-> `art-fix` (`report_from: test`).
- `game-map.yaml`: same shape with `map-produce`, `map-review` <-> `map-fix`, then `map-test` (`resource: unity-editor`) <-> `map-fix`.
- `game-doc.yaml`: `doc-write`, `doc-review` <-> `doc-fix`; no Unity test (still `workspace: project`).

The four `game-*` flows share phases (Préparation, Réalisation, Revue, Test Unity, Merge, Nettoyage) and label the issue with `gh.issue_label` (`in-progress`, `review`, `testing`, `awaiting-merge`, `done`, `blocked`). They need the daemon features `gh.issue_label`, `gh.issue_comment`, `gh.pr_ready`, the step key `resource`, the `{{ }}` templates in `with` and the outputs `steps.<id>.outputs.{verdict,passed,...}` (C9); `aidp flow validate` on a daemon without them reports exactly those.

Workspace of the four `game-*` flows (`workspace: project`): no worktree. Every step runs in the main checkout of the project, where the Unity Editor is open.
- `checkout` (`git.checkout`) is the first step. Dirty checkout: output `blocked: true`, then `checkout_label` (`aidp:blocked`), `checkout_comment` (the file list) and `fail` (business, `blocked: dirty-checkout`). Clean: `git switch` to the issue branch (created from the base when absent, resumed otherwise).
- Lock: the run holds the project's `unity-editor` resource from `checkout` until `restore` (`git.restore`, placed before the human merge approval); a second flow waits `waiting_external` on its `checkout`. When the run ends `escalated`, `failed` or cancelled the daemon runs `git.restore` itself. `git.restore` returns to the base branch only when the checkout is clean; otherwise it leaves it and comments on the issue. Stages never switch branch (`unity-verify.md`: `blocked: unity-branch`).

Daemon facts the flows rely on:


- Pipeline inputs: for a GitHub-mirrored ticket the daemon passes `issue` (the number), `track`, `route` and `feature` to every `pipeline` step itself; no `with: { issue: ... }` is needed. A flow `inputs.track` would not be the ticket track, so none is declared.
- Loops: `max` is a literal 2 (the schema wants a u32) kept equal to `settings.max_*_rounds`. A loop ended by `max` alone escalates the run at once and nothing after it runs, so each `until` also stops on `!(steps.<loop>.iteration < settings.max_*_rounds)`; the steps after the loop then run when the result is not good: label `blocked`, then `fail` with `with: { kind: business, message }`, which ends the run `escalated` (a plain `fail` would end it `failed`, a technical error).
- The last round: a `need-fix` verdict (or a failed test) of the last round is followed by its fix, then no new review; the issue is `blocked` and a human looks.
- Comments: `gh.issue_comment` `with.body` takes `{{ steps.<id>.outputs.<key> }}` (rendered when the step starts; a missing key gives an empty text), `cost_footer: true` appends the cost line.

Always name the flow when you start one: the flow the daemon starts when the request names none
(`ticket-delivery`) is no longer part of this skill.
