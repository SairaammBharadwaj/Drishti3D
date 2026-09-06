# Drishti3D repository audit and evidence-backed improvement roadmap

**Audit date:** 2 September 2026  
**Scope:** repository structure, reconstruction and georegistration code, committed
quality reports, tests, and relevant primary literature. This is a technical
assessment, not a claim that the system has already reached survey-grade accuracy.

## 1. Intended solution

Drishti3D is meant to turn a single drone-video pass plus telemetry into a
georeferenced, metrically scaled, measurable 3D scene. Its strongest product idea
is not merely reconstruction: it is an *evidence product* that separates observed,
low-confidence, inferred, dynamic, and unobserved geometry.

The repository is a modular monolith:

- `reconstruction/drishti_recon`: ingestion, synchronization, keyframes, masking,
  OpenCV SfM, optional COLMAP, GPS Sim(3), fusion, meshing, measurement and export.
- `backend`: FastAPI, SQLite, storage, job execution and artifact APIs.
- `frontend`: React/Three.js mission, monitoring, workspace and report UI.
- `eval`: loaders and metrics for synthetic, ODM, TartanAir, ETH3D and TUM layouts.
- `tests`: unit and small integration coverage.
- `sample_data`: deterministic synthetic input and two committed result sets.
- `odm_data_bellus-master`: a real, geotagged aerial-image dataset, not yet
  accompanied by a committed Drishti3D scorecard.

## 1a. Corrections to this audit (added 2 September 2026, after execution)

Two statements in the original audit were wrong once the code was actually run.
They are corrected here rather than silently edited, because the audit's own rule
is that a claim states its evidence.

| Original statement | Correction | Evidence |
|---|---|---|
| "Tests could not be executed in the current workspace... this audit cannot call them passing evidence." | The tests pass. All **32 pre-existing tests pass unmodified** in a Python 3.12 environment. The blocker was a missing environment (system Python 3.14 has no OpenCV wheel), not the code. | `docs/ENVIRONMENT.md`; suite now 40/40 with bundle-adjustment tests. |
| "Real aerial imagery exists locally, but no committed real-data evaluation report was found." | The imagery is **not present**. `git-lfs` is not installed and **128 of 130 tracked binary files are unfetched ~130-byte LFS pointer stubs**, including all 123 Bellus images, the synthetic fixture video and every committed `cloud.npz`/`mesh.glb`/`.ply`. Only the two `point_cloud.las` files are real. | `git ls-files` scan; see `docs/ENVIRONMENT.md`. |

The second correction changes phase 1 of the execution order: "run the bundled
Bellus imagery first" cannot begin in this checkout. It requires `git lfs pull`.
Until then the truth harness runs on procedurally generated synthetic scenes,
whose numbers are an upper bound on field performance rather than a prediction of
it. See `docs/BENCHMARK.md`.

A third item is confirmed and quantified rather than corrected: the audit warned
that "a best-case headline is not yet representative". Measured across four
capture regimes, the pipeline that reports 0.169 m ATE on its demo capture
produces 11-13 m ATE, a 71% scale error, 33% of frames unregistered, and one
total failure. See `docs/WORK_LOG.md` section 1.5.

## 2. What is proven today

The statements below are deliberately limited to evidence present in this checkout.

