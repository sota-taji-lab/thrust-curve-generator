$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

if (-not (Test-Path ".\.venv\Scripts\python.exe")) {
    Write-Host "ERROR: .venv was not found in this folder." -ForegroundColor Red
    Write-Host "Create/copy the virtual environment first, then run this script again."
    exit 1
}

if (-not (Test-Path ".\sweep_results\coarse_feasible.csv")) {
    Write-Host "ERROR: coarse_feasible.csv was not found." -ForegroundColor Red
    Write-Host "Run run_sweep_coarse.ps1 first."
    exit 1
}

& ".\.venv\Scripts\python.exe" ".\sweep_runner.py" --mode fine
