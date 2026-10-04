# SIH26158 competitor audit — verified Drishti3D status and completion plan

**Verification date:** 4 October 2026  
**Repository checked:** `/home/naveen/Drishti3D/drishti3d`  
**Audit supplied by team:** 3 October 2026  
**Attached upgrade files checked:** `rasters.py`, `accuracy.py`, `test_upgrades.py`

## 1. What was actually verified

This report distinguishes four states:

- **Complete:** the capability is in the repository, exposed through the product or pipeline where applicable, and covered by a relevant test or recorded evidence.
- **Partial:** some implementation exists, but it is standalone, optional, not wired into the product, incomplete against the PS wording, or not sufficiently validated.
- **Missing:** no usable implementation was found in the current product.
- **Evidence-only:** a benchmark, README or demo claim exists, but it is not itself an implementation.

The three downloaded files were not counted as finished product features merely because they exist. Running the system Python failed because SciPy was unavailable. Running them with `drishti3d/.venv/bin/python` passed the synthetic test:

```
rasters ok: ['class.tif', 'dsm.tif', 'dtm.tif', 'ortho.tif'] volume 79.42 m3 (truth 78.54)
accuracy ok: raw RMSE_H 0.90 / V 0.43 -> GCP-corrected LOO RMSE_H 0.26 / V 0.16
```

The attached files have different SHA-256 hashes from the repository's integrated raster module. They are therefore an **upgrade prototype/reference**, not a proof that the product already contains those exact changes. The synthetic test also does not prove accuracy on a real flight.

## 2. Count of the 29 feature rows in the supplied matrix

| Status | Count | Meaning |
|---|---:|---|
| Complete | **11** | Implemented and supported by code/evidence at the stated scope |
| Partial | **11** | A meaningful foundation exists, but integration, coverage or validation is incomplete |
| Missing | **7** | Not implemented as a usable product capability |
| **Total** | **29** | The A–E rows in the supplied feature matrix |

This is a conservative product count. It does not convert competitor README claims into facts and does not treat a planned command, a UI placeholder, or a synthetic-only result as complete.

## 3. Verified feature-by-feature status

### A. PS compliance and outputs

| # | Audit row | Status | Verification and remaining work |
|---:|---|---|---|
| A1 | Photo-textured mesh | **Missing** | Current mesh is Poisson/Open3D geometry with vertex colours. No OpenMVS texture/UV/material stage is wired. Pre-bake one hero textured OBJ for the demo, clearly labelled display-only. |
| A2 | Georeferenced LAS/PLY | **Complete** | Existing export path writes LAS/PLY, CRS/georeference metadata, provenance and uncertainty fields. Re-run an export test on the exact hero mission before presenting it. |
| A3 | OBJ/FBX | **Partial** | OBJ may be produced through the existing Open3D exporter, but there is no explicit, tested FBX path. Add an explicit OBJ test and optional `assimp export` FBX conversion with a clear “assimp unavailable” status. |
| A4 | DSM/DTM GeoTIFF | **Complete** | Repository `rasters.py` already builds observed-only DSM/DTM GeoTIFF products and previews. Confirm `rasterio` is installed in the demo environment and preserve NoData holes. |
| A5 | Orthomosaic | **Partial** | Current product is a true-ortho-like top-point RGB raster from the cloud, not a camera-projected, seam-corrected orthomosaic. Either call it “dense-cloud orthophoto” or add OpenMVS orthographic projection and document the distinction. |
| A6 | Terrain/building/road/vegetation classes | **Partial** | Rule-based ground/building/vegetation classification exists and is tested; road class and field validation are absent. Add road/paved-surface logic or a gated semantic model, then publish a confusion matrix on labelled data. |
| A7 | Heights above sea level (EGM2008) | **Partial** | `position.py` implements EGM2008 conversion and refuses a silent ballpark transform. The geoid grid is an environment prerequisite; package/check it on the demo laptop and show an explicit unavailable state when absent. |
| A8 | Viewer with measurement | **Complete** | Measurement endpoints/UI, uncertainty, provenance and refusal behaviour exist. This is complete as a viewer capability; acceptance-grade calibration still requires the checkpoint plan in section 6. |

### B. Accuracy and trust

