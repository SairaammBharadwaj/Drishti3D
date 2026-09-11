# Drishti3D engineering decision log

This file records consequential decisions and the evidence behind them. Add an entry
before or alongside material model, metric, data, architecture or claim changes.

## Entry template

- **Date / decision ID:**
- **Decision:**
- **Problem and evidence:**
- **Alternatives considered:**
- **Why this option:**
- **Expected measurable effect:**
- **Risks / reversibility:**
- **Validation and acceptance threshold:**
- **Result after implementation:**
- **Artifacts / commit / report links:**

## 2026-09-02 / D-001 — prioritize validation and geometric optimization

- **Decision:** Put a reproducible real-data baseline and bundle-adjusted geometric
  core ahead of UI polish or additional generative reconstruction models.
- **Problem and evidence:** The default OpenCV engine has no bundle adjustment. The
  two committed synthetic reports range from 0.58–3.49% to 9.90–56.68% dimensional
  error, and no committed real-data scorecard was found.
- **Alternatives considered:** improve UI; enable depth densification by default;
  integrate a new learned model first.
- **Why this option:** the intended product is defensible measurement. New rendering
  or density cannot compensate for unoptimized camera geometry or missing external
  validation.
- **Expected measurable effect:** higher registration fraction, lower tail error and
  fewer catastrophic missions.
- **Risks / reversibility:** PyCOLMAP packaging and runtime complexity. Keep OpenCV as
  a deterministic fallback and compare through a shared evaluation interface.
- **Validation:** benchmark phases 1–3 in the roadmap; accept changes only through
  held-out geometric metrics and failure rate.
- **Result:** pending.
- **Artifacts:** `REPOSITORY_AUDIT_AND_IMPROVEMENT_ROADMAP.md`.

## 2026-09-02 / D-002 — confidence must be calibrated to error

- **Decision:** Replace the hand-weighted confidence interpretation with propagated
  uncertainty calibrated on held-out truth; retain the old score only as an internal
  diagnostic until then.
- **Problem and evidence:** current confidence is a fixed blend of track length,
  reprojection error and triangulation angle. No calibration artifact demonstrates
  that a score corresponds to spatial or measurement error.
- **Alternatives considered:** tune score weights manually; rename it “quality.”
- **Why this option:** the product differentiator is trustworthy measurement, which
  requires confidence to have an empirical meaning.
- **Expected measurable effect:** uncertainty intervals achieve stated coverage and
  unsafe measurements are automatically blocked.
- **Risks / reversibility:** covariance models may be approximate. Check calibration
  empirically and allow conservative conformal correction.
- **Validation:** reliability plots and 50/80/95% interval coverage on held-out data.
- **Result:** pending.

## 2026-09-02 / D-003 — treat missing space as data, not points

- **Decision:** represent unseen, occluded and dynamic-contaminated regions in a
  separate observation-space layer rather than expecting absent 3D points to carry
  `UNOBSERVED` or `DYNAMIC_EXCLUDED` labels.
- **Problem and evidence:** both committed reports contain zero points for these two
  classes. By construction, a missing or masked observation usually creates no point.
- **Alternatives considered:** infer a closed mesh and label its unsupported faces;
  keep the current point-only legend.
- **Why this option:** it expresses exactly what camera rays did and did not establish
  without hallucinating a surface.
- **Expected measurable effect:** hidden surfaces are consistently blocked from
  measurement and recapture advice becomes spatially specific.
- **Risks / reversibility:** voxel/frustum storage and visualization cost. Use a
  multiresolution sparse grid and keep it as a separate optional artifact.
- **Validation:** controlled hidden-surface and moving-object scenes.
- **Result:** pending.


## 2026-09-02 / D-004 — build the environment before believing any number

- **Decision:** Treat "a clean machine reaches a passing test suite" as the gate
  that must close before any accuracy work, and pin the stack in
  [`ENVIRONMENT.md`](ENVIRONMENT.md).
- **Problem and evidence:** the audit could not execute a single test: system
  Python is 3.14, which has no OpenCV wheel, and pytest was absent. Existing
  tests were therefore "useful code" rather than evidence of anything.
- **Alternatives considered:** trust the committed quality reports; test only the
  modules that do not import OpenCV.
- **Why this option:** an unverifiable environment makes every downstream number
  unfalsifiable. It also turned out to be cheap — one `uv venv --python 3.12`.
- **Expected measurable effect:** the suite becomes a regression signal.
- **Result:** **32/32 pre-existing tests pass, unmodified.** The audit's "tests
  could not be executed" was a missing environment, not broken code. Suite now
  40/40 with the bundle-adjustment tests added.
- **Artifacts:** `docs/ENVIRONMENT.md`.

## 2026-09-02 / D-005 — correction: the real imagery is not in this checkout

- **Decision:** Record that no real-data scorecard can be produced here yet, and
  run the truth harness on procedurally generated scenes in the meantime.
- **Problem and evidence:** the audit read the Bellus dataset as present. It is
  not: `git-lfs` is not installed and **128 of 130 tracked binary files are
  ~130-byte LFS pointer stubs**, including all 123 Bellus images, the synthetic
  fixture video, and every committed `cloud.npz` / `mesh.glb` / `.ply`. Only the
  two `point_cloud.las` files are real.
- **Why this matters:** the roadmap's phase 1 ("run the bundled Bellus imagery
  first") cannot start in this checkout. Treating a pointer file as a dataset
  would have produced a scorecard for 123 unreadable files.
- **Alternatives considered:** wait for `git lfs pull` before any measurement.
- **Why this option:** `drishti_recon.synth` renders a scene with *exactly*
  known geometry at run time, so a controlled benchmark needs no download. It
  cannot replace real imagery, and the benchmark doc says so explicitly.
- **Result:** synthetic matrix operational; Bellus row remains an open gap, one
  `git lfs pull` away from running through the existing ODM adapter.

## 2026-09-02 / D-006 — a benchmark, not a demo run

- **Decision:** Every accuracy claim must be generated by `eval/benchmark.py`,
  which runs variants x capture regimes x seeds and reports **median and worst**
  case per cell, with failures counted rather than dropped.
