# Accuracy, terrain analytics, exports and replay

What was added on 4 October 2026 to close the gaps in
[`sih_submission_2026/COMPETITOR_AUDIT_VERIFIED_ACTION_PLAN.md`](sih_submission_2026/COMPETITOR_AUDIT_VERIFIED_ACTION_PLAN.md),
how to use each part, and what each one does not establish. The decision is
DEC-048 in the root [`DECISIONS.md`](../../DECISIONS.md).

## Absolute accuracy against surveyed points

`drishti_recon.accuracy`, `POST /api/projects/{id}/accuracy` (JSON) and
`/accuracy/csv` (upload), `GET /api/projects/{id}/accuracy`, and the
*Absolute accuracy* panel in the workspace.

A surveyed point is a **GCP** (may be used to correct the model) or a
**checkpoint** (held back to judge it). The report has one block per question,
and each says whether it is independent:

| Block | What it is | Independent |
|---|---|---|
| `raw` | the model as reconstructed, against every surveyed point | yes |
| `correction` | translation for 1–2 GCPs; 7-parameter similarity for 3+ that are not collinear | — |
| `fit_residuals` | residuals at the GCPs after the fit | **no** |
| `leave_one_out` | each GCP scored by a correction fitted without it | **no** (cross-validated) |
| `checkpoints` | the corrected model against points the fit never saw | yes |

Statistics: per-axis RMSE, horizontal and 3-D RMSE, CE90 = 1.5175 × RMSE_r,
LE90 = 1.6449 × RMSE_U, and empirical 90th percentiles from ten points. Below
30 independent checkpoints the report says the sample is too small for an
ASPRS (2014) class. When every point is a GCP, the headline is the raw figure
and a warning says the corrected model has no independent number.

CSV columns: `id, role` (`gcp` or `check`), `model_e, model_n, model_u` (the
point as picked in the viewer, local ENU metres), and the survey as one of
`lat, lon, h`; `easting, northing, h, epsg`; or `e, n, u` (already in the
mission frame). Survey heights are declared ellipsoidal or above sea level; a
height on a datum the mission cannot be compared with is refused, and a
sea-level conversion without the geoid grid is refused too.

**Not established by this:** accuracy on any mission without surveyed points.
The synthetic tests prove the arithmetic and the labels, not field accuracy.

## RTK / PPK solutions (RTKLIB `.pos`)

`drishti_recon.rtk`, accepted wherever telemetry is (`.pos` upload).

- Epochs as `yyyy/mm/dd hh:mm:ss.sss` or GPS `week tow`, in GPST, UTC or JST;
  positions in degrees, d m s, or ECEF.
- GPS time is converted to UTC with the leap-second table (18 s since 2017).
  Sample timestamps are seconds from the first epoch, like other telemetry;
  UTC, GPS week and time of week are kept per sample.
- `Q` maps 1 fix → `RTK_FIXED`, 2 float → `RTK_FLOAT`, 3 SBAS, 4 DGPS,
  5 single, 6 PPP. The original `Q`, `ns`, standard deviations, `age` and
  `ratio` are kept. (Q=4 is DGPS here, not "fixed" as in the CSV convention.)
- `height=WGS84/ellipsoidal` sets the vertical datum to ellipsoidal,
  `/geodetic` to above sea level; a header that says neither leaves it
  unknown, with a warning.
- Malformed rows are reported by line number and skipped.

## Terrain analytics

`drishti_recon.terrain`, `POST /api/projects/{id}/terrain/{volume,profile,slope,los}`
(points in viewer ENU), and the *Terrain analysis* tools in the workspace.
They read `rasters.npz` — observed points only — and refuse below 80% observed
coverage.

- **Volume**: cut, fill and net above a base (plane through the polygon's
  edge, lowest point inside, or a fixed height), on the **mean** height per
  cell. The DSM's highest point is biased up by noise: on a flat test surface
  with 0.1 m noise and ~25 points per 0.5 m cell, the DSM gives 50.2 m³ of
  phantom volume over 256 m², the mean 0.06 m³. Sigma is given as
  a range between independent cells and fully correlated cells, uncalibrated.
- **Profile**: mean height along a line; unobserved samples are `null` and
  drawn as breaks.
- **Slope**: central differences only where every neighbour was observed.
- **Line of sight**: over the **DSM** (the top of whatever stands there).
  `blocked` names the first clear obstruction; a ray that clears every
  observed cell but crosses unobserved ones, or passes within 2σ of the
  surface, is `unknown`, never `visible`. The viewer stands the observer and
  target on the picked points.

## Mesh formats

