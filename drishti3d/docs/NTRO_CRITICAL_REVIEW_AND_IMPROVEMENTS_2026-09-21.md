# Drishti3D: critical evaluator review and improvement plan

**Reviewed:** 21 September 2026 · **Checkout:** `d94ec29`  
**Perspective:** a demanding technical evaluator assessing whether this solves the stated single-pass UAV reconstruction problem. This is a simulated evaluator's assessment, not NTRO feedback or an official judging rubric.

**Verdict:** Drishti3D has become a substantial reconstruction and evidence prototype. It still has gaps serious enough that I would withhold a recommendation for operational use. The immediate priority is to make its measurements, evidence records, exports, and ordinary operator workflow agree. Adding more AI models before resolving those gaps would weaken the entry's focus.

The strongest possible pitch is: **“From one pass, obtain useful 3D geometry, answer a specific dimensional question, show the images supporting the answer, and explain exactly where the evidence runs out.”** The repository contains much of that system. It does not yet demonstrate that promise consistently from upload to exported result.

## 1. What this review actually examined

I read the current overview and backlog, recent dense-MVS and refinement results, reconstruction and uncertainty code, API routes, frontend workflows, exports, job handling, and deployment files. I built the frontend, ran focused tests, and exercised small numerical and file-level reproductions. Verification results and limitations are recorded at the end.

The requirement baseline is the repository's [problem-statement transcription](PROBLEM_STATEMENT.md): single-pass UAV video plus GPS/flight metadata into georeferenced, metrically accurate 3D, including point clouds and textured meshes useful for measurement and analysis. An official-site search did not establish a public SIH26158 page during this review. Any additional expectations below are my proposed evaluation criteria, not invented official requirements.

Finding labels:

- **Reproduced:** exercised in this review with a small local check.
- **Code-confirmed:** directly visible in the current implementation; the full user scenario was not rerun.
- **Recorded evidence:** reported by existing benchmark artifacts; not a fresh reconstruction in this review.
- **Proposed:** a feature or evaluation improvement, not an allegation that existing code is broken.

## 2. Give the updated project credit where it has earned it

These are implemented assets to build on, not missing features to propose again:

| Capability | What is now present | Remaining qualification |
|---|---|---|
| Dense observed geometry | COLMAP PatchMatch stereo and fusion; recorded output about 252k points, versus about 17.9k sparse | One mission; dense surface accuracy and uncertainty remain unvalidated |
| Two reconstruction engines | OpenCV and COLMAP with a measured comparison | Ordinary web processing still defaults to OpenCV and does not expose engine selection |
| Observation lineage | Sparse image observations and dense contributing-image records survive into artifacts | Dense attribution uses approximations that must be distinguished from original measured pixels |
| Tolerance Lens | Questions, intervals, refusal reasons, tolerance changes, evidence listing, refinement button and before/after display | Older measurement flow remains alongside it; evidence replay and portable measurement exports are incomplete |
| Same-pass refinement | Recover unused frames, pose them, refit locally, retain run records | Generalisation, corroboration, per-endpoint evidence accounting, and API persistence need work |
| Coverage reasoning | Observed/weak/occluded/unseen/empty volume, with a positive free-space rule | The main viewer does not show the coverage field |
| Sensor handling | Timestamp work, distortion correction, lever-arm support, rolling-shutter detection and guarded alignment | Several controls are inaccessible through the normal web workflow; detection is not rolling-shutter correction |
| Honesty mechanisms | AI geometry separation, missing-calibration refusal, warning/report infrastructure | Some routes, exports and wording do not preserve the same guarantees |

The September 21 benchmark reports 59/60 sampled dense measurements blocked only by calibration, compared with 40/60 sparse. That is promising **internal gate behaviour**, not 59 measurements independently demonstrated to be accurate. Keep that distinction prominent. [Dense benchmark](benchmarks/2026-09-21_dense_mvs/RESULTS.md)

The targeted-refinement advantage was measured on three test beds derived from one flight. Those are useful experiments, but they are not three independent demonstrations of generalisation. [Refinement results](benchmarks/2026-09-20_f4_second_capture/RESULTS.md)

## 3. The challenges I would put to the team

1. **“Give me a new continuous video. Can your actual upload interface reproduce the quality shown in your prepared project?”** Right now it cannot select the best demonstrated dense path or pass the full calibration used by the benchmark script.
2. **“You say accurate. Accurate relative to what?”** Camera-trajectory agreement, point spacing, reprojection residual, dimensional error and absolute map position are different quantities.
3. **“Show one real dimension with independent truth, its uncertainty, and the original supporting images.”** Existing evidence does not yet close that entire chain on a field measurement.
4. **“What happens on a white wall, a moving tree, a road with repeated markings, or a surface behind a building?”** A good answer needs a visible failure boundary, not just a warning buried in JSON.
5. **“Can I take your result into GIS and have it land in the correct place?”** Current LAS output is a concrete weakness.
6. **“Why should I use this instead of a standard reconstruction package?”** The answer must be demonstrated improvement in evidence-backed measurement and operator decisions; dense reconstruction alone is established functionality.
7. **“Can another analyst verify your measurement tomorrow after a rerun?”** Current cache, revision and refinement-record issues make this harder than the design promises.
8. **“How long does useful output take on the machine you are actually carrying?”** The recorded dense run took 1,231 seconds for a 184.4-second sequence: about 20.5 minutes, or 6.7 times capture duration. This is a legitimate offline workflow, but it is not real-time dense reconstruction.

