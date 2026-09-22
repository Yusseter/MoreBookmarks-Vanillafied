[CmdletBinding()]
param(
    [string]$ProjectRoot = "",
    [string]$AsilModRoot = "",
    [string]$VanillaRoot = "C:\Program Files (x86)\Steam\steamapps\common\Crusader Kings III\game",
    [string]$PremergeRevision = "09588cbb5",
    [string]$RelationCsv = "",
    [string]$LocatorAuditCsv = "",
    [switch]$SkipControlPng
)

$ErrorActionPreference = "Stop"

if (-not $ProjectRoot) {
    $ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
}
if (-not $AsilModRoot) {
    $AsilModRoot = Join-Path (Split-Path $ProjectRoot -Parent) "Leviathonlx MoreBookmarks-Plus"
}
if (-not $RelationCsv) {
    $RelationCsv = Join-Path $ProjectRoot "development\analysis\generated\province_relation_mapping\current_state_refresh\province_relation_master.csv"
}
if (-not $LocatorAuditCsv) {
    $LocatorAuditCsv = Join-Path $ProjectRoot "development\analysis\generated\map_object_locator_audit\locator_position_audit.csv"
}

$auditScript = Join-Path $ProjectRoot "development\tools\audit_silk_road_market_closure.py"
if (-not (Test-Path -LiteralPath $auditScript -PathType Leaf)) {
    throw "Silk Road market closure audit script not found: $auditScript"
}

$arguments = @(
    $auditScript,
    "--repo-root", $ProjectRoot,
    "--asil-mod-root", $AsilModRoot,
    "--vanilla-root", $VanillaRoot,
    "--premerge-revision", $PremergeRevision,
    "--relation-csv", $RelationCsv,
    "--locator-audit-csv", $LocatorAuditCsv
)
if ($SkipControlPng) {
    $arguments += "--skip-control-png"
}

Write-Host "Project root : $ProjectRoot"
Write-Host "Asil mod     : $AsilModRoot"
Write-Host "Vanilla      : $VanillaRoot"
Write-Host "Relation CSV : $RelationCsv"
Write-Host "Locator CSV  : $LocatorAuditCsv"
Write-Host "Control PNG  : $(-not $SkipControlPng)"

& python @arguments
if ($LASTEXITCODE -ne 0) {
    throw "Silk Road market closure audit failed with exit code $LASTEXITCODE"
}
