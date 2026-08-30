# Drishti3D — Complete Project Draft

**SIH 2026 · Problem SIH26158 (NTRO) · Single-pass drone video → measurable, georeferenced 3D**

_Full handoff/status document. Companion to `convo.md` (the working-session transcript)._
_State as of 2026-08-30 — all planned work complete, 31/31 tests passing._

---

## 1. Executive summary

Drishti3D turns **one linear drone pass (video or aerial photos) + coordinates** into a
**georeferenced, metrically-scaled 3D point cloud you can measure** — where **every point
carries explicit provenance** (was it truly observed, or filled in by AI?). It runs
**offline on CPU** for the verified core, uses the **GPU (RTX 4060)** only for optional
learned models, and its differentiator is **measurement safety**: a click-two-points
distance in real-world metres, with a trust map that separates surveyed-grade geometry
from AI-inferred fill.

**The moat (validated this session):** a **monocular depth prior (Depth Anything V2)** is
fused with classical Structure-from-Motion to densify the sparse single-pass cloud, and
those added points are tagged **AI-assisted** and excluded from measurement by default —
the honest answer to "how do we know the AI didn't hallucinate that wall?"

**Headline proof points:**
- **Real drone video → dense 3D of buildings** (Zurich Urban MAV): 70/70 frames, 29,879 pts.
- **Accuracy vs a laser scanner** (ETH3D + Faro GT): **measured geometry 8.9 cm median**.
- **Dimensional accuracy** on ground-truth synthetic: **4.70%**, sub-metre GPS.

---

## 2. What it does (the pitch)

> "Give us one flat pass of a drone — no slow orbits, no ground-survey team — and we hand
> you a **measurable** 3D model of the site."

Live demo flow: play a drone clip → the pipeline reconstructs → fly through the 3D model →
click two points to measure a real-world distance → toggle the **Trust Map** (green =
observed, purple = AI-inferred) → close on NTRO value: rapid recon, disaster-damage
assessment, border & infrastructure mapping, instant digital twins.

---

## 3. Technical architecture

```
reconstruction/   drishti_recon package — the CV pipeline (importable, tested)
backend/          FastAPI + SQLite + SSE job queue (serves the built SPA at :8000)
frontend/         React + TypeScript + Vite + Three.js viewer
eval/             ground-truth evaluation harness (ATE / scale / cloud / dimensional / laser-GT)
sample_data/      synthetic scene generator (real ground truth, no download)
tests/            pytest suite (31 passing)
docs/             README, EVALUATION, DEMO, OPTIONAL_MODELS, TELEMETRY, TROUBLESHOOTING
```

**Pipeline stages** (each a testable module): ingestion → telemetry → frames → frame-quality
→ sync → keyframes → masking → **SfM** → **densify (depth prior)** → georegistration (Sim3
to GPS) → fusion (+ provenance) → mesh → quality report → exports.

**Engines:** `opencv` (verified, CPU-only, always works — features → essential matrix →
triangulation → PnP → track fusion) and `colmap` (exhaustive matching, best for
wide-baseline surveys and small-baseline video). Metric scale from a robust **Sim(3)
GPS→ENU** alignment.

---

## 4. Feature status (everything)

| Feature | Status | Notes |
|---|---|---|
| Classical SfM (OpenCV, CPU) | ✅ | The verified path — no COLMAP/CUDA/weights needed |
| COLMAP engine | ✅ | Exhaustive matching; best for surveys + small-baseline video |
| GPS Sim(3) georeferencing + metric scale | ✅ | scale source labelled (gps / rtk / relative) |
| **Depth-prior densification (Depth Anything V2, GPU)** | ✅ | The moat — fills single-pass holes |
| **Provenance / Trust Map** | ✅ | observed-high/low, AI-assisted, dynamic-excluded, unobserved |
| Measurement tools (point/distance/height/area) | ✅ | real WGS84 coords; measures observed geometry by default |
| Measurement safety (AI points excluded) | ✅ | "Include inferred geometry" is opt-in |
| **Splat surface render mode (photorealistic)** | ✅ | soft gaussian sprites → continuous surface |
| **Free 360° rotation** | ✅ | TrackballControls (arcball) |
| **No-GPS / relative-scale mode** | ✅ | reconstructs shape from video without telemetry |
| Keyframe floor (robustness) | ✅ | ≥30 keyframes so slow/hover flights don't starve SfM |
| Dynamic-object masking (semantic, GPU) | ✅ | optional; auto-uses CUDA |
| **H.264 playable video encoding** | ✅ | assembled clips play in any browser/player |
| Mesh export (Open3D Poisson → glb) | ✅ | |
| Exports: PLY / LAS / glb / GeoJSON / CSV / report | ✅ | |
| Backend: FastAPI + SSE live progress | ✅ | job queue, per-project storage |
| Frontend: React + Three.js workspace | ✅ | provenance layers, trajectory, keyframe timeline |
| **Eval harness (ATE / scale / cloud / dimensional)** | ✅ | gauge-free, honest metrics |
| **Accuracy vs LASER ground truth (ETH3D)** | ✅ | 8.9 cm median on measured geometry |