| Observation | Repository evidence | Consequence |
|---|---|---|
| The default engine performs real feature detection, essential-matrix pose recovery, DLT triangulation and PnP registration. | `sfm.py` | This is a genuine sparse SfM prototype, not a visual mock. |
| The default engine performs no local or global bundle adjustment. | `sfm.py` ends after repeated triangulation/PnP and cloud assembly. | Camera and point errors are not jointly minimized; this is the largest accuracy gap. |
| GPS alignment accepts `weights`, but does not use them in model selection or refitting. | `geo.robust_sim3()` receives `weights`; the function never reads the value. | Reported GPS-accuracy fields currently have no influence on the solution. |
| Camera distortion is not modeled by the OpenCV path. | `sfm.py` passes `None` distortion to essential/PnP operations; pipeline calibration contains only `fx,fy,cx,cy`. | Wide-angle lenses can create systematic shape and scale error. |
| The committed stronger synthetic run registers 29/29 frames and 10,819 fused points. | `sample_data/proj_none/artifacts/quality_report.json` | The pipeline can succeed on its controlled fixture. |
| That run has dimensional errors of 2.39%, 0.58%, and 3.49%, surface RMSE 1.66 m, and only 6.16% completeness at 0.5 m. | Same quality report. | Sparse measurements can be promising while the reconstructed surface remains very incomplete. |
| A second committed run registers 16/29 frames and reports 9.90%, 56.68%, and 33.86% dimensional error. | `sample_data/proj_demo/artifacts/quality_report.json` | Accuracy is configuration-sensitive; a best-case headline is not yet representative. |
| `UNOBSERVED` and `DYNAMIC_EXCLUDED` have zero points in both reports. | Both quality reports; masking removes observations before reconstruction. | Missing/excluded evidence is named, but is not yet represented spatially. |
| Real aerial imagery exists locally, but no committed real-data evaluation report was found. | `odm_data_bellus-master/.../images`; no real `eval_report.json` or `eval_scorecard.md`. | Generalization to real drone imagery remains unproven in this checkout. |
| Tests could not be executed in the current workspace. | System Python is 3.14.7 and lacks OpenCV and pytest. | Existing tests are useful code, but this audit cannot call them passing evidence. |

## 3. Accuracy blockers found in the implementation

### P0 — jointly optimize geometry and camera parameters

The current OpenCV engine estimates poses incrementally and retriangulates, but
never minimizes all reprojection residuals together. COLMAP's documented pipeline
uses incremental SfM and bundle adjustment; the VGGT paper also reports that BA
post-processing substantially improves its results. Implement Ceres/g2o or make
PyCOLMAP the production verified engine, with global BA after registration and
optional focal/distortion refinement.

**Acceptance experiment:** same fixed keyframes and matches, before-versus-after
BA. Require lower held-out reprojection error, no worse registration fraction,
and improvement on independent dimension/checkpoint error across at least three
seeds/sequences. Do not accept only a lower training reprojection residual.

### P0 — create a reproducible real-data benchmark before optimizing

Run the bundled Bellus imagery first, then at least two capture regimes: nadir
linear video and oblique/orbit video. Freeze one dataset as held-out. Record
registration rate, ATE/RPE when poses exist, scale error, independent RMSEH/RMSEV,
surface accuracy/completeness, dimensional error, runtime and peak memory.

The ASPRS positional-accuracy standard requires independent checkpoints and says
that control fit is not product accuracy. A formal small-area assessment calls
for at least 30 checkpoints; with fewer, label the experiment explicitly as a
reduced-checkpoint validation rather than standards compliance.

**Acceptance experiment:** one versioned command produces inputs' hashes,
environment lock, parameters, per-case JSON and a Markdown comparison. No README
accuracy range may be updated unless it is generated from this benchmark.

### P0 — correct calibration, timing and coordinate modeling

Add a Brown-Conrady or camera-specific distortion model; read actual video PTS
rather than assuming `frame_index/fps`; estimate camera-to-GNSS time offset; and
support GNSS antenna-to-camera lever arm plus IMU/camera boresight. Consumer-drone
rolling shutters also need either detection plus warning or a rolling-shutter BA
mode. Research demonstrates that rolling-shutter BA explicitly estimates motion
during readout, while direct-georeferencing work calibrates lever arm and boresight
at exposure time.

Also distinguish ellipsoidal GNSS altitude from orthometric altitude. Record the
vertical datum in every manifest and export.

**Acceptance experiment:** calibration-board reprojection test; synthetic time
offset recovery; lever-arm unit test under changing attitude; global-vs-rolling
shutter A/B on a fast yaw sequence; datum round-trip tests.

### P0 — preserve georeferencing after leveling

The pipeline currently fits the cloud and cameras to ENU, then may rotate both
about the cloud centroid to level a fitted plane. That post-alignment rotation is
not incorporated into the saved ENU frame or alignment residual. It can therefore
move the deliverable away from GPS while the report retains the pre-rotation fit.

Use IMU gravity as a prior inside optimization, or make leveling a viewer-only
transform. If a spatial transform is applied to deliverables, compose and persist
it in provenance, then recompute checkpoint and GPS residuals.

**Acceptance experiment:** every exported camera coordinate must reproduce the
reported residual when compared with its synchronized GNSS observation.

