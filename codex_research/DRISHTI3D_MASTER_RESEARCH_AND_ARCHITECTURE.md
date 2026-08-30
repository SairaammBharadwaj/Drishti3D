# Drishti3D: Master Research, Architecture, and Execution Blueprint

> **Problem:** SIH26158 — Single-Pass Drone Video to Accurate 3D Model Generation System  
> **Organization:** National Technical Research Organisation (NTRO)  
> **Prepared:** 27 August 2026  
> **Document status:** Decision-grade engineering blueprint  
> **Intended reader:** A team that must understand, build, demonstrate, test, and defend the system

> **Competition objective:** This blueprint is optimized to maximize the probability of winning Smart India Hackathon, not merely to produce a technically interesting prototype.

---

## 1. Executive decision

Drishti3D should be built as a **confidence-aware, offline-capable photogrammetry platform**, not as a generative “video-to-3D” demo. Its primary output should be a georeferenced point cloud with auditable camera poses, measurements, uncertainty, and provenance. A textured mesh is a secondary output generated only where the observations support it.

The winning technical strategy is a **hybrid, staged pipeline**:

1. A classical, testable path based on calibrated keyframes, feature matching, bundle adjustment, COLMAP/PyCOLMAP, GNSS alignment, and Open3D. This is the source of verified geometry.
2. An optional learned path, preferably VGGT as a preview/initializer and only later MASt3R-SLAM, to recover from weak texture and accelerate previews. Learned results must be aligned to and checked against verified geometry.
3. A separate semantic/motion path that removes dynamic objects and marks sky, water, reflective surfaces, blur, rolling-shutter damage, and unobserved regions.
4. A quality engine that converts residuals and observation geometry into confidence—not an arbitrary AI score.

The core product promise should be:

> “Convert one continuous UAV video and synchronized telemetry into an auditable, metrically scaled 3D reconstruction of the surfaces that were actually observed.”

Do **not** promise that a single pass can reconstruct every side of every object. Do **not** claim centimetre accuracy without RTK/PPK or well-surveyed ground control and independent checkpoints. Do **not** allow AI-completed surfaces to be silently measured.

### Recommended MVP boundary

The MVP is successful when a user can upload one real video and telemetry file, obtain real keyframes and quality metrics, run a real sparse reconstruction, align it into a local metric ENU frame using GNSS, inspect it with the flight path, measure distance/height, see confidence, and export the artifacts and an evidence-based report.

Dense meshing, neural reconstruction, LAS/LAZ, tiled streaming, semantic cleanup, and enterprise orchestration are progressive enhancements. This ordering sharply reduces demonstration risk.

### 1.1 The SIH winning thesis

SIH's published evaluation guidance includes novelty, complexity, clarity, feasibility, practicability, sustainability, scale of impact, user experience, and potential for future progression ([official SIH guidelines](https://sih.gov.in/letters/Guidelines-College-SPOC.pdf)). Drishti3D must therefore be optimized across all of these dimensions simultaneously. A technically difficult pipeline with no convincing operator experience will lose points; a beautiful dashboard with fake geometry will fail technical scrutiny.

The competition thesis is:

> **Drishti3D turns a single operational drone pass into an evidence-backed 3D intelligence product, then tells the operator exactly what is measured, what is uncertain, and what was never observed.**

That sentence should anchor the submission, prototype, pitch, poster, and answers to judges. It directly addresses NTRO's stated challenges—single trajectory, blur/compression, illumination, dynamics, GNSS noise, near-real-time operation, occlusion, and metric accuracy—while offering a credible innovation beyond a standard photogrammetry wrapper.

### 1.2 What will make this entry memorable

Most competing approaches are likely to fall into one of four categories:

1. A COLMAP/OpenDroneMap wrapper with limited original engineering.
2. A neural model demo that creates attractive geometry but cannot defend metric accuracy.
3. A polished command dashboard backed by a precomputed model.
4. An over-scoped platform that fails during the live demonstration.

Drishti3D should occupy a different position:

- **Real reconstruction:** uploaded footage genuinely produces the displayed model.
- **Truth-aware innovation:** observed, weak, inferred, dynamic, and unobserved geometry remain distinct.
- **Operational output:** the result supports coordinates and measurements, not only viewing.
- **Evidence:** the team presents independent checkpoint and known-distance errors.
- **Resilience:** classical CPU-capable reconstruction remains usable without proprietary cloud services or optional AI weights.
- **Mission feedback:** weak coverage becomes actionable repeat-flight guidance.
- **Offline readiness:** sensitive video and coordinates never need to leave the deployment boundary.

The highest-value “wow moment” is not an animated mesh. It is a judge selecting two points on a model produced from the visible input, obtaining a metric distance, seeing its confidence/provenance, and comparing it with independent ground truth.

### 1.3 Competition scorecard

| SIH criterion | What judges must see | Concrete proof |
|---|---|---|
| Novelty | Confidence/provenance-aware reconstruction and mission feedback | Layer toggle, uncertainty map, inferred geometry excluded from measurement |
| Complexity | Real video geometry, synchronization, robust geodesy, masking, 3D web interaction | Architecture, live artifacts, stage logs, transform report |
| Clarity | One problem, one workflow, one measurable outcome | 30-second explanation and clean system diagram |
| Feasibility | A working classical path with optional AI | Live/rehearsed end-to-end run and capability fallback |
| Practicability | Handles real telemetry, weak inputs, failure, and export | Device adapter, warnings, retry, offline bundle |
| Sustainability | Open/interoperable formats, modular adapters, modest infrastructure | PLY/GLB/GeoJSON/CSV, CPU mode, maintainable architecture |
| Impact | Faster mapping after disasters, inspection, and strategic reconnaissance | Time/cost comparison and one strong operational scenario |
| User experience | Operator can understand quality and act without CV expertise | Five-step workflow, meaningful errors, decision-ready report |
| Future progression | RTK/GCP, multi-drone, edge preview, change detection, 3D Tiles | credible phased roadmap with present/future separation |

Every pitch slide and demo action should satisfy at least one row. Features that satisfy none should be postponed.

### 1.4 Three levels of innovation

The proposal should claim innovation at three defensible levels:

1. **Algorithmic:** adaptive keyframes, dynamic masking, hybrid learned/classical initialization, robust weighted GNSS Sim(3), and multi-factor confidence.
2. **Systems:** restartable offline pipeline, artifact lineage, graceful hardware degradation, and consistent coordinate/provenance contracts.
3. **Operational:** measurement-safe layers, quality reporting, and coverage-aware recapture recommendations.

Avoid claiming that SfM, COLMAP, SLAM, or monocular depth was invented by the team. Judges usually reward a novel, integrated solution to the problem more than inflated claims that collapse under questioning.

### 1.5 Winning scope: must, differentiator, and trap

#### Must work flawlessly

- Real upload and telemetry parsing.
- Real adaptive frame extraction and quality rejection.
- Real sparse or dense point-cloud reconstruction.
- GNSS-aligned camera path and metric ENU coordinates.
- Distance and height measurement.
- Confidence/provenance visualization.
- Quality report and standard export.
- Offline-capable processing and meaningful failure messages.

#### Differentiators worth building

- Independent checkpoint accuracy page.
- Dynamic-object cleanup comparison slider.
- Weak-coverage heatmap and suggested next viewpoint/flight segment.
- Synchronized video-frame, camera-frustum, map, and point-cloud inspection.
- Fast preview followed by a verified refinement, visibly distinguished.
- Before/after comparison against ordinary uniform frame sampling.

#### Traps to avoid

- Spending the schedule on photorealistic mesh texture before metric alignment works.
- Integrating several large models without one reliable baseline.
- Showing fabricated accuracy, progress, point clouds, or “AI confidence.”
- Claiming occluded geometry is reconstructed truth.
- Depending on internet map tiles or model downloads during judging.
- Building authentication, Kubernetes, or administrative screens that judges never need.
- Presenting twenty use cases rather than proving one operational scenario deeply.

---

## 1A. SIH selection and finale strategy

### 1A.1 Submission-stage strategy

The written idea must be easy to shortlist before evaluators can run the software. Use this order:

1. **Operational pain:** current 3D mapping often needs planned multi-pass capture and long processing; disasters or strategic missions may permit only one pass.
2. **Solution:** one video plus flight metadata becomes a georeferenced 3D model with measurements and confidence.
3. **Novelty:** hybrid verified/AI reconstruction plus explicit observation provenance and coverage feedback.
4. **Feasibility:** COLMAP/PyCOLMAP core, GNSS alignment, optional learned accelerator, offline modular architecture.
5. **Proof plan:** known-distance validation, checkpoints, ATE/RPE, reconstruction accuracy/completeness, and runtime ratio.
6. **Impact:** faster situational awareness, fewer repeat missions, auditable decisions, sensitive-data locality.
7. **Progression:** RTK/GCP, edge preview, multi-flight fusion, temporal comparison, semantic assets.

The submission should include one uncluttered architecture figure, one annotated UI mockup, one comparison table, and one output/evaluation table. Replace generic phrases such as “state-of-the-art AI” with named mechanisms and measurable targets.

### 1A.2 Recommended headline and one-line pitch

**Headline:** Drishti3D — Trustworthy 3D Intelligence from One Drone Pass

**One-line pitch:** An offline AI-assisted platform that converts a single UAV video and telemetry into a measurable, georeferenced 3D scene while separating observed geometry from uncertain or inferred regions.

### 1A.3 The flagship scenario

Choose one scenario and make the entire prototype coherent around it. Recommended:

> **Rapid post-disaster infrastructure assessment:** a drone gets one safe pass over a damaged bridge/building corridor; Drishti3D produces the observed 3D scene, flight path, obstacle/structure geometry, measurements, and uncertainty without cloud upload.

Why this scenario is strong:

- It explains why there is only one pass.
- Near-real-time processing has obvious value.
- Offline/local processing is credible and important.
- Measurements and confidence influence decisions.
- Dynamic objects, occlusion, and poor access naturally arise.
- It avoids making the demo look like generic real-estate photogrammetry.

