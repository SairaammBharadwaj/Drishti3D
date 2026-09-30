# Drishti3D: current project and technical report

**SIH26158 · NTRO · Software · Robotics and Drones**  
**Snapshot:** 22 September 2026, revision `9506a31`.  
**Purpose:** technical dossier, SIH presentation preparation and implementation handoff.  
**Status:** working research prototype; organiser-target compliance and calibrated measurement accuracy remain to be demonstrated.

## 1. Executive abstract

Drishti3D reconstructs a scene from a recorded monocular UAV pass and associated telemetry, then lets an analyst inspect the geometry and ask measurement questions. Its main design emphasis is traceability: distinguish observed geometry from assisted or unsupported geometry, carry coordinate and uncertainty information, and explain why a measurement should or should not support a decision.

The current system combines a React/Three.js web interface, a FastAPI service, a Python reconstruction package, OpenCV and optional COLMAP/dense MVS. It includes mission management, video and telemetry processing, georegistration, measurement tools, evidence and provenance, targeted refinement, quality reports and standard point-cloud/mesh exports. Optional learned components and research engines exist, but their integration maturity differs; they are not all available as complete website workflows.

Fresh checks passed 444 main tests, all 15 previous-review checks, and the frontend production build. Saved artifacts include a 2.14-million-point UseGeo cloud and a 251,785-point AGZ cloud. These demonstrate functioning reconstruction; they do not establish centimetre accuracy or the organiser's speed and completeness targets. The companion critical review specifies the remaining experiments and improvements.

## 2. Problem, users and objectives