- **Problem and evidence:** the repository's headline came from one synthetic
  self-test (ATE 0.169 m, scale error 0.36%). Running the same code across four
  capture regimes immediately produced 11–13 m ATE, 71% scale error, 66%
  registration and one total failure — behaviour a single run cannot reveal.
- **Alternatives considered:** more seeds of the existing single trajectory;
  reporting the mean instead of the tail.
- **Why this option:** flight geometry, not the algorithm, usually decides
  whether a scene is reconstructable. A benchmark that varies only noise measures
  the wrong thing.
- **Risks / reversibility:** synthetic renders are noise-free apart from GNSS, so
  the numbers are an upper bound on field performance. Documented as such.
- **Validation:** cells run in isolated subprocesses so one crash cannot destroy
  the matrix and peak RSS is per-cell; provenance records commit, dirty flag,
  `pip freeze` and input SHA-256s.
- **Artifacts:** `eval/benchmark.py`, `eval/variants.py`, `eval/_bench_worker.py`,
  `docs/BENCHMARK.md`.

## 2026-09-02 / D-007 — bundle adjustment is adopted; it is not a failure fix

- **Decision:** Enable sparse bundle adjustment by default in the OpenCV engine,
  with an analytic Jacobian, and stop treating it as the answer to reconstruction
  failures.
- **Problem and evidence:** the engine never jointly minimised reprojection
  residuals, so incremental error accumulated as drift. Measured over 24 cells
  (4 regimes x 3 seeds x 2 variants): median ATE 1.697 m → **0.011 m**, worst-case
  metric scale error **0.7131 → 0.0198**, median dimensional error 5.53% → 2.31%,
  median reprojection 0.572 → 0.128 px.
- **Alternatives considered:** make PyCOLMAP the production path (packaging and
  runtime cost, and it would not have been measurable in this checkout); tune the
  incremental estimator instead.
- **Why this option:** it is the roadmap's P0, it is self-contained, and every
  independent metric moved together rather than one metric improving alone.
- **Risks / reversibility:** `bundle_adjust=False` reproduces the previous
  behaviour exactly, and the `baseline` benchmark variant keeps measuring it.
  Runtime cost was 3.4x, reduced to ~1.2x of that by the analytic Jacobian
  (2.9x speed-up, verified against SciPy's numerical derivative and reaching an
  identical optimum).
- **Validation:** 8 geometry-recovery tests against known truth plus 5 Jacobian
  tests; the 24-cell matrix archived under
  `docs/benchmarks/2026-09-02_baseline_vs_ba/`.
- **Result — and the part that matters most:** the **failure rate did not move**
  (3/12 in both arms). All three failures occur before BA runs. And on one cell
  (`ba/oblique_pass/seed1`) BA lowered reprojection while *degrading* the geometry
  — scale 1.735 → 2.915, triangulation angle 6.24° → 3.93°, completeness 12.4% →
  0.3% — because it converged to a wrong local minimum from a bad initialisation.
  **The accept-if-reprojection-drops guard cannot detect this**, which is exactly
  the roadmap's "do not accept only a lower training reprojection residual".
  Conclusion: initialisation and registration recovery (P1) now own both the
  failure rate and the worst tail, and are the next work.

## 2026-09-02 / D-008 — stated sensor uncertainty must change the answer

- **Decision:** Make GNSS accuracy, frame timing and post-alignment levelling
  affect (and be traceable in) the solution instead of being decorative.
- **Problem and evidence:** three independent correctness gaps, all silent —
  `robust_sim3` accepted `weights` and never read them; frame times assumed
  `frame_index/fps`, which a single dropped frame invalidates for the whole
  sequence; and gravity levelling rotated the deliverables *after* the GNSS fit
  without composing the rotation into the saved transform or recomputing the
  residual, so exported coordinates could not reproduce the published number.
- **Alternatives considered:** keep levelling but document the caveat; treat GNSS
  accuracy as a UI-only field.
- **Why this option:** each gap makes a reported number mean something other than
  what it appears to mean, which is the one failure mode this product cannot
  afford.
- **Expected measurable effect:** better alignment under mixed-quality GNSS;
  correct frame-to-GNSS association on variable-frame-rate video; every exported
  coordinate reproducible from a persisted transform.
- **Risks / reversibility:** the anisotropic refinement is discarded if it does
  not improve the fit; a PTS track that fails validation falls back to the
  nominal clock and says so; levelling is rejected if it would degrade the GNSS
  residual.
- **Validation:** the roadmap's own acceptance experiment — under heteroscedastic
  GNSS (30% of fixes degraded to 8 m), weighted alignment beats unweighted on
  clean held-out positions — plus degeneracy detection for collinear and planar
  tracks, and a regression test that stated accuracy changes the fitted scale.
- **Result:** implemented; suite 55/55. End-to-end effect on the matrix pending
  the re-run with the improved code.

## 2026-09-03 / D-009 — fix initialisation before optimisation

- **Decision:** Score the SfM seed pair on the geometry it can deliver (parallax,
  cheirality, spread, homography rejection), propose pairs at geometric strides,
  and register frames next-best-view with retry.
- **Problem and evidence:** the seed pair was chosen by **inlier count**, which is
  maximised by the *smallest* baseline — adjacent frames match almost perfectly and
  triangulate at ~1 degree. The pair graph contained only `(i,i+1)`, `(i,i+2)` and
  GNSS *nearest* neighbours, so no well-conditioned pair existed anywhere.
- **Expected measurable effect:** fewer hard failures, lower tail error.
- **Result:** `oblique_pass` went from 11.3 m / 13.1 m / total-failure to
  0.069 / 0.011 / 0.020 m **with bundle adjustment disabled**. `nadir_grid`
  registration went 66.7% -> **100% on every seed tested (6/6)**.
- **Also found, in my own new code:** the candidate pre-filter ranked pairs by
  inlier count and truncated to 40 — reselecting exactly the zero-parallax pairs
  the scorer exists to reject. The first two fixes were correct and produced no
  improvement until this was traced. Lesson recorded: trace the actual selection,
  do not re-reason about the design.

## 2026-09-03 / D-010 — bundle adjustment is no longer clearly worth its cost

- **Decision:** Keep `bundle_adjust=True` as the default **for now**, and record
  that the evidence no longer supports it as obviously correct.
