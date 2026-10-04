# Intelligence Edition — execution tracker

Source: "DRONE-TO-3D: Intelligence Edition — Final Master Architecture" ([`INTELLIGENCE_EDITION_MASTER_ARCHITECTURE.pdf`](INTELLIGENCE_EDITION_MASTER_ARCHITECTURE.pdf), in this folder).
This file maps every section of that document to repository status and work items.
Order of execution follows the document's own §37 rule: highest technical risk
first, dashboard last.

## Section-by-section status

| Doc § | Requirement | Repo status | Action |
|---|---|---|---|
| 4 | Smart ingestion: blur, GPS spacing, optical flow, redundancy | DONE (`keyframes.py`, `frame_quality.py`) | none |
| 5 | Dynamic masking via YOLOv8-Seg / FastSAM, mask-before-match | DONE — Mask R-CNN (BSD-3; AGPL avoided, D-034) + measured area cap (D-035) | none |
| 6 | Dense feed-forward reconstruction (DUSt3R / MASt3R family) | DONE — `dense3d.py`, MASt3R, licence-gated | none |
| 7 | Pose graph optimization (GTSAM / g2o) | DONE — `pose_graph.py` (scipy, D-030); AGZ horiz 6.91 → 4.29 m | none |
| 8 | Kalman telemetry filtering + Helmert similarity | DONE — RTS smoother; negative result recorded (D-031: GPS error is bias, not jitter) | none |
| 9–11 | Voxel coverage OBSERVED/UNSEEN/OCCLUDED | DONE — 6-state superset (`coverage.py`) | none |
| 12–15 | Hard measurement refusal + gating logic | DONE (`measure.py`) | none |
| 16 | Provenance boundary (AI never promoted) | DONE (`provenance.py`, `verify.py`) | none |
| 17 | Trust Map 2.0 — 3 viewer modes | viewer has provenance filter | extend (with dashboard phase) |
| 18 | Recapture guidance | DONE (`capture.py`) | none |
| 19 | Two-tier delivery (T1 <3 min, T2 <15 min) | not structured as tiers | **ADD tier presets + timing gate** |
| 20 | Trust score C = w1·O+w2·N+w3·(1−E)+w4·P, calibrated | DONE — `trust.py`, fitted normalisation + weights; Spearman 0.625 (D-033) | none |
| 21 | Calibrated ± uncertainty | DONE — conformal (stronger than asked) | none |
| 22–24 | Dashboard (React+R3F / FastAPI+Celery+Redis) | backend 512 lines, frontend Vite scaffold | LAST per §37 |
| 26–29 | ATE, geometric RMSE ≤1 m, completeness | DONE (`eval/metrics.py`) | none |
| 30 | Coverage classification accuracy metric | DONE — `eval/intel_metrics.py` | none |
| 31 | Measurement refusal correctness (TAR/TRR/FAR/FRR) | DONE — FAR < 0.05, TRR > 0.95 on analytic scene | none |
| 32–33 | Measurement error + uncertainty calibration checks | DONE | none |
| 34 | Tier runtime targets | measure once tiers exist | with §19 |
| 35 | Stack additions: SuGaR | absent (Open3D Poisson only) | Tier-2, after core |
| 36 | Repository layout | ours differs; concepts map 1:1 | keep ours — churn without benefit |
| 37–44 | Priority: reconstruct → metric → intelligence → trust → viz → product | — | this file's order |

## Execution order (risk-first)

1. **M-A dense3d backbone** — DUSt3R/MASt3R adapter, pairing (sequential + skip),
   global alignment, confidence-carrying point cloud + poses. Validate on AGZ
   surveyed truth + gym_pass. GPU: local RTX 5060 8 GB (sm_120, torch 2.11 cu128
   verified); Kaggle as fallback.
2. **M-B pose graph** — chain + skip-pair relative-pose constraints, robust
   optimization; target: beat 6.91 m horizontal on AGZ (GPS baseline 3.19 m).
3. **M-C Kalman telemetry prefilter** before Sim(3).
4. **M-D new metrics** — refusal correctness + coverage classification accuracy.
5. **M-E trust score** with experimental weight calibration.
6. **M-F learned masking** backend.
7. **M-G two-tier orchestration** + runtime gates.
8. **M-H SuGaR Tier-2 mesh**, then dashboard modes.

## License gate (project policy)

DUSt3R/MASt3R checkpoints are CC-BY-NC-SA (non-commercial), same class as
SuperPoint which `features.py` refuses by default. Same treatment: the dense3d
engine is explicit opt-in with a recorded warning; the default engine remains
unrestricted. SIH evaluation use is fine; commercialisation would need a swap.


## Progress — 2026-09-10

Completed: M-A dense3d, M-B pose graph, M-C Kalman (negative result), M-D
metrics 4-5, M-E trust score, M-F learned masking.

Remaining: **M-G two-tier orchestration** (doc §19/§34, Tier-1 < 3 min /
Tier-2 < 15 min), **M-H SuGaR Tier-2 mesh** (§35) and Trust Map 2.0 viewer
modes (§17), then the dashboard (§22-24) — last, per the document's own §37.

### Defects found and fixed while executing the plan

These were not in the plan; they were found by measuring what the plan asked
for and are the reason several published figures moved.

| | Defect | Consequence | Fix |
|---|---|---|---|
| D-032 | Cloud accuracy was nearest-neighbour to a 3,750-point truth sample whose own spacing is 0.33 m median | Published synthetic accuracy was floored by truth sparsity, wrong by 10-40x in the pessimistic direction | Analytic point-to-surface distance; `cloud_acc_source` recorded |
| D-032 | `low_parallax` was absent from the published matrix | "0 failed cells" described a matrix excluding the regime designed to fail | Regime included; honest figure is 2/12 failed |
| D-033 | Trust-score saturation constants were guessed for a distribution the pipeline does not produce | Two of three terms pinned at ceiling; Spearman 0.087 = no ranking power | Constants fitted from data; Spearman 0.625 |
| D-034 | Semantic mask backend reported itself available while running an untrained network | Random masks deleted real image content before matching, silently | Refuses without weights |
| D-035 | Mask R-CNN detected a school roof as "train" at score 0.74 | 48.7 % of a frame masked, deleting the target structure | Measured 2 % per-instance area cap |