| # | Audit row | Status | Verification and remaining work |
|---:|---|---|---|
| B1 | GNSS Sim(3) and degeneracy handling | **Complete** | Existing georegistration includes uncertainty-weighted fitting and conditioning/degeneracy tests. Keep the yaw-only/straight-line limitation visible in the report rather than claiming all attitude cases are solved. |
| B2 | IMU attitude for straight lines | **Partial** | Sensors/telemetry are parsed and weak geometry can be detected, but an IMU-based correction is not a completed georegistration mode. Add a gated attitude prior, compare against the current detector, and score on a straight-line flight. |
| B3 | GCP checkpoints and leave-one-out RMSE | **Partial** | Downloaded `accuracy.py` implements this and passes a synthetic test, but it is not integrated into the reconstruction API/report. Add a versioned `accuracy` module, checkpoint import, LOO report, and a UI/API endpoint. Never report the same GCPs used for fitting as independent accuracy. |
| B4 | RTK/PPK file import | **Partial** | RTK status/telemetry support exists. A robust RTKLIB `.pos` importer with GPS-time conversion and Q-code mapping was not found. Implement it, add parser fixtures, and preserve the original quality/status fields. |
| B5 | Accuracy against independent truth | **Complete at evidence scope** | Repository records same-flight LiDAR and UseGeo evaluations, with explicit caveats separating independent accuracy from GNSS residuals. This is not a universal guarantee: repeat on a second calibrated site before generalising. |
| B6 | Provenance, propagated sigma and refusal | **Complete** | Point provenance, uncertainty and fail-closed measurement/question behaviour are implemented and tested. Keep inferred/fill geometry separate from observed geometry in every export and demo. |
| B7 | Per-point frame and pixel lineage | **Complete** | Observation/lineage structures and tests exist. Include one visible lineage drill-down in the final demo so the claim is auditable. |

### C. Speed and operations

| # | Audit row | Status | Verification and remaining work |
|---:|---|---|---|
| C1 | Under 15 minutes per 10-minute video | **Complete at recorded scope** | README/evidence records 12.2 minutes for an 11:18 native 1080p DJI run on an RTX 5060. Re-run once on the exact demo machine and show stage timings; do not generalise to every GPU/video. |
| C2 | GPU decode/NVDEC | **Missing** | No NVDEC path was found. Do not spend deadline time here unless profiling proves decode is material; recorded timings say dense stereo dominates. |
| C3 | Global SfM/GLOMAP | **Missing** | No integrated global-mapping option was found. Treat as post-round research work and re-score scale/straight-line cases before enabling by default. |
| C4 | Fast preview tier | **Missing** | A capped browser preview is not the same as a fast reconstruction tier. Add a documented sparse/40-keyframe preview preset that chains to the balanced run. |
| C5 | Live stream input/stage resume | **Missing** | No live RTSP and no hash-keyed stage cache/resume workflow was found. Add only after the deadline-critical deliverables are stable. |

### D. Viewer and analytical features

| # | Audit row | Status | Verification and remaining work |
|---:|---|---|---|
| D1 | Volume/profile/slope/line of sight | **Partial** | The downloaded `rasters.py` contains useful prototype algorithms, but matching product endpoints/UI were not found. Port them into the repository module, enforce observed-coverage/unknown rules, add API contracts and browser tests. |
| D2 | MGRS/UTM readout | **Complete** | `position.py`, `/point_info`, and `PositionCard` provide UTM/MGRS and height readouts. Verify the exact zone/example shown in the demo against the mission CRS. |
| D3 | Trained 3D Gaussian Splatting | **Missing** | The repository has Gaussian initialisation/render-style code, not a trained gsplat model and production viewer. A pre-baked splat is a visual enhancement, not measured geometry. |
| D4 | Video ↔ 3D sync/flight replay | **Partial** | Camera/trajectory data and prototype views exist, but a verified timestamp-synchronised playback mode was not found. Implement nearest-keyframe interpolation, OpenCV-to-Three.js transform conversion, pause/scrub tests and a visible sync indicator. |
| D5 | Globe/3D Tiles | **Missing** | No Cesium/3D-Tiles delivery path was found. Add only if time remains after evidence and demo reliability. |
| D6 | Labelled completion of unseen surfaces | **Partial** | Hole/fill concepts and provenance-aware previews exist, but there is no complete labelled-surface product workflow. Keep inferred surfaces in a separate layer, mark them visually, and never permit them to answer measured questions. |

