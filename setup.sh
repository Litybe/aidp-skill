#!/usr/bin/env bash
# setup.sh — one-shot setup of the ai-dev-pipeline-v7 skill (macOS / Linux).
# Builds and installs aidp from its own repository (AIDP_SRC, default ~/CODE/Tools/aidp) through
# that repository's bootstrap, then merges the skill's hooks, installs its slash commands and
# runs doctor against this skill. Idempotent: safe to re-run.

set -e

skill_root="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
sources_repo="https://github.com/AlexisVuk/ai-dev-pipeline-v7"
default_sources="$HOME/CODE/Tools/aidp"
sources="${AIDP_SRC:-$default_sources}"
install_dir="${AIDP_INSTALL_DIR:-$HOME/.aidp/bin}"
hooks_example="$skill_root/hooks/settings.example.json"
ci_hooks_example="$skill_root/hooks/ci-events.example.json"
settings_target="$HOME/.claude/settings.json"

section() { printf '\n=== %s ===\n' "$1"; }
ok()    { printf '  OK    %s\n' "$1"; }
skip()  { printf '  SKIP  %s\n' "$1"; }
warn()  { printf '  WARN  %s\n' "$1"; }
fail()  { printf '  FAIL  %s\n' "$1"; }

# 1. aidp, built from its own repository
section '1/5  aidp'
if [ -f "$sources/bootstrap.sh" ]; then
    bash "$sources/bootstrap.sh"
    ok "aidp built and installed from $sources"
else
    warn "no aidp sources at $sources (set AIDP_SRC, or clone $sources_repo there)"
fi
aidp="$install_dir/aidp"
if [ ! -x "$aidp" ]; then
    if ! aidp="$(command -v aidp)"; then
        fail "aidp is not installed. Clone $sources_repo into $default_sources (or set AIDP_SRC), then re-run."
        exit 1
    fi
fi
ok "using $aidp"
export AIDP_SKILL_ROOT="$skill_root"

# 2. Merge hooks
section '2/5  Hooks'
if [ ! -f "$hooks_example" ]; then
    fail "hooks example missing: $hooks_example"
    exit 1
fi
"$aidp" setup merge-hooks --example "$hooks_example" --target "$settings_target"
if [ -f "$ci_hooks_example" ]; then
    if "$aidp" setup merge-hooks --example "$ci_hooks_example" --target "$settings_target"; then
        ok "CI autopilot hooks installed (aidp ci hook post-tool | stop | prompt)"
    else
        warn "CI autopilot hooks not installed - the pipelines still work, they just will not start on their own"
    fi
else
    skip "no hooks/ci-events.example.json - CI autopilot not installed"
fi

# 3. Slash commands: without them the skill is only reachable by name.
section '3/5  Slash commands'
commands_src="$skill_root/commands"
commands_dst="$HOME/.claude/commands"
if [ -d "$commands_src" ]; then
    mkdir -p "$commands_dst"
    n=0
    for f in "$commands_src"/*.md; do
        [ -e "$f" ] || continue
        cp -f "$f" "$commands_dst/"
        n=$((n + 1))
    done
    ok "$n command(s) installed into $commands_dst"
else
    warn "no commands/ directory at $commands_src"
fi

# 4. Knowledge graph (optional): the pipeline degrades to Grep/Read without it.
section '4/5  Knowledge graph (optional)'
if command -v graphify >/dev/null 2>&1; then
    ok "graphify at $(command -v graphify)"
else
    warn 'graphify CLI not found — knowledge-graph acceleration is off until it is installed.'
    set +e
    pip_bin=""
    if command -v pip >/dev/null 2>&1; then pip_bin=pip
    elif command -v pip3 >/dev/null 2>&1; then pip_bin=pip3
    fi
    if [ -n "$pip_bin" ]; then
        printf '  ...   attempting: %s install graphifyy\n' "$pip_bin"
        "$pip_bin" install graphifyy
        if [ $? -eq 0 ] && command -v graphify >/dev/null 2>&1; then
            ok "graphify installed at $(command -v graphify)"
        else
            warn 'could not install/locate graphify automatically. Install manually: pip install graphifyy (and put its bin dir on PATH).'
        fi
    else
        warn 'pip not found. Install Python, then: pip install graphifyy'
    fi
    set -e
fi

# 5. Doctor, against this skill
section '5/5  Doctor'
set +e
"$aidp" doctor --format json-pretty
doctor_exit=$?
set -e

printf '\n'
if [ "$doctor_exit" -eq 0 ]; then
    printf 'Setup complete. Try: /run-pipeline-v7 dev <JIRA-KEY>\n'
else
    printf 'Setup finished with warnings (see doctor output above).\n'
    printf 'Open a new terminal or session so the new PATH takes effect, then run /pipeline-doctor-v7.\n'
fi
exit $doctor_exit