**Honestly scoped / future work:**
- **Full 3D Gaussian Splatting training** (we ship a splat *render* of the dense cloud, not a
  trained 3DGS model).
- **Depth-assisted registration** (using learned depth to *register* cameras, not just
  densify) — research-grade; we delivered the pragmatic keyframe-floor fix for the failure
  mode instead.
- Optional: expose no-GPS mode explicitly in the wizard UI; depth metric for TartanAir.

---

## 5. Results (all reconstructions this session)

| Scene | Input | Engine | Registered | Points (obs / AI) | Reproj | Scale / accuracy |
|---|---|---|---|---|---|---|
| **Zurich Urban MAV** | real drone **video**, 70 frames | COLMAP + depth | **70/70** | 5,692 / 24,187 | 0.451 px | GPS, align 0.51 m — **dense buildings** |
| **Waterbury DENSE** | 50 real aerial photos | COLMAP + depth | 35/50 | 5,579 / **498,055** | 0.306 px | GPS, align 1.27 m |
| Real Drone Mapping (aukerman) | 50 real aerial photos | COLMAP | 50/50 | 9,030 | 0.223 px | GPS, align 1.74 m; **measured 38.146 m** |
| **ETH3D terrace (accuracy)** | 23 real photos | COLMAP + depth | 23/23 | 2,078 / 56,720 | 0.359 px | **8.9 cm median vs laser scan** |
| Synthetic self-test (eval) | rendered GT scene | opencv | 38/38 | ~15k | 0.15 px | **ATE 0.24 m, scale 0.35%, dim 4.70%** |
| Bellus (user data) | 61 forest photos | COLMAP | 5/61 | 149 / 92k | 0.390 px | forest canopy — hard for SfM (honest) |
| Milan DJI (single-pass grass) | real drone video | opencv | 2/38 | — | — | forward pass over grass — degenerate (honest) |

**What registers well:** structured scenes with rigid texture + parallax — wide-baseline
aerial surveys of roads/buildings, or close-range urban video with lateral motion.
**What fails (honestly reported):** forward passes over low-texture (grass), near-static
hover, uniform forest canopy.

---

## 6. The honesty / trust model (the wedge)

- **Every point carries provenance:** observed-high (green), observed-low (yellow),
  AI-assisted (purple), dynamic-excluded (red), unobserved (grey).
- **Measurements use observed high-confidence geometry by default** — AI-inferred points are
  opt-in ("Include inferred geometry").
- **Alignment residual ≠ accuracy** — the GPS-consistency residual is reported separately,
  never dressed up as independent accuracy.
- **Scale is labelled by source** — ordinary GPS is metre-level; RTK/PPK labelled as such;
  no-GPS runs are labelled "relative (not metric, not georeferenced)".
- **Capabilities are probed live** — the UI only claims engines actually installed.
- **Proven:** on ETH3D, observed geometry is **8.9 cm** vs a laser scan while AI-inferred is
  ~51 cm — which is exactly why measurements stay on the green.

---

## 7. How to run

**Environment:** conda env `jupyter_env` — `C:/Users/saira/anaconda3/envs/jupyter_env/python.exe`
(has fastapi, cv2, torch 2.7.1+cu118 with CUDA on the RTX 4060, open3d, laspy, transformers,
imageio-ffmpeg, py7zr; COLMAP via pycolmap). No system ffmpeg/COLMAP needed.

