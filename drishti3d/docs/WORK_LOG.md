# Work log

A chronological record of what was changed, why, and what it measurably did.
Entries are append-only. Decisions live in
[`ENGINEERING_DECISION_LOG.md`](ENGINEERING_DECISION_LOG.md); this file records
the work itself, including the things that did not go as expected.

The plan being executed is
[`REPOSITORY_AUDIT_AND_IMPROVEMENT_ROADMAP.md`](REPOSITORY_AUDIT_AND_IMPROVEMENT_ROADMAP.md),
in its stated phase order.

---

## 2026-09-02 — Phase 1: truth harness

### 1.1 Built a reproducible environment (roadmap phase 1 gate)

The audit could not execute the test suite, so it could not treat any committed
number as verified. Built a Python 3.12 virtualenv with the full stack (3.13/3.14
have no OpenCV wheel).

**Result: the 32 pre-existing tests passed unmodified.** The audit's finding
"tests could not be executed" was an environment gap, not broken code. That is a
meaningful correction — the existing suite *is* evidence, it just had nowhere to
run. Documented in [`ENVIRONMENT.md`](ENVIRONMENT.md).

### 1.2 Correction: the real imagery is not in this checkout

The audit recorded "real aerial imagery exists locally, but no committed
real-data evaluation report was found", implying the data was available and only
the report was missing. Checked directly:

```
tracked binary files: 130   unfetched LFS pointers: 128
```

`git-lfs` is not installed, and 128 of 130 tracked binaries are ~130-byte pointer
stubs — **all 123 Bellus images**, the synthetic fixture video, and every
committed `cloud.npz` / `mesh.glb` / `.ply`. Only the two `point_cloud.las` files
are real.

So roadmap phase 1's "run the bundled Bellus imagery first" cannot start here.
Had this gone unchecked, the harness would have produced a scorecard over 123
unreadable files. Recorded as decision D-005; the fix is `git lfs pull`, and the
ODM adapter to consume it already exists in `eval/cases.py`.

**Consequence for everything below: all measurements are synthetic.** They are an
upper bound on field performance, not a prediction of it.

### 1.3 Capture regimes in the synthetic generator

`synth.generate` rendered exactly one trajectory. A benchmark over one flight
geometry measures the algorithm under the single condition it was tuned for, so
added four regimes (`drishti_recon.synth.REGIMES`): `oblique_pass` (the existing
demo pass), `nadir_grid` (constant-altitude lawn-mower, camera down),
`orbit` (strongest single-pass parallax), `low_parallax` (high, fast, straight —
the failure-mode probe).

Also made the seed drive the procedural textures, not just the GNSS noise draw,
so repeated trials are independent rather than the same pixels with different
noise; and moved GNSS perturbation from degrees to **metres in the local ENU
frame**, so a horizontal sigma means the same thing at every latitude. Added
`gps_outlier_frac`, which degrades a fraction of fixes *and honestly reports the
larger sigma* in the `gps_accuracy` column — the input an uncertainty-weighted
alignment is supposed to exploit.

**Bug found and fixed while doing this:** `_look_at` was degenerate for
straight-down views. It builds the camera basis from `cross(forward, world_up)`,
which is the zero vector when forward is `(0,0,-1)`, so every nadir pose came out
`NaN`. Nothing caught it because no nadir capture had ever been rendered. Fixed
by falling back to a north reference when the cross product degenerates; oblique
poses are unchanged.

### 1.4 The benchmark harness

Added `eval/benchmark.py` (driver), `eval/_bench_worker.py` (one isolated cell)
and `eval/variants.py` (the ablation registry). Design rules and the
reproducibility contract are in [`BENCHMARK.md`](BENCHMARK.md). The three choices
worth calling out:

- **Cells run in subprocesses.** One crash cannot destroy the matrix, and
  `ru_maxrss` measures that cell's peak memory instead of the high-water mark of
  every case run before it.
- **A variant is a recorded parameter dictionary**, never an edited source tree,
  so an A/B is genuinely controlled.
- **Scenes are rendered once and shared across variants.** An A/B that also
  re-rolls its inputs measures input noise instead of the change under test.

### 1.5 Baseline: the single self-test was a best case

The repository's reference number came from one synthetic self-test:

```
solved 38/38   ATE_rmse=0.169 m   scale_err=0.0036   completeness=28.2%
```

Running the *same code* across four capture regimes:

| Regime | Registration | ATE RMSE | Scale error |
|---|---|---|---|
| `oblique_pass` seed 0 | 100% | **11.26 m** | **71.3%** |
| `oblique_pass` seed 1 | 100% | **13.11 m** | 5.6% |
| `oblique_pass` seed 2 | — | **total failure** ("reconstruction produced no 3D points") | — |
| `nadir_grid` seeds 0–2 | **66.7%** | 0.72–2.31 m | 0.4–0.8% |
| `orbit` seed 0 | 100% | 1.23 m | 0.01% |

This is the roadmap's point about tail behaviour, demonstrated on the actual
code: the same pipeline that reports 0.169 m on its demo capture produces 11–13 m
ATE, a 71% scale error, 33% of frames unregistered, and one complete failure once
the flight geometry changes. No single-run headline should be quoted again.

**Process note:** the first baseline matrix was discarded. I edited the pipeline
while it was running, and because each cell launches a fresh subprocess, later
cells picked up bundle adjustment while earlier ones had not — an invalid
comparison. Re-run cleanly with the code frozen. The re-run reproduced
`oblique_pass/seed0` exactly (ATE 11.258 m, scale error 0.7131), which also
confirms the harness is deterministic.

---

## 2026-09-02 — Phase 2: geometric core

### 2.1 Bundle adjustment (roadmap P0)

The audit's largest single accuracy finding: the OpenCV engine estimates poses
incrementally and retriangulates, but never minimises all reprojection residuals
together, so early error is baked in and accumulates as drift.

Added `reconstruction/drishti_recon/bundle.py`: sparse Levenberg–Marquardt over
all camera poses and points, with optional focal-length and Brown–Conrady
distortion refinement, via `scipy.optimize.least_squares` with an explicit
Jacobian sparsity pattern.

Wired into `sfm.reconstruct` at three points — an early solve on the seed pair,
capped interim solves every `ba_every` registered cameras to stop drift
accumulating mid-sequence, and one full global solve at the end. Exposed as
`PipelineParams.bundle_adjust` / `ba_every` / `refine_focal` /
`refine_distortion`, so the benchmark can toggle it by name.

**Every solve is accepted only if it lowers reprojection RMSE**, and rejected
solves hand back the input untouched. Bundle adjustment therefore cannot make the
reconstruction worse than the incremental estimate it was given.

#### Two real bugs found by testing against known geometry

Both would have shipped as "bundle adjustment doesn't help much".

1. **Single-view points corrupted the solve.** A point observed by one camera is
   unobservable: its depth slides freely along the viewing ray at zero
   reprojection cost. Left in the problem, the optimiser drives the residual down
   while the geometry drifts — in the first test, reprojection improved while
   point error got *worse* (3.3 m → 7.6 m). Such points are now held fixed and
   returned unchanged, and there is a regression test for it.

2. **The solver defaults were starving the optimisation.** `max_nfev=60` with
   `ftol=1e-6` terminated far from the optimum, which reads as "BA doesn't work"
   rather than the misconfiguration it was. Measured the alternatives on a
   controlled 8-camera problem with a 0.5 px noise floor:

   | Loss | `x_scale` | Result | Cost |
   |---|---|---|---|
   | huber | `jac` | 0.625 px | 185 evaluations |
   | huber | `1.0` | **stalls at 11.7 px** | hit the cap |
   | soft_l1 | `jac` | 0.625 px | **36 evaluations** |
   | linear | `jac` | 0.625 px | 5 evaluations (not robust to outliers) |

   Defaults are now `soft_l1`, `x_scale="jac"`, `max_nfev=200`, `ftol=1e-8`.
   `x_scale="jac"` is not optional — without Jacobian-based scaling the same
   problem stalls at 11.7 px instead of converging to 0.62 px.

   A third trap, avoided: my own first test aligned the gauge using camera
   centres from a *perfectly straight* camera track. Umeyama's rotation about
   that line is undetermined, so every point appeared to be off by a constant
   62 m. That was the test's gauge being degenerate, not the solver. The
   committed tests fit the gauge on the points and fly the cameras along an arc.

#### Verification on known geometry

`tests/test_bundle.py` — 8 tests, all passing. They check *geometry recovery*,
not the training residual, because a bundle adjuster that lowers reprojection
error while moving away from truth has failed:

| Test | Result |
|---|---|
| Recovers known geometry | reprojection 16.4 px → 0.63 px (0.5 px noise floor); camera-centre RMSE 0.1008 m → **0.0048 m** (21× better) |
| No-op on an already-optimal input | does not degrade it |
| Never returns a worse reconstruction | rejected solve returns the input unchanged |
| Single-view points held fixed | unobservable point returned exactly as supplied |
| Recovers a 10%-wrong focal length | error more than halved |
| Recovers radial distortion | `k1` recovered to within 0.03 of −0.12 |
| Vectorised rotation matches `cv2.Rodrigues` | agrees to 1e-9 |
| Zero rotation vector | no NaN from the 0/0 |

Full suite: **40/40 passing** (32 pre-existing + 8 new).

#### Measured effect: the full baseline-vs-BA matrix

4 capture regimes x 3 seeds x 2 variants = 24 cells, ~44 min.
Archived: [`benchmarks/2026-09-02_baseline_vs_ba/`](benchmarks/2026-09-02_baseline_vs_ba/).
Reported median / worst, pooled over all regimes and seeds:

| Metric | `baseline` | `ba` |
|---|---|---|
| Failure rate | 25% (3/12) | **25% (3/12) — unchanged** |
| ATE RMSE (m) | 1.697 / 13.114 | **0.011** / 7.182 |
| Metric scale error | 0.0065 / **0.7131** | **0.0023 / 0.0198** |
| Dimensional error (%) | 5.53 / 100.0 | **2.31** / 121.6 |
| Cloud accuracy, median (m) | 0.993 / 86.71 | **0.879** / 86.71 |
| Completeness @0.5 m | 0.456 / 0.000 | **0.508** / 0.000 |
| Median reprojection (px) | 0.572 | **0.128** |
| Runtime (s, median) | **63.7** | 219.6 |

Per regime, on the cells that reconstruct at all:

