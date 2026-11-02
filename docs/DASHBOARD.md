# Growth dashboard

## What it is

`scripts/build_dashboard.py` renders one self-contained HTML file from the
metrics CSVs. CSS and every chart PNG are embedded, so the page needs no
server, no JavaScript, no database and no network access. Alerts come from a
pure, deterministic rule engine (`plantvision.analytics.rules`) — no LLM is
involved anywhere in the pipeline.

## Build

From the repository root:

```sh
.venv/bin/python scripts/build_dashboard.py \
  --out output/dashboard/index.html \
  --now "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
```

Defaults:

| Option | Default |
|---|---|
| `--dataset` | `basil=data/derived/metrics/timeseries.csv` and `lettuce=data/derived/metrics/lettuce-timeseries.csv` |
| `--out` | `output/dashboard/index.html` |
| `--pipeline-version` | `unrecorded` |
| `--title` | `PlantVision — growth dashboard` |
| `--now` | current UTC time |

The command prints exactly one JSON line, for example:

```json
{"status": "ok", "out": "output/dashboard/index.html", "datasets": 2, "rows": 912, "alerts": {"critical": 3, "warn": 4}, "charts": 7}
```

## View

```sh
xdg-open output/dashboard/index.html
# or open file:///home/codexrescriptus/devel/CV/plantvision-lab/output/dashboard/index.html
```

## View from another machine

Serve the directory over the LAN:

```sh
.venv/bin/python -m http.server 8765 --bind 0.0.0.0 --directory output/dashboard
```

Then open `http://<host-lan-ip>:8765/index.html`. If `ufw` is active, allow
incoming `8765/tcp` first. The page itself still needs no server for local
viewing because every asset is embedded.

## Datasets

Datasets are passed as `LABEL=PATH`; repeat `--dataset` to render more than
one. Default labels and paths are `basil` →
`data/derived/metrics/timeseries.csv` and `lettuce` →
`data/derived/metrics/lettuce-timeseries.csv`.

The CSV header must equal `plantvision.analytics.timeseries.TIMESERIES_COLUMNS`
or be a strict prefix of it (legacy stores with fewer trailing columns are
accepted). Any other header aborts the build with a `ValueError` naming both
headers.

## Rules

Rules run per `zone_id` (blank → `unknown`); timestamps are parsed as ISO-8601
and unparseable rows are skipped by time rules. `now` is injected, so results
are reproducible. Findings sort critical → warn, then `(zone, rule_id)`.

| rule_id | Formula (per zone) | warn | critical | Precondition |
|---|---|---|---|---|
| `growth-stall` | trailing 24 h; split at index mid; `pct = (median(2nd half area_px) − median(1st half)) / median(1st half) × 100`; fire when `abs(pct) < 2.0` | warn | — | ≥6 dated rows, ≥2 numeric `area_px` per half |
| `area-drop` | `drop = (median(prior ≤30 area_px) − median(last 3)) / median(prior) × 100` | ≥15% | ≥30% | ≥6 numeric `area_px`, baseline > 0 |
| `solidity-drop` | `drop = median(prior ≤30 solidity) − median(last 3)` | ≥0.08 | ≥0.15 | ≥6 numeric `solidity` |
| `scale-coverage` | `drop_pt = true% (first half) − true% (second half)` | ≥15 pt | ≥30 pt | ≥6 dated rows, ≥3 per half |
| `capture-gap` | max consecutive `Δt` in hours | ≥12 h | ≥24 h | ≥2 dated rows |
| `stale-data` | `age_days = max(0, (now − last captured_at) / 86400)` | ≥2 d | ≥7 d | ≥1 dated row |
| `quality-flag-rate` | `100 × rows with ≥1 token not in {"", "ok"} / rows in trailing 24 h` | ≥10% | ≥25% | ≥5 rows in window |
| `camera-settings-change` | count of distinct non-blank `(exposure_s, white_balance, gain_db)` | >1 | — | ≥1 non-blank setting |
| `camera-settings-provenance` | `100 × rows with settings_source ∈ {exif, app, manual} / rows` | <50% | — | rows > 0 |

## Exit codes

| Code | Meaning |
|---|---|
| 0 | Dashboard written; one JSON line with `"status": "ok"` |
| 1 | Data or I/O error (missing CSV, header mismatch, duplicate label, unwritable output); JSON line with `"status": "error"` |
| 2 | Usage error (bad `--dataset` etc.); argparse prints usage on stderr |

## Limits

- Thresholds are first-pass defaults calibrated on two series. Tune them after
  P2 produces blurple masks; they are `RuleConfig` fields, not CLI flags.
- The store has no `pipeline_version` or `crop_id` column, so the dashboard
  cannot separate pipeline generations or crops beyond the dataset label.
- The existing 69-row basil store is the **white-light `phone-01` series**
  (2026-10-16/17, zone `shelf-a/tray-1`), not the farm-02 blurple run. The
  dashboard labels it as that white-light series and does not present it as
  farm-02 basil.
- farm-02 basil (697 frames, blurple) has **no classical series**. A classic
  HSV/ExG mask covers ~1% of the frame versus ~22% plant area from SAM2, so a
  rebuilt classical series would be false data. Basil metrics come from SAM2
  proposals and the P2 student; bridging that into the timeseries is deferred
  to milestone A2.
- A framing change in the phone-01 series makes endpoint growth misleading;
  treat the area trend as indicative, not a growth rate.
- Multi-zone datasets render one overlaid chart per metric; per-zone facets are
  deferred.
- `data/derived/` is gitignored: regenerate the dashboard after every
  `update_metrics.py` run instead of committing generated HTML.

## Tests

```sh
.venv/bin/pytest tests/test_analytics_rules.py tests/test_analytics_dashboard.py tests/test_build_dashboard.py -q
```

Expected: `36 passed`. The full suite is `.venv/bin/pytest -q`.