### E. Engineering evidence

| # | Audit row | Status | Verification and remaining work |
|---:|---|---|---|
| E1 | Tests | **Complete** | The repository contains a broad test suite (102 test files at verification) covering reconstruction, exports, API, lineage, uncertainty and rasters. Run the focused suite below before submission and record the result. |
| E2 | Real flights in published results | **Partial** | Real-flight/LiDAR evidence is documented internally. It is not equivalent to a peer-reviewed or independently audited certification, and the audit's “six flights” count should be backed by a dated evidence index. |
| E3 | Licence-clean default stack | **Complete at default-stack scope** | The repository has a model/licence manifest and gates non-commercial optional models. Package the actual demo environment and run an offline licence/dependency check; do not claim optional NC/AGPL components are part of the clean default. |

## 4. What the three downloaded Python files contribute

### `rasters.py` (221 lines)

Useful standalone reference: rasterisation, DSM/DTM, simple classes, volume/profile/line-of-sight and GeoTIFF writing. It must not replace the repository's current raster module blindly: the repository version already has its own `Grid`, resolution policy, provenance/uncertainty fields, previews and pipeline artefact contract. Port missing algorithms deliberately and preserve those contracts.

### `accuracy.py` (136 lines)

Useful standalone reference: E/N/U, horizontal/3-D RMSE, CE90/LE90, GCP correction, leave-one-out logic, `.pos` parsing and EGM2008 helper. It is not currently the product's accuracy service. Integrate it behind stable dataclasses and API schemas, then test with real checkpoint files and an independent hold-out set.

### `test_upgrades.py` (53 lines)

This is a synthetic smoke test, not an end-to-end product test. It passes only under the project virtual environment because SciPy is required. Keep it as a unit test, add it to CI, and add integration tests that run the actual pipeline and API against a small fixture.

## 5. Required implementation prompt for the team

> **Implement the remaining SIH26158 Drishti3D capability gap without weakening measurement honesty. Work in `/home/naveen/Drishti3D/drishti3d`. Do not overwrite the existing raster/export contracts with the downloaded prototypes. First integrate only the missing, tested behaviour; then expose it through the pipeline, API, viewer and report. Every generated field must carry source, CRS/vertical datum, observed-versus-inferred state, uncertainty and an evidence reference. A feature is not complete until it has a focused test, an integration test, a demo artefact and a documented limitation.**
>
> **P0 — submission-critical (complete and verify):**
> 1. Add `drishti_recon.accuracy` from the downloaded reference, adapted to repository dataclasses. Implement checkpoint import, raw RMSE (E/N/U/H/3-D), CE90/LE90, translation-only correction for 1–2 GCPs, 7-parameter correction for 3+, and honest leave-one-out scoring. Add API/report output and a visible “not independent if used for fit” label.
> 2. Add RTKLIB `.pos` parsing with GPS-time/UTC handling and Q-code mapping. Add fixtures for RTK fixed/float/DGPS/single and malformed rows.
> 3. Verify the existing DSM/DTM/orthophoto/sigma/class outputs on one hero mission. Preserve empty cells as NoData; use mean-Z for volume/profile, not max-Z DSM. Add explicit output names, CRS, vertical datum and observed/inferred metadata.
> 4. Add explicit OBJ export testing and optional FBX conversion through `assimp`; report a clear unavailable state if the executable is absent.
> 5. Implement volume/profile/slope/line-of-sight endpoints and viewer controls from the prototype algorithms. Refuse below the coverage threshold and return `unknown` where the ray crosses unobserved cells.
> 6. Put the EGM2008 grid on the demo machine, test a known coordinate, and demonstrate refusal when the grid is missing instead of silently returning ellipsoidal height.
> 7. Produce one evidence package: exact input video hash, hardware, stage timings, output hashes, CRS, truth source, accuracy policy and test command/result.
>
> **P1 — visual/demo upgrade (do not mix display geometry with measurements):**
> 8. Run OpenMVS on one hero dataset to make a photo-textured OBJ. Transform it from COLMAP coordinates into stored ENU, label it “display only”, and keep all measurements on observed points.
> 9. Implement the video/3-D timestamp sync with trajectory keyframes, correct OpenCV-to-Three.js axes, scrub/pause tests and a visible sync state.
> 10. Add a road/paved class only after labelled validation; otherwise keep the current class names and disclose that they are rule-based.
> 11. Add a real preview reconstruction preset (not merely a capped point display), then chain it to the balanced run.
>
> **P2 — post-round research:**
> 12. Benchmark GLOMAP/global SfM, NVDEC, stage resume, trained 3DGS, Cesium/3D Tiles, live RTSP and semantic models separately. Each must be A/B scored for accuracy, coverage, runtime, memory and licence before becoming default.
>
> **Quality gate:** run focused tests, then the full suite; process one 10-minute real video; compare outputs against the same truth policy; inspect the viewer at all supported layers; and reject any claim whose evidence source, datum or independence is unclear.

