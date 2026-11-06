---
description: Setup of ai-dev-pipeline-v7 for the gamedev profile (Unity, Aseprite, Pixellab, GitHub, aidp) — nothing on C: but two config files. Sets the user variables, the Stop hook and the aidp config, installs agents and commands into the Unity project, validates, runs doctor.
argument-hint: "[Unity project folder] [vault folder]"
---

Run the gamedev setup of **ai-dev-pipeline-v7** (Windows, PowerShell 5.1).

Skill root: `D:\AIDP\skill` (the `AIDP_SKILL_ROOT` user variable once the setup ran).

Procedure:

1. Run `powershell -NoProfile -ExecutionPolicy Bypass -File D:\AIDP\skill\setup-gamedev.ps1`, adding
   `-Project "<folder>"` when the user gave the Unity project (or when the current directory holds
   `Assets/` and `ProjectSettings/`), `-Vault "<folder>"` when they gave a vault, and
   `-AidpBin "<folder>"` when `aidp.exe` is not in `D:\AIDP\bin`.
2. Stream the output to the user. Its sections are: paths and binary → user variables → Stop hook →
   aidp config → project agents and commands → validation and doctor.
3. When it finishes:
   - Exit 0: say the setup is complete. Ask the user to open a new terminal or Claude Code session,
     because `AIDP_SKILL_ROOT`, `AIDP_GATEWAY_DIR` and maybe the PATH changed. Then give the next step,
     from the Unity project: `/run-unity-dev-pipeline <issue>` or `/run-pipeline-v7 dev-unity`.
   - Non-zero: surface the `FAIL` lines and suggest `/pipeline-doctor-v7`.

What it does:

- **Nothing on C:** every target path (vault, project, binary folder, daemon state, backups) must be
  on another drive, or the script stops. The only files it writes on C: are `~/.claude/settings.json`
  and `~/.aidp/config.json`, which Claude Code and aidp read only there; their previous versions are
  saved under `D:\AIDP\backup\setup-gamedev\<date>\`.
- **aidp**: it uses the `aidp.exe` already in `-AidpBin` (default `D:\AIDP\bin`); it builds nothing
  and fails when there is none. It adds that folder to the user PATH when missing.
- **User variables**: `AIDP_SKILL_ROOT` (this skill, `D:\AIDP\skill`) and `AIDP_GATEWAY_DIR`
  (`D:\AIDP\gateway`).
- **Hook**: only the Stop hook (`aidp run summary`), merged idempotently. No CI hook.
- **Config**: `~/.aidp/config.json` gets the vault (default `D:\AIDP\Vault`) and `ci.enabled: false`;
  every other key is kept.
- **Agents and commands**: with `-Project`, the four generic agents and every command go to
  `<Project>\.claude\agents` and `<Project>\.claude\commands`, and `aidp setup agents` writes the
  `aidp-<role>-ro` agents there. Without `-Project` they are not installed; `~/.claude` is never
  touched.
- **Checks**: `aidp validate --all`, `aidp flow validate` on every flow, then `aidp doctor`. A red
  `ci_autopilot_hooks` is expected (no CI in this profile) and does not fail the setup.

The Unity skills and agents (`unity-issue-workflow`, `unity-csharp-dev`, `unity-shader-hlsl`, the
`unity-*` and `pixel-*` agents) and the MCP servers (Unity, Aseprite, Pixellab) are not part of this
skill: they are installed separately.
