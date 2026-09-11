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

## 2026-09-10 — Dense feed-forward + pose graph (Intelligence Edition stages 3–4)

New backbone: MASt3R pairwise geometry (sequential + skip pairs at offsets
1,2,4,8) assembled by a GPS-anchored pose graph (`pose_graph.py`) — the dense
model supplies *pairwise* constraints only; global assembly belongs to the
graph. Its own global alignment produced locally-clean but globally-broken
geometry here (robust Sim(3) accepted 12/62 cameras).

Same AGZ surveyed segment as the 2026-09-06 entry. Direct UTM error, no
alignment to truth:

| | 3D med | p90 | horiz | vert |
|---|---|---|---|---|
| Onboard GPS | 5.52 | 12.37 | 3.26 | 2.68 |
| COLMAP + priors (06 Sep) | 7.33 | ~20 | 6.91 | 1.44 |
| **Dense + PGO** | **6.02** | **9.77** | 4.29 | **1.10** |

The dense path beats the classical engine everywhere, beats GPS on the tail
(p90) and on height by 2.4x. Horizontal remains behind raw GPS (4.29 vs 3.26).

What mattered, in measured order:
1. **Undistort first.** Raw AGZ frames (k1 = −0.281) break the dense model:
   90.1 m median chained error distorted → 7.6 m undistorted. COLMAP models
   distortion internally; a feed-forward pointmap model does not.
2. **Pairwise, not global.** Skipping MASt3R's global alignment and assembling
   with the GPS-anchored graph: 33.5 → 6.0 m.
3. **Cycle-consistency noise estimation.** Skip edges vs composed sequential
   edges give a truth-free per-dataset noise figure (here 15% translation,
   2.1° rotation). Fixed guessed sigmas made PGO *worse than GPS* (22 m).
4. **Per-edge anisotropic sigmas.** Direction noise = rot_err × edge length;
   magnitude noise = rel_err × length. A constant clamp doubled horizontal
   error when 22 m skips met a 0.10 m perpendicular sigma.

Runtime: 62 frames → 233 edges in ~127 s on an RTX 5060 laptop (8 GB), PGO 5 s.
License: MASt3R checkpoint is CC-BY-NC-SA — engine is opt-in
(`allow_noncommercial=True`), per the SuperPoint precedent.

Reproduce: `python -m eval.agz_dense_eval <dir with agz_pick.npy>`.

## 2026-09-10 — CORRECTION: synthetic cloud accuracy was measuring truth sparsity

**The cloud-accuracy figures published in the 2026-09-04 table were wrong**, by
roughly an order of magnitude, in the pessimistic direction. They are superseded
by this section. See D-032 for the full investigation.

`cloud_acc_median` was nearest-neighbour distance from each reconstructed point
to `scene_points_enu` — a **3,750-point sample of a 60 x 60 x 9 m scene**. That
cloud's own nearest-neighbour self-spacing is **0.33 m median and 2.50 m at
p90**, so the metric could not resolve any error below its own sampling
density. A perfectly placed point landing between two truth samples scored
~1 m. 30 % of reported "errors" fell beneath the floor.

The synthetic scene is six planar rectangles and is exactly known, so
`synth.surface_distance` gives true point-to-surface distance. On identical
points: **sampled-NN 0.782 m median vs analytic 0.020 m** — a factor of 39,
and the two rank the same points at only rho = 0.20. They were not noisy
versions of each other.

### Corrected results

