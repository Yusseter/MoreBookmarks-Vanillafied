param(
	[switch]$DryRun,
	[switch]$SkipLandedTitles,
	[string]$SourceModRoot = 'F:\Storage\Codding\git\Crusader Kings III\Leviathonlx MoreBookmarks-Plus\BookmarksGit',
	[string]$TitleRelationCsv = '',
	[switch]$SkipCountyCultureReligionOverlay
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
$script:GitPrefix = (((& git rev-parse --show-prefix) 2>$null) | Out-String).Trim()
$script:DryRun = [bool]$DryRun
$script:LiveWriteRows = New-Object System.Collections.Generic.List[object]

function Get-Utf8NoBomEncoding {
	return New-Object System.Text.UTF8Encoding($false)
}

function Read-TextUtf8 {
	param(
		[Parameter(Mandatory = $true)][string]$Path
	)

	$bytes = [System.IO.File]::ReadAllBytes($Path)
	$encoding = Get-Utf8NoBomEncoding
	$text = $encoding.GetString($bytes)
	if ($text.Length -gt 0 -and [int][char]$text[0] -eq 0xFEFF) {
		return $text.Substring(1)
	}
	return $text
}

function Write-TextUtf8 {
	param(
		[Parameter(Mandatory = $true)][string]$Path,
		[Parameter(Mandatory = $true)][string]$Text
	)

	$directory = Split-Path -Parent $Path
	if ($directory -and -not (Test-Path -LiteralPath $directory)) {
		New-Item -ItemType Directory -Path $directory -Force | Out-Null
	}

	$encoding = Get-Utf8NoBomEncoding
	[System.IO.File]::WriteAllText($Path, $Text, $encoding)
}

function Write-LiveTextUtf8 {
	param(
		[Parameter(Mandatory = $true)][string]$Path,
		[Parameter(Mandatory = $true)][string]$Text,
		[Parameter(Mandatory = $true)][string]$Reason
	)

	$status = if ($script:DryRun) { 'dry_run_skipped' } else { 'written' }
	$script:LiveWriteRows.Add([pscustomobject]@{
		path = $Path
		reason = $Reason
		status = $status
		character_count = $Text.Length
	}) | Out-Null

	if ($script:DryRun) {
		return
	}

	Write-TextUtf8 -Path $Path -Text $Text
}

function Read-HeadOrWorkingText {
	param(
		[Parameter(Mandatory = $true)][string]$RelativePath,
		[Parameter(Mandatory = $true)][string]$WorkingPath
	)

	$gitRelativePath = (($script:GitPrefix + ($RelativePath -replace '\\', '/')) -replace '//', '/')
	$psi = New-Object System.Diagnostics.ProcessStartInfo
	$psi.FileName = 'git'
	$psi.Arguments = ('show HEAD:{0}' -f $gitRelativePath)
	$psi.WorkingDirectory = (Get-Location).Path
	$psi.UseShellExecute = $false
	$psi.RedirectStandardOutput = $true
	$psi.RedirectStandardError = $true
	$psi.CreateNoWindow = $true

	$process = New-Object System.Diagnostics.Process
	$process.StartInfo = $psi
	[void]$process.Start()
	$memory = New-Object System.IO.MemoryStream
	$process.StandardOutput.BaseStream.CopyTo($memory)
	$stderr = $process.StandardError.ReadToEnd()
	$process.WaitForExit()

	if ($process.ExitCode -eq 0) {
		$encoding = Get-Utf8NoBomEncoding
		$text = $encoding.GetString($memory.ToArray())
		if ($text.Length -gt 0 -and [int][char]$text[0] -eq 0xFEFF) {
			return $text.Substring(1)
		}
		return $text
	}

	return Read-TextUtf8 -Path $WorkingPath
}

function Read-CsvUtf8 {
	param(
		[Parameter(Mandatory = $true)][string]$Path
	)

	$text = Read-TextUtf8 -Path $Path
	if ([string]::IsNullOrWhiteSpace($text)) {
		return @()
	}
	return $text | ConvertFrom-Csv
}

function Export-CsvUtf8 {
	param(
		[Parameter(Mandatory = $true)]$Rows,
		[Parameter(Mandatory = $true)][string]$Path
	)

	$directory = Split-Path -Parent $Path
	if ($directory -and -not (Test-Path -LiteralPath $directory)) {
		New-Item -ItemType Directory -Path $directory -Force | Out-Null
	}

	$Rows | Export-Csv -Path $Path -NoTypeInformation -Encoding UTF8
}

function Split-Lines {
	param(
		[Parameter(Mandatory = $true)][AllowEmptyString()][string]$Text
	)
	return [System.Text.RegularExpressions.Regex]::Split($Text, "`r?`n")
}

function Strip-LineComment {
	param(
		[Parameter(Mandatory = $true)][AllowEmptyString()][string]$Line
	)

	$index = $Line.IndexOf('#')
	if ($index -lt 0) {
		return $Line
	}
	return $Line.Substring(0, $index)
}

function Get-BraceDelta {
	param(
		[Parameter(Mandatory = $true)][AllowEmptyString()][string]$Line
	)

	$visible = Strip-LineComment -Line $Line
	$opens = ([regex]::Matches($visible, '\{')).Count
	$closes = ([regex]::Matches($visible, '\}')).Count
	return $opens - $closes
}

function Get-TopLevelBlocks {
	param(
		[Parameter(Mandatory = $true)][AllowEmptyString()][string]$Text
	)

	$lines = Split-Lines -Text $Text
	$blocks = New-Object System.Collections.Generic.List[object]
	$inBlock = $false
	$blockName = $null
	$blockStart = -1
	$depth = 0

	for ($i = 0; $i -lt $lines.Length; $i++) {
		$line = $lines[$i]
		if (-not $inBlock) {
			if ($line -match '^\s*([A-Za-z0-9_@:\.\-\?]+)\s*=\s*\{') {
				$blockName = $matches[1]
				$blockStart = $i
				$depth = Get-BraceDelta -Line $line
				if ($depth -le 0) {
					$blockText = ($lines[$blockStart..$i] -join "`r`n")
					$blocks.Add([pscustomobject]@{
						Name = $blockName
						StartIndex = $blockStart
						EndIndex = $i
						Text = $blockText
					})
					$blockName = $null
					$blockStart = -1
					$depth = 0
				}
				else {
					$inBlock = $true
				}
			}
		}
		else {
			$depth += Get-BraceDelta -Line $line
			if ($depth -eq 0) {
				$blockText = ($lines[$blockStart..$i] -join "`r`n")
				$blocks.Add([pscustomobject]@{
					Name = $blockName
					StartIndex = $blockStart
					EndIndex = $i
					Text = $blockText
				})
				$inBlock = $false
				$blockName = $null
				$blockStart = -1
			}
		}
	}

	return $blocks
}

function Remove-TopLevelBlocksAndAppend {
	param(
		[Parameter(Mandatory = $true)][string]$OriginalText,
		[Parameter(Mandatory = $true)][string[]]$RemoveNames,
		[Parameter(Mandatory = $true)][string[]]$AppendBlocks,
		[Parameter(Mandatory = $true)][string]$MarkerComment
	)

	$removeLookup = @{}
	foreach ($name in $RemoveNames) {
		$removeLookup[$name] = $true
	}

	$lines = Split-Lines -Text $OriginalText
	$blocks = Get-TopLevelBlocks -Text $OriginalText
	$skipLine = @{}

	foreach ($block in $blocks) {
		if ($removeLookup.ContainsKey($block.Name)) {
			for ($i = [int]$block.StartIndex; $i -le [int]$block.EndIndex; $i++) {
				$skipLine[$i] = $true
			}
		}
	}

	$outputLines = New-Object System.Collections.Generic.List[string]
	for ($i = 0; $i -lt $lines.Length; $i++) {
		if (-not $skipLine.ContainsKey($i)) {
			$outputLines.Add($lines[$i])
		}
	}

	while ($outputLines.Count -gt 0 -and [string]::IsNullOrWhiteSpace($outputLines[$outputLines.Count - 1])) {
		$outputLines.RemoveAt($outputLines.Count - 1)
	}

	if ($AppendBlocks.Count -gt 0) {
		$outputLines.Add('')
		$outputLines.Add('# -----------------------------------------------------------------------------')
		$outputLines.Add("# $MarkerComment")
		$outputLines.Add('# -----------------------------------------------------------------------------')
		$outputLines.Add('')

		for ($i = 0; $i -lt $AppendBlocks.Count; $i++) {
			foreach ($appendLine in (Split-Lines -Text $AppendBlocks[$i])) {
				$outputLines.Add([string]$appendLine)
			}
			if ($i -lt ($AppendBlocks.Count - 1)) {
				$outputLines.Add('')
			}
		}
	}

	return (($outputLines -join "`r`n").TrimEnd() + "`r`n")
}

function Get-NumericHistoryBlocksFromDirectory {
	param(
		[Parameter(Mandatory = $true)][string]$DirectoryPath
	)

	$map = @{}
	$allBlocksById = @{}
	$duplicateRows = New-Object System.Collections.Generic.List[object]
	$ambiguousRootCultureReligionDuplicateIds = @{}
	$files = Get-ChildItem -Path $DirectoryPath -Filter '*.txt' | Sort-Object Name
	foreach ($file in $files) {
		$text = Read-TextUtf8 -Path $file.FullName
		$blocks = Get-TopLevelBlocks -Text $text
		foreach ($block in $blocks) {
			if ($block.Name -match '^\d+$') {
				$blockEntry = [pscustomobject]@{
					Id = [int]$block.Name
					File = $file.Name
					Text = $block.Text
				}
				if (-not $allBlocksById.ContainsKey($block.Name)) {
					$allBlocksById[$block.Name] = New-Object System.Collections.Generic.List[object]
				}
				$allBlocksById[$block.Name].Add($blockEntry) | Out-Null

				if ($map.ContainsKey($block.Name)) {
					$existingFile = [string]$map[$block.Name].File
					$existingScore = Get-ProvinceHistoryBlockSelectionScore -BlockText ([string]$map[$block.Name].Text)
					$duplicateScore = Get-ProvinceHistoryBlockSelectionScore -BlockText ([string]$block.Text)
					$existingHasRoot = Test-ProvinceHistoryBlockHasRootCultureReligion -BlockText ([string]$map[$block.Name].Text)
					$duplicateHasRoot = Test-ProvinceHistoryBlockHasRootCultureReligion -BlockText ([string]$block.Text)
					$selectedFile = $existingFile
					$selectionReason = 'kept_existing'
					if ($existingHasRoot -and $duplicateHasRoot) {
						$ambiguousRootCultureReligionDuplicateIds[[string]$block.Name] = $true
						$selectionReason = 'ambiguous_root_culture_religion'
					}
					elseif ($duplicateScore -gt $existingScore) {
						$map[$block.Name] = $blockEntry
						$selectedFile = $file.Name
						$selectionReason = 'selected_duplicate_higher_history_score'
					}
					$duplicateRows.Add([pscustomobject]@{
						id = $block.Name
						existing_file = $existingFile
						duplicate_file = $file.Name
						existing_score = $existingScore
						duplicate_score = $duplicateScore
						selected_file = $selectedFile
						selection_reason = $selectionReason
					})
				}
				else {
					$map[$block.Name] = $blockEntry
				}
			}
		}
	}

	return [pscustomobject]@{
		Map = $map
		BlocksById = $allBlocksById
		Duplicates = $duplicateRows
		AmbiguousRootCultureReligionDuplicateIds = @($ambiguousRootCultureReligionDuplicateIds.Keys)
	}
}

function Get-BaronyProvinceMapFromText {
	param(
		[Parameter(Mandatory = $true)][AllowEmptyString()][string]$Text
	)

	$lines = Split-Lines -Text $Text
	$map = @{}
	$inBarony = $false
	$baronyName = ''
	$depth = 0

	for ($i = 0; $i -lt $lines.Length; $i++) {
		$line = $lines[$i]
		if (-not $inBarony) {
			if ($line -match '^\s*(b_[A-Za-z0-9_-]+)\s*=\s*\{') {
				$inBarony = $true
				$baronyName = $matches[1]
				$depth = Get-BraceDelta -Line $line
				if ($depth -le 0) {
					$inBarony = $false
					$baronyName = ''
				}
			}
		}
		else {
			if ($line -match '^\s*province\s*=\s*(\d+)') {
				if (-not $map.ContainsKey($baronyName)) {
					$map[$baronyName] = [int]$matches[1]
				}
			}
			$depth += Get-BraceDelta -Line $line
			if ($depth -eq 0) {
				$inBarony = $false
				$baronyName = ''
			}
		}
	}

	return $map
}

function Remove-NestedBlocksByName {
	param(
		[Parameter(Mandatory = $true)][AllowEmptyString()][string]$Text,
		[Parameter(Mandatory = $true)][string[]]$Names
	)

	if ($Names.Count -eq 0) {
		return $Text
	}

	$nameLookup = @{}
	foreach ($name in $Names) {
		$nameLookup[$name] = $true
	}

	$lines = Split-Lines -Text $Text
	$output = New-Object System.Collections.Generic.List[string]
	$skipping = $false
	$depth = 0

	for ($i = 0; $i -lt $lines.Length; $i++) {
		$line = $lines[$i]
		if (-not $skipping) {
			if ($line -match '^\s*([A-Za-z0-9_@:\.\-\?]+)\s*=\s*\{') {
				$name = $matches[1]
				if ($nameLookup.ContainsKey($name)) {
					$skipping = $true
					$depth = Get-BraceDelta -Line $line
					if ($depth -le 0) {
						$skipping = $false
						$depth = 0
					}
					continue
				}
			}
			$output.Add($line)
		}
		else {
			$depth += Get-BraceDelta -Line $line
			if ($depth -eq 0) {
				$skipping = $false
				$depth = 0
			}
		}
	}

	return ($output -join "`r`n")
}

function Rewrite-LandedTitleBlockProvinceIds {
	param(
		[Parameter(Mandatory = $true)][string]$BlockText,
		[Parameter(Mandatory = $true)][string]$Root,
		[Parameter(Mandatory = $true)]$VanillaOldToFinal,
		[Parameter(Mandatory = $true)]$ModBaronyProvinceMap,
		[Parameter(Mandatory = $true)]$ReportRows
	)

	$lines = Split-Lines -Text $BlockText
	$output = New-Object System.Collections.Generic.List[string]
	$inBarony = $false
	$baronyName = ''
	$depth = 0
	$missingBaronies = New-Object System.Collections.Generic.List[string]

	for ($i = 0; $i -lt $lines.Length; $i++) {
		$line = $lines[$i]
		if (-not $inBarony) {
			if ($line -match '^\s*(b_[A-Za-z0-9_]+)\s*=\s*\{') {
				$inBarony = $true
				$baronyName = $matches[1]
				$depth = Get-BraceDelta -Line $line
			}
			$output.Add($line)
			if ($inBarony -and $depth -le 0) {
				$inBarony = $false
				$baronyName = ''
			}
		}
		else {
			if ($line -match '^(\s*province\s*=\s*)(\d+)(\s*(#.*)?)$') {
				$oldId = [int]$matches[2]
				if ($VanillaOldToFinal.ContainsKey($oldId)) {
					$newId = $VanillaOldToFinal[$oldId]
					$ReportRows.Add([pscustomobject]@{
						root = $Root
						barony = $baronyName
						old_vanilla_id = $oldId
						final_new_id = $newId
						status = 'rewritten'
					})
					$line = $matches[1] + $newId + $matches[3]
				}
				elseif ($ModBaronyProvinceMap.ContainsKey($baronyName)) {
					$newId = $ModBaronyProvinceMap[$baronyName]
					$ReportRows.Add([pscustomobject]@{
						root = $Root
						barony = $baronyName
						old_vanilla_id = $oldId
						final_new_id = $newId
						status = 'fallback_mod_barony'
					})
					$line = $matches[1] + $newId + $matches[3]
				}
				else {
					$ReportRows.Add([pscustomobject]@{
						root = $Root
						barony = $baronyName
						old_vanilla_id = $oldId
						final_new_id = ''
						status = 'missing_mapping_barony_removed'
					})
					if (-not $missingBaronies.Contains($baronyName)) {
						$missingBaronies.Add($baronyName)
					}
				}
			}

			$output.Add($line)
			$depth += Get-BraceDelta -Line $line
			if ($depth -eq 0) {
				$inBarony = $false
				$baronyName = ''
			}
		}
	}

	$rewritten = ($output -join "`r`n")
	if ($missingBaronies.Count -gt 0) {
		return Remove-NestedBlocksByName -Text $rewritten -Names $missingBaronies.ToArray()
	}
	return $rewritten
}

function Rewrite-ProvinceHistoryBlockId {
	param(
		[Parameter(Mandatory = $true)][string]$BlockText,
		[Parameter(Mandatory = $true)][int]$NewId
	)

	$lines = Split-Lines -Text $BlockText
	if ($lines.Length -eq 0) {
		return $BlockText
	}
	if ($lines[0] -match '^(\s*)\d+(\s*=\s*\{.*)$') {
		$lines[0] = $matches[1] + $NewId + $matches[2]
	}
	return ($lines -join "`r`n")
}

function Get-CsvField {
	param(
		[Parameter(Mandatory = $true)]$Row,
		[Parameter(Mandatory = $true)][string]$Name
	)

	foreach ($property in $Row.PSObject.Properties) {
		if ($property.Name.Trim() -eq $Name) {
			return ([string]$property.Value).Trim()
		}
	}
	return ''
}

function Normalize-TitleId {
	param([Parameter(Mandatory = $true)][AllowEmptyString()][string]$Value)

	$trimmed = $Value.Trim()
	if ($trimmed -match '([ekdcbh]_[A-Za-z0-9_-]+)') {
		return [string]$matches[1]
	}
	return $trimmed
}

function Get-CountyFirstBaronyMap {
	param(
		[Parameter(Mandatory = $true)][AllowEmptyString()][string]$LandedTitlesText
	)

	$lines = Split-Lines -Text $LandedTitlesText
	$map = @{}
	$titleStack = New-Object System.Collections.Generic.List[object]
	$depth = 0

	for ($i = 0; $i -lt $lines.Length; $i++) {
		$line = $lines[$i]
		$visible = Strip-LineComment -Line $line
		$delta = Get-BraceDelta -Line $line

		if ($visible -match '^\s*([a-z]_[A-Za-z0-9_-]+)\s*=\s*\{') {
			$titleName = [string]$matches[1]
			$parent = if ($titleStack.Count -gt 0) { $titleStack[$titleStack.Count - 1] } else { $null }

			if ($titleName -match '^c_') {
				if (-not $map.ContainsKey($titleName)) {
					$map[$titleName] = [pscustomobject]@{
						county = $titleName
						first_barony = ''
						first_province_id = ''
						status = 'missing_first_barony'
						line_index = $i + 1
					}
				}
			}
			elseif ($titleName -match '^b_' -and $null -ne $parent -and ([string]$parent.Name) -match '^c_') {
				$countyName = [string]$parent.Name
				if (-not $map.ContainsKey($countyName)) {
					$map[$countyName] = [pscustomobject]@{
						county = $countyName
						first_barony = ''
						first_province_id = ''
						status = 'missing_first_barony'
						line_index = $i + 1
					}
				}
				if ([string]::IsNullOrWhiteSpace([string]$map[$countyName].first_barony)) {
					$map[$countyName].first_barony = $titleName
					$map[$countyName].status = 'missing_first_barony_province'
				}
			}

			if ($delta -gt 0) {
				$parentCounty = ''
				if ($titleName -match '^c_') {
					$parentCounty = $titleName
				}
				elseif ($titleName -match '^b_' -and $null -ne $parent -and ([string]$parent.Name) -match '^c_') {
					$parentCounty = [string]$parent.Name
				}
				elseif ($null -ne $parent) {
					$parentCounty = [string]$parent.ParentCounty
				}

				$titleStack.Add([pscustomobject]@{
					Name = $titleName
					ParentCounty = $parentCounty
					CloseDepth = $depth
				}) | Out-Null
			}
		}

		if ($visible -match '^\s*province\s*=\s*(\d+)\s*$' -and $titleStack.Count -gt 0) {
			$provinceId = [string]$matches[1]
			$currentTitle = $titleStack[$titleStack.Count - 1]
			if (([string]$currentTitle.Name) -match '^b_' -and -not [string]::IsNullOrWhiteSpace([string]$currentTitle.ParentCounty)) {
				$countyName = [string]$currentTitle.ParentCounty
				if ($map.ContainsKey($countyName) -and [string]$map[$countyName].first_barony -eq [string]$currentTitle.Name -and [string]::IsNullOrWhiteSpace([string]$map[$countyName].first_province_id)) {
					$map[$countyName].first_province_id = $provinceId
					$map[$countyName].status = 'ok'
				}
			}
		}

		$depth += $delta
		while ($titleStack.Count -gt 0 -and [int]$titleStack[$titleStack.Count - 1].CloseDepth -ge $depth) {
			$titleStack.RemoveAt($titleStack.Count - 1)
		}
	}

	return $map
}

function Get-CultureReligionTimeline {
	param(
		[Parameter(Mandatory = $true)][AllowEmptyString()][string]$BlockText
	)

	$root = @{}
	$dates = @{}
	$lines = Split-Lines -Text $BlockText
	$depth = 0
	$currentDate = ''
	$dateCloseDepth = -1

	for ($i = 0; $i -lt $lines.Length; $i++) {
		$line = $lines[$i]
		$visible = Strip-LineComment -Line $line
		$delta = Get-BraceDelta -Line $line

		if ($depth -eq 1 -and $visible -match '^\s*(culture|religion)\s*=\s*([A-Za-z0-9_\.\-:]+)\s*$') {
			$root[[string]$matches[1]] = [string]$matches[2]
		}

		if ($depth -eq 1 -and $visible -match '^\s*(\d{3,4}\.\d{1,2}\.\d{1,2})\s*=\s*\{') {
			$currentDate = [string]$matches[1]
			$dateCloseDepth = 1
			if (-not $dates.ContainsKey($currentDate)) {
				$dates[$currentDate] = @{}
			}
		}
		elseif (-not [string]::IsNullOrWhiteSpace($currentDate) -and $depth -eq 2 -and $visible -match '^\s*(culture|religion)\s*=\s*([A-Za-z0-9_\.\-:]+)\s*$') {
			$dates[$currentDate][[string]$matches[1]] = [string]$matches[2]
		}

		$depth += $delta
		if (-not [string]::IsNullOrWhiteSpace($currentDate) -and $depth -le $dateCloseDepth) {
			$currentDate = ''
			$dateCloseDepth = -1
		}
	}

	return @{
		Root = $root
		Dates = $dates
	}
}

function Test-ProvinceHistoryBlockHasRootCultureReligion {
	param(
		[Parameter(Mandatory = $true)][AllowEmptyString()][string]$BlockText
	)

	$timeline = Get-CultureReligionTimeline -BlockText $BlockText
	return ($timeline.Root.ContainsKey('culture') -and $timeline.Root.ContainsKey('religion'))
}

function Get-ProvinceHistoryBlockSelectionScore {
	param(
		[Parameter(Mandatory = $true)][AllowEmptyString()][string]$BlockText
	)

	$timeline = Get-CultureReligionTimeline -BlockText $BlockText
	$score = 0
	if ($timeline.Root.ContainsKey('culture')) {
		$score += 100
	}
	if ($timeline.Root.ContainsKey('religion')) {
		$score += 100
	}
	foreach ($date in $timeline.Dates.Keys) {
		if ($timeline.Dates[$date].ContainsKey('culture')) {
			$score += 10
		}
		if ($timeline.Dates[$date].ContainsKey('religion')) {
			$score += 10
		}
	}
	$score += [Math]::Min(9, [int]([Math]::Floor($BlockText.Length / 1000)))
	return $score
}

function Get-ProvinceHistoryBlockCommentTitle {
	param(
		[Parameter(Mandatory = $true)][AllowEmptyString()][string]$BlockText
	)

	$lines = Split-Lines -Text $BlockText
	if ($lines.Length -gt 0 -and $lines[0] -match '#\s*([a-z]_[A-Za-z0-9_-]+)') {
		return [string]$matches[1]
	}
	return ''
}

function Get-OverlaySourceHistoryOverrideMap {
	param(
		[Parameter(Mandatory = $true)][AllowEmptyString()][string]$Path
	)

	$map = @{}
	if ([string]::IsNullOrWhiteSpace($Path) -or -not (Test-Path -LiteralPath $Path)) {
		return $map
	}

	foreach ($row in (Read-CsvUtf8 -Path $Path)) {
		$targetCounty = Normalize-TitleId -Value (Get-CsvField -Row $row -Name 'target_county')
		$sourceCounty = Normalize-TitleId -Value (Get-CsvField -Row $row -Name 'source_county')
		$sourceProvinceId = Get-CsvField -Row $row -Name 'source_province_id'
		$rootCulture = Get-CsvField -Row $row -Name 'root_culture'
		$rootReligion = Get-CsvField -Row $row -Name 'root_religion'
		if ([string]::IsNullOrWhiteSpace($targetCounty) -or [string]::IsNullOrWhiteSpace($sourceCounty) -or [string]::IsNullOrWhiteSpace($sourceProvinceId)) {
			continue
		}
		$key = '{0}|{1}|{2}' -f $targetCounty, $sourceCounty, $sourceProvinceId
		$map[$key] = [pscustomobject]@{
			target_county = $targetCounty
			source_county = $sourceCounty
			source_province_id = $sourceProvinceId
			root_culture = $rootCulture
			root_religion = $rootReligion
		}
	}

	return $map
}

function Resolve-ProvinceHistoryBlockForOverlay {
	param(
		[Parameter(Mandatory = $true)]$HistoryData,
		[Parameter(Mandatory = $true)][string]$ProvinceId,
		[Parameter(Mandatory = $true)][AllowEmptyString()][string]$SourceBarony,
		[Parameter(Mandatory = $true)][AllowEmptyString()][string]$TargetCounty,
		[Parameter(Mandatory = $true)][AllowEmptyString()][string]$SourceCounty,
		[Parameter(Mandatory = $true)]$OverrideMap
	)

	$blocksById = $HistoryData.PSObject.Properties['BlocksById'].Value
	if ($null -eq $blocksById -or -not $blocksById.ContainsKey($ProvinceId)) {
		return [pscustomobject]@{
			Status = 'missing'
			Block = $null
		}
	}

	$allBlocks = @()
	foreach ($block in $blocksById.Item($ProvinceId)) {
		$allBlocks += $block
	}
	$rootBlocks = @($allBlocks | Where-Object { Test-ProvinceHistoryBlockHasRootCultureReligion -BlockText ([string]$_.Text) })
	if ($rootBlocks.Count -eq 0) {
		return [pscustomobject]@{
			Status = 'ok'
			Block = $allBlocks[0]
		}
	}
	if ($rootBlocks.Count -eq 1) {
		return [pscustomobject]@{
			Status = 'ok'
			Block = $rootBlocks[0]
		}
	}

	$overrideKey = '{0}|{1}|{2}' -f $TargetCounty, $SourceCounty, $ProvinceId
	if ($OverrideMap.ContainsKey($overrideKey)) {
		$override = $OverrideMap[$overrideKey]
		$overrideMatches = @($rootBlocks | Where-Object {
			$timeline = Get-CultureReligionTimeline -BlockText ([string]$_.Text)
			$timeline.Root.ContainsKey('culture') -and
			$timeline.Root.ContainsKey('religion') -and
			[string]$timeline.Root['culture'] -eq [string]$override.root_culture -and
			[string]$timeline.Root['religion'] -eq [string]$override.root_religion
		})
		if ($overrideMatches.Count -eq 1) {
			return [pscustomobject]@{
				Status = 'ok'
				Block = $overrideMatches[0]
			}
		}
		if ($overrideMatches.Count -eq 0) {
			return [pscustomobject]@{
				Status = 'override_no_matching_source_history_block'
				Block = $rootBlocks[0]
			}
		}
		return [pscustomobject]@{
			Status = 'override_ambiguous_source_history_block'
			Block = $overrideMatches[0]
		}
	}

	$baronyMatches = @($rootBlocks | Where-Object { (Get-ProvinceHistoryBlockCommentTitle -BlockText ([string]$_.Text)) -eq $SourceBarony })
	if ($baronyMatches.Count -eq 1) {
		return [pscustomobject]@{
			Status = 'ok'
			Block = $baronyMatches[0]
		}
	}

	return [pscustomobject]@{
		Status = 'ambiguous_root_culture_religion_duplicate'
		Block = $rootBlocks[0]
	}
}

function Get-DateBlockInfoByStart {
	param(
		[Parameter(Mandatory = $true)][AllowEmptyString()][string[]]$Lines
	)

	$byStart = @{}
	$depth = 0
	$inDate = $false
	$dateName = ''
	$dateStart = -1
	$dateCloseDepth = -1
	$hasNonCultureReligionContent = $false

	for ($i = 0; $i -lt $Lines.Length; $i++) {
		$line = $Lines[$i]
		$visible = Strip-LineComment -Line $line
		$trimmedVisible = $visible.Trim()
		$delta = Get-BraceDelta -Line $line

		if (-not $inDate -and $depth -eq 1 -and $visible -match '^\s*(\d{3,4}\.\d{1,2}\.\d{1,2})\s*=\s*\{') {
			$inDate = $true
			$dateName = [string]$matches[1]
			$dateStart = $i
			$dateCloseDepth = 1
			$hasNonCultureReligionContent = $false
		}
		elseif ($inDate -and $i -gt $dateStart -and $depth -ge 2) {
			if ($trimmedVisible -ne '' -and $trimmedVisible -ne '}' -and $trimmedVisible -notmatch '^(culture|religion)\s*=') {
				$hasNonCultureReligionContent = $true
			}
		}

		$depth += $delta
		if ($inDate -and $depth -le $dateCloseDepth) {
			$byStart[$dateStart] = [pscustomobject]@{
				Date = $dateName
				StartIndex = $dateStart
				EndIndex = $i
				HasNonCultureReligionContent = $hasNonCultureReligionContent
			}
			$inDate = $false
			$dateName = ''
			$dateStart = -1
			$dateCloseDepth = -1
			$hasNonCultureReligionContent = $false
		}
	}

	return $byStart
}

function Set-CultureReligionTimelineOnProvinceBlock {
	param(
		[Parameter(Mandatory = $true)][AllowEmptyString()][string]$BlockText,
		[Parameter(Mandatory = $true)]$Timeline
	)

	$lines = Split-Lines -Text $BlockText
	if ($lines.Length -eq 0) {
		return $BlockText
	}

	$rootExisting = @{}
	$existingDates = @{}
	$dateBlockByStart = Get-DateBlockInfoByStart -Lines $lines
	$rootIndent = "`t"
	$dateInnerIndent = "`t`t"
	$depth = 0

	for ($i = 0; $i -lt $lines.Length; $i++) {
		$visible = Strip-LineComment -Line $lines[$i]
		if ($depth -eq 1 -and $visible -match '^(\s*)(culture|religion)\s*=') {
			$rootExisting[[string]$matches[2]] = $true
			$rootIndent = [string]$matches[1]
		}
		if ($depth -eq 1 -and $visible -match '^\s*(\d{3,4}\.\d{1,2}\.\d{1,2})\s*=\s*\{') {
			$existingDates[[string]$matches[1]] = $true
		}
		if ($depth -eq 2 -and $visible -match '^(\s*)(culture|religion)\s*=') {
			$dateInnerIndent = [string]$matches[1]
		}
		$depth += Get-BraceDelta -Line $lines[$i]
	}

	$output = New-Object System.Collections.Generic.List[string]
	$rootWritten = @{}
	$dateWritten = @{}
	$depth = 0
	$currentDate = ''
	$dateCloseDepth = -1
	$i = 0

	while ($i -lt $lines.Length) {
		$line = $lines[$i]
		$visible = Strip-LineComment -Line $line
		$delta = Get-BraceDelta -Line $line

		if ($dateBlockByStart.ContainsKey($i)) {
			$dateInfo = $dateBlockByStart[$i]
			if (-not $Timeline.Dates.ContainsKey([string]$dateInfo.Date) -and -not [bool]$dateInfo.HasNonCultureReligionContent) {
				$i = [int]$dateInfo.EndIndex + 1
				continue
			}
		}

		if ($depth -eq 1 -and $visible -match '^\s*(\d{3,4}\.\d{1,2}\.\d{1,2})\s*=\s*\{') {
			$currentDate = [string]$matches[1]
			$dateCloseDepth = 1
			if (-not $dateWritten.ContainsKey($currentDate)) {
				$dateWritten[$currentDate] = @{}
			}
		}

		if ($depth -eq 1 -and $visible -match '^(\s*)(culture|religion)\s*=\s*([A-Za-z0-9_\.\-:]+)\s*$') {
			$key = [string]$matches[2]
			if ($Timeline.Root.ContainsKey($key)) {
				$output.Add(('{0}{1} = {2}' -f $matches[1], $key, $Timeline.Root[$key])) | Out-Null
				$rootWritten[$key] = $true
			}
			$i++
			continue
		}

		if (-not [string]::IsNullOrWhiteSpace($currentDate) -and $depth -eq 2 -and $visible -match '^(\s*)(culture|religion)\s*=\s*([A-Za-z0-9_\.\-:]+)\s*$') {
			$key = [string]$matches[2]
			if ($Timeline.Dates.ContainsKey($currentDate) -and $Timeline.Dates[$currentDate].ContainsKey($key)) {
				$output.Add(('{0}{1} = {2}' -f $matches[1], $key, $Timeline.Dates[$currentDate][$key])) | Out-Null
				$dateWritten[$currentDate][$key] = $true
			}
			$i++
			continue
		}

		if (-not [string]::IsNullOrWhiteSpace($currentDate) -and $depth -eq 2 -and $visible.Trim() -eq '}' -and ($depth + $delta) -le $dateCloseDepth) {
			if ($Timeline.Dates.ContainsKey($currentDate)) {
				foreach ($key in @('culture', 'religion')) {
					if ($Timeline.Dates[$currentDate].ContainsKey($key) -and (-not $dateWritten[$currentDate].ContainsKey($key))) {
						$output.Add(('{0}{1} = {2}' -f $dateInnerIndent, $key, $Timeline.Dates[$currentDate][$key])) | Out-Null
						$dateWritten[$currentDate][$key] = $true
					}
				}
			}
		}

		if ($depth -eq 1 -and $visible.Trim() -eq '}' -and ($depth + $delta) -eq 0) {
			foreach ($date in ($Timeline.Dates.Keys | Sort-Object)) {
				if (-not $existingDates.ContainsKey([string]$date)) {
					$output.Add(('{0}{1} = {{' -f $rootIndent, $date)) | Out-Null
					foreach ($key in @('culture', 'religion')) {
						if ($Timeline.Dates[$date].ContainsKey($key)) {
							$output.Add(('{0}{1} = {2}' -f $dateInnerIndent, $key, $Timeline.Dates[$date][$key])) | Out-Null
						}
					}
					$output.Add(('{0}}}' -f $rootIndent)) | Out-Null
				}
			}
		}

		$output.Add($line) | Out-Null
		if ($i -eq 0) {
			foreach ($key in @('culture', 'religion')) {
				if ($Timeline.Root.ContainsKey($key) -and (-not $rootExisting.ContainsKey($key))) {
					$output.Add(('{0}{1} = {2}' -f $rootIndent, $key, $Timeline.Root[$key])) | Out-Null
					$rootWritten[$key] = $true
				}
			}
		}

		$depth += $delta
		if (-not [string]::IsNullOrWhiteSpace($currentDate) -and $depth -le $dateCloseDepth) {
			$currentDate = ''
			$dateCloseDepth = -1
		}
		$i++
	}

	return ($output -join "`r`n")
}

function Apply-ProvinceBlockReplacementsToText {
	param(
		[Parameter(Mandatory = $true)][AllowEmptyString()][string]$OriginalText,
		[Parameter(Mandatory = $true)]$ReplacementById
	)

	$lines = Split-Lines -Text $OriginalText
	$blocks = Get-TopLevelBlocks -Text $OriginalText
	$blockByStart = @{}
	foreach ($block in $blocks) {
		$blockByStart[[int]$block.StartIndex] = $block
	}

	$output = New-Object System.Collections.Generic.List[string]
	$appliedReplacementIds = @{}
	$i = 0
	while ($i -lt $lines.Length) {
		if ($blockByStart.ContainsKey($i)) {
			$block = $blockByStart[$i]
			if ($block.Name -match '^\d+$' -and $ReplacementById.ContainsKey([string]$block.Name)) {
				foreach ($replacementLine in (Split-Lines -Text $ReplacementById[[string]$block.Name])) {
					$output.Add([string]$replacementLine) | Out-Null
				}
				$appliedReplacementIds[[string]$block.Name] = $true
			}
			else {
				foreach ($existingLine in $lines[$block.StartIndex..$block.EndIndex]) {
					$output.Add([string]$existingLine) | Out-Null
				}
			}
			$i = [int]$block.EndIndex + 1
			continue
		}

		$output.Add([string]$lines[$i]) | Out-Null
		$i++
	}

	$appendReplacementIds = @(
		$ReplacementById.Keys |
			Where-Object { -not $appliedReplacementIds.ContainsKey([string]$_) } |
			Sort-Object { [int]$_ }
	)
	if ($appendReplacementIds.Count -gt 0) {
		if ($output.Count -gt 0 -and -not [string]::IsNullOrWhiteSpace([string]$output[$output.Count - 1])) {
			$output.Add('') | Out-Null
		}
		$output.Add('# -----------------------------------------------------------------------------') | Out-Null
		$output.Add('# County culture/religion overlay: generated missing target province history blocks') | Out-Null
		$output.Add('# -----------------------------------------------------------------------------') | Out-Null
		foreach ($replacementId in $appendReplacementIds) {
			$output.Add('') | Out-Null
			foreach ($replacementLine in (Split-Lines -Text $ReplacementById[[string]$replacementId])) {
				$output.Add([string]$replacementLine) | Out-Null
			}
		}
	}

	return (($output -join "`r`n").TrimEnd() + "`r`n")
}

function Apply-CountyCultureReligionOverlay {
	param(
		[Parameter(Mandatory = $true)][AllowEmptyString()][string]$HistoryText,
		[Parameter(Mandatory = $true)][string]$TargetLandedTitlesPath,
		[Parameter(Mandatory = $true)][string]$SourceLandedTitlesPath,
		[Parameter(Mandatory = $true)][string]$TitleRelationPath,
		[Parameter(Mandatory = $true)][string]$SourceHistoryDir,
		[Parameter(Mandatory = $true)][AllowEmptyString()][string]$SourceHistoryOverridePath,
		[Parameter(Mandatory = $true)][string]$ReportPath,
		[Parameter(Mandatory = $true)][string]$SummaryPath
	)

	$reportRows = New-Object System.Collections.Generic.List[object]
	$replacementById = @{}

	if (-not (Test-Path -LiteralPath $TargetLandedTitlesPath)) {
		throw "Target landed_titles file not found: $TargetLandedTitlesPath"
	}
	if (-not (Test-Path -LiteralPath $SourceLandedTitlesPath)) {
		throw "Source landed_titles file not found: $SourceLandedTitlesPath"
	}
	if (-not (Test-Path -LiteralPath $TitleRelationPath)) {
		throw "Title relation CSV not found: $TitleRelationPath"
	}
	if (-not (Test-Path -LiteralPath $SourceHistoryDir)) {
		throw "Source history/provinces directory not found: $SourceHistoryDir"
	}

	$targetCountyMap = Get-CountyFirstBaronyMap -LandedTitlesText (Read-TextUtf8 -Path $TargetLandedTitlesPath)
	$sourceCountyMap = Get-CountyFirstBaronyMap -LandedTitlesText (Read-TextUtf8 -Path $SourceLandedTitlesPath)
	$sourceHistoryOverrideMap = Get-OverlaySourceHistoryOverrideMap -Path $SourceHistoryOverridePath
	$sourceHistoryData = Get-NumericHistoryBlocksFromDirectory -DirectoryPath $SourceHistoryDir
	$sourceHistoryBlocks = $sourceHistoryData.Map
	$sourceHistoryBlocksById = $sourceHistoryData.PSObject.Properties['BlocksById'].Value
	$targetHistoryBlocks = Get-TopLevelBlocks -Text $HistoryText
	$targetHistoryById = @{}
	foreach ($block in $targetHistoryBlocks) {
		if ($block.Name -match '^\d+$') {
			$targetHistoryById[[string]$block.Name] = $block
		}
	}

	$relationRows = @(
		Read-CsvUtf8 -Path $TitleRelationPath | Where-Object {
			(Normalize-TitleId -Value (Get-CsvField -Row $_ -Name 'source_title_id')) -match '^c_' -and
			(Normalize-TitleId -Value (Get-CsvField -Row $_ -Name 'mod_title_id')) -match '^c_'
		}
	)

	$targetCountyCounts = @{}
	foreach ($row in $relationRows) {
		$targetCounty = Normalize-TitleId -Value (Get-CsvField -Row $row -Name 'source_title_id')
		if (-not $targetCountyCounts.ContainsKey($targetCounty)) {
			$targetCountyCounts[$targetCounty] = 0
		}
		$targetCountyCounts[$targetCounty]++
	}

	foreach ($row in $relationRows) {
		$targetCounty = Normalize-TitleId -Value (Get-CsvField -Row $row -Name 'source_title_id')
		$sourceCounty = Normalize-TitleId -Value (Get-CsvField -Row $row -Name 'mod_title_id')
		$status = 'applied'
		$message = 'County top-barony culture/religion overlay applied.'

		if ($targetCountyCounts[$targetCounty] -gt 1) {
			$status = 'blocker_duplicate_target_county_relation'
			$message = 'More than one c_ relation row targets this current county.'
		}
		elseif (-not $targetCountyMap.ContainsKey($targetCounty)) {
			$status = 'blocker_missing_target_county'
			$message = 'Target county not found in current landed_titles.'
		}
		elseif (-not $sourceCountyMap.ContainsKey($sourceCounty)) {
			$status = 'blocker_missing_source_county'
			$message = 'Source county not found in source mod landed_titles.'
		}
		else {
			$targetInfo = $targetCountyMap[$targetCounty]
			$sourceInfo = $sourceCountyMap[$sourceCounty]
			if ([string]$targetInfo.status -ne 'ok') {
				$status = 'skipped_no_direct_target_barony'
				$message = 'Target county has no direct first barony province; culture/religion overlay is not applicable.'
			}
			elseif ([string]$sourceInfo.status -ne 'ok') {
				$status = 'blocker_missing_source_first_barony_or_province'
				$message = 'Source county has no direct first barony province.'
			}
			elseif ($null -eq $sourceHistoryBlocksById -or -not $sourceHistoryBlocksById.ContainsKey([string]$sourceInfo.first_province_id)) {
				$status = 'blocker_missing_source_history_block'
				$message = 'Source top-barony province has no history block.'
			}
			elseif ($replacementById.ContainsKey([string]$targetInfo.first_province_id)) {
				$status = 'blocker_duplicate_target_province_overlay'
				$message = 'Another county relation already prepared an overlay for this target province.'
			}
			else {
				$sourceHistoryResolve = Resolve-ProvinceHistoryBlockForOverlay -HistoryData $sourceHistoryData -ProvinceId ([string]$sourceInfo.first_province_id) -SourceBarony ([string]$sourceInfo.first_barony) -TargetCounty $targetCounty -SourceCounty $sourceCounty -OverrideMap $sourceHistoryOverrideMap
				if ([string]$sourceHistoryResolve.Status -eq 'ambiguous_root_culture_religion_duplicate') {
					$status = 'blocker_ambiguous_duplicate_source_history_block'
					$message = 'Source top-barony province has multiple duplicate history blocks with root culture/religion and no unique source-barony comment match.'
					$timeline = $null
				}
				elseif ([string]$sourceHistoryResolve.Status -eq 'override_no_matching_source_history_block') {
					$status = 'blocker_source_history_override_no_match'
					$message = 'Manual source history override exists, but no duplicate source history block matches its root culture/religion.'
					$timeline = $null
				}
				elseif ([string]$sourceHistoryResolve.Status -eq 'override_ambiguous_source_history_block') {
					$status = 'blocker_source_history_override_ambiguous'
					$message = 'Manual source history override matches more than one duplicate source history block.'
					$timeline = $null
				}
				else {
					$timeline = Get-CultureReligionTimeline -BlockText ([string]$sourceHistoryResolve.Block.Text)
				}
				if ($null -ne $timeline -and (-not $timeline.Root.ContainsKey('culture') -or -not $timeline.Root.ContainsKey('religion'))) {
					$status = 'blocker_missing_source_root_culture_or_religion'
					$message = 'Source top-barony history block lacks root culture or root religion.'
				}
				elseif ($null -ne $timeline) {
					if ($targetHistoryById.ContainsKey([string]$targetInfo.first_province_id)) {
						$targetBlockText = [string]$targetHistoryById[[string]$targetInfo.first_province_id].Text
					}
					else {
						$targetBlockText = Rewrite-ProvinceHistoryBlockId -BlockText ([string]$sourceHistoryResolve.Block.Text) -NewId ([int]$targetInfo.first_province_id)
						$status = 'applied_created_target_history_block'
						$message = 'Target top-barony history block was missing; source block copied and rewritten to target province ID before overlay.'
					}
					$replacementById[[string]$targetInfo.first_province_id] = Set-CultureReligionTimelineOnProvinceBlock -BlockText $targetBlockText -Timeline $timeline
				}
			}
		}

		$targetInfoForReport = if ($targetCountyMap.ContainsKey($targetCounty)) { $targetCountyMap[$targetCounty] } else { $null }
		$sourceInfoForReport = if ($sourceCountyMap.ContainsKey($sourceCounty)) { $sourceCountyMap[$sourceCounty] } else { $null }
		$sourceTimelineForReport = $null
		if ($null -ne $sourceInfoForReport -and -not [string]::IsNullOrWhiteSpace([string]$sourceInfoForReport.first_province_id) -and $null -ne $sourceHistoryBlocksById -and $sourceHistoryBlocksById.ContainsKey([string]$sourceInfoForReport.first_province_id)) {
			$sourceHistoryResolveForReport = Resolve-ProvinceHistoryBlockForOverlay -HistoryData $sourceHistoryData -ProvinceId ([string]$sourceInfoForReport.first_province_id) -SourceBarony ([string]$sourceInfoForReport.first_barony) -TargetCounty $targetCounty -SourceCounty $sourceCounty -OverrideMap $sourceHistoryOverrideMap
			if ($null -ne $sourceHistoryResolveForReport.Block) {
				$sourceTimelineForReport = Get-CultureReligionTimeline -BlockText ([string]$sourceHistoryResolveForReport.Block.Text)
			}
		}
		$dateSummary = ''
		if ($null -ne $sourceTimelineForReport) {
			$dateParts = New-Object System.Collections.Generic.List[string]
			foreach ($date in ($sourceTimelineForReport.Dates.Keys | Sort-Object)) {
				$keyParts = New-Object System.Collections.Generic.List[string]
				foreach ($key in @('culture', 'religion')) {
					if ($sourceTimelineForReport.Dates[$date].ContainsKey($key)) {
						$keyParts.Add(('{0}={1}' -f $key, $sourceTimelineForReport.Dates[$date][$key])) | Out-Null
					}
				}
				if ($keyParts.Count -gt 0) {
					$dateParts.Add(('{0}:{1}' -f $date, ($keyParts -join '|'))) | Out-Null
				}
			}
			$dateSummary = ($dateParts -join '; ')
		}

		$reportRows.Add([pscustomobject]@{
			target_county = $targetCounty
			source_county = $sourceCounty
			target_barony = if ($null -ne $targetInfoForReport) { [string]$targetInfoForReport.first_barony } else { '' }
			source_barony = if ($null -ne $sourceInfoForReport) { [string]$sourceInfoForReport.first_barony } else { '' }
			target_province_id = if ($null -ne $targetInfoForReport) { [string]$targetInfoForReport.first_province_id } else { '' }
			source_province_id = if ($null -ne $sourceInfoForReport) { [string]$sourceInfoForReport.first_province_id } else { '' }
			root_culture = if ($null -ne $sourceTimelineForReport -and $sourceTimelineForReport.Root.ContainsKey('culture')) { [string]$sourceTimelineForReport.Root['culture'] } else { '' }
			root_religion = if ($null -ne $sourceTimelineForReport -and $sourceTimelineForReport.Root.ContainsKey('religion')) { [string]$sourceTimelineForReport.Root['religion'] } else { '' }
			date_overrides = $dateSummary
			status = $status
			message = $message
		}) | Out-Null
	}

	Export-CsvUtf8 -Rows $reportRows -Path $ReportPath

	$summaryLines = @(
		'# County Culture/Religion Overlay Summary',
		'',
		('- relation county rows: {0}' -f @($relationRows).Count),
		('- applied rows: {0}' -f @($reportRows | Where-Object { $_.status -like 'applied*' }).Count),
		('- skipped rows: {0}' -f @($reportRows | Where-Object { $_.status -like 'skipped*' }).Count),
		('- blocker rows: {0}' -f @($reportRows | Where-Object { $_.status -like 'blocker*' }).Count),
		('- prepared province replacements: {0}' -f $replacementById.Count),
		'',
		('Report: `{0}`' -f $ReportPath)
	)
	Write-TextUtf8 -Path $SummaryPath -Text (($summaryLines -join "`r`n") + "`r`n")

	if ($replacementById.Count -eq 0) {
		return $HistoryText
	}

	return Apply-ProvinceBlockReplacementsToText -OriginalText $HistoryText -ReplacementById $replacementById
}

function Parse-LocatorText {
	param(
		[Parameter(Mandatory = $true)][AllowEmptyString()][string]$Text,
		[string]$SourceLabel = '<text>'
	)

	$lines = Split-Lines -Text $text

	$instancesLine = -1
	for ($i = 0; $i -lt $lines.Length; $i++) {
		if ($lines[$i] -match '^\s*instances\s*=\s*\{') {
			$instancesLine = $i
			break
		}
	}
	if ($instancesLine -lt 0) {
		throw "instances block not found in $SourceLabel"
	}

	$headerLines = New-Object System.Collections.Generic.List[string]
	foreach ($headerLine in $lines[0..$instancesLine]) {
		$headerLines.Add([string]$headerLine)
	}

	$instanceRows = New-Object System.Collections.Generic.List[object]
	$footerLines = $null
	$depth = 0
	$inBlock = $false
	$blockStart = -1

	for ($i = $instancesLine + 1; $i -lt $lines.Length; $i++) {
		$line = $lines[$i]
		if (-not $inBlock) {
			if ($line -match '^\s*\{\s*$') {
				$inBlock = $true
				$blockStart = $i
				$depth = Get-BraceDelta -Line $line
			}
			elseif ($line -match '^\s*\}\s*$') {
				$footerLines = $lines[$i..($lines.Length - 1)]
				break
			}
		}
		else {
			$depth += Get-BraceDelta -Line $line
			if ($depth -eq 0) {
				$blockText = ($lines[$blockStart..$i] -join "`r`n")
				if ($blockText -notmatch '(?m)^\s*id\s*=\s*(-?\d+)') {
					$inBlock = $false
					$blockStart = -1
					continue
				}
				$instanceRows.Add([pscustomobject]@{
					Id = [int]$matches[1]
					Text = $blockText
				})
				$inBlock = $false
				$blockStart = -1
			}
		}
	}

	if ($null -eq $footerLines) {
		throw "Failed to find locator footer in $SourceLabel"
	}

	return [pscustomobject]@{
		HeaderLines = $headerLines
		FooterLines = $footerLines
		Instances = $instanceRows
	}
}

function Parse-LocatorFile {
	param(
		[Parameter(Mandatory = $true)][string]$Path
	)

	$text = Read-TextUtf8 -Path $Path
	return Parse-LocatorText -Text $text -SourceLabel $Path
}

function Rewrite-LocatorBlockId {
	param(
		[Parameter(Mandatory = $true)][string]$BlockText,
		[Parameter(Mandatory = $true)][int]$NewId
	)

	$lines = Split-Lines -Text $BlockText
	for ($i = 0; $i -lt $lines.Length; $i++) {
		if ($lines[$i] -match '^(\s*id\s*=\s*)-?\d+(\s*(#.*)?)$') {
			$lines[$i] = $matches[1] + $NewId + $matches[2]
			break
		}
	}
	return ($lines -join "`r`n")
}

function Group-LocatorInstancesById {
	param(
		[Parameter(Mandatory = $true)]$Instances
	)

	$grouped = @{}
	foreach ($instance in $Instances) {
		$key = [string]$instance.Id
		if (-not $grouped.ContainsKey($key)) {
			$grouped[$key] = New-Object System.Collections.Generic.List[string]
		}
		$grouped[$key].Add($instance.Text)
	}
	return $grouped
}

function Normalize-InstanceText {
	param(
		[Parameter(Mandatory = $true)][string]$Text
	)
	return (($Text -replace '\s+', ' ').Trim())
}

function Build-LocatorText {
	param(
		[Parameter(Mandatory = $true)]$HeaderLines,
		[Parameter(Mandatory = $true)]$FooterLines,
		[Parameter(Mandatory = $true)][string[]]$InstanceBlocks
	)

	$output = New-Object System.Collections.Generic.List[string]
	foreach ($headerLine in $HeaderLines) {
		$output.Add([string]$headerLine)
	}
	foreach ($block in $InstanceBlocks) {
		foreach ($instanceLine in (Split-Lines -Text $block)) {
			$output.Add([string]$instanceLine)
		}
	}
	foreach ($footerLine in $FooterLines) {
		$output.Add([string]$footerLine)
	}
	return (($output -join "`r`n").TrimEnd() + "`r`n")
}

$repoRoot = (Get-Location).Path
$worksRoot = Join-Path $repoRoot 'Works'
$generatedRoot = Join-Path $worksRoot 'analysis\generated\core_province_integration'
if (-not (Test-Path -LiteralPath $generatedRoot)) {
	New-Item -ItemType Directory -Path $generatedRoot -Force | Out-Null
}
if ([string]::IsNullOrWhiteSpace($TitleRelationCsv)) {
	$TitleRelationCsv = Join-Path $repoRoot 'title_relation_master_manuel_new.csv'
}

$paths = @{
	FinalMaster = Join-Path $worksRoot 'analysis\generated\final_master_preserve_old_ids.csv'
	FinalModlu = Join-Path $worksRoot 'analysis\generated\final_modlu_tracking_preserve_old_ids.csv'
	FinalOrijinal = Join-Path $worksRoot 'analysis\generated\final_orijinal_tracking_preserve_old_ids.csv'
	ModHistoryDir = Join-Path $repoRoot 'history\provinces'
	VanillaHistoryDir = 'C:\Program Files (x86)\Steam\steamapps\common\Crusader Kings III\game\history\provinces'
	ModLandedTitles = Join-Path $repoRoot 'common\landed_titles\00_landed_titles.txt'
	VanillaCommonBase = 'C:\Program Files (x86)\Steam\steamapps\common\Crusader Kings III\game\common\landed_titles'
	ModHistoryTitlesDir = Join-Path $repoRoot 'history\titles'
	VanillaHistoryTitlesDir = 'C:\Program Files (x86)\Steam\steamapps\common\Crusader Kings III\game\history\titles'
	ModAdjacencies = Join-Path $repoRoot 'map_data\adjacencies.csv'
	VanillaAdjacencies = 'C:\Program Files (x86)\Steam\steamapps\common\Crusader Kings III\game\map_data\adjacencies.csv'
	IslandRegion = Join-Path $repoRoot 'map_data\island_region.txt'
	VanillaIslandRegion = 'C:\Program Files (x86)\Steam\steamapps\common\Crusader Kings III\game\map_data\island_region.txt'
	MapObjectDir = Join-Path $repoRoot 'gfx\map\map_object_data'
	VanillaMapObjectDir = 'C:\Program Files (x86)\Steam\steamapps\common\Crusader Kings III\game\gfx\map\map_object_data'
	GeneratedOracleDir = 'C:\Users\bsgho\Documents\Paradox Interactive\Crusader Kings III\generated'
	ManualLocatorProvinces = Join-Path $worksRoot 'manual\manual_locator_provinces.csv'
	CountyCultureReligionSourceHistoryOverrides = Join-Path $worksRoot 'manual\county_culture_religion_overlay_source_history_overrides.csv'
	SourceModRoot = $SourceModRoot
	SourceModLandedTitles = Join-Path $SourceModRoot 'common\landed_titles\00_landed_titles.txt'
	SourceModHistoryDir = Join-Path $SourceModRoot 'history\provinces'
	TitleRelationCsv = $TitleRelationCsv
}

$finalMasterRows = Read-CsvUtf8 -Path $paths.FinalMaster
$modluRows = Read-CsvUtf8 -Path $paths.FinalModlu
$orijinalRows = Read-CsvUtf8 -Path $paths.FinalOrijinal
$manualLocatorIds = @{}
if (Test-Path -LiteralPath $paths.ManualLocatorProvinces) {
	foreach ($row in (Read-CsvUtf8 -Path $paths.ManualLocatorProvinces)) {
		if ($null -ne $row.PSObject.Properties['province_id'] -and -not [string]::IsNullOrWhiteSpace([string]$row.province_id)) {
			$manualLocatorIds[[int]$row.province_id] = $true
		}
	}
}

$finalIdSet = @{}
$finalPreferredSource = @{}
$vanillaOldToFinal = @{}
$modOldToFinal = @{}
$candidateRows = New-Object System.Collections.Generic.List[object]

foreach ($row in $finalMasterRows) {
	$finalId = [int]$row.final_new_id
	$finalIdSet[$finalId] = $true
	$finalPreferredSource[$finalId] = $row.preferred_source_subset
	if ($row.row_type -eq 'candidate') {
		$candidateRows.Add($row)
	}
}

foreach ($row in $orijinalRows) {
	$vanillaOldToFinal[[int]$row.old_id] = [int]$row.final_new_id
}
foreach ($row in $modluRows) {
	$modOldToFinal[[int]$row.old_id] = [int]$row.final_new_id
}

$historyCoverageRows = New-Object System.Collections.Generic.List[object]
$historySourceDataMod = Get-NumericHistoryBlocksFromDirectory -DirectoryPath $paths.SourceModHistoryDir
$historySourceDataVanilla = Get-NumericHistoryBlocksFromDirectory -DirectoryPath $paths.VanillaHistoryDir

$historyBlocksOutput = New-Object System.Collections.Generic.List[string]
$historyBlocksOutput.Add('# Auto-generated by Works/tools/implement_core_province_integration.ps1')
$historyBlocksOutput.Add('# Core province integration: modlu_kalan from SourceModRoot, orijinal_dogu from vanilla with final ID rewrite.')
$historyBlocksOutput.Add('')

foreach ($row in ($candidateRows | Sort-Object { [int]$_.final_new_id })) {
	$finalId = [int]$row.final_new_id
	$preferredSubset = $row.preferred_source_subset
	if ($preferredSubset -eq 'modlu_kalan') {
		$sourceId = [int]$row.modlu_old_id
		$lookup = $historySourceDataMod.Map
		$sourceLabel = 'modlu'
	}
	elseif ($preferredSubset -eq 'orijinal_dogu') {
		$sourceId = [int]$row.orijinal_old_id
		$lookup = $historySourceDataVanilla.Map
		$sourceLabel = 'orijinal'
	}
	else {
		continue
	}

	if ($lookup.ContainsKey([string]$sourceId)) {
		$blockText = $lookup[[string]$sourceId].Text
		if ($sourceId -ne $finalId) {
			$blockText = Rewrite-ProvinceHistoryBlockId -BlockText $blockText -NewId $finalId
		}
		$historyBlocksOutput.Add($blockText)
		$historyBlocksOutput.Add('')
		$historyCoverageRows.Add([pscustomobject]@{
			final_new_id = $finalId
			source_subset = $preferredSubset
			source_old_id = $sourceId
			source_file = $lookup[[string]$sourceId].File
			status = 'ok'
		})
	}
	else {
		$historyCoverageRows.Add([pscustomobject]@{
			final_new_id = $finalId
			source_subset = $preferredSubset
			source_old_id = $sourceId
			source_file = ''
			status = 'missing_history_block'
		})
	}
}

$historyTextOutput = (($historyBlocksOutput -join "`r`n").TrimEnd() + "`r`n")
$countyCultureReligionOverlayApplied = $false
if (-not $SkipCountyCultureReligionOverlay) {
	$historyTextOutput = Apply-CountyCultureReligionOverlay `
		-HistoryText $historyTextOutput `
		-TargetLandedTitlesPath $paths.ModLandedTitles `
		-SourceLandedTitlesPath $paths.SourceModLandedTitles `
		-TitleRelationPath $paths.TitleRelationCsv `
		-SourceHistoryDir $paths.SourceModHistoryDir `
		-SourceHistoryOverridePath $paths.CountyCultureReligionSourceHistoryOverrides `
		-ReportPath (Join-Path $generatedRoot 'county_culture_religion_overlay_report.csv') `
		-SummaryPath (Join-Path $generatedRoot 'county_culture_religion_overlay_summary.md')
	$countyCultureReligionOverlayApplied = $true
}
else {
	$overlaySkipRows = @(
		[pscustomobject]@{
			target_county = ''
			source_county = ''
			target_barony = ''
			source_barony = ''
			target_province_id = ''
			source_province_id = ''
			root_culture = ''
			root_religion = ''
			date_overrides = ''
			status = 'skipped_by_parameter'
			message = 'SkipCountyCultureReligionOverlay was specified; history culture/religion overlay was not applied.'
		}
	)
	Export-CsvUtf8 -Rows $overlaySkipRows -Path (Join-Path $generatedRoot 'county_culture_religion_overlay_report.csv')
	Write-TextUtf8 -Path (Join-Path $generatedRoot 'county_culture_religion_overlay_summary.md') -Text "# County Culture/Religion Overlay Summary`r`n`r`n- skipped: `True`r`n"
}

$historyOutputPath = Join-Path $paths.ModHistoryDir '00_MB_PROVINCES.txt'
Write-LiveTextUtf8 -Path $historyOutputPath -Text $historyTextOutput -Reason 'history_provinces_merge'
Export-CsvUtf8 -Rows $historyCoverageRows -Path (Join-Path $generatedRoot 'history_provinces_merge_report.csv')
Export-CsvUtf8 -Rows $historySourceDataMod.Duplicates -Path (Join-Path $generatedRoot 'history_provinces_mod_duplicates.csv')
Export-CsvUtf8 -Rows $historySourceDataVanilla.Duplicates -Path (Join-Path $generatedRoot 'history_provinces_vanilla_duplicates.csv')

$landedProvinceRewriteRows = New-Object System.Collections.Generic.List[object]
$landedReplacementSpecs = @()
if ($SkipLandedTitles) {
	$landedProvinceRewriteRows.Add([pscustomobject]@{
		root = ''
		barony = ''
		old_province = ''
		new_province = ''
		status = 'skipped_by_parameter'
		reason = 'SkipLandedTitles was specified; common/landed_titles was not rewritten.'
	}) | Out-Null
}
else {
	$landedReplacementSpecs = @(
		@{ Root = 'e_viet'; File = Join-Path $paths.VanillaCommonBase '00_landed_titles.txt' },
		@{ Root = 'e_tibet'; File = Join-Path $paths.VanillaCommonBase '00_landed_titles.txt' },
		@{ Root = 'h_china'; File = Join-Path $paths.VanillaCommonBase '02_china.txt' },
		@{ Root = 'e_suvarnabhumi'; File = Join-Path $paths.VanillaCommonBase '03_seasia.txt' },
		@{ Root = 'e_brunei'; File = Join-Path $paths.VanillaCommonBase '03_seasia.txt' },
		@{ Root = 'e_kambuja'; File = Join-Path $paths.VanillaCommonBase '03_seasia.txt' },
		@{ Root = 'e_nusantara'; File = Join-Path $paths.VanillaCommonBase '06_philippines.txt' },
		@{ Root = 'e_japan'; File = Join-Path $paths.VanillaCommonBase '01_japan.txt' },
		@{ Root = 'k_chrysanthemum_throne'; File = Join-Path $paths.VanillaCommonBase '01_japan.txt' },
		@{ Root = 'e_goryeo'; File = Join-Path $paths.VanillaCommonBase '05_goryeo.txt' },
		@{ Root = 'k_yongson_throne'; File = Join-Path $paths.VanillaCommonBase '05_goryeo.txt' }
	)

	$landedBlocksByFile = @{}
	foreach ($spec in $landedReplacementSpecs) {
		if (-not $landedBlocksByFile.ContainsKey($spec.File)) {
			$landedBlocksByFile[$spec.File] = Get-TopLevelBlocks -Text (Read-TextUtf8 -Path $spec.File)
		}
	}

	$landedAppendedBlocks = New-Object System.Collections.Generic.List[string]
	$modLandedHeadText = Read-HeadOrWorkingText -RelativePath 'common/landed_titles/00_landed_titles.txt' -WorkingPath $paths.ModLandedTitles
	$modBaronyProvinceMap = Get-BaronyProvinceMapFromText -Text $modLandedHeadText

	foreach ($spec in $landedReplacementSpecs) {
		$block = $landedBlocksByFile[$spec.File] | Where-Object { $_.Name -eq $spec.Root } | Select-Object -First 1
		if ($null -eq $block) {
			throw "Failed to locate common landed title root $($spec.Root) in $($spec.File)"
		}
		$blockText = $block.Text
		$rewrittenBlock = Rewrite-LandedTitleBlockProvinceIds `
			-BlockText $blockText `
			-Root $spec.Root `
			-VanillaOldToFinal $vanillaOldToFinal `
			-ModBaronyProvinceMap $modBaronyProvinceMap `
			-ReportRows $landedProvinceRewriteRows
		$landedAppendedBlocks.Add($rewrittenBlock)
	}

	$modLandedOriginal = $modLandedHeadText
	$landedRootsToRemove = @(
		'e_viet',
		'e_tibet',
		'h_china',
		'e_goryeo',
		'e_brunei',
		'e_kambuja',
		'e_burma',
		'e_japan',
		'e_nusantara',
		'k_yongson_throne',
		'k_chrysanthemum_throne',
		'e_suvarnabhumi',
		'e_qixi',
		'e_tunguse',
		'e_jurchen_china',
		'e_java',
		'e_malayadvipa',
		'e_srivijaya',
		'e_kalimantan',
		'e_angkor',
		'e_ramanya',
		'e_panyupayana',
		'e_maluku'
	)
	$modLandedRewritten = Remove-TopLevelBlocksAndAppend `
		-OriginalText $modLandedOriginal `
		-RemoveNames $landedRootsToRemove `
		-AppendBlocks $landedAppendedBlocks `
		-MarkerComment 'Imported vanilla east landed title roots'
	Write-LiveTextUtf8 -Path $paths.ModLandedTitles -Text $modLandedRewritten -Reason 'common_landed_titles_vanilla_east_rewrite'
}
Export-CsvUtf8 -Rows $landedProvinceRewriteRows -Path (Join-Path $generatedRoot 'landed_titles_vanilla_province_rewrite_report.csv')

$historyTitleSources = @{
	h_china = Join-Path $paths.VanillaHistoryTitlesDir 'e_china.txt'
	e_tibet = Join-Path $paths.VanillaHistoryTitlesDir '00_other_titles.txt'
	e_goryeo = Join-Path $paths.VanillaHistoryTitlesDir 'e_goryeo.txt'
	k_yongson_throne = Join-Path $paths.VanillaHistoryTitlesDir 'e_goryeo.txt'
	e_japan = Join-Path $paths.VanillaHistoryTitlesDir 'e_japan.txt'
	k_chrysanthemum_throne = Join-Path $paths.VanillaHistoryTitlesDir 'e_japan.txt'
	e_kambuja = Join-Path $paths.VanillaHistoryTitlesDir 'e_khmer.txt'
}
$historyTitleTargets = @{
	'00_ASIA_CHINA.txt' = @('h_china')
	'00_OTHER.txt' = @('e_tibet')
	'00_ASIA_NORTH.txt' = @('e_goryeo', 'k_yongson_throne')
	'00_ASIA_JAPAN.txt' = @('e_japan', 'k_chrysanthemum_throne')
	'00_ASIA_SOUTH.txt' = @('e_kambuja')
}

$historyTitleBlocksBySource = @{}
foreach ($root in $historyTitleSources.Keys) {
	$filePath = $historyTitleSources[$root]
	if (-not $historyTitleBlocksBySource.ContainsKey($filePath)) {
		$historyTitleBlocksBySource[$filePath] = Get-TopLevelBlocks -Text (Read-TextUtf8 -Path $filePath)
	}
}

$historyTitleReportRows = New-Object System.Collections.Generic.List[object]
foreach ($targetFileName in $historyTitleTargets.Keys) {
	$targetPath = Join-Path $paths.ModHistoryTitlesDir $targetFileName
	$targetOriginal = Read-HeadOrWorkingText -RelativePath ("history/titles/{0}" -f $targetFileName) -WorkingPath $targetPath
	$roots = $historyTitleTargets[$targetFileName]
	$appendBlocks = New-Object System.Collections.Generic.List[string]

	foreach ($root in $roots) {
		$sourceFile = $historyTitleSources[$root]
		$block = $historyTitleBlocksBySource[$sourceFile] | Where-Object { $_.Name -eq $root } | Select-Object -First 1
		if ($null -eq $block) {
			throw "Failed to locate history title root $root in $sourceFile"
		}
		$appendBlocks.Add($block.Text)
		$historyTitleReportRows.Add([pscustomobject]@{
			target_file = $targetFileName
			root = $root
			source_file = Split-Path -Leaf $sourceFile
			status = 'imported'
		})
	}

	$targetRewritten = Remove-TopLevelBlocksAndAppend `
		-OriginalText $targetOriginal `
		-RemoveNames $roots `
		-AppendBlocks $appendBlocks `
		-MarkerComment 'Imported vanilla east title history roots'
	Write-LiveTextUtf8 -Path $targetPath -Text $targetRewritten -Reason 'history_titles_vanilla_east_rewrite'
}
Export-CsvUtf8 -Rows $historyTitleReportRows -Path (Join-Path $generatedRoot 'history_titles_merge_report.csv')

$adjacencyRowsOutput = New-Object System.Collections.Generic.List[object]
$adjacencyStaleRows = New-Object System.Collections.Generic.List[object]
$adjacencyInvalidRows = New-Object System.Collections.Generic.List[object]
$adjacencySeen = @{}

function Convert-AdjacencyRow {
	param(
		[Parameter(Mandatory = $true)]$Row,
		[Parameter(Mandatory = $true)][string]$SourceKind
	)

	$result = [ordered]@{
		From = $Row.From
		To = $Row.To
		Type = $Row.Type
		Through = $Row.Through
		start_x = $Row.start_x
		start_y = $Row.start_y
		stop_x = $Row.stop_x
		stop_y = $Row.stop_y
		Comment = $Row.Comment
	}

	$relevantFinalIds = New-Object System.Collections.Generic.List[int]
	$unmapped = New-Object System.Collections.Generic.List[string]

	foreach ($columnName in @('From', 'To', 'Through')) {
		$value = [string]$Row.$columnName
		$parsedId = 0
		if ([int]::TryParse($value, [ref]$parsedId) -and $parsedId -gt 0) {
			if ($SourceKind -eq 'modlu') {
				if ($modOldToFinal.ContainsKey($parsedId)) {
					$mapped = $modOldToFinal[$parsedId]
					$result[$columnName] = [string]$mapped
					$relevantFinalIds.Add($mapped)
				}
				else {
					$unmapped.Add("$columnName=$parsedId")
				}
			}
			else {
				if ($vanillaOldToFinal.ContainsKey($parsedId)) {
					$mapped = $vanillaOldToFinal[$parsedId]
					$result[$columnName] = [string]$mapped
					$relevantFinalIds.Add($mapped)
				}
				else {
					$unmapped.Add("$columnName=$parsedId")
				}
			}
		}
	}

	return [pscustomobject]@{
		Result = [pscustomobject]$result
		RelevantFinalIds = $relevantFinalIds
		Unmapped = $unmapped
	}
}

$modAdjText = Read-HeadOrWorkingText -RelativePath 'map_data/adjacencies.csv' -WorkingPath $paths.ModAdjacencies
$modAdjRows = $modAdjText | ConvertFrom-Csv -Delimiter ';'
$vanillaAdjRows = Import-Csv -Path $paths.VanillaAdjacencies -Delimiter ';'

foreach ($row in $modAdjRows) {
	$converted = Convert-AdjacencyRow -Row $row -SourceKind 'modlu'
	if ($converted.Unmapped.Count -gt 0) {
		$adjacencyStaleRows.Add([pscustomobject]@{
			source = 'modlu'
			comment = $row.Comment
			unmapped = ($converted.Unmapped -join '; ')
			action = 'dropped'
		})
		continue
	}

	$touchesOriginal = $false
	foreach ($finalId in $converted.RelevantFinalIds) {
		if ($finalPreferredSource[$finalId] -eq 'orijinal_dogu') {
			$touchesOriginal = $true
			break
		}
	}
	if ($touchesOriginal) {
		continue
	}

	$key = (($converted.Result.PSObject.Properties | ForEach-Object { $_.Value }) -join ';')
	if (-not $adjacencySeen.ContainsKey($key)) {
		$adjacencySeen[$key] = $true
		$adjacencyRowsOutput.Add($converted.Result)
	}
}

foreach ($row in $vanillaAdjRows) {
	$converted = Convert-AdjacencyRow -Row $row -SourceKind 'orijinal'
	if ($converted.Unmapped.Count -gt 0) {
		$adjacencyStaleRows.Add([pscustomobject]@{
			source = 'orijinal'
			comment = $row.Comment
			unmapped = ($converted.Unmapped -join '; ')
			action = 'dropped'
		})
		continue
	}

	$touchesOriginal = $false
	foreach ($finalId in $converted.RelevantFinalIds) {
		if ($finalPreferredSource[$finalId] -eq 'orijinal_dogu') {
			$touchesOriginal = $true
			break
		}
	}
	if (-not $touchesOriginal) {
		continue
	}

	$key = (($converted.Result.PSObject.Properties | ForEach-Object { $_.Value }) -join ';')
	if (-not $adjacencySeen.ContainsKey($key)) {
		$adjacencySeen[$key] = $true
		$adjacencyRowsOutput.Add($converted.Result)
	}
}

foreach ($row in $adjacencyRowsOutput) {
	foreach ($columnName in @('From', 'To', 'Through')) {
		$value = [string]$row.$columnName
		$parsedId = 0
		if ([int]::TryParse($value, [ref]$parsedId) -and $parsedId -gt 0) {
			if (-not $finalIdSet.ContainsKey($parsedId)) {
				$adjacencyInvalidRows.Add([pscustomobject]@{
					file = 'map_data/adjacencies.csv'
					column = $columnName
					invalid_id = $parsedId
					comment = $row.Comment
				})
			}
		}
	}
}

$adjacencyHeader = 'From;To;Type;Through;start_x;start_y;stop_x;stop_y;Comment'
$adjacencyLines = New-Object System.Collections.Generic.List[string]
$adjacencyLines.Add($adjacencyHeader)
foreach ($row in $adjacencyRowsOutput) {
	$adjacencyLines.Add(('{0};{1};{2};{3};{4};{5};{6};{7};{8}' -f $row.From, $row.To, $row.Type, $row.Through, $row.start_x, $row.start_y, $row.stop_x, $row.stop_y, $row.Comment))
}
Write-LiveTextUtf8 -Path $paths.ModAdjacencies -Text (($adjacencyLines -join "`r`n") + "`r`n") -Reason 'map_data_adjacencies_rewrite'
Export-CsvUtf8 -Rows $adjacencyStaleRows -Path (Join-Path $generatedRoot 'stale_old_vanilla_id_report.csv')
Export-CsvUtf8 -Rows $adjacencyInvalidRows -Path (Join-Path $generatedRoot 'invalid_final_id_report.csv')

$currentIslandText = Read-HeadOrWorkingText -RelativePath 'map_data/island_region.txt' -WorkingPath $paths.IslandRegion
Write-LiveTextUtf8 -Path $paths.IslandRegion -Text $currentIslandText -Reason 'map_data_island_region_preserve_current'
$islandReportRows = @(
	[pscustomobject]@{
		file = 'map_data/island_region.txt'
		action = 'unchanged'
		reason = 'No provinces = { } numeric entries detected; current file kept as mod-west baseline for core pass.'
	}
)
Export-CsvUtf8 -Rows $islandReportRows -Path (Join-Path $generatedRoot 'island_region_pass_report.csv')

$locatorFiles = @(
	'building_locators.txt',
	'special_building_locators.txt',
	'player_stack_locators.txt',
	'combat_locators.txt',
	'siege_locators.txt',
	'activities.txt'
)

$locatorOracleDiffRows = New-Object System.Collections.Generic.List[object]
$locatorValidationRows = New-Object System.Collections.Generic.List[object]
$locatorMissingRows = New-Object System.Collections.Generic.List[object]

foreach ($locatorFile in $locatorFiles) {
	$modLocatorSourceText = Read-HeadOrWorkingText -RelativePath ("gfx/map/map_object_data/{0}" -f $locatorFile) -WorkingPath (Join-Path $paths.MapObjectDir $locatorFile)
	$modLocator = Parse-LocatorText -Text $modLocatorSourceText -SourceLabel ("HEAD:gfx/map/map_object_data/{0}" -f $locatorFile)
	$workingModLocator = Parse-LocatorFile -Path (Join-Path $paths.MapObjectDir $locatorFile)
	$vanillaLocator = Parse-LocatorFile -Path (Join-Path $paths.VanillaMapObjectDir $locatorFile)
	$oracleLocator = Parse-LocatorFile -Path (Join-Path $paths.GeneratedOracleDir $locatorFile)

	$modGroups = Group-LocatorInstancesById -Instances $modLocator.Instances
	$workingModGroups = Group-LocatorInstancesById -Instances $workingModLocator.Instances
	$vanillaGroups = Group-LocatorInstancesById -Instances $vanillaLocator.Instances
	$oracleGroups = Group-LocatorInstancesById -Instances $oracleLocator.Instances
	$outputBlocks = New-Object System.Collections.Generic.List[string]

	if ($modGroups.ContainsKey('0')) {
		$seenZero = @{}
		foreach ($block in $modGroups['0']) {
			$key = Normalize-InstanceText -Text $block
			if (-not $seenZero.ContainsKey($key)) {
				$seenZero[$key] = $true
				$outputBlocks.Add($block)
			}
		}
		if ($vanillaGroups.ContainsKey('0')) {
			foreach ($block in $vanillaGroups['0']) {
				$key = Normalize-InstanceText -Text $block
				if (-not $seenZero.ContainsKey($key)) {
					$seenZero[$key] = $true
					$outputBlocks.Add($block)
				}
			}
		}
	}

	foreach ($row in ($candidateRows | Sort-Object { [int]$_.final_new_id })) {
		$finalId = [int]$row.final_new_id
		$subset = $row.preferred_source_subset
		if ($manualLocatorIds.ContainsKey($finalId)) {
			$key = [string]$finalId
			if ($workingModGroups.ContainsKey($key)) {
				foreach ($block in $workingModGroups[$key]) {
					$outputBlocks.Add($block)
				}
			}
			elseif ($modGroups.ContainsKey($key)) {
				foreach ($block in $modGroups[$key]) {
					$outputBlocks.Add($block)
				}
			}
			else {
				$locatorMissingRows.Add([pscustomobject]@{
					file = $locatorFile
					final_new_id = $finalId
					source_subset = $subset
					source_old_id = ''
					status = 'missing_manual_locator'
				})
			}
			continue
		}
		if ($subset -eq 'modlu_kalan') {
			$oldId = [int]$row.modlu_old_id
			$key = [string]$oldId
			$finalKey = [string]$finalId
			if ($modGroups.ContainsKey($key)) {
				foreach ($block in $modGroups[$key]) {
					if ($oldId -eq $finalId) {
						$outputBlocks.Add($block)
					}
					else {
						$outputBlocks.Add((Rewrite-LocatorBlockId -BlockText $block -NewId $finalId))
					}
				}
			}
			elseif ($oracleGroups.ContainsKey($finalKey)) {
				foreach ($block in $oracleGroups[$finalKey]) {
					$outputBlocks.Add($block)
				}
				$locatorMissingRows.Add([pscustomobject]@{
					file = $locatorFile
					final_new_id = $finalId
					source_subset = $subset
					source_old_id = $oldId
					status = 'fallback_generated_for_missing_mod'
				})
			}
			else {
				$locatorMissingRows.Add([pscustomobject]@{
					file = $locatorFile
					final_new_id = $finalId
					source_subset = $subset
					source_old_id = $oldId
					status = 'missing_mod_locator'
				})
			}
		}
		elseif ($subset -eq 'orijinal_dogu') {
			$oldId = [int]$row.orijinal_old_id
			$key = [string]$oldId
			if ($vanillaGroups.ContainsKey($key)) {
				foreach ($block in $vanillaGroups[$key]) {
					$outputBlocks.Add((Rewrite-LocatorBlockId -BlockText $block -NewId $finalId))
				}
			}
			elseif ($oracleGroups.ContainsKey([string]$finalId)) {
				foreach ($block in $oracleGroups[[string]$finalId]) {
					$outputBlocks.Add($block)
				}
				$locatorMissingRows.Add([pscustomobject]@{
					file = $locatorFile
					final_new_id = $finalId
					source_subset = $subset
					source_old_id = $oldId
					status = 'fallback_generated_for_missing_vanilla'
				})
			}
			else {
				$locatorMissingRows.Add([pscustomobject]@{
					file = $locatorFile
					final_new_id = $finalId
					source_subset = $subset
					source_old_id = $oldId
					status = 'missing_vanilla_locator'
				})
			}
		}
	}

	$finalText = Build-LocatorText -HeaderLines $modLocator.HeaderLines -FooterLines $modLocator.FooterLines -InstanceBlocks $outputBlocks.ToArray()
	Write-LiveTextUtf8 -Path (Join-Path $paths.MapObjectDir $locatorFile) -Text $finalText -Reason ('locator_rewrite:{0}' -f $locatorFile)

	$writtenLocator = if ($script:DryRun) {
		Parse-LocatorText -Text $finalText -SourceLabel ('dry_run:{0}' -f $locatorFile)
	}
	else {
		Parse-LocatorFile -Path (Join-Path $paths.MapObjectDir $locatorFile)
	}
	$writtenGroups = Group-LocatorInstancesById -Instances $writtenLocator.Instances

	foreach ($groupKey in $writtenGroups.Keys) {
		$idValue = [int]$groupKey
		if ($idValue -gt 0 -and -not $finalIdSet.ContainsKey($idValue)) {
			$locatorValidationRows.Add([pscustomobject]@{
				file = $locatorFile
				check = 'invalid_final_id'
				id = $idValue
				value = 'present'
			})
		}
		if ($idValue -ne 0 -and $writtenGroups[$groupKey].Count -gt 1) {
			$locatorValidationRows.Add([pscustomobject]@{
				file = $locatorFile
				check = 'duplicate_positive_id'
				id = $idValue
				value = $writtenGroups[$groupKey].Count
			})
		}
	}

	$allKeys = New-Object System.Collections.Generic.HashSet[string]
	foreach ($key in $writtenGroups.Keys) { [void]$allKeys.Add($key) }
	foreach ($key in $oracleGroups.Keys) { [void]$allKeys.Add($key) }
	foreach ($key in $allKeys) {
		$mergedCount = 0
		$oracleCount = 0
		if ($writtenGroups.ContainsKey($key)) { $mergedCount = $writtenGroups[$key].Count }
		if ($oracleGroups.ContainsKey($key)) { $oracleCount = $oracleGroups[$key].Count }
		$mergedNormalized = ''
		$oracleNormalized = ''
		if ($mergedCount -gt 0) {
			$mergedNormalized = (($writtenGroups[$key] | ForEach-Object { Normalize-InstanceText -Text $_ }) -join ' || ')
		}
		if ($oracleCount -gt 0) {
			$oracleNormalized = (($oracleGroups[$key] | ForEach-Object { Normalize-InstanceText -Text $_ }) -join ' || ')
		}
		$status =
			if ($mergedCount -eq 0) { 'oracle_only' }
			elseif ($oracleCount -eq 0) { 'merged_only' }
			elseif ($mergedCount -ne $oracleCount) { 'count_mismatch' }
			elseif ($mergedNormalized -ne $oracleNormalized) { 'text_mismatch' }
			else { 'match' }

		if ($status -ne 'match') {
			$locatorOracleDiffRows.Add([pscustomobject]@{
				file = $locatorFile
				id = $key
				status = $status
				merged_count = $mergedCount
				oracle_count = $oracleCount
			})
		}
	}
}

Export-CsvUtf8 -Rows $locatorMissingRows -Path (Join-Path $generatedRoot 'locator_missing_report.csv')
Export-CsvUtf8 -Rows $locatorValidationRows -Path (Join-Path $generatedRoot 'locator_validation_report.csv')
Export-CsvUtf8 -Rows $locatorOracleDiffRows -Path (Join-Path $generatedRoot 'locator_oracle_diff_report.csv')
Export-CsvUtf8 -Rows $script:LiveWriteRows -Path (Join-Path $generatedRoot 'live_write_report.csv')

$summaryLines = @(
	'# Core Province Integration Summary',
	'',
	('- dry run: {0}' -f $script:DryRun),
	('- skip landed_titles: {0}' -f [bool]$SkipLandedTitles),
	('- skip county culture/religion overlay: {0}' -f [bool]$SkipCountyCultureReligionOverlay),
	('- history/provinces merged candidates: {0}' -f (($historyCoverageRows | Where-Object { $_.status -eq 'ok' }).Count)),
	('- history/provinces missing blocks: {0}' -f (($historyCoverageRows | Where-Object { $_.status -ne 'ok' }).Count)),
	('- county culture/religion overlay applied: {0}' -f $countyCultureReligionOverlayApplied),
	('- landed_titles imported roots: {0}' -f $landedReplacementSpecs.Count),
	('- history/titles imported roots: {0}' -f $historyTitleReportRows.Count),
	('- adjacencies merged rows: {0}' -f $adjacencyRowsOutput.Count),
	('- adjacencies dropped stale rows: {0}' -f $adjacencyStaleRows.Count),
	('- locator missing rows: {0}' -f $locatorMissingRows.Count),
	('- locator validation flags: {0}' -f $locatorValidationRows.Count),
	('- locator oracle diffs: {0}' -f $locatorOracleDiffRows.Count)
)
Write-TextUtf8 -Path (Join-Path $generatedRoot 'core_province_integration_summary.md') -Text (($summaryLines -join "`r`n") + "`r`n")
