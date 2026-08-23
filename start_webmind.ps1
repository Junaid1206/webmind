Set-Location $PSScriptRoot
if (-not (Test-Path .venv\Scripts\python.exe)) { py -m venv .venv; if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE } }
.venv\Scripts\python.exe -m pip install -r backend\requirements.txt
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
.venv\Scripts\python.exe -m uvicorn backend.app.main:app --host 0.0.0.0 --port 8000