- **Problem and evidence:** with initialisation fixed, over 24 cells BA improves
  ATE ~25x (median 0.0693 -> 0.0028 m) but leaves **metric scale error identical**,
  shows **no measurable gain in dimensional error or completeness** (2.49% -> 2.87%
  and 0.712 -> 0.661, both within seed spread), and costs **4.1x runtime**
  (98 s -> 405 s median).
- **Why the earlier conclusion changed:** BA's large win in the previous matrix was
  substantially it repairing damage caused by a bad initialiser. With D-009 in
  place that damage no longer occurs, so BA's marginal value is much smaller.
- **Alternatives considered:** flip the default to off (saves 4x compute); keep it
  on unconditionally.
- **Why this option:** dimensional error and completeness are the product's
  deliverables and BA does not improve them; but the exported camera trajectory is
  also a deliverable and BA improves it 25x. Flipping the default changes output
  for anyone consuming trajectories, so it is a product decision to be made
  deliberately, not a side effect of a benchmark run.
- **Validation:** `docs/benchmarks/2026-09-03_p1_baseline_vs_ba/`. The `baseline`
  variant measures the BA-off path on every run, so the decision stays evidence-backed.

## 2026-09-03 / D-011 — a point must pass its own gate at ship time

- **Decision:** Remove points from the reconstruction when they fail cheirality,
  `max_reproj` or `min_tri_angle` on re-triangulation, rather than leaving the
  previous pass's value in place.
- **Problem and evidence:** `_retriangulate` used `continue` on failure, so a point
  triangulated early — when few cameras were registered — could ship in the final
  cloud carrying reprojection error and triangulation angle measured against older
  poses, while failing the current gates. Both values feed the published per-point
  confidence.
- **Why this matters here specifically:** the product's central claim is that every
  point is verified and carries honest statistics. A point that would be rejected
  if re-checked must not ship with a stale score.
- **Risks:** removes points, so completeness can fall. Measured: point counts fell
  0.3-10%, oblique/orbit results bit-identical, and where anything changed
  dimensional error *improved* (`nadir_grid/s2` 5.16% -> 2.51%).
- **Result:** adopted, together with a frame->tracks reverse index that removed an
  O(frames^2 x points) scan (~10% end-to-end).

## 2026-09-03 / D-012 — three seeds is not enough for a degenerate regime

- **Decision:** Require >= 6 seeds for `nadir_grid` claims, and prefer dimensional
  error over ATE as the headline metric for planar/nadir captures.
- **Problem and evidence:** I reported `nadir_grid/s0` ATE improving 2.312 -> 0.178 m
  as evidence the initialiser helped. Across six seeds under identical code, ATE
  ranges **0.170-2.405 m** (14x). That single-cell comparison was entirely inside the
  spread and should not have been quoted.
- **What is defensible for that regime:** registration 66.7% -> 100%, with **zero**
  spread across six seeds.
- **The underlying insight:** in a near-planar nadir capture the camera trajectory is
  weakly constrained (planar degeneracy), so ATE swings wildly while the surface
  stays stable — dimensional error spread only 1.4 points, completeness 0.12. ATE is
  a poor proxy for measurement quality there.
- **Result:** `docs/BENCHMARK.md` updated with the seed-count rule.

## 2026-09-03 / D-013 — measurement uncertainty is propagated and conformally calibrated

- **Decision:** Replace the unitless heuristic confidence with a propagated
  covariance per point, carried through to each measurement, and calibrate the
  resulting intervals with distribution-free (conformal) quantiles rather than a
  Gaussian multiplier.
- **Problem and evidence:** the shipped confidence had no empirical meaning —
  nothing tied a score of 0.8 to any distance. This is D-002 from the original
  audit.
- **Alternatives considered:** tune the heuristic weights; report a single global
  accuracy figure; scale a Gaussian sigma.
- **Why this option:** a Gaussian rescale fixed the median but left 95% coverage
  at 0.694, because systematic error gives the residual distribution a heavier
  tail than a normal. Conformal quantiles make no distributional assumption and
  hit every level.
- **Expected measurable effect:** intervals achieve stated coverage on withheld
  measurements.
- **Result:** leave-one-out coverage **0.528 / 0.833 / 0.972** against nominal
  0.50 / 0.80 / 0.95 (n = 36). Acceptance criterion met.
- **Two bugs found by the experiment:** `sigma_px` was assumed at 0.5 px against
  actual residuals of 0.03-0.2 px (now estimated from the data); and a units error
  in my own `scale_sigma` reported 10.2% scale uncertainty on a fit good to 0.2%,
  swamping every measurement. My first hypothesis for the discrepancy was wrong,
  and only measuring the components found the real causes.
- **Risks / limits:** n = 36, all synthetic; the 95% conformal factor (k = 11.2)
  is driven by a handful of cases. Calibration factors are reported, never applied
  silently. Pose uncertainty is still unmodelled.
- **Artifacts:** `reconstruction/drishti_recon/uncertainty.py`,
  `eval/calibrate_uncertainty.py`, `tests/test_uncertainty.py` (17 tests),
  `docs/benchmarks/2026-09-03_uncertainty_calibration/`.

## 2026-09-03 / D-014 — unestablished space is a spatial layer, not a point label

- **Decision:** Represent unseen, occluded and weakly-supported regions as a
  voxel coverage field (`coverage.py`), and gate measurement on it, instead of
  expecting absent points to carry `UNOBSERVED` / `DYNAMIC_EXCLUDED` labels.
- **Problem and evidence:** both committed reports show zero points in those two
  classes. By construction a missing or masked observation creates no point, so
  the legend described something the data model could never produce. This is
  D-003 from the original audit, now implemented.
- **Why this option:** it states exactly what the camera rays did and did not
  establish, without hallucinating a surface, and it distinguishes *verified
  free space* from *never looked at* — a distinction a point cloud cannot carry.
- **Result:** on a controlled hidden-wall scene the occluded wall is < 20%
  measurable while the visible wall is > 50%; single-view surface is classified
  WEAK and refused. On real reconstructions, 51% (nadir) and 37% (orbit) of scene
  volume is explained, with 96-99% of found surface measurable.