| Regime | `baseline` ATE | `ba` ATE | `baseline` dim err | `ba` dim err |
|---|---|---|---|---|
| `orbit` | 0.55–1.61 m | **0.003–0.004 m** | 1.0–5.1% | 1.4–2.3% |
| `nadir_grid` | 0.72–2.31 m | **0.018–0.021 m** | 4.7–6.0% | **1.5–3.4%** |
| `oblique_pass` | 11.3 / 13.1 m | **0.002** / 7.18 m | 46–51% | **4.3** / 121.6% |
| `low_parallax` | 2 failures + 1 unusable | identical | — | — |

Three conclusions, including the one that is not good news:

**1. Where reconstruction succeeds, BA is decisive.** Median ATE improves 154x
(1.697 m → 0.011 m) and the catastrophic 71.3% worst-case scale error becomes
2.0%. On `oblique_pass/seed0` every independent metric moved together —
dimensional error 51.4% → 4.3%, completeness 2.8% → 40.7%, cloud accuracy
2.85 m → 0.77 m, median reprojection 1.30 px → 0.07 px — so this is a real
geometric improvement, not one metric being gamed.

**2. BA does not touch the failure rate.** Still 3/12. All three failures die
with "reconstruction produced no 3D points", i.e. *before* bundle adjustment ever
runs. Optimising geometry cannot rescue a reconstruction that never produced any.
The failure rate is owned by initialisation and registration recovery — roadmap
P1 — and that is now clearly the highest-value next item.

**3. One cell got worse, and it is the informative one.**
`ba/oblique_pass/seed1`: ATE improved 13.1 → 7.2 m and scale error 5.6% → 2.0%,
but the cloud degraded badly — completeness 12.4% → 0.3%, dimensional error
46.5% → **121.6%**, cloud accuracy 2.05 → 3.81 m.

Diagnosis from the recorded BA history: the solve never converged. Its final
global residual stalled at 1.77 px, against 0.39 px on the healthy cell, and the
recovered metric scale moved 1.735 → 2.915 while the mean triangulation angle
*fell* 6.24° → 3.93°. Bundle adjustment is a local optimiser: from a bad
initialisation it found a configuration with lower reprojection error but wrong
geometry.

This matters beyond the one cell, because **the accept-only-if-reprojection-drops
guard cannot catch it** — reprojection is exactly what improved. That is the
roadmap's own warning ("do not accept only a lower training reprojection
residual") reproducing itself in our implementation. The guard still prevents BA
from returning a *numerically* worse fit, but it is not a geometric safety net.
The real fix is upstream: a better initialiser and a registration retry policy,
which is the same P1 item that owns the failure rate.

### 2.2 Analytic Jacobian

BA cost 3.4x the baseline runtime (63.7 s → 219.6 s median), because SciPy was
estimating by finite differences a derivative that is known in closed form.

Replaced with an analytic sparse Jacobian (exponential-coordinate rotation
derivative, Gallego & Yezzi compact form, with the correct small-angle branch).
Distortion refinement is not covered and transparently falls back to finite
differences, reporting which was used in `BAResult.stats["jacobian"]` rather than
risking a wrong gradient silently.

Measured on a 30-camera / 3000-point / 81k-observation problem:

| Jacobian | Time | Optimum reached |
|---|---|---|
| finite difference | 23.36 s | 0.689 px |
| **analytic** | **8.07 s (2.9x faster)** | 0.689 px (identical) |

A hand-derived Jacobian is a classic place for a silent sign or transpose error —
the solver still converges, just differently, so nothing looks broken. It is
therefore checked entry-by-entry against SciPy's own numerical derivative
(`test_analytic_jacobian_matches_finite_differences`), with and without focal
refinement, plus a test that both paths land on the same optimum.

---

## 2026-09-02 — Phase 3: sensor correctness

### 3.1 GNSS accuracy now actually affects the solution (roadmap P1)

`robust_sim3` accepted a `weights` argument and never read it, so every reported
GNSS accuracy was decorative. Fixed, and made meaningful in three ways:

- **Inlier scoring is normalised.** A correspondence is judged by Mahalanobis
  distance — residual over that fix's own sigma — instead of one absolute metric
  threshold. A 3 m residual on a 10 m fix is consistent; the same residual on an
  RTK fix is not, and a single threshold in metres cannot express that.
- **The refit is inverse-variance weighted** (`1/sigma^2`, not `1/sigma`: a fix
  twice as noisy should count a quarter as much).
- **Horizontal and vertical are separated.** GNSS altitude is characteristically
  worse than horizontal position; weighting them equally is a standard way to
  tilt a reconstruction. A closed-form Umeyama can only take an isotropic weight,
  so an anisotropic nonlinear refinement follows it, and is discarded if it does
  not improve the fit.

The result now also reports **conditioning**: a straight flight line cannot
constrain rotation about that line, and a constant-altitude pass constrains the
vertical weakly. Both are ordinary drone captures, so they are detected and
reported (`degenerate`, `degeneracy`) rather than yielding a confidently wrong
transform. Scale uncertainty is derived from the trajectory's own extent, because
a short track pins scale far less well than a long one.

Verified by the roadmap's stated acceptance experiment: under heteroscedastic
GNSS (30% of fixes degraded to 8 m), weighted alignment beats unweighted on
*clean held-out* positions. Nine tests, including a regression test that stated
accuracy changes the fitted scale at all.

One test expectation of mine was wrong and got corrected rather than the code:
over-tight sigmas do **not** inflate the normalised RMSE, because it is computed
over inliers and an over-tight sigma simply rejects everything that does not
already fit. The honest symptom of over-claimed precision is the consensus set
collapsing, which is what the test now asserts.

### 3.2 Levelling can no longer silently break georeferencing (roadmap P0)

The pipeline fitted cloud and cameras to GNSS, then rotated both about the cloud
centroid to level the ground plane — after the fit, without composing the
rotation into the saved transform and without recomputing the residual. Exported
coordinates could therefore not reproduce the number the report published.

Now the levelling rotation is composed into the alignment transform (the levelled
map is itself a similarity), the GNSS residual is **recomputed against the
composed transform**, and the correction is **rejected outright if it would
materially degrade the fit** — with the reason surfaced as a warning. Whatever is
applied is persisted in the manifest under `transforms`, alongside an explicit
`vertical_datum` field recording that GNSS altitude here is WGS84 ellipsoidal,
not orthometric.

### 3.3 Real frame timestamps (roadmap P0)

Frame times were `frame_index / fps`, which is only correct for constant-frame-
rate video. Consumer drones drop frames and record variable frame rate, and every
dropped frame shifts all later timestamps — silently pairing frames with the
wrong GNSS sample, a bias no downstream stage can detect.

Now reads each frame's container presentation timestamp, and **validates it**
before trusting it: rejected if all-zero (no timing in the container), not
strictly increasing, or spanning a duration inconsistent with the frame count and
nominal rate. On rejection it falls back to the nominal clock and says so.
Silently trusting a broken PTS track would be worse than the assumption it
replaces. The clock actually used is recorded in the manifest.

**Suite after phase 3: 55/55 passing** (32 pre-existing + 23 new).

### 3.4 Correcting my own regression: gate on the total residual, not GNSS sigma

The benchmark caught a regression I introduced in 3.1. Scoring inliers at 3 sigma
of the *GNSS* uncertainty (~1 m) replaced a fixed 3 m threshold, and metric scale
error got **worse** on well-reconstructed captures while improving dramatically on
the pathological one.

The cause was a modelling error on my part: the residual between a reconstructed
camera centre and its GNSS fix contains **reconstruction error as well as GNSS
noise**, and on a good reconstruction the reconstruction error dominates. Gating
on the GNSS sigma alone assumes the reconstruction is exact, so it discarded good
correspondences and shrank the consensus set until scale became noisy.

Fix: estimate the reconstruction-error scale robustly (normalised MAD) from a
first permissive fit, then gate and weight on
`sigma_total = sqrt(sigma_gnss^2 + sigma_recon^2)`. This keeps the relative
down-weighting of poor fixes — the actual point of weighting — and correctly
*reduces* how much GNSS quality matters when it is not the limiting term. The
result now also reports `error_budget`, so a reader can see whether better GNSS
would help this capture at all.

Baseline metric scale error, same cells, three versions:

| Cell | v1 unweighted | v2 GNSS-sigma gate | v3 total-sigma gate |
|---|---|---|---|
| `oblique_pass/s0` | 0.7131 | 0.0922 | **0.0217** |
| `oblique_pass/s1` | 0.0555 | 0.0412 | **0.0009** |
| `nadir_grid/s0` | 0.0047 | 0.0254 | **0.0044** |
| `orbit/s1` | 0.0003 | 0.0017 | **0.0003** |
| **median** | 0.0065 | 0.0295 | **0.0053** |
| **worst** | 0.7131 | 0.0922 | **0.0217** |

Weighted alignment now beats unweighted on **both** median and worst case (33x
better worst case), where the intermediate version beat it on neither.

---

## 2026-09-02 — Phase 2 (continued): initialisation and registration recovery

This is roadmap P1, and the benchmark had shown it owned everything BA could not
fix: the 25% hard-failure rate and the worst tail.

### 4.1 What was wrong

Three separate defects, each individually sufficient to wreck a reconstruction:

1. **The seed pair was chosen by inlier count.** Inlier count is *maximised by the
   smallest baseline* — adjacent, nearly identical frames match almost perfectly
   and then triangulate at a near-zero angle. The rule reliably picked the worst
   possible pair.
2. **The pair graph contained no wide baselines at all.** Only `(i,i+1)`,
   `(i,i+2)`, and GPS *nearest* neighbours. Over a 44 m pass at ~45 m depth every
   such pair subtends about 1 degree. No downstream optimisation can recover a
   baseline that was never observed.
3. **Registration was a single pass in index order**, so a frame that failed
   before its neighbours existed was never retried.

### 4.2 What changed

- **Seed pairs are scored on the geometry they can deliver**: median
  triangulation angle, cheirality, inlier spread, and rejection of pairs a
  homography explains just as well (rotation-only or planar, where the baseline is
  unrecoverable).
- **Pairs are proposed at geometrically spaced strides** (1, 2, 4, 8, 16...),
  adding wide-baseline candidates at O(n log n) rather than the O(n^2) of
  exhaustive matching. GPS proximity now uses a *distance band* targeting a useful
  baseline instead of nearest-neighbour — the spatially nearest frames are
  precisely the ones with the least parallax.
- **Next-best-view registration** replaces the index-order pass: repeatedly
  register the unsolved frame with the most 2D-3D support, and park rather than
  discard frames that cannot yet be solved, retrying as the model grows.

### 4.3 A bug of my own, caught by tracing rather than assuming

After the first two changes the failing cells *still* failed. The trace showed
`_select_init_pair` returning `None` on a scene where pair (10,42) scored 30
degrees of parallax with 1300 inliers.

