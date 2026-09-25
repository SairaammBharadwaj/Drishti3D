# Intelligence Edition V3.1 plan — review against the code, and future work

Reviewed 2026-09-25 against the repository at the time, and against same-flight
LiDAR results on two MARS-LVIG flights (TESTS_AND_RESULTS 2026-09-25;
DEC-042, DEC-043). The plan is an 88-page target architecture. This note
records what already exists, what was done in response, and what remains,
ordered by measured value where a measurement exists.

## Already in place

| Plan section | What exists |
|---|---|
| 3, 39–47 epistemic honesty, typed measurements | `questions.py`: typed questions, verdicts, 15 refusal reason codes; `measure.py`: point, distance, height, area |
| 50 empirical calibration before "meets requirement" | `CalibrationProfile` gate; nothing is "meets requirement" without 20 calibrated samples (DEC-003, DEC-006) |
| 4 geometry vs presentation authority | inferred fill kept as a separate provenance layer outside the measured cloud (DEC-040) |
| 33–35 evidence-aware coverage, evidence per region | `coverage.py` observation space; `evidence.py` per-point views and parallax |
| 16 dynamic objects | `masking.py` optical-flow residual (not a semantic delete) |
| 56–58 recapture | `capture.py` accuracy-driven refly advice |
| 17–21 backend abstraction | `ai_adapter.py`; VGGT, MASt3R, Depth Anything V2 optional |
| 13 scene coherence | COLMAP registration ratio, reprojection error in every report |

## Done in response to the review (DEC-043)

| Plan section | Change | Evidence |
|---|---|---|
| 67 single-pass benchmark rule | first-visit single-pass test on both flights | single pass is more accurate than multi-pass on the same ground |
| 8 sensor synchronisation | position-based camera-RTK offset; uncertainty stored | alignment 1.53 -> 0.88 m, 1.33 -> 0.69 m |
| 29 rolling shutter as metadata | `camera.json` `"shutter": "global"` | removes a false warning on a global-shutter camera |
| 35, 48 do not trust one score | HIGH class also requires sigma_major <= 0.12 m | vertical p90 1.30 -> 1.10 m, cross-validated across flights |
| 75 licence manifest | `drishti3d/MODEL_LICENSE_MANIFEST.md` | NC-SA datasets now in use |

## Future work, in priority order

1. ~~RTK as pose priors inside bundle adjustment~~ **Done differently
   (DEC-044).** Priors did not help; the warp was a lens-distortion bowl.
   Refining residual distortion after mapping plus a vertical lever arm took
   held-out vertical RMSE to 0.38–0.42 m (single pass) and 0.48–0.53 m
   (multi-pass), and horizontal offset from ~0.54 m to 0.07–0.28 m.
2. ~~A horizontal accuracy metric~~ **Done for global placement (DEC-044):**
   `score_horizontal_offset.py`, injection-validated. Still open: per-point
   horizontal error (needs identifiable features or surveyed targets).
3. **A second site and camera (now the top item).** Both flights are one
   island, one day, one camera. The 0.12 m sigma threshold, the 0.29 m
   antenna height and every number here need an independent site. Cheapest
   next test: HKisland01 (8.8 of 18.8 GB already on disk, L1 extracted) is
   held out from every calibrated value.
3a. **Measure the antenna-to-camera lever arm** on the aircraft instead of
   calibrating it against LiDAR, and apply the horizontal part with heading.
4. **Mission modes and a capability matrix** (plan 14, 15, 37). Turn existing
   signals (scale source, RTK fixed fraction, time-offset uncertainty,
   registration ratio, tile-bias spread when a reference exists) into
   FULL_METRIC / RELATIVE_METRIC / VISUAL_ONLY and per-operation permissions.
5. **Evidence ledger** (plan 52–55). Every number in the UI from one
   append-only record with git commit, parameters and source frames.
6. **Adversarial tests on real data** (plan 69–70). MARS-LVIG makes these
   cheap: inject telemetry offsets (now recoverable), altitude bias, wrong
   focal length, duplicated frames; measure the mission false-accept rate.
7. **Uncertainty calibration** (plan 50, 72). Predicted sigma ranks errors well
   but is ~5x optimistic (interval coverage 21%). Fit a scale on one flight and
   test coverage on another; the gate stays shut until 20 samples exist.
8. **Learned backends** (plan 18–20, 64). MapAnything (Apache variant) and
   Depth Anything 3, benchmarked against COLMAP on the same clips with the
   validated scorers. Needs a GPU machine or Colab; this 15 GB laptop cannot
   run full-resolution dense fusion (DEC-042).
9. **Measurement-grade TSDF / surfel geometry** (plan 31–32). Only after 1–2,
   since fusion quality is bounded by the warp.

## Not recommended from the plan (for now)

- Adding architecture layers before the items above are measured; the plan
  itself says so (section 0).
- Treating processing-time targets as official thresholds; wall/video here is
  set by keyframe count (1.08x on 10 min DJI video, 3.3x on a 49 s clip).
