# Provenance (MIAPPE-lite)

Every sidecar and every time-series row carries the keys below. They are
**optional**: absent information is written as JSON `null` in the sidecar and
as an empty cell in the CSV. Nothing is required, inferred or defaulted to a
crop literal.

Vocabulary: field **names** follow [MIAPPE 1.2](https://github.com/MIAPPE/MIAPPE)
(doi:[10.1111/nph.16544](https://doi.org/10.1111/nph.16544)). Only the field
names are reused here; no MIAPPE prose or checklist text is copied.

| our key | MIAPPE concept | example |
|---|---|---|
| `experiment_id` | experiment / investigation | `basil-2026-10` |
| `biosource_id` | biological source (species/cultivar) | `basil-genovese` |
| `observation_unit_id` | observation unit (zone + slot) | `farm/zone-a/slot-1` |
| `treatment_id` | treatment / factor level | `led-blurple-18h` |
| `light_regime` | environmental variable: photoperiod/spectrum | `blurple-18/6` |
| `exposure_s` | measurement-device setting: exposure time | `0.02` |
| `white_balance` | measurement-device setting: white balance | `auto` |
| `gain_db` | measurement-device setting: gain | `null` |
| `settings_source` | provenance of the settings above | `exif` \| `app` \| `manual` \| `unavailable` |

## Rules

- `crop_id` remains the primary crop key (from the capture config); `biosource_id`
  is the MIAPPE-grained cultivar. If both exist and disagree, the sidecar keeps
  both and the importer warns once per batch — the import does not fail.
- A camera setting (`exposure_s`, `white_balance`, `gain_db`) must never appear
  without a real `settings_source`; a non-null setting with a missing or
  `unavailable` source raises `ValueError`.
- CSV `exposure_s` is formatted to 4 decimals and `gain_db` to 2; the other
  provenance fields are strings. See `plantvision.analytics.timeseries`.
- An explicit JSON `null` and an absent key both become an empty CSV cell. They
  are deliberately indistinguishable in the store; the sidecar keeps the
  distinction.

## Reserved, not yet captured

These fields are reserved for the capture app / manual entry and stay `null`
until a real source writes them:

- `experiment_id`, `biosource_id`, `observation_unit_id`, `treatment_id`,
  `light_regime` — populated only from an explicit capture-config value.
- `gain_db` — phone EXIF has no documented ISO → dB conversion, so it is never
  invented.
- `settings_source` — `exif` when at least one of exposure/white balance/ISO is
  present in the JPEG; `unavailable` otherwise.

## Why camera settings matter

Under BLURPLE a white-balance change shifts the global R/B ratio and can move
`area_cm2` with no change to the plant. A step change in area that coincides
with a camera-settings change is treated as a **camera event** until proven
otherwise. `scripts/audit_coverage.py` counts `settings_unknown` per zone so a
missing provenance source stays visible.