The cause was in the code I had just written: it pre-ranked candidates by inlier
count and truncated to the top 40 — which is exactly the set of adjacent,
zero-parallax pairs the scorer exists to reject. Every good pair sat at the bottom
of that ordering and was never scored. Candidates are now bucketed by temporal
separation with the best few taken from each bucket, so every baseline scale is
actually evaluated.

Worth recording because the first two fixes were correct and still produced no
improvement; only tracing the actual selection, instead of re-reasoning about the
design, found it.

### 4.4 Measured effect — without bundle adjustment

`oblique_pass`, `baseline` variant (BA disabled), so this isolates initialisation
and registration:

| Cell | ATE before | ATE after |
|---|---|---|
| `oblique_pass/s0` | 11.258 m | **0.069 m** |
| `oblique_pass/s1` | 13.114 m | **0.011 m** |
| `oblique_pass/s2` | **total failure** | **0.020 m** (100% registered) |

The regime that produced 11-13 m errors and a hard failure now reconstructs to a
few centimetres *with no bundle adjustment at all*. The earlier conclusion stands
and sharpens: BA was recovering what a bad initialisation had destroyed, and
fixing the initialisation is the cheaper and more reliable cure.

### 4.5 `low_parallax` still fails, and that is the right answer

Two of three `low_parallax` cells still produce no reconstruction. Tracing shows
this is correct, not a defect: at 78 m altitude with a 20 m pass over
near-planar terrain, a homography explains the correspondences *better* than the
essential matrix (H/E inlier ratio 1.002) and cheirality is 0.571 — the pose
decomposition is meaningless. The capture genuinely does not contain the geometry.

Failing loudly is a strict improvement on the previous behaviour, which
"succeeded" on one such cell with 3.3% of frames registered, an 86 m cloud error
and 100% dimensional error. A refusal is a usable answer; a confident wrong number
is not.

**Correction, from the fuller run below:** I first wrote here that the same
planar degeneracy still limited nadir mapping to 66.7% registration. That is no
longer true — the multi-scale pair graph and next-best-view scheduler took
`nadir_grid` to **100% registration on all three seeds**. The planar-degeneracy
concern remains real in principle (and `low_parallax` still demonstrates it), but
it is not currently limiting the nadir regime, and it should not be quoted as
though it were.

Homography/essential model selection with homography-based initialisation (as
ORB-SLAM does) remains the right remedy *if* a genuinely planar capture has to be
reconstructed rather than refused. It is not implemented, and on present evidence
it is no longer the most valuable next item.

### 4.6 Partial re-run of the full matrix (stopped early, deliberately)

Archived at [`benchmarks/2026-09-02_p1_partial/`](benchmarks/2026-09-02_p1_partial/).
Stopped after 8 of 24 cells at a natural break; the `baseline` arm is complete for
three regimes, and it is the arm that isolates the initialisation work because BA
is disabled in it.

| Cell | ATE before P1 | ATE after P1 | Registration before → after |
|---|---|---|---|
| `oblique_pass/s0` | 11.258 m | **0.069 m** | 100% → 100% |
| `oblique_pass/s1` | 13.114 m | **0.011 m** | 100% → 100% |
| `oblique_pass/s2` | **failed** | **0.020 m** | — → **100%** |
| `nadir_grid/s0` | 2.312 m | **0.178 m** | 66.7% → **100%** |
| `nadir_grid/s1` | 1.789 m | **0.317 m** | 66.7% → **100%** |
| `nadir_grid/s2` | 0.716 m | **0.679 m** | 66.7% → **100%** |
| `orbit/s0` | 1.234 m | **0.041 m** | 100% → 100% |
| `orbit/s1` | 0.546 m | **0.055 m** | 100% → 100% |

Every completed cell improved, in every regime — including the two regimes the
change was not designed around. Registration reached 100% wherever the capture
contains recoverable geometry at all.

Runtime rose (nadir 39 s → ~100 s, orbit 64 s → ~85 s): the multi-scale pair graph
matches roughly 2.5x as many pairs. That is the cost of having wide-baseline pairs
available, and on this evidence it buys one to two orders of magnitude in
accuracy. It has not been optimised.

**Not yet measured: the `ba` arm with these fixes.** The open question is whether
bundle adjustment still earns its 3x runtime now that initialisation is sound —
BA was previously repairing damage that no longer occurs. That A/B is the first
thing to run next.

---

## Resume here

State at pause: **working tree consistent, 55/55 tests passing.** Nothing is
half-applied; every change described above is in the tree and covered by tests.

### Rebuild the environment

```bash
cd drishti3d
uv venv --python 3.12 .venv      # see docs/ENVIRONMENT.md for the full install
.venv/bin/python -m pytest tests -q          # expect 55 passed
```

### The one command that decides what happens next

```bash
python -m eval.benchmark --variants baseline,ba \
    --regimes oblique_pass,nadir_grid,orbit,low_parallax \
    --seeds 0,1,2 --frames 60 --out bench_out --scene-cache <cache>
```

It was stopped 8/24 cells in. The `baseline` arm is what proves the
initialisation work; the `ba` arm answers the open question below.

### Superseded

The list below was written at the 2026-09-02 pause. Items 1 and 3 are now done
(see the 2026-09-03 entries); the rest still stand. Kept for the record rather
than rewritten.

### Next items, in the order the evidence supports

1. **Re-measure whether bundle adjustment still pays.** BA costs ~3x runtime and
   was previously recovering error that a bad initialisation created. With
   initialisation fixed, `baseline` (BA off) already reaches 0.011-0.679 m ATE.
   If BA no longer adds much, the honest move is to stop running it by default —
   which would be a result, not a retreat. Do not assume either way.
2. **Reduce the matching cost the multi-scale pair graph added** (~2.5x more
   pairs). Options: cap pairs per stride, prune by GPS-predicted overlap, or
   reuse descriptors more aggressively. Only worth doing after item 1, since
   item 1 may remove the BA cost that dominates anyway.
3. **Roadmap phase 4 — the trust layer.** Calibrated per-point and per-measurement
   uncertainty, and the spatial coverage/observation-space layer (decisions D-002
   and D-003). Untouched. This is the product differentiator and the largest
   remaining body of work.
4. **Real data.** Still blocked on `git lfs pull` (see ENVIRONMENT.md). The ODM
   adapter in `eval/cases.py` already handles the Bellus layout, so a real-data
   scorecard is close once the content is fetched. Every number in this repository
   is synthetic until then.
5. **Roadmap phases 5-6** — learned matching A/B, dense multi-view verification,
   capture-quality prediction and recapture planning. Untouched.

### Things deliberately left alone

- `low_parallax` still refuses to reconstruct 2 of 3 seeds. On the evidence this
  is correct (H/E inlier ratio 1.002, cheirality 0.571 — the capture lacks the
  geometry). Do not "fix" it by loosening the seed-pair criteria without first
  showing the result is better than a refusal.
- The `baseline` variant name still means "BA off", and now also carries the
  improved initialisation. It is **not** the same code as the `baseline` in the
  earlier archived benchmarks. When comparing across archives, compare against the
  dated directory, not against the name.

---

## 2026-09-03 — Does bundle adjustment still pay?

This was the open question left at the pause: BA cost ~3-4x runtime and had been
recovering error that a bad initialisation created. With initialisation fixed,
does it still earn that?

Full 24-cell matrix, archived at
[`benchmarks/2026-09-03_p1_baseline_vs_ba/`](benchmarks/2026-09-03_p1_baseline_vs_ba/).
`baseline` here means **BA off with the fixed initialiser**, not the original code.

| Metric (median / worst) | `baseline` (BA off) | `ba` (BA on) |
|---|---|---|
| ATE RMSE (m) | 0.0693 / 0.6793 | **0.0028 / 0.2555** |
| Metric scale error | 0.0020 / 0.0035 | 0.0020 / 0.0035 — *identical* |
| Dimensional error (%) | **2.49** / 100.0 | 2.87 / 100.0 |
| Completeness @0.5 m | **0.712** | 0.661 |
| Runtime (s, median) | **98** | 405 (**4.1x**) |
| Failures | 2/12 | 2/12 |

**The answer is not the one the earlier numbers implied.** BA still improves
trajectory error by ~25x, and it removed its own worst failure mode entirely
(`oblique_pass` is now 0.002 m on all three seeds, where it was
0.002 / 7.18 / total-failure before). But:

- **metric scale error is bit-identical** with and without it;
- **dimensional error and completeness are no better**, and if anything slightly
  worse;
- it costs **4.1x** the runtime.

Dimensional error and completeness are the product's actual deliverables — what a
user measures. On this evidence BA buys camera-trajectory precision that no
current deliverable consumes, at four times the compute.

**What I did not do:** flip the default. `bundle_adjust=True` remains the
default. Turning it off is a product decision with real consequences for anyone
consuming the exported trajectory, and the evidence supports *raising the
question*, not settling it unilaterally. The `baseline` variant measures the
BA-off path continuously, so the decision can be made on evidence whenever it is
wanted.

**Caveat on the "slightly worse" reading:** the dimensional-error gap
(2.49% vs 2.87%) is *within* the seed-to-seed spread measured below. It should be
read as "no measurable benefit", not as "BA harms accuracy".

## 2026-09-03 — Scheduler performance and point-integrity fixes

Two defects found by re-reading the code I had written, neither caught by tests.

**1. O(frames^2 x points) support scanning.** `_support(f)` walked every entry of
`point_of_track` for every pending frame on every registration step — roughly
60 x 60 x 18k dict lookups. Replaced with a frame->tracks reverse index rebuilt
once per triangulation pass. I had previously attributed the whole runtime rise
(39 s -> 100 s on nadir cells) to the extra matching pairs; that was wrong, and
this was a large part of it.

**2. Stale points survived their own quality gate.** When a track failed
cheirality, exceeded `max_reproj`, or fell below `min_tri_angle`,
`_retriangulate` did `continue` — leaving whatever was stored on a previous pass
in `point_of_track`. A point triangulated early, when few cameras were
registered, could therefore ship in the final cloud carrying a reprojection error
and triangulation angle measured against *older* camera poses, and failing the
current gates. Both numbers feed the published per-point confidence.

This one mattered disproportionately here: the product's claim is that every
point is verified and carries honest statistics. Also hoisted the camera table,
which was being rebuilt once per track.

Measured (baseline arm, archived at
[`benchmarks/2026-09-03_v4_index_stale/`](benchmarks/2026-09-03_v4_index_stale/)):

