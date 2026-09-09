# The truth harness

A single favourable run is not evidence. This document describes the benchmark
that every accuracy claim in this repository must come from, and the rules that
make its numbers mean something.

## The contract

1. **No accuracy claim may be published unless `eval/benchmark.py` generated it.**
   Not the README, not a slide, not a demo caption.
2. **Median *and* worst case are reported together.** A system intended for field
   use is described by its tail. Reporting only the best or the mean hides
   exactly the behaviour an operator will hit.
3. **Failures are data.** A cell that crashes is recorded as a failed cell and
   counted in the failure rate. It is never silently dropped.
4. **One variable at a time.** A variant is a *recorded parameter set*
   (`eval/variants.py`), never an edited source tree, so "baseline vs +BA" runs
   the same code on the same inputs with one dictionary changed.
5. **Alignment residual is never product accuracy.** The GNSS fit residual
   measures consistency between reconstructed camera centres and the GNSS track
   that was used to fit them. Accuracy is measured against withheld truth.

## What it runs

```
variants  x  capture regimes  x  seeds
```

Each cell renders (or reuses) a synthetic scene with exactly known geometry,
runs the full pipeline, and scores the result against ground truth using the
gauge-free protocol in `eval/metrics.py` (Sim(3) alignment for trajectory,
trimmed rigid ICP plus GT-region cropping for the cloud).

### Capture regimes

The flight geometry, not the algorithm, is usually the dominant driver of
whether a scene is reconstructable. Benchmarking one favourable pass is how a
system ends up with a headline number it cannot repeat in the field.

| Regime | Geometry | What it probes |
|---|---|---|
| `oblique_pass` | Single pass flying east at ~46 m, descending, building framed | The product's canonical demo capture |
| `nadir_grid` | 3-strip lawn-mower at constant 45 m, camera straight down | The hard case: constant altitude means GNSS barely constrains the vertical axis, and near-parallel view directions give parallax only from the baseline |
| `orbit` | Circular orbit at 26 m radius, looking inward | Strongest single-pass parallax — the capture a pilot *should* fly for measurable geometry |
| `low_parallax` | High (78 m), fast, nearly straight | The failure-mode probe: short baseline relative to depth, so depth is weakly observed |

Seeds change the scene's procedural textures *and* the GNSS noise draw, so
repeated trials are genuinely independent rather than cosmetic re-rolls of the
same pixels.

**How many seeds.** Three is enough for `orbit` and `oblique_pass`, whose
cell-to-cell spread is small. It is **not** enough for `nadir_grid`: measured over
six seeds its ATE ranges 0.170-2.405 m under identical code, a factor of 14, while
its registration and dimensional error stay stable. A single `nadir_grid` cell is
not evidence of anything, and a 3-seed comparison there can easily invent an
improvement that is pure spread. Use >= 6 seeds for it, and prefer dimensional
error over ATE as the headline for planar/nadir captures — the camera trajectory
is weakly constrained by that geometry even when the reconstructed surface is
good.

### Metrics per cell

Registration fraction, ATE (RMSE / median / max, after Sim(3)), metric scale
error, cloud accuracy (median / RMSE) and completeness at a distance threshold,
dimensional error against known reference distances, median reprojection error,
mean triangulation angle, point count, GNSS alignment residual, wall-clock
runtime, and peak RSS.

## Provenance

Every run records what produced it: git commit and **dirty-tree flag**,
interpreter and platform, library versions, a full `pip freeze` (`env.lock.txt`),
and the SHA-256 of every generated input. A dirty tree is reported in the
Markdown output, because numbers from a modified working tree cannot be
re-derived from the commit alone.

Cells run in **isolated subprocesses**. That is not incidental: it means one
segfault or OOM cannot destroy the whole matrix, and `ru_maxrss` measures that
cell's peak memory rather than the high-water mark of every case run before it.

## Running it

```bash
# full default matrix (4 regimes x 3 seeds)
python -m eval.benchmark --variants baseline,ba --out bench_out

# a controlled A/B on one regime
python -m eval.benchmark --variants baseline,ba --regimes orbit --seeds 0,1,2

# fast smoke test of the harness itself
python -m eval.benchmark --quick --regimes orbit --seeds 0 --out /tmp/smoke

# heteroscedastic GNSS: degrade 30% of fixes to test uncertainty weighting
python -m eval.benchmark --variants baseline,ba --gps-outlier-frac 0.3
```

