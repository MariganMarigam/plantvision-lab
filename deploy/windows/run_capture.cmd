@echo off
REM PlantVision capture runner for Windows Task Scheduler.
REM Runs capture_once from the repo venv and appends stdout/stderr to data\capture_task.log.
REM capture_once itself writes the semantic per-run log to data\capture.log (config log_path).
setlocal

REM Repo root = two levels up from this script (deploy\windows\ -> repo root).
set "REPO=%~dp0..\.."
pushd "%REPO%" || exit /b 1

set "ARGS=-m plantvision.capture.capture_once --config configs\capture.yaml"

if exist ".venv\Scripts\python.exe" (
  ".venv\Scripts\python.exe" %ARGS% >> data\capture_task.log 2>&1
) else (
  py -3.12 %ARGS% >> data\capture_task.log 2>&1
)

REM Capture exit code is authoritative for the task; freeze it BEFORE the flywheel step.
set "RC=%ERRORLEVEL%"

REM P1 flywheel: measure newly captured frames. Best-effort; NEVER affects RC or capture.
if exist ".venv\Scripts\python.exe" (
  ".venv\Scripts\python.exe" scripts\update_metrics.py --config configs\pipeline.yaml >> data\capture_task.log 2>&1
) else (
  py -3.12 scripts\update_metrics.py --config configs\pipeline.yaml >> data\capture_task.log 2>&1
)

popd
endlocal & exit /b %RC%