| | before | after |
|---|---|---|
| Runtime, orbit cells | 82-90 s | **74-77 s** (~10% faster) |
| Points, oblique/orbit | — | −0.3% (stale points removed) |
| ATE, oblique + orbit | — | **bit-identical** |
| Dimensional error, `nadir_grid/s2` | 5.16% | **2.51%** |
| Dimensional error, `nadir_grid/s1` | 1.32% | 1.24% |

The integrity fix pays for itself: where it changed anything, dimensional error
improved. Oblique and orbit results are bit-identical, which is the expected
signature of removing only points that were genuinely stale.

## 2026-09-03 — Correction: an improvement I over-claimed

I previously reported `nadir_grid/s0` ATE improving 2.312 m -> 0.178 m as evidence
that the initialisation work helped that regime. **That comparison was noise, and
I should not have quoted it.**

Running `nadir_grid` across six seeds (archived at
[`benchmarks/2026-09-03_nadir_6seeds/`](benchmarks/2026-09-03_nadir_6seeds/)):

| Metric | median | min | max | spread |
|---|---|---|---|---|
| ATE RMSE (m) | 1.259 | 0.170 | 2.405 | **2.234** |
| Dimensional error (%) | 2.283 | 1.240 | 2.688 | 1.448 |
| Completeness @0.5 m | 0.647 | 0.565 | 0.683 | 0.119 |
| Registration | **1.000** | **1.000** | **1.000** | **0.000** |

ATE varies by a factor of 14 across seeds of the same regime under identical code.
The single-cell "2.312 -> 0.178" I quoted sits entirely inside that spread.

**What is actually defensible for `nadir_grid`:** registration went from 66.7% to
**100% on every seed tested**, with zero spread. That is the real result. The ATE
improvement was not.

**The useful insight underneath it:** in a near-planar nadir capture the camera
trajectory is weakly constrained — the classic planar degeneracy — so ATE swings
wildly, while the reconstructed geometry stays stable (dimensional error spread
only 1.4 points, completeness spread 0.12). **For nadir mapping, trajectory error
is a poor proxy for measurement quality**, and dimensional error should be the
headline metric for that regime.

**Method change this forces:** three seeds is not enough for a high-variance
regime. Any claim about `nadir_grid` needs at least six, and a claim based on a
single cell of it is not evidence at all.

---

## 2026-09-03 — Phase 4: the trust layer (calibrated measurement uncertainty)

Roadmap P1 / decision D-002. The shipped per-point "confidence" was a
hand-weighted blend of track length, reprojection error and triangulation angle:
it orders points plausibly, but has no units and no empirical meaning. Nothing
established that a point scoring 0.8 was accurate to any particular distance. For
a product whose output is a *measurement*, that is the difference between a
decoration and a specification.

### 4.1 What was built

`reconstruction/drishti_recon/uncertainty.py` — first-order (Gauss-Newton)
propagation, `Cov(X) = sigma_px^2 (J^T J)^-1`, where `J` stacks each
observation's 2x3 projection derivative. This captures exactly the geometry that
matters: wide triangulation angles give a well-conditioned normal matrix and a
tight covariance; near-parallel rays give a near-singular one and an enormous
uncertainty *along the viewing direction*.

Threaded end to end: computed in `sfm` from the final camera geometry, carried
through `fusion`'s downsampling and outlier indexing (so a shipped point keeps
*its own* uncertainty), scaled into metres by the GNSS similarity, persisted in
`cloud.npz`, and surfaced by `measure` as
`12.025 +/- 0.286 m (95%)` instead of a bare number.

Measurements now propagate two terms — endpoint geometry *along the measurement
direction*, and metric scale. Scale multiplies the whole distance, so it
dominates long measurements while the endpoint term does not. Inferred
(AI-assisted) points get `sigma = inf`, never zero: a missing uncertainty must
not read as a confident one. `meets_requirement()` refuses a measurement whose
interval exceeds the mission tolerance.

Verified by Monte-Carlo: perturb image measurements by a *known* pixel noise 400
times, re-triangulate, and compare the observed scatter against the prediction
**per principal axis**. Predicted and observed agree within 0.6-1.6x on every
axis.

### 4.2 Two bugs the calibration experiment exposed

Running the acceptance experiment (measure known reference distances on 15
reconstructed scenes, compare error against predicted sigma) gave **100% coverage
at every level** — intervals ~4x too wide. Chasing that found two defects:

1. **Assumed pixel noise.** `sigma_px` was hard-coded to 0.5 px while these
   reconstructions have residuals of 0.03-0.2 px. Now estimated from the actual
   reprojection residuals by a robust (normalised-MAD) scale, so the model adapts
   to real imagery instead of a guess.

2. **A units bug in my own `scale_sigma`** (added earlier, in the weighted-Sim(3)
   work). The trajectory extent was measured in the *arbitrary reconstruction
   frame* while the residual was in metres, and the formula then multiplied by
   the scale factor as well — inflating relative scale uncertainty by the scale
   itself. It reported **10.2%** scale uncertainty on a fit good to ~0.2%, which
   then swamped every measurement (12 m x 0.102 = 1.22 m). Fixed by converting
   the extent to metres before dividing.

Worth recording that my first hypothesis (the conservative worst-axis
approximation) was **wrong** — swapping to the isotropic-equivalent sigma changed
the factor from 0.259 to 0.270, i.e. not at all. Only measuring the actual
components found it.

### 4.3 Gaussian rescaling was not enough

With both bugs fixed, intervals came out **optimistic by 1.56x** — the expected
direction, since pose uncertainty and systematic error are deliberately not
modelled. But a single Gaussian scale factor only fixes one point of the
distribution:

| level | raw coverage | after Gaussian rescale |
|---|---|---|
| 50% | 0.444 | 0.500 |
| 80% | 0.528 | 0.667 |
| 95% | 0.667 | 0.694 |

The 95% level stays badly under-covered because measurement error here is not
Gaussian: unmodelled distortion, pose error and calibration bias are systematic,
and produce a heavier tail than a normal distribution allows.

Replaced with **conformal (distribution-free) calibration**: for each level, the
multiplier is the corresponding empirical quantile of `|error| / sigma`, with the
standard finite-sample adjustment. Validated by **leave-one-out**, so the factor
never sees the measurement it scores:

| level | raw | Gaussian | conformal (leave-one-out) |
|---|---|---|---|
| 50% | 0.444 | 0.500 | **0.528** |
| 80% | 0.528 | 0.667 | **0.833** |
| 95% | 0.667 | 0.694 | **0.972** |

All three levels now achieve their nominal coverage on held-out measurements.
That is the D-002 acceptance criterion met.

`python -m eval.calibrate_uncertainty --scenes <cache> --out <dir>` reproduces
this, and prints the held-out column alongside the fitted one precisely because a
conformal factor scored on its own fitting set is guaranteed to look good.

### 4.4 Honest limits of this result

- **n = 36 measurements**, from 3 reference distances across 12 reconstructable
  scenes. A 95% quantile estimated from 36 samples is driven by its two or three
  worst cases; the conformal factor at that level (k = 11.2) is correspondingly
  uncertain. More scenes would tighten it.
- **All synthetic.** These renders have no motion blur, rolling shutter, exposure
  variation or lens distortion, so the systematic-error component that conformal
  calibration exists to absorb is under-represented. On real imagery the factors
  should be expected to grow.
- **Calibration factors are not applied automatically.** They are reported, not
  baked in — a factor derived from synthetic scenes should not silently widen a
  real customer's intervals.
- Pose uncertainty is still not modelled, and remains the main reason the raw
  intervals are optimistic.

---

## 2026-09-03 — Phase 4 (part 2): observation-space coverage

Decision D-003. Both committed quality reports show **zero** points classified
`UNOBSERVED` and zero `DYNAMIC_EXCLUDED`. That was never a classifier bug — it is
a category error. A surface nobody photographed produces **no point at all**, and
a masked moving object produces no point either. Neither absence can be carried
by a point label, so the legend promised something the data model could not
deliver.

The information is real and it is what a measurement product needs: *which parts
of this scene did the flight actually establish?* That is a question about space,
so `reconstruction/drishti_recon/coverage.py` answers it with a voxel field:

| Class | Meaning |
|---|---|
| `OBSERVED` | surface present, >= 2 unobstructed views, acceptable incidence — **measurable** |
| `WEAK` | surface present but single-view or grazing — not measurable |
| `OCCLUDED` | inside a frustum, but every sight line is blocked — the hidden wall |
| `UNSEEN` | never entered any camera frustum — the flight did not look there |
| `EMPTY` | swept by rays and verified to contain no surface — a *positive* result |

Visibility uses a per-camera z-buffer built from the cloud (one pass per camera,
not a ray march per cell). `is_measurable()` is the gate: `UNSEEN`, `OCCLUDED`
and `WEAK` are refused, because a confident number from unestablished space is
worse than no number. `recapture_hints()` reports the largest gaps as advice a
pilot could act on.

### Acceptance experiment (D-003's stated bar)

`tests/test_coverage.py` builds a scene with a wall *deliberately hidden behind
another wall*, with every camera on the near side:

- hidden wall: **< 20%** measurable, and > 50% classified `UNSEEN`/`OCCLUDED`
- visible wall: **> 50%** measurable
- single-view ground: `WEAK`, **< 5%** measurable — the same surface with two
  views becomes > 50% measurable, showing the distinction is about support, not
  about the surface
- free space between camera and surface: `EMPTY`, distinguished from `UNSEEN`

11 tests, all passing.

### Three bugs found while building it

1. **The depth buffer let sight lines slip between points.** A sparse cloud
   projects to isolated pixels, so a ray passed *between* two points of a solid
   wall and reported the space behind it as free — the fully occluded wall came
   back 100% visible. Fixed by dilating the buffer with a minimum filter, which
   can only make occlusion more likely: the conservative direction for a layer
   whose job is to refuse.

2. **My incidence-angle "proxy" measured the wrong thing.** Without per-cell
   normals I had scored incidence by how vertical the *view ray* was, which rates
   a horizontal ray hitting a vertical wall — the face-on, ideal case — as the
   worst possible incidence. It suppressed 75% of a perfectly visible wall.
   Replaced with real per-cell normals by PCA over the points in each cell, and a
   true ray-to-normal angle. Cells with no estimable normal are now simply not
   incidence-tested, rather than judged by a stand-in that means something else.

3. **Camera rotations were not transformed into the ENU frame.** I moved each
   camera's centre through the GNSS similarity but kept its rotation, on the
   assumption that a similarity leaves rotation unchanged. It does not: with
   `X_enu = s*R_a*X_recon + t`, the world->camera rotation becomes
   `R_cam @ R_a^T`. Every camera pointed the wrong way, nothing fell inside any
   frustum, and a whole reconstructed scene came back `UNSEEN` — with the unit
   tests still green, because they construct cameras directly in the target
   frame. Only running it end-to-end on a real reconstruction exposed it.