## 4. P0: correctness and credibility fixes

**P0 means fix before presenting the affected behaviour as trustworthy.** It does not mean every item needs to block a clearly labelled prototype demonstration.

### C01 — Make the default measurement path obey the same trust contract

**Code-confirmed.** `Workspace.tsx` presents both “Finish,” calling the older `/measurements` route, and “Ask this as a question,” calling the newer question route. The older route computes a measurement without supplying scale uncertainty and persists a reduced response without sigma, tolerance verdict, calibration basis or artifact identity. It also does not check whether metric scale exists.

An operator can therefore obtain a plain number labelled in metres through a route that does not enforce the newer question gate. This does not mean the question gate itself is accepting invalid measurements; it means the product has two incompatible definitions of what a reported measurement means.

**Improve:** route normal measurement creation through one result service. If a quick exploratory ruler is retained, label its units and unvalidated status explicitly and keep it out of accepted-result exports. Make scale status, uncertainty basis and artifact revision unavoidable in saved results.

**Done when:** video-only, poor-scale and uncalibrated cases have consistent treatment through every UI/API entry point; no route emits an unqualified metric result for arbitrary-scale geometry.

**Evidence:** [legacy measurement route](../backend/app/routers/measurements.py), function `create_measurement` at line 47; [workspace](../frontend/src/views/Workspace.tsx); [question route](../backend/app/routers/questions.py), `_answer`.

### C02 — Fix shared scale uncertainty for polylines

**Reproduced.** With zero endpoint noise and 10% scale uncertainty, a 10 m two-point line returns sigma **1.000 m**. Add a midpoint without changing the physical line and the result becomes **0.707 m**. The code applies scale uncertainty independently to each segment and adds segment variances.

A common scale error affects the whole line together. Inserting vertices must not manufacture confidence. Shared endpoint covariance also deserves explicit treatment rather than treating adjacent segments as independent.

**Improve:** propagate the complete polyline function, accounting for shared vertices and applying the common scale term to total length. Apply the same fix to refinement's `measurement_value_fn`.

**Done when:** subdividing a straight line leaves its scale-only uncertainty unchanged; Monte Carlo perturbations of one shared scale reproduce predicted uncertainty for straight and bent polylines.

**Evidence:** [measure.py](../reconstruction/drishti_recon/measure.py), `measure_distance` at line 118; [refinement.py](../reconstruction/drishti_recon/refinement.py), `measurement_value_fn`.

### C03 — Refuse remote snapping and preserve what the operator selected

**Reproduced.** A selection at `[1000, 0, 0]` on a cloud ending at `[10, 0, 0]` snaps **990 m** to that cloud point without a distance-based refusal. `_snap` computes the nearest distance and never uses it to reject the selection. The question path then evaluates evidence at the snapped location.

Normal point picking limits how often this happens, but hidden inferred layers, stale selections, API clients and nearby surfaces still make unrestricted snapping a correctness problem.

**Improve:** retain original and resolved selections, expose snap displacement, use an explicit measurable-provenance allowlist, and impose a local spacing/selection-tolerance bound. For precision work, select an edge, plane or fitted surface patch instead of assuming the nearest point is the intended physical feature.

**Done when:** empty-space and hidden-surface selections return a clear refusal; a foreground roof cannot silently substitute for a selected background wall; the result shows the resolved endpoint.

**Evidence:** [measure.py](../reconstruction/drishti_recon/measure.py), `_snap` at line 61; [question route](../backend/app/routers/questions.py), `_answer`.

### C04 — Treat dense uncertainty as an incomplete model, not a finished calibration input

**Code-confirmed.** `mvs.depth_uncertainty` uses nearest-camera range, focal length, a capped view count and a global sparse-sigma floor. It does not use the contributing cameras' triangulation baseline or ray angles. The stereo term is proportional to `range × pixel_sigma / focal`, which is a transverse ray-localisation scale; depth sensitivity must respond to triangulation geometry.

Consequently, many views with almost identical ray directions are not distinguished adequately from a useful baseline. A floor derived from the median sparse point is a heuristic, not a rigorous bound on each dense point. The benchmark's statement that a dense point necessarily cannot beat the sparse median is too strong: sparse-point uncertainty is not camera-pose covariance.

**Improve:** use contributing-view geometry, disparity/depth consistency, camera uncertainty and per-point anisotropy; record the estimation method per point. Calibrate dense, sparse and refined measurement regimes separately where their error behaviour differs. Keep an explicit unsupported-regime refusal.

**Done when:** a controlled baseline reduction widens depth uncertainty; difficult texture/depth discontinuities increase uncertainty or trigger rejection; independent dense-endpoint errors are covered at the claimed rate on untouched missions.