### P1 — use telemetry uncertainty rather than merely parsing it

Implement weighted, robust Sim(3) where weights are inverse *variance*, preferably
separate horizontal and vertical covariances. Threshold normalized residuals
(Mahalanobis distance), detect degenerate straight/constant-altitude trajectories,
and return scale/orientation covariance. Ordinary GPS altitude should not receive
the same trust as horizontal position.

**Acceptance experiment:** heteroscedastic simulation in which low-quality fixes
are corrupted. Weighted alignment must beat unweighted alignment on clean held-out
camera positions and return wider uncertainty when geometry is degenerate.

### P1 — repair incremental SfM failure recovery

Registration currently tries unsolved frames once in index order. A frame that
fails before neighboring cameras/points exist is never retried. Register the next
image with the largest verified 2D–3D support, run local BA, triangulate, and retry
the frontier until no progress occurs. Choose the initializer using inlier count,
parallax, spatial spread and cheirality—not only the strongest consecutive pair.
Reject tracks that merge two features from the same image and add cycle-consistency
checks before unioning pairwise matches.

**Acceptance experiment:** shuffled frames, skipped frames, repetitive roofs and
low-parallax sequences. Score registration fraction and catastrophic-failure rate,
not just successful-run accuracy.

### P1 — upgrade matching with a controlled learned option

Keep SIFT as the offline baseline and add SuperPoint+LightGlue (or an equivalently
licensed alternative) as an optional matcher. LightGlue reports an adaptive
accuracy/speed trade-off and stronger difficult-pair matching. Learned matches
still require geometric verification and the exact model/hash must be logged.

**Acceptance experiment:** compare SIFT and learned matching on the identical pair
graph using verified inlier count, spatial coverage, registration fraction, pose
error, runtime and VRAM. Adopt it only where downstream geometry improves.

### P1 — replace heuristic confidence with calibrated measurement uncertainty

The current confidence is a fixed blend of observation count, reprojection error
and triangulation angle; thresholds have not been calibrated against actual error.
Propagate pixel, calibration, pose and scale covariance to each point and ultimately
to each distance/area/volume. Calibrate predicted intervals on held-out truth and
report coverage (for example, how often a 95% interval contains the true value).

**Acceptance experiment:** reliability diagrams, expected calibration error, and
empirical 50/80/95% interval coverage. A measurement should be blocked if its
target uncertainty exceeds the mission requirement.

### P1 — make observation provenance spatially meaningful

An unobserved surface cannot appear as a point labeled `UNOBSERVED`, and a removed
dynamic point does not survive to become `DYNAMIC_EXCLUDED`. Build a camera-frustum
and ray-coverage field: observed voxels/surface patches carry view count, incidence
angle, resolution and occlusion evidence; unobserved/weak zones are explicit cells
or mesh overlays. Preserve dynamic masks as rays/regions in a separate evidence
layer rather than pretending they are reconstructed points.

**Acceptance experiment:** synthetic scene with deliberately hidden walls and a
moving vehicle. Hidden walls must be flagged uncovered, the moving region excluded,
and neither may be selectable for default measurement.

### P2 — dense geometry through multi-view verification

The current Depth Anything path fits each frame independently to sparse depth and
merges all inferred points. Add multi-view consistency: reproject into neighboring
frames, reject depth/color disagreement and occlusion conflicts, and retain separate
`AI_ONLY` versus `AI_GEOMETRICALLY_VERIFIED` states. Evaluate VGGT and MASt3R-SLAM
as proposal/initialization engines, but align and verify their geometry against
classical tracks, GNSS and held-out checks.

**Acceptance experiment:** accuracy-completeness curves for sparse, depth-prior,
VGGT and MASt3R variants. Never improve completeness by silently worsening observed
surface accuracy or allowing inferred points into default measurements.

### P2 — capture guidance as part of the solution

Predict whether the current pass can meet a requested accuracy using overlap,
baseline-to-depth ratio, triangulation angle, blur, exposure, texture, GNSS quality
and coverage. Produce a recapture plan identifying the smallest additional path
needed to reduce uncertainty. This moves Drishti3D from post-processing software to
an operational decision system.

## 4. Recommended execution order

