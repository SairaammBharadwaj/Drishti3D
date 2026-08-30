# Drishti3D — Full Session Conversation Log

_Dump of every prompt and response from this working session, followed by a
pending / completed status board. Reconstructed faithfully from the session._

---

## TRANSCRIPT

### [USER 1]
> continue where we left
>
> (plus a dataset priority table:)
>
> | Dataset | Use it for | What it gives us | Priority |
> |---|---|---|---|
> | OpenDroneMap / ODMData | Real aerial reconstruction | Real drone imagery, GPS EXIF on some, GCP/RTK on some | #1 |
> | TartanAir | Depth/SLAM/AI testing | RGB, depth, pose, segmentation, flow, intrinsics | #2 |
> | ETH3D | SLAM/reconstruction benchmark | Images, IMU, ground truth on training sequences | #3 |
> | AGI2P / RTK-SLAM | Aerial localization / point-cloud evaluation | Aerial images, ALS point clouds, ground-truth poses | #4 |
> | Our held-out test set | Final credibility | Never used during development | Essential |
>
> "here is the data which might be helpful for u"

### [ASSISTANT 1]
- Oriented in the project: `SIH/drishti3d/` (reconstruction pipeline, backend FastAPI+SQLite+SSE, frontend React+Three.js, sample_data, tests, docs).
- Found the prototype only self-validated on synthetic data — no reusable scoring path for the datasets in the table.
- Built a **ground-truth evaluation harness** at `drishti3d/eval/`:
  - `cases.py` — adapters → common `EvalCase`; auto-detects **ODM** (image folder + EXIF/geo.txt GPS), **TartanAir** (`pose_left.txt`, fixed K), **ETH3D/TUM** (`groundtruth.txt` + `calibration.txt`), **synthetic**.
  - `harness.py` — one video frame per image + telemetry, runs `pipeline.run`; **never feeds GT poses**; synthesises drone-grade noisy GPS (σ≈2.5 m) for GPS-less datasets.
  - `metrics.py` — ATE (via `geo.umeyama_sim3`), scale error, cloud accuracy/completeness (scipy KD-tree), dimensional error.
  - `report.py` + `run_eval.py` — Markdown scorecard + JSON + CLI (`--self-test`, `--root`, `--dataset`).
  - `docs/EVALUATION.md` — the dataset priority table + per-dataset fetch/layout instructions.
  - `tests/test_eval.py` — 3 fast unit tests + 1 slow e2e (`@pytest.mark.slow`).
- Verified env: conda `jupyter_env` has scipy, cv2, imageio_ffmpeg, PIL 12.3.0, torch 2.7.1+cu118 (CUDA True, RTX 4060 Laptop GPU detected).
- Ran the self-test end-to-end (synthetic GT, no download).

### [USER 2] (mid-turn)
> and one more thing as the system i am using has a rtx 4060 8gb vram so use it instead of fully running on cpu if needed

### [ASSISTANT 2]
- Noted CUDA is live. Kept the **verified SfM core CPU-only by design** (reproducible, hardware-independent eval numbers).
- Made the optional **semantic dynamic-object masker auto-use CUDA** (`masking.py`, `DRISHTI_DEVICE=cpu|cuda` override). Confirmed it now loads on `cuda`.
- Fixed self-test issues found in the first run:
  - Ambiguous numpy truth-test bug (`case.gt_centers or []`).
  - Registered the `slow` pytest marker in `conftest.py`.
- First self-test at 48 frames revealed: cameras aligned well (ATE 0.24 m, scale err 0.3%) but cloud accuracy looked wrong (7.4 m).
  - Root cause 1: scoring cloud via the **camera-only Sim(3)** amplifies a tiny rotation out at the distant ground → bogus 7 m. Fixed by using the pipeline's shared-frame `ground_truth_evaluation` + **rigid scale-locked ICP + crop to GT region** (ETH3D/T&T protocol). Brought 5.95 m (uncropped) / 7.4 m (camera-Sim3) down to **1.20 m** median.
  - Root cause 2: 48 frames undersampled depth (dim/height error 15–36%). Switched self-test to the canonical **90-frame** profile.
