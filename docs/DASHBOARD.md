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
| `--dataset` | `basil farm-02 · SAM2=data/derived/metrics/basil-farm02-sam2.csv` and `lettuce=data/derived/metrics/lettuce-timeseries.csv` |
| `--out` | `output/dashboard/index.html` |
| `--pipeline-version` | `unrecorded` |
| `--title` | `PlantVision · growth dashboard` |
| `--now` | current UTC time |

The command prints exactly one JSON line, for example:

```json
{"status": "ok", "out": "output/dashboard/index.html", "datasets": 2, "rows": 1524, "alerts": {"critical": 2, "warn": 4}, "charts": 8}
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
one. The default basil dataset is `basil farm-02 · SAM2` →
`data/derived/metrics/basil-farm02-sam2.csv` (the mask-derived SAM2 bridge)
and lettuce is → `data/derived/metrics/lettuce-timeseries.csv`. The 69-row
`data/derived/metrics/timeseries.csv` is a legacy white-light series and is
only rendered when passed explicitly.

The CSV header must equal `plantvision.analytics.timeseries.TIMESERIES_COLUMNS`
or be a strict prefix of it (legacy stores with fewer trailing columns are
accepted). Any other header aborts the build with a `ValueError` naming both
headers.

## Basil farm-02 SAM2 series (A2 bridge)

The default basil dataset is rebuilt deterministically from the SAM2 proposal
export; no model inference happens here and the node imports no `torch`.

```sh
.venv/bin/python scripts/build_series_from_proposals.py
```

It rewrites `data/derived/metrics/basil-farm02-sam2.csv` atomically and prints
one JSON line:

```json
{"status": "ok", "out": "data/derived/metrics/basil-farm02-sam2.csv", "proposals": 697, "rows": 681, "excluded_rejected": 16, "excluded_review": 0, "missing_review": 0, "missing_frame": 0, "missing_mask": 0, "missing_sidecar": 0, "read_error": 0, "scale_rows": 677, "scale_pct": 99.41, "trait_rows": 681, "errors": 0, "first_at": "2026-10-24T05:48:26.000000Z", "last_at": "2026-10-27T15:48:29.000000Z", "median_area_px": 148429.0, "median_area_cm2": 91.842}
```

`--review-status accepted` renders only the human-accepted subset (420 rows,
416 with scale, 99.05 %, median `area_px` 156839). The default `all` keeps
accepted + pending rows; review status lives in the label manifest and is
**never** written to the timeseries.

### Quality semantics (physical defects only)

`quality_flag` stores physical capture defects, recomputed from the sidecar
raw metrics with the import-time thresholds
(`PHYSICAL_QUALITY_THRESHOLDS` in `analytics/proposal_series.py`):

| Sidecar metric | Condition | Token |
|---|---|---|
| `blur_lapvar` | `< 10.0` | `blur` |
| `brightness` | `< 40.0` | `dark` |
| `brightness` | `> 220.0` | `bright` |

A frame with no defect records `ok` (the rule engine treats `ok` as "no
flags"); several defects join with `|`. `red` is **not** copied from the
sidecar: the farm-02 blurple LED regime is red-dominant by design, so red
dominance describes the light spectrum, not a defect. `red_dominance_min` in
`configs/capture-farm-02.yaml` applies to white-light captures only.

`--quality-mode` selects the behaviour:

| Value | Effect on `quality_flag` |
|---|---|
| `physical` (default) | Recompute blur/dark/bright; `ok` when clean |
| `none` | Leave the cell blank (no quality claim) |

The dashboard label is `basil farm-02 · SAM2` with the caveat: *SAM2
mask-derived series (sam2.1_hiera_small, marker prompt), not a classical
HSV/ExG measurement; review status stays in the label manifest; scale
recomputed per frame from the 45 mm ArUco tag.*

Scale provenance: `plantvision.vision.scale.px_per_mm` (`vision/scale.py:73`)
detects the printed `DICT_5X5_50`, 45 mm marker in every frame; `px_per_mm`
and everything derived from it are recomputed per frame, never carried over.
Rows without a detectable marker keep blank `px_per_mm`/`area_cm2` and
`scale_ok=false`.

The 69-row `timeseries.csv` is the legacy white-light `phone-01` series. It is
not a default and is rendered explicitly with:

```sh
.venv/bin/python scripts/build_dashboard.py \
  --dataset "basil white-light (phone-01)=data/derived/metrics/timeseries.csv"
