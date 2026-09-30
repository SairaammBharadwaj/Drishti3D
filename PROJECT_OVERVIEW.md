# Drishti3D — Project Overview

**Status of this document:** describes the system as it exists in this checkout
today. It is not a roadmap. Anything not implemented is in
[NEXT_STEPS.md](NEXT_STEPS.md).

Last updated: 2026-09-19.

---

## Project Goal

Drishti3D turns **one continuous drone video plus its telemetry** into a
georeferenced 3D reconstruction, and then lets an operator ask specific
geometric questions of it — a width, a height, a distance, a projected area —
at a **stated tolerance**, receiving either an answer with its evidence and
uncertainty, or a concrete explanation of which evidence is missing.

It targets problem statement **SIH26158 — Single-Pass Drone Video to Accurate 3D
Model Generation System** ([statement](drishti3d/docs/PROBLEM_STATEMENT.md)). The
original product and research plan, now archived, is
[DRISHTI3D_MVP_PLAN.md](drishti3d/docs/archive/DRISHTI3D_MVP_PLAN.md); this
overview records what is actually built.

**Who uses it:** a field mapping or infrastructure assessment team that needs
dimensions and coverage information before leaving a site.

**Inputs**

| Input | Form | Required |
|---|---|---|
| Video | MP4/MOV/WebM, one continuous pass | Yes |
| Telemetry | CSV (`timestamp,latitude,longitude,altitude,…`) or DJI `.SRT` | No — without it the result is shape-only, in arbitrary units |
| Camera calibration | `fx,fy,cx,cy` and optional distortion `k1,k2,p1,p2,k3` | No — estimated from frame size if absent, which costs accuracy |

**Outputs**

| Output | File | Notes |
|---|---|---|
| Colour point cloud | `point_cloud.ply`, `point_cloud.las`, `cloud.npz`, `georeference.json` | Per-point provenance class and propagated 1-sigma, in all three formats ([DEC-027](DECISIONS.md)); LAS declares its UTM CRS when the capture is georeferenced. Heights are WGS84 ellipsoidal, not orthometric. Sparse by default; `densify="mvs"` adds dense stereo geometry, `densify="depth"` adds inferred points excluded from measurement |
| Supported-surface mesh | `mesh.glb` | Visualisation; not measurement evidence |
| Camera trajectory | `trajectory.json/.csv/.geojson` | ENU poses, GNSS track, intrinsics |
| Coverage field | `coverage.npz`, `coverage.json` | Per-voxel observed / weak / occluded / unseen / verified-empty |
| Observation lineage | `observations.npz` | Which frames and pixels produced each cloud point |
| Refinement runs | SQLite `refinement_runs` | Before/after, frames recovered, every rejection with its reason |
| Measurements | REST API, SQLite | Value, interval, acceptance status, reason codes |
| Quality report | `quality_report.html/.json` | Per-stage diagnostics and warnings |

