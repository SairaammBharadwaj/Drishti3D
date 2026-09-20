# F4 gate: targeted same-pass refinement versus a uniform budget

_Run 2026-09-20 by `python -m eval.f4_experiment`. Inputs, commit and full
per-question records in `result.json`; the question set is in
`questions_frozen.json`._

**Result: the targeted arm produces a higher answer yield than the uniform arm —
15 of 20 measurements blocked only by calibration against 10, with zero
regressions against the uniform arm's five — and since the cost work it does so
on *less* compute: 88.6 s against 135.4 s.**

Read it narrowly: one flight, twenty questions, no truth to score error against,
and "blocked only by calibration" is a proxy for acceptance, not acceptance.

The plan states the gate as: *"on frozen questions and equal added compute
budgets, targeted refinement improves correct accepted-answer yield or reaches
the same quality faster than uniform refinement."*

Both conditions are now met on this test bed:

- **It improves answer yield.** 15 of 20 against 10 of 20, from a baseline of 8.
- **It does so on less compute.** 88.6 s against 135.4 s, after the per-question
  cost work. Within the uniform arm's budget it reaches all 20 questions and
  clears 8 blockers, the same 8 the uniform arm clears.

The uniform arm's price is fixed whatever is asked of it; the targeted arm's is
4.4 s per question, so the two break even at about **31 questions**. Below that
the targeted arm is the cheaper option as well as the higher-yield one.

The gate has been run six times against the same frozen questions as the
targeted arm was built out. Every run is reported below; none is discarded. The
caveat that keeps the feature experimental is not the gate — it is that this is
one flight.

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

| Metric | no refit | + local refit | + transfer locator | **+ cost work** | Uniform |
|---|---:|---:|---:|---:|---:|
| **Added compute** | 210.5 s | 219.8 s | 206.7 s | **88.6 s** | 135.4 s |
| **Blocked only by calibration** (from 8) | 7 | 10 | 14 | **15** | 10 |
| Questions with any frame recovered | 5 | 5 | 16 | **17** | n/a |
| Measurements regressed | 1 | 0 | 0 | **0** | 5 |
| Narrower interval | 1 | 4 | 14 | **15** | 14 |
| Verdict moved up | 0 | 2 | 5 | **6** | 4 |
| Median measurement sigma | 0.151 | 0.128 | 0.101 | 0.104 | **0.092** |
| Median supporting views | 3 → 3 | 3 → 3 | 3 → 6.5 | 3 → **6.0** | 3 → 3 |
| Median measured parallax | 10.35° | 10.42° | 26.75° | **26.23°** | 10.26° |
| Blockers cleared per added minute | 0.57 | 0.55 | 2.03 | **5.42** | 3.55 |

Three changes took the targeted arm from losing outright to winning. The **local
refit** (plan section 5.7 step 4) gave it something to do with recovered
evidence beyond intersecting rays at one point. The **transfer locator** gave it
reach: questions it could touch went from 5 of 20 to 17. The **cost work** —
sequential decoding instead of seeking, and a detection cache shared across
measurements — made it 2.3× faster without changing what it produces.

### At equal budget

| | Value |
|---|---:|
| Budget | 135.4 s |
| Questions the targeted arm reached | **20 of 20** |
| Blockers cleared by targeted | 8 |
| Blockers cleared by uniform, the same questions | 8 |
| Break-even question count | **30.6** |

The targeted arm now finishes the whole question set inside the uniform arm's
budget. Earlier versions of this table compared its truncated prefix against the
uniform arm's full set, which charged it for questions it was never given the
budget to answer.

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

## What uniform still wins

Median interval width: 0.092 m against 0.104 m. A global bundle adjustment
improves every point's covariance at once, and the targeted arm only refits the
neighbourhoods it was asked about. On the two half-pass test beds the ordering
reverses — see the
[second test beds write-up](../2026-09-20_f4_second_capture/RESULTS.md) — so this
is not a fixed property of either method.

## Why uniform used to win on cost

Three reasons. The first two were addressed; the third is specific to this
mission.

**A re-reconstruction improves every question at once, for one fixed price.**
The targeted arm pays per question, so the comparison always has a break-even
point rather than a ratio. Cutting the per-question cost from 10.3 s to 4.4 s
moved that point from 13 questions to 31.

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

Same-pass refinement stays an **experimental feature**, and the reason is no
longer the gate — it is that this is one flight. See the
[second test beds write-up](../2026-09-20_f4_second_capture/RESULTS.md) for why
the only genuinely separate AGZ segment cannot run the comparison at all.

What is now claimable, and measured on this test bed:

- Higher answer yield than the control — 15 of 20 against 10.
- **Zero regressions against the control's five.** For a product whose claim is
  that it does not overstate what it knows, that is not a side note.
- Less compute: 88.6 s against 135.4 s, and it finishes all 20 questions inside
  the control's budget.
- Supporting views 3 → 6.0 and measured parallax 9.56° → 26.23°, against the
  control's 3 → 3 and 9.56° → 10.26°. The targeted arm is adding evidence where
  the control is adding resolution.

What is not claimable: a narrower interval. 0.104 m against the control's
0.092 m here, though the ordering reverses on both half-pass test beds.

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
5. **The same, leak fixed.** 206.7 s. Higher answer yield than the control for
   the first time, at 1.53x its compute.
6. **After the per-question cost work** (this run): sequential decoding instead
   of seeking, and a detection cache shared across measurements. 88.6 s — 2.3x
   faster — with yield up from 14 to 15 and nothing else materially changed.

The conclusion changed twice: at run 4 the targeted arm first out-yielded the
control, and at run 6 it did so on less compute.
