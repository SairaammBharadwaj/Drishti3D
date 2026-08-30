# SIH26158 — Drishti3D Research and Claude Implementation Brief

## Problem statement

**ID:** SIH26158  
**Organization:** National Technical Research Organisation (NTRO)  
**Category:** Software  
**Theme:** Robotics and Drones  
**Title:** Single-Pass Drone Video to Accurate 3D Model Generation System

The objective is to develop an AI-enabled system that converts a single-pass UAV video, GPS coordinates, and flight metadata into a georeferenced and metrically accurate 3D representation. Desired outputs include terrain, structures, facades, rooftops, roads, infrastructure, vegetation, obstacles, point clouds, and textured meshes suitable for measurement, visualization, and analysis.

## Research conclusion

A monocular video can recover relative camera movement and 3D geometry because successive frames provide different views. It nevertheless has inherent scale ambiguity. GPS, altitude, IMU, calibrated camera parameters, RTK/PPK, or known dimensions are needed to recover metric scale and geographic coordinates.

A single trajectory also cannot accurately measure a surface never observed by the camera. AI may create a plausible completion, but such a result must be labelled as inferred rather than measured.

The proposed system must distinguish:

- Directly observed, high-confidence geometry
- Observed but low-confidence geometry
- AI-assisted or inferred surfaces
- Dynamic objects excluded from the reconstruction
- Occluded or unobserved regions

This distinction is especially important for intelligence, disaster response, inspection, and measurement applications.

## Relevant technical foundations

- MASt3R-SLAM performs dense monocular reconstruction and reports operation at approximately 15 FPS: <https://openaccess.thecvf.com/content/CVPR2025/papers/Murai_MASt3R-SLAM_Real-Time_Dense_SLAM_with_3D_Reconstruction_Priors_CVPR_2025_paper.pdf>
- VGGT predicts camera poses, depth maps, point maps, and tracks and can export COLMAP-compatible reconstruction data: <https://github.com/facebookresearch/vggt>
- DROID-SLAM jointly estimates camera poses and pixelwise depth using dense bundle adjustment: <https://arxiv.org/abs/2108.10869>
- COLMAP supports conventional Structure from Motion, GPS pose priors, robust similarity alignment, and ECEF/ENU georegistration: <https://github.com/colmap/colmap/blob/master/doc/faq.rst>
- EuRoC provides synchronized UAV imagery, IMU readings, and accurate ground truth: <https://journals.sagepub.com/doi/10.1177/0278364915620033>
- TartanAir provides images, depth, segmentation, optical flow, camera poses, and LiDAR-like ground truth: <https://arxiv.org/abs/2003.14338>

## Proposed product

**Working name:** Drishti3D

> A confidence-aware, georeferenced 3D reconstruction and measurement platform for single-pass UAV video.

### Core approach

Use two complementary reconstruction paths:

1. **Verified geometry:** video keyframes → feature matching/SLAM → bundle adjustment → GPS/IMU scale alignment → point cloud → mesh.
2. **AI-assisted geometry:** learned depth and correspondence priors improve difficult regions, while semantic and motion analysis removes vehicles, humans, animals, shadows, and unstable pixels.

Every output point or surface should carry provenance and confidence.

Suggested visualization:

- Green: high-confidence observed geometry
- Amber: weak-baseline or low-confidence observed geometry
- Purple: AI-assisted/inferred geometry
- Red or transparent: unknown/unobserved region

Measurements should exclude inferred geometry by default.

## Architecture

```text
Drone video + telemetry
          │
          ▼
Ingestion and synchronization
          │
          ├── Video quality analysis
          ├── Keyframe selection
          ├── Camera calibration/estimation
          └── GPS/IMU interpolation
          │
          ▼
Dynamic-object and bad-frame filtering
          │
          ├── Motion masks
          ├── Semantic masks
          └── Blur/exposure confidence
          │
          ▼
Hybrid reconstruction
          │
          ├── Fast AI/SLAM preview
          └── COLMAP verified refinement
          │
          ▼
GPS/IMU-constrained bundle adjustment
          │
          ▼
Dense point cloud + mesh + texture
          │
          ▼
Confidence/provenance map
          │
          ▼
Web viewer, measurements, exports and report
```

## Recommended technology stack

