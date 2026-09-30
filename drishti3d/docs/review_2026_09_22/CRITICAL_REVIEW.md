# Critical review: what will actually improve Drishti3D's chances

**Review date:** 22 September 2026. **Code reviewed:** `9506a31`. Companion: [current project report](PROJECT_REPORT.md), [source trail and verification](README.md).

## 1. Verdict

Drishti3D now has a substantial working prototype: reconstruction, georeferencing, measurement evidence, targeted refinement, exports and a coherent frontend. The previous review's regression failures are fixed. The strongest progress is that the system increasingly distinguishes a plausible result from a defensible measurement.

However, **the repository does not yet demonstrate that the project meets the organiser's principal accuracy, completeness and speed expectations**. A polished viewer, millions of points, low reprojection error and passing tests cannot substitute for those demonstrations. The next iteration should be an evaluation-and-integration sprint, not another broad feature expansion.

The key risk is credibility: the latest dimensional experiment is useful exploratory evidence, but its nearest-LiDAR endpoint construction does not establish the advertised physical dimensional accuracy. Correcting that claim before judges discover the weakness makes the project stronger.

## 2. What the organisers actually ask for

The [official portal](https://www.sih.gov.in/sih2026PS) describes an AI-enabled reconstruction system using one UAV video trajectory, with georeferenced metric output suitable for analysis. The linked [organiser attachment, page 2](https://drive.google.com/file/d/119hjXkLhMW_AhQ4cyYz-XJgcVz4BA-hD/view) supplies the numerical expectations absent from earlier local reviews.

| Scoring category | Weight | Consequence for this project |
|---|---:|---|
| Reconstruction accuracy | 30% | Independent physical references must take priority over internally estimated confidence. |
| Completeness | 20% | Demonstrate how much of the visible scene was reconstructed, including difficult surfaces. |
| Processing speed | 20% | Benchmark the whole required workflow on the specified video duration. |
| Innovation | 15% | Prove the measurement-question and refinement workflow's added value. |
| Scalability | 10% | Show memory, video-length and job-recovery behaviour. |
| User interface | 5% | Improve task clarity and evidence visibility; avoid spending most remaining effort on cosmetics. |

The accuracy target is **at most 1 metre**, and processing should take **under 15 minutes for a 10-minute video**. The attachment calls for the entire visible scene, lists OBJ, PLY, LAS, GeoTIFF, GLB/GLTF and FBX, and accepts a web or desktop viewer. It does not define whether the accuracy statistic is RMSE, a percentile or a maximum, nor specify benchmark hardware. Report several statistics and seek clarification without assuming the most favourable interpretation. The format list also needs clarification about mandatory coverage versus acceptable alternatives.

| Requirement or challenge | Evidence in the current project | Review status / remaining proof |
|---|---|---|
| One moving-UAV video trajectory | Video ingestion, keyframes and sequential reconstruction exist. | Implemented path; principal saved studies use videos assembled from still frames, so native-video behaviour needs direct evaluation. |
| 1080p/4K video, GPS and flight metadata | Video/telemetry upload, timestamp handling and georegistration. | Test native 1080p and 4K captures, long files, missing records and inconsistent clocks end to end. |
| Metric, georeferenced output; ≤1 m spatial target | ENU reconstruction, projected LAS, georeference sidecars. | Not demonstrated against independent checkpoints. UseGeo raw surface-distance RMSE is 1.283 m. |
| Entire visible scene | Dense MVS and internal visibility/coverage classifications. | No independent visible-surface completeness score; own-cloud volume statistics are not that score. |
| Under 15 minutes for 10 minutes of video | Stage timings and CPU/COLMAP comparisons exist. | No qualifying benchmark. Existing dense runs exceed 20 minutes on much shorter derived videos. |
| Mesh or point-cloud output | Point clouds and coloured GLB meshes exist. | Point-cloud route is credible; vertex colouring is not UV photo-texturing. |
| Listed output formats | PLY, LAS and GLB are wired, alongside reports and trajectory exports. | GeoTIFF and FBX are missing. OBJ/standalone GLTF are not established web export options; generic mesh-writer capability is insufficient proof. |
| Terrain, roofs/facades, roads, vegetation and obstacles | General geometry and dynamic masking support. | Need per-scene/per-surface results, particularly facades, thin obstacles and vegetation. Semantic labelling is useful, not clearly a mandatory output. |
| Blur, compression, illumination and motion | Quality filters, masking and robust matching components. | Stress-test controlled degradations; identify failure limits instead of claiming immunity. |
| GPS noise; little dependence on GCPs | Robust alignment, telemetry quality handling; optional corrections. | Establish a consumer-GPS baseline separately from RTK/PPK-assisted performance. Optional references cannot become an unstated mandatory input. |
| Occluded surfaces | Unobserved/inferred geometry is distinguished from observed evidence. | Show gaps honestly. Unseen surfaces cannot become measured truth merely through AI completion. |
| AI contribution | LightGlue/DISK is connected to targeted refinement; optional learned masking/depth and research reconstruction modules also exist. | Extend existing matcher/refinement experiments to independent physical accuracy. The main saved COLMAP/MVS runs use classical settings. |

The portal says the organiser dataset will be provided in real time; a downloadable challenge dataset was not supplied by this entry. Public datasets are development evidence, not proof of performance on the future organiser data.

## 3. What the saved results prove—and what they do not

These figures come from saved artifacts, not new reconstruction runs in this review.

| Quantity | UseGeo `usegeo_1__first` | AGZ `agz_dense_pass__dense_mvs` |
|---|---:|---:|
| Registered selected cameras | 60/60 | 80/80 |
| Final cloud points | 2,138,943 | 251,785 |
| Median reprojection error | 0.271 px | 0.326 px |
| Camera/GPS alignment RMSE, 3D | 0.293 m | 6.143 m |
| Recorded processing time | 1,401.3 s / 23.36 min | 1,243.463 s / 20.72 min |
| Derived video duration | 125.44 s | 184.48 s |
| Processing/video-duration ratio | 11.17 | 6.74 |
| Independent absolute checkpoint accuracy | Not established | Not established |

UseGeo is an approximately 0.478 fps, 7952×5278 video assembled from 60 images. AGZ is an approximately 0.997 fps, 1920×1080 sequence assembled from 184 images, of which 80 were selected as keyframes. These are not substitutes for a ten-minute native video. Their timing ratios are diagnostic, not a valid linear forecast of performance on the organiser's workload. In the current AGZ artifact, densification consumes **1,155.367 seconds**, about **93%** of reported runtime: optimise that stage before micro-optimising the interface.

### UseGeo independent LiDAR comparison

The saved `lidar_score.json` reports 200,000 sampled reconstructed points, with 199,956 within a 5 m nearest-reference cutoff:

- Raw nearest-surface median **1.360 m**, p90 **1.640 m**, RMSE **1.283 m**.
- Median signed vertical difference approximately **+1.245 m**.
- Subtracting a median bias estimated from that same reference produces median **0.299 m** and RMSE **0.330 m**. This diagnoses an offset; it is not an independently validated production correction.
- Raw reference-to-reconstruction completeness within the reconstruction's own footprint is **1.463% at 0.25 m** and **4.207% at 0.5 m**. These values are affected by the offset and are not a whole-visible-scene coverage measure.

The raw 1.283 m figure exceeds 1 m, but it is a nearest-surface statistic, not the organiser's still-undefined spatial-accuracy protocol. The responsible conclusion is **compliance not demonstrated**, not a certified pass/fail determination using an invented protocol.

The score's 4.55% containment under a `1.96 × sigma` rule is a serious discrepancy for that experiment. However, unsigned 3D surface distance compared with a scalar uncertainty is not a calibrated two-sided measurement-interval experiment. Do not present it as a universal coverage rate for every length or height measurement.

### Why the latest 8.8 cm dimensional claim needs revision

The latest documentation describes selecting each reconstructed endpoint's nearest LiDAR neighbour and comparing lengths between those selected neighbours. It reports a median error of 0.088 m over 5–60 m baselines. This is **surface-consistency evidence with output-dependent correspondences**, not independent identification of the same physical endpoints.

A reproducible counterexample is included in `measurement_validity_probe.json`: a true 10 m segment is reconstructed as 10.5 m on a densely sampled plane. Its nearest-reference endpoint pair is also 10.5 m, so the experiment reports essentially zero error despite a real **0.5 m / 5%** error. This does not establish that UseGeo has that error; it establishes that the current method cannot rule it out.

The claimed flat long-baseline result also uses the best-corresponding 6.4% of points. Do not combine that subset result with the all-point 0.088 m number as if they describe one population. The latest commit records the analysis in documentation; a reproducible dimensional scorer with raw named pairs was not located.

**Required correction:** label these numbers exploratory, retain the useful experiment, and add independently named endpoints, a frozen test manifest, the scorer, random seed, exclusions and complete outputs. A ratio of median absolute error to median sigma does not prove conservative 95% intervals; the included counterexample has a zero median ratio while covering only 60% of errors.

### Revisit the explanation of planarity

The new fail-closed measurement guard is safer than allowing unsupported claims. Its mathematical explanation needs precision: non-collinear planar 3D correspondences can determine a proper seven-parameter similarity transform. The diagnostic script demonstrates a rank-seven Jacobian and essentially exact recovery while the current trajectory heuristic flags planarity.

Planar/nadir image acquisition can still weaken joint camera calibration and reconstructed depth. That is different from saying every planar point set makes the similarity transform unidentifiable; an isotropic similarity also has no separate vertical scale parameter. Keep conservative blocking until validated, then replace blanket conclusions with joint-system conditioning and quantity-specific evidence. The 1.245 m bias could involve datum, time, lever arm, camera calibration or reconstruction error; planarity alone has not been isolated as its cause.

## 4. Highest-value implementation gaps

| Priority | Finding and code evidence | Concrete completion criterion |
|---|---|---|
| P0 | The best demonstrated COLMAP/MVS configuration is not reproducible from the normal wizard. Backend/pipeline support is broader than `frontend/src/api.ts` and `views/Wizard.tsx`. | A user creates the benchmark configuration through the UI, and its saved manifest exactly records the selected engine, MVS options and effective settings. |
| P0 | Backend `Intrinsics` supports distortion, model and source dimensions; the frontend exposes/preserves only four pinhole values. | Load, resume, edit and process a calibrated mission without losing distortion/model/dimensions; show resize/undistortion provenance. |
| P0 | Calibration machinery exists, but production question evaluation passes `profile=None` in `backend/app/results.py` and question routes. | Resolve a versioned, applicable released profile; reject mismatched or absent profiles; preserve estimated-only status otherwise. Release only after independent held-out evaluation. |
| P0 | Independent dimensional and ten-minute benchmarks are missing. | Publish reproducible raw endpoints, reference uncertainty, all outcomes and complete timing/resource logs. |
| P1 | New backend result metadata is not fully represented in the frontend's basic `Measurement` view; degeneracy is insufficiently visible. | Every result presents units/frame, uncertainty status, blocking reasons and artifact/profile versions consistently across question, measurement and report screens. |
| P1 | Viewer picks come from a cloud capped at 120,000 points. | Image-anchored or full-resolution ROI selection identifies physical endpoints; display any snap displacement and refuse unsupported corners. |
| P1 | `jobs.py` uses a one-worker in-process executor; restart state and concurrent mutation handling are incomplete. | Persistent recoverable job states, duplicate-run prevention, cancel/retry, server-side deletion locks and atomic artifact publication. |
| P1 | Coverage denominator is derived from reconstruction, not independently defined visible surfaces. | Score visible-reference surfaces by category and distinguish unobserved, occluded, dynamic, reconstructed and measurable. |
| P1 | Existing exports cover only part of the organiser's format table. | A documented supported-format matrix plus round-trip CRS/unit/attribute checks; implement highest-priority missing formats after clarification. |
| P2 | Optional AI module presence can be mistaken for an executable integrated engine. | Capability probes execute a tiny real reconstruction; unsupported web adapters are labelled experimental, and model/weight versions are recorded. |

No open P0 above means the old fifteen-check suite regressed. These are additional evaluation and integration findings beyond that suite.

## 5. Comparable products and research

This is a source-based capability comparison, **not a head-to-head accuracy or price benchmark**. Product availability, editions and engines must be pinned when experiments are run. “Not established” does not mean a competitor lacks a feature.

| Comparator | Verified overlap / established strength | Implication for Drishti3D |
|---|---|---|
| [WebODM](https://webodm.org/) | Local/offline photo and video processing, georeferenced outputs, textured models, measurement, GPU/distributed processing. | Most direct open-source product baseline. Video input, offline operation and a web viewer are not differentiators by themselves. |
| [Agisoft Metashape Professional](https://www.agisoft.com/features/professional-edition/) | Aerial photogrammetry, camera calibration, control/scale bars, measurements, CRS/vertical reference support and textured outputs. | Mature metrology and calibration workflow; match its clarity about control, datum and quality. |
| [PIX4Dmatic quality reports](https://support.pix4d.com/hc/en-us/articles/360040686852) | Reports camera optimisation, geolocation, overlap and control/checkpoint information. | A quality report is an expected feature. Link uncertainty to the actual question and independently measured outcomes. |
| [DroneDeploy accuracy guidance](https://help.dronedeploy.com/hc/en-us/articles/1500004964062-How-Accurate-is-My-Map) and [Verified Accuracy](https://help.dronedeploy.com/hc/en-us/articles/33265412026519-Verified-Accuracy) | Distinguishes relative/absolute accuracy and offers accuracy alerts and guidance. | “Trustworthy mapping” alone is not novel. Demonstrate finer-grained evidence and targeted correction value. |
| [DJI Terra](https://www.dji.com/support/product/dji-terra) | Established reconstruction ecosystem and an offline edition with activation requirements. | Avoid claiming that commercial tools necessarily need a live cloud connection. Benchmark the relevant edition and hardware. |
| [RealityScan video import](https://rshelp.capturingreality.com/en-US/tools/videoimport.htm) | Video-to-frame import integrated into photogrammetry workflows. | Automatic frame extraction from a video is established functionality. |
| [COLMAP](https://colmap.github.io/faq.html) | SfM/MVS infrastructure, georegistration and pose-prior capabilities. | A component and baseline, not evidence that Drishti invented reconstruction. Measure the value added above it. |
| [MASt3R-SLAM, CVPR 2025](https://openaccess.thecvf.com/content/CVPR2025/html/Murai_MASt3R-SLAM_Real-Time_Dense_SLAM_with_3D_Reconstruction_Priors_CVPR_2025_paper.html) | Learned-prior dense monocular SLAM; paper reports real-time operation in its setting. | A relevant speed/geometry research baseline. Its reported frame rate is not a Drishti3D UAV benchmark. |
| [VGGT repository](https://github.com/facebookresearch/vggt) | Learned prediction of cameras and scene geometry, with COLMAP/BA integration examples. | Useful research ingredient, not automatic metric accuracy or a finished integrated backend. Check the exact checkpoint licence. |
| [MASt3R-Fusion](https://arxiv.org/abs/2509.20757) | Learned visual geometry with IMU/GNSS integration and metric/global constraints. | Even learned reconstruction plus GNSS/IMU is established research territory; narrow the novelty claim. |

WebODM's current site says it has decoupled from OpenDroneMap and uses ODX. Do not silently compare a legacy ODM installation with claims from the current WebODM product without recording versions. Its [video options documentation](https://docs.webodm.org/tutorials/options-selection-guide/) also covers video-frame controls and associated GPS subtitles.

The VGGT repository distinguishes its original non-commercial checkpoint from a later commercial checkpoint and explicitly excludes military applications from that commercial permission. The [licence's acceptable-use conditions](https://github.com/facebookresearch/vggt/blob/main/LICENSE.txt) therefore need review for the intended deployment. Do not assume “open source” means every code/weight combination is suitable for an NTRO deployment. A working classical path remains useful while optional model licences are resolved.

### A defensible uniqueness claim

**Proposed positioning:** “Drishti3D turns a single recorded UAV pass into measurement questions backed by source observations, explicit limits and a targeted refinement trail.”

The potentially distinctive combination is:

1. Start with a named distance, height or area question and its required tolerance.
2. Connect the answer to actual source-frame observations, coordinate frame and reconstruction version.
3. Distinguish an estimate from a calibrated decision, and refuse unsupported conclusions.
4. Select additional useful frames from the **same recorded pass**, under a time budget.
5. Show before/after evidence, cost and independently measured improvement.

The repository contains meaningful parts of this workflow, but calibrated acceptance and independent before/after accuracy gains are not yet established. This is a promising product/research hypothesis, not a proven world-first claim. No patent or exhaustive novelty search was performed.

### How to prove the difference

Run Drishti3D, a pinned WebODM engine and COLMAP on the same held-out captures and hardware. Use two tracks: each product's normal best-practice workflow, and an identical-frame/identical-control experiment. Record human effort, settings, failures, preprocessing and runtime boundaries. Measure absolute accuracy, named dimensions, visible-surface completeness, total time and memory. For Drishti3D, compare targeted refinement against no refinement and uniformly selected extra frames under the same compute budget. A result is valuable only if it improves physical error or the calibrated decision, not merely confidence or point count.

## 6. Measurement improvement plan

### Step 1 — Make the evaluation independent

Before inspecting new outputs, freeze identifiable landmarks and tasks: road widths, roof-edge lengths, wall/roof heights with defined ground bases, and planar areas. Obtain surveyed coordinates or independently extracted LiDAR features with reference uncertainty. A nearby LiDAR point selected after reconstruction is not a ground-truth identity.

Store flight/site IDs, source images, endpoint identities, reference coordinates, horizontal/vertical datum, time basis, measurement definition and exclusions. Separate calibration, tuning and final evaluation by **site/flight**, not adjacent frames or two halves of the same flight. An initial six-flight/three-site matrix is a practical engineering start, not proof of a calibrated 95% guarantee.

Report signed bias, MAE, RMSE, p50/p90/p95, maximum error and task success/refusal rates. Separate length, vertical height, horizontal area and any later surface-area implementation. Use flight-clustered uncertainty intervals; millions of correlated random point pairs do not create millions of independent experiments. Publish results before and after any fitted correction, with correction parameters fitted only on training data.

### Step 2 — Fix the input and coordinate error budget

- Preserve full camera model, distortion coefficients, source resolution and resize transforms through the UI, database, pipeline and export. Verify undistortion happens exactly once.
- Validate UTC/GPS epochs, leap-second conversion, video timestamps, clock offset/drift and dropped frames. The documented 18-second UseGeo conversion issue makes this a demonstrated concern.
- Resolve ellipsoidal versus orthometric altitude explicitly before attributing vertical bias to geometry. Preserve CRS and geoid-model provenance.
- Apply a correctly oriented antenna-to-camera lever arm where supplied. Use RTK quality and anisotropic GNSS uncertainty when available; do not silently promote ordinary GPS to RTK quality.
- Keep automated offset/gravity corrections gated by evidence. Rejected estimates should remain visible rather than being forced to make a residual smaller.

**Exit gate:** synthetic and surveyed coordinate checks agree, a calibrated mission survives UI round trips, and no constant correction is estimated on the final test set.

### Step 3 — Improve geometry where it changes the answer

Expose the proven COLMAP/MVS path through the website. Compare post-hoc similarity alignment against joint pose-prior bundle adjustment, using the installed COLMAP version's supported APIs and correctly transformed covariances. Constrain camera calibration appropriately for weak acquisition geometry; avoid simultaneously freeing poorly observed parameters.

For endpoint precision, combine full-resolution image selection with local point/plane/edge fitting. Retain the original clicked observation, fitted support, residuals and snap displacement. A fitted roof plane may improve height on a clean roof, but fitting across vegetation or two intersecting surfaces can make an answer confidently wrong. Require support and reject ambiguous geometry.

Improve height using a defined local ground reference and validated gravity direction. Keep XY-projected area distinct from sloping-surface area. Add ground-to-roof workflows before adding a large collection of superficially impressive measurement tools.

### Step 4 — Model uncertainty for the quantity being measured

Current sparse point covariance conditions on fixed camera poses; dense uncertainty is approximate. Neither alone captures shared pose error, scale, datum bias or endpoint ambiguity. Preserve anisotropic covariance rather than reducing all evidence prematurely to a scalar.

For a two-endpoint length L with direction u, a useful local approximation is:

```text
Var(L) ≈ uᵀ(Ca + Cb − Cab − Cba)u + L² × σ²_relative_scale
```

Here Cab is endpoint cross-covariance. Common translation cancels from a length, but scale does not. If scale is already part of the joint state covariance, do not count its contribution twice. Vertical height uses the vertical projection of the relative covariance plus orientation uncertainty. Area requires its coordinate Jacobian and appropriate scale propagation; under isotropic scaling alone, its scale contribution is approximately `4 × A² × σ²_relative_scale`.

Calibrate the resulting intervals empirically on held-out flights, by measurement kind and acquisition regime. Report coverage **and interval width**, with uncertainty on the coverage estimate. A narrow interval is not better if it misses truth, and an arbitrarily huge interval is not useful merely because it covers truth. A scalar `1.96 × sigma` rule for signed one-dimensional errors is not automatically a 95% radial 3D bound.

### Step 5 — Make “Try targeted refinement” earn its place

The option revisits a question using additional useful observations from the existing recording and local refinement. It cannot create missing viewpoints, resolve an unknown datum by itself, or certify a result without calibration.

Why not run it automatically for everything? Extra frames consume compute, may repeat the same viewing direction, can introduce bad matches or motion, and may offer no remaining information. One documented independent segment had all 62 frames already selected, with only 19 registering, so there was no extra-frame pool to exploit. Existing AGZ targeted-refinement studies improve an internal “blocked only by calibration” yield, **not independently verified physical accuracy**.

A better policy is automatic refinement only when a requested tolerance is unmet, useful candidates remain and predicted information gain justifies the runtime. Rank candidates by novel baseline, target visibility, image quality and expected uncertainty reduction per second. Preserve a no-change outcome, a clear reason for refusal, and the previous artifact. Validate this policy against uniform selection and actual reference error. A recommended second flight is a transparent fallback, not a successful single-pass result.

## 7. Ordered delivery backlog

Effort estimates are planning ranges, not commitments; data availability is the main dependency. Assign by responsibility, not by inventing team members.

| Order / owner role | Deliverable | Suggested effort | Acceptance evidence |
|---|---|---|---|
| 1 / evaluation lead | Freeze truthful claims and build independent landmark scorer. | 1–2 days once references exist | Versioned pair manifest, raw outputs, no nearest-match identity leakage. |
| 2 / frontend + reconstruction | Preserve calibration metadata; expose engine/MVS presets; surface measurement status. | 1–2 days | UI-created run matches benchmark manifest and retains intrinsics on resume. |
| 3 / reconstruction | Datum/time/lever-arm investigation and geometry ablations. | 2–4 days | Independently held-out bias/error reductions with corrections traceable. |
| 4 / performance | Native ten-minute 1080p and 4K runs; stage profiling and bounded MVS. | 1–3 days | End-to-end time, hardware/VRAM/RAM, failures and accuracy/coverage tradeoffs. |
| 5 / evaluation | Visible-surface completeness and competitor benchmark. | 2–4 days | Common input matrix, per-surface recall, matched settings and reproducible scripts. |
| 6 / measurement | Uncertainty/profile integration and targeted-refinement validation. | 3–5 days after reference data | Held-out coverage, widths, false decisions, refusal rate and before/after error. |
| 7 / platform | Durable jobs, atomic artifacts, format round trips and offline rehearsal. | 2–4 days | Restart/cancel/retry/concurrent-request tests and exported files opened independently. |
| 8 / presentation | Six-slide evidence-led pitch and repeatable demonstration. | 1 day after results freeze | Every headline points to a current artifact; limitations survive the demo narrative. |

Within a short deadline, do the first four and make the remaining gaps explicit. Avoid diverting effort into a chatbot, ornamental dashboards, speculative object recognition or photorealistic completion unless a controlled experiment shows they improve a scored requirement.

## 8. Questions a strict judge is likely to ask

1. “Show the same named physical endpoints in your output and independent reference. What is the worst error?”
2. “Which ten-minute video finished in under fifteen minutes, on what machine, including which stages?”
3. “How did you define the entire visible scene before looking at your own reconstruction?”
4. “What happens to facades, power-line-like thin obstacles, vegetation, shadows and moving vehicles?”
5. “Why does your camera/GPS residual look good while the LiDAR comparison is over a metre away?”
6. “What part is your contribution above COLMAP or WebODM, and where is the controlled comparison?”
7. “Does this button improve real measurement error or only your own score?”
8. “Can I reproduce your best run from the website and open the exported file with the same units and CRS?”
9. “What does the system do when no trustworthy measurement is possible?”
10. “Which optional AI component actually ran, what did it improve, and can it be deployed under its licence?”
