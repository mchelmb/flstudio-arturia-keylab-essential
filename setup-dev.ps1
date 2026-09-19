# Creates or refreshes the project-local development environment.
# The environment is for editor tooling only and must never be deployed to FL Studio.

param(
    [switch]$Recreate
)

$ErrorActionPreference = 'Stop'
$root = $PSScriptRoot
$venv = Join-Path $root '.venv'
$python = Join-Path $venv 'Scripts\python.exe'

if ($Recreate -and (Test-Path $venv)) {
    Remove-Item $venv -Recurse -Force
}

if (-not (Test-Path $python)) {
    py -V:Astral/CPython3.12.11 -m venv $venv
}

& $python -m pip install --upgrade pip
& $python -m pip install --requirement (Join-Path $root 'requirements-dev.txt')

Write-Host ''
Write-Host "Development environment ready: $venv" -ForegroundColor Green
Write-Host 'Select .venv in VS Code with Python: Select Interpreter.'
Write-Host 'Do not copy .venv, requirements-dev.txt, or pyrightconfig.json to FL Studio.'