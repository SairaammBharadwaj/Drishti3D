# Drishti3D

**Single-Pass Drone Video → Accurate, Georeferenced 3D — SIH26158 (NTRO)**

Drishti3D turns one operational drone pass (video + GPS/telemetry) into a
metrically scaled, georeferenced 3D point cloud you can **measure**, and it is
explicit about *what was measured, what is uncertain, what was AI-assisted,
what was dynamic and excluded, and what was never observed.*

> Not an official NTRO product. Accuracy figures reflect the specific inputs of
> each run — the app never fabricates results.

---

## Why this is not a fake dashboard

The verified reconstruction path is a **real** feature-based Structure-from-Motion
engine (OpenCV): it detects and matches features across keyframes, estimates
relative pose from the essential matrix, triangulates 3D points, registers the
remaining frames by PnP, and fuses feature tracks into a sparse cloud where
every point is triangulated from ≥ 2 real observations. Metric scale and
geography come from a **robust Sim(3) alignment** of reconstructed camera
centres to GPS in a local ENU frame. **No COLMAP, CUDA, or downloaded weights
are required.**

On the bundled synthetic-but-geometrically-exact demo dataset, a typical run
registers all keyframes and reports **~0.5–3% error on known reference
dimensions** with **honest sub-metre GPS-alignment residuals** — computed
against ground truth, not asserted.

### The scientific invariant (provenance)

| Class | Colour | Measurable by default |
|---|---|---|
| `OBSERVED_HIGH_CONFIDENCE` | green | ✅ |
| `OBSERVED_LOW_CONFIDENCE` | amber | ⚠️ (flagged) |
| `AI_ASSISTED` | purple | ❌ (opt-in only) |
| `DYNAMIC_EXCLUDED` | red | ❌ |
| `UNOBSERVED` | grey | ❌ |

A monocular single pass **cannot** measure a surface no frame ever saw. AI may
complete it visually, but the completion is stored as a separate layer and
excluded from measurement unless the user explicitly opts in.

---

## Architecture

```
drishti3d/
  reconstruction/   drishti_recon package — the CV pipeline (importable, tested)
  backend/          FastAPI + SQLAlchemy (SQLite) + threaded job runner + SSE
  frontend/         React + TypeScript + Vite + Three.js operational UI
  sample_data/      synthetic dataset generator (video + telemetry + ground truth)
  tests/            pytest unit + integration tests (no weight downloads)
  docs/             telemetry schema, calibration, demo script, troubleshooting
  docker-compose.yml
```

Pipeline stages (each a separately testable module):
ingestion → telemetry → frames → frame-quality → sync → keyframes → dynamic
masking → **SfM (verified)** → **GPS Sim(3) georegistration** → fusion/cleanup →
optional mesh → quality/uncertainty report → exports.

---

## Capability matrix

| Capability | CPU | Needs GPU | Status |
|---|---|---|---|
| Ingestion, telemetry, sync, frame quality, keyframes | ✅ | — | implemented |
| Verified SfM reconstruction (OpenCV) | ✅ | — | **implemented (default)** |
| GPS/ENU georegistration, robust Sim(3), metric scale | ✅ | — | implemented |
| Measurements (distance/height/area/point) | ✅ | — | implemented |
| Confidence / provenance classification | ✅ | — | implemented |
| Dynamic masking (optical-flow residual) | ✅ | — | implemented (opt-in) |
| Dynamic masking (semantic) | ✅/slow | recommended | optional (local weights) |
| Mesh (Open3D Poisson) | ✅ | — | optional |
| Exports PLY / LAS / GLB / GeoJSON / CSV / JSON / HTML | ✅ | — | implemented |
| COLMAP verified engine | ✅ | optional | optional adapter |
| MASt3R-SLAM / VGGT learned reconstruction | — | ✅ | optional adapter (stub) |

Missing GPU / models produce **warnings, never crashes** (see
`GET /api/capabilities`).

---

## Quick start (local)

Prereqs: Python 3.11, Node ≥ 18. (FFmpeg and COLMAP are **not** required — a
bundled FFmpeg ships via `imageio-ffmpeg`, and SfM runs without COLMAP.)

