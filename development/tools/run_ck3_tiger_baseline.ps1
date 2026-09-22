[CmdletBinding()]
param(
    [ValidateSet("Current", "Asil", "Both")]
    [string]$Mode = "Both",
    [string]$ProjectRoot = "",
    [string]$AsilModRoot = "",
    [string]$AsilContentRoot = "",
    [string]$GameRoot = "c:\Program Files (x86)\Steam\steamapps\common\Crusader Kings III",
    [string]$TigerPath = "c:\Users\bsgho\AppData\Roaming\Code\User\globalStorage\unlomtrois.ck3tiger-for-vscode\ck3-tiger\ck3-tiger.exe",
    [string]$CurrentDescriptor = "c:\Users\bsgho\Documents\Paradox Interactive\Crusader Kings III\mod\mbp_vp.mod",
    [string]$ConfigPath = "",
    [string]$OutputDir = "",
    [string]$ClosureInputDir = "",
    [string]$VSCodeTigerJson = "c:\Users\bsgho\AppData\Roaming\Code\User\globalStorage\unlomtrois.ck3tiger-for-vscode\ck3-tiger\tiger.json",
    [switch]$CompareVSCodeLog,
    [switch]$PublishCurrentToVSCodeLog,
    [switch]$SkipClosurePublish
)

$ErrorActionPreference = "Stop"

if (-not $ProjectRoot) {
    $ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
}
if (-not $AsilModRoot) {
    $AsilModRoot = Join-Path (Split-Path $ProjectRoot -Parent) "Leviathonlx MoreBookmarks-Plus"
}
if (-not $AsilContentRoot) {
    $AsilContentRoot = Join-Path $AsilModRoot "BookmarksGit"
}
if (-not $ConfigPath) {
    $ConfigPath = Join-Path $ProjectRoot "BookmarksGit\ck3-tiger.conf"
}
if (-not $OutputDir) {
    $OutputDir = Join-Path $ProjectRoot "development\analysis\generated\tiger_premerge_baseline"
}
if (-not $ClosureInputDir) {
    $ClosureInputDir = Join-Path $ProjectRoot "development\analysis\generated\repo_integration_closure"
}

$currentContentRoot = Join-Path $ProjectRoot "BookmarksGit"
$compareScript = Join-Path $ProjectRoot "development\tools\compare_ck3_tiger_json.py"
$requiredFiles = @($TigerPath, $CurrentDescriptor, $ConfigPath, $compareScript)
foreach ($path in $requiredFiles) {
    if (-not (Test-Path -LiteralPath $path -PathType Leaf)) {
        throw "Required file not found: $path"
    }
}
foreach ($path in @($GameRoot, $currentContentRoot)) {
    if (-not (Test-Path -LiteralPath $path -PathType Container)) {
        throw "Required directory not found: $path"
    }
}

$descriptorText = Get-Content -Raw -LiteralPath $CurrentDescriptor
$descriptorMatch = [regex]::Match($descriptorText, '(?m)^\s*path\s*=\s*"([^"]+)"')
if (-not $descriptorMatch.Success) {
    throw "Current descriptor has no path entry: $CurrentDescriptor"
}
$descriptorTarget = $descriptorMatch.Groups[1].Value -replace '/', '\'
$resolvedDescriptorTarget = (Resolve-Path -LiteralPath $descriptorTarget).Path
$resolvedCurrentRoot = (Resolve-Path -LiteralPath $currentContentRoot).Path
if ($resolvedDescriptorTarget -ne $resolvedCurrentRoot) {
    throw "Current descriptor points outside the live repo: $resolvedDescriptorTarget"
}

New-Item -ItemType Directory -Path $OutputDir -Force | Out-Null