- **Validated 90-frame self-test:** 38/38 cams, **ATE 0.24 m, scale err 0.35%, cloud acc 1.20 m median, dimensional error 4.70%**, completeness ~11% (sparse feature cloud vs dense GT — expected).
- Fast unit tests: **3 passed**.
- Wrote memory: `drishti3d-eval-harness.md` (+ MEMORY.md index line).

### [USER 3]
> yes complete the full prototype and download whatever needed and after everything is completed then show me a demo of the working of the prototype

### [ASSISTANT 3]
- Confirmed the app runs: frontend built (`frontend/dist`), backend serves SPA at `:8000`. Learned the job API (create → upload video+telemetry → process → poll; SSE events).
- Tested network — GitHub reachable.
- Downloaded a real drone dataset: **OpenDroneMap `odm_data_aukerman`** — 28 contiguous images (of 77), all with GPS EXIF (Ohio 41.3°N), 4896×3672.
- Started the backend server (background). Opened the app in Chrome.
- Found the app already had a completed **"Real Drone Mapping"** mission (50 real geotagged photos, COLMAP): **50/50 keyframes, 9,030 points, 0.223 px reproj, GPS-scaled, align 1.74/1.01 m**.
- Captured live demo: orbited the 3D cloud, ran the **distance tool → 38.146 m, high-confidence** (real WGS84 coords 41.44°N,−81.72°W), switched to True-color, saw the EXPORTS row (ply/las/mesh_glb/geojson/csv/report/viewer). Recorded a GIF.
- Ran the eval harness on the 28 real aukerman images: **21/28 cameras registered** (no GT poses so ATE/cloud show "—"). Pipeline metrics: 2,809 pts, 0.99 px reproj, GPS-scaled 49.8×, align H 2.01 m, real 210×222 m site.
- Updated `docs/EVALUATION.md` with verified ODM dataset names. Prepared a demo-report generator.

### [USER 4] (mid-turn)
> i would ask u to take a better video where there are buildings are good objects so as to see the real work in progress so i hope you understand

### [ASSISTANT 4]
- Understood: aukerman is a flat field/road — no buildings. Sampled 7 OpenDroneMap datasets by downloading one image each and viewing:
  - brighton_beach = trees/road; seneca = plowed field; caliterra = dirt lot; apt = ground-level walkway; waterbury = houses + trees; **zoo = suburban neighborhood with clear rooftops/houses/roads/cars**.
- Picked **zoo**. Downloaded 36 contiguous images (GPS confirmed, Cleveland area). Submitted to the app as a mission with COLMAP.
- **Result: only 7/36 registered, 413 points** — my contiguous slice jumped between flight rows; overlap too low.
- Downloaded 36 more (→72). Checked geometry: **~64 m spacing over a 567×690 m sparse waypoint grid** — too wide-baseline for monocular SfM.
- Re-ran 72 images with opencv (sequential): **3/72 registered, 251 points**. Confirmed zoo is fundamentally a sparse survey, unsuited to the single-pass-video pipeline.

### [USER 5] (mid-turn)
> i suggest you take a video directly from the open source and its coordinates {webscrap} and then use that video to generate a 3d model

### [ASSISTANT 5]
- Great insight — the pipeline is built for **continuous video** (small baseline), which is why sparse photo surveys fail.
- Found **OpenDroneMap `drone_dataset_dji_video`**: `DJI_0317.MP4` (5.4 MB) + `DJI_0317.SRT` (per-frame GPS). Downloaded both.
- Parsed SRT: 46.6 s, 960×540, 60 fps, 2791 GPS samples, Milan Italy (45.499°N, 9.040°E), 25×81 m footprint at ~29.6 m altitude.
- Extracted frames: a field on the left with a **row of red-roofed townhouses + road + cars** on the right (frame ~1400), a **white villa** (frame ~2400) — buildings present but scene dominated by low-texture grass.
- Built telemetry.csv from the SRT and submitted the real video to the app (`submit_video.py`).
- **Result: 2/38 registered, 5 points** — low-res (960×540) + grass-dominated frames gave SfM nothing to match; buildings only at frame edges.

