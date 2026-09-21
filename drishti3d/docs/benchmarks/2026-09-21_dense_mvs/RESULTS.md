# Dense multi-view stereo on the AGZ single pass

_Run 2026-09-21 by `scripts/run_mission.py --densify mvs`. COLMAP 4.1.0
(commit fa8e3b3ff, built with CUDA) on an RTX 5060 Laptop, 8 GB._

**Result: 251,998 observed points at 0.099 m spacing, against 17,898 at
0.167 m sparse — 14× the density, zero AI-assisted points, and no change to
reconstruction accuracy.**

## Why this run exists

The pipeline shipped only the sparse SfM cloud: the feature points that were
matched and triangulated, and nothing else. On a 233 m flight that is a
scattering of corners, and it reads as a broken reconstruction even though
every point in it is real. Plan section 5.3 asks for dense geometry by name and
it had never been built.

The complaint that prompted it was that the clouds were "full of AI-assisted
points". They were not — the class counts were `AI_ASSISTED: 0` before this run
and after it. The sparseness was the absence of a dense stage, not inference
creeping in.

## Setup

| | Value |
|---|---|
| Mission | `agz_dense_pass` — 184 frames, 233 m flown, 9.43 m eph GNSS |
| Sparse engine | COLMAP, 80 keyframes, all registered |
| Dense | `image_undistorter` → `patch_match_stereo` → `stereo_fusion` |
| Max image size | 1600 px |
| Geometric consistency | on |
| Min fusion views | 5 |

Dense stereo runs through the `colmap` **executable**, not `pycolmap`: the PyPI
wheels are built without CUDA and the call fails outright — *"Dense stereo
reconstruction requires CUDA or HIP, neither of which is available on your
system."*

## Results

| | Sparse only | **Dense (MVS)** |
|---|---:|---:|
| Points in the shipped cloud | 17,898 | **251,998** |
| Median point spacing | 0.167 m | **0.099 m** |
| `OBSERVED_HIGH_CONFIDENCE` | 9,967 | 201,829 |
| `OBSERVED_LOW_CONFIDENCE` | 7,931 | 50,169 |
| **`AI_ASSISTED`** | **0** | **0** |
| Position error vs reference, as georeferenced | 3.764 m | 3.764 m |
| … after Sim(3) | 0.322 m | 0.318 m |
| Wall clock | 94.7 s | 1231 s |

Patch-match produced **1,386,161** points before the pipeline's 0.15 m voxel
downsample. That voxel is tuned for measurement rather than appearance; a finer
one would keep more of the detail at proportionate cost, and the browser viewer
subsamples to 120,000 points regardless.

Reconstruction accuracy is unchanged, which is the right outcome. Dense stereo
adds detail to a model; it does not move it.

## The uncertainty bug this run caught

The first run reported dense points at a **median sigma of 0.0052 m against the
sparse points' 0.0364 m** — seven times *more* certain than the bundle-adjusted
geometry they were triangulated from. That is impossible, and it would have
flowed directly into measurement intervals.

Three errors in the estimate, in increasing order of importance:

1. **Wrong pixel sigma.** It used the sparse reconstruction's reprojection
   residual (0.49 px). That is *feature-localisation* precision — SIFT sits on a
   corner and finds it to a fraction of a pixel. Patch-match correlates a window
   over whatever texture is present. `DENSE_PIXEL_SIGMA` is now 1.0 px.
2. **Correlated views counted as independent.** `sqrt(n_views)` over every
   contributing image treats consecutive frames of one pass, looking at the same
   surface from nearly the same place, as independent samples. Capped at
   `MAX_INDEPENDENT_VIEWS = 4`.
3. **No floor.** A dense point is triangulated from cameras whose poses are known
   only to the bundle adjustment's accuracy, so **it cannot be better known than
   the model it rides on.** The sparse cloud's own median sigma is now combined
   in quadrature — the same reasoning that puts a neighbourhood term on the local
   refit in [DEC-014](../../../DECISIONS.md).