### Measured on real reconstructions

| Scene | OBSERVED | OCCLUDED | UNSEEN | EMPTY | volume explained | measurable surface |
|---|---|---|---|---|---|---|
| `nadir_grid_s0` | 4,063 | 12,451 | 100,501 | 114,593 | 51.2% | 98.7% |
| `orbit_s0` | 4,069 | 14,423 | 86,423 | 56,081 | 37.4% | 95.9% |

The contrast is the useful part: a nadir grid sweeps and verifies far more *free
space* (51% of the volume explained) because it flies over a wide area, while an
orbit concentrates on one structure and leaves more of the volume unvisited.
Neither figure was previously visible at all.

Shipped as `artifacts/coverage.npz` (the field) and `artifacts/coverage.json`
(summary plus recapture hints), and summarised in the quality report.

**Suite: 83 tests.**


---

## Resume here (updated 2026-09-03)

State: **83 tests passing**, working tree consistent, nothing half-applied.
Phases 1-4 of the roadmap are complete and measured.

### Done
1. **Truth harness** — reproducible env, 4 capture regimes, benchmark with
   provenance and median/worst reporting. 8 archives in `docs/benchmarks/`.
2. **Geometric core** — bundle adjustment with an analytic Jacobian, and the
   initialisation/retry rewrite that turned out to matter far more than BA.
3. **Sensor correctness** — uncertainty-weighted GNSS alignment, georeferencing-
   safe levelling, validated container timestamps.
4. **Trust layer** — propagated measurement uncertainty with conformal
   calibration (held-out coverage 0.53 / 0.83 / 0.97 against nominal
   0.50 / 0.80 / 0.95), and the observation-space coverage field that refuses
   measurement in unestablished space.

### Not done, in priority order
1. **Real data.** Blocked, and not on effort: this repo's LFS returns HTTP 401
   (`Requires authentication`) and the upstream OpenDroneMap object hash does not
   match, so the Bellus images cannot be fetched here. Needs the owner's GitHub
   credentials plus `git lfs install && git lfs pull`. **Every number in this
   repository is synthetic until that happens** — no motion blur, no rolling
   shutter, no lens distortion, no exposure variation.
2. **The bundle-adjustment default.** Evidence (D-010): BA costs 4.1x runtime,
   improves ATE 25x, and leaves dimensional error, completeness and scale error
   unchanged. Left at `bundle_adjust=True` deliberately — flipping it changes
   output for anyone consuming exported trajectories, so it is a product call.
3. **Phase 5 — learned matching.** SuperPoint/LightGlue as an optional matcher,
   adopted only if a versioned ablation shows downstream geometry improves.
   Needs model weights and a licence review before anything is wired in.
4. **Phase 6 — dense multi-view verification** (`AI_ONLY` vs
   `AI_GEOMETRICALLY_VERIFIED`), and capture-quality prediction / recapture
   planning. `coverage.recapture_hints()` is a first step toward the latter.
5. **Dynamic-object masking is not folded into the coverage layer.** Masked
   regions should become a distinct evidence class rather than simply producing
   no points.

### Traps worth remembering
- Never edit pipeline code while a benchmark matrix is running; each cell spawns
  a fresh subprocess and silently picks up the change. This invalidated one full
  run already.
- `nadir_grid` needs >= 6 seeds; its ATE spread is 0.17-2.4 m under identical
  code, and a 3-seed comparison there can invent an improvement that is pure noise.
- Unit tests that construct their own cameras cannot catch frame-convention
  errors in the integration. The coverage layer passed 11 unit tests while
  reporting an entire real scene as UNSEEN.

---

## 2026-09-03 — Phase 3 completed: the sensor model

Phase 3 was half done: real container timestamps, uncertainty-weighted GNSS,
georeferencing-safe levelling and a recorded vertical datum were in place, but
four items from the roadmap's P0 "calibration, timing and coordinate modelling"
were not. Grepping the source confirmed it rather than assuming:
`synchronize()` accepted an `offset` argument that **nothing ever estimated**,
and lever arm / boresight / rolling shutter appeared only in comments.

`reconstruction/drishti_recon/sensors.py` closes them. The framing that matters:
each of these biases georegistration in a way **no downstream stage can detect**,
because the result still looks self-consistent.

### Time offset (was: plumbing with no estimator)

The video clock and the GNSS clock start independently. A constant offset slides
every frame onto the wrong GNSS sample, and the aligner absorbs it as a spurious
translation along the flight direction.

Estimated by cross-correlating the **speed profile** of the reconstructed camera
track against the GNSS track. Speed is used deliberately: it is invariant to the
unknown rotation and (after normalising) the unknown scale between the
reconstruction frame and ENU, so this works *before* georegistration rather than
depending on it. Estimation runs after SfM, then the whole sequence is
re-synchronised on the corrected clock.

Recovers known offsets of 0, +0.35, -0.6 and +1.1 s to within 0.06 s, and does so
unchanged when the reconstruction is scaled 17x and rotated.

### Lever arm

The GNSS antenna is not the camera; on a small drone they are 10-30 cm apart. As
the aircraft yaws, that fixed body-frame offset traces a circle in world
coordinates — so ignoring it injects a *rotating* bias, not a constant one that
alignment could absorb. `apply_lever_arm` places the body offset in ENU using
telemetry attitude, and **refuses** when no attitude is available rather than
guessing an orientation.

### Rolling shutter (detected, not corrected)

Angular rate between consecutive poses, multiplied by sensor readout time, gives
how far the scene rotates between the first and last row of one image. Graded
none / mild / severe against feature-matching precision.

Deliberately *reports* rather than corrects: rolling-shutter bundle adjustment
estimates motion during readout and is a far larger change. Saying the
single-pose assumption is being violated is more useful than silently producing a
degraded number.

### Lens distortion

Corrected once, up front, with the intrinsics updated to the undistorted camera.
Threading coefficients through triangulation, PnP, bundle adjustment *and*
uncertainty propagation would need a distortion-aware variant of each — and any
one that was missed would fail silently.

### The bug this work introduced, and what caught it

All 19 sensor unit tests passed, and then **two end-to-end tests failed**: the
cloud collapsed from thousands of points to 12.

The time-offset estimator had returned **+1.800 s with correlation 0.77 and
`accepted=True`** on a fixture whose true offset is zero. That mis-synchronised
every frame, and the resulting alignment scale collapsed to 0.0064.

Cause: the fixture is 40 frames at 20 fps — a **2-second** flight — and the
default search was +/-2 s. At a 1.8 s shift almost nothing overlaps, and a
correlation computed over the surviving sliver is both noisy and biased upward,
so the largest shifts won on luck. Three guards added:

- the search window is clamped to a fraction of the overlapping span (scanning
  +/-2 s across a 2 s clip is not a measurement);
- candidate offsets must retain a substantial overlap to be scored at all;
- a peak pinned to the edge of the search window is rejected, because the true
  offset may lie outside it.

Both cases are now regression-tested. The lesson is the same one the coverage
layer taught earlier that day: **unit tests that construct their own inputs
cannot catch a mis-scaled assumption about real data.** Only the end-to-end run
found it, and it would have quietly corrupted every short real capture.

**Suite: 104 tests.**


### Phase 3 regression check

Baseline arm re-run after the sensor work
([`benchmarks/2026-09-03_p3_sensors_noregression/`](benchmarks/2026-09-03_p3_sensors_noregression/)):
ATE **bit-identical** on all nine cells (0.069 / 0.011 / 0.020 | 2.405 / 0.170 /
0.577 | 0.041 / 0.055 / 0.074 m), registration 100% throughout. The sensor
corrections are inert on this fixture — which is the expected and correct result,
since the synthetic capture has no clock offset, no lever arm and no distortion to
correct. They are guards for real data, and nothing here demonstrates their value
under field conditions.

---

## Resume here (updated 2026-09-03, end of session)

**Roadmap phases 1-4 are complete.** 104 tests passing, working tree consistent,
nothing half-applied, 10 benchmark archives under `docs/benchmarks/`.

| Phase | State |
|---|---|
| 1. Truth harness | Done, except its own exit criterion: the real-data (Bellus) scorecard is blocked. |
| 2. Geometric core | Done — BA with analytic Jacobian, and the initialisation/retry rewrite that mattered more. |
| 3. Sensor correctness | **Done** — time-offset estimation, lever arm, rolling-shutter detection, distortion input. |
| 4. Trust layer | Done — conformally calibrated measurement uncertainty, and the observation-space coverage field. |

### Next, in priority order

1. **Real data — the single biggest gap.** Every number in this repository is
   synthetic. `git lfs` returns HTTP 401 on this repo and the upstream
   OpenDroneMap object hash does not match, so it needs the owner's GitHub
   credentials, then `git lfs install && git lfs pull`. Synthetic renders have no
   motion blur, no rolling shutter, no lens distortion and no exposure variation —
   which means the phase-3 corrections and the conformal calibration factors are
   both **untested against the conditions they exist for**.
2. **The bundle-adjustment default** (D-010). BA costs 4.1x runtime, improves ATE
   25x, and leaves dimensional error, completeness and scale error unchanged.
   Left at `bundle_adjust=True` deliberately: flipping it changes exported
   trajectories, so it is a product decision.
3. **Phase 5 — learned matching.** ~5-7 h wall clock. An RTX 5060 (8 GB) is
   available but torch is not installed; it is Blackwell (sm_120) and needs a CUDA
   12.8+ build, which is the main schedule risk. **Licence gate:** LightGlue is
   Apache-2.0 but the original SuperPoint weights are MagicLeap non-commercial —
   DISK or ALIKED are permissive alternatives. That choice is the owner's.
   Note the honest possibility that the answer is a measured "no", as it was for BA.
4. **Phase 6** — dense multi-view verification (`AI_ONLY` vs
   `AI_GEOMETRICALLY_VERIFIED`), capture-quality prediction and recapture
   planning. `coverage.recapture_hints()` is a first step.
5. **Smaller gaps:** dynamic-object masking is not folded into the coverage layer,
   so `DYNAMIC_EXCLUDED` still has no representation; IMU/camera boresight and
   rolling-shutter-aware BA are not implemented.

### Traps worth remembering

- **Never edit pipeline code while a benchmark matrix is running** — each cell
  spawns a fresh subprocess and silently picks up the change. This invalidated a
  full run once.
- **`nadir_grid` needs >= 6 seeds.** Its ATE spread is 0.17-2.4 m under identical
  code; a 3-seed comparison there can invent an improvement that is pure noise.