function Invoke-TigerRun {
    param(
        [Parameter(Mandatory)] [string]$Label,
        [Parameter(Mandatory)] [string]$Descriptor,
        [Parameter(Mandatory)] [string]$JsonPath,
        [Parameter(Mandatory)] [string]$StderrPath
    )

    Write-Host "Running CK3-Tiger [$Label]"
    $arguments = @(
        "--ck3", "`"$GameRoot`"",
        "--config", "`"$ConfigPath`"",
        "--json", "`"$Descriptor`""
    )
    $process = Start-Process `
        -FilePath $TigerPath `
        -ArgumentList $arguments `
        -RedirectStandardOutput $JsonPath `
        -RedirectStandardError $StderrPath `
        -WindowStyle Hidden `
        -Wait `
        -PassThru
    if ($process.ExitCode -ne 0) {
        throw "CK3-Tiger [$Label] failed with exit code $($process.ExitCode)"
    }
    $reports = Get-Content -Raw -LiteralPath $JsonPath | ConvertFrom-Json
    [pscustomobject]@{
        Label = $Label
        ReportCount = $reports.Count
        JsonPath = (Resolve-Path -LiteralPath $JsonPath).Path
        JsonSha256 = (Get-FileHash -LiteralPath $JsonPath -Algorithm SHA256).Hash
        StderrPath = (Resolve-Path -LiteralPath $StderrPath).Path
    }
}

$results = @()
$currentJson = Join-Path $OutputDir "ck3_tiger_current.json"
if ($Mode -in @("Current", "Both")) {
    $results += Invoke-TigerRun `
        -Label "current" `
        -Descriptor $CurrentDescriptor `
        -JsonPath $currentJson `
        -StderrPath (Join-Path $OutputDir "ck3_tiger_current.stderr.txt")
}

if ($Mode -in @("Asil", "Both")) {
    if (-not (Test-Path -LiteralPath $AsilContentRoot -PathType Container)) {
        throw "Asil mod content root not found: $AsilContentRoot"
    }
    $asilDescriptor = Join-Path $OutputDir "asil_mod_tiger_generated.mod"
    $descriptorPath = ((Resolve-Path -LiteralPath $AsilContentRoot).Path -replace '\\', '/')
    @(
        'version="audit"'
        'name="asil mod tiger snapshot"'
        'supported_version="*.*.*.*"'
        "path=`"$descriptorPath`""
    ) | Set-Content -LiteralPath $asilDescriptor -Encoding utf8
    $results += Invoke-TigerRun `
        -Label "asil_mod" `
        -Descriptor $asilDescriptor `
        -JsonPath (Join-Path $OutputDir "ck3_tiger_asil_mod.json") `
        -StderrPath (Join-Path $OutputDir "ck3_tiger_asil_mod.stderr.txt")
}

$closureResults = @()
if (-not $SkipClosurePublish) {
    New-Item -ItemType Directory -Path $ClosureInputDir -Force | Out-Null
    foreach ($result in $results) {
        $destinationName = switch ($result.Label) {
            "current" { "ck3_tiger_current.json" }
            "asil_mod" { "ck3_tiger_asil_mod.json" }
            default { throw "Unsupported Tiger result label: $($result.Label)" }
        }
        $sourcePath = (Resolve-Path -LiteralPath $result.JsonPath).Path
        $destinationPath = Join-Path $ClosureInputDir $destinationName
        $sourceFullPath = [System.IO.Path]::GetFullPath($sourcePath)
        $destinationFullPath = [System.IO.Path]::GetFullPath($destinationPath)
        if ($sourceFullPath -ne $destinationFullPath) {
            Copy-Item -LiteralPath $sourcePath -Destination $destinationPath -Force
        }
        $publishedHash = (Get-FileHash -LiteralPath $destinationPath -Algorithm SHA256).Hash
        if ($publishedHash -ne $result.JsonSha256) {
            throw "Closure Tiger JSON hash mismatch for $($result.Label): $destinationPath"
        }
        $closureResults += [pscustomobject]@{
            Label = $result.Label
            JsonPath = (Resolve-Path -LiteralPath $destinationPath).Path
            JsonSha256 = $publishedHash
        }
    }
    Write-Host "Closure input: $ClosureInputDir"
}

if ($CompareVSCodeLog) {
    if ($Mode -eq "Asil") {
        throw "CompareVSCodeLog requires a current Tiger run"
    }
    if (-not (Test-Path -LiteralPath $VSCodeTigerJson -PathType Leaf)) {
        throw "VS Code Tiger JSON not found: $VSCodeTigerJson"
    }
    & python $compareScript `
        --left $currentJson `
        --right $VSCodeTigerJson `
        --left-label "audit_current" `
        --right-label "vscode_current" `
        --output-dir $OutputDir
    if ($LASTEXITCODE -ne 0) {
        throw "Current audit JSON differs from the stable VS Code report set"
    }
}

if ($PublishCurrentToVSCodeLog) {
    if ($Mode -eq "Asil") {
        throw "PublishCurrentToVSCodeLog requires a current Tiger run"
    }
    Copy-Item -LiteralPath $currentJson -Destination $VSCodeTigerJson -Force
    Write-Warning "VS Code log replaced. Run 'ck3tiger: Get problems from the log file' to refresh Problems."
}

$manifest = [ordered]@{
    generated_at = (Get-Date).ToString("o")
    mode = $Mode
    project_root = (Resolve-Path -LiteralPath $ProjectRoot).Path
    project_head = (& git -C $ProjectRoot rev-parse HEAD).Trim()
    upstream_main = (& git -C $ProjectRoot rev-parse upstream/main).Trim()
    asil_mod_head = $(if (Test-Path -LiteralPath (Join-Path $AsilModRoot ".git")) { (& git -C $AsilModRoot rev-parse HEAD).Trim() } else { $null })
    tiger_path = (Resolve-Path -LiteralPath $TigerPath).Path
    tiger_version = (& $TigerPath --version).Trim()
    tiger_sha256 = (Get-FileHash -LiteralPath $TigerPath -Algorithm SHA256).Hash
    game_root = (Resolve-Path -LiteralPath $GameRoot).Path
    config_path = (Resolve-Path -LiteralPath $ConfigPath).Path
    config_sha256 = (Get-FileHash -LiteralPath $ConfigPath -Algorithm SHA256).Hash
    current_descriptor = (Resolve-Path -LiteralPath $CurrentDescriptor).Path
    current_descriptor_target = $resolvedCurrentRoot
    asil_content_root = $(if (Test-Path -LiteralPath $AsilContentRoot) { (Resolve-Path -LiteralPath $AsilContentRoot).Path } else { $null })
    results = $results
    closure_publish_enabled = (-not $SkipClosurePublish)
    closure_input_dir = $(if (-not $SkipClosurePublish) { (Resolve-Path -LiteralPath $ClosureInputDir).Path } else { $null })
    closure_results = $closureResults
}
$manifest | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath (Join-Path $OutputDir "tiger_baseline_manifest.json") -Encoding utf8

$results | Format-Table -AutoSize
Write-Host "Manifest: $(Join-Path $OutputDir 'tiger_baseline_manifest.json')"
