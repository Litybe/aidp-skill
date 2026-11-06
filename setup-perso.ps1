# setup-perso.ps1 - setup of the ai-dev-pipeline-v7 skill for the personal profile (Windows).
# Same as setup.ps1 without the work tooling: no CI autopilot hooks, no /ci-autopilot-v7, no
# knowledge-graph install. Uses the aidp already installed when its sources are absent, installs
# the generic agents, and writes ~/.aidp/config.json with the CI autopilot off. Idempotent.
#
# Usage: powershell -ExecutionPolicy Bypass -File setup-perso.ps1 [-Vault <vault folder>]

param(
    [string]$Vault = ''
)

$ErrorActionPreference = 'Stop'
$skillRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$defaultSources = 'C:\CODE\Tools\aidp'
$sources = if ($env:AIDP_SRC) { $env:AIDP_SRC } else { $defaultSources }
$aidpHome = Join-Path $HOME '.aidp'
$installDir = if ($env:AIDP_INSTALL_DIR) { $env:AIDP_INSTALL_DIR } else { Join-Path $aidpHome 'bin' }
$claudeDir = Join-Path $HOME '.claude'
$configPath = Join-Path $aidpHome 'config.json'
$defaultVault = Join-Path $HOME 'Documents\AIDP-Vault'
$excludedCommands = @('ci-autopilot-v7.md')
$ignoredChecks = @('ci_autopilot_hooks')
# Only these are validated: the work templates need skills a personal machine does not have.
$personalPipelines = @('dev-unity.yaml')
$personalFlows = @('perso-delivery.yaml')
$stamp = Get-Date -Format 'yyyyMMdd-HHmmss'

function Write-Section($title) {
    Write-Host ''
    Write-Host "=== $title ===" -ForegroundColor Cyan
}

function Write-OK($msg)   { Write-Host "  OK    $msg" -ForegroundColor Green }
function Write-Skip($msg) { Write-Host "  SKIP  $msg" -ForegroundColor DarkGray }
function Write-Warn($msg) { Write-Host "  WARN  $msg" -ForegroundColor Yellow }
function Write-Fail($msg) { Write-Host "  FAIL  $msg" -ForegroundColor Red }

# Copies a file, keeping a .bak-<stamp> of a different target it replaces.
function Install-File($source, $target) {
    New-Item -ItemType Directory -Force -Path (Split-Path -Parent $target) | Out-Null
    if (Test-Path $target) {
        if ((Get-FileHash $source).Hash -eq (Get-FileHash $target).Hash) { return }
        Copy-Item $target "$target.bak-$stamp" -Force
    }
    Copy-Item $source $target -Force
}

# Writes JSON as UTF-8 without a BOM, which aidp's JSON reader refuses.
function Write-Json($path, $value) {
    $json = $value | ConvertTo-Json -Depth 10
    [IO.File]::WriteAllText($path, $json, (New-Object Text.UTF8Encoding $false))
}

# 1. aidp: rebuilt from its sources when they are here, otherwise the copy already installed
Write-Section '1/6  aidp'
$bootstrap = Join-Path $sources 'bootstrap.ps1'
if (Test-Path $bootstrap) {
    & powershell -NoProfile -ExecutionPolicy Bypass -File $bootstrap
    if ($LASTEXITCODE -ne 0) {
        Write-Fail "the aidp bootstrap failed (exit $LASTEXITCODE): $bootstrap"
        exit 1
    }
    Write-OK "aidp built and installed from $sources"
} else {
    Write-Skip "no aidp sources at ${sources}: keeping the installed aidp"
}
$aidp = Join-Path $installDir 'aidp.exe'
if (-not (Test-Path $aidp)) {
    $onPath = Get-Command aidp -ErrorAction SilentlyContinue
    if (-not $onPath) {
        Write-Fail "aidp is not installed: copy aidp.exe into $installDir, or clone its sources into $defaultSources, then re-run."
        exit 1
    }
    $aidp = $onPath.Source
    $installDir = Split-Path -Parent $aidp
}
$userPath = [Environment]::GetEnvironmentVariable('Path', 'User')
if (-not (($userPath -split ';') -contains $installDir)) {
    [Environment]::SetEnvironmentVariable('Path', ($userPath.TrimEnd(';') + ";$installDir"), 'User')
    Write-OK "$installDir added to the user PATH"
}
if (-not (($env:Path -split ';') -contains $installDir)) { $env:Path = "$installDir;$env:Path" }
[Environment]::SetEnvironmentVariable('AIDP_SKILL_ROOT', $skillRoot, 'User')
$env:AIDP_SKILL_ROOT = $skillRoot
Write-OK "$(& $aidp --version) at $aidp, AIDP_SKILL_ROOT = $skillRoot"