- **Three bugs found building it:** sight lines slipping between sparse points in
  the z-buffer (fixed by conservative dilation); an incidence "proxy" that scored
  face-on views as grazing (replaced with real PCA normals); and camera rotations
  not transformed through the GNSS similarity, which made an entire scene read as
  UNSEEN while unit tests stayed green. The last was only caught by running end
  to end -- a reminder that unit tests which construct their own inputs cannot
  catch a frame-convention error in the integration.
- **Risks / limits:** occlusion is inferred from the *reconstructed* cloud, so a
  surface that failed to reconstruct cannot occlude anything and the space behind
  it may read as EMPTY. Dynamic-object masking is not yet folded into the layer.

## 2026-09-03 / D-015 — close out the sensor model

- **Decision:** Implement camera-to-GNSS time-offset estimation, lever-arm
  correction, rolling-shutter detection and a lens-distortion input path
  (`sensors.py`), completing roadmap phase 3.
- **Problem and evidence:** verified by grep, not assumption — `synchronize()`
  took an `offset` argument that nothing estimated, and lever arm / boresight /
  rolling shutter existed only in comments. Each biases georegistration in a way
  no later stage can detect, because the output stays self-consistent.
- **Why these choices:**
  - time offset from *speed* cross-correlation, because speed is invariant to the
    unknown Sim(3) and so works before georegistration;
  - distortion corrected once up front, because threading coefficients through
    triangulation/PnP/BA/uncertainty would need four distortion-aware variants and
    a missed one fails silently;
  - rolling shutter **detected, not corrected** — RS bundle adjustment is a much
    larger change, and flagging a violated assumption beats a quietly degraded
    number.
- **Result:** known offsets recovered to <0.06 s and invariant to a 17x scale and
  rotation; lever arm verified to rotate correctly with heading and to refuse
  without attitude; rolling shutter graded by severity.
- **Bug introduced and caught end-to-end:** the estimator confidently returned
  +1.8 s on a 2-second fixture, collapsing alignment scale to 0.0064 and the cloud
  to 12 points, while all 19 unit tests passed. Fixed by clamping the search to a
  fraction of the clip, requiring substantial profile overlap, and rejecting
  edge-pinned peaks. Regression-tested.
- **Still not done:** IMU/camera boresight calibration, and rolling-shutter-aware
  bundle adjustment. Both are larger than the items above and are not required by
  phase 3's exit criterion.

## 2026-09-04 / D-016 — learned matching measured, and declined

- **Decision:** Add a pluggable feature-backend adapter with a LightGlue+DISK
  implementation, benchmark it against SIFT, and **keep SIFT as the default**.
- **Problem and evidence:** roadmap phase 5 requires a learned matcher be compared
  on the identical pair graph and adopted "only where downstream geometry
  improves". Measured over 6 cells: median ATE 0.062 -> 0.171 m (2.8x worse),
  median dimensional error 2.22% -> 3.11%, 30-60% fewer points, and slower
  end-to-end despite GPU execution. Completeness improved marginally
  (0.624 -> 0.643), which does not carry the rest.
- **Licensing:** LightGlue code is Apache-2.0 but SuperPoint's weights are
  MagicLeap non-commercial. The backend defaults to DISK (Apache-2.0) / ALIKED
  (BSD-3) and refuses SuperPoint unless explicitly allowed; the licence is
  recorded in each run's provenance. This removes the decision that was
  previously blocking phase 5.
- **Why decline rather than tune:** the benchmark rule is that a model earns
  inclusion. It did not, so it stays available and unselected. `matcher="sift"`
  is unchanged and the SIFT path is asserted byte-identical to the original.
- **The limit of this verdict:** it is synthetic-only, and this is the ablation
  most damaged by that. The fixture's procedural high-frequency texture suits SIFT
  and is unlike DISK's training distribution, and every condition learned matching
  exists for -- illumination change, repetitive structure, appearance change,
  blur, compression -- is absent. Read as "not adopted on this benchmark", **not**
  "learned matching does not help". Re-run it first once real imagery lands.
- **Artifacts:** `reconstruction/drishti_recon/features.py`,
  `tests/test_features.py` (13 tests),
  `docs/benchmarks/2026-09-04_matcher_ablation/`.

## 2026-09-04 / D-017 — inferred geometry can be corroborated, never promoted to measured

- **Decision:** Verify depth-prior points against independent views and mark those
  that agree as `AI_GEOMETRICALLY_VERIFIED`, a class that remains **excluded from
  measurement**.
- **Problem and evidence:** the depth path merged every inferred point, each
  supported by one view and one model prediction. A single-view guess cannot be
  falsified, so nothing distinguished a plausible inference from a wrong one.
- **Why not make verified points measurable:** the project's rule is that
  measurement requires multi-view *observational* support. Agreement with a
  z-buffer is corroboration, not triangulation. Promoting it would be exactly the
  failure the provenance model exists to prevent.
- **Result:** on a controlled scene, inferred points on the true surface verify at
  >80% while identical-looking points floating 8 m above it verify at <20%.
- **Artifacts:** `verify.py`, `tests/test_verify_capture.py`.

## 2026-09-04 / D-018 — the system should say what the flight was capable of

- **Decision:** Add a capture assessment and recapture planner (`capture.py`)
  reporting a grade, the limiting factor, achievable sigma, whether a stated
  accuracy requirement is reachable, and what to refly.
- **Why explicit factors rather than a model:** a score a report cannot explain is
  not actionable. Each factor is a quantity already measured, so the output names
  the binding constraint. Unmeasured factors are renormalised out, never scored 0.
- **Result:** `orbit_s0` grades excellent (0.90) with no advice; `low_parallax_s2`
  grades marginal (0.49), correctly identifies registration and parallax as the
  constraints, and emits 5 recapture waypoints. The requirement gate passes a
  0.10 m target and fails a 0.02 m one against a measured 0.0405 m.
- **Bug found by its own test:** advice keyed off `limiting_factor`, which always
  exists, so a perfect capture was told to refly. Now triggered only by genuine
  deficiency.

## 2026-09-04 / D-019 — dynamic exclusion is a property of space

- **Decision:** Represent masked (dynamic) observations as a `DYNAMIC_EXCLUDED`
  class in the coverage field, closing the gap left open by D-003.
