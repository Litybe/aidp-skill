---
description: One-shot setup for ai-dev-pipeline-v7 — builds and installs aidp from the aidp repository, installs hooks and slash commands, runs doctor.
argument-hint: ""
---

Run the platform-appropriate setup script for **ai-dev-pipeline-v7**.

Skill root: `C:\Users\a.vuk-ext\.claude\skills\ai-dev-pipeline-v7` (or wherever this skill lives on the user's machine).

Procedure:

1. Detect OS:
   - Windows → run `powershell -NoProfile -ExecutionPolicy Bypass -File <skill_root>/setup.ps1`
   - macOS / Linux → run `bash <skill_root>/setup.sh`
2. Stream the script output to the user (it has its own progress sections: aidp → hooks → slash
   commands → knowledge graph → doctor; the aidp section runs the aidp repository's own bootstrap:
   toolchain → build → install → PATH).
3. When it finishes:
   - If exit 0 → run `rtk aidp vault status --format json-pretty` and report where pipeline output will
     land. If `configured` is `false`, offer `rtk aidp vault init --vault <path>` (ask the user for the
     path; on this machine the vault is `C:/CODE/AIDP`). Then: "Setup complete. Try
     `/run-pipeline-v7 dev <JIRA-KEY>` in your project repo."
   - If non-zero → surface the failing section and suggest `/pipeline-doctor-v7` to drill in.

Notes:
- The skill and the binary live in two repositories. This skill holds the templates, agents,
  commands and hooks; `aidp` is built from the **aidp repository**
  (`https://github.com/AlexisVuk/ai-dev-pipeline-v7`), found through `AIDP_SRC`, default
  `C:\CODE\Tools\aidp` (`~/CODE/Tools/aidp` on macOS/Linux).
- If that checkout is missing, the script keeps going with the `aidp` already installed, and stops
  with a clone instruction when there is none. To set it up:
  `rtk git clone https://github.com/AlexisVuk/ai-dev-pipeline-v7 C:\CODE\Tools\aidp`, then re-run.
- The aidp bootstrap runs `rtk cargo build --release -p aidp-cli`, then **copies** the binary (a real
  copy, never a link) into a stable folder: `~/.aidp/bin/` (`%USERPROFILE%\.aidp\bin\aidp.exe` on
  Windows). Set `AIDP_INSTALL_DIR` to use another folder. The copy is written as `aidp(.exe).new`
  first, then renamed atomically.
- That folder, not the repository's `target/release`, is **prepended** to PATH so this binary wins
  over any older `aidp`. On Windows it goes in the user PATH. On macOS/Linux it goes in the shell rc
  block marked `# aidp v7 PATH`. An old PATH entry pointing at a `target/release` folder is removed
  automatically.
- Why: `rtk cargo build` or `rtk cargo clean` in the aidp repository can no longer remove the `aidp` that an
  open session is using.
- To update `aidp`, pull the aidp repository and re-run `/pipeline-setup-v7`. A cargo build alone does
  not update the `aidp` on PATH. Then open a new terminal or Claude Code session, since a running
  session keeps its old PATH.
- `rtk aidp doctor` checks that the installed binary is recent enough for this skill: `SKILL.md` declares
  `min_aidp_version` in its frontmatter. A red `skill_compat` check means the aidp checkout is behind:
  pull it and re-run this setup.
- Windows: if `aidp` is running (another Claude Code session, the gateway daemon, a hook), the install
  fails with an explicit `rtk aidp is in use` message and exit 1. Close those sessions and re-run.
- The script is idempotent. Safe to re-run.
- It modifies `~/.claude/settings.json` (with a `.bak` backup) and the user's shell PATH. Mention this if running for the first time.
- If `cargo` is missing the aidp bootstrap tells the user to install Rust from https://rustup.rs and stops.
- **Two hook sets are installed.** `hooks/settings.example.json` carries a single `Stop` hook (prints
  the run summary) — scope is not enforced live; a stage's write set is checked after the fact by
  `rtk aidp run reconcile` / `rtk aidp scope verify --run <id>`. `hooks/ci-events.example.json` *starts* a
  pipeline — the **CI autopilot** (`aidp ci hook post-tool | stop | prompt`), which reacts to a red
  GitHub Actions build, a red SonarQube gate or new PR review comments by running `gha-fix` /
  `sonar-fix` / `pr-comments` without being asked. Both merges are idempotent. Mention the autopilot
  on a first install, and how to turn it off: `rtk aidp ci config --enable false --save` per repo, or
  `--auto-dispatch false` to keep the reporting without the automatic starts. Full control surface:
  `/ci-autopilot-v7`.
- For the `sonar` signal to work, SonarQube must be reachable:
  `rtk aidp sonar config --host https://sonarqube.betclic.net --save` in the repo, plus `SONAR_TOKEN` in
  the environment (never in the repo). Without it the other two signals still work and
  `rtk aidp ci status` reports the reason. Offer this at the end of a first setup; do not block on it.
- v7 runs live in the Obsidian vault, so hooks that rebuild `.aidp/pipelines/$run_id/…` (v4/v6
  style) no longer resolve — re-running this setup replaces them.