Outputs: `benchmark.json` (every cell plus provenance), `BENCHMARK.md`
(median/worst comparison tables), `env.lock.txt`.

Scenes are cached with `--scene-cache <dir>` and shared across variants within a
run. Sharing is deliberate: an A/B that also re-rolls its inputs measures input
noise instead of the change under test.

## Adding a variant

Add an entry to `eval/variants.py` mapping a name to `PipelineParams` overrides.
**Never change what an existing variant name means** — published numbers are
keyed by it.

## Known gaps

- **No real-data cell yet.** The bundled Bellus imagery is an unfetched LFS
  pointer set (see [ENVIRONMENT.md](ENVIRONMENT.md)); the harness already has an
  ODM adapter (`eval/cases.py`), so a Bellus row is one `git lfs pull` away.
- **Synthetic renders are noise-free apart from GNSS.** No motion blur, rolling
  shutter, exposure variation or lens distortion is simulated yet, so these
  numbers are an *upper bound* on field performance, not a prediction of it.
- **Fewer than 30 checkpoints.** Per ASPRS, a formal positional-accuracy
  assessment needs ≥30 independent checkpoints. These runs are explicitly
  reduced-checkpoint validation, not standards compliance.

## 2026-09-06 — Engine × data 2×2 (COLMAP vs ours)

Motivation: COLMAP on real single-pass footage produced mean track length 6.25
against our 2.37 on Bellus. Two variables moved at once (engine *and* data), so
the number alone attributes nothing. This matrix separates them.

Intrinsics held fixed for the gym_pass column: COLMAP's own self-calibrated
f = 1194.7 px @1920 (scaled to 995.6 @1600), so the comparison is not decided by
who guessed focal length better. Both engines saw 1600 px imagery.

### Registration

| Engine | Bellus (122 photo grid, GPS) | gym_pass (64-frame single pass, no GPS) |
|---|---|---|
| Ours (SIFT) | — | 57/64 · 89.1 % |
| Ours (LightGlue) | 105/122 · 86.1 % | 55/64 · 85.9 % |
| **COLMAP** | 108/122 · 88.5 % | **64/64 · 100 %** |

### Mean track length — the metric the georegistration failure traced to

| Engine | Bellus | gym_pass |
|---|---|---|
| Ours (SIFT) | — | 4.37 |
| Ours (LightGlue) | 2.37 | 4.82 |
| **COLMAP** | 4.00 | **6.25** |

### Decomposition

Both effects are real and roughly additive:

- **Data** (photo grid → continuous single pass), engine held fixed:
  COLMAP 4.00 → 6.25 (**+2.25**); ours 2.37 → 4.82 (**+2.45**)
- **Engine** (ours → COLMAP), data held fixed:
  on Bellus 2.37 → 4.00 (**+1.63**); on gym_pass 4.82 → 6.25 (**+1.43**)

So the earlier 2.37-vs-6.25 gap is **roughly 60 % capture topology, 40 % engine**.
Neither alone explains it, and the widely-repeated assumption that our matcher was
the whole problem is wrong.

Registration tells a different story from track length: on the photo grid the two
engines are within 3 images of each other (105/108 of 122). COLMAP's advantage
appears **only** on single-pass video, where it registers every frame and we lose
7–9. That is the regime the problem statement actually targets.

### Caveats

- Our gym_pass runs called `sfm.reconstruct` directly, without the pipeline's
  bundle adjustment; the Bellus 2.37 figure came from a full pipeline run with
  `bundle_adjust=True`. BA refines geometry but does not create observations, so
  track length is comparable; registration counts are unaffected (BA runs after).
- Our median reprojection error on gym_pass/SIFT is 0.218 px against COLMAP's
  0.43 px. This is **not** a win — fewer and shorter tracks are easier to fit.
  Read it alongside the track column, not on its own.
- LightGlue's median triangulation angle is 11.51° vs SIFT's 6.05°: it does find
  wider-baseline matches, but converted 2 fewer frames into registrations here.
- No GPS on gym_pass, so this matrix says nothing about georegistration accuracy.

## 2026-09-06 — First end-to-end georegistration against surveyed truth (AGZ)

Dataset: **Zurich Urban MAV (AGZ, ETH Zurich RPG)**. 2 km continuous MAV flight
with per-frame GPS, surveyed 6-DoF ground truth, and factory calibration
(fx 893.39, fy 898.33, cx 951.13, cy 555.13, k1 -0.281, k2 0.116).

