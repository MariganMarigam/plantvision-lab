# Adopted OSS findings — 2026-10-22

> Source: `output/research/2026-10-22-vertical-farm-repos.md` (Scout, verified against the GitHub API on
> 2026-10-22). Companion decision context: `docs/forward-plan-2026-10-22.md` (D9, phase P1.5).
> Rule adopted with all findings: **steal algorithms and schemas, not stacks.**

## Verdicts — the four named repos

| Repo | License | Last commit | What it is | Verdict |
|---|---|---|---|---|
| `GaiaKnowledge/VerticalFarming` | **MIT** | 2022-10-24 (dormant ~4 y) | business-risk spreadsheet tool (Excel + p-box survival analysis), no measurement code | **idea-only** (uncertainty ranges); dormant |
| `alexsteinerr/vertical-farm` | **none** (all rights reserved) | 2024-07-07 | student capstone: ESP32-CAM + Express/Mongo dashboard, history lost on restart, zero-padding bugs | **idea-only** (camera liveness/last-seen, device registry); **code not legally reusable** |
| `gpappasv/Vertical-Farming` | **none** (all rights reserved) | 2024-06-10 | Zephyr/nRF BLE + CoAP sensor-network firmware; well-structured, cloud tier dead | **idea-only** (sample-then-publish, FSM + watchdog, node→zone inventory); **code not legally reusable** |
| `divyansh2111/Vertical-Farming-Optimizations` | **none** (all rights reserved) | 2021-05-23 (dormant ~5 y) | Flask + EfficientNet-B7 disease demo, no measurement, no scale, no provenance | **avoid** — negative example: single-shot classifier with no metric; pinned stack uninstallable on modern Python |

Net reusable *code* from the four: zero lines. Net reusable *design*: uncertainty reporting, camera liveness,
store-and-forward sampling, readable prediction cards. None of the four does scale-correct measurement.

## Adopted now (into the forward plan, P1.5)

1. **PlantCV trait formulas** (`danforthcenter/plantcv`, MPL-2.0): convex-hull area, solidity, perimeter,
   equivalent-ellipse axes (+ extent, centroid). Reimplemented from the documented definitions — no code copied,
   no package as a dependency. Separates a collapsing canopy from real growth at constant projected area.
2. **MIAPPE-lite provenance keys** (MIAPPE 1.2 vocabulary, field *names* only — doi:10.1111/nph.16544):
   `experiment_id`, `observation_unit_id`, `biosource_id`, `treatment_id`, `environment_id`, `method_ref` +
   camera-settings fields, all nullable sidecar/CSV columns so legacy data stays valid.
3. **Coverage audit**: expected cadence grid per zone; `missing` vs `outside_dark_policy` vs `present`,
   duplicates, longest gap. "No data" becomes distinguishable from "no change" — no interpolation, no
   zero-padding (the recurring failure mode of the surveyed repos).
4. **Camera-settings capture**: `exposure_s` / `white_balance` / `gain_db` + `settings_source` in provenance.
   Under BLURPLE a white-balance change shifts the mask threshold globally — **a WB change can masquerade as
   growth**; an area step change coinciding with a settings change is a camera event until proven otherwise.

## Ideas only (vocabulary and patterns, no code)

- `kizniche/Mycodo` (GPL-3.0): Input/Function/Output model, first-class measurement units, process-isolated
  sensor daemons. Read for the sensor-track design; never paste (GPL).
- `FarmBot/FarmBot-Web-App` (MIT): command→ack→log over MQTT, schedules as data rows, device last-seen
  reconciliation. Rails/Elixir stack is not adoptable.
- `Pragmatismo/Pigrow` (GPL-3.0): closest philosophy (files + CSV + HTML + cron, no DB); date-grouped
  timelapse index; per-growbox config-as-dict. Triggers lack hysteresis — noted as anti-pattern.

## Later (deferred, revisit on trigger)

- **Streamlit** read-only inspector over `timeseries.csv` (Apache-2.0) — first dashboard choice when the
  terminal is not enough; bind localhost. **Grafana** (AGPL-3.0) stays an unmodified external service, only if
  push alerts are wanted. Both deferred until a sensor/actuator actually exists (D9).
- **ESPHome + MQTT sensor nodes** (MIT+GPL composite): declarative firmware for SHT31/pH/EC or ESP32-CAM
  nodes with stable MQTT topics + units. Not until a physical sensor track starts.
- Related deferred items from the survey: FarmBot-style command→ack→log for camera/light control, PlantCV
  `WorkflowConfig`-style job/collation seam (only past ~1k frames / multi-zone).

## Rejected (explicitly)

- **Copying any code from the four named repos** — three carry no license (default = all rights reserved;
  legally un-copyable in a public repo), the fourth (GaiaKnowledge) is a dormant business-spreadsheet tool;
  none does scale-correct measurement.
- **A second data store** (Mongo/Influx/Postgres) beside the CSV — every surveyed project that added one has
  an open bug about the two disagreeing. CSV + sidecars stay the single source of truth.
- **A live dashboard in the MVP** — explicitly out of scope (forward plan D9 / non-goals); `area_cm2` is one
  number per frame, a static plot already shows it.
- Also avoided: Mycodo/Pigrow forks (GPL relicensing, hardware matrix we do not want) and TF-2.4-era stacks
  (divyansh2111 pins: uninstallable, 250 MB weights for 4 classes).
