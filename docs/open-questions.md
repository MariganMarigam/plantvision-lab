# PlantVision — Open Questions / Uncertainty Journal

Two parts: the decision table (what was asked, what was answered) and the open uncertainties
list (what is still unknown). The uncertainties list is **append-only**: entries are resolved
by adding a `→ resolved:` line, never by deleting them.

## Resolutions table

Defaults from `output/research/2026-10-13-phone-capture-minimal-stack.md`; user confirmations
2026-10-13 (evidence E3/E5 in `output/state/plantvision.md`).

| # | Question | Default (rationale) | Status |
|---|----------|---------------------|--------|
| OQ1 | Phone model / Android version | **Any Android 8.0+ running IP Webcam**, powered 24/7 on the same Wi-Fi SSID. Pull model does not depend on Android background scheduling — exact version is non-critical. User confirmed the phone runs mostly 24/7 (lights off 6–8 h/day per D8). | Resolved 2026-10-13 (user) |
| OQ2 | Pull vs push / doze exemption | **Pull** (IP Webcam), scheduler on Ubuntu (D2). No doze exemption required; disable battery optimisation for IP Webcam and keep it charging. | Resolved 2026-10-13 (decided D2); phone can be dedicated |
| OQ3 | Which single leafy crop | **Lettuce** (green-leaf/butterhead): broad leaves → strong projected-area signal; well covered by CVPPP/PlantVillage-style datasets. User confirmed lettuce. | Resolved 2026-10-13 (user) |
| OQ4 | Fixed phone + scale reference | **Fixed mount + printed ArUco marker** (`DICT_4X4_50`, 50 mm) beside the plant as in-frame scale reference (OpenCV-native). User confirmed mount + printed marker. | Resolved 2026-10-13 (user) |
| OQ5 | Disk budget / retention | **Retention policy doc now**; keep all originals for the MVP; ≤1280×720 JPEG (≤300 KB ⇒ ≤16 GB/yr); weekly free-space check. User: disk path unspecified → `data/` stays under the repo root, gitignored. | Resolved 2026-10-13 (user) |

## Uncertainties (open)

1. **Can growth be estimated reliably from one camera under changing light?**
   (the core scientific risk of the project; revisit at Stage 05 with the first
   projected-area series — `reflection.md:348`).
2. Can the phone hold a stable IP on the home network long-term, or should the server
   fall back to mDNS name discovery (`<hostname>.local`)?
3. Does IP Webcam stay alive for weeks on the phone with battery optimisation disabled,
   or does Android eventually kill it?
4. Will the fixed mount hold framing stability (very small drift) over weeks — enough for
   projected-area comparability (Stage 02 acceptance)?
5. Does the printed ArUco marker stay machine-readable at the working camera distance and
   lighting (glare, shadows), given `DICT_4X4_50` at 50 mm?

## How an entry resolves

Append `→ resolved YYYY-MM-DD: <answer + evidence pointer>` under the entry. Never delete
entries; the history of what was unknown is part of the record.