The full archive is 29.8 GB. The server honours Range requests, so
`eval/httpzip.py` drives `zipfile` over HTTP and pulls individual members:
184 frames (67 MB) extracted without downloading the archive.

Segment: imgid 57211-62701 — a **200 m straight single pass**, 1.13 m frame
spacing, 14.8x straightness, every frame landing on a ground-truth pose.
Onboard GPS on these frames is off by a median of **5.39 m** (max 27.44 m).

### Results

| Run | Frames | Reg | Track | ATE median (Sim3-aligned) |
|---|---|---|---|---|
| Self-calibrating, 62 frames | 62 | 62/62 | 3.30 | 20.18 m |
| + surveyed calibration fixed | 62 | 62/62 | 2.85 | 9.88 m |
| + dense sampling (1.13 m) | 184 | 184/184 | 3.79 | 12.96 m |
| + GPS position priors | 184 | 184/184 | 3.88 | 10.54 m |
| + centred priors | 184 | 184/184 | 3.81 | 10.37 m |

### Direct georeferenced error (no alignment — the metric that matters)

| | median | p90 | max |
|---|---|---|---|
| Ours | 7.33 m | 59.73 m | 84.26 m |
| Onboard GPS | 5.39 m | 12.57 m | 27.44 m |
| **Ours, vertical only** | **1.44 m** | | |
| GPS, vertical only | 2.72 m | | |
| Ours, horizontal | 6.91 m | | |
| GPS, horizontal | 3.19 m | | |

**We beat GPS on height (1.44 m vs 2.72 m) and lose on plan (6.91 m vs 3.19 m).**
Height is the quantity the problem statement actually asks for, so this is the
first real evidence the approach measures what it is supposed to. The horizontal
result is not yet usable, and the p90 of 59.73 m says a minority of frames are
badly placed.

### What was learned

1. **Fixing intrinsics halved the error (20.18 -> 9.88 m).** COLMAP's AUTO camera
   mode gives every image its own camera and self-calibrates each. On the
   well-conditioned gym_pass capture those agreed to within 1 %; on a nearly
   straight trajectory the focal/depth ambiguity is barely observable and
   estimates diverged from 1062 to 2044 px against a surveyed 893.4.
2. **Denser frames improved structure but not accuracy.** 62 -> 184 frames took
   track length 2.85 -> 3.79 and points 14 k -> 124 k, yet ATE went 9.88 -> 12.96 m.
   More observations do not fix a badly conditioned trajectory.
3. **The error is a bow, not drift.** corr(frame index, error) = -0.11. Per-segment
   medians run 26.7, 6.4, 9.0, 18.5, 16.0, 9.4, 3.2, 24.9 m — high at both ends,
   low in the middle. With no loop closure, small rotation errors on a straight
   pass integrate into a low-frequency bend.
4. **Local geometry is good.** Our trajectory is smooth — jerk/step 0.17 against
   ground truth 0.12 and GPS 0.42 — and the scale is right: 1.12 m median step
   against a surveyed 1.13 m. The failure is global shape, not local structure.
5. **Triangulation is not the bottleneck.** Median triangulation angle 10.65 deg
   over 4000 points (p10 3.09). Consecutive baseline/depth is only 0.024, but
   multi-frame tracks recover adequate parallax.
6. **Prior centring did not help** (10.54 -> 10.37 m, within noise). Numerical
   conditioning from raw UTM magnitudes was not the limiter.

### Bugs found and fixed in `colmap_adapter.py`

- `intrinsics` was accepted and **silently ignored**. Now honoured and held fixed.
- Camera mode defaulted to per-image self-calibration; now shares one camera.
- Position priors were inserted alongside COLMAP's own EXIF-derived priors,
  tripping a uniqueness constraint. Existing rows are now updated in place, which
  also lets us state the covariance instead of leaving it NaN.
- Prior centring transformed only the in-memory reconstruction; the model written
  to disk stayed at the centred origin, reading as a 5.2e6 m georeferencing error.
  The corrected model is now written back.

### Next

The bow is the thing to attack: sequential + loop-closure matching rather than
exhaustive, tighter prior sigma, or rig/IMU orientation constraints. Raising
horizontal accuracy below the 3.19 m GPS baseline is the bar to clear.