Strategic reconnaissance may be mentioned as an application, but do not simulate classified branding or sensitive data. Use a safe campus/building/structure dataset.

### 1A.4 Demo choreography

The final demo should be scripted but remain technically honest:

| Time | Action | Judge takeaway |
|---:|---|---|
| 0:00–0:30 | Problem and single-pass constraint | team understands the operational problem |
| 0:30–1:15 | Upload video/telemetry; show trajectory and input validation | real inputs, usable workflow |
| 1:15–2:00 | Show quality/keyframe timeline and dynamic masks | handles stated challenges |
| 2:00–2:45 | Show processing stages and real artifacts | not a fake dashboard |
| 2:45–4:00 | Explore point cloud, cameras, map, confidence layers | technical depth plus UX |
| 4:00–5:00 | Measure known distance/height and show independent error | metric accuracy is evidence-backed |
| 5:00–5:30 | Show coverage weakness and recapture suggestion | memorable innovation |
| 5:30–6:00 | Export/report, offline claim, impact and next step | deployable and scalable |

Keep a one-minute version and a three-minute version ready. Judges may interrupt; each section must end with a meaningful result.

### 1A.5 Demo reliability engineering

Winning requires engineering for the event environment:

- Carry the exact raw demo inputs and immutable accepted output artifacts.
- Process a short 30–60 second “live” dataset within a predictable time envelope.
- Have a second, richer preprocessed dataset whose lineage and logs can be inspected.
- Cache only through the documented stage system; disclose cached stages if asked.
- Package all dependencies, weights, map assets, and documentation offline.
- Test on AC power, battery mode, low VRAM, no network, reboot, and fresh install.
- Provide a single launch script and a preflight status screen.
- Record a short backup demonstration video, but use it only if hardware fails.
- Ensure one team member can continue the pitch while another recovers the system.
- Never modify code or data immediately before evaluation without rerunning the smoke suite.

### 1A.6 Judge questions the team must master

**“How is this different from COLMAP or OpenDroneMap?”**  
They are reconstruction components/baselines. Drishti3D adds single-video synchronization, adaptive selection, dynamic rejection, robust telemetry alignment, provenance-aware confidence, measurement safety, operational reporting, and a complete offline workflow. Demonstrate at least one ablation that proves value beyond the wrapper.

**“Where is the AI?”**  
AI assists correspondence/depth or preview in difficult imagery and performs semantic masking. The production design intentionally retains bundle-adjusted geometry and geometric residuals as verification. AI is used where it adds measured value, not as an unverifiable label.

**“Can one path really reconstruct every facade and occluded surface?”**  
No. Only visible surfaces can be measured. The innovation is to maximize recovery from temporal multi-view observations, optionally infer a separate visualization layer, and clearly expose unobserved regions rather than hallucinating them.

**“How do you prove metric accuracy?”**  
Monocular SfM is aligned by a robust similarity transform to synchronized GNSS/RTK/GCP observations. Internal residuals are reported separately from independent checkpoint and known-distance errors. Show the actual test table.

**“What if GPS is poor?”**  
The robust estimator weights accuracy, rejects outliers, and reports a GPS-limited absolute result. Relative geometry remains available; RTK/PPK, GCPs, or known dimensions improve absolute accuracy.

**“What is near-real-time?”**  
Define it quantitatively. The fast preview targets approximately the video duration on tested hardware; verified dense processing can take several times the duration. Show per-stage timings instead of claiming universal real time.

**“Will it work without an NVIDIA GPU or internet?”**  
Ingestion, quality, sparse classical reconstruction, geodesy, measurement, and reporting have a CPU path. Dense/learned stages are capability-gated. No processing-time network access is required after installation.

**“What did your team actually build?”**  
Be explicit about upstream engines and exact original modules. Point to code ownership: telemetry adapters, selection, orchestration, alignment, confidence, viewer, measurement, reports, testing, and integration.

### 1A.7 Quantitative win board

Maintain a visible internal scorecard and update it from real runs:

| KPI | Minimum demo gate | Stretch target |
|---|---:|---:|
| End-to-end success on fixed demo dataset | 5 consecutive runs | 10 consecutive runs |
| Registered selected keyframes | >= 70% | >= 90% |
| Relative known-distance error, strong observed region | < 5% | < 3% |
| Independent checkpoint result | reported honestly | ordinary GPS: meter-level; RTK/GCP: evidence-driven decimeter or better |
| Fast preview processing/video ratio | <= 2x | near 1x |
| Dynamic contamination reduction | measurable improvement | >= 50% reduction without major static loss |
| Offline smoke test | complete | fresh-machine reproducible |
| Demo recovery time | < 2 minutes | < 30 seconds |

These are engineering gates, not promises to publish before measurement. Replace targets with actual results in the final presentation.

### 1A.8 Team-of-six execution model

If the team has six members, assign clear ownership while cross-training every critical function:

| Role | Primary responsibility | Required backup knowledge |
|---|---|---|
| CV/reconstruction lead | COLMAP, learned adapters, masks | dataset and demo recovery |
| Geospatial/evaluation lead | synchronization, ENU/Sim(3), checkpoints | reconstruction diagnostics |
| Backend/platform lead | API, jobs, artifacts, offline packaging | storage recovery |
| Frontend/3D lead | viewer, map, measurement UX | API and model conventions |
| QA/data lead | capture, fixtures, tests, metrics, licences | demo operation |
| Product/pitch lead | NTRO workflow, submission, narrative, Q&A | full end-to-end demo |

No critical subsystem may have only one person who can operate it. During the finale, freeze roles: presenter, demo operator, technical answer lead, system monitor/recovery, evidence navigator, and note-taker/mentor liaison.

### 1A.9 Mentor-feedback protocol

At each mentor interaction:

1. Show the newest working evidence within 60 seconds.
2. Ask one concrete decision question, not “what do you think?”
3. Record feedback and classify it as required, experiment, or out of scope.
4. Confirm the interpretation before the mentor leaves.
5. Implement high-impact feedback, then demonstrate the change in the next round.

Judges reward visible progression. Preserve a short change log showing what the team learned and improved across evaluation rounds.

### 1A.10 Final go/no-go gates

Twenty-four hours before judging, do not add a feature unless it fixes a judging-critical gap. The release candidate must pass:

- Fresh start and capability preflight.
- Full offline end-to-end smoke test.
- Live short-dataset reconstruction.
- Rich accepted-dataset viewer and artifact lineage.
- All measurement/geodesy tests.
- No fabricated placeholder values or broken controls.
- Export/report download and open verification.
- Six-minute, three-minute, and one-minute pitch rehearsals.
- Q&A drill with hostile technical questions.
- Backup machine/media and recovery rehearsal.

The final optimization is reliability and clarity, not feature count.

---

## 2. What is physically possible

### 2.1 Why a single video can produce 3D

A video is a time-ordered collection of images. As a moving drone observes the same static feature from different locations, parallax provides the geometric constraint needed to estimate camera motion and triangulate 3D points. Structure from Motion (SfM) estimates camera intrinsics, camera poses, and sparse structure; Multi-View Stereo (MVS) densifies that structure.

### 2.2 The unavoidable limitations

Monocular reconstruction has four fundamental limits:

- **Scale ambiguity:** Images alone recover geometry only up to a similarity transform. GNSS, IMU, RTK/PPK, GCPs, altitude, or known dimensions are needed for metric scale.
- **Visibility:** A surface absent from every frame has no measurement. A generated back wall or hidden roof is a hypothesis, not reconstruction.
- **Baseline and parallax:** Very small viewpoint changes produce uncertain depth; extremely large changes reduce feature matching. A forward-only trajectory is especially weak for points near the direction of motion.
- **Static-scene assumption:** Moving cars, people, foliage, water, shadows, and rolling-shutter distortions violate classical geometry.

This leads to a non-negotiable data model:

| Provenance class | Meaning | Measurable by default? |
|---|---|---:|
| `OBSERVED_HIGH_CONFIDENCE` | Multi-view geometry with strong tracks, suitable angles, and low residuals | Yes |
| `OBSERVED_LOW_CONFIDENCE` | Observed but weakly constrained or visually degraded | Yes, with warning |
| `AI_ASSISTED` | Learned depth/correspondence materially influenced the geometry | No |
| `DYNAMIC_EXCLUDED` | Detected moving or unstable content removed from the static map | No |
| `UNOBSERVED` | No defensible observation support | No |

Confidence and provenance are different. Provenance answers “where did this come from?” Confidence answers “how strongly is it supported?” Both must survive into storage, visualization, export, and measurement records.

---

## 3. Product scope and requirements

### 3.1 Primary users

- A reconstruction operator uploading and processing missions.
- An analyst inspecting geometry, trajectory, and quality.
- A field team validating dimensions or planning a repeat flight.
- An administrator deploying the system in local or air-gapped infrastructure.
- An evaluator reproducing claimed accuracy from inputs and checkpoints.

### 3.2 Core use cases

1. Reconstruct visible terrain, buildings, roofs, roads, infrastructure, vegetation, and obstacles.
2. Recover an auditable camera trajectory.
3. Place the model in a metric local coordinate frame and map it back to WGS84.
4. Measure point coordinates, 3D distances, vertical height, area, and optionally profiles/volume.
5. Find gaps and low-quality regions that require a repeat flight.
6. Export an interoperable point cloud, trajectory, measurements, and quality report.

### 3.3 Explicit non-goals for the first release

- Survey certification or a universal accuracy guarantee.
- Reconstruction of surfaces never visible in the footage.
- Fully automatic processing of every drone brand and proprietary flight log.
- Real-time onboard reconstruction.
- A digital twin with semantic BIM topology.
- Orthomosaic/DSM production as a mandatory output.
- Multi-user cloud scale, Kubernetes, or microservices before the single-node pipeline is reliable.

### 3.4 Functional acceptance criteria

The system is accepted only if it:

- Processes uploaded rather than bundled or hardcoded imagery.
- Preserves original inputs with checksums.
- Parses a documented generic telemetry schema and at least one real SRT/CSV example.
- Extracts real frame timestamps and computes real quality metrics.
- Produces keyframes and a visible selection/rejection audit.
- Invokes at least one genuine reconstruction engine.
- Stores reconstructed cameras and points.
- Performs GNSS-to-reconstruction similarity alignment and reports residuals.
- Supports metric distance and height measurements.
- Exposes quality and provenance, not merely a visually appealing model.
- Degrades gracefully when GPU models or dense reconstruction are unavailable.
- Exports reproducible artifacts and a report that contains no fabricated accuracy.

---

## 4. Survey of technical approaches

### 4.1 Classical SfM/MVS — recommended source of truth

COLMAP is the best verified engine for the prototype because it provides mature feature extraction, matching, incremental mapping, bundle adjustment, dense reconstruction, pose priors, model I/O, and Python access. Current COLMAP documentation supports GPS pose priors with configurable covariance and robust georegistration of completed models ([COLMAP FAQ](https://github.com/colmap/colmap/blob/main/doc/faq.rst)).

Strengths:

- Interpretable reprojection errors, tracks, observations, camera models, and bundle adjustment.
- Strong ecosystem and standard reconstruction format.
- Works without learned weights; sparse reconstruction can run on CPU.
- Defensible in evaluation because intermediate geometry can be inspected.

Weaknesses:

- Weak texture, repeated patterns, motion blur, changing illumination, and narrow baseline can cause registration failure.
- Dense MVS is compute- and memory-intensive.
- Standard pipelines assume a global-shutter static scene unless corrected/masked.

Decision: **COLMAP/PyCOLMAP is the primary verified backend.** Keep command-line COLMAP as a supported fallback because binary packaging and CUDA behavior may differ from PyCOLMAP.

### 4.2 OpenDroneMap — valuable benchmark, not the initial core

OpenDroneMap already supports imagery/video-related options, georeferencing, point clouds, meshes, orthophotos, GCPs, reports, and Docker deployment ([official documentation](https://docs.opendronemap.org/)). It is an excellent baseline and could later be exposed through a worker adapter.

Why not make it the only core: its complete pipeline is heavier, less tailored to per-point provenance, and harder to bend into the exact confidence-aware workflow. Its AGPL licensing also requires deliberate distribution/deployment review. Use it as:

- A baseline for output quality and runtime.
- A contingency engine for rapid end-to-end photogrammetry.
- A reference for flight planning, GCP, reporting, and dense product generation.

### 4.3 Learned geometry

#### VGGT

VGGT predicts cameras, depth, point maps, and tracks and can export COLMAP-format reconstructions or run bundle adjustment ([official repository](https://github.com/facebookresearch/vggt)). It is attractive as a preview, initializer, or recovery path. However, the standard model is large, its license is custom rather than a permissive open-source license, and checkpoint terms differ; the repository explicitly identifies a particular checkpoint for commercial use. Legal review must approve the exact code and checkpoint ([license](https://github.com/facebookresearch/vggt/blob/main/LICENSE.txt)).

Recommended role:

- GPU-only optional preview.
- Downscaled batches/windows with overlap on an 8 GB GPU.
- Export predicted cameras/points into the common internal format.
- Align to verified geometry; never silently replace bundle-adjusted results.

#### MASt3R-SLAM

MASt3R-SLAM is a compelling dense SLAM research path and reports real-time operation in its CVPR 2025 paper ([paper](https://openaccess.thecvf.com/content/CVPR2025/papers/Murai_MASt3R-SLAM_Real-Time_Dense_SLAM_with_3D_Reconstruction_Priors_CVPR_2025_paper.pdf)). The upstream MASt3R code is CC BY-NC-SA 4.0 and therefore unsuitable for unrestricted commercial distribution without permission ([repository](https://github.com/naver/mast3r)). Integration complexity and GPU memory make it a Phase 4 experiment, not an MVP dependency.

#### DROID-SLAM and ORB-SLAM3

DROID-SLAM is a strong learned dense bundle-adjustment baseline but adds model/GPU and integration complexity. ORB-SLAM3 is valuable for visual-inertial experiments but its GPL terms and live-SLAM orientation require licensing review. Neither should block the first verified pipeline.

### 4.4 Gaussian splatting and NeRF

These methods can produce excellent novel-view appearance, but their primary objective is view synthesis—not metrologically reliable surfaces. Geometry can be noisy, scale is ambiguous without external constraints, and export to engineering point clouds/meshes is nontrivial. Use Gaussian splats only as an optional visualization layer after camera alignment, never as the default measurement substrate.

### 4.5 Recommended engine policy

```text
All jobs
  -> classical SfM sparse reconstruction (required verified path)
  -> GNSS/RTK/GCP alignment (required for metric/geographic claims)
  -> dense MVS (optional based on hardware and coverage)
  -> learned initializer/preview (optional, clearly labelled)
  -> mesh/texture (optional derivative)
```

The internal artifact schema, not a vendor-specific file, is the stable contract. Every engine adapter emits cameras, intrinsics, points/depth, coordinate frame, confidence inputs, logs, and capability warnings.

---

## 5. Proposed system architecture

### 5.1 Architectural style

Use a **modular monolith plus isolated worker process**. The API, metadata database, and orchestration remain simple; heavy computer-vision work runs in a separate Python worker so crashes and GPU memory exhaustion do not take down the web service. Move to Redis/Celery only when multiple concurrent machines are genuinely required.

```text
Browser
  | REST uploads/queries + SSE progress
  v
FastAPI application
  |-- project, artifact, measurement, export APIs
  |-- SQLite (prototype) / PostgreSQL + PostGIS (production)
  |-- immutable object/artifact store on local disk
  `-- job queue abstraction
          |
          v
      Reconstruction worker
          |-- FFmpeg / ffprobe / ExifTool
          |-- OpenCV quality + keyframes + masks
          |-- COLMAP/PyCOLMAP adapter
          |-- optional VGGT/MASt3R adapters
          |-- pyproj alignment and CRS transforms
          |-- Open3D/PDAL cleanup and export
          `-- report + manifest generator
```

### 5.2 Recommended repository tree

```text
/
├── apps/
│   ├── web/                         # React + TypeScript + Vite
│   ├── api/                         # FastAPI HTTP/SSE boundary
│   └── worker/                      # worker entry point
├── packages/
│   ├── contracts/                   # generated API types / JSON schemas
│   └── ui/                          # reusable UI primitives
├── drishti3d/
│   ├── domain/                      # pure types, enums, invariants
│   ├── ingestion/                   # media, telemetry, checksums
│   ├── synchronization/
│   ├── quality/
│   ├── keyframes/
│   ├── masking/
│   ├── reconstruction/
│   │   ├── base.py
│   │   ├── colmap.py
│   │   ├── vggt.py
│   │   └── mast3r_slam.py
│   ├── geodesy/
│   ├── fusion/
│   ├── meshing/
│   ├── measurements/
│   ├── exports/
│   └── reporting/
├── migrations/
├── tests/
│   ├── unit/
│   ├── integration/
│   ├── golden/
│   └── fixtures/
├── sample_data/                     # tiny redistributable fixtures only
├── deploy/
│   ├── docker/
│   └── airgap/
├── docs/
│   ├── architecture/
│   ├── adr/                         # architecture decision records
│   ├── telemetry/
│   ├── evaluation/
│   └── operations/
├── data/                            # gitignored runtime root
├── docker-compose.yml
├── pyproject.toml
├── package.json
├── .env.example
└── README.md
```

### 5.3 Runtime data layout

Never scatter mission outputs across ad hoc folders. Use an immutable, manifest-driven layout:

```text
data/projects/{project_uuid}/
├── inputs/
│   ├── original_video.ext
│   ├── original_telemetry.ext
│   └── manifest.json
├── jobs/{job_uuid}/
│   ├── config.snapshot.json
│   ├── logs/events.jsonl
│   ├── frames/
│   ├── masks/
│   ├── sparse/
│   ├── dense/
│   ├── aligned/
│   ├── mesh/
│   ├── exports/
│   └── stage-manifest.json
└── current.json                     # points to accepted job artifacts
```

Every artifact record should include SHA-256, byte size, MIME/type, producing stage, parent artifacts, software versions, parameters, coordinate frame, units, and creation time. This creates a reproducibility chain and makes stage caching safe.

---

## 6. Detailed processing pipeline

### 6.1 Stage state machine

Use explicit states: `PENDING -> RUNNING -> SUCCEEDED | SUCCEEDED_WITH_WARNINGS | FAILED | CANCELLED | SKIPPED`. A stage can restart only when its input hashes and configuration hash match, otherwise downstream artifacts are invalidated. Emit append-only progress events through SSE.

### 6.2 Ingestion and validation

Inputs:

- MP4/MOV/MKV video; optionally an extracted image sequence.
- Generic CSV/JSON telemetry; DJI-like SRT through a versioned adapter.
- Optional intrinsics/calibration, GCPs, checkpoints, and known distances.

Actions:

1. Stream upload to a temporary file with a configured byte limit.
2. Sanitize the display filename but use a server-generated UUID on disk.
3. Verify container/content using `ffprobe`, not filename extension alone.
4. Hash the completed file and atomically promote it into `inputs`.
5. Extract stream metadata, duration, time base, nominal/average FPS, rotation, colour data, and presence of subtitle/metadata streams.
6. Reject impossible coordinates and non-monotonic or severely incomplete telemetry.

Security: uploaded media is untrusted. Invoke tools with argument arrays, never constructed shell strings. Run the worker without administrative privileges, with storage and runtime limits. Do not serve input files inline.

### 6.3 Telemetry model and synchronization

Canonical telemetry fields:

```text
timestamp_utc or elapsed_ms
latitude_deg, longitude_deg
altitude_m + altitude_datum
optional: h_accuracy_m, v_accuracy_m, rtk_fix
optional: roll_deg, pitch_deg, yaw_deg + orientation_frame/convention
optional: gimbal_roll/pitch/yaw
optional: velocity_n/e/d_mps
optional: fx, fy, cx, cy, distortion coefficients
```

Altitude must always declare its datum/source: ellipsoidal WGS84, orthometric/MSL, barometric, relative-to-home, or unknown. Mixing relative DJI altitude with ellipsoid height is a common catastrophic error.

Synchronization algorithm:

1. Derive frame presentation timestamps from the video time base; do not assume `frame_index / nominal_fps` for variable-frame-rate media.
2. Normalize telemetry to monotonic mission time.
3. Apply a user-configurable time offset and optionally estimate an offset from visual motion versus IMU/velocity changes.
4. Convert GNSS positions to ECEF then local ENU before interpolation.
5. Interpolate position linearly over short intervals; interpolate orientations with quaternions/SLERP after resolving axes and handedness.
6. Attach source interval, gap size, interpolation/extrapolation flag, and confidence to every frame.

Never interpolate raw longitude naively across the antimeridian. Never average Euler angles around ±180 degrees.

### 6.4 Calibration and camera model

Best to worst:

1. Laboratory/checkerboard calibration at the actual resolution, focus, zoom, stabilization mode, and lens.
2. Manufacturer-provided intrinsics plus distortion.
3. Shared self-calibration across the video.

Start with `OPENCV` or an appropriate radial camera model; do not release every intrinsic parameter on weak footage. Crop/resize operations must update intrinsics. Record whether electronic stabilization altered the effective camera model. Rolling shutter should be a declared limitation initially; a later implementation can use rolling-shutter-aware optimization or shorter exposure/capture guidance.

### 6.5 Frame quality analysis

Compute per-frame:

- Laplacian variance plus a scale-normalized sharpness metric.
- Mean/luminance percentiles, clipped dark/bright fraction, local contrast.
- Feature count and spatial distribution grid occupancy.
- Optical-flow magnitude and inlier ratio.
- Perceptual duplicate distance.
- Timestamp/telemetry gap.
- Optional sky/water/dynamic coverage.

Quality thresholds cannot be universal; resolution and scene texture alter scores. Derive defaults from percentiles within the mission and expose absolute guardrails. Rejections must have machine-readable reasons such as `BLUR`, `OVEREXPOSED`, `DUPLICATE`, `TELEMETRY_GAP`, or `INSUFFICIENT_FEATURES`.

### 6.6 Keyframe selection

A robust selector is a constrained optimization, not “every Nth frame.” Select a frame when it is usable and one or more triggers hold:

- Maximum time gap since the last keyframe.
- Sufficient optical-flow/feature displacement.
- Sufficient ENU displacement relative to expected scene depth/altitude.
- Sufficient viewing rotation.
- Local quality is materially better than nearby candidates.

Reject near duplicates but preserve approximately 70–85% image overlap when flight geometry permits it. Implement presets:

| Preset | Goal | Typical behavior |
|---|---|---|
| Fast | Rapid preview | lower resolution, fewer keyframes, sparse only |
| Balanced | Demo/default | moderate keyframes, verified sparse + optional dense |
| Quality | Maximum defensibility | more keyframes, masks, strict BA, dense and detailed report |

The actual count should arise from motion/quality, not a hardcoded FPS rule.

### 6.6 Verified competitive baseline and claim discipline

Competition positioning must survive a judge checking vendor documentation in real time. Do not claim that established photogrammetry tools are universally “photo-only.” PIX4Dmapper officially accepts AVI/MP4 video and extracts frames, although PIX4D warns that video usually produces inferior results to still imagery and recommends 4K ([official PIX4D guidance](https://support.pix4d.com/hc/en-us/articles/205294735)). OpenDroneMap also exposes video frame-count and resolution controls ([official ODM `video-limit`](https://docs.opendronemap.org/fil/arguments/video-limit/), [official ODM `video-resolution`](https://docs.opendronemap.org/sw/arguments/video-resolution/)).

Therefore, the defensible comparison is:

| Capability | Conventional photogrammetry baseline | Drishti3D target |
|---|---|---|
| Accept a video/extract frames | Some established tools already do this | Yes; not claimed as novel by itself |
| Optimize selection for one continuous telemetry stream | Varies; often simple interval extraction or photo workflow | Quality-, motion-, baseline-, and telemetry-aware keyframes |
| Distinguish observed from AI-assisted/unobserved geometry | Not assumed; verify each product/version before comparison | First-class invariant across artifacts, UI, exports, and measurements |
| Measurement safeguards based on provenance | Product-specific; do not claim universal absence without testing | Inferred geometry excluded by default with recorded warnings |
| Independent accuracy evidence | Mature tools may have strong GCP/checkpoint workflows | Required report separating alignment residual from checkpoint error |
| Offline/air-gapped workflow | Several desktop tools may run locally; licensing/activation differs | No processing network dependency after approved installation |
| Weak-coverage/recapture advice | Product-specific | Single-pass-specific quality heatmap and recommended next observation |

Use this judge-safe answer to “Why not PIX4D/OpenDroneMap?”:

> “Those are strong baselines and some already extract video frames. Our contribution is not the file picker. Drishti3D is engineered around the one-pass constraint: telemetry-aware keyframes, dynamic rejection, robust metric alignment, explicit observation provenance, measurement safety, and actionable coverage feedback in an offline evidence chain. We benchmark against existing tools rather than pretending they do not exist.”

Before the final pitch, run the same dataset through at least one accessible baseline—preferably OpenDroneMap and plain COLMAP—with identical or documented frame selection. Compare registration, runtime, relative measurement error, completeness, and dynamic contamination. A measured improvement is more persuasive than a feature-table assertion.

### 6.7 Dynamic and invalid-region masking

Combine:

- Semantic masks for people, vehicles, animals, sky, and optionally water.
- Geometric motion residuals: flow inconsistent with the dominant camera motion.
- Morphological dilation around object boundaries.
- Temporal persistence to reduce flicker.

Masking is advisory until validated: overly broad masks can remove stable geometry. Preserve masks and statistics. If the semantic model is unavailable offline, continue with geometric/heuristic masks and a clear warning.

### 6.8 Verified sparse reconstruction

Recommended COLMAP sequence:

1. Import/extract keyframes with stable IDs and timestamps.
2. Create one shared camera/intrinsic group for frames from the same unchanged video stream.
3. Extract SIFT features, respecting masks where supported.
4. Use sequential matching with overlap plus selected spatial/loop candidates; avoid all-pairs matching for long videos.
5. Run incremental mapping or the pose-prior mapper when trustworthy covariance is available.
6. Bundle adjust with controlled intrinsic refinement.
7. Export cameras, images, points, observations, tracks, errors, and logs into the internal schema.

Success gates:

- Minimum number and percentage of registered keyframes.
- Plausible connected trajectory.
- Median reprojection error below a configurable threshold.
- Sufficient track length and triangulation angle.
- No gross jumps after GNSS alignment.

If multiple disconnected components occur, rank them, attempt GNSS-assisted component alignment only with evidence, and report incompleteness rather than merging arbitrarily.

### 6.9 GNSS scale and georegistration

Use frames shared by the SfM solution and telemetry. Define:

- `p_i`: reconstructed camera center in arbitrary SfM units.
- `q_i`: telemetry camera/antenna position in local ENU metres.
- Similarity transform `q_i ~= s R p_i + t`, with positive scale `s`, rotation `R`, translation `t`.

Procedure:

1. Convert WGS84 `(lat, lon, ellipsoidal height)` to ECEF.
2. Choose a stable mission origin near the median/first valid fix and convert ECEF to ENU.
3. Compensate the GNSS-antenna-to-camera lever arm if known and orientation is reliable.
4. Estimate Sim(3) robustly with RANSAC, requiring at least three non-collinear correspondences but preferably many.
5. Weight/refine by horizontal and vertical GNSS accuracy; ordinary GPS vertical accuracy is commonly worse.
6. Reject outliers, refine on inliers, and report horizontal, vertical, and 3D residual distributions.
7. Apply the transform to cameras and all geometry. Store both the ENU origin and full transform.

Important: alignment residual is internal consistency with GNSS, **not independent positional accuracy**. Absolute accuracy must be tested against checkpoints not used in alignment. If only relative/home altitude exists, geographic Z must remain unverified.

GCPs should be added as a superior/complimentary constraint when available. Keep GCPs used for control separate from independent checkpoints used for evaluation.

### 6.10 Dense reconstruction, cleanup, and mesh

Run COLMAP dense MVS only after sparse geometry and alignment pass their gates. Preserve the sparse result on dense failure. Downsample for the browser while preserving a full-resolution master.

Cleanup may include statistical/radius outlier removal, voxel downsampling, normals, and density estimates. Never erase the raw dense output; cleanup is a derived artifact with parameters.

Mesh options:

- Ball pivoting for surface samples with suitable normals/density.
- Poisson reconstruction for watertight tendencies, followed by density cropping.
- OpenMVS/ODM as a later texturing alternative.

Poisson can fabricate surfaces across holes. Such faces need support/density tests and must not inherit high-confidence provenance simply because they form a smooth surface.

### 6.11 Confidence calibration

Build an explainable feature vector per point/face:

- Number of independent observations.
- Track length.
- Median/maximum reprojection error.
- Triangulation angle/baseline.
- Source-frame blur/exposure scores.
- View diversity and incidence angle.
- Local point density and MVS consistency.
- Dynamic-mask proximity.
- GNSS alignment residual contribution.
- Learned model confidence/uncertainty, when applicable.

Initially use documented rules and thresholds. Later fit a calibration model against reference errors. Validate reliability diagrams: e.g., points labelled 0.8 confidence should empirically fall within the declared tolerance approximately 80% of the time. Never collapse unknown, inferred, and low confidence into one category.

---

## 7. Coordinate systems and measurement design

### 7.1 Coordinate-frame contract

Every geometry artifact must declare:

- CRS identifier or named local frame.
- Axis order and handedness.
- Linear/angular units.
- Origin and altitude datum.
- Transform to parent frame.

Recommended frames:

```text
camera pixel -> camera coordinates -> SfM world (unitless)
              -> mission ENU (metres) -> ECEF (metres) -> WGS84 geographic
```

Use double precision for geodesy. Render in local coordinates or relative-to-center to avoid floating-point jitter. 3D Tiles is an open standard intended for streaming large geospatial models and point clouds ([3D Tiles specification](https://github.com/CesiumGS/3d-tiles/blob/main/specification/README.adoc)); it is a strong production target, while PLY/GLB is simpler for the MVP.

### 7.2 Measurements

- **Point:** picked ENU coordinate plus converted WGS84 coordinate.
- **Distance:** sum of Euclidean 3D segment lengths; optionally show horizontal and vertical components.
- **Height:** absolute difference along local ENU up, not screen Y or arbitrary model axis.
- **Area:** project polygon vertices to a best-fit plane, calculate planar polygon area, and report plane residual/slope.
- **Terrain profile:** sample a selected polyline against trusted surface points/mesh.
- **Volume, later:** compare a closed/reference surface only with explicit assumptions.

Each measurement stores model/artifact version, vertices, algorithm version, units, timestamp, provenance fractions, confidence summary, and whether inferred geometry was enabled. If the model is replaced, measurements must be marked stale or reprojected through a documented transform.

---

## 8. Application and API design

### 8.1 User workflow

1. **Mission dashboard:** projects, status, last accepted run, headline quality.
2. **New mission wizard:** upload, telemetry mapping/preview, camera details, altitude datum, preset, validation.
3. **Processing monitor:** real stage events, timings, counts, logs, warnings, retry/cancel.
4. **Analysis workspace:** 3D model, 2D map, synchronized camera/frustum/timeline, layers, measurements, quality, exports.
5. **Report:** inputs, versions, methodology, residuals, limitations, accuracy evidence, downloadable manifest.

Use a restrained operational UI. Never add fake “classified” styling or official endorsement.

### 8.2 Viewer choice

Use CesiumJS when WGS84 placement, terrain context, and large point-cloud streaming are central. It supports point-cloud shading and WGS84-aware 3D content ([CesiumJS documentation](https://cesium.com/learn/cesiumjs/ref-doc/Cesium3DTileset.html?classFilter=3d)). For the MVP, a Three.js viewer can load downsampled PLY/GLB more simply. The clean compromise is:

- Three.js for the first local ENU analysis viewer.
- MapLibre for trajectory/map context.
- Cesium/3D Tiles adapter after point counts require streaming or globe placement.

Avoid running Cesium and Three.js simultaneously for the same viewport unless there is a demonstrated need.

### 8.3 API surface

```text
POST   /api/v1/projects
GET    /api/v1/projects
GET    /api/v1/projects/{project_id}
POST   /api/v1/projects/{project_id}/inputs/video
POST   /api/v1/projects/{project_id}/inputs/telemetry
POST   /api/v1/projects/{project_id}/jobs
GET    /api/v1/jobs/{job_id}
GET    /api/v1/jobs/{job_id}/events             # SSE
POST   /api/v1/jobs/{job_id}/cancel
POST   /api/v1/jobs/{job_id}/retry
GET    /api/v1/projects/{project_id}/artifacts
GET    /api/v1/artifacts/{artifact_id}/content
GET    /api/v1/projects/{project_id}/quality
GET    /api/v1/projects/{project_id}/trajectory
POST   /api/v1/projects/{project_id}/measurements
GET    /api/v1/projects/{project_id}/measurements
DELETE /api/v1/measurements/{measurement_id}
POST   /api/v1/projects/{project_id}/exports
GET    /api/v1/exports/{export_id}
```

Use resumable/chunked uploads later; ordinary streaming multipart uploads are sufficient for the prototype. Use SSE rather than WebSockets because progress is primarily server-to-client and SSE reconnect semantics are simple.

### 8.4 Core database entities

- `Project`
- `InputAsset`
- `TelemetrySample` or columnar telemetry artifact
- `ProcessingJob`
- `StageRun`
- `Artifact`
- `CameraFrame`
- `QualityMetric`
- `AlignmentResult`
- `Measurement`
- `Export`
- `SoftwareComponentVersion`

Do not store millions of point rows in SQLite/PostgreSQL for the MVP. Store point clouds as versioned binary artifacts and keep searchable summaries/footprints in the database. PostGIS becomes valuable for footprints, trajectories, GCPs, checkpoints, and mission queries.

---

## 9. Technology decisions

| Concern | MVP decision | Scale-up path |
|---|---|---|
| Web UI | React, TypeScript, Vite | same |
| 3D | Three.js, local ENU, downsampled PLY/GLB | CesiumJS + 3D Tiles |
| Map | MapLibre GL | same/offline tile source |
| API | FastAPI + Pydantic | same behind reverse proxy |
| Persistence | SQLite + SQLAlchemy | PostgreSQL/PostGIS |
| Jobs | DB-backed/local process worker | Redis + Celery/RQ only when needed |
| Progress | SSE + persisted events | broker-backed events |
| Media | FFmpeg/ffprobe, ExifTool | same |
| CV | OpenCV | same |
| Verified 3D | COLMAP/PyCOLMAP | multiple adapters/ODM |
| Geometry | Open3D, NumPy/SciPy | PDAL for production point workflows |
| Geodesy | pyproj/PROJ | same |
| ML | optional PyTorch adapter | isolated GPU worker |
| Packaging | Docker Compose + native dev | signed air-gap bundle |

### 9.1 Local environment finding

Observed on 27 August 2026:

| Capability | Detected |
|---|---|
| OS shell | Windows PowerShell 5.1 |
| Python | 3.13.5 |
| Node/npm | 24.11.1 / 11.6.2 |
| Docker | 29.6.1 |
| GPU | NVIDIA GeForce RTX 4060 Laptop GPU, 8188 MiB |
| NVIDIA driver | 610.88 |
| FFmpeg/ffprobe | Not on PATH |
| COLMAP | Not on PATH |

Recommendation: use a dedicated Python **3.11** reconstruction environment/container. Python 3.13 is likely to encounter gaps in binary wheels across PyTorch, PyCOLMAP, and scientific dependencies. Node 24 may also be ahead of some frontend packages; pin an LTS version in `.nvmrc`/Volta and lock dependencies. Install FFmpeg and COLMAP explicitly; never allow the UI to imply reconstruction capability merely because the API starts.

### 9.2 Hardware expectations

| Operation | CPU | RTX 4060 8 GB |
|---|---:|---:|
| ffprobe/frame extraction/quality | Good | GPU optional |
| SIFT sparse SfM | Works, slower | CUDA build beneficial |
| GNSS alignment/measurements/reports | Excellent | unnecessary |
| Dense MVS | Possible but slow | feasible with controlled resolution |
| Small segmentation model | Works slowly | good |
| VGGT large checkpoint | constrained | use downscaled/windowed inputs; expect OOM tuning |
| MASt3R-SLAM | research integration | feasible only after model-specific tuning |

Run a preflight probe that records executable versions, CUDA availability, VRAM, disk space, and writable paths. Job presets should be derived from this capability matrix.

---

## 10. Accuracy, validation, and evaluation

### 10.1 Accuracy vocabulary

- **Precision/repeatability:** closeness across repeated runs or measurements.
- **Relative accuracy:** dimensional fidelity within the reconstruction.
- **Absolute accuracy:** closeness to independent surveyed coordinates.
- **Alignment residual:** fit to GNSS/GCP observations used by the solution; not independent accuracy.
- **Completeness:** fraction of reference surface recovered within tolerance.

### 10.2 Required metrics

| Layer | Metrics |
|---|---|
| Inputs | usable frames, blur/exposure distributions, telemetry gaps |
| Camera | registered %, ATE/RPE where truth exists, trajectory continuity |
| Sparse geometry | reprojection percentiles, track length, triangulation angle |
| Georegistration | ENU horizontal/vertical/3D residuals, inlier count, rejected fixes |
| Independent accuracy | checkpoint RMSE X/Y/Z/3D, median, 95th percentile, max |
| Dense surface | point-to-reference distance, Chamfer/F-score, completeness |
| Dynamics | dynamic points remaining; static points incorrectly removed |
| Measurements | absolute and percent error for known length/height/area |
| Confidence | error by confidence bin, reliability/calibration error |
| Performance | wall time/stage, peak RAM/VRAM, output size, processing/video ratio |

The current ASPRS Edition 2 Version 2 standard includes dedicated photogrammetry, UAS, and oblique-imagery guidance and emphasizes independent checkpoints; it increased the standard minimum checkpoint count to 30 for formal product accuracy assessment ([ASPRS announcement and standard](https://old.asprs.org/archives/asprs-approves-edition-2-version-2-of-the-asprs-positional-accuracy-standards-for-digital-geospatial-data-2024.html)). A hackathon prototype may have fewer checkpoints, but must describe the result as an experiment rather than standards-compliant certification.

### 10.3 Evaluation datasets

Use three layers of evidence:

1. **Synthetic unit/integration fixture:** known cameras, points, timestamps, GNSS noise, and deliberate outliers. Fast and deterministic; validates transforms and APIs.
2. **Public SLAM dataset:** TartanAir provides RGB, depth, segmentation, optical flow, poses, and LiDAR-like truth and offers ATE/RPE evaluation tooling ([official documentation](https://tartanair.org/examples.html)). EuRoC is useful for visual-inertial trajectory testing, though it is indoor UAV data and not a complete outdoor geospatial validation.
3. **Team-captured drone dataset:** the decisive demo. Capture calibrated video, raw telemetry, RTK/GCPs if possible, known dimensions, varied texture, a few dynamic objects, and independent checkpoints.

Public SLAM datasets test trajectory/reconstruction logic but do not prove outdoor GNSS accuracy. The team dataset must include a written capture protocol and ground-truth provenance.

### 10.4 Ablation matrix

Run comparisons on identical keyframes:

- Uniform sampling vs adaptive keyframes.
- No masks vs semantic masks vs semantic + motion masks.
- SfM only vs pose priors vs post-Sim(3) alignment.
- Estimated intrinsics vs calibrated intrinsics.
- Classical initialization vs learned initialization.
- Ordinary GPS vs RTK/GCP.

This shows which innovations create measurable value and prevents the “AI-enabled” claim from being purely decorative.

### 10.5 Defensible claims

Acceptable:

- “The system produced a real reconstruction from a single continuous flight video.”
- “Metric scale was recovered from synchronized GNSS and validated on independent known distances.”
- “On dataset X, checkpoint horizontal RMSE was Y and vertical RMSE was Z under the stated capture conditions.”

Unacceptable:

- “Centimetre accurate” without calibration and independent ground truth.
- “Complete model” when surfaces were not observed.
- “Real time” based only on one neural forward pass while excluding extraction, alignment, fusion, and export.
- “Confidence 95%” without defining/calibrating what 95% means.

---

## 11. Security, privacy, and offline deployment

### 11.1 Threat model

Threats include malformed media exploiting decoders, path traversal, decompression/resource exhaustion, shell injection, unauthorized access to sensitive coordinates, model-weight supply-chain compromise, stale vulnerable binaries, and accidental network exfiltration.

Controls:

- UUID storage names; path resolution constrained beneath a mission root.
- File size, duration, dimension, frame-count, and processing quotas.
- Subprocess argument arrays, timeouts, memory limits, captured logs.
- Worker account/container with least privilege and no network during processing.
- Localhost binding by default and authentication before multi-user deployment.
- Redact coordinates from ordinary logs; protect downloads.
- SHA-256 and manifest verification for binaries/model weights.
- Software bill of materials, pinned images, lockfiles, and vulnerability scanning.
- Safe deletion limited to a resolved project UUID directory with audit record.

### 11.2 Air-gapped delivery

An offline bundle must include:

- Version-pinned containers or installers.
- FFmpeg, COLMAP, and GPU compatibility matrix.
- Python/npm dependency caches or built images.
- Approved optional model weights with hashes and licence texts.
- Offline basemap strategy; otherwise the map must degrade to a coordinate grid/trajectory view.
- Installation verification script and sample fixture.
- SBOM, third-party notices, backup/restore and upgrade procedure.

No startup-time downloads. No remote fonts, analytics, map tiles, CDN scripts, or automatic model fetching.

---

## 12. Licensing and compliance

Licensing is a release gate, especially for an NTRO-oriented application.

| Component | Main concern/action |
|---|---|
| COLMAP | BSD-style/permissive overall; verify bundled dependencies and binary notices |
| OpenCV/Open3D/pyproj/FastAPI/React/Three.js/MapLibre/CesiumJS | Generally permissive; preserve notices and verify exact versions |
| FFmpeg | LGPL/GPL configuration depends on how it is built; record build flags |
| OpenDroneMap | AGPL; legal review if integrated/distributed as a network service |
| MASt3R | CC BY-NC-SA 4.0 upstream; non-commercial limitation is material |
| VGGT | Custom licence/AUP; approve exact checkpoint and use case |
| ORB-SLAM3 | GPL; distribution/integration implications |
| Model datasets/weights | Terms may differ from code; maintain a separate registry |
| Map tiles | Offline redistribution rights differ from library licence |

Maintain `THIRD_PARTY_NOTICES.md` and a machine-readable component/model registry containing source URL, version/commit, hash, code licence, weight licence, dataset licence, approved usage, and reviewer/date. “Available on GitHub” never means unrestricted use.

---

## 13. Failure modes and mitigations

| Failure | Detection | Response |
|---|---|---|
| Too little parallax | low triangulation angles, unstable depth | warn; keep sparse/trajectory; recommend cross-track/oblique recapture |
| Motion blur | sharpness and feature collapse | reject frames; select sharper neighbors |
| Repeated/textureless surfaces | ambiguous matches, low tracks | stricter geometry checks; learned initializer; report gaps |
| Dynamic crowd/traffic | mask coverage, flow residual | exclude/dilate; preserve warning |
| Water/sky/reflections | semantic/consistency masks | mark unobserved/unstable |
| Bad time offset | GNSS/visual motion mismatch | estimate/manual offset; plot residual vs time |
| Wrong altitude datum | systematic vertical inconsistency | require datum; block geographic-Z claim |
| Poor GPS | high residuals/outliers | robust weighting; report GPS-limited accuracy; use GCP/RTK |
| Rolling shutter | bent geometry during fast motion | capture guidance; later RS-aware model |
| Stabilized/zooming video | changing intrinsics | detect metadata/discontinuities; segment calibration groups |
| COLMAP registers a fragment | registered % and components | return partial result with exact failure report |
| Dense MVS OOM | worker telemetry/exit | reduce resolution/depth range; preserve sparse output |
| Neural model unavailable | capability probe | skip with warning; classical path remains functional |
| Mesh bridges holes | low support/density | crop or label inferred; measurements use points by default |

The capture guide is part of the algorithm: stable shutter, locked focus/exposure when possible, constant zoom, sufficient overlap, moderate speed, oblique views for facades, cross-track variation, and RTK/GCPs improve results more reliably than post-hoc hallucination.

---

## 14. Implementation roadmap

### Phase 0 — Decisions and reproducible foundation (2–3 days)

- Confirm input drone/telemetry, altitude datum, GPU target, offline requirement, allowed licences, and ground truth.
- Add architecture decisions, dependency locks, capability probe, artifact manifest, and tiny synthetic fixture.
- Install/pin Python 3.11, FFmpeg, and a COLMAP path.

Exit: a documented capability report and approved dependency/licence matrix.

### Phase 1 — Honest ingestion and preprocessing (4–6 days)

- Project/job database and immutable storage.
- Streaming uploads, hashes, ffprobe metadata.
- Generic CSV/JSON and SRT adapter framework.
- Frame timestamps, ENU telemetry interpolation.
- Quality metrics, keyframes, rejection audit.
- UI wizard/monitor and SSE.
- Unit and integration tests.

Exit: real uploaded footage produces reproducible keyframes, synchronized telemetry, metrics, artifacts, and a report.

### Phase 2 — Verified reconstruction and viewer (5–8 days)

- COLMAP adapter and preflight.
- Sequential/spatial matching configuration.
- Camera/point internal schema and artifact import.
- Sparse point viewer, camera frustums, map trajectory.
- Failure diagnostics and partial-result handling.

Exit: a real uploaded mission produces and displays a genuine sparse reconstruction.

### Phase 3 — Metric/geographic model (4–6 days)

- WGS84/ECEF/ENU tests.
- Robust weighted Sim(3) with outliers.
- GCP/checkpoint model.
- Distance, height, area and coordinate tools.
- PLY/GLB, trajectory CSV/GeoJSON, JSON/HTML report.

Exit: scale/georegistration is reproducible, residuals are shown, measurements match known dimensions within the declared target.

### Phase 4 — Density, masks, and confidence (5–10 days)

- Dynamic/sky/water masks.
- Dense MVS and cleanup.
- Explainable confidence rules and layer styling.
- Benchmark no-mask/mask and sparse/dense behavior.

Exit: provenance survives into display/export and improves measured cleanliness.

### Phase 5 — Learned assistance and hardened delivery (time-boxed)

- VGGT adapter first; MASt3R-SLAM only after licence/hardware approval.
- Alignment/fusion experiments and ablations.
- Docker Compose, air-gap bundle, SBOM, offline map behavior.
- End-to-end demo rehearsal and recovery paths.

Exit: learned assistance shows measured benefit or remains an explicitly optional experiment; base product remains complete.

### Priority if schedule collapses

Protect, in order: real sparse reconstruction, GNSS metric alignment, measurement, evidence report, confidence visualization, dynamic masking, dense cloud, mesh, learned preview. A point cloud that is real and measurable beats a polished but fabricated mesh.

---

## 15. Testing strategy

### Unit tests

- Telemetry parsers, units, range validation, and malformed rows.
- PTS extraction and interpolation boundaries.
- Quaternion interpolation and wraparound.
- WGS84/ECEF/ENU round trips against known values.
- Sim(3) recovery with noise, outliers, and degenerate layouts.
- Camera center/extrinsic conventions.
- Blur/exposure/duplicate metrics on generated images.
- Distance, height, best-fit-plane area.
- Path containment, filename sanitation, upload limits.
- State transitions, cache keys, and cancellation.

### Integration tests

- Upload -> extract -> synchronize -> keyframes.
- Tiny image set -> COLMAP adapter -> imported cameras/points.
- Synthetic SfM cameras + noisy GNSS -> aligned metric model.
- Artifact download and report manifest verification.
- Restart after a failed stage without corrupting successful outputs.

### End-to-end and golden tests

- One small redistributable mission with expected ranges, not brittle exact point clouds.
- Browser workflow for create/upload/process/view/measure/export.
- CPU-only mode and missing-COLMAP/missing-model warnings.
- Offline test with outbound network disabled.

Never assert that photogrammetry output is bit-for-bit identical across GPU/library versions. Test invariants and tolerances: registered count range, finite coordinates, residual bounds, expected scale, and artifact consistency.

---

## 16. Demonstration plan

### The 6-minute narrative

1. State the scientific constraint: only observed geometry is treated as measured.
2. Upload a real video and telemetry.
3. Show extracted metadata, telemetry trajectory, quality chart, and rejected frames.
4. Start a cached/rehearsed balanced job while showing real stage manifests/logs.
5. Open the genuine reconstruction, cameras, and flight path.
6. Toggle confidence/provenance and dynamic exclusions.
7. Measure a known distance and height; compare with independent truth.
8. Show GNSS alignment residual separately from checkpoint error.
9. Export PLY/GLB, GeoJSON/CSV, and the quality report.
10. End with limitations and the repeat-flight guidance generated from weak regions.

Prepare three demo paths: live success, precomputed accepted artifacts from the same visible inputs, and CPU/sparse-only fallback. Precomputation is legitimate when fully traceable; hardcoded or unrelated output is not.

### Evidence pack

- Raw input hashes.
- Calibration and telemetry schema.
- Exact configuration and software versions.
- Stage timings and logs.
- Checkpoint/known-distance table.
- Ablation results.
- Output manifest and licences.
- Known limitations.

---

## 17. Open decisions that must be answered

| Decision | Why it changes architecture | Recommended default |
|---|---|---|
| Exact drone/camera | telemetry and calibration differ | choose one demo device now |
| SRT/CSV/log format | controls parser and time synchronization | require generic CSV plus one device adapter |
| Altitude datum | determines whether geographic Z is valid | explicit required field; unknown blocks claim |
| RTK/PPK/GCP access | sets attainable absolute accuracy | use independent checkpoints at minimum |
| Offline requirement | affects maps, weights, packages | design offline from day one |
| Licence policy | determines learned engines | classical permissive path mandatory |
| Required primary output | affects schedule | point cloud first, mesh conditional |
| Max video duration/resolution | drives quotas/storage/hardware | publish tested envelope |
| Formal accuracy standard | drives checkpoint protocol | align report terminology with ASPRS, avoid certification claim |
| Windows vs Linux target | affects COLMAP/CUDA packaging | Docker/Linux GPU worker for reproducibility |

---

## 18. Final recommended plan

### Build now

1. Freeze a generic telemetry contract with explicit timing and altitude datum.
2. Create a Python 3.11/Docker environment and install versioned FFmpeg/COLMAP.
3. Implement immutable ingestion, capability probing, stage manifests, and a tiny synthetic fixture.
4. Complete preprocessing and adaptive keyframes with tests.
5. Integrate real sparse COLMAP reconstruction before spending time on advanced UI.
6. Implement robust ENU Sim(3), independent checkpoint evaluation, and measurements.
7. Add the analysis viewer and evidence report.
8. Add masks, dense geometry, and calibrated confidence.
9. Evaluate VGGT only after the verified path works and licensing is approved.

### Architecture invariants

- One canonical coordinate-frame contract.
- One immutable artifact/lineage model.
- Engines behind adapters.
- A complete CPU/classical fallback.
- No metric or accuracy claim without its evidence class.
- No inferred surface measured by default.
- No hidden network dependency.
- No stage success without a validated artifact.

### Definition of “done”

Drishti3D is not done when a 3D object appears on screen. It is done when another engineer can take the original inputs and recorded configuration, reproduce the accepted artifacts, understand every coordinate transform, see which observations support a measurement, quantify the error against independent truth, and obtain the same defensible conclusion.

---

## 19. Primary references and further reading

1. COLMAP documentation — pose priors, georegistration, camera models, reconstruction: <https://github.com/colmap/colmap/tree/main/doc>
2. COLMAP FAQ — GPS priors and model alignment: <https://github.com/colmap/colmap/blob/main/doc/faq.rst>
3. VGGT official repository — cameras, depth, point maps, tracks, COLMAP export: <https://github.com/facebookresearch/vggt>
4. VGGT licence: <https://github.com/facebookresearch/vggt/blob/main/LICENSE.txt>
5. MASt3R-SLAM CVPR 2025 paper: <https://openaccess.thecvf.com/content/CVPR2025/papers/Murai_MASt3R-SLAM_Real-Time_Dense_SLAM_with_3D_Reconstruction_Priors_CVPR_2025_paper.pdf>
6. MASt3R official repository and licence note: <https://github.com/naver/mast3r>
7. DROID-SLAM paper: <https://arxiv.org/abs/2108.10869>
8. OpenDroneMap official documentation: <https://docs.opendronemap.org/>
9. TartanAir documentation and trajectory evaluation: <https://tartanair.org/examples.html>
10. TartanAir paper: <https://arxiv.org/abs/2003.14338>
11. EuRoC MAV dataset paper: <https://journals.sagepub.com/doi/10.1177/0278364915620033>
12. ASPRS Positional Accuracy Standards portal: <https://www.asprs.org/Main/Main/Standards/Positional-Accuracy-Standards.aspx>
13. ASPRS Edition 2 Version 2 announcement: <https://old.asprs.org/archives/asprs-approves-edition-2-version-2-of-the-asprs-positional-accuracy-standards-for-digital-geospatial-data-2024.html>
14. OGC/Cesium 3D Tiles specification: <https://github.com/CesiumGS/3d-tiles/blob/main/specification/README.adoc>
15. CesiumJS point-cloud/3D Tiles documentation: <https://cesium.com/learn/cesiumjs/ref-doc/Cesium3DTileset.html?classFilter=3d>
16. Official SIH idea-selection criteria (published guidelines): <https://sih.gov.in/letters/Guidelines-College-SPOC.pdf>
17. SIH26158 problem-statement mirror, including the 20 September 2026 deadline and stated challenge list (verify against the official portal before submission): <https://sih2026.vuce.in/en/ps/SIH26158>

---

## Appendix A — Generic telemetry CSV

```csv
timestamp_utc,elapsed_ms,latitude_deg,longitude_deg,altitude_m,altitude_datum,h_accuracy_m,v_accuracy_m,roll_deg,pitch_deg,yaw_deg,gimbal_roll_deg,gimbal_pitch_deg,gimbal_yaw_deg,rtk_fix
2026-08-27T06:30:00.000Z,0,28.613900,77.209000,224.12,WGS84_ELLIPSOID,0.03,0.05,0.1,-1.2,91.4,0.0,-45.0,91.2,FIXED
```

Rules:

- Supply either absolute UTC plus a verified video clock relationship, or elapsed milliseconds relative to the first video PTS.
- Degrees are decimal degrees; metres are SI metres.
- Declare orientation frame, rotation order, and whether yaw is true/grid/magnetic north in a sidecar schema.
- Blank optional values are unknown, not zero.
- Reject duplicates or resolve them with an explicit policy.

## Appendix B — Quality report skeleton

```text
Mission identity and hashes
Software/model versions and licences
Input video and camera/calibration
Telemetry source, timing, altitude datum and coverage
Processing configuration and stage status
Frame-quality and keyframe-selection summary
Reconstruction registration and residuals
Coordinate frames and alignment transform
GNSS/GCP fit residuals
Independent checkpoint accuracy
Point/mesh density, completeness and provenance
Measurement validation
Runtime, RAM/VRAM and artifact sizes
Warnings, failures and excluded data
Permitted claims and known limitations
Reproduction commands and artifact manifest
```

## Appendix C — Immediate engineering checklist

- [ ] Select and document the demo drone/camera.
- [ ] Capture a 30–90 second test clip with sufficient parallax and telemetry.
- [ ] Establish altitude datum and video/telemetry time relationship.
- [ ] Obtain calibration or capture a checkerboard calibration set.
- [ ] Survey independent known distances/checkpoints.
- [ ] Approve licences before downloading learned weights.
- [ ] Pin Python 3.11, Node LTS, FFmpeg, COLMAP, CUDA, and drivers.
- [ ] Confirm at least 50–100 GB free scratch space for realistic dense jobs.
- [ ] Implement and run the synthetic Sim(3)/ENU tests first.
- [ ] Demonstrate sparse reconstruction before dense/mesh work.
- [ ] Preserve all actual logs, hashes, parameters, and failure messages.
- [ ] Rehearse offline with the network disabled.

## Appendix D — MASt3R-SLAM Deep Dive and Drishti3D Integration Decision

### D.1 Why this paper matters

MASt3R-SLAM is one of the most directly relevant CVPR 2025 systems for SIH26158. It is a real-time monocular dense SLAM system constructed around MASt3R, a learned two-view 3D reconstruction and matching prior. From ordinary RGB video it estimates camera motion and dense pointmap geometry, including on difficult in-the-wild sequences and with generic or time-varying central camera models ([CVPR 2025 paper](https://openaccess.thecvf.com/content/CVPR2025/html/Murai_MASt3R-SLAM_Real-Time_Dense_SLAM_with_3D_Reconstruction_Priors_CVPR_2025_paper.html), [full paper and supplementary text](https://arxiv.org/abs/2412.12392)).

This makes it valuable for Drishti3D as a **fast preview, learned initializer, and difficult-scene recovery engine**. It does not by itself solve the full problem: it does not synchronize drone telemetry, establish a WGS84/ENU coordinate frame, validate absolute accuracy, remove dynamic objects, or distinguish measured from inferred geometry.

### D.2 System architecture distilled

The system performs:

1. **Two-view pointmap prediction:** MASt3R predicts dense 3D pointmaps for image pairs in a common coordinate frame.
2. **Efficient projective pointmap matching:** the paper replaces slow brute-force MASt3R matching with local projective matching and optional feature refinement.
3. **Camera tracking:** incoming frames are aligned to a canonical keyframe using pointmap/ray consistency.
4. **Local pointmap fusion:** predictions are combined into a canonical local representation using confidence-weighted fusion.
5. **Motion-dependent keyframing:** frames become keyframes based on observed change rather than a fixed interval.
6. **Retrieval and loop closure:** encoded features identify revisited areas and add graph constraints.
7. **Global backend optimization:** a sparse second-order optimizer jointly improves keyframe poses and pairwise scales.
8. **Relocalization:** a failed tracker can reconnect the current frame to an existing graph location.

The important architectural lesson is that a learned prior is not used as a one-shot answer. Its biased local predictions are filtered, connected through a graph, and globally optimized. Drishti3D should adopt the same principle: learned output is a measurement candidate that still requires temporal, geometric, and geospatial consistency.

### D.3 Notable technical ideas worth reusing

#### Ray error for uncertain or changing intrinsics

For the uncalibrated case, the method converts pointmap predictions into directions/rays and optimizes angular ray consistency. Direction is less sensitive than raw 3D point error to incorrect predicted depth. This lets the system handle a generic central camera and even time-varying camera parameters.

Potential Drishti3D use:

- A fallback tracker when accurate intrinsics are missing.
- A diagnostic comparison between calibrated reprojection error and uncalibrated ray error.
- Better tolerance of digital stabilization, zoom changes, and consumer cameras.

This does not eliminate the value of calibration. The paper’s calibrated results are substantially stronger on several benchmarks, so Drishti3D should still request and prefer known intrinsics.

#### Confidence-weighted canonical pointmap fusion

The paper compares retaining the newest pointmap, first pointmap, highest-median-confidence pointmap, and confidence-weighted fusion. Weighted fusion performs best or jointly best in the reported ablation, particularly without calibration. This suggests a reusable fusion rule:

```text
canonical_point = sum(weight_i * transformed_prediction_i) / sum(weight_i)
```

Weights must include more than neural confidence in Drishti3D. Combine MASt3R confidence with reprojection/ray residual, view baseline, source-frame quality, temporal consistency, and dynamic-mask distance.

#### Motion-aware keyframing

The system’s performance depends on selecting keyframes that balance new information with overlap. The paper’s fusion ablation explains why neither always using the first view nor always using the newest view is ideal: the first may lack sufficient baseline while the newest accumulates drift. This supports Drishti3D’s adaptive keyframe design and motivates testing MASt3R overlap/match fraction as another selection signal.

#### Loop-closure retrieval as a graph edge proposal

The system uses feature retrieval to propose loop candidates and only adds edges after sufficient pointmap matches. Drishti3D can reuse this conservative pattern for:

- Detecting flight-path self-intersections.
- Adding limited non-sequential matches without exhaustive all-pairs cost.
- Reconnecting visually overlapping segments.

However, a strict single flyover may contain few true loop closures. Report their count; never assume loop closure will remove drift on a non-revisiting trajectory.

#### Separate pose consistency from dense-map coherence

The authors show that a method may have strong camera trajectory accuracy yet noisy geometry, or more complete geometry because it emits many noisy points. Therefore Drishti3D must evaluate trajectory and surface independently:

- ATE/RPE for poses.
- Accuracy and completion separately for geometry.
- RMSE/percentiles rather than only mean nearest-neighbor distance.
- Visual/outlier inspection alongside Chamfer distance.

### D.4 Reported evidence and its correct interpretation

The paper reports approximately **15 FPS** for the complete system, while tracking itself runs above 20 FPS. Its optimized matching takes approximately 0.5 ms, or around 2 ms with feature refinement, versus roughly 2 seconds for full MASt3R matching in the reported comparison. The neural encoder and decoder remain the main runtime cost, around 64% of total runtime in the supplementary analysis.

These values demonstrate architectural efficiency; they are not a performance promise for Drishti3D’s RTX 4060 Laptop GPU. Runtime depends on input resolution, keyframe frequency, loop closures, CUDA/PyTorch build, power limits, and GPU memory.

On calibrated EuRoC, the supplementary table reports average ATE of approximately:

- DROID-SLAM: 0.022 m.
- MASt3R-SLAM: 0.041 m.
- Uncalibrated MASt3R-SLAM: 0.164 m.

Therefore, do not claim MASt3R-SLAM universally has the best trajectory accuracy. The paper’s advantage is especially compelling in dense geometry coherence and camera-model flexibility. It also reports loop-closure ablations with substantial improvements, but single-pass UAV footage may not contain comparable revisits.

The evaluation primarily uses TUM RGB-D, 7-Scenes, ETH3D-SLAM, and EuRoC-style sequences. These prove general SLAM capability, not outdoor GNSS-georeferenced UAV accuracy. A team-captured drone dataset with checkpoints remains mandatory.

### D.5 Limitations that directly affect SIH26158

The paper acknowledges that not all dense geometry is refined in its global optimization. The backend optimizes graph poses and relative scales, while complete globally consistent pointmap refinement remains future work.

Additional Drishti3D-relevant limitations:

- Learned MASt3R predictions retain bias and can cause drift.
- Uncalibrated mode can be materially less accurate.
- The authors found EuRoC distortion too strong for the learned uncalibrated path and undistorted images first.
- Monocular output still lacks independently established geographic scale and position.
- The method does not consume GNSS, RTK/PPK, GCPs, barometric altitude, or the Drishti3D telemetry contract.
- It assumes sufficient scene rigidity; it is not a dynamic-object-removal solution.
- It cannot measure never-observed surfaces.
- Neural confidence is not calibrated measurement confidence.
- Loop closure provides less benefit when the drone never revisits a location.
- The research benchmarks do not establish operational accuracy for outdoor aerial mapping.

### D.6 Integration architecture

```text
Video keyframes
      |
      v
MASt3R-SLAM adapter
      |-- relative camera poses
      |-- dense pointmaps
      |-- neural confidence
      |-- keyframe/edge graph
      `-- tracking and loop-closure diagnostics
      |
      v
Drishti3D normalization
      |-- timestamps and camera convention
      |-- masks and accepted source pixels
      |-- common artifact schema
      `-- explicit relative coordinate frame
      |
      v
GNSS/RTK/GCP robust Sim(3) alignment to ENU
      |
      +--> COLMAP/geometric verification and optional refinement
      |
      v
Confidence + provenance classification
      |
      v
Viewer, safe measurements, exports, evidence report
```

The adapter should expose at least:

```python
class ReconstructionAdapter:
    def is_available(self) -> bool: ...
    def capability_report(self) -> dict: ...
    def prepare_inputs(self, keyframes, masks, intrinsics=None): ...
    def reconstruct(self, config): ...
    def get_camera_poses(self): ...
    def get_pointmaps(self): ...
    def get_point_cloud(self): ...
    def get_uncertainty(self): ...
    def get_graph(self): ...
    def get_runtime_metrics(self): ...
```

Do not automatically download checkpoints during application startup. Record the exact code commit, checkpoint hash/licence, PyTorch/CUDA versions, parameters, input resolution, and runtime metrics in the job manifest.

### D.7 Provenance promotion policy

MASt3R-SLAM geometry begins as `AI_ASSISTED`. It may be promoted to an observed class only if the implementation can demonstrate sufficient observation support and geometric verification.

| Evidence | Resulting policy |
|---|---|
| Learned pointmap only | `AI_ASSISTED`; excluded from measurement by default |
| Multi-view support but weak baseline/high residual | `OBSERVED_LOW_CONFIDENCE` only if promotion rules pass |
| Strong multi-view support, acceptable residuals, adequate view angle and consistent scale | eligible for `OBSERVED_HIGH_CONFIDENCE` |
| Dynamic-mask intersection or inconsistent motion | `DYNAMIC_EXCLUDED` |
| No supporting input observation | `UNOBSERVED` |

Never treat MASt3R’s network confidence as a calibrated probability of metric correctness. It is one feature in the final confidence model.

### D.8 RTX 4060 8 GB feasibility experiment

Before committing MASt3R-SLAM to the live demonstration, run a time-boxed experiment on this exact machine:

1. Install in an isolated Python 3.11 environment with an explicitly compatible PyTorch/CUDA build.
2. Confirm licence approval before downloading the required MASt3R/retrieval checkpoints.
3. Test short sequences at progressively larger input resolutions.
4. Record startup time, steady FPS, peak VRAM/RAM, keyframe rate, graph growth, output size, and failure mode.
5. Test calibrated and uncalibrated input.
6. Test video with blur, exposure changes, weak texture, a moving vehicle, and a zoom/stabilization change.
7. Compare trajectory and geometry against COLMAP on identical accepted keyframes.
8. Test whether masks can be applied without corrupting the pointmap pipeline.
9. Run at least five consecutive offline jobs to establish demo reliability.
10. If any required resolution causes OOM or instability, reduce it or remove the live dependency; retain prerecorded traceable artifacts and the classical path.

Go/no-go criteria for the SIH demo should include stable execution within 8 GB, acceptable preview latency, consistent model orientation/scale after alignment, and a measured advantage over the classical fast preset on at least one difficult sequence.

### D.9 Licensing decision

The MASt3R/MASt3R-SLAM code and checkpoints must be reviewed separately. The available upstream materials use or inherit **CC BY-NC-SA 4.0** restrictions, which are suitable for non-commercial research use but not an unrestricted deployment path. Preserve licence texts and checkpoint hashes, and do not imply the NTRO deployment can ship these components without approval.

The required architecture decision remains:

- Classical permissive verified path: mandatory and independently operational.
- MASt3R-SLAM: optional adapter for research/demo use after licence and hardware checks.
- Future deployment: replace, relicense, or obtain permission if non-commercial terms conflict with the intended use.

### D.10 Judge-safe claims

Safe:

> “We evaluated MASt3R-SLAM as an optional real-time dense reconstruction prior. Drishti3D adds telemetry synchronization, metric ENU alignment, independent validation, dynamic filtering, provenance-aware measurement, and offline evidence packaging.”

> “The paper reports approximately 15 FPS in its tested configuration. We report our own measured throughput on the RTX 4060 separately.”

Unsafe:

- “MASt3R-SLAM makes our output metrically accurate.”
- “It reconstructs occluded surfaces as measured geometry.”
- “It always beats DROID-SLAM.”
- “It will run at 15 FPS on any NVIDIA GPU.”
- “Its confidence score proves measurement accuracy.”
- “The model is ready for unrestricted operational deployment.”

### D.11 Final decision

| Question | Decision |
|---|---|
| Should it replace COLMAP in the MVP? | No |
| Should it be evaluated? | Yes, high priority after the verified path works |
| Best product role | Fast dense preview, initializer, difficult-scene recovery |
| Is it independently metric/georeferenced? | No; align through GNSS/RTK/GCP and validate |
| Can its points be measured by default? | No; not until promotion through geometric verification |
| Is the paper’s 15 FPS our promised speed? | No; benchmark the exact hardware and configuration |
| Does it strengthen the SIH story? | Yes, when the team clearly explains the additional Drishti3D engineering |

The paper materially strengthens the architecture by showing that a learned two-view 3D prior can support real-time tracking and coherent dense mapping. Its greatest value to Drishti3D is not as a magic replacement for photogrammetry, but as a fast, robust geometric prior inside a larger system that supplies metric scale, geographic coordinates, validation, provenance, and operational trust.
