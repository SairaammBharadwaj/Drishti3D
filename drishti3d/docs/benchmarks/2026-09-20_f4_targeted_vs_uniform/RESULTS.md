# F4 gate: targeted same-pass refinement versus a uniform budget

_Run 2026-09-20 by `python -m eval.f4_experiment`. Inputs, commit and full
per-question records in `result.json`; the question set is in
`questions_frozen.json`._

**Result: with the endpoint locator replaced, the targeted arm produces a
higher answer yield than the uniform arm — 14 of 20 measurements blocked only by
calibration against 10, with zero regressions against the uniform arm's five. It
does so on 1.53x the compute, and at matched budget the two are level.**

This is the first run in which targeted refinement has won anything. Read it
narrowly: it is one mission, twenty questions, and no truth to score error
against.

The plan states the gate as: *"on frozen questions and equal added compute
budgets, targeted refinement improves correct accepted-answer yield or reaches
the same quality faster than uniform refinement."*

Against that wording the answer is split, and the split is the result:

- **It improves answer yield.** 14 of 20 against 10 of 20, from a baseline of 8.
- **It does not do so at an equal budget.** 206.7 s against 135.4 s. Truncated
  to the uniform arm's exact spend it clears 4 blockers where the uniform arm
  clears 5 on the same twelve questions — level, within noise of this sample.

So the feature stays experimental, but for the first time it has a measured
advantage rather than only a measured cost. The uniform arm's price is fixed
whatever is asked of it; the targeted arm's is 10.3 s per question, so the two
break even at about **13 questions**. Below that the targeted arm is the cheaper
option as well as the higher-yield one; above it, a new reconstruction amortises
better.

The gate has been run four times against the same frozen questions, as the
targeted arm was built out. Every run is reported below; none is discarded.

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

| Metric | Targeted, no refit | Targeted, + local refit | **Targeted, + transfer locator** | Uniform |
|---|---:|---:|---:|---:|
| **Added compute** | 210.5 s | 219.8 s | 206.7 s | **135.4 s** |
| **Blocked only by calibration, after** (from 8) | 7 / 20 | 10 / 20 | **14 / 20** | 10 / 20 |
| Questions with any frame recovered | 5 / 20 | 5 / 20 | **16 / 20** | n/a |
| Measurements regressed | 1 / 20 | 0 / 20 | **0 / 20** | 5 / 20 |
| Measurements with a narrower interval | 1 / 20 | 4 / 20 | **14 / 20** | **14 / 20** |
| Verdict moved up the ladder | 0 / 20 | 2 / 20 | **5 / 20** | 4 / 20 |
| Median measurement sigma | 0.151 → 0.151 m | 0.151 → 0.128 m | 0.151 → 0.101 m | 0.151 → **0.092 m** |
| Median supporting views | 3 → 3 | 3 → 3 | 3 → **6.5** | 3 → 3 |
| Median measured parallax | 9.56° → 10.35° | 9.56° → 10.42° | 9.56° → **26.75°** | 9.56° → 10.26° |
| Blockers cleared per added minute | 0.57 | 0.55 | 2.03 | **3.55** |

Two changes moved the targeted arm from losing outright to winning on yield. The
**local refit** (plan section 5.7 step 4) gave it something to do with recovered
evidence beyond intersecting rays at one point. The **transfer locator** gave it
reach: questions it could touch at all went from 5 of 20 to 16.

### At equal budget

| | Value |
|---|---:|
| Budget | 135.4 s |
| Questions the targeted arm reached | 12 of 20 |
| Blockers cleared by targeted, those 12 | 4 |
| Blockers cleared by uniform, **the same 12** | 5 |
| Break-even question count | **13.1** |

Level, within noise of this sample. Comparing the targeted arm's twelve against
the uniform arm's twenty would charge it for questions it was never given the
budget to answer, and the earlier version of this table did exactly that.

### What the two changes did

The local refit is effective where it runs: a representative one is 21 cameras,
400 points, 3,377 observations, reprojection RMSE 1.31 → 0.77 px, boundary drift
0.054 m, anchor scale 0.9993. Before the locator changed, it only ran on 5 of 20
questions.