The [official SIH statement](https://www.sih.gov.in/sih2026PS) asks for single-pass UAV video reconstruction suitable for metric and geospatial analysis. Its [linked attachment](https://drive.google.com/file/d/119hjXkLhMW_AhQ4cyYz-XJgcVz4BA-hD/view) supplies the output targets and scoring rubric, reproduced in the companion review. The product should minimise dependence on extensive ground control while tolerating imperfect video and telemetry.

Intended users are analysts who need to inspect terrain, structures, infrastructure and obstacles from a captured pass. Civilian applications could include infrastructure inspection, disaster assessment, site documentation and environmental observation; these are proposed applications, not completed deployments or partnerships.

The principal objectives are:

1. Produce inspectable, georeferenced geometry from one recorded trajectory.
2. Support clear distance, height and area questions with explicit units and evidence.
3. Identify incomplete or unreliable regions rather than hide them.
4. Improve an eligible question using unused observations from the same recording.
5. Export geometry and evidence for independent inspection.
6. Validate accuracy, completeness and runtime on representative held-out data.

## 3. End-user workflow

**Overview → mission library → upload/setup → processing monitor → analysis workspace → question/refinement → report/export.**

The overview introduces the project through a spatial visualisation and routes into missions. The library supports finding and resuming missions. Setup accepts video, telemetry and basic camera parameters. The processing screen presents staged progress. The workspace displays point geometry, camera context and measurement/question controls, while the report collects quality indicators and downloadable artifacts.

The redesign includes responsive navigation, clearer states, resumable draft setup and a WebGL-unavailable fallback. Its illustrative overview scene must remain recognisable as a research/demo asset rather than a fresh user reconstruction. The intended next UX improvement is consistent evidence status at every result: coordinate frame, measurement definition, estimated/calibrated state, blocking reason and reconstruction version.

## 4. Architecture and data flow

```text
Native video + GPS/flight metadata + optional camera/sensor data
                            |
             React / TypeScript web client
        mission setup, progress, Three.js viewer, questions
                            |
                    FastAPI HTTP / SSE
            validation, routes, SQLite mission records
                            |
          in-process serial reconstruction job executor
                            |
     decode/timestamps -> quality filtering -> keyframes
                            |
        OpenCV SfM or optional COLMAP reconstruction
            optional learned matching/masking/depth
                            |
       camera refinement -> optional dense MVS/fusion
                            |
          telemetry alignment / ENU georegistration
                            |
         cloud + mesh + observations + manifest + report
                            |
        measurements / evidence / targeted refinement
                            |
             viewer payloads and export artifacts
```

This is a logical flow, not a claim that every engine uses identical internal stage ordering. Full-resolution artifacts remain on the backend; browser geometry is sampled for interactive display. Mission state is stored in SQLite, but live jobs use in-process state and do not yet form a durable distributed queue.

### Main code locations

Paths below are relative to `drishti3d/`.

| Area | Code | Responsibility |
|---|---|---|
| Web application | `frontend/src/`, especially `views/` and `api.ts` | Overview, mission setup, monitor, workspace, reports and API contracts. |
| API and persistence | `backend/app/` | Project/request validation, route handling, database access and results. |
| Job execution | `backend/app/jobs.py` | Serial heavyweight work and live progress state. |
| Pipeline configuration | `reconstruction/drishti_recon/pipeline.py` | Orchestration, engine options, reconstruction, artifacts and timings. |
| Geometry and alignment | `sfm.py`, `geo.py`, `sensors.py` | Camera/point reconstruction, coordinate transforms, telemetry and corrections. |
| Evidence and decisions | `evidence.py`, `questions.py`, `uncertainty.py`, `refinement.py` | Observation support, measurement policy, uncertainty estimates and additional-frame refinement. |
| Mesh and exports | `mesh.py`, `exports.py` | Mesh creation, PLY/LAS/GLB, trajectory/GeoJSON and reports. |
| Research AI adapters | `ai_adapter.py`, `dense3d.py`, `vggt_engine.py` | Experimental learned reconstruction interfaces and implementations with different readiness levels. |

## 5. Technology stack: actual versus optional

Version ranges below reflect project declarations unless a resolved build version is explicitly stated. They are not a fully pinned deployment inventory.

| Layer | Current technology | Role and qualification |
|---|---|---|
| UI | React 18.3.1 range, TypeScript 5.6.2 range, React Router 6.26.2 range | Component UI, typed client and navigation. |
| Frontend tooling | Vite 5.4.x; verified build used 5.4.21 | Local development and production bundles. |
| Graphics | Three.js 0.169 range, native canvas/SVG | Point-cloud interaction and overview visualisation. Cesium and MapLibre are not the current stack. |
| API | FastAPI ≥0.110, Uvicorn ≥0.27, Pydantic ≥2.5 | Request validation, uploads, APIs and event streaming. |
| Persistence | SQLAlchemy ≥2, SQLite, filesystem artifacts | Mission/configuration records and reconstruction outputs. |
| Language/runtime | Python ≥3.10 declared; review environment uses Python 3.12 | Reconstruction and backend computation. |
| Numeric/vision core | NumPy ≥1.24, SciPy ≥1.10, OpenCV ≥4.8 | Linear algebra, optimisation, features, matching and geometry. |
| Geodesy | pyproj ≥3.5 | CRS transformations and georeferencing. |
| Video | imageio ≥2.31, imageio-ffmpeg ≥0.4, FFmpeg-related probing/decoding | Frames and real video timestamps. |
| Optional reconstruction | COLMAP/PyCOLMAP; CUDA COLMAP MVS | Alternative SfM and multi-view densification; deployment must pin compatible versions. |
| Optional exports/mesh | Open3D ≥0.17, laspy ≥2.5 | Mesh processing/GLB and LAS export. GLB uses Open3D, not a separate texture pipeline. |
| Optional AI | PyTorch/Torchvision, DISK/ALIKED + LightGlue, Depth Anything V2; MASt3R/VGGT research paths | Learned matching, masking or depth/reconstruction. The matcher defaults to DISK; SuperPoint is restricted by default. Model availability is not proof of accuracy. |
| Packaging | Python package `drishti-recon` 0.1.0, npm frontend, Docker configuration | Local deployment and service packaging; the GPU-worker container entry is currently a placeholder. |
| Verification | pytest, TypeScript build, earlier Playwright UI checks | Unit/regression checks and frontend verification. |

Celery, Redis, Kubernetes, a production cloud scheduler, full authentication/RBAC and a durable multi-worker GPU service are **not current implemented infrastructure**. They must not appear as completed stack components in the SIH deck just because an older planning document suggested them.

## 6. Reconstruction and measurement methodology

### Ingestion, frame selection and telemetry

The pipeline ingests video, validates metadata, extracts frames with timestamp awareness, evaluates image quality and selects keyframes. Telemetry is associated with camera time, then used to establish metric/geographic scale and placement. Optional sensor handling includes guarded time-offset estimates, lens correction and lever-arm processing. Rolling-shutter assessment is not a complete rolling-shutter correction model, and the current system is not a full IMU/GNSS factor-graph fusion implementation.

### Geometry

The default path uses OpenCV feature-based SfM, camera registration/triangulation and optimisation. Optional learned features can change correspondence generation. The COLMAP path provides an alternative reconstruction engine; dense MVS can add image-supported points through stereo depth and fusion. Meshing uses available surface reconstruction components and vertex colours.

More points do not automatically mean better dimensions. Weak triangulation, poor camera calibration, motion, incorrect scale and surface sampling can all survive densification. Density, image reprojection residual, camera registration fraction, geometric accuracy and coverage must be reported separately.

### Georeferencing

Camera trajectories and telemetry support a similarity alignment into a local east-north-up coordinate system. Export routines provide projected coordinates and a georeference sidecar where applicable. The LAS export records a projected CRS and ellipsoidal height; that is not automatically a local orthometric/MSL height.

Camera/GPS fit residual measures agreement with the alignment inputs. It is not independent accuracy. The current production guard blocks decision-grade use when trajectory conditioning is flagged; the critical review explains why the underlying planarity interpretation still needs refinement.

### Provenance, evidence and uncertainty

The data model distinguishes observed confidence levels, assisted geometry, excluded dynamics and unobserved regions. Evidence can connect a measurement question to supporting observations and artifact versions. Sparse point covariance estimates derive from image geometry while holding poses fixed; dense uncertainty is approximate. Current values are estimates, not calibrated error guarantees.

Calibration-profile lifecycle code exists, but the operational evaluation path currently supplies no released profile. Therefore the presentation must distinguish implemented calibration infrastructure from validated, operationally selected calibration.

### Measurements and refinement

The current tools cover lengths/polylines, vertical differences and XY-projected polygon areas. XY area is not sloped-surface area; a vertical difference between selected points is not automatically building height above the correct local ground. Source-image anchors and better endpoint selection are priority extensions.

**AI is already integrated in this refinement path:** `RefinementEngine._transfer_backend` loads LightGlue/DISK when available, with a classical fallback. The September 20 targeted-refinement benchmark documents using the learned matcher to transfer endpoint locations through image correspondences. This is more mature than the separate MASt3R-SLAM/VGGT web adapter stubs. The wizard also exposes optional learned depth-prior densification and semantic masking, subject to usable dependencies and weights; neither is enabled in the two principal COLMAP/MVS run manifests reviewed above.

Targeted refinement can seek more useful observations from the existing recorded pass for a specific question. It is conditional and budgeted work, not an “accuracy boost” that always succeeds. If no useful frames remain or the limiting factor is missing calibration, wrong datum or genuinely unobserved geometry, the correct outcome may be no improvement or refusal.

## 7. Implemented capability and maturity register

| Capability | Maturity at this revision |
|---|---|
| Mission creation, uploads, saved results and resumed drafts | Implemented web workflow. |
| OpenCV reconstruction and telemetry alignment | Implemented baseline. |
| COLMAP and dense MVS | Implemented pipeline and saved runs; incomplete normal-wizard exposure. |
| Basic distance/height/area interactions | Implemented; endpoint and uncertainty limitations apply. |
| Measurement questions, evidence and refinement | Implemented research workflow; independent accuracy gain and calibration remain open. |
| Coverage/provenance displays | Implemented internal indicators; external completeness validation missing. |
| PLY/LAS/GLB and report exports | Implemented paths; optional dependencies apply. |
| Photo-textured UV mesh, GeoTIFF, FBX | Not established implemented outputs. |
| Learned reconstruction options | Mixed experimental readiness; some web adapter methods remain unimplemented. |
| Air-gapped operation | Plausible after dependencies/weights are provisioned; clean offline deployment rehearsal not completed in this audit. |
| Persistent queue, restart recovery, multi-user controls | Incomplete productionisation. |
| Organiser metric/runtime compliance | Not yet demonstrated. |

## 8. Validation and current evidence

The review's fresh verification results are **444 main tests passed, 15/15 follow-up checks passed, and a successful TypeScript/Vite production build**. These are engineering checks, not independent field validation. No new full GPU reconstruction or LiDAR scoring run was performed for this document.

The UseGeo artifact contains 60/60 registered selected cameras and 2,138,943 points. Its raw LiDAR nearest-surface comparison reports median 1.360 m and RMSE 1.283 m, with a substantial vertical bias. The current AGZ dense artifact contains 80/80 registered selected cameras and 251,785 points. Its camera/GPS alignment RMSE is 6.143 m; that is not surveyed positional error. Both current dense runs take over 20 minutes on short derived videos.

The controlled AGZ engine comparison recorded OpenCV at 310.7 seconds and COLMAP at 86.4 seconds for that experiment—approximately 3.60× faster. That experiment used CPU reconstruction; its laptop's RTX 5060 8 GB GPU was not used by those compared engines. Do not combine those sparse-stage numbers with dense end-to-end performance or present them as a universal speedup.

The targeted-refinement benchmark contains 20 questions for the full AGZ capture and each of two same-flight halves. On the full capture, “blocked only by calibration” yield rose from 8 to 15 under targeted refinement versus 10 with uniform selection. Targeted runtime was 88.6 seconds versus 135.4 seconds for uniform selection. Those are internal readiness outcomes, not accepted measurements, and the three partitions are not independent flights. A further independent segment could not supply extra unused frames. These limitations should stay attached to any chart of that benchmark.

An older six-trial synthetic matcher ablation (`docs/benchmarks/2026-09-04_matcher_ablation/BENCHMARK.md`) compared the classical baseline with DISK/LightGlue. Reported median completeness increased from 62.4% to 64.3%, while median dimensional error increased from 2.22% to 3.11% and median runtime from 97.9 to 118.0 seconds. Its recorded tree was dirty, so it cannot be reproduced from the listed commit alone; these are historical, protocol-dependent results, not a current real-flight verdict. They nevertheless show why AI components should be evaluated individually rather than assumed to improve every metric.

### Evidence inventory

Repository-relative sources:

- `data/runs/usegeo_1__first/artifacts/quality_report.json`
- `data/runs/usegeo_1__first/lidar_score.json`
- `data/runs/agz_dense_pass__dense_mvs/artifacts/quality_report.json`
- `docs/benchmarks/2026-09-19_agz_single_pass_engines/RESULTS.md`
- `docs/benchmarks/2026-09-20_f4_second_capture/RESULTS.md`
- `docs/benchmarks/2026-09-21_dense_mvs/RESULTS.md`
- Root `DECISIONS.md` and `TESTS_AND_RESULTS.md`, which include newer dimensional notes requiring the qualification in the critical review.

Some historical benchmark documents describe earlier cloud counts or uncertainty calculations. Current JSON artifacts take precedence for the snapshot values above. The project should next capture artifact hashes, complete commands, dependency locks and hardware/resource logs in each benchmark manifest.

## 9. Feasibility, resources and deployment

The classical path can run without downloading learned weights, which provides a practical development and fallback route. Dense reconstruction and optional learned models add GPU, memory and dependency demands. A recorded laptop experiment is not a universal minimum hardware specification; benchmark actual target hardware before promising deployment capacity.

Required resources are a representative video/telemetry collection, independently referenced test locations, calibrated camera information where available, local SSD capacity for frames/intermediates, and suitable CPU/GPU resources for the chosen configuration. Network-independent deployment requires packaging dependencies and permitted weights in advance and checking for runtime download attempts.

A useful operational cost model is:

```text
cost per processed mission = compute + storage + operator time
                           + reference-data acquisition + support
```

No verified rupee estimate, operating-cost reduction, customer count or market-size claim is available from the repository. Measure operator minutes, runtime, peak memory, stored bytes and repeat-failure cost before attaching a financial benefit to the proposal. Infrastructure ownership and the organisation's deployment constraints should determine local workstation versus managed server packaging.

## 10. Risks and mitigations

| Risk | Practical mitigation |
|---|---|
| Small reprojection error masks wrong real-world geometry. | Independent named checkpoints and dimensions; holdout splits; publish failure tails. |
| GPS/datum/time error shifts an otherwise coherent model. | Coordinate/time provenance, robust sensor checks and appropriate pose priors. |
| Missing overlap, blur, vegetation or moving objects limit reconstruction. | Quality assessment, dynamic masks, category-specific tests and explicit refusal/gap maps. |
| Dense MVS exceeds the processing budget. | Profile stage cost, adaptive image scale, bounded neighbours, ROI refinement and complete-run timing. |
| Confidence becomes a misleading accuracy claim. | Separate estimates from calibrated intervals and validate coverage/width on unseen flights. |
| A model licence is incompatible with intended deployment. | Pin code and checkpoint licences, review actual terms, retain an approved alternative engine. |
| UI configuration silently differs from the successful research run. | Shared typed configuration schema and persisted effective settings. |
| Restart or concurrent actions damage mission state. | Durable queue/state, cancellation, locking and atomic artifact versions. |
| Inferred surfaces look measured. | Persistent provenance styling and exclusion from supported measurement unless independently validated. |

## 11. Impact and benefits: hypotheses with measurable outcomes

The potential benefit is quicker conversion of captured video into usable spatial evidence with less manual interpretation. Traceable measurements could reduce unnecessary confidence in incomplete reconstructions and help operators decide whether the existing recording is sufficient.

Measure impact through time to the first useful answer, median operator effort, fraction of requested tasks answered within tolerance, false acceptance rate, refusal rate, exported-artifact usability and number of repeat captures avoided. Repeat-capture savings are a hypothesis until measured. Societal/environmental benefits should be linked to actual inspection or response workflows rather than generic claims about saving lives or reducing emissions.

The immediate product objective is an analyst workstation prototype with reproducible evaluation. A broader multi-user geospatial platform is a later stage. This scope is credible and leaves room for a distinctive measurement workflow without pretending to replace every feature of mature photogrammetry products.

## 12. Development roadmap and presentation message

The next release should freeze evaluation claims, preserve calibration settings, expose the strongest reconstruction path, and publish native-video runtime and independent landmark results. Then integrate released calibration profiles, improve source-based endpoint selection and validate targeted refinement against actual physical error. Durable job execution and export completeness follow as deployment requirements.

Recommended headline: **“From one UAV pass to traceable spatial measurements.”**

Recommended technical message: **“We combine reconstruction with measurement-specific evidence, explicit uncertainty limits and targeted reuse of the original video.”**

Avoid claiming survey-grade accuracy, guaranteed centimetre precision, full autonomy, real-time operation, first-ever video reconstruction or proven superiority to commercial products. Those claims are not established by current artifacts. A clear account of what works, what fails and how it will be measured is more persuasive than an inflated feature list.

The [six-slide handoff](SIH_SLIDE_HANDOFF.md) translates this report into the current official SIH template. Detailed competitor sources and the measurement roadmap are in [the critical review](CRITICAL_REVIEW.md).
