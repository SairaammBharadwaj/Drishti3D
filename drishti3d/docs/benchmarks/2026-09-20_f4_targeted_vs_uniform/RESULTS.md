# F4 gate: targeted same-pass refinement versus a uniform budget

_Run 2026-09-20 by `python -m eval.f4_experiment`. Inputs, commit and full
per-question records in `result.json`; the question set is in
`questions_frozen.json`._

**Result: the hypothesis is not supported on this mission. Uniform refinement
beat targeted refinement on every metric, on less compute.**

The plan states the gate as: *"on frozen questions and equal added compute
budgets, targeted refinement improves correct accepted-answer yield or reaches
the same quality faster than uniform refinement. No improvement is an acceptable
experiment result and must be visible."* It did not, and this is that.

## Setup

| | Value |
|---|---|
| Mission | `agz_dense_pass` — 184 decoded frames, 233 m flown, 9.43 m eph GNSS |
| Engine | COLMAP (PyCOLMAP 4.2.0) |
| Baseline | `preset="balanced"` → 80 keyframes, 81.9 s SfM, 17,898 points |
| Uniform arm | `preset="quality"` → 160 keyframes, 217.3 s SfM, 52,005 points |
| Questions | 20 distance measurements, ±0.30 m, frozen before either arm ran |
| Targeted budget | 4 frames per question, ≤10 candidates decoded |

Questions were selected from the baseline as the ones refinement exists for:
both endpoints on established coverage, with observation lineage, and the weaker
endpoint under 15° of measured parallax. Easy questions would have let the
targeted arm look good by having nothing to do.

## Results

| Metric | Targeted | Uniform |
|---|---:|---:|
| **Added compute** | 210.5 s | **135.4 s** |
| Measurements with fewer blockers | 2 / 20 | **8 / 20** |
| Measurements regressed | **1 / 20** | 5 / 20 |
| Measurements with a narrower interval | 1 / 20 | **14 / 20** |
| Verdict moved up the ladder | 0 / 20 | **4 / 20** |
| Blocked only by calibration, after | 7 / 20 (from 8) | **10 / 20** (from 8) |
| Median measurement sigma | 0.151 m → 0.151 m | 0.151 m → **0.092 m** |
| Median measured parallax | 9.56° → 10.35° | 9.56° → 10.26° |
| **Blockers cleared per added minute** | 0.57 | **3.55** |

### At equal budget

The arms do not cost the same, so the targeted arm was truncated at the uniform
arm's spend:

| | Value |
|---|---:|
| Budget | 135.4 s |
| Questions the targeted arm reached | 12 of 20 |
| Targeted spend | 127.9 s |
| Blockers cleared by targeted, within budget | **1** |
| Blockers cleared by uniform, all 20 questions | **8** |

The uniform arm's spend buys one reconstruction that answers every question at
once. The targeted arm's buys attention for one question at a time, and it did
not finish the list.

### Where the targeted arm's time went

It recovered frames for only 5 of 20 questions (4, 2, 2, 1, 1 frames), and
changed no verdict upward. The other 15 spent 10–15 s each and recovered
nothing — overwhelmingly because the endpoint could not be matched into a
recovered frame, the failure mode already measured at roughly two thirds of
attempts.

| Dominant limitation | Baseline | Targeted | Uniform |
|---|---:|---:|---:|
| `interval_not_calibrated` (nothing else blocking) | 8 | 7 | **10** |
| `interval_exceeds_tolerance` | 7 | 9 | 6 |
| `insufficient_views` | 4 | 2 | 1 |
| `outside_established_coverage` | 0 | 0 | 3 |
| `view_geometry_unverified` | 1 | 0 | 0 |

## Why uniform wins here

Three reasons, and only the third is specific to this mission.

**A re-reconstruction runs full bundle adjustment.** Targeted refinement adds
rays and re-triangulates a single point in isolation; it cannot touch the poses
or the other points, and its recovered cameras deliberately carry inflated
uncertainty (`POSE_UNCERTAINTY_INFLATION`). A global solve improves every
point's covariance at once. The 39% drop in median sigma is that, not extra
views — median supporting views is 3 in both arms.

**More keyframes is also a denser cloud.** 52,005 points against 17,898, with a
mean track length of 4.93 against 3.91. Endpoints snap to better-observed
points, which helps every question rather than the one being asked about.

**This pass is uniformly under-sampled.** A continuous 233 m traverse selected
down to 80 of 184 frames is short of views nearly everywhere, so spreading the
budget hits something useful wherever it lands. Targeting would be expected to
pay off where *most* of the scene is adequately covered and a few measurements
are not — which this mission is not, and which no capture here tests.

## What this does not establish

- **One mission, one scene, 20 questions.** This is not a general result about
  targeted refinement, and the third reason above suggests the regime matters.
- **Not a comparison of accuracy against truth.** No reference dimensions exist
  for this site, so both arms are scored on measurement standing and interval
  width, not on error.
- **Uniform is not free of harm**: it regressed 5 measurements to the targeted
  arm's 1, three of them to `outside_established_coverage` — a denser cloud
  moves the coverage boundary as well as improving the geometry.
- **Neither arm produced an accepted measurement.** Calibration blocks all 20
  in both arms; that is unchanged and unaffected by either.
- **The targeted arm was not given a local bundle adjustment.** That was an
  explicit scope decision ([DEC-010](../../../DECISIONS.md)), and it is the most
  obvious thing that could change this result.

## Consequences

Same-pass refinement is demoted to an **experimental feature**, per the plan's
own stop/go rule: *"If same-pass refinement does not beat uniform processing,
retain it as an experimental feature and demonstrate only its observed benefits.
Do not claim the main hypothesis succeeded."*

Its observed benefits, which are real and stay claimable: it recovers frames for
roughly a quarter to a third of weak measurements, and when it does it raises
supporting views and measured parallax and clears `insufficient_views`. What it
does not do is beat spending the same compute on a denser reconstruction.

Recorded as [DEC-013](../../../DECISIONS.md).

## Reproducing

```bash
cd drishti3d
.venv/bin/python scripts/run_mission.py --mission agz_dense_pass \
    --max-frames 184 --engine colmap --preset balanced --tag colmap_unc
.venv/bin/python scripts/run_mission.py --mission agz_dense_pass \
    --max-frames 184 --engine colmap --preset quality --tag colmap_quality
.venv/bin/python -m eval.f4_experiment \
    --baseline colmap_unc --uniform colmap_quality --n-questions 20
```

`questions_frozen.json` is reused if present, so a re-run scores the same
questions. Delete it only to start a genuinely new experiment.

## Note on the re-run

This experiment was run twice. The first run reported 2 targeted regressions;
one was an artefact of `RefinementEngine.refine` building its before/after
evidence without endpoint provenances, so an endpoint that did not snap to
observation lineage read as unobserved — disagreeing with the verdict the same
measurement got everywhere else. That was fixed, provenances are now passed, and
the experiment re-ran against the same frozen questions. Targeted regressions
fell from 2 to 1. **No other figure changed, and the conclusion did not.**