```bash
# 1) reconstruction package + backend (serves the built UI at :8000)
pip install -e reconstruction
cd backend
export DRISHTI_DATA_DIR=".../drishti3d/data"
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000

# 2) frontend (already built into frontend/dist; rebuild after edits)
cd frontend && npm install && npm run build      # or: npm run dev  (proxies /api)

# 3) demo dataset (no download): renders a synthetic scene with real ground truth
python sample_data/generate_sample.py sample_data/synthetic

# 4) ground-truth benchmark — no download
python -m eval.run_eval --self-test

# 5) score real datasets (auto-detects ODM / TartanAir / ETH3D / TUM)
python -m eval.run_eval --root eval_data
```

Open `http://127.0.0.1:8000`. New reconstruction → upload video (+ optional telemetry) →
watch live progress → explore/measure the 3D model. Toggle **Depth-prior densification**,
**Splat surface**, **Trust Map**, and drag to rotate freely.

**GPU:** verified SfM core stays CPU (reproducible). GPU is used only for the depth prior and
semantic masking (`DRISHTI_DEVICE=cpu|cuda`, `DRISHTI_DEPTH_MODEL` to pin the checkpoint).

---

## 8. Datasets used / verified

- **Zurich Urban MAV** (UZH-RPG) — real low-altitude drone video + GPS; 200 MB sample
  `download.ifi.uzh.ch/rpg/AGZ_data/AGZ_subset.zip`. Undistort the GoPro fisheye first.
- **ETH3D** (multi-view, laser GT) — `www.eth3d.net/data/<scene>_dslr_undistorted.7z` +
  `_dslr_scan_eval.7z`. Poses in COLMAP `images.txt`; GT clouds = binary xyz float32 PLY.
- **OpenDroneMap** sample sets — `odm_data_aukerman`, `odm_data_waterbury` (buildings),
  `odm_data_zoo`, `odm_data_bellus` (forest). GPS via EXIF / `gps_check.csv`.
- **Synthetic generator** (`synth.py`) — real ground truth, no download.
- Reference (unused/blocked): UseGeo (UAV+LiDAR) — server SSL cert expired, not used;
  WildUAV — gated, 16–175 GB.

---

## 9. Key files & locations

- Pipeline: `reconstruction/drishti_recon/pipeline.py` (+ `sfm.py`, `colmap_adapter.py`,
  **`depth_prior.py`**, `fusion.py`, `provenance.py`, `geo.py`, `keyframes.py`, `masking.py`).
- Backend: `backend/app/` (`routers/processing.py`, `jobs.py`, `schemas.py`).
- Frontend: `frontend/src/` (`PointCloudViewer.tsx`, `views/Workspace.tsx`, `Wizard.tsx`,
  `Monitor.tsx`, `api.ts`).
- Eval: `eval/` (`cases.py`, `harness.py`, `metrics.py`, `report.py`, `run_eval.py`).
- Data / projects: `drishti3d/data/projects/<id>/artifacts/` (cloud.npz, viewer.json,
  trajectory.json, mesh.glb, quality_report.json, PLY/LAS/GeoJSON/CSV).
- Session helper scripts (scratchpad): `prep_zurich.py`, `resubmit_zurich.py`,
  `submit_bellus.py`, `eth3d_eval.py`, `submit_mission.py`, `submit_video.py`,
  `build_report.py`.
- Docs: `docs/EVALUATION.md`, `docs/demo_report.html`; artifact demo report:
  `https://claude.ai/code/artifact/da4cf2d9-2385-4608-ae24-c380b53e3eec`.

---

## 10. Known limitations (state them in the pitch)

1. **Registration, not densification, is the hard part.** The depth prior densifies *around*
   cameras that already registered; it cannot rescue scenes classical SfM can't register at
   all (forward-pass grass, hover, uniform forest).
2. Verified path is **sparse SfM** (thousands of points); the splat mode makes it *look*
   continuous; density comes from the depth prior.
3. No-GPS runs are **relative scale** — shape only, not metric or georeferenced.
4. Splat render ≠ trained 3D Gaussian Splatting (it's a gaussian-sprite render of the cloud).

---

## 11. Current runtime state

- Backend server running (idle) at `http://127.0.0.1:8000`, serving 12 completed projects.
- Frontend rebuilt (splat toggle + free rotation) — reload the browser to pick it up.
- Backend code has no-GPS support — **restart the server** to enable the no-GPS API path.
- All 31 tests pass; nothing is actively computing.
```
