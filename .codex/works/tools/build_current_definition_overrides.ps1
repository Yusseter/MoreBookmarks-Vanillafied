param(
    [string]$RepoRoot = '',
    [string]$CurrentDefinitionCsv = '',
    [string]$BaselineDefinitionCsv = '',
    [string]$FinalMasterCsv = '',
    [string]$ModluDefinitionCsv = '',
    [string]$OrijinalDefinitionCsv = '',
    [Alias('ManualLocatorCsv')]
    [string]$LocatorSeedCsv = '',
    [string]$DiffAuditCsv = '',
    [string]$OverrideCandidatesCsv = '',
    [string]$SummaryPath = ''
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

function Ensure-Directory {
    param([string]$Path)

    if (-not (Test-Path -LiteralPath $Path)) {
        New-Item -ItemType Directory -Path $Path -Force | Out-Null
    }
}

function Export-Utf8Csv {
    param(
        $Rows,
        [string]$Path
    )

    Ensure-Directory -Path ([System.IO.Path]::GetDirectoryName($Path))
    @($Rows) | Export-Csv -Path $Path -NoTypeInformation -Encoding utf8
}

function Resolve-Roots {
    param([string]$Root)

    if ([string]::IsNullOrWhiteSpace($Root)) {
        $Root = Join-Path $PSScriptRoot '..\..\..'
    }
    $resolvedRoot = (Resolve-Path -LiteralPath $Root).Path
    $leaf = Split-Path -Leaf $resolvedRoot

    if ($leaf -ieq 'BookmarksGit') {
        $projectRoot = Split-Path -Parent $resolvedRoot
        return [pscustomobject]@{
            ModRoot = $resolvedRoot
            WorksRoot = Join-Path $projectRoot '.codex\works'
        }
    }

    $candidateMod = Join-Path $resolvedRoot 'BookmarksGit'
    $candidateWorks = Join-Path $resolvedRoot '.codex\works'
    if (
        (Test-Path -LiteralPath (Join-Path $candidateMod 'map_data')) -and
        (Test-Path -LiteralPath (Join-Path $candidateWorks 'analysis'))
    ) {
        return [pscustomobject]@{
            ModRoot = $candidateMod
            WorksRoot = $candidateWorks
        }
    }

    if (
        ($leaf -ieq 'works') -and
        ((Split-Path -Leaf (Split-Path -Parent $resolvedRoot)) -ieq '.codex')
    ) {
        $projectRoot = Split-Path -Parent (Split-Path -Parent $resolvedRoot)
        return [pscustomobject]@{
            ModRoot = Join-Path $projectRoot 'BookmarksGit'
            WorksRoot = $resolvedRoot
        }
    }

    throw "Cannot resolve project, BookmarksGit, and .codex/works roots from: $resolvedRoot"
}

function Convert-RgbPartsToString {
    param(
        [string]$R,
        [string]$G,
        [string]$B
    )

    return ('{0},{1},{2}' -f $R.Trim(), $G.Trim(), $B.Trim())
}

function Read-DefinitionFile {
    param([string]$Path)

    $rows = New-Object System.Collections.Generic.List[object]
    $byId = @{}
    $rgbCounts = @{}
    $manualMarkerIds = New-Object 'System.Collections.Generic.HashSet[int]'
    $inManualMarker = $false
    $lineNo = 0

    foreach ($line in [System.IO.File]::ReadLines($Path)) {
        $lineNo += 1
        $hasManualStart = $line -match '#\s*Start of (manual|manuel) locator'
        $hasManualEnd = $line -match '#\s*End of (manual|manuel) locator'
        if ($hasManualStart) {
            $inManualMarker = $true
        }

        $data = ($line -split '#', 2)[0].Trim()
        if (-not [string]::IsNullOrWhiteSpace($data)) {
            $parts = $data.Split(';')
            if ($parts.Count -ge 5) {
                $id = 0
                if ([int]::TryParse($parts[0].Trim(), [ref]$id)) {
                    $rgb = Convert-RgbPartsToString -R $parts[1] -G $parts[2] -B $parts[3]
                    $row = [pscustomobject]@{
                        id = $id
                        rgb = $rgb
                        name = $parts[4].Trim()
                        line = $lineNo
                        raw = $line
                    }
                    $rows.Add($row) | Out-Null
                    $byId[$id] = $row
                    if (-not $rgbCounts.ContainsKey($rgb)) {
                        $rgbCounts[$rgb] = 0
                    }
                    $rgbCounts[$rgb] += 1
                    if ($inManualMarker) {
                        [void]$manualMarkerIds.Add($id)
                    }
                }
            }
        }

        if ($hasManualEnd) {
            $inManualMarker = $false
        }
    }

    return [pscustomobject]@{
        Rows = $rows.ToArray()
        ById = $byId
        RgbCounts = $rgbCounts
        ManualMarkerIds = $manualMarkerIds
    }
}

function Add-SourceRows {
    param(
        [hashtable]$RgbIndex,
        [string]$SourceLabel,
        [string]$Path
    )

    $source = Read-DefinitionFile -Path $Path
    foreach ($row in $source.Rows) {
        if (-not $RgbIndex.ContainsKey($row.rgb)) {
            $RgbIndex[$row.rgb] = New-Object System.Collections.Generic.List[object]
        }
        $RgbIndex[$row.rgb].Add([pscustomobject]@{
            source = $SourceLabel
            id = $row.id
            rgb = $row.rgb
            name = $row.name
        }) | Out-Null
    }
}

function Read-LocatorSeedIds {
    param(
        [string]$Path,
        [System.Collections.Generic.HashSet[int]]$MarkerIds
    )

    Ensure-Directory -Path ([System.IO.Path]::GetDirectoryName($Path))
    if (-not (Test-Path -LiteralPath $Path)) {
        $seedRows = foreach ($id in ($MarkerIds | Sort-Object)) {
            [pscustomobject]@{
                province_id = $id
                reason = 'definition_marker_locator_seed'
            }
        }
        Export-Utf8Csv -Rows $seedRows -Path $Path
    }

    $ids = New-Object 'System.Collections.Generic.HashSet[int]'
    if (Test-Path -LiteralPath $Path) {
        foreach ($row in @(Import-Csv -Path $Path)) {
            if ($null -eq $row.PSObject.Properties['province_id']) {
                continue
            }
            if ([string]::IsNullOrWhiteSpace([string]$row.province_id)) {
                continue
            }
            [void]$ids.Add([int]$row.province_id)
        }
    }
    return $ids
}

function New-OverrideRow {
    param(
        [string]$Action,
        [int]$FinalId,
        [string]$CurrentRgb,
        [string]$CurrentName,
        [object]$MasterRow,
        [object]$SourceMatch,
        [bool]$ManualLocator,
        [string]$Notes
    )

    $sourceOrigin = ''
    $preferredSubset = ''
    $modluId = ''
    $modluRgb = ''
    $modluName = ''
    $orijinalId = ''
    $orijinalRgb = ''
    $orijinalName = ''
    $currentId = ''

    if ($Action -eq 'update_existing_candidate') {
        $sourceOrigin = [string]$MasterRow.source_origin
        $preferredSubset = [string]$MasterRow.preferred_source_subset
        $modluId = [string]$MasterRow.modlu_old_id
        $modluRgb = [string]$MasterRow.modlu_old_rgb
        $modluName = [string]$MasterRow.modlu_old_name
        $orijinalId = [string]$MasterRow.orijinal_old_id
        $orijinalRgb = [string]$MasterRow.orijinal_old_rgb
        $orijinalName = [string]$MasterRow.orijinal_old_name
        $currentId = [string]$MasterRow.current_id
    }
    elseif ($SourceMatch.source -eq 'modlu') {
        $sourceOrigin = 'modlu'
        $preferredSubset = 'modlu_kalan'
        $modluId = [string]$SourceMatch.id
        $modluRgb = [string]$SourceMatch.rgb
        $modluName = [string]$SourceMatch.name
        $currentId = [string]$SourceMatch.id
    }
    elseif ($SourceMatch.source -eq 'orijinal') {
        $sourceOrigin = 'orijinal'
        $preferredSubset = 'orijinal_dogu'
        $orijinalId = [string]$SourceMatch.id
        $orijinalRgb = [string]$SourceMatch.rgb
        $orijinalName = [string]$SourceMatch.name
        $currentId = [string]$SourceMatch.id
    }

    return [pscustomobject]@{
        override_action = $Action
        override_status = 'ready'
        final_new_id = $FinalId
        current_id = $currentId
        effective_rgb = $CurrentRgb
        effective_name = $CurrentName
        candidate_type = if ($Action -eq 'update_existing_candidate') { [string]$MasterRow.candidate_type } else { 'definition_override_promoted_placeholder' }
        source_origin = $sourceOrigin
        preferred_source_subset = $preferredSubset
        modlu_source_id = $modluId
        modlu_source_rgb = $modluRgb
        modlu_source_name = $modluName
        orijinal_source_id = $orijinalId
        orijinal_source_rgb = $orijinalRgb
        orijinal_source_name = $orijinalName
        primary_status = if ($Action -eq 'update_existing_candidate') { [string]$MasterRow.primary_status } else { ('{0}_definition_override' -f $sourceOrigin) }
        rgb_resolution_status = 'definition_override'
        source_id_conflict_status = if ($Action -eq 'update_existing_candidate') { [string]$MasterRow.source_id_conflict_status } else { 'definition_override_exact_rgb' }
        final_id_status = 'definition_override'
        manual_locator = if ($ManualLocator) { 'yes' } else { 'no' }
        notes = $Notes
    }
}

$roots = Resolve-Roots -Root $RepoRoot
$modRoot = $roots.ModRoot
$worksRoot = $roots.WorksRoot
$generatedDir = Join-Path $worksRoot 'analysis\generated\province_definition'

if ([string]::IsNullOrWhiteSpace($CurrentDefinitionCsv)) {
    $CurrentDefinitionCsv = Join-Path $modRoot 'map_data\definition.csv'
}
if ([string]::IsNullOrWhiteSpace($BaselineDefinitionCsv)) {
    $BaselineDefinitionCsv = Join-Path $generatedDir 'definition_birlesim_final_preserve_old.csv'
}
if ([string]::IsNullOrWhiteSpace($FinalMasterCsv)) {
    $FinalMasterCsv = Join-Path $generatedDir 'final_master_preserve_old_ids.csv'
}
if ([string]::IsNullOrWhiteSpace($ModluDefinitionCsv)) {
    $ModluDefinitionCsv = Join-Path $worksRoot 'map_data_sources\definition_modlu.csv'
}
if ([string]::IsNullOrWhiteSpace($OrijinalDefinitionCsv)) {
    $OrijinalDefinitionCsv = Join-Path $worksRoot 'map_data_sources\definition_orijinal.csv'
}
if ([string]::IsNullOrWhiteSpace($LocatorSeedCsv)) {
    $LocatorSeedCsv = Join-Path $worksRoot 'pipeline_inputs\map\definition_marker_locator_seeds.csv'
}
if ([string]::IsNullOrWhiteSpace($DiffAuditCsv)) {
    $DiffAuditCsv = Join-Path $generatedDir 'current_definition_diff_audit.csv'
}
if ([string]::IsNullOrWhiteSpace($OverrideCandidatesCsv)) {
    $OverrideCandidatesCsv = Join-Path $generatedDir 'current_definition_override_candidates.csv'
}
if ([string]::IsNullOrWhiteSpace($SummaryPath)) {
    $SummaryPath = Join-Path $generatedDir 'current_definition_override_summary.md'
}

$currentDefinition = Read-DefinitionFile -Path $CurrentDefinitionCsv
$baselineDefinition = Read-DefinitionFile -Path $BaselineDefinitionCsv
$locatorSeedIds = Read-LocatorSeedIds -Path $LocatorSeedCsv -MarkerIds $currentDefinition.ManualMarkerIds

$masterRows = @(Import-Csv -Path $FinalMasterCsv)
$masterById = @{}
foreach ($row in $masterRows) {
    $masterById[[int]$row.final_new_id] = $row
}

$sourceByRgb = @{}
Add-SourceRows -RgbIndex $sourceByRgb -SourceLabel 'modlu' -Path $ModluDefinitionCsv
Add-SourceRows -RgbIndex $sourceByRgb -SourceLabel 'orijinal' -Path $OrijinalDefinitionCsv

$allIds = New-Object 'System.Collections.Generic.HashSet[int]'
foreach ($id in $currentDefinition.ById.Keys) {
    [void]$allIds.Add([int]$id)
}
foreach ($id in $baselineDefinition.ById.Keys) {
    [void]$allIds.Add([int]$id)
}

$auditRows = New-Object System.Collections.Generic.List[object]
$overrideRows = New-Object System.Collections.Generic.List[object]

foreach ($id in ($allIds | Sort-Object)) {
    $currentRow = $currentDefinition.ById[$id]
    $baselineRow = $baselineDefinition.ById[$id]
    $masterRow = $masterById[$id]

    $kind = 'unchanged'
    if ($null -eq $currentRow) {
        $kind = 'missing_in_current'
    }
    elseif ($null -eq $baselineRow) {
        $kind = 'new_in_current'
    }
    elseif ($currentRow.rgb -ne $baselineRow.rgb -or $currentRow.name -ne $baselineRow.name) {
        if ($null -ne $masterRow -and [string]$masterRow.row_type -eq 'placeholder') {
            $kind = 'promoted_placeholder'
        }
        elseif ($null -ne $masterRow -and [string]$masterRow.row_type -eq 'candidate') {
            $kind = 'changed_candidate'
        }
        else {
            $kind = 'changed_unknown_master'
        }
    }

    if ($kind -eq 'unchanged') {
        continue
    }

    $currentRgb = if ($null -eq $currentRow) { '' } else { [string]$currentRow.rgb }
    $currentName = if ($null -eq $currentRow) { '' } else { [string]$currentRow.name }
    $baselineRgb = if ($null -eq $baselineRow) { '' } else { [string]$baselineRow.rgb }
    $baselineName = if ($null -eq $baselineRow) { '' } else { [string]$baselineRow.name }
    [object[]]$sourceMatches = @()
    if (-not [string]::IsNullOrWhiteSpace($currentRgb) -and $sourceByRgb.ContainsKey($currentRgb)) {
        $sourceMatches = @($sourceByRgb[$currentRgb].ToArray())
    }
    $manualLocator = $locatorSeedIds.Contains([int]$id)
    $duplicateCurrentRgb = (-not [string]::IsNullOrWhiteSpace($currentRgb) -and $currentDefinition.RgbCounts.ContainsKey($currentRgb) -and [int]$currentDefinition.RgbCounts[$currentRgb] -gt 1)

    $overrideStatus = 'audit_only'
    $overrideAction = ''
    $blockerReason = ''

    if ($duplicateCurrentRgb) {
        $overrideStatus = 'blocked_duplicate_current_rgb'
        $blockerReason = 'current_definition_duplicate_rgb'
    }
    elseif ($kind -eq 'changed_candidate') {
        $overrideStatus = 'ready'
        $overrideAction = 'update_existing_candidate'
        $overrideRows.Add((New-OverrideRow -Action $overrideAction -FinalId $id -CurrentRgb $currentRgb -CurrentName $currentName -MasterRow $masterRow -SourceMatch $null -ManualLocator $manualLocator -Notes 'current_definition_changed_existing_candidate')) | Out-Null
    }
    elseif ($kind -eq 'promoted_placeholder') {
        if ($sourceMatches.Count -eq 1) {
            $overrideStatus = 'ready'
            $overrideAction = 'promote_placeholder'
            $overrideRows.Add((New-OverrideRow -Action $overrideAction -FinalId $id -CurrentRgb $currentRgb -CurrentName $currentName -MasterRow $masterRow -SourceMatch $sourceMatches[0] -ManualLocator $manualLocator -Notes 'current_definition_promoted_placeholder')) | Out-Null
        }
        elseif ($sourceMatches.Count -eq 0) {
            $overrideStatus = 'blocked_source_missing'
            $blockerReason = 'no_exact_source_rgb_match'
        }
        else {
            $overrideStatus = 'blocked_source_ambiguous'
            $blockerReason = 'multiple_exact_source_rgb_matches'
        }
    }

    $auditRows.Add([pscustomobject]@{
        final_new_id = $id
        diff_kind = $kind
        override_status = $overrideStatus
        override_action = $overrideAction
        blocker_reason = $blockerReason
        current_rgb = $currentRgb
        current_name = $currentName
        baseline_rgb = $baselineRgb
        baseline_name = $baselineName
        master_row_type = if ($null -eq $masterRow) { '' } else { [string]$masterRow.row_type }
        master_source_origin = if ($null -eq $masterRow) { '' } else { [string]$masterRow.source_origin }
        master_preferred_source_subset = if ($null -eq $masterRow) { '' } else { [string]$masterRow.preferred_source_subset }
        source_exact_rgb_match_count = $sourceMatches.Count
        source_exact_rgb_matches = (($sourceMatches | ForEach-Object { ('{0}:{1}:{2}' -f $_.source, $_.id, $_.name) }) -join ' | ')
        manual_locator = if ($manualLocator) { 'yes' } else { 'no' }
        current_line = if ($null -eq $currentRow) { '' } else { [string]$currentRow.line }
    }) | Out-Null
}

$auditExportRows = @($auditRows | Sort-Object { [int]$_.final_new_id })
$overrideExportRows = @($overrideRows | Sort-Object { [int]$_.final_new_id })
Export-Utf8Csv -Rows $auditExportRows -Path $DiffAuditCsv
Export-Utf8Csv -Rows $overrideExportRows -Path $OverrideCandidatesCsv

$summaryLines = New-Object System.Collections.Generic.List[string]
$summaryLines.Add('# Current Definition Override Summary') | Out-Null
$summaryLines.Add('') | Out-Null
$summaryLines.Add(('- current definition: `{0}`' -f $CurrentDefinitionCsv)) | Out-Null
$summaryLines.Add(('- baseline definition: `{0}`' -f $BaselineDefinitionCsv)) | Out-Null
$summaryLines.Add(('- final master: `{0}`' -f $FinalMasterCsv)) | Out-Null
$summaryLines.Add(('- diff audit csv: `{0}`' -f $DiffAuditCsv)) | Out-Null
$summaryLines.Add(('- override candidates csv: `{0}`' -f $OverrideCandidatesCsv)) | Out-Null
$summaryLines.Add(('- locator seed csv: `{0}`' -f $LocatorSeedCsv)) | Out-Null
$summaryLines.Add('') | Out-Null
$summaryLines.Add('## Diff Counts') | Out-Null
$summaryLines.Add('') | Out-Null
foreach ($group in @($auditExportRows | Group-Object diff_kind | Sort-Object Name)) {
    $summaryLines.Add(('- `{0}`: `{1}`' -f $group.Name, $group.Count)) | Out-Null
}
$summaryLines.Add('') | Out-Null
$summaryLines.Add('## Override Status Counts') | Out-Null
$summaryLines.Add('') | Out-Null
foreach ($group in @($auditExportRows | Group-Object override_status | Sort-Object Name)) {
    $summaryLines.Add(('- `{0}`: `{1}`' -f $group.Name, $group.Count)) | Out-Null
}
$summaryLines.Add('') | Out-Null
$summaryLines.Add('## Locator Seeds') | Out-Null
$summaryLines.Add('') | Out-Null
$summaryLines.Add(('- locator seed province IDs: `{0}`' -f (($locatorSeedIds | Sort-Object) -join ', '))) | Out-Null
$summaryLines.Add(('- manual marker province IDs seen in definition: `{0}`' -f (($currentDefinition.ManualMarkerIds | Sort-Object) -join ', '))) | Out-Null
$summaryLines.Add('') | Out-Null
$summaryLines.Add('## Validation') | Out-Null
$summaryLines.Add('') | Out-Null
$summaryLines.Add(('- current duplicate RGB groups: `{0}`' -f @($currentDefinition.RgbCounts.GetEnumerator() | Where-Object { [int]$_.Value -gt 1 }).Count)) | Out-Null
$summaryLines.Add(('- ready override rows: `{0}`' -f $overrideExportRows.Count)) | Out-Null
$summaryLines.Add(('- blocker rows: `{0}`' -f @($auditExportRows | Where-Object { [string]$_.override_status -like 'blocked_*' }).Count)) | Out-Null

Ensure-Directory -Path ([System.IO.Path]::GetDirectoryName($SummaryPath))
[System.IO.File]::WriteAllLines($SummaryPath, $summaryLines, [System.Text.UTF8Encoding]::new($false))

Write-Output "Built current definition override audit under '$generatedDir'."
