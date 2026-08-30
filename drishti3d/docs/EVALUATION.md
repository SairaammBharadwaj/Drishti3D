# Drishti3D — Ground-Truth Evaluation

This is how we make the accuracy claim *credible*: run the **verified** pipeline
on datasets that carry ground truth and score it with honest, gauge-free metrics.

## What the harness measures

| Metric | Meaning | How |
|---|---|---|
| **ATE RMSE / median** | camera-position error (m) | estimated centres vs GT centres, after a Sim(3) alignment (standard SLAM protocol) |
| **Scale error** | metric-scale drift | `\|recovered_scale − 1\|` from that Sim(3) |
| **Cloud accuracy** | point-cloud fidelity (m) | recon is registered to the GT cloud by a rigid (scale-locked) ICP, then **cropped to the GT evaluation region** (ETH3D/T&T protocol); nearest-GT distance per point (median / RMSE) |
| **Completeness** | coverage of the GT surface | fraction of GT points within a threshold of the reconstruction |
| **Dim error** | dimensional measurement error (%) | the pipeline's own GT check on known reference distances |

**Honesty rules baked in**
- Ground-truth **poses are never fed to the pipeline**.
- Datasets without real GPS are anchored with **synthesised drone-grade noisy GPS**
  (default σ≈2.5 m horizontal, 4 m vertical) derived from the GT track — so scale
  and position error reflect a real single-pass flight, not an idealised solve.
- Every spatial number is reported **after** the Sim(3) alignment, so a global
  gauge (rotation/translation/scale) can neither flatter nor penalise the result.

## Quick start (no download)

```bash
# from drishti3d/, with the drishti-recon env active
python -m eval.run_eval --self-test --out eval_out
```

This renders a small synthetic scene with full ground truth (trajectory, point
cloud, reference distances), runs the pipeline, and writes
`eval_out/eval_scorecard.md` + `eval_out/eval_report.json`. Use it to confirm the
harness is wired correctly before pulling the big datasets.

## Dataset priority & how to fetch

| Dataset | Use it for | Gives us | Priority |
|---|---|---|---|
| **OpenDroneMap / ODMData** | real aerial reconstruction | real drone imagery, GPS EXIF (some GCP/RTK) | 🔥 #1 |
| **TartanAir** | depth / SLAM / AI testing | RGB, depth, pose, segmentation, flow, intrinsics | 🔥 #2 |
| **ETH3D** | SLAM / reconstruction benchmark | images, IMU, GT on training sequences | #3 |
| **AGI2P / RTK-SLAM** | aerial localization / cloud eval | aerial images, ALS point clouds, GT poses | #4 |
| **Held-out test set** | final credibility | never touched during development | 🔥 essential |

Downloads are multi-GB and are **yours to trigger**. Put each dataset in its own
folder under `eval_data/` and the CLI auto-detects the layout:

```bash
python -m eval.run_eval --root eval_data --out eval_out
```

### #1 OpenDroneMap / ODMData
- Verified example sets (each is a GitHub repo of geotagged JPGs under `images/`):
  `OpenDroneMap/odm_data_zoo` (suburban neighbourhood — **buildings, roads, cars**;
  good for a visible-structure demo), `OpenDroneMap/odm_data_aukerman` (flat
  aerial field/road), `OpenDroneMap/odm_data_waterbury` (mixed houses + trees).
  Pull a contiguous slice of ~30–40 frames for a quick run.
- Source: `github.com/OpenDroneMap/ODMdata` (or any ODM example set).
- Expected layout: a folder of images (`.jpg`), optionally an `images/` subdir.
  GPS is read from EXIF, or from a sibling `geo.txt` (ODM format:
  `name lon lat alt`) or a `*_telemetry.csv`.
- Optional GT cloud: drop a georeferenced `.ply`/`.las`/`.laz` in the folder
  (e.g. an ODM `odm_georeferenced_model.laz`); it is auto-found for cloud metrics.
- Detect kind: `odm`.

### #2 TartanAir
- Source: `theairlab.org/tartanair-dataset`. Grab one trajectory, e.g.
  `abandonedfactory/Easy/P001/`.
- Expected layout: `image_left/000000_left.png …` + `pose_left.txt`
  (NED `tx ty tz qx qy qz qw`). Intrinsics are the fixed TartanAir 640×480 model.
- Detect kind: `tartanair`. Use `--stride 2..5` to keep runs quick.

### #3 ETH3D
- Source: `eth3d.net` → SLAM benchmark, a *training* sequence (has GT).
- Expected layout: `rgb/` + `rgb.txt` + `groundtruth.txt` (TUM
  `timestamp tx ty tz qx qy qz qw`) + `calibration.txt` (`fx fy cx cy`).
- Detect kind: `eth3d`.

### #4 AGI2P / RTK-SLAM (generic TUM)
- Expected layout: `rgb/` + `groundtruth.txt` (TUM), optional `calibration.txt`
  and a `.ply`/`.las` ALS cloud in the folder.
- Detect kind: `tum`.

### Held-out test set
Keep one dataset folder aside, **never run it during development**, and score it
only for the final credibility number. Same layout/commands as above.

## Interpreting results

- **Scale error** is the headline for the metric-safety wedge: a small value
  means we recover true size from noisy GPS + monocular video in a single pass.
- **ATE** separates trajectory quality from scale; report both.
- **Completeness** is threshold-dependent — the scorecard prints the threshold
  used (`--cloud-thr`, default 0.5 m). A sparse feature cloud scores low
  completeness against a dense GT even when accuracy is good; that is expected.
- Cases where the pipeline registered too few cameras (`solved/GT` low) show a
  warning; treat those as capture/coverage failures, not accuracy numbers.

## GPU note (RTX 4060)

The **verified** path (features → essential-matrix SfM → triangulation → robust
Sim(3)) is CPU-only *by design* — it is the reproducible core we defend. The GPU
pays off in the **optional** adapters, not the core:
- learned dense/depth priors (MASt3R-SLAM / VGGT) via `ai_adapter` — see
  `docs/OPTIONAL_MODELS.md`;
- semantic dynamic-object masking (`mask_backend="semantic"`, a torchvision
  checkpoint via `DRISHTI_SEG_WEIGHTS`).

For evaluation runs keep the CPU core so the numbers are hardware-independent;
enable GPU adapters separately when you want to show the learned-prior upside.
