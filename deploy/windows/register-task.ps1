<#
.SYNOPSIS
  Registers the PlantVisionCapture scheduled task (runs every N minutes, current user).
.DESCRIPTION
  Wraps deploy\windows\run_capture.cmd. Default cadence: 1 minute (decision D3).
  Requires no admin rights: it registers a per-user task (RunLevel Limited).
.EXAMPLE
  powershell -ExecutionPolicy Bypass -File .\deploy\windows\register-task.ps1
#>
[CmdletBinding()]
param(
  [string]$TaskName = "PlantVisionCapture",
  [int]$IntervalMinutes = 1
)

$ErrorActionPreference = "Stop"

# Repo root = two levels up from this script (deploy\windows\register-task.ps1).
$repo   = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$runner = Join-Path $PSScriptRoot "run_capture.cmd"

if (-not (Test-Path $runner)) {
  throw "Runner not found: $runner"
}

$action = New-ScheduledTaskAction -Execute $runner -WorkingDirectory $repo

$trigger = New-ScheduledTaskTrigger -Once -At (Get-Date) `
  -RepetitionInterval (New-TimeSpan -Minutes $IntervalMinutes)

$settings = New-ScheduledTaskSettingsSet `
  -MultipleInstances IgnoreNew `
  -StartWhenAvailable `
  -ExecutionTimeLimit (New-TimeSpan -Minutes 5)

$principal = New-ScheduledTaskPrincipal `
  -UserId "$env:USERDOMAIN\$env:USERNAME" `
  -LogonType Interactive `
  -RunLevel Limited

Register-ScheduledTask `
  -TaskName $TaskName `
  -Action $action `
  -Trigger $trigger `
  -Settings $settings `
  -Principal $principal `
  -Description "PlantVision capture_once every $IntervalMinutes minute(s)" `
  -Force | Out-Null

Write-Host "Registered task '$TaskName' -> $runner (every $IntervalMinutes min)."
Write-Host "Test it now:  schtasks /Run /TN `"$TaskName`""
Write-Host "Inspect:      schtasks /Query /TN `"$TaskName`" /V /FO LIST"
