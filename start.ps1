# Run Sarenakh on this computer and open it in the browser.
#   Right-click > "Run with PowerShell", or in a terminal:  .\start.ps1
# Needs Python 3.11+ and Node.js. Put your OpenAI key in .env first (copy .env.example).

$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

if (-not (Test-Path .env)) { Copy-Item .env.example .env; Write-Host "Created .env - add your OPENAI_API_KEY to it, then run again."; exit 1 }

if (-not (Test-Path .venv)) {
  Write-Host "First run: installing Python packages..."
  python -m venv .venv
  .\.venv\Scripts\pip.exe install -q -r backend\requirements.txt
}

if (-not (Test-Path frontend\dist\index.html)) {
  Write-Host "First run: building the website..."
  npm --prefix frontend ci --no-audit --no-fund
  npm --prefix frontend run build
}

Start-Process "http://localhost:8000"
Write-Host "Sarenakh is starting at http://localhost:8000  (Ctrl+C to stop)"
.\.venv\Scripts\python.exe -m uvicorn app.main:app --app-dir backend --port 8000
