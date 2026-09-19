# AGZ single-pass: OpenCV engine vs COLMAP engine

_Run 2026-09-19. Every number below came from
`python scripts/run_mission.py` on the inputs and commit recorded here._

This is the first measurement of this repository's reconstruction on a **real
single-pass aerial video with real consumer-grade GNSS**. Earlier benchmarks in
`docs/benchmarks/` are synthetic or photo-survey; their conclusions do not
transfer and are not repeated here.

## Provenance

| Field | Value |
|---|---|
| Commit at run time | `9a55723a1096` (working tree contained the uncommitted changes of 2026-09-19) |
| Platform | Linux 7.2.6-arch2-1 x86_64, glibc 2.44 |
| Python | 3.12.14 |
| NumPy / OpenCV / PyCOLMAP | 2.5.2 / 5.0.0 / 4.2.0 |
| GPU | RTX 5060 Laptop, 8151 MiB (unused: both engines are CPU) |
| Command | `scripts/run_mission.py --mission agz_dense_pass --max-frames 184 --engine {opencv,colmap}` |

## Input

Mission `agz_dense_pass`, built by `scripts/build_agz_mission.py` from
`drishti3d/data/real_drone/agz_dense` (Zurich Urban MAV, frames 57211–62701,
stride 30).

| Property | Value |
|---|---|
| Frames | 184 |
| Duration | 184.4 s |
| Path length / net displacement | 233.1 m / 201.9 m |
| Median frame-to-frame baseline | 1.17 m |
| Altitude (MSL) | 449.4 – 474.7 m |
| GNSS fix type | 3 (3D fix) throughout |
| GNSS median `eph` | 9.43 m |
| `video.mp4` sha256 | `3b9bd9754db9c188…` |
| `telemetry.csv` sha256 | `270dc380a43b117d…` |

Camera: AGZ factory calibration, `fx=893.4 fy=898.3 cx=951.1 cy=555.1`,
`k1=-0.2805 k2=0.1158 p1=-0.00098 p2=0.00016 k3=-0.0270`. Distortion was
corrected once, up front, in both runs. Both runs used `e_ransac_px=2.0` and
`proc_max_width=1280`.

## Reference

`datasets/truth/agz_dense_pass/reference_camera_positions.csv` — 184 camera
positions the AGZ authors published in `GroundTruthAGL.csv`, EPSG:32632.

**These are not independent survey truth.** They were produced with Pix4D over
the full image set, using loop closures this single pass does not have, and the
publisher states no uncertainty for them. Every error figure below is an
*agreement* measure against another photogrammetric reconstruction. It is
adequate for regression and for detecting gross failure; it cannot substantiate
a positional accuracy class.

The reference was never given to the reconstruction. `run_mission.py` passes
only `datasets/public/zurich_mav/agz_dense_pass/raw/` to `pipeline.run`, and
loads the reference afterwards in `score()`.

## Results

| Metric | OpenCV engine | COLMAP engine |
|---|---:|---:|
| Wall clock | 310.7 s | **86.4 s** |
| SfM stage | 290.6 s | **77.7 s** |
| Keyframes selected | 80 | 80 |
| Cameras registered | 80 (100% of keyframes) | 80 (100% of keyframes) |
| Fraction of the 184 decoded frames registered | 43.5% | 43.5% |
| Sparse points | 23,805 | 22,635 |
| Mean track length | 2.78 | **3.91** |
| Median reprojection error | **0.231 px** | 0.326 px |
| Fused cloud points | 19,080 | 17,848 |
| Fused points classed high-confidence | 6,201 (32.5%) | **9,949 (55.7%)** |

### Position error against the reference, 80 scored cameras

Reported two ways. *As georeferenced* removes only the common translation, so
it keeps the reconstruction's own scale and orientation — that is the
georeferenced product. *After similarity fit* solves scale and rotation against
the reference too, so it isolates shape and is **not** an accuracy claim.

| | OpenCV | COLMAP | Onboard GPS |
|---|---:|---:|---:|
| As georeferenced, median | 3.70 m | 3.76 m | 4.60 m |
| As georeferenced, p90 | 6.91 m | 6.84 m | 11.32 m |
| As georeferenced, max | 9.99 m | 10.93 m | 25.08 m |
| After Sim(3), median | 0.68 m | **0.32 m** | — |
| After Sim(3), p90 | 1.04 m | **0.51 m** | — |
| After Sim(3), fitted scale | 0.9781 | 0.9778 | — |

