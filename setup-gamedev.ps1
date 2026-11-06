# setup-gamedev.ps1 - installation du skill ai-dev-pipeline-v7 pour le profil gamedev (Windows,
# PowerShell 5.1). Profil : Unity, Aseprite et Pixellab (MCP), GitHub (issues, PR), aidp, graphify.
# Pas de Jira, Confluence, Sonar, CI, Teams ni déploiement.
#
# Rien ne s'installe sur C:. Les seuls fichiers écrits sur C: sont les deux fichiers de config que
# Claude Code et aidp ne lisent que là :
#   - ~/.claude/settings.json : le seul hook Stop (`aidp run summary`) ;
#   - ~/.aidp/config.json     : le vault et `ci.enabled = false`, les autres clés gardées.
# Leurs sauvegardes vont sur D: (D:\AIDP\backup\setup-gamedev\<date>\). Tout autre chemin cible
# sur C: est refusé.
#
# Relançable sans effet de bord. Étapes :
#   1. vérifie les chemins et le binaire aidp déjà présent dans -AidpBin (rien n'est compilé) ;
#   2. pose AIDP_SKILL_ROOT et AIDP_GATEWAY_DIR en variables utilisateur, ajoute -AidpBin au PATH
#      utilisateur s'il n'y est pas ;
#   3. ajoute le hook Stop à ~/.claude/settings.json (fusion idempotente) ;
#   4. écrit ~/.aidp/config.json ;
#   5. avec -Project : copie les agents et les commandes du skill dans <Project>\.claude\agents et
#      <Project>\.claude\commands, et y génère les agents aidp-<role>-ro (`aidp setup agents`) ;
#   6. lance `aidp validate --all`, `aidp flow validate` sur chaque flow, puis `aidp doctor`.
#
# Usage : powershell -NoProfile -ExecutionPolicy Bypass -File setup-gamedev.ps1 `
#           [-Vault D:\AIDP\Vault] [-Project D:\CLAUDE_UNITY\<projet>] [-AidpBin D:\AIDP\bin]

param(
    [string]$Vault = 'D:\AIDP\Vault',
    [string]$Project = '',
    [string]$AidpBin = 'D:\AIDP\bin'
)

$ErrorActionPreference = 'Stop'
$skillRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$gatewayDir = 'D:\AIDP\gateway'
$backupRoot = 'D:\AIDP\backup\setup-gamedev'
$claudeSettings = Join-Path $HOME '.claude\settings.json'
$aidpConfig = Join-Path $HOME '.aidp\config.json'
# Contrôles de `aidp doctor` rouges par construction dans ce profil.
$ignoredChecks = @('ci_autopilot_hooks')
$readOnlyAgents = @('aidp-analyzer-ro.md', 'aidp-planner-ro.md', 'aidp-reviewer-ro.md')
$stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
$backupDir = Join-Path $backupRoot $stamp

function Write-Section($title) {
    Write-Host ''
    Write-Host "=== $title ===" -ForegroundColor Cyan
}

function Write-OK($msg)   { Write-Host "  OK    $msg" -ForegroundColor Green }
function Write-Skip($msg) { Write-Host "  SKIP  $msg" -ForegroundColor DarkGray }
function Write-Warn($msg) { Write-Host "  WARN  $msg" -ForegroundColor Yellow }
function Write-Fail($msg) { Write-Host "  FAIL  $msg" -ForegroundColor Red }