| Phase | Deliverable | Exit condition |
|---|---|---|
| 1. Truth harness | Reproducible environment, Bellus scorecard, held-out policy, generated report | Baseline reruns from a clean environment and contains no unsupported claim. |
| 2. Geometric core | PyCOLMAP/BA production path, calibrated camera model, retry scheduler | Material improvement in registration and held-out geometry across datasets. |
| 3. Sensor correctness | PTS/time-offset, uncertainty-weighted GNSS, lever arm, datum, georef-safe leveling | Exported coordinates reproduce all reported residuals. |
| 4. Trust layer | Covariance-based point/measurement uncertainty and spatial coverage | Confidence is empirically calibrated; unseen/dynamic zones are visible and blocked. |
| 5. Learned assistance | LightGlue and dense-prior A/B adapters | Each model earns inclusion through a versioned benchmark and license review. |
| 6. Operational moat | Pre-flight/capture score and minimal recapture planner | Demonstrated reduction in uncertainty or failed missions on held-out captures. |

## 5. Proposed benchmark matrix

Run ablations rather than changing several components at once:

1. OpenCV current baseline.
2. Baseline + retry scheduler and safer initialization.
3. Baseline + BA.
4. BA + calibrated intrinsics/distortion.
5. Previous + time-offset/lever-arm/weighted GNSS.
6. Previous + learned matcher.
7. Previous + each dense prior separately.

For each row report median plus worst case. A prototype intended for field use is
better represented by failure rate and tail error than by its single best run.

## 6. Decision rules

- Geometry used for measurement must have multi-view observational support.
- Alignment residual is never presented as independent product accuracy.
- AI output remains separate until it passes an explicit geometric test.
- A feature is “implemented” only after a deterministic test or benchmark artifact.
- Accuracy claims state dataset, sensor/calibration, truth source, sample count,
  metric and percentile; avoid an unqualified “accurate to X cm.”
- Optimize the next largest measured error source, not the most fashionable model.

## 7. Primary sources used

- Johannes L. Schönberger and Jan-Michael Frahm, “Structure-from-Motion
  Revisited,” CVPR 2016, and the [COLMAP pipeline tutorial](https://colmap.github.io/tutorial/).
- Bangyan Liao et al., [“Revisiting Rolling Shutter Bundle Adjustment”](https://openaccess.thecvf.com/content/CVPR2023/html/Liao_Revisiting_Rolling_Shutter_Bundle_Adjustment_Toward_Accurate_and_Fast_Solution_CVPR_2023_paper.html), CVPR 2023.
- Philipp Lindenberger et al., [“LightGlue: Local Feature Matching at Light Speed”](https://openaccess.thecvf.com/content/ICCV2023/papers/Lindenberger_LightGlue_Local_Feature_Matching_at_Light_Speed_ICCV_2023_paper.pdf), ICCV 2023.
- Jianyuan Wang et al., [“VGGT: Visual Geometry Grounded Transformer”](https://openaccess.thecvf.com/content/CVPR2025/html/Wang_VGGT_Visual_Geometry_Grounded_Transformer_CVPR_2025_paper.html), CVPR 2025.
- Riku Murai et al., [“MASt3R-SLAM: Real-Time Dense SLAM with 3D Reconstruction Priors”](https://openaccess.thecvf.com/content/CVPR2025/papers/Murai_MASt3R-SLAM_Real-Time_Dense_SLAM_with_3D_Reconstruction_Priors_CVPR_2025_paper.pdf), CVPR 2025.
- ASPRS, [Positional Accuracy Standards for Digital Geospatial Data, Edition 2](https://www.asprs.org/wp-content/uploads/2024/03/October2023_HLA-Positional_Accuracy_Standards.pdf), Version 2 / 2024 publication.
- M. Eling et al., [direct-georeferenced UAV photogrammetric platform study](https://pmc.ncbi.nlm.nih.gov/articles/PMC3444096/), including exposure-time synchronization, lever-arm and boresight calibration.

## 8. Audit limitations

This audit did not install dependencies or alter the model. `pytest` was not
available, and the system Python lacks OpenCV. No new real-data reconstruction was
therefore generated. External papers support the proposed mechanisms; they do not
prove that a mechanism will improve Drishti3D until the planned ablation does.

