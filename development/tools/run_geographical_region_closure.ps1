[CmdletBinding()]
param(
    [string]$ProjectRoot = "",
    [string]$AsilModRoot = "",
    [string]$VanillaRoot = "C:\Program Files (x86)\Steam\steamapps\common\Crusader Kings III\game",
    [string]$PremergeRevision = "09588cbb5",
    [int]$MaxGapProvinces = 20,
    [switch]$SkipGeometry
)

$ErrorActionPreference = "Stop"

if (-not $ProjectRoot) {
    $ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
}
if (-not $AsilModRoot) {
    $AsilModRoot = Join-Path (Split-Path $ProjectRoot -Parent) "Leviathonlx MoreBookmarks-Plus"
}

$auditScript = Join-Path $ProjectRoot "development\tools\audit_geographical_region_closure.py"
if (-not (Test-Path -LiteralPath $auditScript -PathType Leaf)) {
    throw "Region closure audit script not found: $auditScript"
}

$arguments = @(
    $auditScript,
    "--repo-root", $ProjectRoot,
    "--asil-mod-root", $AsilModRoot,
    "--vanilla-root", $VanillaRoot,
    "--premerge-revision", $PremergeRevision,
    "--max-gap-provinces", $MaxGapProvinces
)
if ($SkipGeometry) {
    $arguments += "--skip-geometry"
}

Write-Host "Project root : $ProjectRoot"
Write-Host "Asil mod     : $AsilModRoot"
Write-Host "Vanilla      : $VanillaRoot"
Write-Host "Geometry     : $(-not $SkipGeometry)"

& python @arguments
if ($LASTEXITCODE -ne 0) {
    throw "Geographical region closure audit failed with exit code $LASTEXITCODE"
}