**Evidence:** [mvs.py](../reconstruction/drishti_recon/mvs.py), `depth_uncertainty` at line 131; [dense benchmark](benchmarks/2026-09-21_dense_mvs/RESULTS.md).

### C05 — Describe dense lineage precisely and stop equating projected pixels with original observations

**Code-confirmed.** `_dense_observations` assigns each surviving cloud point the visibility list of its nearest dense input within one voxel diagonal, then projects the surviving point into those cameras to create `uv`. These are contributing-image records plus derived pixel locations. They are not preserved original stereo pixel correspondences.

At the current 0.15 m voxel, the association threshold is approximately **0.260 m**. Proximity alone does not establish that points are on the same surface near thin structures, roof edges or adjacent foreground/background surfaces. The function also queries all cloud points, so sparse survivors may inherit nearby dense support.

**Improve:** store exact fusion contributors or representative identities; distinguish `sparse_feature_observation`, `dense_fusion_contributor`, and `projected_display_pixel`. Record coordinate space, rescaling and undistortion transforms. If approximate attribution remains, preserve its displacement and apply surface/normal/depth-consistency checks.

**Done when:** original feature pixels and projected dense markers are labelled differently; two nearby surfaces cannot donate support to each other; held-out depth/image checks provide independent evidence. “99.9% project inside the image” remains a useful indexing check, not an accuracy validation.

**Evidence:** [pipeline.py](../reconstruction/drishti_recon/pipeline.py), `_dense_observations` at line 895; [evidence response](../backend/app/routers/questions.py), `question_evidence` at line 295.

### C06 — Make refinement's saved result and supporting evidence agree

**Code-confirmed; not reproduced through a fresh full refinement run in this review.** There are several connected issues:

- The engine stores moved endpoints in `run.refined_points_enu`, but the API persists its original `pts` in the new `Measurement`. A changed value can therefore be saved alongside endpoints that do not reproduce it.
- The API copies `threshold_result` from the previous measurement even when value or interval changes.
- The evidence endpoint reconstructs its listing from the original on-disk lineage. Recovered observations are recorded in refinement detail but are not merged into that normal evidence response.
- The engine adds `added_rays` to the measurement-wide minimum view count. If both endpoints had three views and only one gains four, the minimum should remain three, not become seven. The analogous aggregate parallax update can also hide the weaker endpoint.
- The frontend caches its evidence response and does not clear it after refinement.

**Improve:** persist refined endpoints, their own uncertainty, per-endpoint observations and provenance, and the newly computed threshold verdict as one versioned result. Recompute worst-endpoint support after updating only the affected endpoint. Replay evidence for the selected result revision and reload it after refinement.

**Done when:** recomputing from stored endpoints reproduces the displayed value; the threshold changes when the new interval crosses it; unchanged weak endpoints continue to limit acceptance; evidence before/after names the actual new frames. Repeat refinement and page reload must preserve the same chain.

**Evidence:** [question route](../backend/app/routers/questions.py), `refine_question` at line 355, especially lines 432 and 442; [refinement engine](../reconstruction/drishti_recon/refinement.py), around line 1492; [Tolerance Lens](../frontend/src/ToleranceLens.tsx).

### C07 — Version artifacts and invalidate cached geometry on every reconstruction change

**Reproduced at loader level; missing lifecycle wiring confirmed in code.** Replacing `cloud.npz` after calling `load_cloud(project_id)` still returns the cached old points. An `invalidate` helper exists, but the normal job-completion and upload paths do not call it. Question evidence is also cached by project ID.

The new manifest timestamp can identify a new artifact revision while measurement code still holds old geometry in memory. Changing an input also leaves previous outputs looking current. A failed rerun can leave old optional exports beside new files.

**Improve:** use immutable reconstruction-run directories and a run ID/content digest; key caches by run identity; atomically publish the completed run; mark results as belonging to an older revision. Preserve earlier runs as history instead of mixing files in one artifact directory.

**Done when:** upload → reconstruct → measure → replace input → reconstruct → measure, without restarting the API, uses the correct geometry and lineage; failed reruns do not publish mixed artifacts; question lists identify superseded results.

**Evidence:** [cloud cache](../backend/app/routers/measurements.py), `load_cloud` at line 21; [evidence cache](../backend/app/routers/questions.py); [jobs.py](../backend/app/jobs.py).

### C08 — Repair geographic and uncertainty information in exports

**Reproduced.** `export_las(..., frame=...)` writes local point coordinates but does not use `frame` or set a CRS. Reading the generated file gives `header.parse_crs() == None`. It also has no extra dimensions for provenance or uncertainty. PLY contains confidence/provenance but omits sigma; GLB carries vertex colours without the measurement evidence contract.

**Improve:** provide a declared projected or geocentric export with CRS metadata and a documented vertical reference, plus a local-coordinate export with an explicit transform sidecar. Preserve provenance, uncertainty method and units in suitable extra fields or a linked manifest. Make the complete package downloadable through the API.