## 6. Verification commands and acceptance criteria

Run from the repository:

```bash
cd /home/naveen/Drishti3D/drishti3d
.venv/bin/python /home/naveen/Downloads/test_upgrades.py
.venv/bin/pytest -q tests/test_rasters.py tests/test_position.py tests/test_vertical_datum.py \
  tests/test_export_georeference.py tests/test_lineage.py tests/test_measurement_contract.py \
  tests/test_read_only.py tests/test_integration.py
.venv/bin/pytest -q
```

**Run recorded on 4 October 2026:** the focused command reached **83 passed, 2 failed**. Both failures are vertical-reference assertions (`tests/test_rasters.py::test_geotiffs_carry_crs_nodata_mask_and_palette` and `tests/test_export_georeference.py::test_sidecar_places_a_local_file`): the tests require the tag to contain `ellipsoidal`, while the current implementation returns the more cautious text that telemetry does not state the altitude datum. Resolve this contract deliberately before submission—either provide a known ellipsoidal datum for those fixtures or update the assertions/fixture metadata to accept and test the explicit unknown-datum state. Do not weaken the fail-closed vertical-datum behaviour just to make the string assertion pass.

Acceptance is met only when:

1. all focused tests and the full suite pass;
2. the hero mission produces LAS/PLY/OBJ, DSM, DTM, orthophoto, sigma and class artefacts with metadata;
3. a picked point shows ENU, lat/lon, UTM, MGRS, ellipsoidal height, MSL height or an explicit geoid-unavailable refusal;
4. at least one measurement has visible uncertainty/provenance and one deliberately unobservable query refuses;
5. GCP correction is reported with leave-one-out numbers, never as independent accuracy when the same points fit the model;
6. the demo timing is measured end-to-end on the actual laptop; and
7. the textured/splat view, if shown, is labelled visual/display geometry and cannot silently feed measurement answers.

## 7. Claims that must not be made yet

- Do not say every PS output format is complete: FBX, textured mesh, globe/tiles and several analytics remain unfinished.
- Do not call the synthetic `test_upgrades.py` result field accuracy.
- Do not call GNSS alignment residual an independent accuracy result.
- Do not claim ASPRS-style acceptance until at least 30 surveyed checkpoints and the stated reporting policy are satisfied.
- Do not present inferred or hole-filled geometry as observed measurement evidence.
- Do not claim universal `<1 m` accuracy or universal `<15 min` runtime; state the exact mission, hardware, truth source and processing preset.

**Recommended submission position:** lead with the completed evidence features (lineage, uncertainty, refusal, same-flight LiDAR evidence, measured runtime and georeferenced exports), show the textured hero asset as a labelled visual layer, and describe the partial/missing checklist items as the concrete next sprint above.

## 8. Implementation status — 4 October 2026 (later)

Work on branch `repo-cleanup-and-showcase`; decision DEC-048; user guide
[`docs/ANALYTICS_AND_ACCURACY.md`](../ANALYTICS_AND_ACCURACY.md).

### P0

