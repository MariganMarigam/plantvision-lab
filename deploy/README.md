# deploy/systemd — PlantVision capture timer

Runs `plantvision.capture.capture_once` every 10 minutes via the **user-level**
systemd timer. The timer fires around the clock; `capture_once` self-gates on
`light_window` (06:00–22:00 local by default) so dark-window runs exit 0 with
status `skipped_dark` — no fetch, no frame, no gap.

## Files

- `plantvision-capture.service` — oneshot unit running
  `~/.venv/bin/python -m plantvision.capture.capture_once --config configs/capture.yaml`
  from `%h/devel/plantvision-lab`.
- `plantvision-capture.timer` — `OnBootSec=2min`, `OnUnitActiveSec=10min`,
  `Persistent=true` (backfills one missed run after sleep/reboot).

Verified with `systemd-analyze verify` (both files, exit 0), 2026-10-13.

## Install (do this only once the phone exists on the LAN)

```sh
cd ~/devel/plantvision-lab
# 1. Put the phone's real LAN address into the config first:
#    sed -i "s|http://192.168.1.50:8080/photo.jpg|http://<phone-ip>:8080/photo.jpg|" configs/capture.yaml
# 2. Sanity-run once by hand; expect status ok/duplicate (or skipped_dark at night):
.venv/bin/python -m plantvision.capture.capture_once --config configs/capture.yaml

# 3. Install + enable the timer:
mkdir -p ~/.config/systemd/user
cp deploy/systemd/* ~/.config/systemd/user/
systemctl --user daemon-reload
systemctl --user enable --now plantvision-capture.timer

# 4. Confirm:
systemctl --user list-timers plantvision-capture.timer
systemctl --user status plantvision-capture.service
```

## Operating

- Logs (unit stdout): `journalctl --user -u plantvision-capture.service -n 50`
- Capture status log (JSONL, one line per run): `data/capture.log`
  (`ok | duplicate | skipped_dark | gap | spooled`).
- Originals + sidecars: `data/originals/<camera_id>/<zone>/<day>/` (gitignored).
- Stop the cadence: `systemctl --user disable --now plantvision-capture.timer`.
- After editing a unit file: re-copy to `~/.config/systemd/user/`, then
  `systemctl --user daemon-reload` and restart the timer.

## Design note

systemd (not cron) is used so missed-run backfill (`Persistent=true`) and
stdout logging via journald are unified. `Type=oneshot` makes a non-zero exit
(service failure, i.e. a `gap`) visible in `systemctl --user status`.