**Done when:** another analyst imports the exported artifact into GIS without guessing the origin; known coordinates survive a round trip; uncertainty and provenance remain recoverable. The overview must stop saying exported point clouds carry sigma until each advertised format actually does.

**Evidence:** [exports.py](../reconstruction/drishti_recon/exports.py), `export_las` at line 36 and `export_ply` at line 16; [artifact download allowlist](../backend/app/routers/artifacts.py).

### C09 — Report absolute position error without fitting away the error

**Reproduced.** `_rigid_and_similarity_error` labels a centred comparison `as_georeferenced`: it subtracts each trajectory's mean. A reference trajectory shifted by `[100, 200, 30]` m scores **zero error** under that label.

The estimates and references have already been transformed into UTM in `score()`. If their coordinate and height references are genuinely comparable, an offset is part of absolute error. If height references are unresolved, disclose that and report eligible components separately; do not silently remove the offset and call the result absolute accuracy.

**Improve:** report raw common-CRS absolute residuals, translation-aligned residuals, and Sim(3)-aligned shape residuals as three separate metrics. Include the removed translation, fitted scale and reference uncertainty. Correct related benchmark prose.

**Done when:** a deliberate global offset is visible in the absolute metric; existing relative/shape regression metrics remain available under accurate labels. Do not reuse the recorded 3.764 m centred result as absolute positioning accuracy.

**Evidence:** [run_mission.py](../scripts/run_mission.py), `_rigid_and_similarity_error` at line 53; [engine comparison](benchmarks/2026-09-19_agz_single_pass_engines/RESULTS.md).

### C10 — Make calibration a validated release artifact, not a sample-count switch

**Code-confirmed and recorded evidence.** The production question route intentionally passes `profile=None`. That is appropriate today. However, `CalibrationProfile.from_calibration` marks a profile validated based on sample count, and its regime matching is delegated to callers. A future integration must not equate reaching 20 samples with independent validation.

**Improve:** separate fitting, held-out evaluation and release approval states in the profile data model. Match camera/lens/calibration, capture pattern, scale source, reconstruction settings, sparse/dense/refined path, and supported measurement type. Store split IDs, hashes, sample/mission counts, coverage, interval widths and reference-instrument uncertainty. Reject unsupported interval levels instead of silently substituting a 95%-style factor.

**Done when:** calibration and locked evaluation missions are disjoint; coverage and useful answer rate are reported with sample uncertainty; a profile refuses an unsupported camera/regime; the UI can explain why a particular profile applies.

**Evidence:** [questions.py](../reconstruction/drishti_recon/questions.py), `CalibrationProfile` at line 153; [current backlog](../../NEXT_STEPS.md).

**Evaluator objection:** “59/60 blocked only by calibration” does not imply 59/60 will pass after calibration. Fitted intervals may widen and expose additional tolerance failures.

## 5. P1: close the ordinary operator workflow

These changes make the implemented work usable and demonstrable. They should be delivered after, or alongside, the affected correctness fixes.

| ID | Improvement and present gap | Acceptance demonstration | Effort/dependency |
|---|---|---|---|
| U01 | **Expose the best reconstruction path.** Wizard offers `none`/`depth` densification, not MVS, and sends no engine. Add capability-aware sparse preview and dense observed options, with engine/settings recorded. | A new upload can produce the demonstrated COLMAP+MVS output without a private script; unavailable GPU capability gives a specific explanation. | Small–medium; installed engine required |
| U02 | **Carry camera calibration end to end.** API `Intrinsics` accepts only fx/fy/cx/cy; a request containing distortion loses that field. Add calibration-file import, camera model, source resolution and distortion; explain image resize/crop transformations. | Upload the benchmark calibration through the UI and verify the worker receives the same values as the mission script. | Medium; numerical field-drop reproduced |
| U03 | **Evidence Replay.** Replace frame-number badges with actual source frames, crosshairs, timestamps and endpoint markers. Account for distortion and processing resolution before placing a marker on raw imagery. | Select a dimension and inspect two contributing views, then jump to the source-video time. Dense projected markers are labelled accurately. | Medium; depends on C05/C06 |
| U04 | **Unknown-space overlay.** Render coverage separately from point colours. Distinguish unseen, occluded, weak, dynamic and positively verified empty cells. Add a legend and clipping. | A hidden wall remains visibly unknown; an empty-looking hole is never presented as confirmed free space. | Medium; backend coverage already exists |
| U05 | **Measurement passport.** Export the selected result revision, endpoints, units, interval basis, calibration ID, source-image references, hashes, transforms and refinement history. Provide an offline verifier. | A second machine recomputes the value and detects an altered evidence file without the running API. | Medium–large; C06–C08 first |
| U06 | **Precision selection tools.** Add orthographic views, section clipping, zoom-to-question, endpoint handles, edge/plane fitting and full-resolution local picking. The viewer currently uses a capped preview cloud. | Two operators independently select the same known edge; report their selection variability and snapping displacement. | Medium |
| U07 | **Unit-correct questions.** The tolerance control always displays metres, even for area. Introduce result-unit-aware fields, custom tolerance entry, labels/notes, and threshold controls already partly represented in the API. | A projected-area question shows m² for value, tolerance and threshold; invalid point counts fail before creating a persisted question. | Small–medium |
| U08 | **Refinement controls and history.** The UI currently requests a fixed four-frame budget and holds the last run in local state. Expose budget/history/cost and whether the limitation is actually recoverable from unused frames. | Refresh after refinement and inspect every attempt, including no improvement; a scale-limited question does not invite pointless compute. | Medium; C06 first |
| U09 | **Operator summary.** Show capture limits, usable measurement coverage, scale source, elapsed time, warnings requiring action and unanswered questions in one mission summary. | An unfamiliar operator can explain which answers are usable and what to do next without reading JSON. | Small–medium |
| U10 | **One coherent product entry point.** Dashboard/workspace, presentation and dense prototype pages should clearly distinguish new processing, saved-run playback and separate experiment assets. | The judge can navigate from the source upload to that same run's evidence and exports without changing to an unrelated prepared scene. | Small–medium |

