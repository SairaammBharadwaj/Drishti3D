# Drishti3D one-shot local launcher (Windows PowerShell).
# Usage:  ./run_local.ps1   (from the drishti3d/ directory)
$ErrorActionPreference = "Stop"
$py = "C:/Users/saira/anaconda3/envs/jupyter_env/python.exe"

Write-Host "==> Ensuring sample dataset exists..."
if (-not (Test-Path "sample_data/synthetic/synthetic_flight.mp4")) {
    & $py sample_data/generate_sample.py sample_data/synthetic
}

Write-Host "==> Building frontend (if node_modules present)..."
if (Test-Path "frontend/node_modules") {
    Push-Location frontend; npm run build; Pop-Location
} else {
    Write-Host "   (run 'cd frontend; npm install; npm run build' once for the served UI)"
}

Write-Host "==> Starting backend on http://127.0.0.1:8000  (Ctrl+C to stop)"
$env:DRISHTI_DATA_DIR = "$PWD/data"
Push-Location backend
& $py -m uvicorn app.main:app --host 127.0.0.1 --port 8000
Pop-Location