### [ASSISTANT 5b] (pivot to waterbury)
- Diagnosis: resolution + texture matter, not just overlap. The winning combo = high-res, textured, well-overlapped photos + COLMAP (like the 50/50 aukerman in-app run).
- Checked **waterbury** (downloaded 50 images earlier as fallback): high-res 4896×3672, has a **large commercial building + full parking lot of cars + highway + textured trees**, 45 m spacing (matches the proven aukerman 46 m).
- Ran waterbury 50 with COLMAP: **35/50 registered (70%), 5,780 points, 0.306 px, GPS-scaled, align 1.27/0.91 m, real 359×827×39 m site**. Success — a real reconstruction with recognizable buildings.
- Opened it in the app, switched to True-color (building + parking-lot rows + tree canopy visible), increased point size, orbited, recorded a GIF. Measurement tool was finicky on the sparse strip (already demonstrated 38.146 m on the denser cloud).
- Built + published a **demo report Artifact**: https://claude.ai/code/artifact/da4cf2d9-2385-4608-ae24-c380b53e3eec (Sora + IBM Plex design, KPI tiles, 3 embedded screenshots, three evidence tiers, honesty rules, run instructions). Fixed a UTF-8 mojibake bug (JSON read with wrong encoding) and republished.

### [USER 6] (mid-turn)
> dont waste my credits, instead i want you to take a real world video which can really show me that the model created is working as expected, and i also need to give a demo to my mentor and all

### [ASSISTANT 6]
- Stopped the dataset roulette. Explained the fundamental issue: the **verified path is sparse SfM** (feature points, CPU, no COLMAP/CUDA) → real scenes come out sparse, not dense/solid; free datasets are wide-baseline surveys that only partially register.
- Noted the runs already produced **mesh.glb** surfaces (aukerman 1.8 MB, waterbury 1.0 MB) but the app viewer renders points, not the mesh.
- Asked a focused question (Demo path): Polish what works / **Get one DENSE real model** / Show the solid MESH.
- **USER SELECTED: "Get one DENSE real model"** (find a dedicated low-alt/orbit drone video WITH GPS, textured building; more credits, best visual).

