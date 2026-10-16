# ADR 0002 — Scale reference: printed ArUco DICT_5X5_50, 45 mm side, per-frame calibration

- **Status**: Accepted
- **Date**: 2026-10-16
- **Deciders**: project owner (confirmed facts), with scout/ivan normalization notes

## Context

PlantVision measurements must be converted from pixels to millimeters, which requires an
in-frame scale reference of known physical size. The repo's references disagreed on what
that reference actually is:

- `configs/pipeline.yaml` and `docs/glossary.md` said **ArUco `DICT_4X4_50`, 50 mm**.
- `docs/HANDOFF-2026-10-15.md` (D9) said **`DICT_5X5_50`, id 0**, physical size
  "measured at calibration" — i.e. unspecified.
- Earlier planning texts also implied the dict could be treated as a fixed px/mm constant.

On 2026-10-16 the project owner confirmed the live setup decodes the printed marker as
**`DICT_5X5_50`** and measured its printed physical side as **45 mm**.

Constraints that shaped the decision:

- The scale conversion must be trustable in every frame, not only when the mount or
  distance happens to match the calibration session.
- The camera-to-marker distance is not guaranteed fixed; the phone may be remounted,
  moved, or refocused over the growth cycle.
- Detection must be OpenCV-native (`cv2.aruco`) and forgiving about marker id
  (`DICT_5X5_50` is a dictionary, not a single id).

## Decision

1. **Reference object.** The scale reference is the printed ArUco marker from dictionary
   **`DICT_5X5_50`** with a physical (printed) side of **45 mm**. This is the single
   source of truth: `configs/pipeline.yaml` (scale_reference block), and the user-facing
   docs now agree on it.
2. **Calibration is per-frame.** The px/mm factor is **recomputed from the detected
   marker in each frame** (marker side in pixels ÷ 45 mm) and is **never a fixed
   constant**. Evidence that this is required, not optional: two frames from
   2026-10-16 of the same 45 mm marker gave marker sides of **~203 px (~4.51 px/mm)**
   and **~241 px (~5.36 px/mm)**.
3. **Id-agnostic detection.** Detection runs on the `DICT_5X5_50` dictionary and accepts
   any of its ids; the scale conversion uses the **detected corners** of whatever marker
   id is found. The id observed in the 2026-10-16 frames was **1** — recorded for
   traceability, not as an assumed constant.

## Consequences

- **A moving or remounted camera stays viable**: per-frame scale survives changes in
  distance, zoom, or resolution without any recalibration procedure.
- **Supersedes prior references**: ADR/handoff note **D9** ("`DICT_5X5_50`, id 0") is
  corrected (id is not fixed; observed id was 1), and every earlier `DICT_4X4_50` /
  50 mm mention in docs and configs is replaced. `docs/HANDOFF-2026-10-15.md` is left
  as-is as a dated historical snapshot; this ADR governs.
- **Frames without a detectable marker cannot be scaled to mm** — the pipeline must
  surface this per frame (pixel-space metrics only) rather than falling back to a stale
  constant.
- **The printed marker becomes calibration-critical equipment**: printing must be
  verified at 45 mm side length; printer scaling mistakes silently skew all mm outputs.

## Alternatives considered

1. **Fixed global px/mm constant.** Rejected: refuted by the 2026-10-16 evidence
   (4.51 vs 5.36 px/mm at different distances); would silently mis-scale frames.
2. **Checkerboard / ruler in frame for calibration only.** Rejected: requires a
   separate calibration session and machine-readable per-session constants; the printed
   ArUco marker gives scale in every frame with zero extra hardware.
3. **`DICT_4X4_50`, 50 mm marker.** Rejected: contradicts the confirmed physical setup;
   kept only as the prior (wrong) documented reference, now removed everywhere.

## References

- `configs/pipeline.yaml` — `scale_reference` block (`dict: DICT_5X5_50`,
  `marker_size_mm: 45`).
- `docs/HANDOFF-2026-10-15.md` — D9 (superseded by this ADR; id 0 assumption corrected).
- `docs/open-questions.md` — OQ4 (scale reference choice, now consistent with this ADR).
- `docs/decisions/0001-data-flow.md` — capture flow this calibration feeds into.