**The central design commitment:** a number is reported with what supports it,
or it is refused with the reason. The system never fills an evidence gap with a
plausible value. Concretely, that is why the current deployment cannot report
"meets requirement" for any measurement at all — no interval calibration has
been validated yet, so the strongest honest verdict is *estimated only*. See
[DEC-003](DECISIONS.md#dec-003--acceptance-requires-a-validated-calibration-profile).

---

## Current Features

### Under-15-minute processing (one laptop run)
**What:** DJI_1003, an 11.3-min 1080p flight, processes end to end in
**733.7 s (12.2 min)**, down from > 32.5 min. Dense stereo went 1,585 s -> 409 s
with settings that were *more* accurate on UseGeo's LiDAR (RMSE 0.324 -> 0.316 m).
**Where:** `PipelineParams.mvs_*` defaults, `mvs.run_colmap`,
`scripts/dense_trial.py`, `scripts/sfm_trial.py`, `artifacts/timing.json`.
One run, one GPU, one reference scene ([DEC-041](DECISIONS.md)).

### Hole and water fill (inferred, never measured)
**What:** Water and other areas the cameras saw but stereo could not
reconstruct get a surface fitted to the observed ground around them. It is
level when the shoreline is level, coloured from the video, and labelled
`INFERRED_FILL` (provenance 6). Ground no camera looked at stays empty.
**Where:** `holefill.py`, pipeline stage 14b (`PipelineParams.fill_holes`,
default on), `scripts/fill_holes.py` for finished projects, `fill.npz` /
`fill.json`, the `/model` and `/model.bin` endpoints, the viewer's blue layer.
**Measured:** DJI_1003 (Lady Bird Lake, Austin) 44.2 ha filled of 141.4 ha
surveyed; DJI_1001 26.0 ha of 129.2 ha; 15–27 s each. Fill lives beside the
cloud, never in it, so no measurement or evaluation reads it
([DEC-040](DECISIONS.md)).

### Dense multi-view stereo
**What:** `densify="mvs"` adds COLMAP PatchMatch stereo — **observed** geometry,
triangulated from photometric agreement across real images, measurable under
exactly the same rules as the sparse points. Kept strictly distinct from
`densify="depth"`, whose points are predicted from single images and excluded
from measurement.
**Where:** `mvs.py`, `pipeline.py` densify stage, `colmap_adapter.keep_workspace`.
**Measured on the AGZ mission:** 251,998 points at 0.099 m spacing against
17,898 at 0.167 m sparse — **14× the point count**, median spacing 0.167 m →
0.099 m, `AI_ASSISTED: 0`. 20.5 minutes, ~19 of it patch-match stereo on the
GPU. Point count is not a measured 14× gain in geometric resolution, and
**camera-trajectory agreement being unchanged is not evidence that dense surface
accuracy is unchanged** — no held-out surface reference has been scored
([DEC-024](DECISIONS.md), [DEC-025](DECISIONS.md)).
**Requires** a CUDA-enabled `colmap` executable; the PyPI `pycolmap` wheels are
CPU-only and dense stereo refuses without CUDA. `/api/capabilities` reports
which of those two cases applies.
**Lineage:** dense points carry observation tracks like sparse ones — the images
`stereo_fusion` fused each point from — so they are measurable rather than
refused for unverified support. All 251,785 points have one; 1,331,016
observations, median 5 per point ([DEC-020](DECISIONS.md)). Each row is labelled
`sparse_feature_observation` or `dense_fusion_contributor`: a dense row's pixel
is **projected** from the fused point, not a pixel a detector measured there
([DEC-029](DECISIONS.md)). "99.9% reproject inside the image that claims them"
is an indexing check, not an accuracy validation.
**Effect on measurement:** on a 60-measurement sample, **59 of 60 are blocked
only by calibration** on the dense cloud against 40 of 60 on the sparse one;
median supporting views 3 → 4 and measured parallax 16.6° → 27.9°.
**Uncertainty caveat:** dense points carry a geometric estimate, not a
propagated covariance, floored by the sparse model's own accuracy
([DEC-019](DECISIONS.md)).

### Reconstruction pipeline
**What:** video + telemetry → georeferenced point cloud, mesh, trajectory,
coverage field, quality report.
**Where:** `drishti3d/reconstruction/drishti_recon/pipeline.py` — `run()`, a
fourteen-stage sequence (ingestion → telemetry → frames → quality → sync →
keyframes → masking → SfM → densify → georegistration → fusion → mesh → report
→ exports).
**Depends on:** `ingestion.py`, `telemetry.py`, `sync.py`, `frame_quality.py`,
`keyframes.py`, `features.py`, `sfm.py`, `bundle.py`, `colmap_adapter.py`,
`geo.py`, `fusion.py`, `mesh.py`, `coverage.py`, `exports.py`.

### Two interchangeable SfM engines
**What:** the repository's own incremental SfM (`sfm.py` + `bundle.py`), and
COLMAP via PyCOLMAP (`colmap_adapter.py`), selectable per run with
`PipelineParams.engine`.
**Measured 2026-09-19** on the real AGZ single-pass mission: COLMAP is 3.5×
faster and roughly 2× more accurate in shape. Its longer tracks also leave far
more measurements usable — 51 of 60 blocked only by calibration, against 10 of
60. See
[TESTS_AND_RESULTS.md](TESTS_AND_RESULTS.md#agz-single-pass-engine-comparison).
The OpenCV engine remains the always-available CPU fallback and is still the
pipeline default.

### Telemetry-aware georeferencing with degeneracy checks
**What:** robust covariance-weighted Sim(3) alignment of reconstructed camera
centres onto the GNSS track, with explicit conditioning tests, a scale
uncertainty estimate, and a gravity-levelling step that is *rejected* when it
worsens the GNSS residual.
**Where:** `geo.py` (`robust_sim3`, `umeyama_sim3`, `ENUFrame`),
`pipeline.py` georegistration stage.

### Provenance-classified geometry
**What:** every point carries one of six provenance classes
(`OBSERVED_HIGH_CONFIDENCE`, `OBSERVED_LOW_CONFIDENCE`, `AI_ASSISTED`,
`DYNAMIC_EXCLUDED`, `UNOBSERVED`, `AI_GEOMETRICALLY_VERIFIED`). Measurements use
observed geometry by default and flag anything else.
**Where:** `provenance.py`, `fusion.py`.

### Propagated measurement uncertainty
**What:** per-point covariance from the reconstruction, propagated into distance,
height and area measurements including the metric-scale term. Both SfM engines
produce it, using the same MAD-based pixel-noise estimator so an engine
comparison is not also a comparison of two noise models.
**Where:** `uncertainty.py` (`point_covariances`,
`polyline_length_uncertainty`, `height_uncertainty`, `area_uncertainty`,
`calibrate`), `measure.py`, `colmap_adapter._point_uncertainty`.
**One scale error per measurement, not per segment.** A polyline's length is
propagated whole, so subdividing a straight line leaves its uncertainty
unchanged and a shared interior vertex is not counted twice
([DEC-022](DECISIONS.md)).
**One definition of a result.** Both the question route and the exploratory
ruler go through `backend/app/results.py`, so a measurement carries its sigma,
interval basis, acceptance status and artifact version whichever way it was
created — and a reconstruction with no georeference reports
`reconstruction units`, never metres ([DEC-021](DECISIONS.md)).
**Measured on the AGZ mission:** median measurement sigma 0.064 m (COLMAP),
0.069 m (in-repo).

### Coverage field with a positive free-space rule
**What:** a voxel field classifying the mission volume as observed / weak /
occluded / unseen / dynamic-excluded / verified-empty. **Free space is
established only where a ray passed through the cell and terminated on a
finite, supported depth** — a hole in a sparse cloud is unknown, not clear.
**Where:** `coverage.py` (`build`, `CoverageGrid.is_measurable`).

### Measurement questions and the tolerance gate
**What:** an operator asks a geometry question *with a tolerance*; the backend
returns the value, its interval, an acceptance status
(`meets_requirement` / `estimated_only` / `needs_refinement` /
`not_observable`), reason codes, and a concrete next action for each reason.
Changing the tolerance re-decides the verdict without re-running geometry.
**Where:** `questions.py` (the rules), `backend/app/routers/questions.py` (the
API), `backend/app/models.py` (`MeasurementQuestion`, `Measurement`).

### Observation lineage
**What:** every cloud point records the image measurements that produced it —
which frames, and the pixel in each. Both SfM engines emit it, it survives
fusion's voxel downsampling and outlier removal, and it is persisted as
`observations.npz`.
**Where:** `sfm.py` / `colmap_adapter.py` (`ReconResult.obs_point/obs_frame/obs_uv`),
`fusion.py` (`PointCloud.source_index`), `pipeline.py`
(`_remap_observations`).
**Measured on the AGZ mission:** 69,173 observations across 17,897 points,
median 3 per point.

### Measurement evidence
**What:** for a selected point — the frames that actually measured it and the
pixel each was measured at, the parallax those measurements provided, coverage
membership, and the metric scale source with its relative uncertainty.
**Where:** `evidence.py` (`ReconstructionEvidence`).
**Two bases, and the record says which:** with lineage, support is stamped
`triangulated_observations` and can license acceptance. Without it, support
falls back to camera frustums, is stamped `frustum_upper_bound`, and blocks
acceptance — on the AGZ mission the frustum figures overstate view count by 3.0×
and parallax by 3.7× against what the measurements actually provided.

### Same-pass evidence recovery — **experimental**
**Status: experimental, and it now passes its own gate.** Targeted refinement
produces a **higher answer yield than a uniform budget on all three test beds
tried** — 15 against 10, 13 against 5, and 15 against 9 measurements blocked
only by calibration — with **zero regressions in every one, against the
control's four to seven**. Since the per-question cost work it does so at
comparable or lower compute (88.6 s against the control's 135.4 s on the full
pass), and at the control's own budget it ties once and wins twice.

**All three test beds are partitions of one flight.** The only genuinely
separate AGZ segment cannot run the comparison at all: at a 2.8 m baseline
keyframe selection correctly declines to thin it, so there is no unused frame
pool and no denser arm. Do not describe this as a proven advantage
([DEC-013](DECISIONS.md), [DEC-014](DECISIONS.md), [DEC-015](DECISIONS.md),
[DEC-016](DECISIONS.md),
[results](drishti3d/docs/benchmarks/2026-09-20_f4_targeted_vs_uniform/RESULTS.md),
[second test beds](drishti3d/docs/benchmarks/2026-09-20_f4_second_capture/RESULTS.md)).

**What:** "Improve this measurement" — frames of the pass that the
reconstruction never processed are ranked by the parallax they would add at the
measurement's weakest endpoint, a bounded batch is posed by PnP against the
existing model, the endpoint is located in each by pose-guided descriptor match
and re-triangulated, and the measurement is re-decided. Runs are recorded
whether or not they helped.
**Where:** `refinement.py` (`RefinementEngine`, `RefinementRun`),
`POST /api/projects/{id}/questions/{qid}/refine`, `models.RefinementRun`.
**Observed benefits, which are real:** in the F4 experiment it recovered frames
for 16 of 20 questions, took supporting views from a median of 3 to 6.5 and
measured parallax from 9.56° to 26.75° — against the control's 3 → 3 and
9.56° → 10.26°. It is adding evidence where the control is adding resolution.

**How the endpoint is found in a recovered frame:** not by re-identifying its
keypoint — the reconstruction's observations sit at its own detector's
keypoints, a median 8.9 px from a fresh detection's, and across the viewpoint
change worth recovering SIFT matches the same surface at a best-to-second ratio
of 0.93, no better than chance. Instead the two frames are matched densely,
correspondences near the endpoint fit a local affine map, and the pixel is
transferred through it. Measured: 1.3% of candidates located by descriptor
match, 10.7% by chaining descriptors through intermediates, **40.0% by
transfer**.

**What it does not do:** produce a narrower interval than the control on the
full pass (0.104 m against 0.092 m) — though on both half-pass test beds the
ordering reverses, so neither method is uniformly better on interval width.

### Dataset tooling
**What:** inventory of every dataset in the checkout with content digests, LFS
stub detection and flown-geometry statistics; a builder that turns an AGZ frame
subset into a plan-conformant mission with real presentation timestamps and
access-separated reference data; a runner that reconstructs a mission and scores
it against held-out references.
**Where:** `drishti3d/scripts/inventory_datasets.py`,
`drishti3d/scripts/build_agz_mission.py`, `drishti3d/scripts/run_mission.py`,
`drishti3d/scripts/agz_logs.py`. Outputs land in `datasets/`.

### REST API and web workspace
**What:** project CRUD, upload, processing jobs with progress, artifact
download, measurements, measurement questions. React + Three.js viewer.
**Where:** `drishti3d/backend/app/`, `drishti3d/frontend/src/`.

### Optional learned components
**What:** MASt3R dense backend (`dense3d.py`), VGGT (`vggt_engine.py`),
monocular depth prior (`depth_prior.py`), LightGlue/DISK matching
(`features.py`), semantic and optical-flow dynamic masking (`masking.py`).
All are opt-in and off by default. Weights are not bundled.

---

## Tech Stack

### FastAPI
Backend API framework. **Why:** async support, automatic OpenAPI generation,
Pydantic validation at the boundary, and it stays out of the way of a
compute-heavy worker. **Used in:** `backend/app/main.py`,
`backend/app/routers/`.

### SQLAlchemy + SQLite
Metadata persistence: projects, jobs, measurements, measurement questions.
**Why:** a single workstation deployment does not justify a server database, and
SQLite is a file that can be copied with the mission. **Alternative when
concurrency or spatial queries arrive:** PostgreSQL + PostGIS.
**Used in:** `backend/app/db.py`, `backend/app/models.py`.

### OpenCV (`opencv-python` 5.0)
Decoding, feature detection and matching, PnP, triangulation, undistortion.
**Why:** the classical geometry machinery is mature, CPU-only, and has no
licence encumbrance. **Used in:** `sfm.py`, `features.py`, `sensors.py`,
`pipeline.py`.

### PyCOLMAP 4.2
The second SfM engine. **Why:** COLMAP's incremental mapper and bundle
adjustment are the field reference, and on real data here they are both faster
and more accurate than the in-repo engine.
**Used in:** `colmap_adapter.py`.

### NumPy / SciPy
Linear algebra, sparse least squares for bundle adjustment, KD-trees for
snapping and outlier removal. **Used in:** everywhere in
`reconstruction/drishti_recon/`.

### PyTorch 2.11 (CUDA 12.8)
Only for the optional learned components. **Why:** the pretrained models that
exist are PyTorch. It is not on the critical path — the classical pipeline runs
without a GPU. **Used in:** `dense3d.py`, `vggt_engine.py`, `depth_prior.py`,
`masking.py`, `features.py` (LightGlue).

### pyproj
CRS transforms for scoring and export (WGS 84 ↔ UTM). **Used in:**
`scripts/run_mission.py`, `exports.py`.

### FFmpeg / ffprobe
Container probing and mission video construction with explicit per-frame
presentation timestamps. **Used in:** `ingestion.py`,
`scripts/build_agz_mission.py`, `scripts/inventory_datasets.py`.

### React + Vite + Three.js
The operator workspace and 3D viewer. **Why:** the viewer needs real-time
point-cloud rendering in a browser. **Used in:** `frontend/src/`.

---

## Architecture

```mermaid
graph TD
    U[Operator] --> FE[React + Three.js workspace]
    FE -->|REST /api| API[FastAPI]
    API --> DB[(SQLite: projects, jobs,<br/>questions, measurements)]
    API --> ST[storage.py: per-project<br/>uploads + artifacts]
    API --> JOB[jobs.py: background<br/>reconstruction job]
    JOB --> PIPE[drishti_recon.pipeline.run]

    PIPE --> ING[ingestion / telemetry / sync]
    PIPE --> SFM{SfM engine}
    SFM -->|engine=opencv| OCV[sfm.py + bundle.py]
    SFM -->|engine=colmap| COL[colmap_adapter.py]
    PIPE --> GEO[geo.py: Sim3 onto GNSS<br/>+ degeneracy checks]
    PIPE --> FUS[fusion.py: clean + classify]
    PIPE --> COV[coverage.py: observed /<br/>occluded / unseen / empty]
    PIPE --> EXP[exports.py: PLY, LAS,<br/>GLB, GeoJSON]

    API --> Q[questions.py<br/>acceptance rules]
    API --> EV[evidence.py<br/>candidate views]
    Q --> UNC[uncertainty.py]
    EV --> COVF[(coverage.npz)]
    EV --> TRAJ[(trajectory.json)]
```

The dependency direction is one-way: the API calls the geometry service, and
rendering never determines measurement validity. The frontend displays a status;
it never computes one.

---

## Directory Structure

```text
Drishti3D/
├── README.md                    front page: what it is, results, how to run
├── PROJECT_OVERVIEW.md          this file
├── DECISIONS.md  WORKLOG.md  SYSTEM_FLOW.md
├── TESTS_AND_RESULTS.md  NEXT_STEPS.md
├── datasets/                    plan section 6.6 data layout
│   ├── catalog.csv              machine-readable inventory (tracked)
│   ├── INVENTORY.md             the same, with caveats (tracked)
│   ├── public/<set>/<mission>/  built missions: raw/, calibration/, manifest
│   ├── truth/<mission>/         reference data — never given to the worker
│   └── splits/                  development / calibration / locked test
└── drishti3d/
    ├── backend/app/             FastAPI: routers, models, jobs, storage
    ├── reconstruction/drishti_recon/   the geometry and measurement library
    ├── frontend/src/            React + Three.js workspace
    ├── scripts/                 dataset inventory, mission build, mission run
    ├── eval/                    benchmark harness, calibration, metrics
    ├── tests/                   pytest suite
    ├── deploy/                  read-only public showcase: image and server kit
    ├── data/                    local DB, project artifacts, raw captures
    └── docs/                    engineering docs, benchmarks; docs/archive/ for superseded plans
```

**Responsibilities**

- `reconstruction/drishti_recon/` — all geometry, uncertainty and acceptance
  logic. Has no dependency on the web layer and is usable as a library.
- `backend/app/` — persistence, job orchestration, HTTP. Contains no geometry.
- `scripts/` — operator-facing tooling that stands outside the request path.
- `datasets/truth/` — evaluation data. **Never mounted into the worker.**

---

## Important Files

`drishti3d/reconstruction/drishti_recon/pipeline.py`
The reconstruction entry point. `run(project_dir, video, telemetry, params)`
executes every stage and writes the artifact set.

`drishti3d/reconstruction/drishti_recon/questions.py`
The acceptance gate: `Status`, `Reason`, `CalibrationProfile`,
`MeasurementQuestion`, `Evidence`, and `evaluate()`. Read this first to
understand what the product will and will not claim.

`drishti3d/reconstruction/drishti_recon/evidence.py`
`ReconstructionEvidence` — measuring frames and their pixels, parallax,
coverage membership and supporting frames for a selected point, with the basis
each figure came from.

`drishti3d/reconstruction/drishti_recon/coverage.py`
The unknown-space map and the free-space rule.

`drishti3d/reconstruction/drishti_recon/refinement.py`
Same-pass evidence recovery: candidate ranking, PnP re-registration,
pose-guided endpoint location, re-triangulation and the run record.

`drishti3d/backend/app/main.py`
FastAPI application; runs `init_db()` on startup.

`drishti3d/backend/app/db.py`
Engine, session, `init_db()` and `_add_missing_columns()` — an additive-only
startup migration for the development SQLite database.

`drishti3d/backend/app/config.py`
Reads `DRISHTI_DATA_DIR` and derives the data, project and database paths.

`drishti3d/scripts/build_agz_mission.py`
Builds a mission in the `datasets/` layout from an AGZ frame subset.

`drishti3d/scripts/run_mission.py`
Reconstructs a mission and scores it against `datasets/truth/`.

---

## How To Run

### Dependencies

There is no `requirements.txt`; the canonical build is
`drishti3d/docs/ENVIRONMENT.md`, reproduced here:

```bash
cd drishti3d
uv venv --python 3.12 .venv                 # 3.14 has no OpenCV wheel yet
VIRTUAL_ENV=.venv uv pip install \
    numpy scipy "opencv-python-headless>=4.8" pyproj imageio imageio-ffmpeg \
    fastapi "uvicorn[standard]" sqlalchemy pydantic python-multipart aiofiles \
    httpx laspy open3d pytest pyyaml
VIRTUAL_ENV=.venv uv pip install -e reconstruction
VIRTUAL_ENV=.venv uv pip install pycolmap    # the reference SfM engine
```

`pip` works identically. FFmpeg and ffprobe must be on `PATH` for ingestion and
for `scripts/build_agz_mission.py`.

Verified in this checkout: Python 3.12.14, NumPy 2.5.2, OpenCV 5.0.0,
PyCOLMAP 4.2.0, PyTorch 2.11.0+cu128 (CUDA available), FastAPI 0.141.1,
pyproj 3.7.2, FFmpeg on `PATH`.

### Environment variables

| Variable | Meaning |
|---|---|
| `DRISHTI_DATA_DIR` | Root for the SQLite database and per-project artifacts. Defaults to `drishti3d/data`. |
| `DRISHTI_SEG_WEIGHTS` | Path to a local torchvision segmentation checkpoint for semantic dynamic masking. Optional. |

No secrets are required. Do not commit any.

### Backend

```bash
cd drishti3d
.venv/bin/uvicorn backend.app.main:app --reload --port 8000
# OpenAPI at http://localhost:8000/docs
```

### Frontend

```bash
cd drishti3d/frontend
npm install
npm run dev            # Vite dev server, proxies /api to :8000
```

### Tests

```bash
cd drishti3d
.venv/bin/python -m pytest tests/ -q
```
256 tests, ~110 s on this machine as of 2026-09-19.

### Dataset and mission workflow

```bash
cd drishti3d
# 1. what is on disk, with digests and flown geometry
.venv/bin/python scripts/inventory_datasets.py          # --no-hash to skip digests

# 2. build a mission from an AGZ frame subset
.venv/bin/python scripts/build_agz_mission.py \
    --source data/real_drone/agz_dense --name agz_dense_pass --overwrite

# 3. reconstruct it and score against the held-out reference
.venv/bin/python scripts/run_mission.py \
    --mission agz_dense_pass --engine colmap --max-frames 184 --tag colmap_full
```

---

## Current System State

### What works

- End-to-end reconstruction from a real single-pass aerial video with real
  consumer-grade GNSS, producing a georeferenced cloud, mesh, trajectory,
  coverage field and exports. Measured on the AGZ mission: 86 s wall with the
  COLMAP engine, 291 s with the OpenCV engine.
- Two SfM engines with a measured comparison on identical input.
- Telemetry-aware scale and georeferencing, with the scale's own uncertainty
  reported and conditioning tested.
- Propagated uncertainty from point covariance through distance, height and
  area, including the scale term.
- Coverage classification that keeps unknown space unknown.
- Holes over water and untextured ground filled for display with a labelled,
  non-measurable surface ([DEC-040](DECISIONS.md)).
- Measurement questions with tolerance, acceptance status, reason codes and
  actionable guidance, re-decidable at a new tolerance without re-running
  geometry.
- Observation lineage end to end, on both engines, so a measurement can name
  the frames and pixels that produced it.
- Measurement evidence for any selected point, labelled with the basis it was
  derived from.
- Same-pass evidence recovery for a single measurement, with every candidate
  frame's fate reported — experimental, and measured against its control.
- A reproducible A/B harness for that control (`eval/f4_experiment.py`) with a
  frozen, hashed question set.
- Reproducible dataset inventory, mission construction and scoring, with
  reference data access-separated from the worker.

### What does not work yet

- **Nothing can be accepted.** No calibration profile has been fitted or
  validated for any capture regime, so every verdict is at best
  `estimated_only`. This is deliberate, not a defect ([DEC-003](DECISIONS.md)),
  and since observation lineage landed it is the *only* remaining blocker on
  real data.
- **Same-pass refinement is unproven, not disproven.** It now beats the uniform
  control on answer yield across three test beds with zero regressions and at
  comparable or lower compute — but all three are partitions of one flight, and
  the one genuinely separate segment cannot run the comparison. It stays
  experimental ([DEC-013](DECISIONS.md) … [DEC-017](DECISIONS.md)).
- **A denser reconstruction is not strictly better for measurement.** On one
  test bed, doubling the keyframes took answer yield from 7 down to 5 and raised
  median measurement sigma from 0.183 m to 0.260 m: endpoints re-snap elsewhere
  and the coverage grid's boundaries move.
- **A learned matcher is now on the refinement path.** LightGlue/DISK
  (Apache-2.0 via kornia) is what made endpoint location work, and it wants a
  GPU. The classical fallback exists but is untested at scale.
- **The pipeline still defaults to the slower engine.** Both engines now
  produce measurable reconstructions, but `PipelineParams.engine` defaults to
  `"opencv"`, and on COLMAP 51 of 60 sampled measurements have nothing blocking
  them but calibration, against 10 of 60 on the in-repo engine. Changing the
  default needs more than one mission.
- **No measurement passport or verifier** (plan F3).
- **No Tolerance Lens UI.** The backend gate exists; the frontend does not
  render it yet.
- **Registration is poor on real data.** Keyframe selection kept 80 of 184
  frames on the AGZ mission and SfM registered all 80, so 104 frames of the
  pass contributed nothing.
- **Georeferenced accuracy is GNSS-bound.** Median 3.7 m against the AGZ
  reference, with a 5% scale uncertainty from a ±9.4 m eph receiver. Centimetre
  claims are not available from this capture.
- **No field data.** There is no capture with independently measured checkpoints
  or reference dimensions, so no positional accuracy class can be assessed.