- **Unit tests that build their own inputs cannot catch integration-scale
  errors.** This bit twice in one day: the coverage layer passed 11 unit tests
  while reporting a whole real scene as UNSEEN (camera rotations not transformed
  through the similarity), and the time-offset estimator passed 19 while
  confidently inventing a +1.8 s offset on a 2-second clip. Both were only found
  by running end to end.

---

## 2026-09-04 — Phase 5: learned matching, and a measured "no"

### The environment risk did not materialise

I had flagged Blackwell (sm_120) support as the main schedule risk. PyTorch
2.11.0+cu128 installs and runs on the RTX 5060; GPU matmul verified, kornia 0.8.3
alongside. The install needed a raised HTTP timeout — the CUDA wheels are large
enough that the default aborted mid-download.

### The licence gate, removed rather than deferred

LightGlue's *code* is Apache-2.0, but the original **SuperPoint weights are
MagicLeap non-commercial** — a problem discovered late is a problem discovered too
late. `features.py` therefore defaults to **DISK (Apache-2.0)** or ALIKED
(BSD-3), and **refuses SuperPoint** unless a caller explicitly opts in. There is a
test asserting the refusal, and every run records the licence of the backend it
used in its provenance.

### The adapter

`reconstruction/drishti_recon/features.py`. A backend owns exactly two
operations — detect in one image, match two descriptor sets — and nothing else.
The pair graph, geometric verification, triangulation thresholds and registration
order are all shared, which is what makes a difference attributable to the
matcher rather than to which images were compared.

Two properties worth stating:

- The SIFT path is asserted **byte-identical** to the original inline code, so all
  archived benchmarks stay comparable.
- An unknown backend name **raises** rather than falling back to SIFT. A silent
  fallback is the worst possible failure here: the run would be labelled as the
  learned variant while measuring the classical one.

### Result: SIFT vs LightGlue+DISK (identical pair graph)

Archived at [`benchmarks/2026-09-04_matcher_ablation/`](benchmarks/2026-09-04_matcher_ablation/).

| Cell | ATE SIFT | ATE LG | dim% SIFT | dim% LG | compl SIFT | compl LG | pts SIFT | pts LG |
|---|---|---|---|---|---|---|---|---|
| `orbit/s0` | **0.041** | 0.094 | 2.03 | **1.60** | **0.956** | 0.898 | 29,384 | 12,622 |
| `orbit/s1` | **0.055** | 0.227 | **2.30** | 2.93 | **0.947** | 0.880 | 29,491 | 12,393 |
| `oblique/s0` | 0.069 | **0.068** | **2.62** | 3.28 | 0.345 | **0.503** | 12,630 | 10,144 |
| `oblique/s1` | **0.011** | 0.116 | 4.01 | **2.66** | **0.425** | 0.374 | 12,807 | 10,378 |
| `nadir/s0` | 2.405 | **2.327** | **2.15** | 7.92 | 0.565 | **0.636** | 21,512 | 17,293 |
| `nadir/s1` | **0.170** | 1.681 | **1.24** | 3.29 | **0.683** | 0.651 | 23,620 | 18,815 |
| **median** | **0.062** | 0.171 | **2.22** | 3.11 | 0.624 | **0.643** | | |

**LightGlue+DISK is not adopted.** Median trajectory error is 2.8x worse, median
dimensional error is worse, it produces 30-60% fewer points, and it is *slower*
end-to-end despite running on the GPU. Completeness is marginally better, which is
not enough to carry the rest. `matcher="sift"` remains the default.

A classical control (ORB) was run first to prove the adapter is not SIFT-shaped:
2.4x faster, up to 15x worse ATE. Also archived.

### The caveat that matters more than the result

**This is a synthetic-data verdict, and this is the ablation where that limitation
bites hardest.** The fixture's textures are high-frequency procedural noise — close
to ideal for SIFT, and unlike anything DISK was trained on. Every condition a
learned matcher exists to handle is *absent* here: no illumination change, no
repetitive man-made texture, no viewpoint-induced appearance change, no motion
blur, no compression artefacts.

So the honest statement is **"not adopted on this benchmark"**, not "learned
matching does not help". Re-running this ablation is one of the first things worth
doing once real imagery is available, and the adapter now makes that a
one-flag experiment rather than a project.

### Bugs found and fixed

1. `create()` passed `detector` twice when called as `create("lightglue",
   detector=...)`.
2. DISK rejects single-channel input; the pipeline works in grayscale. The
   backend now replicates the channel rather than forcing colour frames through
   every call site.
3. **AKAZE no longer exists in OpenCV 5.0** — the version this project pins. The
   intended classical control had to become ORB.

**Suite: 117 tests.**


---

## Resume here (updated 2026-09-04)

**Roadmap phases 1-5 are complete.** 117 tests passing, working tree consistent,
12 benchmark archives under `docs/benchmarks/`.

| Phase | State |
|---|---|
| 1. Truth harness | Done, except its exit criterion: the real-data scorecard is blocked. |
| 2. Geometric core | Done. |
| 3. Sensor correctness | Done. |
| 4. Trust layer | Done. |
| 5. Learned matching | Done — **measured and declined**. Adapter shipped, SIFT stays default. |

### Next

1. **Real data — still the biggest gap, and now the blocker for two conclusions.**
   Both the phase-5 verdict (learned matching declined) and the conformal
   calibration factors are synthetic-only, and both are exactly the kind of result
   real imagery could overturn. Needs the owner's GitHub credentials, then
   `git lfs install && git lfs pull`. Re-run `--variants baseline,lightglue`
   first — it is now a one-flag experiment.
2. **The bundle-adjustment default** (D-010) — still a product decision.
3. **Phase 6** — dense multi-view verification (`AI_ONLY` vs
   `AI_GEOMETRICALLY_VERIFIED`), capture-quality prediction, recapture planning.
   `coverage.recapture_hints()` is a first step. This is the last unstarted phase.
4. **Smaller gaps:** dynamic-object masking is still not folded into the coverage
   layer, so `DYNAMIC_EXCLUDED` has no representation; IMU/camera boresight and
   rolling-shutter-aware BA are not implemented.

### Environment note

torch 2.11.0+cu128 and kornia 0.8.3 are now installed and working on the RTX 5060
(sm_120). The CUDA wheels need `UV_HTTP_TIMEOUT=300` or the download aborts.

---

## 2026-09-04 — Phase 6: verified inference, capture guidance, and dynamic space

The last unstarted phase, plus the `DYNAMIC_EXCLUDED` gap left open since D-003.

### 6.1 Multi-view verification of inferred geometry

`reconstruction/drishti_recon/verify.py`. The depth-prior path fits a monocular
network's depth to one frame's sparse points and merges everything it produces.
Each inferred point is therefore supported by exactly one view and one model
prediction — and **a single-view guess has no way to be wrong in a detectable
way**.

Verification projects each inferred point into the *other* cameras and tests it
against a z-buffer built from the classical, triangulated cloud only — something
independent of the depth model that produced it. Points agreeing in depth and
colour across enough views are promoted to a new provenance class,
`AI_GEOMETRICALLY_VERIFIED`.

Two design points that matter:

- **A view only votes if it can see the point.** Outside the frustum, or behind
  observed geometry, is neither agreement nor disagreement. Counting occlusion as
  failure would punish inferred geometry exactly where it is legitimately hidden.
- **Verified inferred geometry is still not measurable.** "A model produced it"
  and "several cameras agree with it" are different claims, and only the second is
  evidence — but corroborated is not triangulated. Promoting it into the
  measurable class would be precisely the failure this project exists to prevent.
  What the class buys is an honest middle tier.

Tested on a scene where the discriminating case is built in: inferred points *on*
the true surface verify at >80%, identical-looking points floating 8 m above it
verify at <20%, and a mixed batch separates cleanly in one call.

### 6.2 Capture assessment and recapture planning

`reconstruction/drishti_recon/capture.py`. This is the difference between
post-processing software and an operational tool: it answers *was this capture
geometrically capable of the accuracy asked for, and if not what is the smallest
additional flying that would fix it?*

Five factors — parallax, coverage, registration, redundancy, image quality — each
already measured elsewhere in the pipeline, combined explicitly so the report can
name **which** factor limited the capture rather than emitting an opaque score.
Factors that could not be measured are renormalised out rather than scored as
zero.

The plan separates **fixable** from **unfixable**: unobserved regions can be
reflown, but blur and exposure cannot be fixed by flying the same way again, and
telling someone to refly a sensor problem is worse than telling them nothing.

End-to-end on real reconstructions:

| Capture | Grade | Limiting factor | Advice |
|---|---|---|---|
| `orbit_s0` | excellent (0.90) | coverage (0.62) | none — no busywork |
| `low_parallax_s2` | marginal (0.49) | registration (0.03) | second pass at a different angle; more overlap; **5 waypoints** |

With `required_sigma_m` set, the gate answers directly: `orbit_s0` delivers
0.0405 m, so it **meets** a 0.10 m requirement and **fails** a 0.02 m one, with
the reason stated.

**A bug caught by its own test:** the planner keyed advice off
`limiting_factor`, which is just the *minimum* factor and therefore always exists
— so a capture scoring 1.00/1.00 was still told to refly. Advice is now triggered
only by a factor being genuinely deficient; `limiting_factor` is used for
prioritisation in the summary, not as a trigger.

### 6.3 `DYNAMIC_EXCLUDED` finally has a representation

The original audit found zero points in this class and I recorded (D-003) that
this was a category error: a masked moving object produces no point, so no point
can carry the label. The coverage field now carries it as a property of **space**.

A ray through a pixel masked as dynamic carries no usable evidence — the
observation was discarded on purpose. Cells seen *only* through such rays are
classified `DYNAMIC_EXCLUDED`: neither established geometry nor unexplored
volume. Masking now also visibly *costs* measurable surface, rather than being
silently ignored.

**Suite: 137 tests.**


### Phase 6 regression check

Baseline arm re-run
([`benchmarks/2026-09-04_p6_noregression/`](benchmarks/2026-09-04_p6_noregression/)):
ATE **bit-identical** on all nine cells (0.069 / 0.011 / 0.020 | 2.405 / 0.170 /
0.577 | 0.041 / 0.055 / 0.074 m), registration 100% throughout. Phase 6 is
additive — it observes and reports on the reconstruction without changing it.

---

## Resume here (updated 2026-09-04, end of session)

**All six roadmap phases are implemented.** 137 tests passing, working tree
consistent, 14 benchmark archives under `docs/benchmarks/`, decisions D-001
through D-019 recorded.

| Phase | State |
|---|---|
| 1. Truth harness | Done, except its own exit criterion — the real-data scorecard. |
| 2. Geometric core | Done. |
| 3. Sensor correctness | Done. |
| 4. Trust layer | Done. |
| 5. Learned matching | Done — measured and **declined**; SIFT remains default. |
| 6. Dense verification + capture guidance | Done. |