Every meshed run now writes `mesh.obj` directly (vertex colours, ENU metres,
the origin in a comment) and `mesh.fbx` through the `assimp` command-line tool
when it is installed. `mesh_formats.json` records which, and why FBX is absent
when it is ("assimp unavailable: install …"). The mesh is a Poisson surface
interpolated over observed points: **display geometry, never measured**.

## Photo-textured hero mesh (OpenMVS)

`scripts/texture_hero.py <artifacts> --colmap <workspace> --openmvs <bin>`
runs OpenMVS on the COLMAP workspace a `--engine colmap` run kept and moves
the textured OBJ into the stored ENU frame with the run's own recorded
transform. It first checks that transform puts COLMAP's camera centres on the
solved cameras (≤ 5 cm RMS) and refuses otherwise. Outputs:
`textured_mesh.obj/.mtl`, textures, `textured_mesh.zip`, and
`textured_mesh.json` (`display_only: true`). Not yet run on a hero mission:
OpenMVS was not available where this was written.

## Heights above sea level

`GET /api/system/geoid` reports whether the EGM2008 grid is installed.
`scripts/install_geoid.py` downloads it (or copies it with `--from` on an
offline laptop), verifies its SHA-256, and checks geoid heights at the
showcase sites. Without it a picked point shows ellipsoidal height and an
explicit "geoid grid not installed" note; it never shows the ellipsoidal
height as sea level.

## Evidence package

`scripts/evidence_package.py <artifacts> [--video <file>] [--run-tests "<cmd>"]`
writes `evidence_package.json` and `.md`: input video hash (re-hashed and
matched against the run's manifest), machine and GPU, software versions,
stage and end-to-end timings, SHA-256 of every output, CRS, vertical datum,
placement source, truth source and accuracy policy, and optionally a test
command's result. Missing evidence is stated as missing.

## Video ↔ 3-D replay

`GET /api/projects/{id}/replay` returns the solved cameras on the video clock,
converted from OpenCV (x right, y down, z forward, world→camera) to Three.js
(camera→world, looking down −Z, +Y up). The workspace plays the source video,
interpolates the camera at the presented frame (linear position, slerp
rotation), draws it as a frustum or flies the view with it, and shows:

- **Synced**: between keyframes at most 2 s apart;
- **Gap — interpolated**: between keyframes further apart;
- **No solved camera here**: outside the solved span.

`drishti_recon.replay` is the tested reference; `frontend/src/replayMath.ts`
mirrors it (`npm test`).

## Preview tier

`preset: "preview"` is a real reconstruction — the same sparse solve,
georegistration, uncertainty and rasters — on at most 40 keyframes from 160
frames at 960 px, without dense stereo, mesh, coverage or hole fill. The
report carries `tier.preview: true` and the workspace says so. With
`then_full: true` the balanced run is queued when the preview finishes and
replaces it; the wizard's *Preview first* does this. On the 5-second
synthetic clip on a 4-core CPU machine: preview 159 s (36 keyframes), full
283 s (47 keyframes). Not yet timed on a 10-minute flight or the demo laptop.

## Not done

- **Road / paved class.** Not added: there is no labelled road data to
  validate one. Roads stay in *ground*, and the land-cover caption and
  `rasters.json` say so.
- **IMU attitude prior for straight-line flights (audit B2).** Not started. The
  current system detects the straight-line degeneracy and refuses to hide it;
  adding a prior requires a real flight with trustworthy body attitude and an
  independent score, so it must not be marked complete from a synthetic run.
- **P2 research** — GLOMAP/global SfM, NVDEC decode, stage resume, trained
  3D Gaussian splats, Cesium/3D Tiles, live RTSP and learned semantic models
  remain unattempted. This machine has no `glomap`, `torch`, `gsplat`, Cesium
  runtime or OpenMVS installation; each item remains gated on the required
  tooling and a real-flight A/B result.

## Local completion record — 4 October 2026

The EGM2008 grid was installed with `scripts/install_geoid.py` and passed the
known-point checks: Zurich `N=+47.715 m`, Austin `N=-26.900 m`, and Hong Kong
`N=-2.199 m`. The grid is now usable on this machine; the offline demo laptop
still needs the same installer/check.

An evidence package was generated for the recorded DJI_1003 performance run:
`data/runs/dji_1003__perf_final/artifacts/evidence_package.json` and `.md`.
It records hashes, machine/software details, timing, georeference, output
hashes and the accuracy policy. It has no input-video match because the source
video is not present beside that historical run, so it must not be presented as
a freshly re-run hero-mission package.