- **Problem and evidence:** the audit found zero `DYNAMIC_EXCLUDED` points. A
  masked pixel produces no point, so the point cloud could never express it.
- **Why it matters:** a cell seen only through discarded observations is neither
  established geometry nor unexplored volume, and conflating it with either
  misstates what the flight achieved. Masking now also visibly reduces measurable
  surface instead of passing unnoticed.

## 2026-09-04 / D-020 — real data overturns the learned-matching decision

- **Decision:** Supersede D-016 for real captures. LightGlue+DISK yields 10-20x
  more geometrically verified correspondences than SIFT on real aerial imagery
  (278-729 inliers per consecutive pair against SIFT's 14-50).
- **Why the earlier verdict was wrong:** it was measured only on synthetic scenes
  whose procedural high-frequency texture is close to ideal for SIFT and unlike
  DISK's training distribution. D-016 recorded that caveat explicitly and said to
  re-run on real imagery first; doing so reversed the result.
- **What this says about method, not just matching:** a synthetic benchmark can
  be rigorous, reproducible, well-controlled -- and still point the wrong way.
  The benchmark discipline was worth building, but it does not substitute for real
  data, and a conclusion drawn only from synthetic input should carry that label.
- **Not yet done:** the default remains `matcher="sift"`, because a full ablation
  on real data (registration, dimensional error, runtime) has not been run -- only
  pairwise inlier counts. Adoption still has to be earned on downstream geometry.

## 2026-09-04 / D-021 — three real-data defects invisible to synthetic input

- **Decision:** Read intrinsics from EXIF; weight seed pairs by graph
  connectivity; measure inter-frame displacement with phase correlation instead of
  Farneback optical flow.
- **Evidence, in order of discovery:**
  1. Intrinsics were guessed at `0.9*max(w,h)` = 3643 px against a true ~2800 px
     (30% error). Synthetic fixtures always supplied exact intrinsics, so this path
     had never been exercised.
  2. The seed-pair scorer picked a pair with 19.6 deg parallax and 330 inliers that
     was topologically isolated, registering 2 cameras of 61. Synthetic sequential
     video is uniformly connected, so an island could not occur there.
  3. **Farneback under-reported a ~570 px displacement as 2.1 px** (27x), because
     it is a small-motion estimator. The keyframe selector read that as
     "near-duplicate frames" and thinned a capture with no overlap to spare:
     consecutive frames give ~363 inliers and 5339 tracks, every-second-frame gives
     **zero verified pairs**.
- **Result:** 13/61 -> 20/122 registered and 1,396 -> 5,169 points. Still a failure
  at 16%; registration remains the limiting factor and tracks reach only length 4.
- **The general lesson:** all three bugs live in code paths that synthetic data
  never exercised -- estimated intrinsics, non-sequential capture topology, and
  large inter-frame motion. Coverage of *code* was never the issue; coverage of
  *input conditions* was.

## 2026-09-04 / D-022 — bound the pair graph, and cap heavy runs by cgroup

- **Decision:** Cap the GNSS-proximity radius at 2.5 flight steps with <=10
  neighbours per frame and a hard ceiling on total pairs; bound the rotation
  cache; run heavy jobs under a cgroup memory limit.
- **Problem and evidence:** the previous radius of `8 x median step` proposed
  7,298 of 7,381 possible pairs on the real survey. Combined with a 3-rotation
  retry per failing pair and an unbounded descriptor cache, this exhausted memory
  and **took the desktop session down**.
- **Result:** 7,298 -> 1,291 pairs while retaining 89% of genuinely overlapping
  pairs. The discarded pairs were nearly all non-overlapping.
- **Why cgroup, not RLIMIT_AS:** address-space limits break CUDA, which reserves
  tens of GB of virtual address space, and broke video encoding here before
  reconstruction began. `systemd-run --user --scope -p MemoryMax=` limits
  resident memory, so a runaway job dies instead of the desktop.
- **Regression caught:** enabling rotation retry for SIFT took the dataset from
  13 registered cameras to 0, because SIFT is already rotation invariant and the
  appended near-duplicate features fragment tracks. Retry is now gated to learned
  backends.
- **Open:** LightGlue does not complete on 122 frames within 8 GB. Its pairwise
  advantage (10-20x inliers) is measured and real; end-to-end usability at survey
  scale is not yet demonstrated.

## 2026-09-05 / D-023 — the real-data bottleneck was memory, not hardware

- **Decision:** Halve `max_keypoints` to 2048 for the learned matcher and keep
  rotation-robust pairing; adopt LightGlue for real aerial captures.
- **Evidence:** 45/122 -> **99/122** cameras and 2,440 -> **31,991** points on the
  real Bellus survey, at 4,052 MB peak. The prior OOM was against a cgroup cap on
  *system* RAM; GPU memory was at 4% utilisation throughout, so more VRAM would
  not have helped.
- **Note on D-016/D-020:** learned matching is now demonstrated end-to-end on real
  data, not just pairwise. The synthetic-only verdict declining it (D-016) should
  be treated as superseded for real captures.

## 2026-09-05 / D-024 — canonical per-frame orientation: right idea, wrong propagation

- **Decision:** Keep per-pair rotation retry as the default; ship canonical
  per-frame orientation as opt-in, off.
- **Problem:** the retry appends a second descriptor set per frame, so one
  physical point can become two tracks -- a plausible cause of mean track length
  stalling at 2.37 despite ~400 inliers per pair.
- **What was measured:** assigning one canonical orientation per frame gave
  **7/122 cameras** against 99/122. Propagating along the sequential chain is
  fragile: at a strip turn consecutive frames barely overlap, and one wrong link
  corrupts everything downstream.
- **Why it is still the right idea:** those 7 cameras georegistered to **3.53 m
  (6/7 inliers)**, the best on this dataset, against 13.12 m for the 99-camera
  model. One descriptor set per frame does appear to buy accuracy.
- **Next:** propagate orientation over a spanning tree of the strongest pairs, or
  seed from GPS-adjacent neighbours, rather than capture order.

## 2026-09-05 / D-025 — the georegistration residual is the model, not the GPS

- **Finding:** 13.12 m alignment residual is a reconstruction defect, established
  by three independent measurements: GPS cross-track scatter about straight
  flight strips is only **2.11 m median / 5.38 m p90**; the residual does not grow
  along the sequence (so not drift); and refitting on the best 25% of cameras
  still leaves 7.86 m with scale 0.99 (so not a displaced block or scale error).
- **Consequence:** dense MVS must wait. It inherits pose error, so densifying now
  would produce far more points in the same wrong places.
- **The number to attack:** mean track length 2.37.

## 2026-09-05 / D-026 — orientation by maximum spanning tree, not capture order

- **Decision:** Assign one canonical orientation per frame for rotation-sensitive
  backends, propagated over a maximum spanning tree of verified pairs weighted by
  inlier count. Enabled by default for learned matchers.
- **Evidence:** 105/122 cameras registered (best measured), mean track length
  2.37 -> 2.54, GNSS inlier ratio 52% -> 53%, and only 5 frames left unanchored.
  Sequential propagation of the same idea gave 7/122.
- **Bug found in my own first implementation:** a single descending-weight pass
  dropped every edge whose two endpoints were both unanchored at that instant and
  never revisited it, leaving 68/122 frames unanchored. Fixed with a fixpoint loop
  plus component seeding.
- **Trade-off accepted:** fewer points than the append approach (18,409 vs 31,991)
  because duplicate feature sets no longer create duplicate tracks. More cameras
  and longer tracks is the better base for georegistration.

## 2026-09-05 / D-027 — the next constraint is pair verification rate

- **Finding:** only **243 of 1,291 proposed pairs verify** (19%). Tracks cannot
  chain through pairs that never verified, which caps mean track length at ~2.5,
  which leaves most camera positions weakly determined, which is why 94 of 105
  cameras fail a tight GNSS fit while 11 agree to 3.3 m horizontal.
- **Consequence:** georegistration cannot be fixed downstream. It is not the GNSS
  (2.11 m measured scatter), not drift, not scale, and not solved by bundle
  adjustment. It is a structure problem.
- **Next work:** propose pairs by predicted ground overlap rather than index
  stride, and diagnose why genuinely overlapping pairs still fail verification.
- **Dense MVS remains blocked** behind this: it inherits pose error.

## 2026-09-05 / D-028 — quality metrics are scored on observed geometry only

- **Decision:** Compute surface accuracy, completeness and dimensional error over
  OBSERVED points only; report the inferred layer's contribution separately and
  label it coverage, not accuracy. Dimensional measurement no longer passes
  `allow_inferred=True`.
- **Evidence:** with densification on, surface accuracy read 1.847 m over the full
  cloud against **0.835 m over observed geometry** -- densification appeared to be
  an accuracy regression while the measured cloud was untouched. And the headline
  dimensional number was free to snap to AI-generated surface, which is exactly
  the failure the provenance model exists to prevent.

## 2026-09-05 / D-029 — two of my own optimisations reverted after measurement

- **Decision:** Disable the separation-based pair prune by default and revert
  `max_gps_neighbours` to 10.
- **Evidence:** the prune deleted 86% of cross-strip pairs on real data and 100%
  on synthetic nadir (found by a review agent), and on the **target single-pass
  regime** it deleted the wide-baseline stride pairs that create parallax --
  ATE 0.020 -> 0.102 m and 0.074 -> 0.309 m. Raising neighbours 10 -> 14
  independently degraded orbit ATE 0.041 -> 0.237 m.
- **Lesson:** both changes were justified by a measurement on *one* dataset
  (Bellus pair counts) and shipped without re-measuring the regime the product
  actually targets. A graph metric ("more useful pairs") is not a product metric.
- **Also:** a proposed fix to loosen the epipolar band to 3 px collapsed the
  synthetic reconstruction to zero points -- absence of EXIF distortion
  coefficients does not imply a distorted lens. Now an explicit opt-in.

## 2026-09-10 / D-030 — pose graph optimizer: own scipy implementation, not GTSAM/g2o

**Context.** The Intelligence Edition architecture (§7) calls for pose graph
optimization via GTSAM or g2o to correct bowed single-pass trajectories — the
exact failure measured on AGZ (26.7 m at the ends, 3.2 m mid-sequence).

**Decision.** Implement PGO in-repo on `scipy.optimize.least_squares`.

**Why.** `pip install gtsam` force-downgrades numpy 2.5.2 → 1.26.4 — changing
the numeric foundation every benchmark was validated on, which the benchmark
contract forbids. `g2o-python` fails to build in this environment. Our graphs
are small (≤ a few hundred nodes); `bundle.py` already contains the analytic
SE(3) machinery; scipy's sparse trust-region solver handles this class of
problem directly. The document's intent — a global relative-pose + GPS-prior
fusion stage — is honored by an equivalent implementation.

## 2026-09-10 / D-031 — Kalman smoothing helps jitter, not bias; sigmas must not lie

**Context.** Intelligence Edition §8 calls for a Kalman filter on raw telemetry.
Implemented as a constant-velocity RTS smoother (`telemetry.kalman_smooth`).

**Measurement.** On the AGZ surveyed segment the smoother left the GPS error
unchanged (5.39 → 5.41 m median 3D): that receiver's error is slowly-varying
bias, which a smoother cannot see. Worse, the filter's posterior sigma came out
at 1.74 m while the true error stayed 5.4 m — trusting it would inject
overconfident priors into the pose graph.

**Decision.** The smoother is used for jitter removal and gap handling only.
Downstream consumers must apply a receiver bias floor to its posterior sigma
(default: the raw receiver sigma unless independent evidence justifies less).
This also settles expectations for absolute accuracy: with GPS bias common-mode
across a pass, no GPS-anchored solve can beat the bias floor (~3 m horizontal
here). Vertical is less biased, which is why the reconstruction's averaging
beats GPS 2.4x there. The doc's absolute-vs-relative accuracy distinction (§8)
is measured reality, not a caveat.

## 2026-09-10 / D-032 — a published accuracy number was measuring the truth cloud's sparsity

**Context.** Building the trust score (doc §20) required a per-point error
target. The obvious one — nearest-neighbour distance to `scene_points_enu` —
produced a calibration that ranked points at Spearman 0.087, i.e. no ranking
power, with the weight sweep collapsing onto a single corner of the simplex.

**Investigation.** The synthetic truth cloud is 3,750 points over a 60x60x9 m
scene. Its own nearest-neighbour self-spacing is **0.33 m median, 2.50 m at
p90**. A perfectly reconstructed point landing between two truth samples is
therefore scored as ~1 m wrong. 30 % of measured "errors" fell below that
sampling floor.

The scene is six planar rectangles and is exactly known, so
`synth.surface_distance` computes true point-to-surface distance. On identical
points: **sampled-NN 0.782 m median, analytic 0.020 m** — a factor of 39. The
two metrics rank the same points at only rho = 0.20, so they were not noisy
versions of each other; they were measuring different things.

**Scope.** This was not confined to the trust work. `eval/metrics.py` scored
`cloud_acc_median` the same way, so the synthetic cloud-accuracy figures
published in BENCHMARK.md were floored by truth sampling, not by our
reconstruction. Corrected, per regime: oblique_pass 0.809 -> 0.084 m, orbit
0.675 -> 0.054 m, nadir_grid 0.911 -> 0.022 m.

**Decision.** `EvalCase` gains `gt_surface_distance`; metrics prefer it for
accuracy when present and fall back to sampled-NN otherwise, recording which
was used in `cloud_acc_source` so numbers from the two sources are never
silently compared. Completeness keeps the sampled cloud — it asks the opposite
question ("is there a reconstructed point near each truth point"), which a
sample answers soundly.

**Rule.** An error metric must be validated against its own resolution floor
before any claim rests on it. The check is cheap: compare the truth
representation's internal spacing against the errors being reported. If they
are the same order, the metric is reporting itself.

## 2026-09-10 / D-033 — the trust score's terms are correlated; weights are not importances

**Context.** Doc §20 specifies C = w1*O + w2*N + w3*(1-E) + w4*P with weights
"calibrated experimentally". Two failures had to be fixed before calibration
meant anything.

**Saturation.** The first implementation used plausible constants — 6 views,
2 px, 10 degrees. The pipeline's actual distribution is 11 views median,
0.09 px median, 17 deg median, so O and P were pinned at 1.0 for over half the
points and contributed nothing at all. `fit_normalisation` now derives the
constants from the data's own quantiles. Fitted: 50 views, 0.30 px, 59.5 deg.

**Confounding.** Measured on oblique_pass with the corrected error target:

| term | marginal rho | partial rho |
|---|---|---|
| `tri_angle` | -0.600 | -0.373 (controlling obs) |
| `obs_count` | -0.510 | **+0.044** (controlling parallax) |
| `reproj_err` | **-0.078** (wrong sign) | +0.126 (controlling obs), +0.226 (controlling parallax) |

`obs_count` correlates with `tri_angle` at rho = 0.88 and carries essentially
no independent information. `reproj_err` appears to have the *wrong* sign
marginally only because points with many views accumulate more total residual
while being more accurate; within every track-length band it is correctly
positive.

**Result.** Spearman 0.087 -> **0.625**; median error falls monotonically
across all ten trust deciles, 0.101 m -> 0.0061 m (16.6x). Calibrated effective
weights O/N/E/P = 0 / 0 / 0.222 / 0.778 — O's zero is the expected consequence
of its redundancy with P, not a bug.

**Rule.** Weights fitted over correlated inputs rank well but are not per-term
importances, and the module says so. Reporting them as importances would invite
the conclusion that observation count does not matter, which is false — it is
simply already counted through parallax.

## 2026-09-10 / D-034 — dynamic masking uses Mask R-CNN, not YOLOv8-Seg/FastSAM

**Context.** The architecture document (stage 2) names YOLOv8-Seg or FastSAM
for dynamic-object masking.

**Decision.** Implement on torchvision's Mask R-CNN instead, accepting `yolo`
and `fastsam` as aliases that resolve to it with a recorded notice.

**Why.** Both named models are Ultralytics, licensed **AGPL-3.0** — network
copyleft that would propagate to this entire codebase on distribution. This
project already refuses SuperPoint over a non-commercial clause
(`features.py`), and AGPL is the stronger constraint, so the same rule applies
rather than a weaker one. torchvision's Mask R-CNN is BSD-3, ships
COCO-pretrained weights, and covers every dynamic class the document lists:
person, bicycle, car, motorcycle, bus, train, truck, boat and ten animal
classes.

Instance segmentation is also the better fit than semantic segmentation:
per-object masks carry per-object scores, so a confidence threshold is
meaningful and one uncertain detection cannot mask an entire class of pixels.

**Also fixed here.** `TorchvisionSemanticMask` reported itself available
whenever torch imported, while constructing its network with `weights=None` —
randomly initialised — and returning an argmax over random logits. Masking runs
*before* matching, so those random masks deleted real image content from the
reconstruction: a silent, destructive failure rather than a merely useless one.
It now reports unavailable without usable weights and raises rather than
running untrained.

## 2026-09-10 / D-035 — an area cap on dynamic instances, measured not guessed

**Context.** Running Mask R-CNN over the repository's real drone footage, one
`gym_pass` frame came back **48.7 % masked**. The cause: the school's flat
gravel roof detected as a **"train" at score 0.74**, covering 46.8 % of the
frame. A COCO detector has never seen a building from above; large elongated
static structures land confidently on `train` and `boat`.

Because masking precedes matching, this deletes the primary structure the
reconstruction exists to recover — and does so without any error.

**Measurement.** Over 322 dynamic-class instances across all real footage in
the repo:

| | area, fraction of frame |
|---|---|
| genuine objects, p50 | 0.13 % |
| genuine objects, p90 | 0.52 % |
| p95 | 5.74 % (already contaminated) |
| max | 46.8 % |

**Every instance above 5 % of frame was a `train` (10) or `boat` (8)** — all
hallucinated on roofs and facades. Genuine classes (car 154, person 76,
truck 15, motorcycle 3, bicycle 1) stay small because a drone views them from
tens of metres away.

**Decision.** Reject any single instance covering more than **2 %** of the
frame. That sits an order of magnitude above real objects and an order below
the false positives. The cap is per-instance, not cumulative: many small
objects may legitimately sum past it.

**Effect on `gym_pass` (64 frames):** maximum masked fraction 48.7 % → 3.7 %;
frames masking more than 10 % of the image 13 → 0; 22 oversized instances
rejected; frames retaining a genuine mask 50 → 48. Median masked fraction
barely moves (0.85 % → 0.53 %), so real detections survive.

**Limitation, recorded not hidden.** Detection needs the object to be resolved:
measured object size is 30 px (sqrt of mask area) median at low oblique
altitude, dropping to 14 px on the survey-altitude road corridor, where the
detector finds essentially nothing. Above roughly survey altitude this backend
should be assumed ineffective, and the optical-flow residual backend — which
keys on motion rather than appearance — is the appropriate choice.

## 2026-09-11 / D-036 — the GNSS bias floor bounds what any algorithm can do here

**Question.** Horizontal georeferencing loses to the drone's own GNSS (4.29 m
against 3.26 m). Is that worth attacking, and how far can it go?