### What is genuinely left

1. **Real data. This is now the only thing standing between the project and its
   own stated exit criteria.** `git lfs` returns HTTP 401 on this repo; it needs
   the owner's GitHub credentials, then `git lfs install && git lfs pull`.

   Three conclusions in this repository are synthetic-only and are exactly the
   kind that real imagery could overturn:
   - the phase-5 verdict declining learned matching (the fixture's procedural
     texture flatters SIFT and is unlike DISK's training data);
   - the conformal calibration factors (synthetic renders under-represent the
     systematic error those factors exist to absorb);
   - every phase-3 sensor correction (the fixture has no clock offset, no lever
     arm, no rolling shutter and no lens distortion to correct, so those code
     paths are verified by unit tests but have never done real work).

2. **The bundle-adjustment default** (D-010) — a product decision, still open.

3. **Not implemented, and honestly out of scope so far:** IMU/camera boresight
   calibration, rolling-shutter-aware bundle adjustment, and PyCOLMAP as an
   alternative production engine.

### Traps worth remembering

- Never edit pipeline code while a benchmark matrix is running.
- `nadir_grid` needs >= 6 seeds; its ATE spread is 0.17-2.4 m under identical code.
- **Unit tests that construct their own inputs cannot catch integration-scale
  errors.** This bit three times: the coverage layer passed 11 unit tests while
  reporting a whole scene as UNSEEN; the time-offset estimator passed 19 while
  inventing a +1.8 s offset on a 2 s clip; the recapture planner told a perfect
  capture to refly. All three were only found end to end.
- CUDA wheels need `UV_HTTP_TIMEOUT=300` or the download aborts mid-way.

---

## 2026-09-04 — Real data, at last. And it changes several conclusions.

The Bellus LFS objects were fetched (122 images, 4048x3048, Canon PowerShot S110,
719 MB). This is the first time any of this pipeline has touched real imagery.

**Headline: the pipeline does not yet work on this dataset.** Best result so far
is **20 of 122 frames registered (16%)**. The synthetic benchmark reported 100%
registration on every regime. That gap is the single most important finding of
this whole effort, and it vindicates the roadmap's insistence that real data come
first — a position the synthetic results had made easy to forget.

Four distinct defects were found, each invisible to synthetic data.

### 1. Camera intrinsics were guessed, and the guess was 30% wrong

The ODM adapter passed no intrinsics, so the pipeline fell back to
`0.9 * max(w, h)` = 3643 px. EXIF gives focal length 5.2 mm and focal-plane
resolution, which fix the true value at **2795-2828 px**. Both essential-matrix
estimation and PnP depend directly on focal length. `eval/cases.py` now reads
intrinsics from EXIF (focal-plane resolution, falling back to 35 mm equivalent).

### 2. The seed-pair scorer chose a geometrically perfect island

With correct intrinsics, registration *fell* from 13 to 2. The chosen pair was
frames [0, 54]: 19.6 deg parallax, 330 inliers -- excellent geometry, and
topologically isolated. On a lawn-mower grid two frames from different strips can
view the same ground patch beautifully while almost nothing else observes it.

The scorer optimised parallax with no regard for whether the reconstruction could
*grow* from the pair. It now weights candidates by co-visibility -- how many other
frames are verified against both members (`_connectivity`).

### 3. Farneback optical flow saturates, and the keyframe selector trusted it

The real cause of the collapse. Consecutive frames displace ~570 px on a 1600 px
image (~36% of the width). Farneback reported **2.1 px** -- a 27x under-estimate --
because it is a small-motion estimator and a third-of-a-frame shift is far outside
its range.

The selector therefore concluded the frames were near-duplicates and thinned
122 -> 61. Measured consequence: consecutive frames verify with ~363 inliers and
build 5339 multi-view tracks; every-second-frame produces **zero** verified pairs.
Thinning took a workable capture and made it unreconstructable.

Video arrives with far more overlap than reconstruction needs, so thinning is free.
A photo survey has no overlap to spare -- every image was taken at the minimum the
pilot planned for. `keyframes.select` now measures consecutive displacement by
**phase correlation**, which handles large global translation, and returns the
capture untouched when frames already move more than 15% of the frame width. On
Bellus it measures 0.325 and keeps all 122 frames.

### 4. The Phase 5 verdict is overturned

Yesterday's ablation declined LightGlue on synthetic data, with the recorded
caveat that the fixture's procedural texture flattered SIFT and that real imagery
should be tested first. That caveat was correct.

Geometrically verified inliers per consecutive real pair:

| Matcher | pair 0 | pair 1 | pair 2 | pair 3 |
|---|---|---|---|---|
| SIFT | 14 | 35 | 31 | 50 |
| **LightGlue+DISK** | **278** | **563** | **729** | **656** |

**10-20x more verified correspondences on real aerial imagery.** Exactly the
reversal the synthetic benchmark could not have shown. D-016's conclusion is
superseded for real captures; see D-020.

### Where it stands, honestly

| Run | Registered | Points |
|---|---|---|
| First (SIFT, guessed intrinsics, thinned) | 13/61 | 1,396 |
| + EXIF intrinsics | 2/61 | 369 |
| + seed-pair connectivity | 12/61 | — |
| + LightGlue, still thinned | 2/61 | 502 |
| **+ no thinning (all four fixes)** | **20/122** | **5,169** |

Points are up 10x and registration is the best yet, but 16% is still a failure.
The alignment residual of 11.6 m confirms it. Something beyond these four defects
still limits growth on this capture -- the next thing to investigate is why
registration stalls at 20 cameras when tracks reach only length 4 (5339 two-view
tracks, 409 three-view, 5 four-view). Short tracks mean each new camera has little
2D-3D support to register against.

**Nothing in this repository should be described as validated on real data.**
Suite: 137 tests.

---

## 2026-09-04 (later) — I crashed the machine, and what that exposed

The rotation-robust matching run took the whole desktop down. The cause was
entirely mine, and it was three compounding unbounded quantities:

1. **The GNSS-proximity pair radius was `8 x median step`.** On this survey that
   is 8 x 51 m = 410 m, against a site 383 x 492 m -- so it proposed essentially
   *every* pair: **7,298 of a possible 7,381**.
2. **Each failing pair then retried 3 rotations**, so ~22,000 learned-matcher
   invocations were queued.
3. **The rotation cache was unbounded**, holding a full descriptor set per
   (frame, rotation).

### Fixes

- Radius is now `2.5 x step` with at most 10 nearest neighbours per frame, and a
  hard ceiling on total pairs. Measured: **7,298 -> 1,291 pairs (5.6x fewer)
  while retaining 89% of genuinely overlapping pairs (605 of 679)**. The extra
  6,000 pairs were buying almost nothing.
- The rotation cache is bounded and evicts, never discarding a set that has been
  merged into a frame.
- Heavy runs now execute under a **cgroup memory cap**
  (`systemd-run --user --scope -p MemoryMax=7G`). First attempt used
  `RLIMIT_AS`, which was wrong: it caps *virtual* address space, and CUDA
  reserves tens of GB of it up front -- that broke video encoding before any
  reconstruction started. cgroups cap resident memory, which is the actual
  constraint.

### A regression I introduced and caught

Enabling rotation retry for **SIFT** took the dataset from 13 registered cameras
to **zero**. SIFT is rotation invariant by construction, so the retry buys
nothing and actively harms -- it appends near-duplicate features that fragment
tracks. The retry is now gated to *rotation-sensitive* (learned) backends only.

### Where real-data reconstruction actually stands

| Configuration | Registered | Points |
|---|---|---|
| First real run (SIFT, guessed intrinsics, thinned frames) | 13/61 (21%) | 1,396 |
| **SIFT + EXIF intrinsics + no thinning + bounded graph** | **45/122 (37%)** | **2,731** |

Better, and still not good. Mean track length is **2.28** -- barely above the
two views needed to triangulate at all -- and georegistration is poor: 17 of 45
cameras inlier, 11.4 m residual.

**LightGlue on the full 122-frame set does not currently complete**: it exceeds
the 8 GB cgroup cap and is killed. Its 10-20x pairwise advantage is measured and
real, but it is not yet usable end-to-end on a survey this size on this hardware.
That is an honest open problem, not a result.

### The lesson worth keeping

Every fix in this session came from real data exposing an assumption that
synthetic data had silently validated. This one is slightly different: the crash
came from *my own* unbounded resource use, in code that was correct on 60-frame
synthetic scenes and catastrophic on a 122-frame real survey. Scale is an input
condition too, and it was untested.

### Regression check after the real-data changes (and a regression it caught)

The pair graph, keyframe selection and rotation handling all changed while
chasing real data, so the archived synthetic numbers no longer described the
code. Re-running the synthetic baseline found that **the tightened GNSS radius
had broken the nadir regime**:

| Cell | before the real-data work | tightened radius (2.5 steps) | after the fix |
|---|---|---|---|
| `nadir_grid/s0` | 2.405 m | 3.489 m | **1.749 m** |
| `nadir_grid/s1` | 0.170 m | 0.966 m | **0.097 m** |
| `nadir_grid/s2` | 0.577 m | 1.960 m | **0.343 m** |
| `nadir_grid/s0` scale err | 0.0029 | **0.0539** | **0.0008** |
| `orbit` s0-s2 | 0.041/0.055/0.074 | 0.046/0.066/0.083 | 0.042/0.056/0.074 |
| `oblique` s0-s2 | 0.069/0.011/0.020 | 0.068/0.011/0.020 | 0.069/0.049/0.132 |

**The fix, and why the first attempt was wrong.** Radius and neighbour count do
different jobs: the radius decides *which* frames are eligible, the cap decides
*how many* are taken. Cost is bounded by the cap alone (<= cap x n pairs), so the
radius can stay generous. Tightening the radius instead did bound cost, but on a
nadir grid the adjacent strip sits several strip-widths away in units of the
along-track step -- a small radius simply cannot reach it, and the cross-strip
links that make a survey rigid disappear.

With radius restored to 8 steps and the cap at 10, the Bellus graph is unchanged
at 1,291 pairs retaining 89% of overlapping pairs (the cap binds there either
way), while the nadir regime recovers. Orbit is restored exactly; oblique is
marginally worse at centimetre scale (0.020 -> 0.132 m on seed 2), attributable to
the keyframe guard changing which frames are kept.

Nadir's apparent improvement is **not** claimed as a gain: it sits inside the
0.17-2.4 m seed spread already documented for that regime.

The general point: three subsystems changed to chase a real-data failure, and one
of those changes silently damaged a regime nobody was looking at. The synthetic
benchmark could not find the real-data bugs, but it did catch the collateral
damage from fixing them. Both directions of that are worth keeping.

---

## 2026-09-05 — Real-data bottleneck largely cleared; georegistration is not

### Result

| | session start | now |
|---|---|---|
| Registered | 45/122 (37%) | **99/122 (81%)** |
| Points | 2,440 | **31,991** (13x) |
| Ground covered | 37,420 m2 | **106,415 m2** |
| Density | 0.065 pts/m2 | **0.300 pts/m2** |
| Peak memory | OOM at 8 GB | **4,052 MB** |

Two changes did it: **`max_keypoints` 4096 -> 2048** (LightGlue attention is
O(N^2), so a 4x memory cut, which is what let it finish at all) and the
rotation-robust pairing, which rescued **209 cross-strip pairs**. Bundle
adjustment then added the last 7 cameras and 9k points.

The GPU was never the constraint: the job peaked at ~4 GB of *system* RAM with
VRAM barely touched. The OOM was against a cgroup limit I had set myself.

### Georegistration is still unsolved, and it is not the GPS

13.12 m residual, 51/99 cameras inlier. Three measurements narrow it down:

- **The GPS is good.** Fitting straight lines through each flight strip, the
  cross-track scatter is **2.11 m median / 5.38 m p90** -- a drone cannot
  physically wobble that little, so this is the receiver's own error. A 13 m
  residual is not GPS noise.
- **It is not drift.** Residual is uniform across frame ranges (12-23 m), not
  growing along the sequence.
- **It is not a displaced block or a scale error.** Refitting on the best 25% of
  cameras still leaves 7.86 m, with recovered scale 0.99.

So the camera geometry itself is loose, and the cause is visible in one number:
**mean track length 2.37**. Most points are seen by exactly two cameras -- the
bare minimum to triangulate -- so camera positions are weakly constrained.

### A fix I tried, measured, and reverted

The rotation rescue *appends* a second feature set to a frame, so pair (i,j) can
match one set while (j,k) matches the other, splitting one physical point into
two tracks. That is a real defect and a plausible cause of the short tracks.

The fix was to assign **one canonical orientation per frame** instead. Measured:
**7/122 cameras registered**, against 99/122 with the append approach.

Why it failed: the orientation was propagated along the *sequential chain*, and
at a lawn-mower strip turn consecutive frames barely overlap, so the choice there
is a guess -- and in a chain one bad link corrupts every frame after it.
Interestingly the 7 cameras it did solve aligned to **3.53 m with 6/7 inliers**,
the best georegistration seen on this dataset, which supports the underlying idea.

Left in the code as `canonical_orientation_opt`, default **off**, with the reason
recorded. Making it work needs the orientation propagated over a spanning tree of
the *strongest* pairs, or seeded from GPS-adjacent neighbours -- not capture order.

### Honest status

The reconstruction now covers the site and recovers terrain relief. It is **not**
survey grade: 13 m absolute placement against 2 m GPS. Dense MVS should wait --
it inherits whatever pose error it is given, so densifying this model would
produce far more points in the same wrong places.

### MST orientation propagation — the fix that worked, and what it exposed

Propagating canonical orientation over a **maximum spanning tree of the strongest
verified pairs** (rather than capture order) works:

| | append (per-pair retry) | sequential canonical | **MST canonical** |
|---|---|---|---|
| Registered | 99/122 | 7/122 | **105/122 (86%)** |
| Points | 31,991 | 689 | 18,409 |
| Mean track length | 2.37 | 2.22 | **2.54** |
| Frames unanchored | n/a | n/a | **5** |
| GNSS residual | 13.12 m | 3.53 m (7 cams) | 13.40 m |

**A bug in my first MST attempt**, worth recording: edges were processed once in
descending weight order, and any edge whose *two* endpoints were both unanchored
at that moment was skipped and never revisited. That left **68 of 122 frames
unanchored** and cost half the registrations. Fixed by iterating to a fixpoint and
seeding any component the anchored set cannot reach: unanchored 68 -> 5, and
registration 55 -> 105.

### Georegistration: characterised, not yet fixed

Decomposing the 13.4 m residual over 105 cameras:

- horizontal median **9.08 m** (p90 18.4), vertical median **14.07 m** (p90 39.4)
- a robust fit with tight sigmas finds **11 cameras agreeing to 3.30 m horizontal
  / 1.95 m vertical**, and rejects the other 94

So the model has a well-constrained core and a poorly-constrained majority --
precisely what a mean track length of 2.54 predicts. Most points are seen by two
or three cameras, so most camera positions are weakly determined.

**The number that now gates everything: only 243 of 1,291 proposed pairs verify
(19%).** Tracks cannot chain through pairs that never verified. Raising that
ratio -- by proposing pairs that genuinely overlap rather than by index stride,
and by understanding why overlapping pairs still fail verification -- is the next
piece of work, and it is upstream of both georegistration and dense MVS.

**Dense MVS still has to wait.** It inherits pose error, so densifying a model
whose cameras are ~9 m out horizontally would produce far more points in the same
wrong places.

---

## 2026-09-05 (later) — Refocus on the problem statement: single-pass video -> dense 3D

Scope correction from the owner: the product is **single-pass drone video to 3D**,
and it needs both good measurements *and* a clearer picture. The Bellus dataset
is a 20-strip lawn-mower photo survey -- the right *real data*, but the wrong
*topology*. Much of the recent work (cross-strip pairing, rotation handling,
MST orientation) is grid-specific and does not apply to a single pass.

### Dense single-pass result

`densify="depth"` (Depth Anything V2, on GPU) plus the Phase 6 verification layer:

| | sparse | **dense** |
|---|---|---|
| Points | 19,037 | **251,492** (13x) |
| Density | 5.2 pts/m2 | **~52 pts/m2** |
| Runtime | 157 s | 247 s |

| Provenance class | points |
|---|---|
| Observed, high confidence | 6,588 |
| Observed, low confidence | 1,885 |
| **AI-inferred, multi-view verified** | **186,335** |
| AI-inferred, unverified | 56,684 |

**76.7% of inferred points are corroborated by a median of 26 independent
views**, tested against a z-buffer built only from the classical triangulated
cloud. The verification layer built in Phase 6 does real work here.

Measured geometry is unchanged by densification -- dimensional errors 0.71% /
3.72% / 2.20% on the known reference distances, from the 8,473 observed points.

### Two reporting bugs found by running it

1. **Quality metrics were scored on all points, including inferred ones.**
   Surface accuracy read **1.847 m over the full cloud against 0.835 m over
   observed geometry**, so enabling densification looked like an accuracy
   regression while the measured cloud was untouched. Metrics are now scored on
   observed geometry, with the inferred layer's contribution reported separately
   and explicitly labelled as coverage, not measured accuracy.

2. **Dimensional accuracy was measured with `allow_inferred=True`.** The headline
   accuracy number was allowed to snap to AI-generated surface -- precisely the
   failure the provenance model exists to prevent. Now `False`.

### Two of my own "improvements" were net-negative, and are reverted

A reviewer agent flagged that my separation-based pair prune contradicted the GNSS
radius. It was right, and worse than it looked:

- **The prune deleted 86% of cross-strip pairs on real data and 100% on synthetic
  nadir.** Fixed by exempting GNSS-proximity pairs (they are selected *because*
  they are spatially closest).
- **On the target single-pass regime the prune was actively harmful.** Video has
  a tiny flight step (~0.75 m over 60 frames), so a 1.8-step limit is 1.35 m and
  deletes exactly the wide-baseline stride pairs that create parallax. Measured:
  ATE 0.020 -> 0.102 m and 0.074 -> 0.309 m. **Now off by default**; a correct
  version needs predicted ground overlap, not a multiple of the step.
- **Raising `max_gps_neighbours` 10 -> 14 also degraded ATE** (orbit
  0.041 -> 0.237 m). More candidate pairs is not more useful geometry. Reverted.

Both were introduced this session with good intentions and no measurement of the
target regime. Regression check after reverting: orbit back to 0.042 / 0.056 /
0.074 m, oblique to 0.069 / 0.049 / 0.132 m -- matching the last known-good state.

The reviewer's other finding (loosening the epipolar RANSAC band from 1.0 to
3.0 px for real, uncorrected lenses) was tested and **collapsed the synthetic
reconstruction to zero points**: absence of distortion coefficients does not imply
a distorted lens, and synthetic renders are exact pinholes. It is now an explicit
per-capture opt-in rather than a default.