| Component | Recommendation |
|---|---|
| Frontend | React, TypeScript, Vite |
| 3D viewer | CesiumJS; Three.js fallback |
| 2D mapping | MapLibre GL |
| API | FastAPI |
| Job execution | Python worker initially; Celery and Redis later |
| Media | FFmpeg/ffprobe and ExifTool |
| Frame processing | OpenCV |
| Verified reconstruction | COLMAP/PyCOLMAP |
| AI reconstruction | MASt3R-SLAM or VGGT adapter |
| Point-cloud processing | Open3D |
| Coordinate conversion | pyproj |
| Dynamic masking | Torchvision model plus optical-flow residuals |
| Prototype database | SQLite |
| Production database | PostgreSQL/PostGIS |
| Outputs | PLY, LAS/LAZ, OBJ/GLB, GeoJSON, trajectory CSV, JSON and HTML reports |
| Deployment | Docker Compose with optional NVIDIA GPU worker |

The product should support local and air-gapped operation.

## Prototype deliverables

1. Upload 1080p/4K video and telemetry.
2. Synchronize frames and telemetry.
3. Display blur, exposure, GPS, and coverage quality.
4. Generate a quick 3D preview.
5. Generate a refined, georeferenced point cloud.
6. Generate a mesh where coverage is sufficient.
7. Display the UAV trajectory on a map.
8. Measure distance, height, area, and coordinates.
9. Toggle observed, uncertain, dynamic, and inferred layers.
10. Export models, measurements, and a quality report.
11. Operate offline after dependencies and model weights are installed.
12. Provide stage progress and meaningful failure explanations.

## Desired output and evaluation criteria

| Desired output | Evaluation criterion | Metric |
|---|---|---|
| Georeferenced point cloud or mesh | Geographic accuracy | Horizontal and vertical RMSE against RTK/GCP/reference points |
| Metrically scaled model | Dimensional accuracy | Absolute and percentage errors for known distances, heights, and areas |
| Accurate camera trajectory | Pose accuracy | Absolute Trajectory Error and Relative Pose Error |
| Complete visible-scene reconstruction | Completeness | Percentage of reference surface reconstructed within a tolerance |
| Geometric fidelity | Surface accuracy | Point-to-reference RMSE, Chamfer distance, or cloud-to-cloud distance |
| Robust video processing | Frame usability | Percentage of frames correctly accepted/rejected for blur and exposure |
| Dynamic-object resistance | Static-map cleanliness | Dynamic points remaining in the final model |
| Textured output | Visual quality | Texture coverage and reprojection consistency |
| Near-real-time processing | Efficiency | Processing time divided by video duration |
| Reliable measurements | Repeatability | Variation across repeated measurements and runs |
| Confidence-aware output | Confidence calibration | Error rate grouped by predicted confidence band |
| Portable output | Interoperability | Successful PLY, LAS, GLB/OBJ, GeoJSON, CSV, and report exports |

### Defensible prototype targets

- With RTK/PPK, target decimetre or better georegistration, subject to camera, altitude, and flight geometry.
- With ordinary GPS, explicitly report GPS-limited absolute accuracy, which may be metre-level.
- Target below 3–5% relative dimensional error on well-observed surfaces.
- Target a fast preview close to video duration; allow refined reconstruction to take several times the video duration.
- Never claim centimetre accuracy without measured ground-truth evidence.

## Immediate decisions required

By September 1, confirm:

- Expected NTRO telemetry formats
- Available NVIDIA GPU and VRAM
- Whether deployment must be internet-free
- Whether point-cloud output is sufficient for the primary demonstration
- Licences permitted for AI models and weights
- Test drone/camera and availability of camera calibration
- One public evaluation dataset and one team-captured dataset
- Accuracy claims supported by actual tests

For the September 20 submission, prioritize:

1. Real point-cloud reconstruction from video
2. GPS-aligned camera trajectory
3. Distance and height measurement
4. Confidence visualization
5. Dynamic-object masking
6. Exportable artifacts
7. Reproducible evaluation report

---

# Claude Pro implementation prompt

Copy the following prompt into Claude Pro and give it access to a new repository. Require phase-by-phase implementation and verification.

