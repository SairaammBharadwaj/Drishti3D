# Native-video accuracy against same-flight LiDAR (MARS-LVIG)

One place for the investigation of 2026-09-24 to 26: what reference was used
and why, how every metric was validated before it was trusted, what was found,
what was fixed, and what remains. The detailed tables live in
`TESTS_AND_RESULTS.md` (entries dated 2026-09-25 and 26) and the decisions in
`DECISIONS.md` DEC-042, DEC-043 and DEC-044.

## 1. Headline

Two independent flights (MARS-LVIG HKisland02 and HKisland03), native 10 Hz
video, RTK, scored against a DJI L1 LiDAR carried on the same drone in the
same flight. Settings that fit a 15 GB laptop (80 keyframes, 1600 px, dense at
1300 px). The antenna-height offset for each flight is calibrated on the
**other** flight.

| | single pass (SIH's scenario) | multi-pass (whole survey) |
|---|---:|---:|
| vertical RMSE | **0.38–0.42 m** | 0.48–0.53 m |
| vertical median abs error | **0.18–0.23 m** | 0.24–0.25 m |
| vertical p90 | **0.57–0.63 m** | 0.76–0.86 m |
| vertical p99 | 1.30–1.40 m | 1.50–1.65 m |
| horizontal placement error | 0.08–0.28 m | 0.07–0.13 m |

At the start of the investigation the same flights scored 0.83–0.92 m
vertical RMSE (multi-pass), p90 1.30–1.42 m, with a ~0.54 m horizontal offset.

**What this is not.** One site, one day, one camera, one run per setting.
Vertical and horizontal *placement* are measured; per-point horizontal error is
not. Nothing here is a "meets requirement" verdict: the uncertainty model is
still ~5x optimistic, and the calibration gate (DEC-003, DEC-006) stays shut.

## 2. Why this reference

- **Same flight.** The L1 LiDAR (10 cm H / 5 cm V after DJI Terra) records
  simultaneously with the camera, so no construction, vegetation or water
  change between reference and video. A 2021 LiDAR under 2025 Austin video was
  rejected for exactly that reason.
- **Independent instrument.** Not photogrammetry, unlike UAVScenes' map (also
  rejected).
- **Checked, not assumed.** The HKisland02 and HKisland03 L1 surveys are
  separate flights over the same ground. All 19.8 M points of one against the
  other: RMSE 0.077 m, vertical bias -1.3 mm. The reference is ~5-10x finer
  than the errors measured.
- **Same flight, verified per mission.** The LiDAR's `gps_time` window lies
  inside each bag, and the kept video span matches it (282.8 s vs 282.6 s).
- **Truth isolated.** `run_mission.py` gives the pipeline only video,
  telemetry and settings; the truth lives in `datasets/truth/` and only the
  scorers read it.

Pairing trap: `HKisland_GNSS03` and `HKisland03` fly the same route but are
different flights a year apart. `HKisland.7z` holds L1 for HKisland01/02/03
only.

## 3. Metrics, and how each was validated

Every metric is re-checked by **injecting a known error** into a real cloud
and confirming it is recovered. That rule exists because a scorer here has
been blind before (DEC-037).

| metric | script | injection check | status |
|---|---|---|---|
| cloud-to-cloud (nearest point) | `score_against_lidar.py` | +0.30 m up read as +0.05; +1 m east as +0.025 | **surface noise only**; its "systematic offset" is not a measurement |
| vertical, flat LiDAR cells | `score_vertical_dsm.py` | +0.30 / +1.00 / -0.10 m recovered within 2 mm, every run | **validated** |
| horizontal placement, sloped surfaces | `score_horizontal_offset.py` | +0.5 / +1.0 m east and north recovered exactly, every run | **validated** (global offset only) |
| raw COLMAP cloud, RTK-aligned | `score_colmap_fused.py` | keyframes recovered by pixel matching (ratio >= 80) matched `keyframes.json` exactly | used to score runs the pipeline could not finish |

## 4. What was found and fixed, in order

1. **RTK arrives ~0.5 s late** (DEC-042, DEC-043). On constant-speed surveys
   the speed-profile estimator found only part of it.
   `refine_time_offset_by_alignment` estimates it from position agreement and
   stores its uncertainty. Camera-to-RTK fit: 1.53 -> 0.88 m, 1.33 -> 0.69 m.
