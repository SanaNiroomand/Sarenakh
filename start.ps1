# Runs Sarenakh on this computer and opens it in the browser. Easiest: double-click start.cmd.
# Needs Python 3.11+ and Node.js. Your OpenAI key goes in .env (copied from .env.example on first run).

$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

if (-not (Test-Path .env)) {
  Copy-Item .env.example .env
  Write-Host "Created .env - open it, put your key after OPENAI_API_KEY=, then run this again."
  exit 1
}

if (Get-NetTCPConnection -LocalPort 8000 -State Listen -ErrorAction SilentlyContinue) {
  Write-Host "Sarenakh is already running."
  Start-Process "http://localhost:8000"
  exit 0
}

if (-not (Test-Path .venv)) { Write-Host "First run: setting up Python..."; python -m venv .venv }
Write-Host "Checking Python packages..."
.\.venv\Scripts\pip.exe install -q -r backend\requirements.txt

if (-not (Test-Path frontend\node_modules)) { Write-Host "First run: installing website packages..."; npm --prefix frontend ci --no-audit --no-fund }
Write-Host "Building the website..."
npm --prefix frontend run build --silent

Start-Process "http://localhost:8000"
Write-Host "Sarenakh is running at http://localhost:8000 - close this window to stop it."
.\.venv\Scripts\python.exe -m uvicorn app.main:app --app-dir backend --port 8000
