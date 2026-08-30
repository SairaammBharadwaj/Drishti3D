# Demo script (5 minutes)

A judge-facing walkthrough that shows a **real** reconstruction and honest
uncertainty — no hardcoded model.

## 0. Prep (once)
```bash
pip install -e reconstruction && pip install open3d laspy -r backend/requirements.txt
python sample_data/generate_sample.py sample_data/synthetic
(cd backend && uvicorn app.main:app)      # terminal 1
(cd frontend && npm install && npm run dev)  # terminal 2
```
Open http://localhost:5173.

## 1. Capabilities (10s)
On the dashboard, point out the **capabilities strip**: the classical OpenCV SfM
engine is always available; COLMAP / MASt3R-SLAM / VGGT show as optional and
*honestly unavailable* unless installed. Nothing is faked.

## 2. New mission (45s)
`New mission` → name it → upload `synthetic_flight.mp4` and
`synthetic_telemetry.csv` → (optional) leave intrinsics blank to show the
system estimates and *warns* → **Balanced** preset → **Process**.

## 3. Processing monitor (60s)
Watch staged progress over SSE: ingestion → quality → keyframes → **SfM** →
georegistration → fusion → report. Note the honest elapsed time and any
warnings (e.g. the intrinsics-estimated notice).

## 4. Analysis workspace — the memorable moment (2 min)
- The point cloud is a genuine triangulated reconstruction of the scene.
- Toggle **True colour ↔ Provenance**: green = high-confidence observed, amber =
  low-confidence. Toggle provenance layers on/off.
- **Measure** the building width/height: click two points → the app returns a
  metric value with a confidence note. Compare against the known reference
  (12 m wide / 9 m tall in the synthetic scene).
- Flip on **"include inferred geometry"** and show the warning that appears when
  a measurement touches non-observed geometry — this is the product's thesis.
- Show the 2D trajectory mini-map (GPS track vs recovered camera path).

## 5. Report + exports (45s)
Open **Report**: registered keyframes, reprojection-error stats, GPS-alignment
RMSE (with the *"residual is not independent accuracy"* caveat), and — because
this is the synthetic fixture — an **independent dimensional-accuracy table**
computed against ground truth. Export **PLY / GLB / GeoJSON / HTML report**.

## Talking points
- One safe drone pass → measurable 3D intelligence, fully offline.
- The wedge vs Pix4D/ODM: telemetry-aware single-pass handling, explicit
  observation provenance, measurement safeguards, and reproducible evidence.
- We never claim centimetre accuracy without ground-truth evidence.