**Measurement.** Decomposing the AGZ GNSS error over 184 frames:

- mean error vector `[0.25, -2.81, 1.09] m`, magnitude **3.02 m**
- **56 % of the total error is a constant offset**, not noise
- autocorrelation half-length 9-17 frames of 184 -- slowly varying, which is
  why the Kalman smoother could not touch it (D-031)

**Consequence.** A solve anchored only to this GNSS inherits its bias. The best
achievable horizontal is therefore ~3.19 m, and we were adding 1.10 m of our
own on top. That 1.10 m is the entire algorithmic headroom; going below 3.19 m
requires different information -- RTK, ground control, or registration against
a map or DEM -- not a better optimiser.

Height is different, and this explains why we beat the GNSS there: scene
structure -- the ground plane and building heights -- constrains height
independently of the GNSS, so the reconstruction is not limited by the bias.

## 2026-09-11 / D-037 — long-range edges help only when gated on the model's own fit

**Hypothesis.** The residual error is a low-frequency bow, so longer-baseline
pose-graph edges should constrain it directly.

**First result: strongly negative.** Extending offsets from (1,2,4,8) to
(1,2,4,8,16,32) made everything worse -- 3D 6.02 -> 13.93 m, horizontal
4.29 -> 13.78 m -- with cycle-consistency noise rising 15 %/2.1 deg to
28 %/4.4 deg.

