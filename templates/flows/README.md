# Flow definitions

This directory holds ticket workflow definitions read by the flow engine
(`rtk aidp flow ...`). They are validated against `schema/flow.schema.json`.

They are not v7 pipelines: they carry no `stages:` and must not be run with
`rtk aidp run`. `rtk aidp pipeline list` must not discover them.

## Definitions

- `ticket-delivery.yaml`: the ticket delivery flow, from assignment to worktree cleanup, with CI fix loops, local review, DEV test and human merge.
- `local-delivery.yaml`: the delivery flow of a local ticket: worktree, dev, CI fix loops, local review, optional Copilot review (off by default) and human merge. No Jira step, no DEV deployment, no Teams notification. Start it with `POST /api/tickets/:key/flow` and the body `{"flow": "local-delivery"}`.
- `perso-delivery.yaml`: the delivery flow of a local ticket in a personal GitHub repo with no CI, no Copilot and no Jira: worktree, branch, `dev-unity` (the `unity-issue-workflow` agents: implement and open the PR, GitHub review, fixes), PR ready, human merge, cleanup. No `ci` block. Start it with `{"flow": "perso-delivery"}`; see `docs/perso-profile.md`.
- `test-flow.yaml`: a minimal flow used by tests.
