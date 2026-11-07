# Capture protocol for a grower (one page)

This page is the whole protocol. If a step is skipped, write it down; an
unrecorded change is a measurement change.

## The ten steps

1. **Mount once.** Put the phone or camera on a rigid bracket and write the
   lens-to-canopy distance on the bracket. Photograph before and after
   tightening; the two frames must be pixel-aligned.
2. **Put the marker in every frame.** Use the 45 mm `DICT_5X5_50` marker, flat
   and matte, never behind a leaf. If a leaf can cover it, move the marker, not
   the plant.
3. **Never move the plant or the pot.** Rotation changes the silhouette. Record
   any rotation date.
4. **Log the light.** Write `blurple` or `white`, the switch date and time, and
   the photoperiod. One line per change.
5. **Lock the camera.** Manual exposure, manual white balance, fixed ISO. Auto
   is a measurement change you did not record.
6. **Capture every five minutes inside the light window** (06:00–22:00). Skip
   dark frames.
7. **Weigh two plants from each tray twice a week** (or install load cells).
   Record fresh mass and the number of plants in the tray.
8. **Keep a control.** Same crop, same tray, no treatment; otherwise you cannot
   separate the plant from the condition.
9. **Clean the lens with a microfibre cloth on a fixed schedule.** Do not use
   your sleeve; log each cleaning.
10. **Archive, do not delete.** A bad frame is evidence of a bad condition.

## Failure modes already observed, and the countermeasure

| Failure | Evidence | Effect | Countermeasure (deterministic) |
|---|---|---|---|
| Marker occlusion | farm-03: 39 % of frames | `area_cm2` missing, scale-coverage alert | `scale_ok` plus the `scale-coverage` rule; show a badge on cm² charts; prefer px area for trend |
| Framing change | phone-01 | endpoint growth misleading | framing check card; split the series at the change date; record provenance |
| Light regime change | farm-04: 457 blurple → 322 white | the ExG threshold is invalid; 28 px vs 480,098 px | condition key + validity record + split chart + `validity-violation` |
| Auto-exposure drift | `settings_source=exif`, blanks | colour indices and brightness shift without a plant change | `camera-settings-change` rule; require manual settings |
| Blurple saturation | farm-04 blurple | red dominates; the green threshold fails | store `red_dominance`; use a separate method per light |
| Sparse cadence | phone-01: 69 frames total | no daily median | freshness rule; never compute RGR under two days |
| n = 1 | every panel | no between-plant variance | treat plant-level claims as case studies; add plants before inference |

## Before quoting a number

1. Find the panel's condition key and validity verdict in Method › validity.
2. If the cell is not `✓ valid`, do not quote the number.
3. If the cell is `unproven`, quote it only as a hypothesis and say so.
4. A missing record is `unproven`, never `valid`.
