# PlantVision on Windows — deployment guide (Task Scheduler)

> Author: @scout · 2026-10-15 · Companion to `output/handoff/HANDOFF-2026-10-15.md`.
> Decision D10: the running host is **Windows**; the 10-min cadence is owned by **Task Scheduler**.
> The wrapper/register scripts are specified verbatim in `output/handoff/deploy-windows-spec.md` (Ivan creates them).

Goal: on a Windows box, pull one frame every 10 minutes from the phone's IP Webcam and store it exactly
as on Linux — one JPEG + one JSON sidecar under `data\originals\...`, one JSONL line per run in
`data\capture.log`. The capture code is cross-platform Python; only the scheduler differs.

---

## 1. Prerequisites

| Need | Notes |
|---|---|
| **Git for Windows** | `winget install --id Git.Git -e` or https://git-scm.com/download/win |
| **Python 3.12** | `winget install --id Python.Python.3.12 -e` (or python.org). Verify: `py -3.12 --version` |
| **pip** | Bundled with Python (`python -m pip`). |
| Phone on the **same LAN** as the Windows box, IP Webcam **Start server** running. |

Optional but recommended: enable **long paths** (Developer Mode / `git config --system core.longpaths true`).

---

## 2. Clone and create the virtual environment

Open **PowerShell** (or cmd), then:
```powershell
git clone https://github.com/MariganMarigam/plantvision-lab.git
cd plantvision-lab
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
```
> In cmd the same install line: `.venv\Scripts\python -m pip install -e .[dev]`
> In PowerShell always quote `".[dev]"` (bare brackets are parsed specially).

---

## 3. Set `source_url`

Edit `configs\capture.yaml` and set the phone's real LAN address:
```yaml
source_url: "http://192.168.1.5:8080/photo.jpg"   # ← the IP IP Webcam shows on-screen
```
Pin the address in the router (static DHCP lease by phone MAC) so it stops drifting — otherwise the
config breaks on every router reboot or phone reconnect.

---

## 4. Manual test run (before scheduling anything)

```powershell
.\.venv\Scripts\python.exe -m plantvision.capture.capture_once --config configs\capture.yaml
```
Expected JSON: `{"status":"ok","sha256":"…","path":"data\\originals\\phone-01\\shelf-a_tray-1\\<day>\\…jpg"}`
(in the light window). Run it twice on the same frame → `{"status":"duplicate"}`. At night → `{"status":"skipped_dark"}`.

Run the tests once:
```powershell
.\.venv\Scripts\python.exe -m pytest -q      # expect: 23 passed
```

---

## 5. Schedule every 10 minutes — Task Scheduler

Use the scripts from `output/handoff/deploy-windows-spec.md` (create them first):
`deploy\windows\run_capture.cmd` and `deploy\windows\register-task.ps1`.

### Option A — GUI walkthrough
1. **Start → Task Scheduler → Create Task** (not "Basic").
2. **General** tab: Name `PlantVisionCapture`; select **Run only when user is logged on**; **Run with highest
   privileges** unchecked.
3. **Triggers** tab → **New…** → *Begin the task: On a schedule* → *One time*, set Start = now →
   check **Repeat task every:** `10 minutes` → **for a duration of:** `Indefinitely` → OK.
4. **Actions** tab → **New…** → *Start a program* →
   Program/script: `C:\path\to\plantvision-lab\deploy\windows\run_capture.cmd`
   Start in: `C:\path\to\plantvision-lab`
5. **Conditions** tab: uncheck *Start the task only if the computer is on AC power* (if a laptop).
6. **Settings** tab: check *If the task is already running, do not start a new instance*; check
   *If the task fails, restart every* `10 minutes` (a few attempts).
7. **OK** (enter Windows password if prompted). Right-click the task → **Run** to test; confirm files appear.

