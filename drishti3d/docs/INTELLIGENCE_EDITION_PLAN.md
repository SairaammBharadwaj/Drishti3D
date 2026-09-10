# Intelligence Edition — execution tracker

Source: "DRONE-TO-3D: Intelligence Edition — Final Master Architecture" (root PDF).
This file maps every section of that document to repository status and work items.
Order of execution follows the document's own §37 rule: highest technical risk
first, dashboard last.

## Section-by-section status

| Doc § | Requirement | Repo status | Action |
|---|---|---|---|
| 4 | Smart ingestion: blur, GPS spacing, optical flow, redundancy | DONE (`keyframes.py`, `frame_quality.py`) | none |
| 5 | Dynamic masking via YOLOv8-Seg / FastSAM, mask-before-match | optical-flow fallback only | **ADD learned backend** |
| 6 | Dense feed-forward reconstruction (DUSt3R / MASt3R family) | absent | **ADD `dense3d` engine** |
| 7 | Pose graph optimization (GTSAM / g2o) | absent | **ADD `pose_graph.py`** — directly attacks the measured AGZ bow (6.91 m horiz) |
| 8 | Kalman telemetry filtering + Helmert similarity | Sim(3) robust fit DONE; no Kalman | **ADD Kalman prefilter** |
| 9–11 | Voxel coverage OBSERVED/UNSEEN/OCCLUDED | DONE — 6-state superset (`coverage.py`) | none |
| 12–15 | Hard measurement refusal + gating logic | DONE (`measure.py`) | none |
| 16 | Provenance boundary (AI never promoted) | DONE (`provenance.py`, `verify.py`) | none |
| 17 | Trust Map 2.0 — 3 viewer modes | viewer has provenance filter | extend (with dashboard phase) |
| 18 | Recapture guidance | DONE (`capture.py`) | none |
| 19 | Two-tier delivery (T1 <3 min, T2 <15 min) | not structured as tiers | **ADD tier presets + timing gate** |
| 20 | Trust score C = w1·O+w2·N+w3·(1−E)+w4·P, calibrated | per-point confidence exists | **ADD formal score + calibration** |
| 21 | Calibrated ± uncertainty | DONE — conformal (stronger than asked) | none |
| 22–24 | Dashboard (React+R3F / FastAPI+Celery+Redis) | backend 512 lines, frontend Vite scaffold | LAST per §37 |
| 26–29 | ATE, geometric RMSE ≤1 m, completeness | DONE (`eval/metrics.py`) | none |
| 30 | Coverage classification accuracy metric | absent | **ADD** |
| 31 | Measurement refusal correctness (TAR/TRR/FAR/FRR) | absent | **ADD** — FALSE ACCEPT is the critical error |
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
