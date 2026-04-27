$ErrorActionPreference = "Stop"

$projectRoot = Split-Path -Parent $PSScriptRoot
$activateScript = Join-Path $projectRoot "venv\\Scripts\\Activate.ps1"

if (-not (Test-Path $activateScript)) {
    throw "Virtual environment not found at $activateScript"
}

. $activateScript
Set-Location $projectRoot

python -m app.main