| | Sparse only | Dense, before the fix | **Dense, after** |
|---|---:|---:|---:|
| p10 | 0.0123 m | 0.0035 m | 0.0371 m |
| **median** | **0.0364 m** | 0.0052 m | **0.0379 m** |
| p90 | 0.1367 m | 0.0116 m | 0.0450 m |

Dense now comes out marginally *worse* than sparse, which is correct. Note also
that the sparse p10 (0.0123 m) still beats every dense point: the
best-constrained sparse points have long tracks and wide baselines that generic
stereo cannot match, and the distribution should show that.

## Dense points carry observation lineage

A dense point's track is the set of images `stereo_fusion` fused it from — the
same thing a sparse point's track is, arrived at photometrically rather than by
feature matching. COLMAP writes it to a `fused.ply.vis` sidecar, and the first
version of this work discarded everything but the count.

That mattered more than it looks. Without lineage a dense point falls back to
the frustum basis and is refused `view_geometry_unverified`, which is a
*blocking* reason: on a 60-measurement sample the dense cloud produced better
intervals than the sparse one and **every single measurement was refused**.

With lineage, all 251,785 points carry a track — 1,331,016 observations, median
5 per point.

### Measurement outcomes, 60 in-coverage distance measurements per cloud

| | Sparse | **Dense** |
|---|---:|---:|
| Median measurement sigma | 0.0647 m | **0.0619 m** |
| 95% interval | ±0.127 m | **±0.121 m** |
| Median supporting views | 3 | **4** |
| Median measured parallax | 16.6° | **27.9°** |
| Blocked by `insufficient_views` | 12 | **1** |
| Blocked by `interval_exceeds_tolerance` | 7 | **0** |
| Blocked by `view_geometry_unverified` | 1 | **0** |
| **Blocked only by calibration** | 40 / 60 | **59 / 60** |
| `needs_refinement` | 10 | **0** |

On the dense cloud 59 of 60 measurements have nothing standing between them and
acceptance except the calibration profile that does not exist yet.

### Three bugs this cost, all mine

Each produced a plausible-looking result that was wrong, and each was caught by
checking rather than by a test:

1. **Wrong camera model in the validation.** Checking that a point reprojects
   into the images that claim to have seen it gave 59%, and I read that as a
   broken image-ordering map. It was `image_undistorter` emitting PINHOLE
   (`fx, fy, cx, cy`) while the check read `params[1]` as `cx`. With COLMAP's
   own projection it is **99.9%** — the ordering was right all along.
2. **`source_index` is not a bijection on the Open3D fusion path.** It is a
   nearest-point mapping (DEC-009), so attributing dense tracks through it found
   the right input for only 21.5% of survivors. Survivors are now matched to
   their dense input spatially, within one voxel diagonal.
3. **ENU points projected through reconstruction-frame cameras.** The cloud is
   in ENU and `recon.cameras` are not; the cheirality test then discarded most
   observations silently, giving 17%. Also, `cameras_enu` is keyed by decoded
   frame index while visibility lists carry keyframe indices — the third time
   those two numbering schemes have had to be separated explicitly.

After all three: **100%** of points have lineage, and 99.9% of the observations
reproject inside the image that claims them.

## What this does not establish

- **Dense uncertainty is still a geometric estimate, not a propagated
  covariance.** Fusion does not report which images agreed at what disparity, so
  the Jacobian in `uncertainty.py` cannot be formed. The pipeline warns on every
  run that uses it.
- **It has not been checked against truth.** No reference dimensions exist for
  this site. That the numbers are now *plausible* is not the same as their being
  *right*, and only measured dimensions can settle it.
- **One mission.** Dense stereo on a different capture — weaker texture, more
  motion blur, worse overlap — may behave quite differently.

## Reproducing

```bash
cd drishti3d
.venv/bin/python scripts/run_mission.py --mission agz_dense_pass \
    --max-frames 184 --engine colmap --densify mvs --tag dense_mvs
```

Needs a CUDA-enabled `colmap` on `PATH`. `/api/capabilities` reports whether one
is present and, if not, which of the two reasons applies.