| # | Item | Status | Where |
|---:|---|---|---|
| 1 | Checkpoint/GCP accuracy, CE90/LE90, translation / 7-parameter correction, leave-one-out, API + UI, "not independent" labels | **Done** | `drishti_recon/accuracy.py`, `POST/GET /accuracy`, Absolute accuracy panel; `tests/test_accuracy.py`, `tests/test_analysis_api.py` |
| 2 | RTKLIB `.pos` with GPS time/UTC and Q codes; fixed/float/SBAS/DGPS/single/malformed fixtures | **Done** | `drishti_recon/rtk.py`; `tests/test_rtk_pos.py`, `tests/fixtures/rtk/` |
| 3 | Raster outputs: NoData kept, mean-Z for volume/profile, names, CRS, datum, observed/inferred metadata | **Done in code; hero mission not re-run here** | `rasters.py` (unchanged contract), `terrain.py` |
| 4 | Explicit OBJ test; FBX through assimp with an unavailable state | **Done** | `exports.export_mesh_formats`; `tests/test_mesh_formats.py` |
| 5 | Volume/profile/slope/line-of-sight endpoints and viewer controls; refusal below coverage; `unknown` over unobserved cells | **Done** | `drishti_recon/terrain.py`, `/terrain/*`, Terrain analysis tools; `tests/test_terrain.py` |
| 6 | EGM2008 on the demo machine, known-point check, refusal when missing | **Tooling done; grid must be installed on the demo laptop** | `scripts/install_geoid.py`, `GET /api/system/geoid`; refusal tested. The download is blocked in the build sandbox |
| 7 | Evidence package | **Tool done; run it on the hero mission on the demo laptop** | `scripts/evidence_package.py`; `tests/test_evidence_package.py` |

### P1

| # | Item | Status |
|---:|---|---|
| 8 | OpenMVS textured OBJ in ENU, display only | **Tool done, not yet run** (`scripts/texture_hero.py`; transform check refuses a mismatched workspace). Needs OpenMVS and a kept COLMAP workspace |
| 9 | Video ↔ 3-D sync: keyframe interpolation, OpenCV→Three.js, scrub/pause tests, sync indicator | **Done** (`drishti_recon/replay.py`, `/replay`, `VideoSync.tsx`; `tests/test_replay.py`, `npm test`; checked in Chromium) |
| 10 | Road class only after labelled validation | **Not added, by design**; disclosed in `rasters.json` and the land-cover caption |
| 11 | Real preview preset chained to the balanced run | **Done** (`preset=preview`, `then_full`; `tests/test_preview_tier.py`; run end to end) |

### P2

Not attempted: GLOMAP, NVDEC, stage resume, trained 3DGS, Cesium/3D Tiles,
live RTSP, semantic models. Each needs a GPU and real flights for its A/B.

### Local completion update — 4 October 2026

The EGM2008 grid has now been installed and verified on the development
machine using `scripts/install_geoid.py` (Zurich, Austin and Hong Kong known
points all passed). An evidence package was also generated for the recorded
`dji_1003__perf_final` artefacts. It records the historical run faithfully but
has no matching source video beside the run, so it is not a replacement for a
fresh hero-laptop capture.

The remaining items are not safely finishable in this environment: OpenMVS,
GLOMAP, NVDEC, trained 3DGS/Cesium stacks and a GPU are absent. The IMU prior
and road class also require an independent real-flight/labelled validation set;
the current fail-closed degeneracy detection and ground classification remain
the honest defaults.

### Section 6 test failures

The two vertical-reference failures are resolved without weakening the
fail-closed behaviour: the fixtures that assert "ellipsoidal" now declare an
ellipsoidal datum, and two new tests assert the unknown-datum wording.

### Revised count of the 29 rows

| Status | Before | Now | Rows that moved |
|---|---:|---:|---|
| Complete | 11 | **17** | A3 OBJ/FBX, B3 GCP/LOO, B4 RTK/PPK, C4 preview tier, D1 analytics, D4 video sync |
| Partial | 11 | **7** | A1 textured mesh (missing → partial: tool, no hero run) |
| Missing | 7 | **5** | C2 NVDEC, C3 GLOMAP, C5 RTSP/resume, D3 trained 3DGS, D5 globe/3D Tiles |

Still partial: A1 textured mesh, A5 orthomosaic (still a dense-cloud
orthophoto), A6 classes (no road class), A7 EGM2008 (grid not yet on the demo
machine), B2 IMU attitude prior, D6 labelled completion, E2 dated evidence
index. "Complete" for B3 means implemented, exposed and tested on synthetic
truth: no field checkpoints have been scored, so section 7's limits on
accuracy claims still apply in full.