```

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
- The farm-02 basil series is the **SAM2 bridge**: mask-derived, not a
  classical HSV/ExG measurement. It exposes `settings_source`,
  `light_regime` and `treatment_id` as blank by design (the capture rig does
  not record them), so the provenance warning reads "not recorded", not
  "pipeline broke".
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

Expected: `57 passed`. The full suite is `.venv/bin/pytest -q`.

## Interactive shell (v2)

The v2 renderer is a package, not a second copy of the legacy module:
`plantvision.analytics.dashboard` re-exports the frozen v1 API from
`dashboard/legacy.py` and adds `build_report`, `load_panels`, `Panel` and
`ReportResult`. The old CLI (`scripts/build_dashboard.py`) is unchanged.

```sh
.venv/bin/python scripts/build_report.py \
  --now 2026-11-03T12:00:00Z \
  --out output/dashboard/index.html
```

The command prints exactly one JSON line:

```json
{"alerts": {"critical": 3, "warn": 6}, "bytes": 457460, "charts": 8,
 "days": 11, "frames": 12, "json_bytes": 174267, "now_source": "cli",
 "out": "output/dashboard/index.html", "panels": 3, "rows": 1593,
 "status": "ok"}
```

### Flags

| Flag | Default | Meaning |
|---|---|---|
| `--panels` | `configs/dashboard-panels.yaml` | panel metadata (crop/method/csv live only here) |
| `--out` | `output/dashboard/index.html` | destination HTML |
| `--now` | last capture in the data | ISO-8601 reference time for age/gap rules |
| `--title` | config `title` | page title |
| `--thumb-width` | `288` | thumbnail width, px |
| `--thumb-quality` | `58` | initial JPEG quality |
| `--no-frames` | off | skip embedded thumbnails |
| `--max-bytes` | `1048576` | hard page budget |
| `--dump-payload` | none | write the JSON payload (no frames/cards) |
| `--lang` | `en` | initial language, `en` or `ru` |

Exit codes: `0` ok, `1` data/IO/YAML error, `2` argparse usage, `3` page over
`--max-bytes` (nothing is written). Output is deterministic for a fixed
`--now`: two builds produce identical `sha256` bytes.

### Budgets

Page hard gate 1 MiB (exit 3). The accepted build ranges are 620 000–700 000
bytes with the default static-growth fallback and 480 000–560 000 bytes with
`--no-static-growth`; payload JSON stays under 256 kB and embedded frames under
300 kB (quality ladder 58 -> 45 -> drop). The inline client renderer budget is
60 000 characters. The page contains no `http://`, `https://`, `<link>`,
`@import` or webfont, so it works from `file://`.

### Language

Every visible string is embedded twice (`data-en` / `data-ru`) with the active
language as text. The top-bar toggle rewrites `textContent`, updates
`<html lang>`, persists the choice in `localStorage` (`pv-lang`) and does not
reload. `--lang` sets the initial language; Russian copy is a real translation
and numbers/units stay numeric.

### Tabs

`Overview[status,kpi] · Crops · Growth[area-px,area-cm2,rate,daily] · Shape ·
Data quality · Alerts · Compare · Capture · Method`. Gate 1 populates
**Overview** and **Growth** (10 cards); the other seven tabs are shell entries
with an explicit "coming in gate 2" state. The card registry, token system,
chart primitives, payload contract, drawer, frames and budget gate are complete,
so gate 2 only adds cards and config.

Deep links use `#/<tab>/<sub>~<chart-id>`, e.g.
`#/growth/area-cm2~ch-gr-area-cm2` opens the tab, the sub-tab and the drawer in
one pass. `Esc` closes the drawer and returns focus; the rail is a roving
`tablist`; every chart is `role="img"` with a title and description.

### Vocabulary (D7/D15)

- **not measured**: the instrument never produced a value (`quality_flag` blank
  in a store that does not record it).
- **not recorded**: a provenance fact was never captured (`settings_source`
  blank, `treatment_id` absent).
- **not computable**: the value needs at least two measured days
  (`growth_rate` on a one-day panel).

A measured `0` is still rendered as `0`; only blank/unparseable cells become a
missing label.

### Regenerate

```sh
.venv/bin/python scripts/build_series_from_proposals.py   # if masks changed
.venv/bin/python scripts/build_dashboard.py               # legacy page
.venv/bin/python scripts/build_report.py --now <ISO>      # v2 page
```

`data/derived/` is gitignored: rebuild after `update_metrics.py` rather than
committing generated HTML.

### Rollback (source only)

