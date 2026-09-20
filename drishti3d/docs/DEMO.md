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

## Inference presentation page

Open **Inference demo** in the top navigation (`/demo`), then select a mission.
You can also use **Present inference** on a mission card.

1. Play the original capture in the embedded video player.
2. Click **Generate 3D & metrics** for an unprocessed mission. The page follows
   the real job and automatically opens the results when it finishes. This uses
   the balanced OpenCV pipeline with optional mesh export; runtime depends on
   footage and hardware. Upload and calibration are available under **New reconstruction**.
3. For a completed mission, **Reveal 3D & metrics** opens its saved artifacts.
   This is explicitly labelled presentation playback, so you can prepare a
   reconstruction before presenting without implying instant inference.
4. Rotate the point cloud and switch to **Evidence colours**. Show the point
   count, camera registration, reprojection error, runtime, frame selection,
   geometry, provenance, and GPS fit. Independent accuracy appears only when
   the run report contains a ground-truth evaluation.
5. Open **Measure in workspace**, the full report, or generated exports.
   **Replay original** returns to the video; **Fullscreen** expands the demo.

Without established metric scale, the presentation suppresses metre-based
model dimensions and spacing. GPS fit residuals are labelled separately from
independent accuracy. Browser-unsupported video codecs have a source download
fallback. The 3D view requires WebGL and displays the API's preview point cloud;
exported artifacts may contain more points.

### Gymnasium capture: use the continuous shot

The downloaded `data/real_drone/gymnasium_neubiberg.webm` is a 129-second
edited montage. Use `data/real_drone/gymnasium_single_pass.mp4`, its first
63.5 seconds, for the single-pass demo. The full montage produced only three
output points and 2/40 registered keyframes in the September 15 UI run.
Processing completion alone does not establish reconstruction success.

The recovery mission is named **Gymnasium — continuous pass (COLMAP)** and
uses the installed COLMAP engine on the trimmed clip, with no telemetry and
no AI densification. Its point cloud is a sparse reconstruction at relative
scale. Its description identifies the input segment and engine; the original
failed run remains available for comparison. The UI flags runs with fewer
than ten output points or three registered cameras as insufficient geometry;
passing that basic check is not a quality or accuracy certification.

## Original dense prototype in interactive 3D

Open `/prototype` (top navigation: **Dense prototype**). This loads the actual
saved Gymnasium experiment assets used by the prototype: 838,658 AI-assisted
dense points and a separate 33,624-point measured layer. No inference runs
when the page opens. Drag to rotate, scroll to zoom, right-drag to pan. The
**Demo view**, flight camera presets and **Overview** recover useful views.
The comparison video is expandable below the viewer.

The browser assets live in `frontend/public/prototype/` and are included in
production builds. Regenerate with `.venv/bin/python scripts/prepare_prototype.py
/path/to/experiment`. Required source files are `gym_dense.npz`,
`gym_dense_aligned.npz`, and `gym_measured.npz`. The script inverts their saved
alignment to bring measured points into the original dense-camera frame.
Coordinates have relative scale, no GPS. Evidence colours identify source
layers, not validated point accuracy. MASt3R assets were generated for research
with a noncommercial checkpoint; see `reconstruction/drishti_recon/dense3d.py`.