# 2. The Stop hook only: no CI autopilot hooks
Write-Section '2/6  Hooks'
& $aidp setup merge-hooks --example (Join-Path $skillRoot 'hooks\settings.example.json') --target (Join-Path $claudeDir 'settings.json')
if ($LASTEXITCODE -ne 0) {
    Write-Fail "aidp setup merge-hooks failed (exit $LASTEXITCODE)"
    exit 1
}
Write-OK 'Stop hook (aidp run summary) installed'
Write-Skip 'CI autopilot hooks not installed (personal profile)'

# 3. Generic agents and slash commands, without /ci-autopilot-v7
Write-Section '3/6  Agents and slash commands'
$agents = Get-ChildItem -Path (Join-Path $skillRoot 'agents') -Filter '*.md'
$agents | ForEach-Object { Install-File $_.FullName (Join-Path $claudeDir "agents\$($_.Name)") }
Write-OK "$($agents.Count) agent(s) installed into $(Join-Path $claudeDir 'agents')"
& $aidp setup agents --force | Out-Null
if ($LASTEXITCODE -ne 0) {
    Write-Fail "aidp setup agents failed (exit $LASTEXITCODE)"
    exit 1
}
Write-OK 'read-only agents (aidp-<role>-ro) generated'
$commands = Get-ChildItem -Path (Join-Path $skillRoot 'commands') -Filter '*.md' |
    Where-Object { $excludedCommands -notcontains $_.Name }
$commands | ForEach-Object { Install-File $_.FullName (Join-Path $claudeDir "commands\$($_.Name)") }
Write-OK "$($commands.Count) command(s) installed into $(Join-Path $claudeDir 'commands')"

# 4. Config: vault and CI autopilot off, other keys kept
Write-Section '4/6  Config'
New-Item -ItemType Directory -Force -Path $aidpHome | Out-Null
$config = [ordered]@{}
if (Test-Path $configPath) {
    Copy-Item $configPath "$configPath.bak-$stamp" -Force
    $existing = Get-Content $configPath -Raw | ConvertFrom-Json
    $existing.PSObject.Properties | ForEach-Object { $config[$_.Name] = $_.Value }
}
if ($Vault) {
    $config['vault'] = $Vault -replace '\\', '/'
} elseif (-not $config.Contains('vault')) {
    $config['vault'] = $defaultVault -replace '\\', '/'
}
New-Item -ItemType Directory -Force -Path $config['vault'] | Out-Null
$ci = [ordered]@{}
if ($config.Contains('ci') -and $config['ci']) {
    $config['ci'].PSObject.Properties | ForEach-Object { $ci[$_.Name] = $_.Value }
}
$ci['enabled'] = $false
$config['ci'] = $ci
Write-Json $configPath $config
Write-OK "$configPath : vault $($config['vault']), CI autopilot off"

# 5. Knowledge graph: not used by the personal pipelines
Write-Section '5/6  Knowledge graph'
Write-Skip 'graphify not installed (personal profile)'

# 6. Validation and doctor
Write-Section '6/6  Doctor'
foreach ($pipeline in $personalPipelines) {
    & $aidp validate (Join-Path $skillRoot "templates\$pipeline") | Out-Null
    if ($LASTEXITCODE -ne 0) {
        Write-Fail "templates\$pipeline is invalid: run aidp validate on it for the details"
        exit 1
    }
}
foreach ($flow in $personalFlows) {
    & $aidp flow validate (Join-Path $skillRoot "templates\flows\$flow") | Out-Null
    if ($LASTEXITCODE -ne 0) {
        Write-Fail "templates\flows\$flow is invalid: run aidp flow validate on it for the details"
        exit 1
    }
}
Write-OK "personal pipelines valid: $($personalPipelines + $personalFlows -join ', ')"
$doctor = (& $aidp doctor --format json-compact) | ConvertFrom-Json
$failed = @($doctor.checks | Where-Object { -not $_.ok -and $ignoredChecks -notcontains $_.name })
$doctor.checks | Where-Object { $_.ok } | ForEach-Object { Write-OK "$($_.name): $($_.detail)" }
$doctor.checks | Where-Object { -not $_.ok -and $ignoredChecks -contains $_.name } |
    ForEach-Object { Write-Skip "$($_.name): expected in the personal profile" }
$failed | ForEach-Object { Write-Fail "$($_.name): $($_.detail)$(if ($_.fix) { " -> $($_.fix)" })" }

Write-Host ''
if ($failed.Count -eq 0) {
    Write-Host 'Personal setup complete. Open a new terminal, then in a Unity repo: /run-pipeline-v7 dev-unity' -ForegroundColor Green
    exit 0
}
Write-Host "Personal setup finished with $($failed.Count) failed check(s), listed above." -ForegroundColor Yellow
Write-Host 'Open a new terminal or Claude Code session so the new PATH takes effect, then run /pipeline-doctor-v7.' -ForegroundColor Yellow
exit 1
