# Flow definitions

This directory holds ticket workflow definitions read by the flow engine
(`rtk aidp flow ...`). They are validated against `schema/flow.schema.json`.

They are not v7 pipelines: they carry no `stages:` and must not be run with
`rtk aidp run`. `rtk aidp pipeline list` must not discover them.

## Definitions

- `perso-delivery.yaml`: the delivery flow of a local ticket in a personal GitHub repo with no CI: worktree, branch, `dev-unity` (the `unity-issue-workflow` agents: implement and open the draft PR, playtest in the Unity Editor), `review-unity` (GitHub review), `fix-review-unity` (fixes), PR ready, human merge, cleanup. No `ci` block. Start it with `POST /api/tickets/:key/flow` and the body `{"flow": "perso-delivery"}`.
- `game-code.yaml`: Unity code issue to merged PR. claim, worktree, branch, `unity-implement` (input `track`: `standard` or `bug`), loop `unity-review` <-> `unity-fix` (2 rounds), loop `unity-test` <-> `unity-fix` with `report_from: test` (2 rounds), PR ready, human merge, `done`, cleanup. Editor steps (`implement`, `fix`, `test`, `fix_test`) carry `resource: unity-editor`.
- `game-art.yaml`: same shape with `art-produce`, `art-review` <-> `art-fix`, then `art-import` (the Unity test, `resource: unity-editor`) <-> `art-fix` (`report_from: test`).
- `game-map.yaml`: same shape with `map-produce`, `map-review` <-> `map-fix`, then `map-test` (`resource: unity-editor`) <-> `map-fix`.
- `game-doc.yaml`: `doc-write`, `doc-review` <-> `doc-fix`; no Unity test, no lock.

The four `game-*` flows share phases (Préparation, Réalisation, Revue, Test Unity, Merge, Nettoyage) and label the issue with `gh.issue_label` (`in-progress`, `review`, `testing`, `awaiting-merge`, `done`, `blocked`). They need the daemon features `gh.issue_label`, `gh.issue_comment`, the step key `resource` and the outputs `steps.<id>.outputs.{verdict,passed,...}` (C9); `aidp flow validate` on a daemon without them reports exactly those. Loop `max` is a literal 2 (the schema wants a u32) and must be kept equal to `settings.max_*_rounds`. A loop left without a good result sets `blocked`, then the `fail` action ends the run.

Always name the flow when you start one: the flow the daemon starts when the request names none
(`ticket-delivery`) is no longer part of this skill.