```bash
# 1) Backend + reconstruction
cd drishti3d
pip install -e reconstruction            # core CV pipeline
pip install open3d laspy                  # optional: mesh + LAS export
pip install -r backend/requirements.txt

# 2) Generate the bundled demo dataset (video + telemetry + ground truth)
python sample_data/generate_sample.py sample_data/synthetic

# 3) Run the API (binds to 127.0.0.1 by default)
cd backend && uvicorn app.main:app --reload
#   API docs at http://127.0.0.1:8000/docs

# 4) Frontend (separate terminal)
cd frontend && npm install && npm run dev
#   open http://localhost:5173  (Vite proxies /api to the backend)
```

Demo: **New mission → upload `sample_data/synthetic/synthetic_flight.mp4` and
`synthetic_telemetry.csv` → Balanced preset → Process.** Watch staged progress,
then open the workspace to view the cloud, toggle provenance layers, measure a
building edge, and export the evidence report.

### Docker (offline)

```bash
docker compose up --build
# frontend: http://localhost:8080   backend API: http://localhost:8000
```

---

## Telemetry schema

CSV / JSON / SRT accepted. **Required:** `timestamp, latitude, longitude,
altitude`. **Optional:** `roll, pitch, yaw, velocity, gps_accuracy, rtk_status,
fx, fy, cx, cy, focal_length`. Column aliases are recognised (`lat`, `lon`,
`heading`, `hdop`, …). Invalid rows are reported, never silently dropped. See
`docs/TELEMETRY.md`.

## Camera calibration

Provide `fx, fy, cx, cy` (wizard or telemetry) for best accuracy. Without
intrinsics the system estimates `focal ≈ 0.9·max(w,h)` and **reports the
assumption as a warning**.

## Accuracy & honesty rules

- Alignment residual ≠ independent accuracy (reported separately).
- With ordinary GPS, absolute accuracy is **GPS-limited (often metre-level)**;
  with RTK/PPK the report labels scale as RTK-derived.
- Centimetre accuracy is never claimed without measured ground-truth evidence.

## Testing

```bash
pip install pytest
pytest tests/ -q      # unit + a small synthetic integration test; no weight downloads
```

## Ground-truth evaluation

Credibility comes from scoring the verified pipeline against datasets that carry
ground truth (trajectory ATE, metric-scale error, cloud accuracy/completeness).
GT poses are never fed in; datasets without GPS are anchored with synthesised
drone-grade noisy GPS, so numbers reflect a real single-pass flight.

```bash
python -m eval.run_eval --self-test          # no download: synthetic GT self-test
python -m eval.run_eval --root eval_data      # auto-detects ODM / TartanAir / ETH3D / TUM
```

Writes `eval_out/eval_scorecard.md` + `eval_report.json`. See `docs/EVALUATION.md`
for the dataset priority list and per-dataset fetch/layout instructions.

## GPU (optional)

The verified SfM core is CPU-only by design (reproducible, hardware-independent).
GPU (e.g. an RTX 4060) accelerates only the **optional** learned adapters:
semantic dynamic-object masking (`mask_backend="semantic"`) now auto-uses CUDA
when available — override with `DRISHTI_DEVICE=cpu|cuda` — and the MASt3R-SLAM /
VGGT depth priors below.

## Optional: COLMAP / MASt3R-SLAM / VGGT

- COLMAP: install COLMAP or `pip install pycolmap`; the adapter is auto-detected.
- MASt3R-SLAM: set `DRISHTI_MAST3R_PATH` (note **CC BY-NC-SA** licensing).
- VGGT: set `DRISHTI_VGGT_PATH`.
These are optional; the default classical path always runs. See `docs/OPTIONAL_MODELS.md`.

## Licences of major dependencies

FastAPI (MIT), SQLAlchemy (MIT), OpenCV (Apache-2.0), NumPy/SciPy (BSD),
pyproj (MIT), Open3D (MIT), laspy (BSD), React/Three.js (MIT). MASt3R ecosystem
weights may be **non-commercial (CC BY-NC-SA)** — review before use.

See `docs/` for the demo script, troubleshooting, and air-gapped deployment.
