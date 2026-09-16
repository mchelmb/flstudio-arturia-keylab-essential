# Deploys this script folder to FL Studio's Hardware directory.
#
# Copies ONLY legitimate project files. Explicitly refuses to copy any .py file whose name
# matches an FL Studio built-in module (ui.py, plugins.py, channels.py, ...), since those shadow
# FL's real modules and silently break everything - see stub_guard.py for the full explanation.
#
# Usage (from this folder, in PowerShell):
#     .\deploy.ps1
#
# Optional: pass a different destination
#     .\deploy.ps1 -Destination "D:\SomeOther\Hardware\my-script"

param(
    [string]$Destination = "$env:USERPROFILE\Documents\Image-Line\FL Studio\Settings\Hardware\flstudio-arturia-keylab-essential-nav"
)

$ErrorActionPreference = 'Stop'
$source = $PSScriptRoot

# Names FL Studio provides itself - never copy these, even if present locally.
$flBuiltins = @(
    'arrangement', 'channels', 'device', 'general', 'launchMapPages', 'midi', 'mixer',
    'patterns', 'playlist', 'plugins', 'screen', 'transport', 'ui', 'utils'
)

# Other things that should never ship.
$excludeFiles = @('deploy.ps1', 'tests_import.py')
$excludeDirs  = @('__pycache__', '.git', '.github', 'vst_param_scans', 'docs')

Write-Host "Source:      $source"
Write-Host "Destination: $Destination"
Write-Host ""

# Warn about any stub files sitting in the source folder.
$foundStubs = @()
foreach ($name in $flBuiltins) {
    $p = Join-Path $source "$name.py"
    if (Test-Path $p) { $foundStubs += "$name.py" }
}
if ($foundStubs.Count -gt 0) {
    Write-Host "WARNING: fake FL Studio modules found in the SOURCE folder:" -ForegroundColor Yellow
    $foundStubs | ForEach-Object { Write-Host "    $_" -ForegroundColor Yellow }
    Write-Host "  These will NOT be copied. Consider deleting them from source too." -ForegroundColor Yellow
    Write-Host ""
}

if (-not (Test-Path $Destination)) {
    New-Item -ItemType Directory -Path $Destination -Force | Out-Null
    Write-Host "Created destination folder."
}

# Remove any stubs already sitting in the DESTINATION from a previous bad copy.
$cleaned = 0
foreach ($name in $flBuiltins) {
    $p = Join-Path $Destination "$name.py"
    if (Test-Path $p) {
        Remove-Item $p -Force
        Write-Host "Removed stale stub from destination: $name.py" -ForegroundColor Cyan
        $cleaned++
    }
}
$pycache = Join-Path $Destination '__pycache__'
if (Test-Path $pycache) {
    Remove-Item $pycache -Recurse -Force
    Write-Host "Cleared destination __pycache__ (stale bytecode can mask changes)." -ForegroundColor Cyan
}
if ($cleaned -gt 0) { Write-Host "" }

# Copy .py files, excluding stubs and excluded names.
$copied = 0
Get-ChildItem -Path $source -Filter *.py -File | ForEach-Object {
    $base = [System.IO.Path]::GetFileNameWithoutExtension($_.Name)
    if ($flBuiltins -contains $base) { return }
    if ($excludeFiles -contains $_.Name) { return }
    Copy-Item $_.FullName -Destination $Destination -Force
    $copied++
}

# Copy supporting folders that SHOULD ship (vst_maps holds user-editable JSON maps).
foreach ($dir in @('vst_maps')) {
    $src = Join-Path $source $dir
    if (Test-Path $src) {
        Copy-Item $src -Destination $Destination -Recurse -Force
        Write-Host "Copied folder: $dir"
    }
}

# Copy the .pyd if present (pykeys - harmless if unused).
Get-ChildItem -Path $source -Filter *.pyd -File -ErrorAction SilentlyContinue | ForEach-Object {
    Copy-Item $_.FullName -Destination $Destination -Force
}

Write-Host ""
Write-Host "Copied $copied .py files." -ForegroundColor Green
Write-Host "Done. Reload the script in FL Studio: MIDI Settings -> refresh icon." -ForegroundColor Green