## 2026-09-06 — Sourcing real single-pass drone video

Downloaded three CC-licensed drone videos from Wikimedia Commons (no registration,
direct HTTP, ~326 MB total) into `drishti3d/data/real_drone/` (gitignored):

| File | Dur | Res | Subject |
|---|---|---|---|
| `gymnasium_neubiberg.webm` | 129 s | 1920×1080 @30 | school building |
| `st_lambertus.webm` | 346 s | 1920×1080 @19 | church (Immerather Dom) |
| `goetheanum.ogv` | 283 s | 1920×1080 @25 | Goetheanum, Dornach |

**Finding: published drone video is edited, not captured.** All three are montages —
15, 33 and 22 scene cuts respectively (histogram correlation < 0.80 between samples
at 2 fps). Feeding a whole file to the pipeline violates the single-pass assumption:
the frames span many unrelated shots, so pair matching is mostly cross-shot and fails.

**Finding: the 10–30 %-of-frame-width parallax rule needs a timescale.** Measured at
0.5 s spacing these read 0.7–2.9 %, which looks like the failure signature we saw on
the user's samples. They are not failures — they are cinematic, so the same parallax
arrives over seconds rather than frames. The diagnostic must state its spacing.

Added two reusable probes (`scan2.py`/`scan3.py` pattern):
1. **cut segmentation** — split at histogram-correlation drops, keep the longest run;
2. **cumulative parallax walk** — from each keyframe advance until phase-correlation
   shift reaches 15 % of frame width, abandoning the reach when response < 0.05.

Selected shots (longest cut-free run per file):

| Shot | Window | Length | Parallax @2 s |
|---|---|---|---|
| `gym_pass` | 0–63.5 s | 63.5 s | 6.7 % |
| `lambertus` | 182–223.5 s | 41.5 s | 6.5 % |
| `goetheanum` | 86–114 s | 28.0 s | 8.5 % |

Extracted at 1 fps / full res to `data/real_drone/shots/`.

**Caveat: no telemetry.** These carry no GPS or EXIF intrinsics, so reconstructions
are scale-free — they test structure and density, not georegistration. Goetheanum
and St. Lambertus have published dimensions and can anchor scale externally.