```text
You are the principal computer-vision engineer and full-stack architect for an SIH prototype named Drishti3D.

PROBLEM STATEMENT

SIH26158, submitted by the National Technical Research Organisation:

“Single-Pass Drone Video to Accurate 3D Model Generation System.”

Build an AI-enabled, offline-capable system that accepts a single-pass drone video plus GPS and flight metadata, reconstructs a georeferenced and metrically scaled 3D scene, and supports visualization, measurement, analysis and export.

The system should reconstruct visible terrain, structures, rooftops, roads, infrastructure, vegetation and obstacles as a point cloud and, when feasible, a textured mesh.

CORE SCIENTIFIC CONSTRAINT

A monocular single-path video cannot accurately observe surfaces that never appear in any frame. Do not present hallucinated geometry as measured truth.

Represent geometry using explicit provenance classes:

1. OBSERVED_HIGH_CONFIDENCE
2. OBSERVED_LOW_CONFIDENCE
3. AI_ASSISTED
4. DYNAMIC_EXCLUDED
5. UNOBSERVED

Measurements must default to observed geometry only. AI-assisted surfaces must be visually distinguishable and excluded from measurement unless the user explicitly enables them.

PRIMARY PRODUCT OBJECTIVE

Create a working end-to-end prototype that demonstrates:

1. Video and telemetry upload
2. Video/telemetry synchronization
3. Adaptive keyframe selection
4. Blur, exposure and metadata quality analysis
5. Dynamic-object masking
6. Real 3D reconstruction from video
7. GPS-based georegistration and metric scale recovery
8. Point-cloud display
9. UAV trajectory display
10. Distance, height, area and coordinate measurement
11. Confidence/provenance visualization
12. Export and quality-report generation

Do not build a fake dashboard with a hardcoded 3D model. At least one pipeline path must generate an actual reconstruction from uploaded frames.

ARCHITECTURE

Build a modular monorepo:

/
  frontend/
  backend/
  reconstruction/
  sample_data/
  tests/
  docs/
  docker-compose.yml
  README.md
  .env.example

Frontend:
- React
- TypeScript
- Vite
- A clean operational UI
- CesiumJS if practical for georeferenced visualization
- Three.js fallback if Cesium integration blocks progress
- MapLibre for 2D maps if needed

Backend:
- Python 3.11
- FastAPI
- Pydantic
- SQLAlchemy
- SQLite initially, designed for PostgreSQL/PostGIS later
- Background-job abstraction
- Local worker initially; Redis/Celery adapter optional
- WebSocket or Server-Sent Events for progress updates

Reconstruction:
- OpenCV for frame processing
- FFmpeg/ffprobe for media inspection
- PyCOLMAP/COLMAP as the verified reconstruction engine
- Open3D for point-cloud cleanup, downsampling, normals and mesh generation
- pyproj for WGS84, ECEF and local ENU transformations
- Define an adapter interface for MASt3R-SLAM and VGGT
- The default system must still run if those AI models are unavailable
- Do not download large weights automatically during application startup

PIPELINE

Implement the following stages as separately testable modules:

1. INGESTION
- Accept MP4/MOV video.
- Accept telemetry CSV, JSON, SRT or a documented generic CSV format.
- Required telemetry fields: timestamp, latitude, longitude, altitude.
- Optional fields: roll, pitch, yaw, velocity, barometric_altitude, focal_length, fx, fy, cx, cy, distortion coefficients, RTK status and GPS accuracy.
- Use ffprobe to extract resolution, FPS, duration and codecs.
- Validate timestamps, coordinate ranges and missing fields.
- Store immutable originals and SHA-256 checksums.

2. SYNCHRONIZATION
- Map each extracted frame timestamp to interpolated telemetry.
- Interpolate coordinates through a local ENU frame.
- Use linear interpolation for positions and angle-aware interpolation for orientation.
- Record synchronization residual and confidence.
- Permit a configurable video-to-telemetry time offset.

3. FRAME QUALITY
- Calculate Laplacian blur score.
- Calculate brightness and clipped-dark/clipped-bright percentages.
- Calculate inter-frame motion and duplicate-frame score.
- Identify sudden exposure changes.
- Save metrics and mark rejected frames with reasons.
- Use configurable thresholds.

4. KEYFRAME SELECTION
- Combine temporal spacing, optical-flow magnitude, feature displacement, blur, exposure, GPS displacement and rotation change.
- Preserve sufficient overlap while avoiding duplicates.
- Produce a keyframe timeline.
- Provide fast, balanced and quality presets.

5. DYNAMIC MASKING
- Create a pluggable mask generator.
- First implementation may use a lightweight torchvision-supported model.
- Mask humans, vehicles and animals.
- Supplement semantic masks with optical-flow inconsistency where feasible.
- Dilate masks to avoid boundary contamination.
- Continue with a clear warning if the model is unavailable.

6. VERIFIED RECONSTRUCTION
- Use COLMAP or PyCOLMAP.
- Use sequential matching plus limited loop candidates.
- Share intrinsics across frames from the same video.
- Use supplied intrinsics when available; otherwise estimate a suitable model and report uncertainty.
- Exclude dynamic masked pixels from features if technically feasible.
- Generate sparse points, registered poses, reprojection errors, track lengths and per-point observation counts.
- Attempt dense reconstruction when supported.
- If dense reconstruction is unavailable, preserve the sparse output and issue a precise capability warning.

7. AI RECONSTRUCTION ADAPTER

Define a Python interface containing:
- is_available()
- prepare_inputs()
- reconstruct()
- get_camera_poses()
- get_depth_maps()
- get_point_cloud()
- get_uncertainty()

Provide adapters/stubs for MASt3R-SLAM and VGGT. Detect installation and provide exact setup instructions. Never report that a model ran when it did not. Fuse AI output only after alignment with verified geometry.

8. GEOREGISTRATION AND SCALE
- Convert WGS84 telemetry into local ENU.
- Associate GPS positions with reconstructed camera centres.
- Estimate a robust Sim(3) transform using RANSAC.
- Require at least three non-collinear GPS correspondences.
- Weight positions by GPS accuracy when available.
- Reject major outliers and calculate residuals.
- Transform cameras and clouds into metric ENU coordinates.
- Preserve the WGS84 origin.
- Support conversion of selected points back to WGS84.
- Distinguish relative, GPS-derived and RTK-derived scale.

9. FUSION AND CLEANUP
- Merge points only in a common metric coordinate frame.
- Use voxel downsampling and statistical/radius outlier removal.
- Calculate normals and retain confidence/provenance attributes.
- Colour points from source frames.
- Do not fill unseen areas as observed geometry.
- Store optional inferred completion as a separate layer.

10. MESH
- Provide optional Open3D Poisson or ball-pivoting meshing.
- Crop low-density artifacts.
- Preserve point-cloud output if meshing fails.
- Retain provenance labels.
- Export GLB or OBJ where feasible.

11. QUALITY AND UNCERTAINTY

Compute:
- Registered keyframe count and percentage
- Median and percentile reprojection error
- Mean feature-track length
- GPS alignment horizontal/vertical RMSE
- Point density
- Model bounding dimensions
- Geometry percentage in each confidence class
- Processing time per stage
- Video-duration-to-processing-time ratio

Confidence should consider reprojection error, track length, observations, triangulation angle, AI uncertainty, GPS residual, blur and exposure.

12. API

Implement endpoints resembling:

POST   /api/projects
GET    /api/projects
GET    /api/projects/{id}
POST   /api/projects/{id}/video
POST   /api/projects/{id}/telemetry
POST   /api/projects/{id}/process
GET    /api/jobs/{id}
GET    /api/jobs/{id}/events
GET    /api/projects/{id}/quality
GET    /api/projects/{id}/trajectory
GET    /api/projects/{id}/model
POST   /api/projects/{id}/measurements
GET    /api/projects/{id}/measurements
DELETE /api/projects/{id}/measurements/{measurement_id}
GET    /api/projects/{id}/exports
POST   /api/projects/{id}/exports

Use explicit schemas, validation and useful errors.

13. FRONTEND WORKFLOW

Create:

A. Mission dashboard
- Recent missions
- Processing status
- Quality summaries

B. New reconstruction wizard
- Video and telemetry upload
- Telemetry preview
- Optional camera intrinsics
- Processing preset
- Input validation

C. Processing monitor
- Stage progress
- Frame/keyframe counts
- Warnings and failures
- Honest elapsed and estimated progress

D. Analysis workspace
- Large 3D viewer
- Map and UAV trajectory
- Timeline/keyframe strip
- Layer toggles
- Confidence legend
- Point-size control
- Measurement tools
- Coordinates
- Quality and export panels

E. Report view
- Input summary
- Reconstruction statistics
- Accuracy/confidence
- Performance
- Known limitations
- JSON and printable HTML output

Use a professional, dark, high-contrast operational design. Avoid decorative animation. Support laptop displays and keyboard navigation. Do not claim official NTRO endorsement or add fake classified markings.

14. MEASUREMENTS

Implement:
- Point coordinate
- 3D polyline distance
- Vertical height difference
- Polygon area projected onto a best-fit plane
- Optional terrain profile

Record model ID, coordinates, units, confidence, inferred-geometry usage and timestamp. Warn when measurements intersect low-confidence or AI-assisted geometry.

15. EXPORTS

Support where practical:
- PLY with RGB and confidence
- LAS/LAZ
- GLB or OBJ
- GeoJSON trajectory and measurements
- CSV camera trajectory
- JSON quality report
- Printable HTML report

16. SECURITY AND OFFLINE OPERATION
- Validate MIME types and sizes.
- Sanitize filenames and prevent path traversal.
- Never execute uploaded data.
- Avoid network calls during processing.
- Bind locally by default.
- Do not log precise coordinates unnecessarily.
- Use safe, scoped mission deletion.
- Document air-gapped deployment.

17. TESTING

Add unit tests for:
- Telemetry parsing
- Timestamp interpolation
- WGS84/ECEF/ENU conversion
- Robust Sim(3) with outliers
- Frame-quality scoring
- Measurement calculations
- API validation
- Path sanitization

Add an integration test using a small, openly licensed or generated fixture containing an image sequence, synthetic telemetry and expected approximate scale. Tests must not download large model weights.

18. DOCUMENTATION

README must document:
- Implemented versus optional capabilities
- Scientific limitations
- Architecture
- Local and Docker setup
- CPU/GPU capability matrix
- Telemetry schema
- Camera calibration
- COLMAP installation
- Optional MASt3R-SLAM/VGGT configuration
- Demo procedure
- Troubleshooting
- Major dependency licences

NON-FUNCTIONAL REQUIREMENTS

- Preserve raw inputs.
- Make pipeline stages restartable.
- Cache intermediate outputs.
- Use structured logging.
- Return actionable errors.
- Never fabricate output.
- Use deterministic seeds where applicable.
- Keep units and coordinate frames explicit.
- Never mix geographic degrees with metric coordinates.
- Use type hints and docstrings.
- Prefer maintainable modules over unnecessary abstractions.

ACCEPTANCE CRITERIA

The prototype is accepted only if:

1. It starts with documented commands.
2. A user can create a mission and upload video and telemetry.
3. Metadata and quality metrics are calculated from real inputs.
4. Keyframes are extracted from uploaded video.
5. At least one real reconstruction engine can be invoked.
6. Generated camera poses and point cloud are stored and displayed.
7. GPS can align the reconstruction to metric ENU coordinates.
8. Distance and height measurement work.
9. Quality and confidence are displayed.
10. Results can be exported.
11. Missing GPU models cause warnings rather than crashes.
12. Tests pass.
13. No screen displays invented accuracy or fabricated results.

IMPLEMENTATION ORDER

Work incrementally and keep the application runnable after every phase.

Phase 1:
- Repository scaffold
- Database and schemas
- Upload wizard
- Telemetry parsing
- Frame extraction
- Frame-quality analysis
- Processing progress
- Tests

Phase 2:
- COLMAP adapter
- Reconstruction artifacts
- Point-cloud API
- 3D viewer
- Trajectory visualization

Phase 3:
- ENU conversion
- Robust Sim(3) alignment
- Metric measurements
- Quality report
- Exports

Phase 4:
- Dynamic masks
- Confidence classification
- AI adapter interface
- Optional MASt3R-SLAM or VGGT integration

Phase 5:
- Mesh generation
- UI refinement
- Docker/offline deployment
- Full testing and demonstration documentation

STARTING INSTRUCTION

Before writing code:

1. Inspect the repository and development environment.
2. Report detected OS, Python, Node, Docker, CUDA, GPU, FFmpeg and COLMAP availability.
3. Propose the final directory tree.
4. Identify dependencies with potentially restrictive licences.
5. State which capabilities work on CPU and which require an NVIDIA GPU.
6. Produce a concise implementation plan with acceptance tests.
7. Implement Phase 1 completely.
8. Run its tests and show the actual results.
9. Stop after Phase 1 and wait for review.

Do not attempt all phases in one uncontrolled generation.
```

## Working method

Use Claude phase by phase. After each phase, review the repository, test results, limitations, and unresolved issues before providing the next execution prompt. Do not accept UI-only mock behavior as a substitute for real reconstruction.
