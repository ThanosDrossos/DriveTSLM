# One-command local dev (Windows). Requires the venv from README setup.
# Frontend changes need a rebuild: docker run --rm -v "$PWD\frontend:/app" -w /app node:22-alpine sh -c "npm install && npm run build"
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root
if (Test-Path "$root\.env") {
  Get-Content "$root\.env" | ForEach-Object {
    if ($_ -match "^\s*([^#=]+)=(.*)$") { [Environment]::SetEnvironmentVariable($Matches[1].Trim(), $Matches[2].Trim()) }
  }
}
& "$root\.venv\Scripts\python.exe" -m uvicorn app.main:app --port 8000 --app-dir backend
