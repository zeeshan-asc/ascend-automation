$ErrorActionPreference = "Stop"

$projectRoot = Split-Path -Parent $PSScriptRoot
$webScript = Join-Path $PSScriptRoot "run_web.ps1"
$workerScript = Join-Path $PSScriptRoot "run_worker.ps1"

$webProcess = Start-Process powershell -ArgumentList @(
    "-NoExit",
    "-ExecutionPolicy",
    "Bypass",
    "-File",
    $webScript
) -WorkingDirectory $projectRoot -PassThru

$workerProcess = Start-Process powershell -ArgumentList @(
    "-NoExit",
    "-ExecutionPolicy",
    "Bypass",
    "-File",
    $workerScript
) -WorkingDirectory $projectRoot -PassThru

Write-Host "Web PID: $($webProcess.Id)"
Write-Host "Worker PID: $($workerProcess.Id)"