### Option B — one-liner / script
PowerShell (uses the register script, recommended):
```powershell
powershell -ExecutionPolicy Bypass -File .\deploy\windows\register-task.ps1
```
cmd `schtasks` equivalent:
```cmd
schtasks /Create /TN "PlantVisionCapture" /SC MINUTE /MO 10 ^
  /TR "C:\path\to\plantvision-lab\deploy\windows\run_capture.cmd" /F
```
> `schtasks /SC MINUTE /MO 10` = every 10 minutes. Verify: `schtasks /Query /TN "PlantVisionCapture" /V /FO LIST`.
> Remove: `schtasks /Delete /TN "PlantVisionCapture" /F`.

---

## 6. Windows Firewall notes

- The capture is **outbound-only** HTTP to the phone — Windows normally needs **no inbound rule**.
- Windows may show a **Firewall prompt** on the first run of `python.exe`; choose **Allow on private networks**
  (the capture is a private-LAN client). If syslog/phone checks are blocked, allow `python.exe` for Private.
- If you later add an ingest **server** on Windows, then open the chosen port on Private only.

---

## 7. Where files land (identical to Linux)

```
plantvision-lab\
├─ data\
│  ├─ originals\phone-01\shelf-a_tray-1\<YYYY-MM-DD>\<UTC-TS>_<sha16>.jpg   ← original
│  │                                                        └─ .json        ← sidecar (sha256, timestamps, dims)
│  ├─ spool\                                     ← reconnect queue (sha256.jpg + .json), empty when healthy
│  ├─ capture.log                                ← one JSONL line per run (ok|duplicate|skipped_dark|gap|spooled)
│  └─ capture_task.log                           ← scheduler stdout/stderr (added by run_capture.cmd)
└─ .venv\ , configs\ , src\ , tests\ , deploy\windows\
```

---

## 8. Dark-window behaviour

`capture_once` self-gates to `light_window` (default **06:00–22:00 local**, start inclusive / end exclusive).
Task Scheduler fires every 10 minutes; a run outside the window prints `{"status":"skipped_dark"}`, writes
**no** frame, and exits **0**. In Task Scheduler this shows as **Last Run Result `0x0`** — that is normal at night.
No gap is logged for a dark skip (only real pull failures log `gap`).

---

## 9. Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| `status:"gap"` / `connection refused` in `data\capture.log` | IP Webcam server not running, or wrong IP | Open IP Webcam → **Start server**; copy the on-screen URL into `configs\capture.yaml` |
| Worked, then suddenly gaps | Phone **IP changed** (no reservation) | Give the phone a **static DHCP lease**; update `source_url`; re-run the manual test |
| `ModuleNotFoundError: plantvision` | venv not activated / not installed | Run via `.\.venv\Scripts\python.exe -m …` and (re)run `pip install -e ".[dev]"` |
| `No such file or directory: '.venv'` / no venv | venv not created | `py -3.12 -m venv .venv` then install (step 2) |
| `run_capture.cmd` will not run / register-task.ps1 blocked: *"running scripts is disabled"* | PowerShell **execution policy** | Run with `-ExecutionPolicy Bypass` (as in §5 Option B), or `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned` |
| Task shows *Last Run Result 0x…* non-zero every 10 minutes | capture error (gap) | Read `data\capture_task.log` and `data\capture.log`; usually the phone is unreachable |
| Task never runs | trigger/timezone, or "only when logged on" and you logged out | Keep **Run only when user is logged on**, or store credentials; re-check the trigger |
| Nothing overnight | dark window / computer asleep | Expected (D8); set **StartWhenAvailable** so a missed run backfills after wake |

---

## 10. Stop / inspect

```cmd
schtasks /Query /TN "PlantVisionCapture" /V /FO LIST
schtasks /End    /TN "PlantVisionCapture"
schtasks /Run    /TN "PlantVisionCapture"        :: force one run now
schtasks /Delete /TN "PlantVisionCapture" /F     :: remove the schedule
```
Logs: `data\capture_task.log` (scheduler stdout/stderr) and `data\capture.log` (per-run JSONL).