Commit `64fd2ad7ffdb`, **clean tree**, baseline variant, 4 regimes x 3 seeds.
Accuracy from `analytic_surface`; completeness still uses the sampled cloud,
which answers the opposite question ("is there a reconstructed point near each
truth point") and is sound for that.

| Regime | ok/n | Reg. | ATE med / worst | Cloud acc med / worst | Complete | Dim err |
|---|---|---|---|---|---|---|
| `oblique_pass` | 3/3 | 100 % | 0.069 / 0.132 m | **0.084 / 0.108 m** | 36.5 % | 2.50 % |
| `orbit` | 3/3 | 100 % | 0.056 / 0.074 m | **0.054 / 0.065 m** | 94.9 % | 2.29 % |
| `nadir_grid` | 3/3 | 100 % | 0.343 / 1.749 m | **0.022 / 0.115 m** | 68.1 % | 1.08 % |
| `low_parallax` | **1/3** | 3.3 % | — | — | — | 100 % |
| **pooled** | **10/12** | — | 0.075 / 1.749 m | **0.065 / 0.115 m** | 68.1 % / 35.5 % | — |

### What changed against the superseded table

| | published (sampled-NN) | corrected (analytic) | factor |
|---|---|---|---|
| `oblique_pass` | 0.809 m | 0.084 m | 9.6x |
| `orbit` | 0.675 m | 0.054 m | 12.5x |
| `nadir_grid` | 0.911 m | 0.022 m | 41x |

### `low_parallax` is now reported, and it fails

The earlier table covered three regimes. `low_parallax` — the deliberate
failure probe — was not among them, so "0 failed cells" described a matrix that
excluded the regime designed to fail. Included: **2 of 3 seeds produce no 3D
points at all**, and the third registers 3.3 % of frames. The honest pooled
figure is **2/12 failed**, not 0/9.

This is the contract working as intended ("failures are data"), and it is the
strongest evidence in the suite for the project's central claim that capture
geometry dominates outcome: identical code, 100 % registration on `orbit` and
total failure on `low_parallax`.

### Rule added

An error metric must be validated against its own resolution floor before any
claim rests on it. Compare the truth representation's internal spacing to the
errors being reported; if they are the same order, the metric is reporting
itself. `cloud_acc_source` is now recorded per cell so analytic and sampled
numbers are never silently compared.

## 2026-09-11 — CORRECTION: the height result does not survive a second segment

**The 2026-09-10 claim that the system measures height 2.4x more accurately
than the drone's GNSS is withdrawn.** It held on one segment and fails on
another. See D-038.

Validated on a second, non-overlapping segment of the same AGZ flight
(imgid 64531-70021, 62 frames, identical camera and processing):

| metric | segment 1 | segment 2 |
|---|---|---|
| ours — 3D / horiz / vert | 6.02 / 4.29 / 1.10 m | 6.37 / 5.94 / 2.63 m |
| GNSS — 3D / horiz / vert | 5.52 / 3.26 / 2.68 m | **1.91 / 1.33 / 1.36 m** |
| verdict, 3D | lose 1.1x | lose 3.3x |
| verdict, horizontal | lose 1.3x | lose 4.5x |
| verdict, vertical | **win 2.4x** | **lose 1.9x** |

**Our accuracy is the stable quantity** — 6.02 and 6.37 m 3D across the two.
The GNSS is what moved: 5.52 m on one segment, 1.91 m on the other. Segment 1
had unusually poor GNSS, and every "beats the GNSS" statement rested on it.

Segment 2 is not the harder case. It is **less** straight (7.2x elongation
against 14.8x) and has a smaller altitude range — conditions that favour
reconstruction, not hinder it.

### Position now supported

Absolute georeferencing is **~6 m 3D and does not beat consumer GNSS**. For
non-RTK photogrammetry anchored to a sensor whose error is 56-61 % constant
bias (D-036), that is expected rather than anomalous — but it is not what was
published.

What the measurements do still support, unchanged:

- **relative geometry**: metric scale to ~1 % (1.12 m median step against a
  surveyed 1.13 m), and a trajectory smoother than the GNSS it was anchored to
  (jerk/step 0.17 against 0.42)
- **100 % frame registration** on real single-pass video, both segments
- **measurement refusal** (FAR 2.0 %), **coverage classification** (97.8 %) and
  calibrated uncertainty — none of which depend on absolute position
- synthetic accuracy against analytic surfaces: 0.022–0.084 m by regime

### Rule extended

The contract already required median and worst case together, and more than
three seeds for regimes with spread. It now says so for real data explicitly:
**no real-data claim from a single capture segment.** One segment is one seed.