Evidence: [Wizard](../frontend/src/views/Wizard.tsx), [API types/client](../frontend/src/api.ts), [schemas](../backend/app/schemas.py), [Tolerance Lens](../frontend/src/ToleranceLens.tsx), [viewer](../frontend/src/PointCloudViewer.tsx), [presentation](../frontend/src/views/Presentation.tsx).

The existing `/api/capabilities` route is worth retaining, but its implementation should report tested usability. In particular, the MVS probe currently treats absence of a particular error string as success without requiring a successful exit or actual device availability. The optional adapter status also needs to distinguish installed components, available weights, wired pipeline support and executable readiness.

## 6. P1: prove the complete problem statement, not just the strongest subsystem

### V01 — Run a real, frozen field evaluation

The existing Field Pack idea—one site, three passes and measured dimensions—is a useful start. It is not broad evidence of deployment readiness. Schedule it immediately while software fixes proceed; acquiring truth is the long dependency.

**Proposed sequence:**

1. Capture at least one new continuous video with original timestamps, telemetry, camera settings and independent dimensions. Do not derive evaluation truth from the reconstruction being tested.
2. Include short and long horizontal dimensions, vertical dimensions, a surface near a depth discontinuity, and an intentionally unobservable feature. Record measurement-instrument uncertainty.
3. Separate development, calibration and locked evaluation by complete mission; where possible, also hold out site or camera. Adjacent frames and partitions of one flight must not inflate the independence count.
4. Freeze questions and settings before scoring. Include failures, unavailable outputs and operator selection error.
5. Report dimensional error, surface accuracy/completeness, raw absolute coordinate error where reference quality permits, accepted-answer rate, false acceptance, interval coverage/width, runtime and peak resources.

The number of independent missions matters more than the number of nearby endpoints. A small pilot must be labelled a pilot. Report uncertainty around empirical coverage rather than treating “19 of 20” as a robust universal 95% guarantee.

### V02 — Build a scene and failure matrix

| Test condition | What I would expect to see |
|---|---|
| Nadir corridor versus oblique facade pass | Separate completeness and dimensional results; do not expect unseen facades from a nadir pass |
| Small baseline/pure rotation | Depth degeneracy detected; useful refusal rather than confident geometry |
| White/repetitive surfaces, glass and water | Increased uncertainty or missing surfaces; no photorealistic completion treated as evidence |
| Trees and moving vehicles | Temporal inconsistency identified; false masks on static rooftops counted |
| Low light, blur, compression and rolling shutter | Explicit degradation curve and supported operating envelope |
| Missing GNSS, poor fixes, outages and time offset | Relative-only output or qualified map placement; scale/position status remains correct |
| Cropped/resized video, zoom change, wrong calibration | Detect incompatible calibration or split camera regimes |
| Scene cut or edited montage | Reject or split the input; never silently treat it as one continuous pass |
| Long corridor and larger capture | Drift, registration failures, resource use and time-to-first-useful-output measured |

There is already capture assessment and a recapture heuristic in [capture.py](../reconstruction/drishti_recon/capture.py). Improve and surface those rather than claiming capture guidance is wholly absent. For this problem, demonstrate the result achievable from the original pass first. A suggested second pass is a recovery option, not evidence that the single-pass requirement was met.

### V03 — Benchmark against the tool a judge would otherwise use

