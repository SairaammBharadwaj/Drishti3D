# F4 gate: targeted same-pass refinement versus a uniform budget

_Run 2026-09-20 by `python -m eval.f4_experiment`. Inputs, commit and full
per-question records in `result.json`; the question set is in
`questions_frozen.json`._

**Result: the hypothesis is still not supported. The targeted arm now matches
the uniform arm's answer yield, but takes 1.6x the compute to get there.**

The plan states the gate as: *"on frozen questions and equal added compute
budgets, targeted refinement improves correct accepted-answer yield or reaches
the same quality faster than uniform refinement. No improvement is an acceptable
experiment result and must be visible."* Two things are asked for and the
targeted arm does neither: it does not improve yield (both arms finish with 10
of 20 measurements blocked only by calibration), and it does not reach that
yield faster (219.8 s against 135.4 s).

The gate has been run twice against the same frozen questions, before and after
giving the targeted arm the local bundle adjustment plan section 5.7 step 4
calls for. **The refit changed the result substantially and did not change the
verdict.** Both runs are reported below; neither is discarded.

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

| Metric | Targeted, no refit | **Targeted, local refit** | Uniform |
|---|---:|---:|---:|
| **Added compute** | 210.5 s | 219.8 s | **135.4 s** |
| **Blocked only by calibration, after** (from 8) | 7 / 20 | **10 / 20** | **10 / 20** |
| Measurements with fewer blockers | 2 / 20 | 2 / 20 | **8 / 20** |
| Measurements regressed | 1 / 20 | **0 / 20** | 5 / 20 |
| Measurements with a narrower interval | 1 / 20 | 4 / 20 | **14 / 20** |
| Verdict moved up the ladder | 0 / 20 | 2 / 20 | **4 / 20** |
| Median measurement sigma | 0.151 → 0.151 m | 0.151 → 0.128 m | 0.151 → **0.092 m** |
| Blockers cleared per added minute | 0.57 | 0.55 | **3.55** |

The local refit moved the targeted arm from losing outright to tying on the
metric closest to accepted-answer yield, with **no regressions at all** against
the uniform arm's five. It did not make it faster, and it did not close the gap
on interval width.

### What the refit changed

Only 5 of the 20 questions had any frame recovered, so those are the only ones
either targeted arm could affect. On those five:

| Question | Frames | Sigma before → after | Status |
|---|---:|---|---|
| q004 | 4 | 0.201 → **0.106 m** | `needs_refinement` → `estimated_only` |
| q015 | 1 | 0.181 → **0.128 m** | `needs_refinement` → `estimated_only` |
| q014 | 1 | 0.074 → **0.054 m** | unchanged (already calibration-only) |
| q013 | 2 | 0.095 → **0.086 m** | unchanged (already calibration-only) |
| q012 | 2 | 0.114 → 0.115 m | unchanged; the refit was rejected and this fell back to a standalone ray intersection |

q004 and q015 each cleared both `insufficient_views` and
`interval_exceeds_tolerance`. A representative refit: 21 cameras, 400 points,
3,377 observations, reprojection RMSE 1.31 → 0.77 px, boundary drift 0.054 m,
anchor scale 0.9993.

Four of five improved. **The limit is not the mechanism, it is reach**: the
targeted arm's ceiling on this mission is 5 of 20 questions, set by how often
the endpoint can be located in a recovered frame.

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

15 of 20 questions spent 10–15 s each and recovered nothing, overwhelmingly
because the endpoint could not be matched into a recovered frame — the failure
mode already measured at roughly two thirds of attempts. That is where the
compute went and why the per-minute rate stays at 0.55 against 3.55: most of the
budget buys candidate decodes that are then discarded.

| Dominant limitation | Baseline | Targeted | Uniform |
|---|---:|---:|---:|
| `interval_not_calibrated` (nothing else blocking) | 8 | 7 | **10** |
| `interval_exceeds_tolerance` | 7 | 9 | 6 |
| `insufficient_views` | 4 | 2 | 1 |
| `outside_established_coverage` | 0 | 0 | 3 |
| `view_geometry_unverified` | 1 | 0 | 0 |

## Why uniform wins here

Three reasons, and only the third is specific to this mission.

**A re-reconstruction improves every question at once.** This was originally
read as "the control runs bundle adjustment and the targeted arm does not", and
giving the targeted arm its own local refit tested that directly. It helped —
median sigma 0.151 → 0.128 where before it did not move at all — but the control
still reaches 0.092, because a global solve touches all 20 questions while the
targeted arm reaches 5.

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
- **Whether a better endpoint locator changes the verdict.** Reach, not the
  refit, is now the binding constraint: 5 of 20 questions touched. If matching
  succeeded on most attempts rather than a third, the targeted arm would act on
  15–20 questions instead of 5, and this comparison would have to be rerun.

## Consequences

Same-pass refinement stays an **experimental feature**, per the plan's own
stop/go rule: *"If same-pass refinement does not beat uniform processing, retain
it as an experimental feature and demonstrate only its observed benefits. Do not
claim the main hypothesis succeeded."*

Its observed benefits, which are real and stay claimable: on the measurements it
can reach it improved 4 of 5 intervals, cleared blockers on 2, regressed none,
and cut the worst measurement's sigma by 47%. It is also the conservative
option — 0 regressions against the uniform arm's 5, which matters for a product
whose claim is that it does not overstate what it knows.

What it does not do is match the throughput of spending the same compute on a
denser reconstruction.

Recorded as [DEC-013](../../../DECISIONS.md) and
[DEC-014](../../../DECISIONS.md).

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

## Runs

Three runs, all against the same `questions_frozen.json`. `result.json` holds
the latest.

1. **Targeted without a local refit.** Reported 2 targeted regressions, one of
   which was an artefact of `RefinementEngine.refine` building its before/after
   evidence without endpoint provenances, so an endpoint that did not snap to
   observation lineage read as unobserved.
2. **The same, provenances fixed.** Regressions fell from 2 to 1; no other
   figure changed. These are the "Targeted, no refit" numbers above.
3. **With the local refit** (this run). Two further corrections were needed to
   make it meaningful, both documented in
   [DEC-014](../../../DECISIONS.md): the refit's own sigma is combined with the
   neighbourhood's existing uncertainty, because alone it reported 0.006 m on a
   point the surrounding cloud knows to 0.036 m; and the refined endpoint's
   coverage is taken from the frames that measured it rather than from the grid,
   which was built before the point moved and was occluding it with its own
   stale position.

The conclusion has not changed across any of them.