The transfer locator is why the rest became reachable. Measured on 75 candidates
drawn from 25 weak endpoints:

| Locator | Endpoint located | Refit accepted |
|---|---:|---:|
| Descriptor match against a measuring frame | 1.3% | 4% |
| Descriptors chained through intermediate frames | 10.7% | 20% |
| **Transfer through dense correspondences** | **40.0%** | **36%** |

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

## Why the locator mattered so much

Every earlier attempt tried to **re-identify** the endpoint's own keypoint in a
recovered frame, and that cannot work here for two measured reasons:

- The reconstruction's observations sit at *its* detector's keypoints. Matching
  COLMAP's stored observations against a fresh OpenCV SIFT detection, the median
  separation is **8.9 px**, and only 212 of 1,852 observations have a redetected
  keypoint within 3 px.
- Across the viewpoint change worth recovering, descriptors of the same surface
  are not distinctive. At the final match the best-to-second-best ratio has a
  median of **0.93** — no clearer than chance — with the best descriptor
  distance at 388 against the ~123 seen between adjacent frames.

Computing descriptors directly at the stored pixel was tried and rejected:
upright SIFT at an arbitrary pixel separates true correspondences from random
ones by only 1.6–1.9x, against roughly 4x for descriptors at detected keypoints.
An arbitrary pixel is often on texture that is not distinctive.

**Transfer sidesteps identification entirely.** Two frames are matched densely —
LightGlue returns 700–1,600 correspondences where SIFT returns 90–190 — the
correspondences near the endpoint's known pixel fit a local affine map, and the
pixel goes through it. No single keypoint has to be found twice. The result is
still an image measurement, built from where the detector independently found
features in both frames, and it is accepted only if it agrees to 25 px with the
pose-projected prediction, which shares none of its inputs.

## Why uniform still wins on cost

Three reasons, and only the third is specific to this mission.

**A re-reconstruction improves every question at once, for one fixed price.**
The targeted arm pays per question. That is the whole of the remaining cost
difference, and it is why the two break even at 13 questions rather than at some
ratio of efficiency.

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
- **That the yield advantage would survive on another capture.** It rests on
  16 of 20 questions being reachable, which depends on the locator succeeding at
  40% of candidates on *this* imagery.
- **That "blocked only by calibration" means accepted.** It is the closest proxy
  available while no calibration profile exists, and it is not the same thing.

## Consequences

Same-pass refinement stays an **experimental feature**. The plan's stop/go rule
is conditioned on not beating uniform processing, and this result is split: a
higher yield, at a higher price, level at matched budget. One mission is not
enough to retire the caveat.

What is now claimable, and measured:

- Higher answer yield than the control — 14 of 20 against 10.
- **Zero regressions against the control's five.** For a product whose claim is
  that it does not overstate what it knows, that is not a side note.
- Supporting views 3 → 6.5 and measured parallax 9.56° → 26.75°, against the
  control's 3 → 3 and 9.56° → 10.26°. The targeted arm is adding evidence where
  the control is adding resolution.
- Cheaper than the control for sessions asking fewer than about 13 questions.

What is not claimable: a better interval (0.101 m against 0.092 m), or better
throughput (2.03 blockers cleared per added minute against 3.55).

Recorded as [DEC-013](../../../DECISIONS.md),
[DEC-014](../../../DECISIONS.md) and [DEC-015](../../../DECISIONS.md).

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

Five runs, all against the same `questions_frozen.json`. `result.json` holds the
latest.

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

4. **With the transfer locator.** The first attempt reported 4,665 s of added
   compute. That was one question taking 74 minutes against a median of 12
   seconds: `RefinementEngine` loaded its own LightGlue model per instance, an
   engine is created per measurement, and twenty of them filled the 8 GB card.
   The matcher is now shared at module scope.
5. **The same, leak fixed** (this run). 206.7 s, and the numbers above.

The conclusion changed at run 4: for the first time the targeted arm produces a
higher answer yield than the control. It is still not cheaper, and at matched
budget the two are level.
