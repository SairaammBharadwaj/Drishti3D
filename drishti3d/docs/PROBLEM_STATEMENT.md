# Problem statement: SIH26158

The requirement every result in this repository is measured against. The
official attachment is [`review_2026_09_22/sources/SIH26158_official_attachment.pdf`](review_2026_09_22/sources/SIH26158_official_attachment.pdf).

**ID:** SIH26158  
**Organization:** National Technical Research Organisation (NTRO)  
**Category:** Software  
**Theme:** Robotics and Drones  
**Title:** Single-Pass Drone Video to Accurate 3D Model Generation System

The objective is to develop an AI-enabled system that converts a single-pass UAV video, GPS coordinates, and flight metadata into a georeferenced and metrically accurate 3D representation. Desired outputs include terrain, structures, facades, rooftops, roads, infrastructure, vegetation, obstacles, point clouds, and textured meshes suitable for measurement, visualization, and analysis.

## How the team evaluates against it

This table and the targets under it are the team's framework, written at the
start of the project; they are not part of the official statement. Current
measured results, with their scope, are in [BENCHMARK.md](BENCHMARK.md) and
[VIDEO_ACCURACY_MARS_LVIG.md](VIDEO_ACCURACY_MARS_LVIG.md).

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

### Targets set at the start

- With RTK/PPK, target decimetre or better georegistration, subject to camera, altitude, and flight geometry.
- With ordinary GPS, explicitly report GPS-limited absolute accuracy, which may be metre-level.
- Target below 3–5% relative dimensional error on well-observed surfaces.
- Target a fast preview close to video duration; allow refined reconstruction to take several times the video duration.
- Never claim centimetre accuracy without measured ground-truth evidence.