**Cause.** Pairwise fit quality collapses with frame separation. Median
Procrustes residual by offset: 0.029, 0.036, 0.064, 0.213, 0.603, 0.489 at
1, 2, 4, 8, 16, 32. Frames 32 apart on a straight pass barely share a view, so
the model returns a confident-looking transform it never had the overlap to
solve.

**Second result: the distinction is *bad* edges, not *long* edges.** Gating on
the model's own Procrustes residual keeps the long edges that were genuinely
solved. Sweeping the gate as a multiple of the dataset's own short-edge
residual (so it transfers across captures):

| gate | 3D | horizontal | vertical |
|---|---|---|---|
| none | 6.02 | 4.29 | 1.10 |
| 2x | 5.87 | 3.78 | 1.11 |
| 3x | 5.71 | 3.24 | 1.94 |
| 4x | 5.90 | 3.10 | 1.75 |
| 6x | 5.66 | 3.86 | 1.46 |

**Decision: 2x, not the argmin.** 4x reaches 3.10 m horizontal -- at the bias
floor -- but gives back 59 % of the height advantage, which is the metric this
system actually beats the GNSS on and the one the problem statement asks for.
2x improves all three. The non-monotonic response across multipliers marks a
noisy objective tuned on one segment; a second surveyed segment should confirm
the threshold before it is trusted.

