# deploy/windows — PlantVision on Windows (Task Scheduler)

Runs `plantvision.capture.capture_once` every 1 minute on Windows, mirroring the Linux
systemd timer. The code is cross-platform Python; only the scheduler differs (decision D10).

## Files
- `run_capture.cmd` — Task Scheduler action: runs the venv `capture_once`, appends stdout/stderr
  to `data\capture_task.log`.
- `register-task.ps1` — registers the per-user `PlantVisionCapture` task (every 1 minute).

## Setup
```powershell
git clone https://github.com/MariganMarigam/plantvision-lab.git
cd plantvision-lab
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
# put the phone's LAN address into configs\capture.yaml -> source_url
.\.venv\Scripts\python.exe -m plantvision.capture.capture_once --config configs\capture.yaml
# then register the cadence:
powershell -ExecutionPolicy Bypass -File .\deploy\windows\register-task.ps1
```

## Operate
- Force one run: `schtasks /Run /TN "PlantVisionCapture"`
- Inspect: `schtasks /Query /TN "PlantVisionCapture" /V /FO LIST`
- Remove: `schtasks /Delete /TN "PlantVisionCapture" /F`
- Logs: `data\capture_task.log` (scheduler stdout/stderr) and `data\capture.log` (per-run JSONL).

## Notes
- Outbound-only HTTP to the phone; no inbound Windows Firewall rule is required.
- Outside the light window (default 06:00–22:00 local) a run exits 0 with `skipped_dark`.