# Chemin absolu normalisé (un chemin relatif est résolu depuis le dossier courant).
function Get-FullPath([string]$path) {
    return [IO.Path]::GetFullPath([IO.Path]::Combine((Get-Location).ProviderPath, $path)).TrimEnd('\')
}

# Vrai quand le chemin est sur C: ou sur le disque système, quelle que soit sa lettre.
function Test-OnSystemDrive([string]$path) {
    $full = Get-FullPath $path
    if ($full.StartsWith('\\')) { return $false }
    $drives = @('C:', $env:SystemDrive) | Where-Object { $_ } | ForEach-Object { $_.ToUpperInvariant() }
    return $drives -contains $full.Substring(0, 2).ToUpperInvariant()
}

# Arrête le script quand un chemin cible est sur C:, sauf les deux fichiers de config autorisés.
function Assert-NotOnC([string]$path, [string]$what) {
    $full = Get-FullPath $path
    $allowed = @((Get-FullPath $claudeSettings), (Get-FullPath $aidpConfig))
    if ((Test-OnSystemDrive $full) -and ($allowed -notcontains $full)) {
        Write-Fail "$what est sur C: ($full). Rien ne s'installe sur C: : donne un chemin sur D:."
        exit 1
    }
    return $full
}

# Copie un fichier dans le dossier de sauvegarde sur D:, préfixé par $label. Rien s'il est absent.
function Backup-File([string]$path, [string]$label) {
    if (-not (Test-Path $path)) { return }
    New-Item -ItemType Directory -Force -Path $backupDir | Out-Null
    Copy-Item $path (Join-Path $backupDir "$label-$(Split-Path -Leaf $path)") -Force
}

# Copie un fichier quand la cible est absente ou différente ; une cible remplacée est d'abord
# sauvegardée sur D:. Renvoie $true quand le fichier a été copié.
function Install-File([string]$source, [string]$target, [string]$label) {
    New-Item -ItemType Directory -Force -Path (Split-Path -Parent $target) | Out-Null
    if (Test-Path $target) {
        if ((Get-FileHash $source).Hash -eq (Get-FileHash $target).Hash) { return $false }
        Backup-File $target $label
    }
    Copy-Item $source $target -Force
    return $true
}

# Écrit du JSON en UTF-8 sans BOM : le lecteur JSON d'aidp refuse le BOM.
function Write-Json([string]$path, $value) {
    $json = ConvertTo-Json -InputObject $value -Depth 64
    [IO.File]::WriteAllText($path, $json, (New-Object Text.UTF8Encoding $false))
}

# Pose une variable utilisateur, et la même variable dans ce processus.
function Set-UserVariable([string]$name, [string]$value) {
    if ([Environment]::GetEnvironmentVariable($name, 'User') -ne $value) {
        [Environment]::SetEnvironmentVariable($name, $value, 'User')
    }
    Set-Item -Path "Env:$name" -Value $value
    Write-OK "$name = $value"
}

# 1. Chemins et binaire
Write-Section '1/6  Chemins et binaire'
$skillRoot = Assert-NotOnC $skillRoot 'Le skill'
$Vault = Assert-NotOnC $Vault 'Le vault (-Vault)'
$AidpBin = Assert-NotOnC $AidpBin 'Le dossier du binaire (-AidpBin)'
$gatewayDir = Assert-NotOnC $gatewayDir "L'état du daemon"
$backupDir = Assert-NotOnC $backupDir 'Le dossier des sauvegardes'
if ($Project) {
    $Project = Assert-NotOnC $Project 'Le projet (-Project)'
    if (-not (Test-Path $Project -PathType Container)) {
        Write-Fail "Le projet $Project n'existe pas."
        exit 1
    }
    $isUnity = (Test-Path (Join-Path $Project 'Assets')) -and (Test-Path (Join-Path $Project 'ProjectSettings'))
    if (-not $isUnity) {
        Write-Warn "$Project n'a ni Assets\ ni ProjectSettings\ : ce n'est pas un projet Unity, on continue."
    }
}
$aidp = Join-Path $AidpBin 'aidp.exe'
if (-not (Test-Path $aidp)) {
    Write-Fail "aidp.exe absent de $AidpBin. Compile-le depuis D:\AIDP\src\aidp (toolchain sur D:), copie-le là, puis relance."
    exit 1
}
Write-OK "$(& $aidp --version) : $aidp"
Write-OK "skill : $skillRoot"
$graphify = Get-Command graphify -ErrorAction SilentlyContinue
if ($graphify) {
    Write-OK "graphify : $($graphify.Source)"
} else {
    Write-Warn "graphify absent du PATH : les stages qui lisent le graphe se rabattent sur Grep et Read. Ce script ne l'installe pas."
}

# 2. Variables utilisateur
Write-Section '2/6  Variables utilisateur'
Set-UserVariable 'AIDP_SKILL_ROOT' $skillRoot
New-Item -ItemType Directory -Force -Path $gatewayDir | Out-Null
Set-UserVariable 'AIDP_GATEWAY_DIR' $gatewayDir
$userPath = [Environment]::GetEnvironmentVariable('Path', 'User')
if (-not $userPath) { $userPath = '' }
if (($userPath -split ';') -contains $AidpBin) {
    Write-Skip "$AidpBin déjà dans le PATH utilisateur"
} else {
    [Environment]::SetEnvironmentVariable('Path', ($userPath.TrimEnd(';') + ";$AidpBin").TrimStart(';'), 'User')
    Write-OK "$AidpBin ajouté au PATH utilisateur"
}
if (-not (($env:Path -split ';') -contains $AidpBin)) { $env:Path = "$AidpBin;$env:Path" }

# 3. Hook Stop : aidp calcule la fusion à blanc (--dry-run), ce script l'écrit, si bien
#    qu'aucun settings.json.bak n'atterrit sur C: (la sauvegarde va sur D:).
Write-Section '3/6  Hook Stop'
$example = Join-Path $skillRoot 'hooks\settings.example.json'
$mergeText = (& $aidp setup merge-hooks --example $example --target $claudeSettings --dry-run) | Out-String
if ($LASTEXITCODE -ne 0) {
    Write-Fail "aidp setup merge-hooks --dry-run a échoué (code $LASTEXITCODE)"
    exit 1
}
$merge = $mergeText | ConvertFrom-Json
if ($merge.hooks_added -eq 0) {
    Write-Skip "hook Stop (aidp run summary) déjà présent dans $claudeSettings"
} else {
    Backup-File $claudeSettings 'claude'
    New-Item -ItemType Directory -Force -Path (Split-Path -Parent $claudeSettings) | Out-Null
    Write-Json $claudeSettings $merge.preview
    Write-OK "hook Stop (aidp run summary) ajouté à $claudeSettings"
}

# 4. Config aidp : vault et CI coupée, les autres clés gardées
Write-Section '4/6  Config aidp'
New-Item -ItemType Directory -Force -Path $Vault | Out-Null
$config = [ordered]@{}
if (Test-Path $aidpConfig) {
    $existing = Get-Content $aidpConfig -Raw | ConvertFrom-Json
    foreach ($property in $existing.PSObject.Properties) { $config[$property.Name] = $property.Value }
}
$ci = [ordered]@{}
if ($config.Contains('ci') -and $config['ci']) {
    foreach ($property in $config['ci'].PSObject.Properties) { $ci[$property.Name] = $property.Value }
}
$vaultValue = $Vault -replace '\\', '/'
if (($config['vault'] -eq $vaultValue) -and ($ci['enabled'] -eq $false)) {
    Write-Skip "$aidpConfig déjà à jour : vault $vaultValue, CI coupée"
} else {
    Backup-File $aidpConfig 'aidp'
    $config['vault'] = $vaultValue
    $ci['enabled'] = $false
    $config['ci'] = $ci
    New-Item -ItemType Directory -Force -Path (Split-Path -Parent $aidpConfig) | Out-Null
    Write-Json $aidpConfig $config
    Write-OK "$aidpConfig : vault $vaultValue, CI coupée"
}

# 5. Agents et commandes, dans le projet seulement
Write-Section '5/6  Agents et commandes du projet'
if (-not $Project) {
    Write-Skip "pas de -Project : agents et commandes non installés (~/.claude n'est jamais touché)"
} else {
    $agentsDir = Join-Path $Project '.claude\agents'
    $commandsDir = Join-Path $Project '.claude\commands'
    $changed = 0
    $agents = @(Get-ChildItem -Path (Join-Path $skillRoot 'agents') -Filter '*.md')
    foreach ($agent in $agents) {
        if (Install-File $agent.FullName (Join-Path $agentsDir $agent.Name) 'agents') { $changed++ }
    }
    Write-OK "$($agents.Count) agent(s) dans $agentsDir"
    $commands = @(Get-ChildItem -Path (Join-Path $skillRoot 'commands') -Filter '*.md')
    foreach ($command in $commands) {
        if (Install-File $command.FullName (Join-Path $commandsDir $command.Name) 'commands') { $changed++ }
    }
    Write-OK "$($commands.Count) commande(s) dans $commandsDir"
    foreach ($name in $readOnlyAgents) { Backup-File (Join-Path $agentsDir $name) 'agents' }
    & $aidp setup agents --dest $agentsDir --force | Out-Null
    if ($LASTEXITCODE -ne 0) {
        Write-Fail "aidp setup agents a échoué (code $LASTEXITCODE)"
        exit 1
    }
    Write-OK "agents aidp-<role>-ro générés dans $agentsDir"
    if ($changed -gt 0) { Write-OK "$changed fichier(s) copié(s) ; les versions remplacées sont dans $backupDir" }
}

# 6. Validation et doctor
Write-Section '6/6  Validation et doctor'
& $aidp validate --all | Out-Null
if ($LASTEXITCODE -ne 0) {
    Write-Fail "aidp validate --all a échoué (code $LASTEXITCODE) : lance-le pour le détail"
    exit 1
}
Write-OK 'aidp validate --all : tous les templates sont valides'
$flows = @(Get-ChildItem -Path (Join-Path $skillRoot 'templates\flows') -Filter '*.yaml')
foreach ($flow in $flows) {
    & $aidp flow validate $flow.FullName | Out-Null
    if ($LASTEXITCODE -ne 0) {
        Write-Fail "flow $($flow.Name) invalide : lance aidp flow validate dessus pour le détail"
        exit 1
    }
}
Write-OK "flows valides : $(($flows | ForEach-Object { $_.BaseName }) -join ', ')"
$doctorArgs = @('doctor', '--format', 'json-compact')
if ($Project) { $doctorArgs += @('--workspace-root', $Project) }
$doctor = ((& $aidp @doctorArgs) | Out-String) | ConvertFrom-Json
$failed = @($doctor.checks | Where-Object { -not $_.ok -and $ignoredChecks -notcontains $_.name })
$doctor.checks | Where-Object { $_.ok } | ForEach-Object { Write-OK "$($_.name): $($_.detail)" }
$doctor.checks | Where-Object { -not $_.ok -and $ignoredChecks -contains $_.name } |
    ForEach-Object { Write-Skip "$($_.name) : attendu dans le profil gamedev (pas de CI)" }
$failed | ForEach-Object { Write-Fail "$($_.name): $($_.detail)$(if ($_.fix) { " -> $($_.fix)" })" }

Write-Host ''
if ($failed.Count -eq 0) {
    Write-Host 'Setup gamedev terminé. Ouvre un nouveau terminal ou une nouvelle session Claude Code (variables et PATH changés),' -ForegroundColor Green
    Write-Host 'puis, dans le projet Unity : /run-unity-dev-pipeline <issue> ou /run-pipeline-v7 dev-unity.' -ForegroundColor Green
    exit 0
}
Write-Host "Setup gamedev terminé avec $($failed.Count) contrôle(s) en échec, listés ci-dessus." -ForegroundColor Yellow
Write-Host 'Ouvre un nouveau terminal ou une nouvelle session Claude Code, puis lance /pipeline-doctor-v7.' -ForegroundColor Yellow
exit 1
