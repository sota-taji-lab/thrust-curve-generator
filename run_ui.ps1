$ErrorActionPreference = "Stop"

Set-Location $PSScriptRoot

$Python = Join-Path $PSScriptRoot ".venv\Scripts\python.exe"

if (-not (Test-Path $Python)) {
    Write-Host "[FAIL] Project virtual environment was not found." -ForegroundColor Red
    Write-Host "Expected: $Python"
    Write-Host "Create the environment and install requirements before launching the UI."
    exit 1
}

Write-Host "Starting Hybrid Rocket Thrust Curve Generator UI..." -ForegroundColor Cyan
& $Python -m streamlit run (Join-Path $PSScriptRoot "streamlit_app.py")
