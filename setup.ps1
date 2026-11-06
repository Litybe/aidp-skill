# setup.ps1 — one-shot setup of the ai-dev-pipeline-v7 skill (Windows).
# Builds and installs aidp from its own repository (AIDP_SRC, default C:\CODE\Tools\aidp) through
# that repository's bootstrap, then merges the skill's hooks, installs its slash commands and
# runs doctor against this skill. Idempotent: safe to re-run.

$ErrorActionPreference = 'Stop'
$skillRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$defaultSources = 'C:\CODE\Tools\aidp'
$sourcesRepo = 'https://github.com/AlexisVuk/ai-dev-pipeline-v7'
$sources = if ($env:AIDP_SRC) { $env:AIDP_SRC } else { $defaultSources }
$installDir = if ($env:AIDP_INSTALL_DIR) { $env:AIDP_INSTALL_DIR } else { Join-Path $HOME '.aidp\bin' }
$hooksExample = Join-Path $skillRoot 'hooks\settings.example.json'
$ciHooksExample = Join-Path $skillRoot 'hooks\ci-events.example.json'
$settingsTarget = Join-Path $HOME '.claude\settings.json'

function Write-Section($title) {
    Write-Host ''
    Write-Host "=== $title ===" -ForegroundColor Cyan
}

function Write-OK($msg)   { Write-Host "  OK    $msg" -ForegroundColor Green }
function Write-Skip($msg) { Write-Host "  SKIP  $msg" -ForegroundColor DarkGray }
function Write-Warn($msg) { Write-Host "  WARN  $msg" -ForegroundColor Yellow }
function Write-Fail($msg) { Write-Host "  FAIL  $msg" -ForegroundColor Red }

# 1. aidp, built from its own repository
Write-Section '1/5  aidp'
$bootstrap = Join-Path $sources 'bootstrap.ps1'
if (Test-Path $bootstrap) {
    & powershell -NoProfile -ExecutionPolicy Bypass -File $bootstrap
    if ($LASTEXITCODE -ne 0) {
        Write-Fail "the aidp bootstrap failed (exit $LASTEXITCODE): $bootstrap"
        exit 1
    }
    Write-OK "aidp built and installed from $sources"
} else {
    Write-Warn "no aidp sources at $sources (set AIDP_SRC, or clone $sourcesRepo there)"
}
$aidp = Join-Path $installDir 'aidp.exe'
if (-not (Test-Path $aidp)) {
    $onPath = Get-Command aidp -ErrorAction SilentlyContinue
    if (-not $onPath) {
        Write-Fail "aidp is not installed. Clone $sourcesRepo into $defaultSources (or set AIDP_SRC), then re-run."
        exit 1
    }
    $aidp = $onPath.Source
}
Write-OK "using $aidp"
$env:AIDP_SKILL_ROOT = $skillRoot

# 2. Merge hooks into ~/.claude/settings.json
Write-Section '2/5  Hooks'
if (-not (Test-Path $hooksExample)) {
    Write-Fail "hooks example missing: $hooksExample"
    exit 1
}
& $aidp setup merge-hooks --example $hooksExample --target $settingsTarget
if ($LASTEXITCODE -ne 0) {
    Write-Fail "aidp setup merge-hooks failed (exit $LASTEXITCODE)"
    exit 1
}
if (Test-Path $ciHooksExample) {
    & $aidp setup merge-hooks --example $ciHooksExample --target $settingsTarget
    if ($LASTEXITCODE -ne 0) {
        Write-Warn "CI autopilot hooks not installed (exit $LASTEXITCODE) - the pipelines still work, they just will not start on their own"
    } else {
        Write-OK "CI autopilot hooks installed (aidp ci hook post-tool | stop | prompt)"
    }
} else {
    Write-Skip "no hooks/ci-events.example.json - CI autopilot not installed"
}

# 3. Slash commands: without them the skill is only reachable by name.
Write-Section '3/5  Slash commands'
$commandsSrc = Join-Path $skillRoot 'commands'
$commandsDst = Join-Path $HOME '.claude\commands'
if (Test-Path $commandsSrc) {
    New-Item -ItemType Directory -Force -Path $commandsDst | Out-Null
    $n = 0
    Get-ChildItem -Path $commandsSrc -Filter '*.md' | ForEach-Object {
        Copy-Item $_.FullName -Destination (Join-Path $commandsDst $_.Name) -Force
        $n++
    }
    Write-OK "$n command(s) installed into $commandsDst"
} else {
    Write-Warn "no commands/ directory at $commandsSrc"
}

# 4. Knowledge graph (optional): the pipeline degrades to Grep/Read without it.
Write-Section '4/5  Knowledge graph (optional)'
$graphify = Get-Command graphify -ErrorAction SilentlyContinue
if ($graphify) {
    Write-OK "graphify at $($graphify.Source)"
} else {
    Write-Warn 'graphify CLI not found - knowledge-graph acceleration is off until it is installed.'
    $pip = Get-Command pip -ErrorAction SilentlyContinue
    if (-not $pip) { $pip = Get-Command pip3 -ErrorAction SilentlyContinue }
    if ($pip) {
        Write-Host "  ...   attempting: $($pip.Source) install graphifyy" -ForegroundColor DarkGray
        try {
            & $pip.Source install graphifyy
            $graphify = Get-Command graphify -ErrorAction SilentlyContinue
            if (($LASTEXITCODE -eq 0) -and $graphify) {
                Write-OK "graphify installed at $($graphify.Source)"
            } else {
                Write-Warn 'graphifyy installed but graphify is not on PATH yet. Open a new terminal, or add your Python Scripts dir to PATH.'
            }
        } catch {
            Write-Warn "pip install graphifyy errored: $_. Install manually: pip install graphifyy"
        }
    } else {
        Write-Warn 'pip not found. Install Python, then: pip install graphifyy'
    }
}

# 5. Doctor, against this skill
Write-Section '5/5  Doctor'
& $aidp doctor --format json-pretty
$doctorExit = $LASTEXITCODE

Write-Host ''
if ($doctorExit -eq 0) {
    Write-Host 'Setup complete. Try: /run-pipeline-v7 dev <JIRA-KEY>' -ForegroundColor Green
} else {
    Write-Host 'Setup finished with warnings (see doctor output above).' -ForegroundColor Yellow
    Write-Host 'Open a new terminal or Claude Code session so the new PATH takes effect, then run /pipeline-doctor-v7.' -ForegroundColor Yellow
}
exit $doctorExit