COLMAP already provides sparse/dense reconstruction and surface reconstruction; current upstream documentation also describes textured output. OpenDroneMap documents georeferenced clouds, textured models, orthophotos and optional DSM/DTM outputs. Therefore, “we make a dense 3D model” is weak differentiation. [COLMAP tutorial](https://colmap.github.io/tutorial), [OpenDroneMap outputs](https://docs.opendronemap.org/outputs/)

Use matched input images, calibration, hardware and declared tuning budgets. Compare bare COLMAP and, where practical, an ODM workflow with Drishti3D. Test the installed versions; current upstream capabilities do not imply they exist in the local binary.

Score **time to a defensible answer**, correct refusals, endpoint error, useful measurement yield and operator effort. Compare targeted refinement with uniform compute at matched wall-time budgets and independent truth. A smaller internally predicted sigma alone is not a successful refinement.

### V04 — Close the textured-surface and terrain-output gap

**Code-confirmed.** Current `mesh_poisson` returns geometry and vertex colours; `export_glb` writes those colours. I found no texture-atlas creation in this path. The mesher takes the point cloud without coverage input or explicit per-face observational support, despite the overview's “supported-surface mesh” wording. Density trimming does not by itself prove a face was observed.

**Improve:** build a supported surface with hole preservation, source-image texturing, per-face support/quality metadata and sensible levels of detail. Keep extrapolated closure separate. Where terrain analysis is part of the chosen demo, add a georeferenced DSM and cross-section; derive a DTM only where ground observations/classification support it. Add orthophoto output if it directly helps the selected workflow.

**Done when:** facade/roof detail is inspectable in a textured export; unsupported faces are visibly distinguished; a held-out surface reference measures both error and completeness. Unchanged camera trajectory error after densification must not be called proof that dense surface accuracy is unchanged.

Evidence: [mesh.py](../reconstruction/drishti_recon/mesh.py), [GLB exporter](../reconstruction/drishti_recon/exports.py), [pipeline mesh stage](../reconstruction/drishti_recon/pipeline.py).

### V05 — Make sensor quality and dynamic contamination evidence-specific

`TelemetryReport.has_rtk` becomes true if **any** sample matches an RTK label, and the pipeline then labels the scale source RTK. That does not describe how much of the contributing track had a fixed solution. `ReconstructionEvidence.for_points` also sets `dynamic_contamination=False` unconditionally.

**Improve:** carry per-observation fix quality, sensor conventions and mask/temporal evidence into the result. Distinguish fixed/float/ordinary GNSS fractions and unknown quality. Require an explicit input altitude reference instead of declaring all incoming heights ellipsoidal. Expose time alignment and calibration status to the operator.

**Done when:** a single RTK-labelled sample cannot make a mostly poor-fix mission appear RTK-derived; unknown dynamic status is not represented as a verified negative; moving-surface and mixed-datum test cases fail visibly.

Evidence: [telemetry.py](../reconstruction/drishti_recon/telemetry.py), `_validate`; [pipeline.py](../reconstruction/drishti_recon/pipeline.py), scale-source assignment and `_write_manifest`; [evidence.py](../reconstruction/drishti_recon/evidence.py), `for_points`.

## 7. P1/P2: make the system survive ordinary field use

### R01 — Recoverable processing and immutable inputs

The worker uses one process-local thread pool and in-memory SSE state. Jobs persist in SQLite, but startup does not reconstruct their live state or reconcile interrupted processing. The SSE loop only emits entries from the in-memory map. Duplicate processing submissions are not rejected. Refinement runs synchronously in a separate request path, so the one-worker reconstruction limit does not bound all heavy computation.

Uploads use fixed `video.<extension>` / `telemetry.<extension>` destinations. Same-extension replacement overwrites the prior input; a failed replacement can remove it. Different-extension replacements can leave multiple files, while the worker chooses the first glob match instead of the filename stored on the project.

**Improve:** input revisions and temporary-upload validation before atomic publication; select inputs by recorded identity; refuse conflicting edits during a run; queue reconstruction and refinement with resource limits; support cancellation, durable progress and restart recovery. Publish only completed artifact sets.

**Acceptance:** duplicate clicks, interrupted upload, service restart, failed dense stage and project deletion during a run all have deterministic outcomes. SSE can recover a persisted terminal result after restart. No job silently processes a previous upload.

Evidence: [storage.py](../backend/app/storage.py), [jobs.py](../backend/app/jobs.py), [processing routes](../backend/app/routers/processing.py).

### R02 — A demonstrably offline, installable deployment

The Dockerfile downloads packages during build; that is compatible with offline runtime only after preparation. The GPU-worker profile is explicitly a placeholder, and the backend image does not install the demonstrated CUDA COLMAP stack.

**Improve:** a versioned release image or installer, pinned dependencies/model hashes, tested GPU and CPU capability profiles, preflight checks, local help, and a documented storage/backup procedure. Distinguish “prebuilt runtime works offline” from “can install from scratch without internet.”

**Acceptance:** on a clean test machine, with network disconnected after transferring the prepared bundle, import a new capture, process it with the advertised profile, inspect evidence and export results. Record hardware, RAM, VRAM, disk use and missing-capability behaviour.

Evidence: [Docker Compose](../docker-compose.yml), [backend image](../backend/Dockerfile), [frontend image](../frontend/Dockerfile).

### R03 — A clear local-versus-shared deployment boundary

There is no application authentication/authorization layer in the examined API. Compose publishes its ports without a localhost-only bind. This is a concrete shared-deployment gap, not evidence that a locally used demo has been compromised.

**Improve:** default to loopback for personal use; for shared operation add authenticated access, project permissions, audit records for edits/exports, and a deployment-supported storage encryption policy. Hash input, telemetry, calibration and result artifacts. Hashes detect alteration; authenticated signatures and key handling are needed if claiming who issued a report.

**Acceptance:** a second unauthorized session cannot read/delete another mission; a report identifies actor and result revision; exported bundles expose modifications. Do not spend competition time implementing a large enterprise administration suite before the scientific path works.

### R04 — Bound resource use and support larger scenes

Add stage-level runtime and peak-memory measurements, clear time estimates, resumable dense processing where supported, and an AOI/quality budget. Use streamed/binary or tiled preview data and a spatial index for local full-resolution measurement, instead of treating a large JSON point array as the long-term delivery format.

**Acceptance:** publish preview time, dense completion time, frame rate and peak memory for at least a small and a substantially larger capture. State the supported hardware envelope. Introduce streaming/incremental reconstruction only if it earns its complexity in those measurements.

## 8. Features that could make the entry memorable

Choose two or three after P0. These should reinforce the main task.

| Feature | Why it matters | Smallest convincing demonstration |
|---|---|---|
| **Answer with a visual receipt** | Turns “trust our model” into inspectable evidence | A dimension, two annotated source frames, uncertainty basis and a portable verification result |
| **A visible map of what is unknown** | Shows the limits of one pass in a way point colours cannot | Select an occluded wall and see its missing evidence, while a genuinely observed surface remains measurable |
| **Requirement-aware compute** | Makes targeted refinement an operator benefit | At fixed time budget, answer a frozen difficult question more accurately or refuse it more correctly than uniform processing |
| **An observability ceiling** | Prevents futile refinement when scale dominates | A long span explains its scale-limited tolerance and separates “more frames may help” from “better scale evidence is needed” |
| **A task-focused infrastructure assessment** | Connects geometry to a real analyst workflow | A small set of labelled widths, heights and projected areas exported with evidence and unresolved questions |
| **Supported cross-sections and profiles** | Useful for terrain and structure inspection | A road/embankment profile with gaps and uncertainty visible, without bridging unseen space |
| **Uncertainty-aware repeat-survey comparison** | Valuable later for change assessment | Distinguish a real structural change from registration error, vegetation motion and viewpoint differences |

Repeat-survey comparison is a later extension. Each model can still come from one pass, but it must not distract from proving the requested one-pass reconstruction first. Likewise, geometric visibility tools should represent unknown geometry as unknown; avoid implying that an incomplete model establishes safe clearance.

I would defer a general chatbot, broad object-detection catalogue, autonomous flight integration, thermal fusion, VR mode and additional large reconstruction models. They have plausible future uses, but none closes the current evidence gaps. If “AI-enabled” needs a stronger demonstration, choose one learned component already supported—such as matching—and show a controlled downstream improvement with its weights/version recorded.

## 9. Correct the claims and backlog before the presentation

| Current wording or implication | More defensible wording/action |
|---|---|
| “P0: Nothing” in `NEXT_STEPS.md` | Reopen P0 for the correctness findings in this review |
| “Calibration is the only thing left” | Calibration is one necessary gate; lineage, error modelling, result persistence and export integrity also need validation/fixes |
| “14× density” | Approximately 14× point count; median spacing changed from 0.167 m to 0.099 m. Point count is not a measured 14× increase in geometric resolution |
| “Accuracy unchanged” after dense MVS | Camera-reference agreement stayed similar; dense surface accuracy was not independently scored |
| “95% interval” in the dense benchmark | Nominal 95% sensitivity interval, currently uncalibrated |
| “Every pixel actually measured the point” | Sparse feature pixels are recorded; current dense pixel locations are projected from geometry with approximate contributor attribution |
| “Supported-surface mesh” | Current coloured Poisson mesh; face-level support and texture validation still need implementation |
| “Single-pass proven on three test beds” | Three partitions of one flight; independent-flight evaluation pending |
| “Point clouds carry sigma” | NPZ carries uncertainty; the reviewed PLY/LAS exporters do not yet preserve it |
| “Originals are immutable” | Current uploads overwrite fixed paths; implement revisions before making that claim |
| “Offline GPU deployment” | Local CUDA MVS was demonstrated; the supplied Docker GPU profile remains a placeholder |

The backlog also still says the refinement button is missing in one section and correctly describes it as built in another. Consolidate it into one current state per feature, linking implementation and evidence. The README's default-engine narrative and capability descriptions need the same refresh. Good documentation here directly affects whether a judge trusts the rest of the submission.

Do not blindly adopt “use all discarded frames” as an improvement. First measure why each frame was rejected and whether it adds useful baseline or coverage. Frame count is a resource budget, not an accuracy metric. COLMAP's capture guidance explicitly notes that additional images are not always beneficial and that video may need subsampling. [COLMAP capture guidance](https://colmap.github.io/tutorial)

## 10. Recommended execution order

Effort is relative: **small** is local integration, **medium** crosses components, **large** needs a substantial implementation or experiment. These are not promised calendar estimates.

| Order | Deliverable | Work included | Exit condition |
|---|---|---|---|
| 1 | Consistent measurement results | C01–C03, C06–C07; unit fixes from U07 | Same geometry and requirement give the same result through UI/API, after refinement and after rerun |
| 2 | Honest evidence and scoring | C04–C05, C09–C10; documentation corrections | No derived support or aligned metric is presented as independent accuracy |
| 3 | Repeatable new-upload demo | U01–U03; basic R01 input/job fixes | A fresh capture runs through the demonstrated engine with intact calibration and visible evidence |
| 4 | Usable deliverable | C08, U04–U05, V04 | GIS import, textured/support-aware model and verifiable measurement package work |
| 5 | Independent proof | V01–V03, V05 | Frozen mission-level evaluation supports the actual accuracy and refinement claims |
| 6 | Field deployment polish | R02–R04, U06/U08–U10 | Offline bundle, restart behaviour and larger-scene limits are demonstrated |

**Start field-data arrangements alongside order 1.** Do not wait until all code is finished. Calibration-profile plumbing and export verification can be built with fixtures while real references are collected; their empirical validation cannot.

If time is tight, prioritize **C01, C02, C06, C07, C09, U01–U03, C08 and one independent field evaluation**. Keep dense uncertainty explicitly experimental until C04/C05/C10 are resolved. This creates a smaller, coherent demonstration with evidence behind it.

## 11. The demonstration I would find convincing

1. Identify the continuous capture, camera/calibration, telemetry quality and processing machine. State whether this is new processing or replay of a saved run.
2. Show the actual sparse preview and the recorded dense processing cost. Do not animate saved results as if dense reconstruction finished instantly.
3. Inspect a useful textured/observed region and reveal a deliberately occluded region in the unknown-space layer.
4. Ask a physical dimension chosen before evaluation. Compare its estimate and interval with an independent reference, including the reference uncertainty.
5. Open the supporting images. Explain the difference between recorded feature observations and projected dense markers.
6. Change the required tolerance and show a sensible verdict change. A refusal must remain an acceptable outcome when evidence is insufficient.
7. Refine a question that can benefit from unused frames. Show value, evidence, uncertainty and elapsed cost separately, including a failed/no-improvement case.
8. Export the selected measurement passport and a geographically correct artifact. Verify the passport and import the artifact outside Drishti3D.

That is stronger than a tour through many panels. It demonstrates capture → geometry → answer → evidence → independently usable output.

## 12. Verification performed for this review

**Frontend:** `npm run build` passed, including TypeScript compilation and the Vite production build. This is not a browser usability or visual-performance test.

**Focused tests:** 78 passed in 1.52 seconds:

```bash
cd drishti3d
.venv/bin/python -m pytest \
  tests/test_questions.py tests/test_uncertainty.py tests/test_mvs.py \
  tests/test_lineage.py tests/test_quality_measure.py tests/test_evidence.py -q
```

**Full suite:** **335 passed, 49 warnings in 114.73 seconds**, using the command below outside the sandbox after approval. Warnings concern deprecated dependency interfaces. The diagnostic traceback emitted after 60 seconds was from the running synthetic integration test; that test subsequently completed successfully.

```bash
cd drishti3d
.venv/bin/python -m pytest tests/ -q -o faulthandler_timeout=60
```

The initial sandboxed run stalled starting Starlette's `TestClient`; a focused rerun located the wait in the AnyIO blocking-portal startup. The successful run outside the sandbox resolved that verification limitation. The passing suite is valuable, but it does not test away the specific numerical and artifact-lifecycle counterexamples below. Add targeted regression coverage when fixing them.

**Additional isolated reproductions:** used temporary files and synthetic arrays, without processing or altering the user's saved missions.

| Check | Observed result |
|---|---|
| Same 10 m length, 10% shared scale noise, zero endpoint noise | Two vertices: sigma 1.0 m; three collinear vertices: sigma 0.70710678 m |
| Select `[1000,0,0]` with nearest cloud point `[10,0,0]` | Snapped 990 m with no distance rejection |
| Export LAS with a supplied ENU origin | Parsed CRS `None`; no extra dimensions |
| Replace `cloud.npz` after first cached load | Subsequent loader call returned old points |
| Add `[100,200,30]` m to a reference trajectory | `as_georeferenced` returned zero median, p90, maximum and RMSE |
| Send distortion coefficients in `ProcessRequest.intrinsics` | Validated request retained only fx, fy, cx and cy |

**Review limits:** no fresh GPU dense reconstruction, independent field capture, full browser walkthrough, clean-machine install, penetration test, or empirical calibration study was performed. Existing benchmark results are attributed as recorded evidence. Code-confirmed risks are distinguished from executed reproductions. New features and acceptance experiments are proposals; no claim is made that completing a checklist guarantees a competition win.

**My decision as the simulated evaluator:** the project now has enough substance to justify serious attention. I would still challenge its central promise until the team demonstrates that a reported physical measurement is tied to the correct reconstruction revision, survives refinement/export, and agrees with independent truth. Solving those issues and making the evidence visible would do more for this entry than another impressive-looking model.
