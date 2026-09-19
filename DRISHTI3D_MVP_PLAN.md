# Drishti3D — MVP product, research, and implementation plan

**Prepared:** 19 September 2026  
**Problem:** SIH26158 — Single-Pass Drone Video to Accurate 3D Model Generation System  
**Status:** Proposed design and validation targets, not a report of completed capabilities.  
**Scope of this deliverable:** Planning only. No application changes or dataset downloads.

**Reading guide:** [Product](#1-the-product-to-build) · [Feature scope](#4-the-minimum-compelling-feature-set) · [Architecture](#5-technical-architecture-and-implementation-decisions) · [Datasets to obtain](#6-datasets-what-to-obtain-and-why) · [Proof and benchmarks](#7-proving-superiority-with-experiments) · [Build sequence](#8-implementation-sequence-effort-and-decision-gates) · [Drawbacks](#9-drawbacks-mitigations-and-residual-limits) · [Stakeholder survey](#10-stakeholder-survey-and-pilot-validation) · [Demo](#11-the-demonstration-that-makes-the-advantage-visible).

## 1. The product to build

Build **Drishti3D: One Pass, Defensible Measurements**.

An operator uploads one continuous drone video and its telemetry, selects a structure or area, and receives an interactive, georeferenced 3D model. The operator can ask for a width, height, distance, or area at a specified tolerance. Drishti3D returns the result, its evidence and uncertainty, or a concrete explanation of why the question cannot yet be answered. When evidence is insufficient, it searches unused frames from the **same pass** and spends additional computation on that particular measurement.

The distinctive experience is a **Tolerance Lens**: change the required tolerance and immediately see which saved measurements qualify, which need refinement, and which are unanswerable from this capture. Click a result to see the original pixels, camera views, scale source, and processing history. Click **Improve this measurement** to recover useful evidence that a uniform reconstruction budget missed.

The core loop is:

```text
One video + telemetry
        ↓
Georeferenced 3D model
        ↓
Select a question + required tolerance
        ↓
Answer with evidence ── or ── Explain the missing evidence
                                    ↓
                        Reprocess useful frames from this pass
                                    ↓
                          Update result and evidence
```

**Primary user:** a field mapping or infrastructure assessment team needing dimensions and coverage information before leaving a site. **Flagship setting:** a campus/service-road corridor with a building, an access opening, a roof, vegetation, and partially hidden surfaces. This is reproducible, accessible, and representative of rapid site assessment.

Example questions: “What is this opening's width?”, “How high is this visible facade?”, “What is the horizontal area of this observed roof footprint?”, and “Which of these measurements meet ±20 cm?” A width comparison is a geometric result; it does not establish vehicle passage, road load capacity, structural stability, or public safety.

**Why this is a competitive bet:** a reconstruction becomes useful when someone can act on its measurements and understand their limits. The innovation hypothesis is that task-specific evidence recovery and calibrated measurement acceptance produce more useful answers per minute from a constrained pass. That hypothesis is testable; neither universal superiority nor a hackathon win can be guaranteed.

## 2. Problem fit and the boundaries we must respect

### 2.1 What the statement requires

The local brief and the currently accessible [community statement mirror](https://sih2026.vuce.in/ps/SIH26158) describe a single moving-UAV video, GPS and flight metadata, producing georeferenced metric geometry for visualization, measurement and analysis. Listed subjects include terrain, structures, facades, rooftops, roads, vegetation and obstacles. The challenges include limited views, blur/compression, lighting, moving objects, sensor error, processing speed, occlusions and limited ground control. Optional inputs include IMU, barometer, intrinsics and RTK/PPK.

The [official portal](https://sih.gov.in/sih2026PS) and the mirror's dataset attachment could not be retrieved in this research session. The local brief is therefore the working requirement, cross-checked against the mirror; official attachments and submission dates remain unverified. This plan uses relative implementation days and does not assume a contest deadline.

| Requirement | MVP commitment | Boundary |
|---|---|---|
| Single flight path | One continuous clip is the complete primary reconstruction input | No orbit/grid frames secretly added to the scored single-pass result |
| Metric and geographic output | Telemetry-aware reconstruction, scale provenance, coordinate-system metadata | Ordinary GNSS is not a centimetre accuracy guarantee |
| Scene reconstruction | Colored point cloud throughout supported regions; textured mesh on supported rigid surfaces | Terrain below canopy and unseen building sides remain unknown |
| Measurement and analysis | Distance, vertical height, projected area, tolerance checking and evidence inspection | No automatic engineering certification |
| Operational speed | Progressive overview followed by targeted refinement | Near-real-time is a measured latency target; full live streaming is later |
| Occlusion handling | Spatial unknown/occluded regions; optional clearly labeled visual completion | No claim to recover the true geometry of never-observed surfaces |

### 2.2 Define “survey ready” precisely

This plan is ready for a **literature survey, stakeholder review, implementation, and a controlled field pilot**. Survey-grade deliverables require independent positional validation for the declared capture and accuracy class. Merely implementing this architecture does not confer that status.

Monocular imagery alone leaves metric scale ambiguous. A learned metric-depth model supplies a statistical prior, not an independently traceable scale reference. GNSS trajectory, calibrated sensors, surveyed control or known dimensions can constrain scale, subject to observability and their own uncertainty.

A perfectly straight camera trajectory leaves rotation around its trajectory weakly or unobservable from camera positions alone. Planarity and weak parallax introduce other conditioning problems. Detect rank/conditioning problems; use trustworthy gravity/orientation or suitably distributed control when available; otherwise downgrade geographic/height claims. Do not hide these failures behind a small alignment residual.

### 2.3 Keep three different product claims separate

| Output class | Required basis | Allowed wording |
|---|---|---|
| Relative reconstruction | Image evidence; no accepted scale source | “Shape only; arbitrary units” |
| Metric reconnaissance | Valid scale/georeference model, stated uncertainty and capture limits | “Estimated dimensions/coordinates at the reported tolerance” |
| Independently validated survey deliverable | Independent checkpoints, documented reference accuracy, CRS/datum, acceptance against an agreed specification | “Validated for this mission and this declared accuracy class” |

Ground control used in optimization is never reused as independent validation. A known length used to scale the model cannot also prove dimensional accuracy. A visualization mesh and its interpolated triangles are never automatically measurement evidence.

## 3. What the research and current repository actually imply

### 3.1 Competitive and literature survey

This is a focused survey of directly relevant approaches, not an exhaustive patent or market novelty search. Sources were checked on 19 September 2026. Product documentation establishes advertised capabilities, not independent comparative performance.

| Existing approach | Documented strength | Implication for our design |
|---|---|---|
| [SkyeBrowse](https://www.skyebrowse.com/) | Video-to-3D with measurement-oriented public-safety workflows | “Drone video to 3D in minutes” is already a product category |
| [PIX4D quality reporting](https://support.pix4d.com/hc/en-us/articles/16173344040733) | GCP/checkpoint reporting, camera and calibration diagnostics | A quality report or a confidence color alone is not sufficient differentiation |
| [Agisoft Metashape](https://www.agisoft.com/pdf/metashape_2_3_en.pdf) | Photogrammetry, point-cloud confidence filtering and established modeling workflows | Do not claim competitors lack confidence or offline reconstruction |
| [OpenDroneMap](https://docs.opendronemap.org/) | Video-frame controls, georeferenced products, GCP and accuracy workflows | Use as an open end-to-end baseline; video input is not unique |
| [COLMAP](https://colmap.github.io/faq.html) | SfM/MVS, bundle adjustment, model alignment and georegistration tools | Use mature geometry machinery and build the product contribution above it |
| [MASt3R-SLAM, CVPR 2025](https://openaccess.thecvf.com/content/CVPR2025/html/Murai_MASt3R-SLAM_Real-Time_Dense_SLAM_with_3D_Reconstruction_Priors_CVPR_2025_paper.html) | Dense monocular reconstruction using learned pairwise geometry | A useful optional engine; reconstruction priors are established research |
| [MASt3R-Fusion](https://github.com/GREAT-WHU/MASt3R-Fusion) | Combines learned geometry with IMU/GNSS | “AI plus telemetry” cannot be the novelty claim either |
| [VGGT](https://github.com/facebookresearch/vggt) and [MapAnything](https://github.com/facebookresearch/map-anything) | Feed-forward camera/geometry prediction; MapAnything supports metric reconstruction | Evaluate one bounded learned candidate; no need to train a foundation model |
| [Prediction-based UAV next-best-view research](https://isprs-annals.copernicus.org/articles/X-2-W2-2025/207/2025/) | Coverage-aware view planning is already studied | Recapture suggestions alone are not a novel research contribution |

**Defensible differentiation to evaluate:** the combination of a user-selected tolerance, measurement-specific same-pass refinement, calibrated abstention, and a portable chain from each reported measurement back to source pixels. We have not established that no competitor offers any part of this combination.

The potential long-term advantage is the dataset of real single-pass failures, measurement outcomes and useful recovery actions; validated uncertainty calibration; and interoperability with existing survey engines. The UI and the choice of a pretrained model are readily copied.

### 3.2 Current assets worth reusing

Inspected repository state: commit `9a55723` plus existing uncommitted user changes. Hardware probe found an **RTX 5060 Laptop GPU with 8151 MiB VRAM**; older documents mention a different GPU. Treat the current probe as the planning baseline and benchmark on the actual deployment machine.

| Existing asset | What inspection supports | Planned treatment |
|---|---|---|
| FastAPI, React/Three.js, mission storage | Working application structure is present | Reuse; revise workflows around questions and evidence |
| `sfm.py`, `bundle.py`, `colmap_adapter.py` | Classical reconstruction and optimization implementations exist | Compare engines on identical captures before selecting a production default |
| `sensors.py`, `sync.py`, `geo.py` | Timing/calibration/georeferencing foundations exist | Audit and integrate with the new measurement contract |
| `uncertainty.py` | Point covariance, scale contribution and calibration helpers exist; camera poses are treated as fixed in the base model | Extend for measurement-level correlated errors and domain-aware calibration |
| `coverage.py`, `capture.py`, `verify.py` | Coverage, heuristic capture advice and AI corroboration already exist | Reuse interfaces, strengthen evidence rules, replace heuristic claims with validated results |
| Learned adapters | MASt3R/VGGT/depth integration code exists | Availability is not proof of quality or a production license |
| Benchmark harness | Historical results and failures are stored | Extend; do not relabel historical runs as current results |
| `data/real_drone/AGZ_subset/` | Images, navigation logs and calibration files are present | Inventory and hash before requesting another download |

The [10 September analytic benchmark](drishti3d/docs/benchmarks/2026-09-10_analytic_accuracy/RESULTS.md) records **2 failures out of 12 synthetic trials**, both in the low-parallax regime, for its specific baseline configuration. This is evidence that failure modes matter; it is not a performance claim about today's full application. The [work log](drishti3d/docs/WORK_LOG.md) also records real experiments where apparently reasonable changes made reconstruction worse.

One concrete planning concern: the inspected coverage code considers a voxel visible when `z <= nearest + tolerance`; `nearest` can be infinity where no depth was reconstructed, and visible empty cells can then become `EMPTY`. The new design must require a finite, supported depth termination before asserting observed free space. A hole in a sparse cloud does not prove a clear corridor. This observation is a code-reading finding, not a newly executed test.

The task is therefore **a product and measurement-model upgrade**, with reconstruction improvements where benchmark evidence justifies them. Rebuilding the entire stack would consume effort without creating differentiation.

## 4. The minimum compelling feature set

### F1. One-pass reconstruction with a useful progressive result — essential

Upload video, GPS/flight metadata and optional calibration. Show timestamp coverage, blur, motion/parallax and telemetry warnings. Produce the flight path, a colored cloud and visible-surface mesh where supported. A quick overview is labeled provisional until refinement and checks finish.

**Done when:** three development clips and three locked evaluation clips pass ingestion; valid scenes produce reproducible metric artifacts; a deliberately invalid scene produces an intelligible failure with preserved diagnostics. No fabricated geometry is substituted for a failed run.

### F2. Tolerance Lens — signature feature

The user selects a measurement type and required absolute tolerance. Each measurement card has one of: **meets requirement**, **estimated only**, **needs refinement**, or **not observable**. Spatial overlays indicate supporting geometry, but the acceptance result belongs to the complete measurement, including its scale, orientation, endpoint and selection errors.

An illustrative card, not a claimed result:

```text
Opening width: 3.42 m
95% calibrated interval: [3.30, 3.54] m
Requested tolerance: ±0.20 m → meets requirement
Scale: GNSS + documented control     Local image support: 7 views
Dominant limitation: endpoint localization
[Show evidence] [Improve this measurement] [Export]
```

Moving the requirement to ±0.05 m changes this card's status. It does not change the model or its measured interval. Without validated interval calibration, show an estimated range and **estimated only**, not a calibrated probability claim.

For a threshold query such as width ≥3.20 m: return **above threshold** only when the accepted interval lies entirely above it, **below threshold** when entirely below, and **indeterminate** when it crosses it. This is a geometric threshold comparison, not operational clearance authorization.

**Done when:** the same model produces correct acceptance changes across tolerances; unsupported measurements cannot be exported as accepted; model/version updates invalidate stale results.

### F3. Evidence Replay and Measurement Passport — signature feature

Click a measurement to replay its source frames, marked pixels, view rays and camera positions. Show which frames informed geometry and which were withheld for corroboration. Include scale source, CRS/datum, calibration identity, dynamic/occlusion flags and uncertainty limitations.

Export a small standalone evidence bundle. A verifier must be able to recompute the reported number and validate artifact hashes without the running backend. Full reconstruction reproducibility requires the larger source bundle and pinned dependencies; the small passport alone cannot reproduce every reconstruction decision.

**Done when:** a clean verifier reproduces saved dimensions within declared numerical precision; a modified source/artifact is detected; selecting a measurement displays its actual supporting images rather than generic scene thumbnails.

### F4. Improve This Measurement — principal engineering contribution

Preserve a low-cost index of the full original clip. When the user selects a weak measurement, retrieve unused sharp frames that see the relevant surfaces from useful baselines. Add a bounded number, rematch locally at higher resolution, refine the connected camera/point neighborhood, and re-evaluate the measurement.

This is **same-pass evidence recovery**. It exploits observations that were not processed initially; it cannot create parallax that the flight never captured.

Show: old interval, new interval, additional runtime, new supporting frames and remaining limits. If the new estimate moves substantially, show the change explicitly; a narrower interval alone is not proof of improvement.

**Done when:** on frozen questions and equal added compute budgets, targeted refinement improves correct accepted-answer yield or reaches the same quality faster than uniform refinement. No improvement is an acceptable experiment result and must be visible.

### F5. Unknown-Space Map and Missing-Evidence Cards — essential

Distinguish supported surfaces, weak surfaces, occluded regions, regions outside usable views, dynamic contamination and narrowly supported free-space rays. A hidden wall remains unknown. A moving vehicle is recorded as an observation excluded from static geometry; it is not evidence that the road underneath was clear.

Each rejected question gets a specific explanation: “far endpoint never visible”, “scale insufficient”, “two views have almost identical ray direction”, or “opening boundary moved during capture.” Suggested actions prioritize existing-data processing, metadata correction or a manual survey. Optional extra-view guidance is P1, outside the single-pass score.

**Done when:** withheld/hidden surfaces and no-depth pixels do not become accepted evidence; the stated reason is supported by saved diagnostics.

### F6. Offline mission package and honest comparison report — essential

Run locally after installing dependencies and weights. Export PLY/LAS, a supported-surface GLB, measurements CSV/GeoJSON, evidence JSON and a human-readable report. Include a same-input baseline comparison, runtime, unknown area and independent errors where truth exists.

**Done when:** a mission can be processed, inspected and verified with networking disabled; interrupted work resumes from a valid stage; GIS imports preserve units and coordinate interpretation.

### Scope deliberately postponed

Trained Gaussian splatting, automatic temporal change detection, natural-language chat, multi-drone collaboration, autonomous flight commands, city-scale streaming, stockpile volume on unknown bases, and general-purpose automatic object interpretation are P2. They can be valuable later, but none is required to establish the six-feature product.

A fixed set of explicit geometric questions is the MVP interface. Do not put an LLM between the operator and the measurement calculation.

## 5. Technical architecture and implementation decisions

### 5.1 Processing and storage boundaries

```text
React + Three.js workspace
        │ REST / job events
FastAPI + SQLite metadata
        │ durable job record
Isolated reconstruction worker — one GPU job at a time
        │
        ├─ immutable source video / telemetry / calibration
        ├─ frame index + image observations + camera graph
        ├─ reconstructed geometry + spatial evidence
        ├─ measurements + uncertainty calibration reference
        └─ versioned artifacts + report + reproducibility manifest
```

Keep a modular monolith. Use a separate worker process with heartbeat, cancellation and persisted stage completion. SQLite is sufficient for one workstation; Redis/Celery and PostGIS are later choices when concurrency and spatial queries justify them.

Stage flow: validate → synchronize → index frames → select views → reconstruct → georeference/refine → build dense supported geometry → assemble evidence → answer questions → export. Targeted refinement creates a new artifact version, preserving the original.

### 5.2 Inputs, timing and calibration

1. Use FFmpeg/ffprobe timestamps, including variable frame rate; do not derive all timing from frame number divided by nominal FPS.
2. Define telemetry time basis, units, GNSS fix type, horizontal/vertical covariance, datum and missing-value behavior. Preserve original logs.
3. Use camera-model-specific distortion. Undistorted images carry their new intrinsics; never undistort twice. Detect zoom/crop/stabilization changes and split or reject unsupported camera changes.
4. Estimate time offset only when the motion contains information to identify it; otherwise require an offset or carry uncertainty. Include camera-to-GNSS lever arm, IMU extrinsics and the moving gimbal where relevant.
5. Flag strong rolling-shutter motion. Initial MVP uses conservative rejection/downweighting; a rolling-shutter optimizer is a later improvement if field data demands it.
6. Scene cuts produce separate sequences or a rejected input. They are not bridged by invented camera motion.

### 5.3 Reconstruction engine selection

Start the field reference implementation with **COLMAP/PyCOLMAP SfM + bundle adjustment**, retaining the repository OpenCV engine as a transparent CPU fallback and experimental baseline. [COLMAP documents](https://colmap.github.io/faq.html) model alignment, bundle-adjustment practices and dense reconstruction constraints; pin the actual tool version and probe GPU capabilities rather than assuming every wheel includes every feature.

Default to SIFT initially. Trial **DISK + LightGlue** on failed or weak pairs, using identical keyframes and budgets. [LightGlue's repository](https://github.com/cvg/LightGlue) distinguishes its Apache-2.0 code/weights and DISK from SuperPoint's different restrictions. Record extractor and matcher licenses separately.

Use adjacent pairs plus temporal skips and actual overlap evidence. Preserve long-baseline connections that improve depth observability. Add disconnected frames only after geometric verification; never merge disconnected components by visual plausibility alone.

For metric optimization, begin with robust covariance-weighted alignment and explicit degeneracy tests. For long sequences where drift matters, add GNSS position factors inside bundle adjustment or a factor graph, with robust losses and camera/GNSS frame transforms. Do not count an IMU-fused autopilot pose and its underlying GNSS samples as independent evidence.

Create dense observed geometry using multi-view stereo where the capture supports it. Keep a sparse measurement result if dense processing fails. For the textured mesh, retain only supported faces and source-image associations; avoid watertight completion across unobserved gaps. Texture projection is a visualization operation and does not add geometric evidence.

### 5.4 Bounded learned-model experiment

Allocate at most two engineer-days initially to **MapAnything's Apache checkpoint** as a coarse preview or initialization candidate. Its [official repository](https://github.com/facebookresearch/map-anything) distinguishes Apache and noncommercial model variants. Pin the exact checkpoint and code revision. Start with 8–16 reduced-resolution views, measure peak VRAM, and increase only within budget. Predicted metric scale remains a prior until externally supported.

Keep the candidate only if it improves registration, useful coverage or time to first useful result on held-out captures without unacceptable measurement regression. Otherwise ship classical reconstruction plus learned matching. The AI-enabled requirement can be met through verified learned correspondence/masking assistance; it does not require an all-neural reconstruction backbone.

Existing MASt3R adapters remain research options. Do not assume their checkpoints are deployable merely because they can be downloaded. In particular, [VGGT's published license update](https://github.com/facebookresearch/vggt) distinguishes checkpoints and excludes military applications from its commercial-use allowance. It is unsuitable as an unexamined default for this project's intended stakeholder. Maintain a license manifest for code, weights and datasets; review the exact deployment rights before field distribution.

Do not simultaneously integrate MASt3R-SLAM, MASt3R-Fusion, VGGT and MapAnything. Their papers are survey references; one bounded candidate is enough for the MVP.

### 5.5 Provenance is a set of independent attributes

Store three axes, rather than one overloaded confidence label:

- **Origin:** multi-view triangulation, multi-view stereo, learned proposal, manual input, interpolation.
- **Evidence state:** supported, weak, corroborated-only, dynamic, occluded, unseen.
- **Measurement status:** meets requirement, estimated only, needs refinement, not observable.

A learned matcher can produce genuine measured geometry when its image correspondences are geometrically verified and triangulated. A learned pointmap merely agreeing with another predicted pointmap remains prior-assisted. Corroboration does not erase origin or establish independence.

Reserve neighboring frames for corroboration before fitting an AI proposal. Those views still share calibration and potentially pose error: call them held-out image evidence, not independent surveyed truth. Promote to measured geometry only through actual image-supported reconstruction and the same uncertainty checks applied to classical output.

### 5.6 The uncertainty model

The present fixed-camera point covariance is a useful starting point but misses correlated pose, calibration and endpoint effects. For a distance `d = ||B - A||`, use the complete measurement Jacobian against the joint state covariance where feasible. The endpoint contribution includes the cross terms:

```text
u = (B - A) / ||B - A||
Var(d) ≈ uᵀ (ΣAA + ΣBB - ΣAB - ΣBA) u
```

Scale, calibration and other nuisance parameters belong in the same model, or are added once through explicitly separate terms. Do not double-count shared uncertainty. Global translation cancels from relative distance; it does not cancel from absolute coordinates. Vertical height additionally depends on gravity/orientation. Area needs its own propagation, units and surface/projection definition.

Implement an affordable approximation first: local optimization plus 10–20 targeted perturbation/refit trials for timing, intrinsics, correlated GNSS bias, view subsets and endpoint marking. Sample common-mode errors together, not independent noise for every point. Save seeds and perturbation bounds. Treat this as a model of sensitivity; it only becomes a calibrated interval through held-out evaluation.

Calibrate residual distributions on separate **missions/sites**, with separate profiles for camera/capture regime and metric source where sample size permits. Nearby points and adjacent frames are not independent calibration samples. Account for reference-survey uncertainty. Use finite-sample quantiles with the correct sample-size handling; tiny datasets cannot substantiate precise tail probabilities.

Report empirical interval coverage, interval width and sample counts on untouched test missions. Conformal calibration does not guarantee conditional coverage for every selected measurement or under domain shift. Test the complete selection/refinement policy, not just raw point errors. Disable the “calibrated” label outside supported regimes and until sample size is adequate.

### 5.7 Same-pass refinement algorithm

1. Back-project the selected endpoints or polygon into all candidate frames, preserving tentative visibility as distinct from verified support.
2. Reject cuts, severe blur, dynamic contamination, incompatible camera models and likely occlusion.
3. Rank candidates by useful baseline direction, image resolution, expected reduction in the queried measurement variance, and marginal processing cost.
4. Add a small batch, for example 4–8 frames. Recover image matches and locally refine with a connected boundary to the global model.
5. Retain global uncertainty at that boundary; fixing neighboring cameras must not make the interval artificially certain.
6. Recompute the number, its error model and eligibility. Stop on budget, lack of information gain, or reaching tolerance.
7. Keep corroboration frames outside the fit, or rotate to a new reserved set when old reserved frames enter refinement. Never report a used fitting frame as withheld evidence.

Initial ranking can use deterministic geometry heuristics; a learned ranking model requires logged outcomes and later training. Expected uncertainty reduction is a ranking proxy, not a guaranteed improvement. Report measured outcomes across the benchmark.

### 5.8 Spatial evidence and missing-data rules

Use a sparse voxel grid or tiled surface patches in a bounded region around the mission. Establish observed free space only along rays to **finite, supported** depths, stopping before the depth uncertainty margin. No return/no depth remains unknown. Unknown space stays unknown after meshing, downsampling, exporting and reopening.

Compute coverage on declared surface/query regions, with area weighting. Never report a fraction of bounding-box voxels as “percentage of building reconstructed.” Without a full reference surface, report observed support within the selected ROI; do not invent whole-object completeness.

### 5.9 Data contracts and APIs

Add schema-versioned records for `Mission`, `FrameObservation`, `SurfaceEvidence`, `MeasurementQuestion`, `MeasurementResult`, `CalibrationProfile`, `RefinementRun` and `ArtifactManifest`.

| Record | Required content |
|---|---|
| Mission | Source hashes, time mapping, camera/sensor models, CRS/datum, ENU transform, engine/weights/config versions |
| Frame observation | Frame ID/PTS, original-to-working pixel transform, feature/track IDs, camera pose, mask and quality flags |
| Measurement question | Geometry type, stable selected entities or source pixels, tolerance, coordinate/reference-plane definition |
| Result | Value/units, interval method/level, status/reason, scale source, supporting observations, calibration profile, artifact version |
| Passport | Result plus relevant image crops/original references, camera/calibration data, transforms, input/artifact hashes, verifier version |
| Refinement run | Parent/result versions, added frames, excluded frames, budget, actual runtime, before/after result, termination reason |

Suggested API additions: create/list measurement questions; retrieve measurement evidence; request bounded refinement; inspect spatial support; export/verify mission bundle. Backend gating is authoritative. The frontend must not bypass it by measuring arbitrary rendered vertices.

For interoperable exports, LAS uses a suitable metric projected CRS with explicit vertical metadata; GeoJSON uses longitude/latitude conventions with altitude meaning documented. GLB is local metric geometry with a georeference sidecar. Store full transforms and axes; test round trips in an independent GIS/viewer.

## 6. Datasets: what to obtain and why

### 6.1 Acquisition order

**Do not begin by collecting a huge training corpus.** The MVP uses pretrained components. Its critical data needs are reconstruction evaluation, calibration, measurement truth, and controlled failure cases. Download small matched image-and-truth subsets first, then collect the field data that public benchmarks cannot supply.

| Priority | Dataset and source | Exactly what is needed | Purpose and limits |
|---|---|---|---|
| P0 — already partly local | [Zurich Urban MAV](https://rpg.ifi.uzh.ch/zurichmavdataset.html) | Existing `AGZ_subset`; images, original timestamps, onboard GPS/IMU/barometer, calibration, `GroundTruthAGL.csv`; full route only if needed | Real aerial temporal imagery and telemetry. Select contiguous, non-revisiting segments. Reference camera positions were generated with Pix4D and loop closures; they are **not independent RTK/LiDAR survey truth** |
| P0 — obtain | [ETH3D training datasets](https://eth3d.ethz.ch/datasets) | Begin with `terrace_dslr_undistorted.7z`, `terrace_dslr_scan_eval.7z`, associated calibration and occlusion/evaluation metadata. Then a second outdoor scene such as `courtyard` or `delivery_area`, retaining matched scene names | Laser-referenced visible-surface geometry checks. Terrestrial photos, not a single-pass UAV-video validation. Do not feed supplied reference poses into a pose-estimation benchmark |
| P0 — collect | **Drishti Field Pack v1**, team-owned | Unedited 1080p/4K video + synchronized flight logs + camera information + independently measured checkpoints and dimensions; specification below | The indispensable evidence for the real product claim. Public scenes cannot replace this |
| P0 — generate | Repository synthetic scenes, extended | RGB frames, timestamps, exact camera poses/intrinsics, depth, mesh, visibility, dynamic masks; independently injected sensor/blur errors | Deterministic diagnosis of scale, occlusion, motion and refusal. Not evidence of field accuracy |
| P1 — small subset | [TartanAir](https://theairlab.org/tartanair-dataset/) | Two outdoor environments, e.g. `neighborhood` and `seasidetown`; left RGB, left depth, poses, calibration, segmentation when available | Stress tests and known visibility/geometry. Use only left RGB as monocular input; depth/poses remain evaluator truth. Any synthetic GNSS is labeled synthetic |
| P1 — mapping regression | [ODMdata](https://github.com/OpenDroneMap/ODMdata) | `aukerman` images with EXIF; optionally `helenenschacht` images and supplied GCP/RTK material; preserve per-set license/readme | Survey-photo regression and georeference adapters. These photo surveys do not prove single-pass performance or provide independent truth merely because GCPs exist |
| P2 — sensor integration | [EuRoC MAV](https://projects.asl.ethz.ch/datasets/euroc-mav/) | `MH_01_easy` and one harder sequence from the current ETH Research Collection link; camera, IMU, calibration and truth records | Timing, visual-inertial integration and trajectory tests. Use one camera for monocular evaluation; no claim of outdoor geographic survey validation |

Zurich's publisher lists an approximately **200 MB sample and 28 GB full archive**. The [ETH3D listing](https://eth3d.ethz.ch/datasets) lists terrace's undistorted imagery at about **0.3 GB** and its evaluation scan at about **0.1 GB**, excluding extra metadata packages. The [ODM catalog](https://github.com/OpenDroneMap/ODMdata) lists Aukerman at **543 MB** and Helenenschacht at **2553 MB**. These are publisher-listed approximate download sizes, not our processed storage requirements.

The ETH3D dataset page was searchable but direct retrieval was intermittent in this session. Its [official preparation repository](https://github.com/ETH3D/dataset-pipeline) is an alternate source for package instructions. Obtain image and truth packages from the same dataset release. If a named archive changes, use the current official scene manifest, not a similarly named unofficial copy.

**Storage planning assumption:** reserve 30–60 GB for the small public subsets plus extracted data/cache, and initially 50–150 GB for team captures and outputs. These are working allowances, not measured dataset sizes. A complete Zurich archive and repeated dense intermediates can require substantially more. Set a per-mission cache quota and retain raw data separately.

### 6.2 What is already in this checkout

`drishti3d/data/real_drone/AGZ_subset.zip`, an extracted `AGZ_subset/`, calibration and navigation logs are present. Additional prepared AGZ image folders and public drone footage also exist. Inventory file counts, sizes, decodability, timestamp ranges and hashes before reusing them; this planning session did not validate every binary.

The work log identifies public cinematic clips with scene cuts and absent telemetry. They are useful structural/visual stress tests after segmentation. They cannot support an independent geographic-accuracy claim. Existing historical reports that say real imagery is entirely absent are stale for this checkout.

### 6.3 Field Pack v1: the data only your team can supply

**Minimum acquisition to unblock engineering:** one accessible site, three unedited passes of 30–90 seconds, actual telemetry, camera metadata, and ten independently measured dimensions. This permits development and an illustrative demonstration, not broad calibration or survey certification.

**Target for the MVP evaluation:** three physically distinct sites with four passes each, **12 missions total**, and at least **20 predefined measurement questions per site**. Use site A for development, B for calibration/policy selection, and C as a locked demonstration of transfer. This remains a small pilot: publish uncertainty in the results and expand to more sites before claims of broad calibrated reliability.

Recommended sites:

- Site A: campus/service lane with textured buildings, openings and roof edges.
- Site B: a different infrastructure or construction site with partial occlusion and elevation variation.
- Site C: a held-out mixed scene containing roads, rigid structures, vegetation and difficult texture.

For each site acquire a normal oblique pass, a mostly nadir linear pass, a weak-parallax pass, and a repeat under a different capture condition or with controlled moving objects. All are scored separately. A separate rich multi-view reference capture may help interpret completeness, but must never enter the single-pass input and is not automatically survey truth.

| Required item | Collection specification |
|---|---|
| Original video | Unedited MP4/MOV, 1080p or 4K, original metadata, no social-media recompression; record resolution/FPS/exposure and stabilization/zoom state |
| Navigation | Raw GPS/flight logs plus SRT if available; native timestamps and documented clock relation to the video; preserve fix-quality and covariance fields |
| Camera | Make/model, active resolution/crop, focal settings, distortion calibration if available; calibration-board video or images where practical |
| Optional sensors | IMU, barometer, RTK/PPK records; antenna lever arm, camera/IMU extrinsics, gimbal orientation and calibration method |
| Geographic reference | Surveyed checkpoints with ID, coordinates, horizontal CRS, vertical datum, instrument method, uncertainty and marking photographs |
| Dimension reference | Widths/distances/heights measured independently with suitable tape, laser instrument or total station; endpoint photographs, repeated readings and uncertainty |
| Scene/visibility annotations | Mark measurement endpoints in 3–5 usable frames where visible; annotate hidden surfaces, dynamic objects and unsupported edges on a small representative frame subset |
| Mission log | Site/date, weather/lighting, intended capture regime, any cuts/dropouts, operator notes, permitted data uses and privacy treatment |

For a formal positional assessment, plan **at least 30 well-distributed independent checkpoints for each product being assessed**, with the applicable sampling and reference-accuracy requirements. Do not pool 30 points across unrelated sites and describe each site as formally assessed. Start with fewer for the engineering pilot and label that result clearly. [ASPRS's Edition 2 Version 2 announcement](https://old.asprs.org/archives/asprs-approves-edition-2-version-2-of-the-asprs-positional-accuracy-standards-for-digital-geospatial-data-2024.html) documents the change to 30 and the need to account for checkpoint accuracy.

A preferred benchmark arm uses zero GCPs in reconstruction and independent checkpoints only for scoring. A separate controlled arm uses optional RTK/PPK or a small, disclosed GCP set. This preserves the problem's limited-ground-control requirement while quantifying what extra reference information buys.

If no survey-grade positioning is available, acquire independent **length** references anyway. They validate dimensions but not global coordinate accuracy. Consumer phone GPS must not be relabeled centimetre-level ground truth. Record instrument uncertainty; aim for reference uncertainty materially smaller than the target tolerance, preferably at most one-third for the pilot.

### 6.4 Capture design

Use an ordinary permitted continuous pass with stable camera settings. Select a direction and viewing angle that can observe the intended question; an oblique view is useful for visible facades and roofs. Do not prescribe one universal altitude or speed: choose them from field of view, desired ground sampling distance, exposure, available baseline and site constraints.

For the first fixture, seek several sharp, spatially separated views of every reference endpoint. Nearby video frames are highly redundant; useful baseline must be checked over seconds, not only adjacent frames. Log focal/crop changes and rolling-shutter risk. Keep a deliberately difficult pass in the evaluation instead of discarding it.

For field collection, use a qualified operator and the site's current permissions/airspace process. This is a data specification, not flight authorization or an autonomous route. Use benign controlled objects for dynamic tests; do not stage activity on an open public road.

### 6.5 Training, tuning, calibration and testing separation

| Data split | Allowed use | Prohibited use |
|---|---|---|
| Development | Algorithm choices, failure analysis, threshold selection | Calling these results held out |
| Calibration | Fix interval multipliers/quantiles and acceptance policy, with a recorded version | Repeatedly choosing models against the locked test set |
| Locked test | One final evaluation of frozen models, policy and tolerances | Feeding truth into scale, BA, ICP alignment for absolute scoring, or hyperparameter selection |
| Expanded pilot | Assess transfer across cameras/sites/operators and update future releases | Silently updating deployed calibration while retaining old validation claims |

Split by **site/mission**, not random adjacent frames. Keep related passes from the same site in the same split for transfer claims. Public datasets may have appeared in pretrained-model training; record known overlap and treat new team captures as the stronger generalization test.

No custom foundation-model training is planned. Small supervised calibrators/rankers can follow once mission diversity supports them. Hundreds of thousands of points from one flight are not hundreds of thousands of independent field examples.

### 6.6 Folder layout and minimum file schemas

Place new data under the proposed `datasets/` folder at the repository root. These paths are a specification; this planning task does not move existing files or create empty data placeholders. Keep raw archives intact and list existing local AGZ paths in the manifest.

```text
datasets/
  README.md
  catalog.csv
  public/
    zurich_mav/                 # or catalog pointer to existing AGZ_subset
    eth3d/terrace/
    eth3d/courtyard/
    tartanair/neighborhood/
    odm/aukerman/
    euroc/MH_01_easy/            # optional
  field/
    site_a/pass_01/
      manifest.yaml
      raw/video.mp4
      raw/flight_log.*
      raw/telemetry.srt         # if available
      calibration/camera.json
      calibration/extrinsics.json
      annotations/questions.json
      annotations/image_marks.csv
      annotations/visibility.json
      license_and_permissions.txt
    site_b/...
    site_c/...
  truth/                       # evaluation-only; not mounted into worker
    site_a/checkpoints.csv
    site_a/reference_dimensions.csv
    site_a/reference_cloud.laz  # optional
    site_b/...
    site_c/...
  splits/
    development.json
    calibration.json
    test_locked.json
```

Truth and raw mission inputs must be access-separated during benchmarking. Controls intended for processing are a distinct input file; checkpoints stay in the evaluator folder. Folder names alone do not prevent leakage.

Proposed normalized telemetry columns, retaining the original logs:

```text
timestamp_ns,time_basis,latitude_deg,longitude_deg,altitude_m,altitude_reference,
sigma_e_m,sigma_n_m,sigma_u_m,fix_type
```

Proposed checkpoint columns:

```text
point_id,easting_m,northing_m,height_m,horizontal_crs,vertical_datum,
sigma_e_m,sigma_n_m,sigma_u_m,reference_method,role
```

Proposed dimension-reference columns:

```text
question_id,type,endpoint_a_id,endpoint_b_id,reference_value,unit,
reference_sigma,reference_method,notes
```

Area references use a polygon/vertex file and specify horizontal projected area versus actual surface area. A height requires a defined vertical direction and top/bottom references. Missing uncertainty is `unknown`, never zero.

Every `manifest.yaml` records dataset/site/mission identity, input hashes, original source, license, split, raw-to-video time mapping, coordinate conventions, camera model, sensor accuracy origin and any derivatives. Imported image sequences preserve original timestamps and are labeled as such; a synthetic MP4 assembled from unordered survey photos is not a genuine drone video.

### 6.7 Rights and access checklist

The [Zurich publisher](https://rpg.ifi.uzh.ch/zurichmavdataset.html) permits research/evaluation/commercial use; retain its citation and notices. [TartanAir](https://theairlab.org/tartanair-dataset/) states CC BY 4.0. [ETH3D](https://eth3d.ethz.ch/) states CC BY-NC-SA 4.0; keep it in the research evaluation track and review rights for redistribution/commercial use. ODM sets have individual provenance/licenses; do not apply a blanket repository license to every image. Record EuRoC's current deposit terms at download.

Access to a landing page is not verification that every archive currently downloads. Save the source URL, retrieval date, license text and checksum when the team obtains each dataset. Do not upload private field imagery to a competitor's cloud without the data owner's authorization; local baselines can cover the comparison.

## 7. Proving superiority with experiments

### 7.1 Primary outcome

Use **correct accepted answers per processing minute**, accompanied by answer coverage and false-acceptance rate. A method that refuses everything must not win. A method that answers everything incorrectly must not win either.

For a predefined set of questions with tolerances:

```text
answer coverage = accepted questions / all predefined questions
false acceptance = accepted answers outside tolerance / accepted answers
useful-answer rate = correct accepted answers / end-to-end processing minutes
```

Report these by site, capture regime, tolerance and metric source, including failures and unanswered questions. A zero denominator is “not estimable”, not 0% error. Also report time to first correct accepted answer and operator task time separately.

### 7.2 Baselines and fairness

| Baseline | Comparison purpose |
|---|---|
| B0: current repository engine/config, pinned | Quantifies improvement over the starting project |
| B1: plain COLMAP, conventional keyframe sampling and identical telemetry alignment | Isolates frame selection, evidence recovery and product gating |
| B2: OpenDroneMap on the same video-derived images and eligible metadata | End-to-end open mapping baseline |
| B3: one licensed commercial product if available | Operator workflow and result quality; clearly identify product/version/config |
| Ablations: remove targeted refinement, remove calibrated gate, remove sensor handling, remove learned matcher | Shows which proposed contributions actually help |

Run two comparison tracks. **Matched-input engine track:** identical frames, resolution, calibration, GNSS/control and compute hardware. **Whole-product track:** identical raw video and allowed metadata, equal wall-clock/compute budgets; each product can select frames normally. Never give Drishti3D extra control points or later-flight frames and call the comparison equal.

Separate native product capabilities from a shared evaluator applied to exported results. If a competitor does not expose per-measurement intervals, mark that field unavailable; do not invent an equivalent probability or assume all its measurements are unsafe. Compare actual measurement errors and task completion time, and compare our gating ablations on common geometry.

Use the best documented baseline settings within the agreed budget. Publish failed attempts, version/config manifests and actual outputs. Images may be downsampled consistently for controlled tests; retain an additional best-practical-settings track when appropriate.

### 7.3 MVP acceptance targets — to be measured, not advertised today

| Dimension | Proposed pilot target | Evidence required |
|---|---|---|
| Real single-pass processing | At least 3 locked clips from the held-out site produce supported results; difficult captures may abstain explicitly | Raw hashes, clips, telemetry, results and failure accounting |
| Practical dimensional accuracy | ≥90% of accepted, predefined 2–20 m rigid-feature lengths within `max(0.10 m, 2% of reference length)` | Independent dimensions; report absolute errors for short lengths and uncertainty in rates |
| Geographic accuracy | Predeclared reconnaissance target: RMSEH ≤2 m and RMSEV ≤3 m; controlled/RTK research target: ≤0.10 m / ≤0.15 m | Separate accuracy classes and independent checkpoints; ordinary GNSS may fail these targets |
| Interval calibration | 95% nominal intervals: report empirical coverage and confidence bounds, with interval width and mission count | Separate calibration/test missions; no certified claim from one held-out site |
| Acceptance safety and usefulness | Target false acceptance ≤5% while answering ≥60% of predefined supported-regime questions | Publish uncertainty bounds, denominator and failure-regime results; tiny samples cannot prove the rate |
| Same-pass improvement | ≥20% relative gain in correct accepted-answer yield at the same additional compute budget, or ≥20% lower time to the same yield | Paired tests against uniform refinement on fixed questions; report absolute gain too |
| Geometry | Report accuracy/completeness/F-score at 5, 10 and 20 cm where reference resolution permits | Visibility-aware reference masks; separate observed and inferred layers |
| First overview | Target ≤90 s for a 60 s 1080p clip | Fixed frame/resolution limits; cold/warm timings and machine specification |
| Verified question set | Target ≤5 min for the bounded demo mission | End-to-end timing including decode, refinement and export |
| Targeted refinement | Target ≤60 s per selected question | Additional compute cap, actual added frames and measured change |
| Resource use | ≤7 GB peak GPU allocation, ≤24 GB RAM for the reference preset | Measure process/device memory; preserve headroom on the observed 8 GB GPU |
| Integrity/offline behavior | All planned tampering fixtures detected; complete offline replay and evidence verification | Network-disabled rehearsal, immutable manifest and verifier output |

The dimensional tolerance is an engineering target for the selected pilot, not a universal survey specification. Geographic targets are separate because local dimensions can be useful while absolute GNSS placement is poor. If these targets fail, preserve the measured class/limitations; do not tune the headline after looking at test results.

Survey reporting uses RMSE and the applicable standard methodology. The app's 95% measurement intervals are a separate uncertainty interface: ASPRS Edition 2's removal of 95% confidence as its positional accuracy measure must not be confused with an endorsement of our interval model. See the [ASPRS announcement](https://old.asprs.org/archives/asprs-approves-edition-2-version-2-of-the-asprs-positional-accuracy-standards-for-digital-geospatial-data-2024.html).

### 7.4 Evaluation traps to prevent

1. **Absolute accuracy:** score directly in the declared geographic/project frame. No best-fit ICP or Sim(3) against test truth before reporting absolute error.
2. **Relative shape:** an aligned shape score is allowed in a separate table. Declare transformation degrees of freedom; a scale alignment removes the very scale error we need to measure.
3. **Trajectory:** distinguish position-error evaluation from gauge-aligned ATE. Zurich's reconstruction-derived path is a reference comparison, not independent survey certification.
4. **Completeness:** compare surface area against an appropriate visibility mask, not raw point count or cloud density. Unknown rear facades are reported separately from visible-surface reconstruction failures.
5. **Dense truth:** use the dataset's evaluation tooling/masks when available. Sparse nearest-neighbor truth can create an artificial error floor.
6. **Uncertainty:** report width as well as coverage; arbitrarily wide intervals should not win. Include boundary marking and operator repeatability, not only triangulation noise.
7. **Adaptive selection:** evaluate the full question-selection and refinement policy. Choosing only easy green points after observing results biases accuracy.
8. **Statistics:** summarize independent missions/sites. Do not generate narrow confidence intervals by treating correlated pixels or points as independent samples.

### 7.5 Required challenge suite

Include low parallax, near-hover, straight-line GNSS degeneracy, biased GNSS altitude, wrong time offset, variable frame rate, rolling shutter, repeated windows, featureless roof, vegetation, reflective water/glass, dynamic vehicle, hidden facade, wrong known scale, altered artifact and worker interruption.

Each challenge has an expected outcome: valid reconstruction within tolerance, an explicit weaker result, or refusal with the correct reason. A confidently wrong accepted number is a failure even if the 3D rendering is attractive.

## 8. Implementation sequence, effort and decision gates

### 8.1 Planning assumptions

Assume a team of **4–6 contributors**, one 8 GB NVIDIA GPU, sufficient local disk, and access to a permitted field site. These are planning assumptions, not facts about the team's availability. Assign ownership across geometry, backend/data, UI and field/evaluation. One person may cover several roles; the timeline then expands.

Target **four weeks for a convincing integrated prototype**, then **two to four additional weeks for a controlled field pilot**, contingent on data and reference-survey access. New calibration across multiple sites and formal acceptance must not be squeezed into a UI demo deadline.

### 8.2 Dependency-ordered backlog

| Stage | Indicative time | Build and owner | Exit gate |
|---|---|---|---|
| G0: freeze contract and truth | Days 1–2 | Evaluation/data owner: capture specification, site splits, question list, dataset inventory, baseline manifest | One real unedited clip with logs and independent dimensions is available; otherwise only public-data prototype claims are allowed |
| G1: reliable geometry | Days 3–6 | Geometry owner: compare existing SfM and COLMAP, calibration/timing, degeneracy checks, dense-supported ROI | Repeatable metric result on development data, explicit low-parallax failure, baseline report |
| G2: evidence foundation | Days 5–8, after G1 interfaces stabilize | Backend + geometry: persistent tracks, source pixels, artifact schema, supported-depth coverage, worker isolation | Every selectable measured entity resolves to real observations; missing depth remains unknown |
| G3: measurement and uncertainty | Days 8–12 | Geometry/evaluation: question types, correlated sensitivity, calibration profiles, acceptance policy | Numerical reproducibility and development/calibration split reports; provisional labels retained where calibration is insufficient |
| G4: product workflow | Days 10–14, using G2/G3 contracts | UI/backend: Tolerance Lens, Evidence Replay, state-specific explanations, exports | Operator completes question → evidence → report without shell access |
| G5: same-pass improvement | Days 13–17 | Geometry + evaluation: full-clip index, candidate ranking, local refit, budget control | Paired targeted-versus-uniform experiment completed, including negative cases |
| G6: demonstration release | Days 18–20 | All owners: locked test, one open baseline, offline packaging, GIS round trip, demo rehearsal | Measured scorecard, no unsupported headline, fresh and stored result clearly distinguished |
| G7: field-pilot hardening | Following 2–4 weeks | Field lead + engineering: more sites, reference survey, access control, backup/recovery, deployment licensing | Independent review against intended accuracy/use class; unresolved limits documented |

Approximate total engineering effort: **45–70 person-days** for prototype integration and evaluation, depending on how reusable the existing adapters are; field travel/survey availability adds calendar risk. These are estimates, not commitments. Data acquisition is on the critical path from day one.

### 8.3 Concrete code work packages

| Work package | Existing integration points | New or extended responsibility |
|---|---|---|
| WP1: source/evidence persistence | `sfm.py`, `colmap_adapter.py`, `fusion.py`, `exports.py` | Stable observation IDs and lineage through filtering/downsampling/meshing |
| WP2: metric-state contract | `geo.py`, `sensors.py`, `sync.py`, `quality.py` | Coordinate/time frames, degeneracy, reference accuracy and scale-source metadata |
| WP3: truthful visibility | `coverage.py`, `verify.py`, `masking.py` | Finite-depth evidence, uncertainty margins, no-depth unknowns, transient observations |
| WP4: question-level inference | `measure.py`, `uncertainty.py`, `trust.py` | Measurement type semantics, correlated sensitivity, calibrated eligibility and reason codes |
| WP5: refinement scheduler | `keyframes.py`, `features.py`, `bundle.py`, `pipeline.py` | Full-clip retrieval, query-aware candidate selection and bounded local reprocessing |
| WP6: product surface | Backend routers/storage/jobs; `Workspace.tsx`, viewer and API client | Measurement questions/results, Evidence Replay, Tolerance Lens and versioned job states |
| WP7: independent proof | `eval/`, `tests/`, benchmark docs | Site splits, independent reference evaluator, fair baselines, passport verifier and fault fixtures |

Expected new modules may be `evidence.py`, `questions.py`, `refinement.py` and `passport.py`; exact names are implementation choices. Keep dependency direction clear: the API invokes the geometry service, and rendering never determines measurement validity.

### 8.4 Stop/go rules

- If real reconstruction fails by G1, spend the next iteration on capture/calibration/registration and reduce scope. A polished viewer cannot compensate for missing geometry.
- If the learned candidate exceeds memory or fails to improve the frozen development benchmark, remove it from the critical path.
- If uncertainty cannot be calibrated with available missions, ship estimated ranges and independent measurement errors; keep formal acceptance disabled.
- If same-pass refinement does not beat uniform processing, retain it as an experimental feature and demonstrate only its observed benefits. Do not claim the main hypothesis succeeded.
- If no independent reference data arrives, the deliverable is an evidence-aware reconstruction prototype, not a survey-validated product.
- If dense meshing exceeds budget, ship a colored supported cloud and selected textured patches. This still fits the point-cloud-or-mesh output requirement.

### 8.5 Short-deadline cut

If the build window is only 7–10 days, ship reconstruction, three geometric question types, source-frame evidence, basic tolerance states, unknown regions and offline exports. Show targeted same-pass refinement on one reproducible case as experimental. Use existing engines and the local AGZ subset; collect one reference-bearing field clip immediately. Defer new backbone integration, autonomous recapture, splatting and full uncertainty certification.

The reduced build must still disclose how many real examples were validated. A precomputed genuine result is acceptable for a presentation when labeled; a simulated processing animation is not evidence of fresh processing speed.

## 9. Drawbacks, mitigations and residual limits

| Risk / drawback | What to build or test | Residual limit / fallback |
|---|---|---|
| Little or no parallax | Baseline-direction diagnostics; retrieve wider-separated frames; test conditioning | If the pass contains no useful baseline, depth cannot become measured through more compute |
| Hidden surfaces | Unknown-space map; source visibility records; prevent hole-filling from becoming evidence | True hidden geometry requires a new observation or another sensor |
| GNSS bias and weak geographic orientation | Covariance-aware factors, robust residuals, degeneracy checks, optional trusted gravity/control | Smoothing does not remove common GNSS bias; downgrade absolute accuracy |
| Inaccurate or missing timing | PTS mapping, offset observability checks, sensitivity trials | Ambiguous timing limits telemetry fusion; preserve visual-only/relative fallback |
| Rolling shutter, gimbal motion or electronic stabilization | Camera-model checks, readout metadata where available, motion screening | Strong unmodeled distortion may require rejection or a more advanced optimizer |
| Blur, compression and illumination change | Quality-aware selection, photometric normalization for matching, original pixels retained | Do not measure generatively sharpened detail as if it were an observation |
| Repeated windows / textureless roofs | Cycle checks, wider context, verified learned matches and redundant views | Reject plausible but ambiguous correspondences; learned appearance is not proof |
| Water, glass, reflective roofs | Identify unstable depth/appearance, mask or label weak | Transparent/reflective geometry may need LiDAR/manual survey |
| Vegetation and thin obstacles | Separate vegetation, conservative support rules, explicit resolution limits | Ground under canopy and thin wires may remain unobserved; no obstacle-free guarantee |
| Moving vehicles/people | Motion plus semantics, temporal masks, saved transient observations | Masks can remove useful texture or hide ground; excluded does not mean absent |
| Learned hallucinations | Preserve origin; geometric verification; measure only accepted observational geometry | Agreement between correlated models does not establish truth |
| Misleading confidence | Mission-level calibration, coverage/width reporting, distribution checks | Small data or a new camera invalidates calibrated labels until revalidated |
| Overly conservative refusal | Optimize useful-answer yield at bounded false acceptance; show a specific next action | Do not lower uncertainty thresholds merely to make more cards green |
| Selected-point / area ambiguity | Source-image marking, repeated operator trials, explicit horizontal/surface area definitions | Endpoint selection can dominate error even with an accurate cloud |
| Unsupported free space | Require finite verified depths; maintain unknown cells | Sparse reconstruction cannot establish a fully traversable 3D volume |
| Mesh bridges and smoothing | Support masks on faces; measurement against underlying evidence; original model retained | Rendered watertightness does not imply observed geometry |
| RAM/VRAM and thermal limits | Bounded frames, tiled ROIs, one GPU job, resolution presets, cold/warm timings | CPU fallback is slower and may yield only sparse output |
| Large missions / accumulated drift | Overlapping processing windows, connected global refinement, checkpointed artifacts | Multi-kilometre production performance is outside the initial bounded mission |
| Power loss / worker failure | Durable state, atomic artifact writes, resume and cancellation, disk quotas | Re-run only incomplete stages; do not expose partial files as final |
| Bad uploads / hostile media | Decoder process isolation, resource limits, path validation, no untrusted archive extraction into app paths | Pilot hardening is required before multiuser exposure |
| Offline deployment | Bundle tested wheels/binaries/weights, license notices, offline assets and recovery guide | Hardware/driver changes need a new compatibility test |
| Sensitive scene data | Local processing, access-controlled storage, optional redacted exports, retention/backup policy | Raw imagery remains sensitive; hashes do not anonymize it |
| False authenticity claims | Hash-linked artifacts and optional locally signed manifests | Hashes prove consistency with a recorded manifest, not truth of the original scene or trusted capture time |
| License restrictions | Pin code/weight/data licenses separately; deploy an eligible engine path | Research permission does not automatically cover government/industrial deployment |
| Tiny or leaked benchmarks | Site-held-out tests, truth isolated from worker, fixed questions and transparent failures | A small pilot establishes feasibility, not domain-wide superiority |

### Optional P1: missing-evidence acquisition guidance

Only after the six core features work, rank a small set of candidate additional views for a rejected question using expected ray geometry, surface visibility, uncertainty reduction and operator-supplied capture constraints. Show a preferred viewing region and the assumptions, not a certified safe trajectory. The operator remains responsible for airspace, collision avoidance and feasibility.

Test on a controlled site with a reserved additional-view pool. Compare selected view versus an equal-budget random or conventional view, then assess both predicted interval reduction and actual measurement error. Once extra images enter the result, label it **augmented capture** and keep it outside the original single-pass benchmark.

This fallback is useful precisely because some information is missing permanently from one pass. It must not become a hidden requirement for completing the main demo.

## 10. Stakeholder survey and pilot validation

### 10.1 Questions the research should answer

1. Does a per-measurement tolerance state help operators choose suitable outputs faster than a conventional model and quality report?
2. Does same-pass targeted refinement recover more correct answers for the same compute budget?
3. Does image-linked evidence reduce incorrect acceptance without making the workflow unusably slow?
4. Which missing input most often prevents useful results: camera metadata, synchronization, capture geometry, or metric reference?

These are the research questions to defend in a literature survey and evaluate in the pilot. They do not require claiming a new foundational SfM algorithm.

### 10.2 Interview protocol ready to use

Recruit approximately **8–12 participants** across drone operators, survey/GIS practitioners, infrastructure assessors and field-response personnel. This is a qualitative discovery sample, not a representative market survey. Record role, experience and consent; do not request sensitive operational details.

Ask neutral questions before showing the proposed product:

1. Describe the most recent job where drone-derived dimensions were needed quickly.
2. Which specific dimensions or coordinates mattered, and what error was acceptable?
3. What data and hardware were available on site? Was internet access reliable?
4. How did you decide whether a model or measurement could be trusted?
5. What happens when the capture is incomplete or inaccurate? What does a return visit cost in time?
6. Which outputs must integrate with your existing GIS/CAD/reporting workflow?
7. Who reviews or signs off a measurement before it is used?
8. What reference instruments or checkpoints can realistically be collected?

Then show the prototype and ask the participant to measure a visible width, inspect its evidence, evaluate a hidden facade, and request tighter tolerance on a borderline measurement. Ask what they believe each status means, what they would do next, and what information is still missing. Do not ask “Would you like our unique AI feature?”

### 10.3 Comparative usability test

Use matched tasks with a conventional model/quality report and Drishti3D. Counterbalance tool order and use equivalent questions to reduce learning effects. Measure time to a correct result, incorrect acceptance, correct recognition of unknowns, evidence-finding time and task completion. Ask a short usefulness/clarity rating and record explanations.

Initial adoption targets: at least 80% of participants correctly distinguish measured, inferred and unknown examples; median evidence-finding time below 30 seconds; and a material reduction in time to a correctly qualified answer against the chosen baseline. These are test targets. Publish sample size and failures, not just selected favorable quotations.

### 10.4 Real deployment pilot

Pilot with one campus/facility, local mapping firm or infrastructure team on a benign, permitted site. Start with dimension documentation and GIS handoff. Record time from capture to accepted report, operator corrections, reprocessing count, unsupported questions, baseline discrepancy and support burden.

Deliver a versioned installer/container, capability probe, known-limits sheet, data retention/backup instructions, coordinate/export guide and operator checklist. Add authentication/roles before shared-network use; single-user local operation does not justify exposing an unauthenticated service to a team network.

Measure cost per mission as machine time, operator time, reference-survey effort and failure/revisit effort. Avoid an invented selling price or market-size claim before interviews. The most plausible first deployment is a local workstation used alongside existing survey software, with open-format exports.

## 11. The demonstration that makes the advantage visible

Use one real 45–90 second pass over the chosen corridor. Freeze five questions beforehand: a supported width, a height, an area, a weak-but-recoverable measurement, and a never-visible surface. Keep the reference measurements with the evaluator until the model and answers are frozen.

| Time | What the judge sees | What it establishes |
|---|---|---|
| 0:00–0:30 | Original continuous clip, flight path, input identity and telemetry availability | It is an actual one-pass input |
| 0:30–1:15 | Genuine model; point cloud and supported texture; capture limits | Required reconstruction output exists |
| 1:15–2:00 | Select a width; compare it with an independent reference | A useful, testable metric result |
| 2:00–2:45 | Tighten Tolerance Lens from ±50 cm to ±10 cm | Suitability depends on the required precision |
| 2:45–3:30 | Click the result; source pixels and view rays appear | A direct explanation of the number |
| 3:30–4:30 | Improve a frozen weak question using unused frames from this same clip | The proposed contribution has a visible before/after result |
| 4:30–5:00 | Select the never-visible surface; show the specific missing evidence | Failure handling is part of the product |
| 5:00–6:00 | Same-input benchmark panel, offline evidence export and verifier | Advantage is backed by comparable results and a usable deliverable |

Prepare one fresh short processing run and one larger stored result, explicitly labeled with processing date, input hash and measured runtime. Do not imply the full pipeline ran during a presentation if it did not.

The benchmark panel contains actual accuracy, answer coverage, false acceptance, time and memory. Include a case where a baseline is equal or better. Present the demonstrated advantage narrowly: for example, “More correctly qualified dimensions under the same processing budget on these held-out passes,” only if the numbers support it.

If targeted refinement fails on the selected question, show the unchanged/shifted answer and explanation. Rehearsal should select a representative reproducible example from development data; final comparative results still come from the locked test set.

## 12. Final deliverables and implementation handoff

The completed MVP should ship these artifacts:

1. An offline application implementing the six essential features and visible status/version semantics.
2. A supported geometry package with explicit coordinate systems, point/surface provenance and unknown regions.
3. Measurement passports and a backend-independent verifier.
4. A reproducible benchmark bundle: input manifests, configurations, environment/weights hashes, splits, raw metrics, baseline artifacts and failure records.
5. A field-data catalog and capture/reference protocol, with permissions and licenses recorded.
6. A concise operator guide, installation/recovery instructions and known operational limits.
7. A survey/pilot report containing the literature comparison, experimental hypotheses, actual results and stakeholder findings.

**First implementation actions, in order:** inventory existing AGZ and real footage; obtain the ETH3D matched imagery/scan subset; arrange the first reference-bearing field capture; freeze measurement questions and evaluation rules; run the existing engine and COLMAP baseline; then build persistent observation evidence and the Tolerance Lens. Same-pass refinement follows a reliable metric baseline.

**Dataset request to the team:** start with the matched ETH3D terrace package and one original drone clip with real telemetry and independent dimensions. Reuse the local Zurich subset. Obtain broader public datasets only as their corresponding experiment becomes necessary. Independent field measurements are the highest-value missing input.

**Product positioning for the proposal:**

> Drishti3D turns one drone pass into a measurable 3D scene whose answers can be inspected, qualified to a requested tolerance, and improved using overlooked evidence from that same pass.

### Source and evidence notes

External sources are linked beside the claims they support throughout this document. Documentation was reviewed on 19 September 2026; linked software and dataset pages may change. Public product claims were not independently benchmarked in this planning task. Dataset landing pages were checked, but no new archives were downloaded. No new reconstruction or application test suite was executed for this documentation-only task.

Local context consulted includes the original [problem brief](SIH26158_Drishti3D_research_and_claude_prompt.md), [project draft](DRISHTI3D_PROJECT_DRAFT.md), [master research](codex_research/DRISHTI3D_MASTER_RESEARCH_AND_ARCHITECTURE.md), [Intelligence Edition tracker](drishti3d/docs/INTELLIGENCE_EDITION_PLAN.md), [distinctive ideas](drishti3d/docs/UNCOMMON_AND_DISTINCTIVE_IDEAS.md), [repository/market report](drishti3d/docs/DRISHTI3D_COMPREHENSIVE_PROJECT_AND_MARKET_REPORT.md), source modules and historical benchmarks. Older status and hardware statements were treated as historical; inspection findings and future targets are labeled separately above.
