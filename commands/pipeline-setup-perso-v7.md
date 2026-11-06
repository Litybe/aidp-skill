---
description: Setup of ai-dev-pipeline-v7 for the personal profile — no CI autopilot, no Sonar, no knowledge graph. Installs hooks, agents, commands and config, runs doctor.
argument-hint: "[vault folder]"
---

Run the personal setup of **ai-dev-pipeline-v7** (Windows only).

Skill root: `~/.claude/skills/ai-dev-pipeline-v7` (or wherever this skill lives on the user's machine).

Procedure:

1. Run `powershell -NoProfile -ExecutionPolicy Bypass -File <skill_root>/setup-perso.ps1`, adding
   `-Vault "<folder>"` when the user gave a vault folder as argument.
2. Stream the output to the user. Its sections are: aidp → hooks → agents and commands → config →
   knowledge graph (skipped) → doctor.
3. When it finishes:
   - Exit 0: say the setup is complete. Ask the user to open a new terminal or Claude Code session,
     because the PATH and `AIDP_SKILL_ROOT` changed. Then give the next step, from a Unity repo:
     `/run-pipeline-v7 dev-unity`.
   - Non-zero: surface the `FAIL` lines and suggest `/pipeline-doctor-v7`.

What it does, compared with `/pipeline-setup-v7`:

- **aidp**: it rebuilds aidp only when the sources are present (`AIDP_SRC`, default
  `C:\CODE\Tools\aidp`). Otherwise it keeps the installed `~/.aidp/bin/aidp.exe` and fails only
  when there is none. It adds the bin folder to the user PATH and sets `AIDP_SKILL_ROOT`.
- **Hooks**: it installs only the Stop hook (`aidp run summary`), never the CI autopilot hooks.
- **Agents and commands**: it installs the four generic agents and generates the
  `aidp-<role>-ro` ones. It installs every command except `/ci-autopilot-v7`.
- **Config**: it writes `~/.aidp/config.json` with `ci.enabled: false` and keeps every other key.
  The vault is the one given; failing that, the one already configured; failing that,
  `Documents\AIDP-Vault`. The previous file is saved as `config.json.bak-<date>`.
- **Knowledge graph**: no graphify, no Sonar setup.
- **Doctor**: the missing CI autopilot hooks are expected and do not fail the setup.

It turns the CI autopilot off globally. Do not run it on a work machine that relies on the
autopilot. The Unity skills and agents (`unity-issue-workflow`, `unity-csharp-dev`, `unity-shader-hlsl`, the three
`unity-*` agents) are not part of this skill: install them separately, as the personal kit does.
