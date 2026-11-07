# Flow definitions

This directory holds ticket workflow definitions read by the flow engine
(`rtk aidp flow ...`). They are validated against `schema/flow.schema.json`.

They are not v7 pipelines: they carry no `stages:` and must not be run with
`rtk aidp run`. `rtk aidp pipeline list` must not discover them.

## Definitions

- `perso-delivery.yaml`: the delivery flow of a local ticket in a personal GitHub repo with no CI: worktree, branch, `dev-unity` (the `unity-issue-workflow` agents: implement and open the draft PR, playtest in the Unity Editor), `review-unity` (GitHub review), `fix-review-unity` (fixes), PR ready, human merge, cleanup. No `ci` block. Start it with `POST /api/tickets/:key/flow` and the body `{"flow": "perso-delivery"}`.

Always name the flow when you start one: the flow the daemon starts when the request names none
(`ticket-delivery`) is no longer part of this skill.
