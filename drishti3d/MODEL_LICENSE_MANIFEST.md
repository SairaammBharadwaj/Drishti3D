# Model, data and dependency licence manifest

Asked for by the Intelligence Edition V3.1 plan (§75) and by `NEXT_STEPS.md`
("Licence manifest ... nothing tracks this today"). Code, weights and datasets
are listed separately because their terms differ: a permissive codebase can
ship non-commercial weights.

**Status column:** *verified* = read at the source on the date given;
*recorded* = taken from an earlier note in this repository; *to verify* =
believed correct but not yet checked at the source. Nothing here is legal
advice; review before any field or commercial distribution.

## Datasets used for validation

| Dataset | Used for | Licence | Consequence | Status |
|---|---|---|---|---|
| MARS-LVIG (HKU) — HKisland01/02/03, L1 LiDAR | same-flight video accuracy (DEC-042) | CC BY-NC-SA 4.0, academic use; commercial use by contacting the lab | numbers may be published with attribution; derived clouds may not ship in a commercial product | verified 2026-09-25, mars.hku.hk |
| UseGeo (3DOM-FBK) | still-image accuracy (DEC-036..041) | CC BY-NC-SA 4.0 | as above | recorded (NEXT_STEPS.md) |
| AirLock-WACV2026 (DJI_1001–1007) | native-video timing | CC BY 4.0 (basemaps under their providers' terms) | attribution required | verified 2026-09-24, Hugging Face card |
| TxGIO StratMap 2021 Bexar & Travis LiDAR | considered as Austin reference; rejected (4.5-year gap) | CC0 1.0 | none | verified 2026-09-24, api.tnris.org |
| USGS 3DEP TX Central 2017 LiDAR | one tile inspected | US public domain | none | to verify |
| UAVScenes | not used (reference is photogrammetric, not independent) | CC BY-NC-SA 4.0 | — | verified 2026-09-24, repository README |

## Learned models (all optional; the default pipeline runs without them)

| Model | Role here | Licence | Consequence | Status |
|---|---|---|---|---|
| MASt3R / DUSt3R weights | research adapter (`dense3d.py`) | CC BY-NC-SA 4.0 | research only | recorded (docs/OPTIONAL_MODELS.md) |
| VGGT | research adapter (`vggt_engine.py`) | custom; commercial allowance excludes military applications | unsuitable as a default for this stakeholder | recorded (NEXT_STEPS.md) |
| Depth Anything V2 | depth prior (`depth_prior.py`) | depends on checkpoint size | check which checkpoint is configured | to verify |
| MapAnything (Apache variant) | proposed in V3.1 §19 | Apache-2.0 per the V3.1 plan | not integrated | to verify |
| Depth Anything 3 | proposed in V3.1 §20 | Apache-2.0 codebase per the V3.1 plan | not integrated | to verify |

## Core dependencies

| Dependency | Role | Licence | Status |
|---|---|---|---|
| COLMAP / pycolmap | SfM, dense stereo, fusion | BSD-3-Clause | to verify |
| OpenCV | decoding, features, undistortion | Apache-2.0 (4.5 and later) | to verify |
| Open3D | fusion, normals, mesh | MIT | to verify |
| NumPy, SciPy | numerics | BSD-3-Clause | to verify |
| pyproj | coordinate systems | MIT | to verify |
| laspy / lazrs | LAS/LAZ I/O | BSD-2-Clause / MIT-or-Apache | to verify |
| rosbags | MARS-LVIG bag reading (scripts only) | Apache-2.0 | to verify |
| FastAPI, React, Three.js | API and viewer | MIT | to verify |

## Rules

- A new model, checkpoint or dataset gets a row here in the same change that
  adds it.
- A *to verify* row is checked at the source before any distribution outside
  the team, and its status updated with the date.
- Non-commercial (NC) material may be used to measure and publish accuracy, but
  data derived from it (clouds, meshes, trained weights) must not be shipped in
  a product without the owner's permission.
