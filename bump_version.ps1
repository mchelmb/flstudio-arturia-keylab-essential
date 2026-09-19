param(
    [switch]$WhatIf
)

$ErrorActionPreference = 'Stop'
$versionPath = Join-Path $PSScriptRoot 'version.py'

if (-not (Test-Path $versionPath)) {
    throw "Version file not found: $versionPath"
}

$content = Get-Content -Path $versionPath -Raw
$linePattern = '(?m)^CHANGE_DATE[ \t]*=[ \t]*([0-9_]+)[ \t]*\r?$'
$match = [regex]::Match($content, $linePattern)
if (-not $match.Success) {
    throw "CHANGE_DATE assignment not found in $versionPath"
}

$now = Get-Date
$candidateDate = $now
$currentText = $match.Groups[1].Value
$current = [int64]($currentText -replace '_', '')

# Keep the value strictly increasing when multiple commits happen in one minute or when an older
# manually assigned value is encountered.
while ([int64]$candidateDate.ToString('yyyyMMddHHmm') -le $current) {
    $candidateDate = $candidateDate.AddMinutes(1)
}
$candidate = $candidateDate.ToString('yyyy_MM_dd_HHmm')

$updated = [regex]::Replace(
    $content,
    $linePattern,
    "CHANGE_DATE = $candidate"
)

if ($WhatIf) {
    Write-Host "Would update CHANGE_DATE: $current -> $candidate"
    exit 0
}

[System.IO.File]::WriteAllText($versionPath, $updated, [System.Text.UTF8Encoding]::new($false))
Write-Host "Updated CHANGE_DATE: $current -> $candidate"