```sh
git checkout 2c0393d -- src/plantvision/analytics/dashboard.py docs/DASHBOARD.md
rm -rf src/plantvision/analytics/dashboard scripts/build_report.py \
  configs/dashboard-panels.yaml
rm -f tests/test_dashboard_v2_model.py tests/test_dashboard_v2_charts.py \
  tests/test_dashboard_v2_html.py tests/test_build_report.py
.venv/bin/pytest -q
```

## Control bar

The sticky top bar carries six controls before the language toggle:
`[crop] [window] [aggregation] [mode] [reset] [snapshot] [EN]`. Per-panel
freshness is shown once, as the age column of the Overview status board; the
top bar stays unclipped at 1280 and 1440.

| Control | Values | Default | Applies to |
|---|---|---|---|
| crop | one checkbox per `payload.crops` entry | all | every tab |
| window | `24h`, `7d`, `30d`, `all` | `all` | time-windowed cards |
| aggregation | `raw`, `hourly`, `daily` | `raw` | line/area/bars and the daily table |
| mode | `abs`, `idx`, `delta` | `abs` | line/area cards only |
| reset | clears the four filters | disabled at defaults | every tab |
| snapshot | opens Export / Diff | always enabled | every tab |

The last checked crop cannot be unchecked. A selected panel with no frames in
the window stays in the legend, muted, with its last-frame date.

Growth card copy follows the crop filter. The payload carries `now_parts` and
`conclusion_parts` keyed by panel id plus `now_join` / `conclusion_join`
templates; the client joins only the selected panels in config order. With all
crops selected the precomputed sentence is rendered unchanged. The `do` line
switches to `ui.do.ok` when every selected panel is healthy and to the
rule-specific action when any selected panel is critical.

## Hash grammar

```
#/<tab>[/<sub>][~<chart-id>][!c=<crop>[,<crop>…]&w=<24h|7d|30d|all>&a=<raw|hourly|daily>&m=<abs|idx|delta>]
```

Filters are always last. Parsing strips `!` first, then `~`, then `/`; the
page never rewrites an invalid hash, it renders sanitised defaults and shows
`#pv-filter-note`. Canonical parameter order is `c, w, a, m`, defaults are
omitted, and crop order follows `payload.crops`.

Examples:

| State | Hash |
|---|---|
| fresh page | `#/overview` |
| growth, area-cm2, two crops, 7 days, hourly, index | `#/growth/area-cm2!c=basil,lettuce&w=7d&a=hourly&m=idx` |
| same + drawer | `#/growth/area-cm2~ch-gr-area-cm2!c=basil,lettuce&w=7d&a=hourly&m=idx` |
| crops drill-down for one panel | `#/crops/lettuce-farm03-exg` |
| alerts, one crop, defaults for the rest | `#/alerts!c=lettuce` |

## Snapshot schema and filename

Snapshot export runs entirely in the browser and writes `pv-snapshot/1`:
`schema, generated_at, now_source, page, filters, window, panels, cards,
sources, thumbnails, thumbnail_state`. `generated_at` and every `now` value are
UTC ISO-8601 strings ending in `Z` (never `+00:00`). Panel series points are
`[ISO-8601 Z string, number]`; `null` values are omitted but counted in
`stats.missing`; floats are rounded to six decimals. The JSON is key-sorted and
contains no SVG.

Filename:

```
pv-snapshot-<YYYYMMDDTHHMMSSZ>-<cropslug>-<window>-<agg>-<mode>.json
```

`cropslug` is the selected crops in `payload.crops` order joined by `+` with
spaces replaced by `_`, or `all`; the timestamp comes from `payload.now`, never
the wall clock. Identical inputs produce byte-identical files.

The Diff pane reads two files with `FileReader` (works from `file://`), rejects
non-`pv-snapshot/1` input, banners a filter mismatch, and reports sorted
per-metric `A | B | Δ` rows with `|Δ| ≤ 1e-9` collapsed as unchanged.

## Byte budgets

| Budget | Limit |
|---|---|
| page, hard gate | 1 MiB, exit 3 |
| page, default (`--static-growth`) | 620 000–700 000 bytes |
| page, lean (`--no-static-growth`) | 480 000–560 000 bytes |
| payload JSON | 256 kB, hard gate, exit 3 |
| embedded frames | 300 kB, quality ladder 58 -> 45 -> drop |
| inline client renderer | 60 000 characters |

The page contains no `http://`, `https://`, `<link>`, `@import` or webfont, so
it works from `file://`.

## Static-growth fallback

`--static-growth` (default) keeps the Python-rendered Growth SVG as the no-JS
fallback; the client renderer replaces those nodes in place when JavaScript is
available. `--no-static-growth` drops that fallback (the JS-required variant)
and is verified separately.