### Georeferencing

| | OpenCV | COLMAP |
|---|---:|---:|
| Similarity scale (recon units → m) | 4.450 | 16.953 |
| Scale 1-sigma, absolute | 0.0522 | 0.1943 |
| **Scale 1-sigma, relative** | **1.17%** | **1.15%** |
| GNSS alignment RMSE (3D) | 6.29 m | 6.14 m |
| Inliers | 80/80 | 80/80 |
| Degenerate | no | no |
| Gravity levelling | rejected (6.29 → 16.78 m) | rejected (6.14 → 14.97 m) |

### Coverage

Built under the corrected free-space rule (`EMPTY` requires a ray that
terminated on a finite, supported depth). Not comparable with coverage figures
from before 2026-09-19.

| Class | OpenCV | COLMAP |
|---|---:|---:|
| OBSERVED | 5,275 | 4,108 |
| WEAK | 336 | 170 |
| EMPTY (verified free) | 145,399 | 54,360 |
| OCCLUDED | 1,207,051 | 517,548 |
| UNSEEN | 1,105,491 | 786,126 |
| Fraction explained | 6.13% | 4.30% |

Grid extents differ between the runs because each engine's cloud has a different
bounding box, so the absolute counts are not directly comparable; the class
*ordering* is the readable part.

## What this shows

1. **COLMAP is the better engine on this data.** 3.5× faster and half the shape
   error, with a longer mean track (3.91 vs 2.78 observations per point) — more
   views per point is the mechanism, and it is also what a future
   observation-lineage layer has to work with. Recorded as
   [DEC-008](../../../DECISIONS.md).

2. **Absolute accuracy is set by the receiver, not the engine.** As-georeferenced
   medians are 3.70 m and 3.76 m — indistinguishable — against a 9.43 m `eph`
   GNSS. Choosing an engine on that number would have found no difference.
   The reconstruction is nonetheless better than the raw GNSS it was given
   (3.7 m vs 4.6 m median, 6.9 m vs 11.3 m p90), so the fit is adding
   information rather than merely following the track.

3. **Scale uncertainty is the binding constraint on measurement.** Both engines
   land at ~1.15% relative, consistently. That is ±5.7 cm at 1-sigma on a 5 m
   width and ±46 cm on a 40 m span — before any endpoint or pose error. A ±20 cm
   tolerance is therefore unreachable on anything longer than about 9 m from
   this capture, whatever is done to the geometry. `questions.py` reports this
   as a distinct `scale_uncertainty_dominates` reason precisely because local
   refinement cannot fix it.

4. **Less than half the pass is being used.** Keyframe selection kept 80 of 184
   frames; SfM then registered all 80. The loss is in selection, before either
   engine sees the data, and it is engine-independent. 104 frames of a
   single-pass capture contributed nothing.

5. **Gravity levelling is wrong on this capture** and both runs correctly
   declined it. Worth investigating rather than leaving as a permanent
   rejection.

## What this does not show

- Any positional accuracy class. The reference is not independent.
- Any measurement accuracy. No reference dimensions exist for this site, so
  distance, height and area error are entirely unmeasured.
- Anything about other cameras, other sites, or other capture patterns. This is
  one pass over one scene.
- Interval calibration. No coverage check has been run, which is why no
  measurement in the system can be accepted.

## Reproducing

```bash
cd drishti3d
.venv/bin/python scripts/build_agz_mission.py \
    --source data/real_drone/agz_dense --name agz_dense_pass --overwrite
.venv/bin/python scripts/run_mission.py --mission agz_dense_pass \
    --max-frames 184 --engine colmap --tag colmap_full
.venv/bin/python scripts/run_mission.py --mission agz_dense_pass \
    --max-frames 184 --engine opencv --tag opencv_full
```

Full machine-readable results, including every pipeline warning and the whole
report block, are written to
`drishti3d/data/runs/agz_dense_pass__{tag}/run_{tag}.json`.
