# Integration bottlenecks — status against the brief

Four bottlenecks were flagged as likely roadblocks. This records what the code
actually does about each, with evidence, and what is still open.

## 1. Coordinate frame alignment (`T_body^cam`)

**Risk.** Feed-forward models emit OpenCV camera axes (+Z forward, +Y down,
+X right); drone telemetry is NED or ENU. A wrong convention does not crash —
it produces a plausible reconstruction in the wrong place, and Sim(3)
alignment to GNSS absorbs part of the error and hides the rest.

**Status: addressed.** `reconstruction/drishti_recon/frames.py` owns every
transform between the four named frames (ENU, NED, BODY/FRD, CAM/OpenCV).
Nothing else in the codebase converts between them.

Tests pin *physical meaning* rather than algebraic round-trips — a round-trip
passes just as happily with two compensating sign errors:

| assertion | value |
|---|---|
| gimbal pitch −90° | optical axis `(0, 0, −1)`, straight down |
| level, yaw 0° | `(0, 1, 0)`, north |
| level, yaw 90° | `(1, 0, 0)`, east |
| body lever `+x`, yaw 90° | offset moves east |
| body lever `+z` | offset moves **down** |

**The gimbal double-counting trap.** A 3-axis gimbal stabilises the camera, so
DJI reports gimbal attitude relative to the *world*, not the airframe.
Composing it onto body attitude — the intuitive reading — makes the camera yaw
with the aircraft, which is exactly what the gimbal exists to prevent.
`R_enu_from_cam` is world-referenced by default; `gimbal_relative_to_body=True`
is available for rigid mounts and *requires* `body_rpy_deg` rather than
silently assuming level flight. Both behaviours are tested.

Boresight (fixed gimbal-to-optical misalignment) and lever arm are supported;
the lever arm declines to apply itself without attitude rather than guessing,
since a body offset cannot be placed in the world without it.

**Open:** rolling-shutter-aware bundle adjustment. Rolling shutter is detected
(`sensors.detect_rolling_shutter`) but not modelled inside the optimisation.

## 2. Feed-forward → SuGaR handshake

**Risk.** SuGaR needs an existing 3DGS model, normally initialised from a
COLMAP sparse cloud. Skipping COLMAP means building the bridge from
MASt3R/VGGT pointmaps to initial Gaussian attributes (position, SH, scale,
opacity).

**Status: open.** `dense3d.py` produces positions, colours and per-point
confidence, which covers position and the DC spherical-harmonic term. Missing:
per-Gaussian scale from local point density, opacity from confidence, and the
rotation quaternion. This is the main remaining gap for Tier 2.

## 3. Telemetry synchronisation jitter

**Risk.** DJI/Autel `.SRT` subtitles lag the video by 1–2 frames.

**Status: partly addressed, and weaker than the brief asks for.**
`sensors.estimate_time_offset` cross-correlates the *speed profile* of the
reconstructed camera track against the GNSS speed profile. Both are
normalised, so neither unknown scale nor unknown orientation matters.

Two honest limitations:

- It runs **after** SfM, because it needs reconstructed camera centres. The
  brief's suggestion — optical flow against gyro angular velocity — would lock
  sync *before* reconstruction, which is strictly better ordering. Not yet
  implemented; `.SRT` files rarely carry gyro, so this needs the flight log.
- An early version returned +1.8 s on a 2 s clip, collapsing the alignment
  scale to 0.0064. Now guarded by a search clamp, a minimum-overlap
  requirement, and edge-peak rejection, and it reports low confidence instead
  of a confident wrong number when the capture cannot reveal its own timing.

`.SRT` ingestion now captures gimbal attitude, airframe attitude, focal length,
and distinguishes `rel_alt` from `abs_alt` — the last of which matters because
treating a relative altitude as MSL displaces the reconstruction vertically by
the launch elevation with nothing downstream able to notice.

## 4. C++ environment collisions

**Risk.** `openvdb` bindings, `trimesh[embreex]` and CUDA PyTorch wheels
conflict over `libstdc++` ABI.

**Status: avoided rather than solved, deliberately.** The current stack has no
`openvdb` or `embreex`: coverage is a NumPy z-buffer over a voxel grid
(`coverage.py`), and meshing uses Open3D. Two measured reasons to keep it that
way for now:

- **GTSAM was rejected on exactly this class of problem** (D-030). `pip install
  gtsam` force-downgrades numpy 2.5.2 → 1.26.4, changing the numeric foundation
  every benchmark was validated on. `g2o-python` does not build here. The pose
  graph is scipy, and on the synthetic bow scenario it removes the bow to 0.86 m
  median with per-frame GPS priors.
- Adding a C++ layer buys speed, not capability, and the current graphs
  (≤ a few hundred nodes) are well inside scipy's range.

If Embree raycasting becomes necessary for coverage at scale, the brief's
recommendation stands: isolate it in a container with pinned LLVM/TBB rather
than mixing it into this environment.

---

## Update — 2026-09-11

### 2. Feed-forward → SuGaR handshake: **now closed**

`reconstruction/drishti_recon/gaussians.py` builds the bridge. Every 3DGS
attribute is derived from what a feed-forward model actually returns:

| attribute | derivation |
|---|---|
| position | the pointmap directly |
| SH DC term | colour through the degree-0 SH basis constant |
| SH rest | zero — one colour per point carries no view-dependent information |
| scale | mean distance to k nearest neighbours, so a Gaussian closes the gap to its neighbours |
| rotation | quaternion aligning +z to the PCA surface normal, flattened along it |
| opacity | model confidence, floored so a low-confidence point is not born invisible |

Two traps are handled explicitly and tested. **Everything is stored
pre-activation** — 3DGS applies `exp` to scale and `sigmoid` to opacity on
load, so post-activation values produce a file that loads cleanly, holds
plausible numbers and renders as fog. And **opacity has a floor**: a Gaussian
at opacity 0 receives no gradient, so a low-confidence point initialised there
could never recover.

`write_ply` emits the 62-property binary layout 3DGS and SuGaR both read
(xyz, normals, f_dc×3, f_rest×45, opacity, scale×3, rot×4), verified by
round-trip. 15 tests.

### 4. C++ collisions: one more data point

VGGT was added as an alternative backbone and **does not fit an 8 GB card**
(D-040): 4.76 GB of weights, ~0.65 GB per frame, OOM above 4 frames. MASt3R
stays, because its cost is bounded by the image pair rather than the sequence.
This is the same theme as the GTSAM rejection — the constraint on this machine
is consistently memory and ABI, not algorithmic capability.

### Validation: the most important update

The AGZ height result **did not survive a second segment** (D-038). Our
accuracy is stable at 6.02 / 6.37 m 3D; the GNSS moved from 5.52 m to 1.91 m.
Absolute georeferencing does not beat consumer GNSS. The benchmark contract now
says so explicitly for real data: no claim from a single capture segment.

UseGeo could not be fetched — its Synology share reports
`sharing_status: "none"` and requires credentials or has lapsed, so dense LiDAR
surface truth is still missing. That remains the highest-value open item,
because it is the only thing that can support a surface-accuracy claim.