2. **High confidence meant nothing for dense points** (DEC-043). It depended on
   view count alone. HIGH now also requires `sigma_major <= 0.12 m`, a threshold
   chosen on HKisland02 and tested on HKisland03: vertical p90 1.30 -> 1.10 m,
   81% of points kept.
3. **The benchmark was multi-pass** (V3.1 plan section 67). 43–54% of each
   flight revisits ground. Reconstructing only the first-visit stretch was
   *more* accurate on the same ground (0.56–0.59 vs 0.85–0.94 m).
4. **~40% of vertical error was large-scale bending** (DEC-043). Per-40 m-tile
   biases spanned -1.2..+2.1 m.
5. **The bending was the lens, not georeferencing** (DEC-044). RTK pose priors
   inside bundle adjustment made it worse. The error changed with distance from
   the flight line in the same wave on both flights (-0.22 / +0.20 / +0.30 /
   -0.27 m at 0-20 / 20-40 / 40-60 / 60-80 m): residual radial distortion.
   `refine_residual_distortion` refines k1, k2, p1, p2 after mapping with focal
   and principal point fixed. Both flights refine to k1 ~ -0.002, k2 ~ +0.004.
   The ~0.5 m horizontal offset disappeared with it.
6. **The antenna sits ~0.3 m above the camera** (DEC-044). With the bowl gone a
   constant +0.19..+0.36 m vertical offset remained. It is now
   `gnss_antenna_above_camera_m` in `camera.json` (0.29 m for MARS-LVIG,
   calibrated; accuracy claims use the other flight's value).
7. Smaller: a declared global shutter disables the rolling-shutter check; the
   fusion cache (`use_cache`) is actually enabled; frames live in a disk-backed
   store (671 full-resolution frames in 580 MB of RAM); heavy jobs run capped
   (`scripts/run_capped.sh`), so a runaway job cannot take the editor down.

## 5. Reproduce

```bash
cd drishti3d
# data: scripts/fetch_mars_lvig.sh (Drive quota permitting), or copy the bags
#       into ~/Downloads; L1 clouds come from HKisland.7z
.venv/bin/python scripts/build_mars_lvig_mission.py --bag <HKisland03.bag> \
    --calib HKisland --name mars_hkisland03_sp \
    --utc-start 2022-11-29T06:17:44.3+00:00 --utc-end 2022-11-29T06:18:33.7+00:00 \
    --truth-las <HKisland03/lidars/terra_las/cloud*.las>
scripts/run_capped.sh -- .venv/bin/python scripts/run_mission.py --set mars_lvig \
    --mission mars_hkisland03_sp --engine colmap --preset balanced --max-frames 20 \
    --sfm-threads 6 --mvs-cache-gb 1 --mvs-max-image-size 1300 --proc-width 1600 \
    --densify mvs --tag check
.venv/bin/python scripts/score_vertical_dsm.py --run mars_hkisland03_sp__check \
    --truth ../datasets/truth/mars_hkisland03_sp/reference_lidar.las --epsg 32650
.venv/bin/python scripts/score_horizontal_offset.py --run mars_hkisland03_sp__check \
    --truth ../datasets/truth/mars_hkisland03_sp/reference_lidar.las --epsg 32650
```

Windows used: HKisland03 LiDAR 06:17:44.3–06:21:05.3 UTC, first-visit
06:17:44.3–06:18:33.7. HKisland02 LiDAR 06:08:26.1–06:13:08.7, first-visit
06:08:26.0–06:09:29.2. HKisland01 LiDAR 06:32:54.6–06:42:13.6 (held out).

## 6. Open

In priority order (`docs/V3_1_REVIEW_AND_FUTURE_WORK.md`):

1. **A held-out flight and a second site.** HKisland01 has been held out of
   every calibration (L1 extracted; bag partly downloaded).
2. Measure the antenna-to-camera lever arm on the aircraft instead of
   calibrating it, and apply its horizontal part with heading.
3. Per-point horizontal error (needs identifiable features or surveyed
   targets).
4. Uncertainty calibration: predicted sigma ranks error well but is ~5x
   optimistic.
5. Mission modes and a capability matrix, an evidence ledger, adversarial
   tests on real data, and learned backends on a GPU machine.
6. Processing time is set by keyframe count: ~3 min per 20–25 keyframes of
   5 MP video and ~12–13 min per 80 on this laptop (wall/video 1.1x on 10 min
   DJI video, 3.4x on a 49 s clip).