## 2026-09-11 / D-038 — the height advantage was one segment's bad GNSS, not a capability

**What was claimed.** On the AGZ surveyed segment the system measured height
2.4x more accurately than the drone's own GNSS (1.10 m against 2.68 m). That
was reported as the project's headline result.

**Validation on a second, non-overlapping segment of the same flight**
(imgid 64531-70021, 62 frames, same camera, same processing) overturns it:

| | segment 1 | segment 2 |
|---|---|---|
| **our** 3D / horiz / vert | 6.02 / 4.29 / 1.10 | 6.37 / 5.94 / 2.63 |
| **GNSS** 3D / horiz / vert | 5.52 / 3.26 / 2.68 | 1.91 / 1.33 / 1.36 |
| verdict, 3D | lose 1.1x | lose 3.3x |
| verdict, horizontal | lose 1.3x | lose 4.5x |
| verdict, **vertical** | **win 2.4x** | **lose 1.9x** |

**Reading.** Our absolute accuracy is stable -- 6.02 and 6.37 m 3D. What moved
was the GNSS: 5.52 m on one segment, 1.91 m on the other. Segment 1 simply had
unusually poor GNSS, and every "beats the GNSS" statement rested on that.

Segment 2 is not a harder case: it is *less* straight (7.2x elongation against
14.8x), which should favour reconstruction, and its altitude range is smaller.

**Honest position.** Absolute georeferencing is ~6 m 3D and **does not beat
consumer GNSS**. That is not a disaster -- it is the expected behaviour of
non-RTK photogrammetry anchored to a biased sensor (D-036) -- but it is not
what was claimed. What the measurements still support:

- *relative* geometry is sound: metric scale to ~1 % (1.12 m step against a
  surveyed 1.13 m), trajectory smoother than the GNSS it was anchored to
- 100 % frame registration on real single-pass video
- measurement refusal, coverage classification and calibrated uncertainty,
  none of which depend on absolute position

**Process failure, recorded.** This repository's own benchmark contract says
median *and* worst case are reported together, and that three seeds is not
enough for a regime with spread. A single segment was reported as a capability
anyway. The rule now extends explicitly to real data: **no real-data claim from
one capture segment.**

## 2026-09-11 / D-039 — the residual gate did not survive held-out validation

Swept on segment 1, gating long-range edges on the model's own Procrustes
residual looked like a clear win (horizontal 4.29 -> 3.78 m at 2x, D-037). On
segment 2 every setting was worse, monotonically: 5.94 m ungated against
6.99 / 7.80 / 9.27 at 2x / 3x / 4x.

Default reverted to off. The *mechanism* stands -- ungated long edges are
catastrophic, and per-edge residual is the right signal for telling a solved
pair from an unsolved one. What has no support is any particular threshold,
which was fitted to one stretch of flight.