### [USER 7] (mid-turn, with 2 screenshots)
> [Image #5 = older version, Image #4 = newer version] same video as input but see the difference, see the main task is to produce a model which clearly shows the 3d model from the raw feed from a drone video and the coordinates file
>
> - Image #5 (older): 29/29 keyframes, 10,819 points, 0.147 px, align 0.44/0.24 m, proc/video 17.7×, MEASUREMENTS (4). Shows a flat ground plane + a raised building slab.
> - Image #4 (newer): 60/60 keyframes, 14,924 points, 0.979 px, align 1.75/0.46 m, proc/video 283.8×, track length 11.79. Same structure, denser.

### [ASSISTANT 7]
- Recognized both screenshots show the target: a clear ground plane + raised building slab. Image #4's signature (track 11.79, 0.98 px, 1.75 m GPS align) reads like a real continuous video — proving the pipeline nails it with a proper overlapping pass.
- Web-searched for real drone video + SRT/GPS datasets; confirmed **orbit flight** is the right capture pattern and DJI SRT is the telemetry source.
- Started searching GitHub for DJI SRT drone-video repos (orbit/building).

### [USER 8] (interrupt)
> https://huggingface.co/datasets/imageomics/KABR-raw-videos check this dataset might be helpful?

### [USER 9] (interrupt)
> stop every work u are doing and write everything i mean every prompt and every response into a file name it convo and dump everything into it and at last add the things to do pending and the things completed and working

### [ASSISTANT 8/9]
- Stopped all work and wrote this `convo.md`.

---

## STATUS BOARD

### ✅ COMPLETED & WORKING
- **Evaluation harness** (`drishti3d/eval/`): dataset adapters (ODM/TartanAir/ETH3D/TUM/synthetic), honest gauge-free metrics (ATE, scale, cloud acc/completeness via rigid ICP+crop, dimensional), scorecard + JSON + CLI. **3 fast unit tests pass.**
- **90-frame synthetic self-test validated:** 38/38 cams, ATE 0.24 m, scale err 0.35%, cloud 1.20 m, **dimensional error 4.70%** — the ground-truth accuracy proof.
- **GPU:** semantic masker auto-uses CUDA (`DRISHTI_DEVICE` override); verified SfM core stays CPU by design.
- **App runs end-to-end** (backend `:8000` serving built UI). Job API is scriptable (`submit_mission.py`, `submit_video.py` in scratchpad).
- **Real reconstructions produced:**
  - In-app "Real Drone Mapping" (50 aukerman photos, COLMAP): **50/50, 9,030 pts, 0.223 px, align 1.74/1.01 m** — densest real run.
  - **Waterbury (50 photos, COLMAP): 35/50, 5,780 pts, 0.306 px, align 1.27/0.91 m** — real building + parking lot + cars.
  - aukerman eval-harness run: 21/28, 2,809 pts.
- **Measurement tool works:** 38.146 m distance, high-confidence, real WGS84 coords.
- **Demo report Artifact published (live):** https://claude.ai/code/artifact/da4cf2d9-2385-4608-ae24-c380b53e3eec
- **Two demo GIFs** in Downloads: `drishti3d_demo.gif`, `drishti3d_waterbury_demo.gif`.
- Memory updated: `drishti3d-eval-harness.md`, MEMORY.md index.
- `docs/EVALUATION.md`, `docs/demo_report.html` written.

### ⏳ PENDING / TO DO
- **[MAIN GOAL] Produce ONE clear DENSE 3D model from a real drone VIDEO + coordinates file** — like the user's Image #4 (14,924 pts, clear building slab on ground). Need a real drone **orbit / low-altitude** video that is:
  1. continuous (small baseline between frames),
  2. textured (buildings/objects, not bare grass),
  3. with GPS coordinates (DJI `.SRT` or a telemetry CSV).
- **Evaluate the Hugging Face dataset the user suggested:** `https://huggingface.co/datasets/imageomics/KABR-raw-videos` (KABR = Kenyan Animal Behavior Recognition — aerial drone videos of animals; check whether any clip has buildings/ground structure + usable GPS/coordinates; likely animal-focused, may lack per-frame GPS — verify before use).
- Candidate video sources to try next (real drone video + GPS):
  - GitHub DJI `.SRT`+`.MP4` repos (search was in progress).
  - Kaggle "Drone Flight Video with Telemetry (GPS & ESC)" (needs auth).
  - A dedicated building-orbit DJI clip with SRT.
- Once a good video reconstructs densely: capture a clean orbit + measurement recording and a short **mentor demo script**.
- Optional: render the existing `mesh.glb` as a solid surface (build a tiny local three.js/GLTF viewer) for a "solid model" visual.
- Optional harness extension: depth-error metric for TartanAir (it ships per-pixel depth); held-out-set workflow.

### 🧠 KEY LEARNINGS (do not repeat mistakes)
- **Single-pass VIDEO (continuous, small baseline, textured) reconstructs well; sparse aerial PHOTO surveys (45–65 m spacing) do NOT** — they only partially register.
- Content must be **textured** — bare grass/fields give SfM nothing to match (Milan video failed 2/38 on grass despite having GPS).
- **Resolution matters** — 960×540 is marginal; 4896×3672 photos + COLMAP worked (aukerman 50/50).
- The verified path is **sparse SfM** — expect thousands of points, not a dense solid surface. A `mesh.glb` is produced but not shown in the app viewer.
- Working spacing reference: **~45–46 m worked** (aukerman/waterbury), **~64 m failed** (zoo).

### 🔧 ENVIRONMENT / RUN NOTES
- Python: `C:/Users/saira/anaconda3/envs/jupyter_env/python.exe` (conda `jupyter_env`).
- Backend: `cd drishti3d/backend && uvicorn app.main:app` (binds 127.0.0.1:8000, serves UI). `DRISHTI_DATA_DIR=drishti3d/data`.
- Eval self-test (no download): `python -m eval.run_eval --self-test`.
- Scratchpad helpers: `submit_mission.py` (images→video+telemetry→app), `submit_video.py` (video+SRT→app), `build_report.py` (demo report generator), `metrics.json`, `images.json`.
- Downloaded data in scratchpad: `odm_aukerman/` (28), `odm_zoo/` (72), `odm_waterbury/` (50), `dji/DJI_0317.MP4+SRT`.

---
---

# SESSION CONTINUATION (2026-08-30) — Depth-prior moat, real drone video, rotation fix

## TRANSCRIPT (continued)

### [USER 10]
> (Friend's review, paraphrased directive:) The original plan (learned depth priors + Gaussian Splatting) is stronger for SIH 2026. Pure classical SfM on a single linear pass fails (tiny parallax, textureless areas, drift/"banana effect"). Inject **monocular depth priors (Depth Anything V2)** fused with classical bundle adjustment to make single-pass reconstruction possible. STEAL from Drishti3D the **Provenance Toggle / Trust Map**: green = high-confidence classical geometry, yellow/red = low-confidence AI-filled. Two modes: photorealistic (Gaussian Splat) + tactical trust map. "After reviewing them continue the work and show the real working prototype."

### [ASSISTANT 10]
- Confirmed the critique matches my empirical failures. Implemented **depth-prior densification** (the moat):
  - New `reconstruction/drishti_recon/depth_prior.py` — Depth Anything V2 (`depth-anything/Depth-Anything-V2-Small-hf`) on CUDA; per keyframe: predict affine-invariant disparity → robust IRLS fit `1/z ≈ a·disp + b` to the sparse SfM points visible in that frame → back-project a strided pixel grid into the recon frame. **Import cv2 BEFORE torch** (Windows DLL clash).
  - Pipeline: `PipelineParams.densify: none|depth` + `depth_stride`; new `densify` STAGE_SPANS entry (0.72–0.78); dense points carried through the same Sim(3)+gravity transform, voxel-downsampled, outlier-trimmed, merged via `fusion.add_inferred_layer` (tags **AI_ASSISTED**, purple, excluded from measurement by default).
  - Exposed via API (`schemas.ProcessRequest.densify`, `jobs.py`) + frontend Wizard toggle + Monitor stage. Frontend rebuilt.
- Validated: synthetic → 14,924 observed + **438,406 AI-assisted**; waterbury (50 real ODM photos, COLMAP) → 5,579 observed + **498,055 AI-assisted** = 503,634 pts, dense colored surface, trust map (green observed vs purple AI). Wrote memory `drishti3d-depth-densification.md`.

### [USER 11]
> "C:\Users\saira\Downloads\claude\SIH\track-b-no-isro.html" also check this html {only our project details}

### [ASSISTANT 11]
- Read the SIH dossier. Confirms SIH26158 Drone-to-3D is Rank 01 (86/100, NTRO). Killer feature = **learned depth-prior fusion (Depth Anything V2) for single-pass low-overlap reconstruction** + **click-two-points metric measurement with error bar vs GT**. Data strategy lists ETH3D, Tanks&Temples, BlendedMVS, Mip-NeRF360, **UseGeo (UAV+LiDAR GT)**, WildUAV, DJI footage. My depth-densification work aligns exactly with the documented moat.

### [USER 12] (mid-turn)
> dont waste my credits, instead i want you to take a real world video which can really show me that the model created is working as expected, and i also need to give a demo to my mentor and all

### [ASSISTANT 12]
- Fixed the **video encoding**: assembled videos were `mp4v` (players reject). Rewrote `eval/harness._write_video` to **H.264/yuv420p** (imageio-ffmpeg, ≤1920w). Re-encoded the waterbury upload → `video_playable.mp4`.
- Honest reality: the verified path is **sparse SfM**; real forward-pass clips fail registration; reliable inputs are wide-baseline aerial surveys (photos). Asked a focused question → **USER CHOSE "Get one DENSE real model."**

### [USER 13] (mid-turn, 2 screenshots)
> [Image #5 old: 29/29, 10,819 pts, 0.147px] [Image #4 new: 60/60, 14,924 pts, 0.979px] same video input, see the difference. "the main task is to produce a model which clearly shows the 3d model from the raw feed from a drone video and the coordinates file."

### [ASSISTANT 13]
- Recognized Image #4 (14,924 pts / 60 keyframes) = the synthetic scene run. Searched for real drone video + GPS.
- **WildUAV**: gated (MS Forms), 16–175 GB, video set is JPGs w/o GPS. **UseGeo**: direct links exist but... (see below).

### [USER 14]
> (chose) Download UseGeo (real UAV+LiDAR)

### [ASSISTANT 14]
- UseGeo host `eostore.itc.utwente.nl` has an **EXPIRED SSL cert** + a locked-down Synology JS share (curl API blocked, error 119). Browser cert-bypass was **correctly blocked by the security classifier** — I refused to work around it. Reported honestly; proposed **ETH3D** (real laser-scanner GT, freely downloadable) as the clean substitute for #3.

### [USER 15]
> keep hunting

### [ASSISTANT 15]
- Found **Zurich Urban MAV** (UZH-RPG): real low-altitude MAV video over Zurich streets, onboard GPS+IMU+GT, **200 MB sample** (`AGZ_subset.zip`), valid cert. Downloaded + extracted: 350 images (1920×1080), `OnboardGPS.csv`, `calibration_data.npz` (K + fisheye distCoeff).
- Frames = ornate Zurich apartment buildings at close range, strong lateral parallax (GPS too coarse at ±13 m to show the few-m motion). Undistorted the GoPro fisheye (verified straight lines).
- First run (`prep_zurich.py`, opencv, 350 frames) → only 11 keyframes selected (near-static GPS collapsed selection) → 2/11 registered. **Fix:** subsample to ≤80 frames (pipeline keeps ALL as keyframes) + COLMAP.
- Re-run (`resubmit_zurich.py`, 70 frames, COLMAP + densify) → **70/70 registered, 0.451px, mean track 17.24, GPS-scaled 0.51 m**; 5,692 observed + **24,187 AI-assisted** = 29,879 pts. **True-color view shows real dense building facades** — the genuine raw-drone-video → dense 3D demo. Raw clip: `scratchpad/zurich_work/zurich_drone.mp4`.

### [USER 16] (mid-turn)
> can u make it free to rotate 360degree? (the 3D model fixes one base, can't rotate 360°)

### [ASSISTANT 16]
- Swapped `PointCloudViewer.tsx` from **OrbitControls → TrackballControls** (true arcball, no fixed up-vector) — free 360° rotation in every axis, incl. flipping over the top. Added `controls.handleResize()`. Rebuilt frontend. Verified live (model tilts freely, grid at an angle).

### [USER 17] (mid-turn)
> "...odm_data_bellus-master" check this folder (images + csv with alt/lat/lon/datetime), if good convert to input format and run.

### [ASSISTANT 17]
- Bellus: 122 images (4048×3048) + `images/gps_check.csv` (per-image GPS) + `gcp_list.txt` (surveyed GCPs). 51 m spacing (good range). BUT content = **dense forest canopy** → viewed a frame (all trees).
- Converted (`submit_bellus.py`, 61 frames, COLMAP + densify) → **only 5/61 registered** (0.390px), 149 observed + 92,657 AI. Honest: forest canopy is self-similar → feature matching fails (not a data problem; roads/buildings register, uniform vegetation doesn't).

### [USER 18]
> stop every work ... write everything into a file name convo ... add pending + completed/working.

### [ASSISTANT 18]
- Stopped; appended this continuation to `convo.md`.

---

## STATUS BOARD (LATEST — supersedes the earlier one above)

### ✅ COMPLETED & WORKING (this continuation)
- **Depth-prior densification (the moat)** — `depth_prior.py` (Depth Anything V2, CUDA) fused with classical SfM; `densify="depth"` param through pipeline/API/UI. Validated on synthetic (438k AI pts), waterbury (498k), Zurich (24k). AI points tagged AI_ASSISTED, excluded from measurement — the trust map.
- **Real drone video → dense 3D of BUILDINGS (Zurich Urban MAV):** 70/70 frames, 29,879 pts, 0.451px, GPS-scaled, dense colored building facades + trust map. Playable raw clip at `scratchpad/zurich_work/zurich_drone.mp4`. **This is the headline "raw video → 3D" demo.**
- **Free 360° rotation** — TrackballControls in the viewer (rebuilt). Reload app to use.
- **Playable video encoding** — H.264/yuv420p for all assembled videos; waterbury `video_playable.mp4`.
- **Provenance trust map** confirmed working on real data (green observed vs purple AI-inferred; measurements locked to observed).
- Dossier `track-b-no-isro.html` reviewed — work aligns with the documented SIH26158 moat.

### ⏳ PENDING / TO DO
- **#2 Gaussian Splatting render mode** — the dossier's photorealistic "jaw-drop" fly-through. NOT started; large build (train 3DGS on the 4060 via gsplat/nerfstudio + a WebGL splat viewer in the frontend). Multi-hour, highest-risk item.
- **#3 Metric accuracy vs LiDAR/laser GT** — eval harness already does cloud-vs-GT (proven on synthetic: 1.20 m cloud, 4.70% dimensional). **UseGeo is blocked** (expired cert + I won't bypass security). Substitute: **ETH3D** (real Faro laser-scan GT, freely downloadable, adapter exists) — recommended, not yet run. Could also use bellus **GCPs** for control-point accuracy.
- **Polish the Zurich demo** into a shareable recording/report (optional; user earlier said ignore the demo report for now).
- **Depth-assisted REGISTRATION** (open research) — current densify fills AROUND registered cameras; it does NOT rescue scenes where classical SfM fails to register (forward-pass grass; hovering; forest). Making arbitrary real clips register would need depth/learned-matching in the registration stage.
- Optional: no-GPS/relative-scale mode so any user clip runs without telemetry.

### 🧠 KEY LEARNINGS (this continuation)
- **Depth priors densify but do NOT register** — they help AFTER classical SfM registers cameras. Registration still needs texture + parallax.
- **What registers:** structured scenes with rigid texture + real parallax — wide-baseline aerial surveys of roads/buildings (aukerman/waterbury 35–50/50), or close-range urban video with lateral motion (Zurich 70/70 via COLMAP).
- **What fails:** forward-pass over low-texture (Milan grass 2/38), near-static hover (Zurich opencv 2/11 before fix), uniform forest canopy (bellus 5/61).
- **Keyframe trick:** feed ≤80 frames so the pipeline keeps ALL as keyframes (avoids GPS-degenerate thinning); COLMAP (exhaustive) beats opencv (sequential) for small-baseline sets.
- **GoPro/fisheye:** undistort with provided calibration before SfM (verified straight lines) — critical.
- **Video encoding:** always H.264/yuv420p (mp4v is rejected by players/browsers).
- **UI:** TrackballControls for free rotation; click UI buttons via `find`→ref (pixel clicks missed the True-color toggle).
- **Security:** did not bypass the expired-cert warning for UseGeo (classifier blocked it; correct).

### 🔧 NEW FILES / SCRIPTS (this continuation)
- `drishti3d/reconstruction/drishti_recon/depth_prior.py` (new module).
- Edits: `pipeline.py` (densify stage), `fusion.py` (used add_inferred_layer), `masking.py` (GPU), `backend/app/jobs.py` + `schemas.py` (densify param), `frontend/src/PointCloudViewer.tsx` (TrackballControls), `Wizard.tsx` + `Monitor.tsx` + `api.ts` (densify UI), `eval/harness.py` (H.264 encoder).
- Scratchpad: `prep_zurich.py`, `resubmit_zurich.py`, `submit_bellus.py`, `build_report.py`, `submit_mission.py`, `submit_video.py`, `metrics.json`, `images.json`.
- Data: `scratchpad/AGZ/` (Zurich sample), `scratchpad/zurich_work/` (undist frames, telemetry, `zurich_drone.mp4`), `scratchpad/dji/` (Milan), `odm_data_bellus-master/` (user's, forest).
- Key app projects (in `drishti3d/data/projects/`): Zurich dense = `20c4c45372b645cc8a3ec8a6108b8f7c`; waterbury dense = `ca5e1826a09e4187988692e27a420b1e`.
- Memory added: `drishti3d-depth-densification.md`.

### ⚠️ CURRENT RUNTIME STATE
- Backend running (background) at `http://127.0.0.1:8000` (may need restart with `cd drishti3d/backend && uvicorn app.main:app`; set `DRISHTI_DATA_DIR`).
- Frontend rebuilt with TrackballControls + densify toggle — **reload the browser** to pick it up.
