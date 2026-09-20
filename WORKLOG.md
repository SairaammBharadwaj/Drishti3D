# Work Log

Chronological engineering log. Entries are appended; historical entries are not
rewritten.

---

# 2026-09-19 — Dataset foundation, two silent-wrongness fixes, and the measurement acceptance gate

## Objective

Begin implementing `DRISHTI3D_MVP_PLAN.md`. Two things had to be true before any
feature work was worth doing:

1. Establish what data is actually in this checkout and whether it supports real
   reconstruction, rather than trusting earlier reports.
2. Get a measured baseline on real single-pass aerial video, since the project's
   own notes record that synthetic benchmarks previously produced conclusions
   that real data overturned.

Then build the gate that makes the product's central claim honest: a tolerance
is asked, and the system either accepts, or names the missing evidence.

Target for the session: plan gates G0 (freeze contract and truth) and the
reconstruction half of G1 (reliable geometry), plus the F2 acceptance backbone.

## Work Completed

### Dataset layer (plan G0, section 6.6)

Created `datasets/` at the repository root in the plan's layout, with payload
directories gitignored and manifests tracked.

**`drishti3d/scripts/agz_logs.py`** — reader for the AGZ log files, keyed by
`imgid`, which is what lets a frame subset be rejoined to its telemetry and to
the published reference positions.

**`drishti3d/scripts/inventory_datasets.py`** — inventories every dataset in the
checkout: per-file sha256, an order-stable set digest, Git-LFS pointer
detection, ffprobe facts for videos, and *flown geometry* for AGZ image sets
(path length, net displacement, median baseline, altitude range, GNSS fix
types). Writes `datasets/catalog.csv` and `datasets/INVENTORY.md`.

**`drishti3d/scripts/build_agz_mission.py`** — turns an AGZ frame subset into a
plan-conformant mission: a variable-frame-rate `video.mp4` whose per-frame
presentation timestamps come from the log, a normalised `telemetry.csv`, a
`frame_index.csv` mapping every encoded frame back to its source JPEG and hash,
`calibration/camera.json` from the publisher's factory calibration, and a
`manifest.json`/`.yaml` recording hashes, flown geometry, known deviations, and
explicitly which claims the mission does and does not support. Reference
positions go to `datasets/truth/<mission>/`, a separate root the worker is never
given.

**`drishti3d/scripts/run_mission.py`** — reconstructs a mission and scores it.
The worker role gets only the mission folder; the evaluator role loads truth
afterwards. Errors are reported twice: as-georeferenced (translation removed
only) and after a similarity fit, because reporting only the second is the usual
way a drifting reconstruction is made to look accurate.

### Two correctness fixes

**Frame presentation timestamps.** The pipeline read `CAP_PROP_POS_MSEC` before
each `cap.read()`. On OpenCV 5.0.0 here that series starts with a duplicate zero
and lags the true timestamp by one frame, so `_adopt_pts` rejected it as
non-monotonic and silently fell back to `frame_index / fps`. Harmless for
constant-rate video; a full second per frame wrong on the variable-rate missions
built from AGZ. Now both sides of the read are sampled and the self-consistent
series is chosen, with the convention reported in the run warnings.

**Verified free space in the coverage field.** `coverage.build` classified a
voxel as `EMPTY` — "swept by rays, verified to hold no surface" — whenever any
camera had an unobstructed sight line. The z-buffer is initialised to `+inf`, so
a pixel through which nothing was reconstructed reported `nearest = inf`, the
`z <= nearest + tol` test passed, and the cell was published as verified free
space. A hole in a sparse cloud was becoming an assertion that a volume is
clear. Free space now requires a ray that terminated on a finite, supported
depth, with the slack subtracted rather than added.

The MVP plan predicted this one by code reading (section 3.2) before any test
was run.

### Measurement acceptance gate (plan F2, F5)

**`reconstruction/drishti_recon/questions.py`** — `Status` (four verdicts),
`Reason` (thirteen reason codes, each with operator-facing text and the action
that would actually change the verdict), `CalibrationProfile`,
`MeasurementQuestion`, `Evidence`, and `evaluate()`.

**`reconstruction/drishti_recon/evidence.py`** — `ReconstructionEvidence`:
candidate views from a real frustum test, parallax as the widest angle between
any two view rays, coverage membership, scale source and relative scale
uncertainty, and a diversity-ranked list of supporting frames.

**Backend** — `MeasurementQuestion` table; acceptance columns on `Measurement`;
`questions` router with create / list / patch-tolerance / evidence / delete; an
additive startup migration so existing development databases survive the schema
addition.

### Test suite

41 tests added across four new files. 223 → 264 passing, none removed or
weakened.

## Files Changed

`drishti3d/reconstruction/drishti_recon/pipeline.py`
Decode loop samples PTS both sides of `read()`; `_adopt_pts` picks the
self-consistent series and reports which; camera export carries the ENU-frame
rotation `R_cam @ R_world^T` alongside the centre, plus `K` and `image_size` in
`trajectory.json`, because a stored pose cannot say what it was looking at
without them; `manifest.json` gained the alignment block, since scale provenance
dominates a measurement's interval and was previously only in an in-memory
report.

`drishti3d/reconstruction/drishti_recon/coverage.py`
Free space now requires a finite depth return; new `free_count` array drives the
`EMPTY` class and is persisted in `coverage.npz`;
`meta["free_space_requires_finite_depth"]` marks grids built under the new rule.

`drishti3d/reconstruction/drishti_recon/questions.py` (new)
The acceptance rules.

`drishti3d/reconstruction/drishti_recon/evidence.py` (new)
Evidence assembly from stored artifacts.

`drishti3d/backend/app/models.py`
`MeasurementQuestion` table; `Measurement` gained `sigma`,
`interval_half_width`, `interval_level`, `interval_basis`, `status`,
`status_reasons`, `dominant_limitation`, `threshold_result`, `evidence`,
`artifact_version`, `calibration_profile`, `question_id`.

`drishti3d/backend/app/db.py`
`_add_missing_columns()` — additive-only `ALTER TABLE` at startup, so a schema
addition does not break an existing development database.

`drishti3d/backend/app/routers/questions.py` (new)
The API. Contains no geometry; calls `measure`, `evidence` and `questions`.

`drishti3d/backend/app/routers/measurements.py`
`_load_cloud` → `load_cloud` for reuse, and it now loads `sigma` and
`sigma_major` from `cloud.npz`. It had been dropping them, so every endpoint
reported `sigma = inf` and the entire uncertainty pipeline was computed, written
to disk, and discarded one step before use.

`drishti3d/backend/app/schemas.py`, `main.py`
Question request/response models; router registration.

`drishti3d/scripts/{agz_logs,inventory_datasets,build_agz_mission,run_mission}.py` (new)
Dataset tooling.

`drishti3d/tests/{test_timing_and_freespace,test_questions,test_evidence,test_questions_api}.py` (new)
41 tests.

`.gitignore`
`datasets/{public,field,truth}/` — the bytes are not tracked, the catalog and
manifests are.

Root documentation: `PROJECT_OVERVIEW.md`, `DECISIONS.md`, `SYSTEM_FLOW.md`,
`TESTS_AND_RESULTS.md`, `NEXT_STEPS.md`, this file.
`drishti3d/docs/benchmarks/2026-09-19_agz_single_pass_engines/RESULTS.md`.

## Important Implementation Details

**Acceptance cannot currently be reached, deliberately.**
`questions.evaluate()` returns `MEETS_REQUIREMENT` only when a validated
`CalibrationProfile` covering the capture regime is supplied and no blocking
reason applies. The backend passes `profile=None` unconditionally because no
profile has been fitted for any regime, and `Evidence.view_support_basis` is
always `frustum_upper_bound` because the cloud carries no observation lineage.
Both are blocking. The strongest verdict the system can produce today is
`estimated_only`, and a test asserts that no tolerance — including 100 m —
changes that. See DEC-003 and DEC-006.

**Mission video timing.** The frame set is a stride subsample of a 30 Hz
capture, so the real spacing is ~1 s. The video is built with an `ffconcat`
carrying a per-frame `duration` from the log, encoded with `-fps_mode vfr`. The
concat demuxer drops the final entry's duration unless the file is repeated, so
it is repeated and the encode is then cut to exactly `len(images)` frames —
otherwise the clip ends with a duplicate frame carrying a timestamp no telemetry
row belongs to.

**Telemetry sigma columns carry only what the log supports.** AGZ's `eph_m` is a
horizontal DOP in metres and goes to `sigma_e_m` and `sigma_n_m`. Its `epv_m`
column is corrupt in the published release — values around 1e-43, not metres —
so `sigma_u_m` is written empty. Unknown is not the same as small.

**Camera rotations are transformed, not copied.** The similarity that moves the
cloud into ENU rotates the world under every camera, so the exported pose is
`R_cam @ R_world^T`. Exporting the solver's raw `R` would point every camera in
the wrong direction downstream — the same trap the coverage grid's comments
already record having fallen into once.

**Relative scale uncertainty.** `alignment.scale_sigma` is the absolute 1-sigma
of the similarity scale *factor*, whose magnitude depends on the
reconstruction's arbitrary internal units. It must be divided by the factor.
Using it raw reported the same 1.15% scale error as 19.4% on the COLMAP run and
1.17% on the OpenCV run, purely because the two solvers chose different internal
units.

**Support is set by the weakest endpoint.** A width whose near edge is seen from
twenty angles and whose far edge from one is a one-view measurement, so
`Evidence.for_points` takes the minimum across endpoints, not the mean.

**Supporting frames are ranked by added angular spread**, not by proximity or
distance, so a run of near-identical neighbours does not fill the list. This is
the ranking a same-pass refinement scheduler will reuse.

## Commands Executed

```bash
# baseline before any change
cd drishti3d && .venv/bin/python -m pytest tests/ -q        # 223 passed, 111 s

# dataset inventory
.venv/bin/python scripts/inventory_datasets.py --no-hash    # fast pass
.venv/bin/python scripts/inventory_datasets.py              # 16 entries, hashed

# build the mission
.venv/bin/python scripts/build_agz_mission.py \
    --source data/real_drone/agz_dense --name agz_dense_pass --overwrite

# reconstruct and score, both engines
.venv/bin/python scripts/run_mission.py --mission agz_dense_pass \
    --max-frames 184 --engine opencv --tag opencv_full
.venv/bin/python scripts/run_mission.py --mission agz_dense_pass \
    --max-frames 184 --engine colmap --tag colmap_full

# after the changes
.venv/bin/python -m pytest tests/ -q                        # 264 passed, 140 s
```

## Problems Encountered

**Problem** — The downloaded `AGZ_subset.zip` sample is byte-identical in size
to the copy already in `drishti3d/data/real_drone/`, and its 350 bundled MAV
frames turned out to span 6.07 m of flight over 11.6 s, with 0.66 m of net
displacement.

**Cause** — Those frames are the pre-flight hold, not a pass. The publisher's
subset is a sample of the *archive*, not a usable flight segment.

**Solution** — The usable data was already present: `agz_dense` (184 frames,
233 m, 1.17 m median baseline), `agz_pass` and `agz_seg2` hold frames from
outside the 1–350 subset, drawn from the full archive by an earlier session. The
inventory script now computes flown geometry for every AGZ image set so this is
visible at a glance instead of discovered by a failed reconstruction.

---

**Problem** — `ffmpeg` rejected `-vsync vfr` with *"Unrecognized option
'vsync'"*.

**Cause** — Removed in current FFmpeg.

**Solution** — `-fps_mode vfr`.

---

**Problem** — The built video decoded to 185 frames for 184 inputs, and PTS
compared against `frame_index.csv` was offset by one.

**Cause** — Two independent issues. The extra frame is the concat demuxer's
repeated-last-file idiom. The offset is OpenCV reporting `CAP_PROP_POS_MSEC` for
the frame just returned rather than the one about to be decoded.

**Solution** — `-frames:v N` cuts the encode to exactly the input count. The PTS
convention is now detected rather than assumed (DEC-005). Confirmed on two
unrelated constant-rate videos that the lag is a property of this OpenCV build.

---

**Problem** — Every measurement through the new API came back `not_observable`
with `uncertainty_undefined`.

**Cause** — `routers/measurements._load_cloud` constructed `PointCloud` without
`sigma` or `sigma_major`, so `measure._snap` returned `inf` for every endpoint.
The pipeline computes, propagates and persists per-point uncertainty; the API
was dropping it one step before use.

**Solution** — Load both arrays from `cloud.npz` when present.

---

**Problem** — Adding columns to `measurements` broke the existing development
database with `OperationalError: no such column`.

**Cause** — `Base.metadata.create_all()` creates missing tables and leaves
existing ones alone.

**Solution** — `db._add_missing_columns()`, an idempotent additive-only `ALTER
TABLE` pass at startup (DEC-007).

---

**Problem** — `ReconstructionEvidence` reported a 19.4% relative scale
uncertainty on the COLMAP run and 1.17% on the OpenCV run, for the same capture.

**Cause** — Treating `alignment.scale_sigma` as already relative. It is the
absolute sigma of the scale factor, and the two engines chose internal units
differing by ~3.8×.

**Solution** — Divide by `alignment.scale`. Both engines then report ~1.15%,
which is the consistency one should expect. `pipeline.py` already did this
division internally, which is what identified the error.

## Approaches That Did Not Work

**Reading `CAP_PROP_POS_MSEC` before `read()` and trusting the documented
meaning.** It is not what this OpenCV build does, and the failure is invisible
on constant-rate video because the fallback happens to be correct there. Anyone
tempted to "simplify" this back to a single read should first run
`tests/test_timing_and_freespace.py`.

**Using the frustum-derived view count as measurement support.** It was the
obvious shortcut while lineage is missing, and it is optimistic in exactly the
direction that matters: cameras that merely have a point in frame would clear
the degeneracy check for a point that only one direction ever observed. Rejected
in favour of stamping the basis and treating a non-lineage basis as blocking
(DEC-006).

**Accepting measurements on the propagated interval alone, with an "estimated"
label beside them.** A label does not survive contact with a user who acts on
the status. Rejected in favour of requiring a validated calibration profile,
accepting that nothing can be accepted today (DEC-003).

**Building the mission by copying reference positions in alongside the
telemetry, relying on discipline to keep them apart.** The plan's own warning
applies — "folder names alone do not prevent leakage" — and a single careless
argument would invalidate every result afterwards, silently. Rejected in favour
of two roots and a call structure where the worker never receives the truth path
(DEC-002).

## Verification

- **Unit and integration:** 264 tests pass, up from 223. Details and per-test
  assertions in [TESTS_AND_RESULTS.md](TESTS_AND_RESULTS.md).
- **End-to-end on real data:** both engines reconstructed the AGZ single-pass
  mission and were scored against 184 held-out reference camera positions. Full
  numbers in
  [`docs/benchmarks/2026-09-19_agz_single_pass_engines/RESULTS.md`](drishti3d/docs/benchmarks/2026-09-19_agz_single_pass_engines/RESULTS.md).
- **Reproducibility:** the COLMAP run was executed twice — 86.1 s and 86.4 s
  wall, medians 3.7627 m and 3.7635 m.
- **Manual:** video PTS round-trip against `frame_index.csv`; evidence assembly
  against the real COLMAP artifacts (80 cameras with rotations, 8 candidate
  views and 78.45° parallax for a sample point, verdict
  `estimated_only / scale_uncertainty_dominates`); dataset inventory over 2.4 GB
  finding zero unfetched LFS pointers.

## Result

Reconstruction works end to end on real single-pass aerial video with real
consumer-grade GNSS, and is measured: 86 s with COLMAP, 3.76 m median position
error against the published reference as georeferenced, 0.32 m after a
similarity fit, 1.15% relative scale uncertainty. COLMAP is 3.5× faster and
halves the shape error versus the in-repo engine, so it becomes the engine new
work is developed against (DEC-008).

The measurement layer decides and explains verdicts correctly, through the API,
with tests covering every refusal path. It cannot yet accept anything, and that
is the accurate state of a system with no interval calibration and no
observation lineage rather than a defect to work around.

Two silent-wrongness bugs are fixed: timestamps that were quietly falling back
to a nominal clock, and free space that was being asserted from an absence of
data.

Known limits carried forward, all in [NEXT_STEPS.md](NEXT_STEPS.md): no
observation lineage (P0, blocks three MVP features), no validated calibration
(P1, needs field data), 56% of the pass discarded by keyframe selection (P1),
no refinement, no passport, no Tolerance Lens UI.

---

# 2026-09-19 (later) — Observation lineage: measurements know which frames made them

## Objective

Clear the P0 blocker recorded in the previous entry. Three MVP features
depend on it — Evidence Replay (F3), same-pass refinement (F4), and acceptance
on view support (F2) — and none can start until a cloud point can say which
image measurements produced it.

Plan work package WP1.

## Work Completed

### Lineage out of both engines

`ReconResult` gained three parallel arrays: `obs_point` (index into `points`),
`obs_frame` (keyframe index) and `obs_uv` (pixel at solving resolution), plus an
`observations_of(i)` helper.

The in-repo engine already held everything needed — `tracks[root]` maps frame to
keypoint index and `point_of_track` is iterated in the same order the point
arrays are built — so the observations are accumulated in the same loop, keyed
by the point index as it is appended. Only observations in registered cameras
are recorded; a track can carry a measurement from a frame that never
registered, and that measurement contributed nothing.

The COLMAP adapter reads `Point3D.track.elements`, which gives an image id and
the index of the 2D point within that image directly. Image ids are database
identifiers, so a `frame_of_image` map translates them to keyframe indices once,
at the point where the cameras are already being walked.

### Survival through fusion

`PointCloud` gained `source_index`: for each surviving point, the row it had in
the array passed to `fuse`. Both fusion paths now carry it through the same
indexing they already apply to confidence and sigma — exact on the numpy voxel
path, nearest-original-point on the Open3D path, which is the mapping that path
already uses for confidence.

`pipeline._remap_observations` inverts that map onto the fused cloud and drops
observations whose point did not survive. Each surviving row is written with
**both** frame numberings: the solver's keyframe index, and the decoded frame
index `sel` maps it to.

Persisted as `observations.npz` beside `cloud.npz` — one row per observation,
not per point, so a consumer that wants only geometry does not pay for it.

### Evidence prefers lineage

`ReconstructionEvidence` now loads `cloud.npz` and `observations.npz`, and
gained `has_lineage`, `lineage_point`, `observations_of` and
`measured_ray_separation_deg`. `for_points` uses the measuring frames and their
parallax when every endpoint resolves to lineage, stamping
`triangulated_observations`; otherwise it falls back to the frustum test and
stamps `frustum_upper_bound`, which still blocks acceptance.

`supporting_frames` returns the measuring frames with the pixel each
measurement was made at, flagged `measured`. That is the data Evidence Replay
needs to draw a marker on a source frame.

The evidence endpoint reports the real basis per endpoint and for the
measurement as a whole, instead of the hardcoded `frustum_upper_bound` it
returned before.

## Files Changed

`drishti3d/reconstruction/drishti_recon/sfm.py`
`ReconResult` carries observation lineage; the assembly loop accumulates it.

`drishti3d/reconstruction/drishti_recon/colmap_adapter.py`
Same lineage from COLMAP tracks; `frame_of_image` translates database image ids
to keyframe indices.

`drishti3d/reconstruction/drishti_recon/fusion.py`
`PointCloud.source_index`, threaded through both cleaning paths.
`add_inferred_layer` marks AI-proposed points `-1`.

`drishti3d/reconstruction/drishti_recon/pipeline.py`
`_remap_observations`; `observations.npz` written in `_write_artifacts`.

`drishti3d/reconstruction/drishti_recon/evidence.py`
Lineage loading and queries; `for_points` and `supporting_frames` prefer it.

`drishti3d/backend/app/routers/questions.py`
The evidence endpoint reports the actual basis and, where available, the
measuring frames, their pixels and the measured parallax.

`drishti3d/tests/test_lineage.py` (new), `test_evidence.py`
13 tests.

## Important Implementation Details

**A merged-away point donates nothing.** Voxel downsampling keeps one
representative per cell; the survivor keeps only its own observations rather
than the union of the cell's. That understates support for a point standing in
for several, which is the safe direction — attributing a measurement of one
piece of surface to a different one is exactly the overstatement this path
exists to prevent.

**Both frame numberings are stored in every row.** The solver numbers by
keyframe; the exported cameras and the mission's `frame_index.csv` use the
decoded frame index. Keyframe selection decimates, so on the AGZ mission
keyframe 1 is decoded frame 2.

**A selection must be near a point to inherit its lineage.** Snapping is capped
at `LINEAGE_SNAP_FACTOR = 2.0` times the cloud's median nearest-neighbour
spacing. Beyond that the nearest point is different surface and the measurement
falls back to the frustum basis. A cloud too small to have a spacing requires an
exact hit.

**A mixed measurement reports as frustum-derived.** If any endpoint lacks
lineage the whole measurement is stamped `frustum_upper_bound`. Averaging the
two bases would produce a figure belonging to neither.

## Commands Executed

```bash
cd drishti3d
.venv/bin/python scripts/run_mission.py --mission agz_dense_pass \
    --max-frames 184 --engine colmap --tag lineage
.venv/bin/python scripts/run_mission.py --mission agz_dense_pass \
    --max-frames 60 --engine opencv --tag lineage_ocv
.venv/bin/python -m pytest tests/ -q          # 277 passed, 112 s
```

## Problems Encountered

**Problem** — On the first real run, `measured_ray_separation_deg` returned
0.0 for a point with four recorded observations, while the frustum figure for
the same point was 84.6°.

**Cause** — The camera lookup map was keyed by decoded frame index (what the
exported cameras carry) while observations were looked up by keyframe index. No
camera resolved, so fewer than two rows came back and the function returned its
"not enough views" zero.

**Solution** — Key the map by decoded frame index and resolve through
`obs["frame_index"]`. This is precisely the trap the "two frame numberings"
comment written an hour earlier warned about, which is why both numbers are
stored in every row rather than one being derived at read time.
`test_frame_numbering_is_not_guessed_between` pins it. The failure mode is worth
naming: zero parallax on a well-observed point is indistinguishable from a
correctly detected degenerate capture.

---

**Problem** — Three new evidence tests failed with `frustum_upper_bound` on
fixtures that clearly had lineage.

**Cause** — `lineage_point` rejects a selection further than two point spacings
from the cloud, and `_spacing()` returns `inf` for a cloud with fewer than two
points. The guard `not np.isfinite(spacing)` then rejected everything, so a
single-point fixture could never match.

**Solution** — A degenerate cloud requires an exact hit (1e-6 m) instead of
admitting everything or nothing, and the fixtures were given a realistic
surrounding cloud so the spacing means something.

## Approaches That Did Not Work

**Unioning a voxel cell's observations into its surviving representative.**
Considered because it would raise measured support toward the frustum figure
and keep more measurements acceptable. Rejected: the survivor sits at a
different position from the points merged into it, so their measurements are of
different surface. It reintroduces the overstatement from a new direction.

**Storing lineage inside `cloud.npz`.** Rejected: it is one row per
observation, not per point — 69,173 against 17,897 on the AGZ mission — so it
would need padding to the longest track or object arrays, and every consumer
wanting geometry alone would load it.

**Deriving the decoded frame index from the keyframe index at read time.**
Rejected after the bug above. The conversion needs `sel`, which is not in the
artifact set, and a wrong guess fails silently in the direction that looks like
a correct refusal.

## Verification

- 277 tests pass, up from 264. 13 added across `test_lineage.py` and
  `test_evidence.py`.
- Both engines produce lineage on the real mission: COLMAP 69,173 observations
  over 17,897 points (median 3 per point, 32 points without lineage); OpenCV
  7,750 over 3,184 (median 2, none without). Pixels lie within the 1280×720
  solving resolution and the keyframe→decoded map is correct.
- Reconstruction is unaffected: the COLMAP run reproduces at 86.6 s with a
  3.765 m median as-georeferenced error and 0.322 m after Sim(3), matching the
  runs from earlier in the day.
- 400 points sampled from the real reconstruction quantify what the frustum
  basis was overstating: median 11 views against 3 measured (3.0×), and 81.1°
  of parallax against 20.5° measured (3.7×).
- End to end, a well-supported 3.0 m span now returns `estimated_only` with the
  single reason `interval_not_calibrated`; supplying a hypothetical validated
  profile turns the same measurement into `meets_requirement`.

## Result

Every measurement can name the frames that produced it and the pixel each was
measured at. `VIEW_GEOMETRY_UNVERIFIED` no longer fires on either engine, so
**interval calibration is now the only thing standing between this system and
an accepted measurement** — and that needs field data, not code.

Evidence Replay (F3) and same-pass refinement (F4) are unblocked. The
measurement passport moves from "needs lineage first" to buildable.

P0 in [NEXT_STEPS.md](NEXT_STEPS.md) is now empty.

---

# 2026-09-20 — Same-pass evidence recovery: "Improve this measurement"

## Objective

Build plan feature F4, the principal engineering contribution. Keyframe
selection discards 104 of 184 decoded frames on the AGZ development mission.
Those frames were flown, they see the scene, and nothing ever processed them.
The claim to test is that spending a bounded budget on the frames that would
help *one* measurement recovers evidence a uniform budget missed.

## Work Completed

### `reconstruction/drishti_recon/refinement.py`

`RefinementEngine` indexes every decoded frame of the pass, marks which ones the
reconstruction used, and for a given endpoint:

1. Gives each unused frame a **tentative** pose by slerp/lerp between the
   registered cameras bracketing it in time, and back-projects the endpoint.
2. Rejects candidates that cannot help, each with a stable reason code: already
   used, below the quality floor, outside the registered span, endpoint not in
   frame, or no parallax gain.
3. Ranks survivors by parallax gain, discounted past `MATCHABLE_GAIN_DEG = 25°`
   and by range.
4. For each, in order: decodes and undistorts to the solver's geometry, matches
   against temporally neighbouring registered frames, turns matches into 2D-3D
   correspondences through stored observations, and recovers a real pose by PnP
   RANSAC.
5. Locates the endpoint by **pose-guided** descriptor match — the projection
   bounds a window, and what is accepted is an independently detected keypoint
   inside it.
6. Re-triangulates from the enlarged ray set with weights in metres, and
   re-decides the measurement.

`RefinementRun` records before, after, every frame added with its PnP inliers
and located pixel, every rejection with its reason, the budget, the wall clock
and the termination reason — whether or not anything was recovered.

`measurement_value_fn` recomputes a measurement from given positions **without
re-snapping to the cloud**.

### Backend

`POST /api/projects/{id}/questions/{qid}/refine` and
`GET …/refinements`. A refinement that recovers frames inserts a *new*
`Measurement` (the original is kept, linked by `refined_from_id`) and a
`RefinementRun` row. Refining without the original video returns 409 naming the
missing input.

### Tests

24 added: 21 in `tests/test_refinement.py`, 3 API cases. 277 → 301.

## Files Changed

`drishti3d/reconstruction/drishti_recon/refinement.py` (new) — the whole feature.

`drishti3d/reconstruction/drishti_recon/evidence.py` — a point that resolves to
observation lineage now counts as observed geometry when no provenance is
supplied. Without this every refinement's before/after read `not_observable`.

`drishti3d/backend/app/models.py` — `RefinementRun` table;
`Measurement.refined_from_id`.

`drishti3d/backend/app/routers/questions.py`, `schemas.py` — the two endpoints.

`drishti3d/tests/test_refinement.py` (new), `test_questions_api.py`.

## Important Implementation Details

**The tentative pose is never measured against.** Interpolation decides what is
worth decoding. Everything that becomes evidence comes from the PnP pose.

**The projected pixel is never accepted.** Accepting it would make the new ray
pass exactly through the estimate it came from — no new information, a narrower
interval, and a refinement that reports success for doing nothing.

**A recovered camera counts for less.** `POSE_UNCERTAINTY_INFLATION = 2.0`
multiplies its pixel sigma, so adding views narrows the interval by less than
the geometry alone suggests. Treating a PnP pose as exact would make the
interval artificially certain, which is worse than not refining.

**Triangulation weights are in metres, not pixels.** A pixel error `s` at focal
length `f` and range `r` displaces the point by about `r·s/f`. Weighting by
pixels alone made a distant observation count as heavily as a near one and left
the covariance in units that were not metres — it reported a 7.24 m endpoint
sigma before this was fixed.

**Improvement is not interval width.** `reasons_cleared`, `interval_narrowed`
and `value_change_m` are reported separately.

## Commands Executed

```bash
cd drishti3d
.venv/bin/python scripts/run_mission.py --mission agz_dense_pass \
    --max-frames 184 --engine opencv --tag ocv_lineage_full
.venv/bin/python -m pytest tests/ -q          # 301 passed, 191 s
# 30-measurement outcome survey (script in the session scratchpad)
```

## Problems Encountered

**Problem** — Every PnP solve failed: 46 correspondences, zero inliers, on all
three OpenCV solvers.

**Cause** — Two independent faults. First, `FrameSource` derived the resize
factor from the principal point (`width / 2·cx`), assuming the optical centre is
the image centre. On the AGZ calibration that is off by 1%, putting every
feature ~10 px from where the stored observations say it should be. Second, and
larger: anchor frames were chosen as the frames that *measured the endpoint*,
which on this mission sit 25 frames — about 32 m of flight — from the
candidate. SIFT across that baseline returned 74 matches from 4000 keypoints,
almost all wrong.

**Solution** — Take the resize factor from the frame itself. Split the anchor
roles: `_pnp_anchors` are the registered frames nearest *in time* (posing needs
shared texture), `_endpoint_anchors` are the frames that measured the endpoint
(locating needs 3D identity). PnP then recovers 571–1378 inliers at 1.2–1.3 px,
and the recovered centres agree with the interpolated ones to 0.09–0.38 m.

---

**Problem** — With PnP fixed, endpoint location still failed on every candidate.
Descriptor distances of 389–571 with best-to-second ratios of 0.86–0.98.

**Cause** — SIFT emits a separate keypoint for each dominant gradient
orientation at a location, so one pixel commonly carries two or three mutually
unrelated descriptors. Taking the nearest keypoint and its single descriptor
picked one arbitrarily. The decisive measurement: the *same* physical point's
two observations compared at **599** when orientations were mismatched — worse
than the 5th percentile of random descriptors — while the correct pairing
compared at **122.9** and was rank 0 among all 4000 in the frame.

**Solution** — `_endpoint_descriptors` returns every descriptor within the
match radius and a match against any of them counts. The first frame was
recovered on the next run.

---

**Problem** — The first successful run reported an endpoint sigma of 7.24 m.

**Cause** — `_triangulate` weighted rays by inverse *pixel* variance and
inverted the resulting normal matrix as if it were a covariance in metres. It
is not; the units are wrong and range does not enter at all.

**Solution** — Convert each observation's pixel sigma to the cross-ray
positional sigma it implies, `range · sigma_px / focal`, and weight by that.
The same example now reports 0.216 m.

---

**Problem** — Every measurement on a COLMAP reconstruction returned
`not_observable` with `uncertainty_undefined`.

**Cause** — `colmap_adapter` never populates `point_sigma` / `point_sigma_major`;
only the in-repo engine runs the `uncertainty.point_covariances` pass. So
`cloud.npz` from a COLMAP run carries no uncertainty at all.

**Solution** — Not fixed here. Recorded as [DEC-011](DECISIONS.md) and raised
to P0, since it means the engine DEC-008 recommends cannot be measured on. All
measurement and refinement results in this entry used the in-repo engine. A
placeholder sigma was explicitly rejected: it would flow into acceptance once
calibration exists, which is what DEC-003 exists to prevent.

## Approaches That Did Not Work

**Ranking candidates by maximum parallax gain.** The obvious objective, and it
recovered nothing. The frames that add the most parallax are the same frames
whose view of the surface has changed the most; the top-ranked candidate added
70° and produced a descriptor ratio of 0.85, correctly refused as ambiguous.
Every top candidate failed identically. Ranking now peaks at 25°.

**Accepting the projected pixel as the endpoint's location.** It would have made
every candidate "succeed" — and circularly: the new ray passes through the
estimate that produced it, so triangulation returns the same point with a
falsely reduced sigma.

**Using `measure.measure_distance` as the refinement's value function.** It
snaps to the nearest cloud point, so a refined endpoint snaps back to the
unrefined point it started from and the run reports a successful refinement that
changed nothing. `measurement_value_fn` exists for this reason and a test pins
it.

**Judging refinement by whether the interval narrowed.** It would have called
the worked example a failure: the interval moved 0.001 m while the value moved
0.104 m and a blocking reason was cleared.

## Verification

- 301 tests pass, up from 277.
- **Outcome survey**, 30 weak measurements on the AGZ mission, 4-frame budget,
  median 13.7 s each: 10 of 30 recovered at least one frame and all 10 cleared a
  blocking reason (9 × `insufficient_views`, 1 ×
  `outside_established_coverage`). Supporting views 2 → 4 median, parallax
  8.1° → 15.5° median, median absolute value change 0.032 m. Reproduced exactly
  on a second run.
- **Why the rest failed**, across every candidate processed: 243 ×
  `endpoint_not_located_in_image`, 22 × `pose_recovery_failed`. Pose recovery
  works 92% of the time; endpoint location is the bottleneck.
- **Self-PnP check:** recovering a known camera from its own stored observations
  returns its centre to 2 mm with 544/546 inliers, confirming the frame, pose
  and intrinsic conventions all agree.

## Result

"Improve this measurement" works end to end and is measured. On the AGZ mission
it recovers evidence for a third of weak measurements and clears the blocking
reason every time it does.

What it does **not** yet have is the comparison the plan's F4 gate asks for:
targeted versus uniform refinement at equal added compute. Only the targeted arm
exists, so the central innovation hypothesis is supported and untested. That
experiment is now the highest-value work left, at P1.

Two findings were raised to P0/P1 in [NEXT_STEPS.md](NEXT_STEPS.md): the COLMAP
path ships no per-point uncertainty and cannot be measured on, and endpoint
location in recovered frames is the binding constraint on refinement.

---

# 2026-09-20 (later) — Per-point uncertainty on the COLMAP path

## Objective

Clear the P0 from the previous entry. COLMAP reconstructions carried no
per-point covariance, so every endpoint on one snapped to an infinite sigma and
every measurement was refused as `not_observable` — the faster, more accurate
engine was the one that could not be measured on ([DEC-011](DECISIONS.md)).

## Work Completed

### `colmap_adapter._point_uncertainty`

Runs the same covariance pass the in-repo engine uses. Observations are mapped
from keyframe index to camera row, poses converted to Rodrigues vectors,
`sigma_px` estimated from this reconstruction's own reprojection residuals via a
normalised MAD floored at 0.05 px, then `uncertainty.point_covariances` builds
each point's normal matrix from the observations that produced it — which
observation lineage made available.

The same estimator on both engines on purpose: a fixed 0.5 px would inflate a
clean reconstruction's intervals about tenfold, and two different noise models
would make every engine comparison partly a comparison of the models.

Results flow into `ReconResult.point_cov / point_sigma / point_sigma_major /
point_observable`, and the pipeline's existing scale multiplication carries them
into metres without change.

### Refinement outcome accounting

`RefinementRun` gained `reasons_added`, `status_regressed` and a verdict
ordering; `improved` now requires that the verdict did not regress. See
Problems below — this was found by running the survey on the new engine.

### Tests

11 added: 8 in `tests/test_colmap_uncertainty.py` (synthetic geometry, so they
run without PyCOLMAP), 3 in `tests/test_refinement.py`. 301 → 312.

## Files Changed

`drishti3d/reconstruction/drishti_recon/colmap_adapter.py`
`_point_uncertainty` plus the call site and the `uncertainty` stats block.

`drishti3d/reconstruction/drishti_recon/refinement.py`
`reasons_added`, `status_regressed`, verdict ordering, corrected `improved`.

`drishti3d/tests/test_colmap_uncertainty.py` (new), `test_refinement.py`.

## Important Implementation Details

**Observations are matched to cameras by frame index, not row index.** COLMAP's
image ids are database identifiers and the camera list is sorted by frame index,
so the two numbering schemes differ. Observations whose camera is absent are
dropped rather than allowed to select the wrong pose.

**The helper returns its error rather than swallowing it.** It returns
`(PointUncertainty | None, sigma_px | None, error | None)` and the error lands
in `stats["uncertainty"]["error"]`. This is not decoration — see below.

## Commands Executed

```bash
cd drishti3d
.venv/bin/python scripts/run_mission.py --mission agz_dense_pass \
    --max-frames 184 --engine colmap --tag colmap_unc
.venv/bin/python -m pytest tests/ -q          # 312 passed, 111 s
# 30-measurement refinement survey on both engines (scratchpad script)
```

## Problems Encountered

**Problem** — Every call to the new helper returned `None`. All eight unit tests
failed identically.

**Cause** — `NameError: name 'np' is not defined`. This module imports numpy
*inside* each function rather than at module scope, and the new helper did not.
A blanket `except Exception: return None, None` turned a one-line import bug
into a silent no-op.

**Solution** — Add the import, and change the helper to return the error string
so a failure is reported in `stats` instead of vanishing. The irony is the
point: a silently swallowed `None` is exactly what let the *absence* of this
whole pass go unnoticed until a measurement refused itself for want of a sigma
nobody had computed.

---

**Problem** — The refinement survey on the newly measurable COLMAP
reconstruction reported 8 improvements in 30, and two of them were measurements
that had become **unusable**:

```
needs_refinement -> not_observable
  cleared: ["interval_exceeds_tolerance", "interval_not_calibrated"]
  interval_narrowed: true
```

**Cause** — `questions.evaluate` returns early on a hard refusal carrying only
its hard-refusal reasons, so a verdict that drops to `not_observable` sheds
every soft reason it had. A set difference over the reason lists reads that as a
clean sweep. Both statements above are literally true; the measurement is worse.
It happens for a real reason: a re-triangulated endpoint can land outside
established coverage, and the coverage gate correctly refuses it.

**Solution** — `status_regressed` against an explicit verdict ordering, and
`improved` gated on it. Reported improvements on COLMAP fall from 8 to 6, with 2
regressions. Recorded as [DEC-012](DECISIONS.md).

The in-repo survey was re-run under the corrected metric so the two are
comparable — it is unchanged at 10 of 30 with no regressions, so the earlier
figure was already sound.

## Approaches That Did Not Work

**Nothing was abandoned this session.** Worth recording instead: substituting a
default sigma on the COLMAP path was rejected in the previous session and stayed
rejected. It would have made every measurement "work" immediately and fed a
fabricated interval straight into acceptance once calibration exists.

## Verification

- 312 tests pass, up from 301.
- COLMAP run: `sigma_px` 0.486 px estimated from its own residuals, 22,649
  points with covariance, `sigma_major` median 0.0364 m after fusion and scale.
  Reconstruction unchanged (94.7 s, 3.764 m median as-georeferenced).
- **60 in-coverage measurements per engine, ±0.30 m tolerance:**

  | | COLMAP | in-repo |
  |---|---:|---:|
  | Median measurement sigma | 0.0638 m | 0.0687 m |
  | Blocked only by calibration | 51 / 60 | 10 / 60 |
  | Blocked by `insufficient_views` | 4 / 60 | 50 / 60 |

- **Refinement survey on both engines**, corrected metric: in-repo 10 of 30
  improved with 0 regressions; COLMAP 6 of 30 improved with 2 regressions.

## Result

Both engines now produce measurable reconstructions, and the better one is
markedly better at it: COLMAP's longer mean track length (3.91 vs 2.78
observations per point) means 51 of 60 sampled measurements have nothing
blocking them but calibration, against 10 of 60.

An uncomfortable corollary, recorded rather than buried: **fixing the engine
reduced the need for same-pass refinement.** Refinement improved 6 of 30
measurements on COLMAP against 10 of 30 on the in-repo engine, because fewer
measurements were short of views to begin with. The feature's value depends on
what it is compared against, which is exactly why the plan's F4 gate — targeted
versus uniform refinement at equal compute — is now the highest-value experiment
left.

P0 in [NEXT_STEPS.md](NEXT_STEPS.md) is empty again. Interval calibration
remains the only thing between this system and an accepted measurement.

---

# 2026-09-20 (later still) — The F4 gate: targeted refinement loses to a uniform budget

## Objective

Run the comparison plan feature F4 actually asks for. Everything built so far is
the targeted arm; the control had never existed, so the project's central
innovation hypothesis was being claimed on a demonstration rather than a test.

Interval calibration, nominally the next item, stays blocked: no dataset in this
repository has independently measured reference dimensions, and producing them
needs a site visit rather than code.

## Work Completed

### `eval/f4_experiment.py`

A paired A/B harness. Freezes a question set to disk with a hash **before**
either arm runs and reuses it on re-runs, measures both arms from the same
stored ENU endpoints, reports each arm's *measured* added compute rather than
assuming they match, and adds an equal-budget view that truncates the targeted
arm at the control's exact spend.

`scripts/run_mission.py` gained `--preset` so the uniform arm is the same
pipeline at a denser keyframe setting rather than a different code path.

### The experiment

20 distance questions, ±0.30 m, chosen from the baseline as the ones refinement
exists for: both endpoints on established coverage, with lineage, weaker
endpoint under 15° of parallax.

| Metric | Targeted | Uniform |
|---|---:|---:|
| Added compute | 210.5 s | **135.4 s** |
| Measurements with fewer blockers | 2 / 20 | **8 / 20** |
| Measurements regressed | **1 / 20** | 5 / 20 |
| Narrower interval | 1 / 20 | **14 / 20** |
| Verdict moved up | 0 / 20 | **4 / 20** |
| Median sigma | 0.151 → 0.151 m | 0.151 → **0.092 m** |
| Blockers cleared per added minute | 0.57 | **3.55** |

At the control's exact budget the targeted arm reached 12 of 20 questions and
cleared 1 blocker against the control's 8.

### Consequence

Same-pass refinement demoted to **experimental** across the documentation, per
the plan's own stop/go rule. Its observed benefits are kept and still claimable;
the hypothesis is not.

## Files Changed

`drishti3d/eval/f4_experiment.py` (new) — the harness.

`drishti3d/scripts/run_mission.py` — `--preset`, recorded in the run JSON.

`drishti3d/reconstruction/drishti_recon/refinement.py` — `refine()` takes
`provenances`; `RefinementRun.refined_points_enu` exposes the moved endpoints.

`drishti3d/backend/app/routers/questions.py` — passes provenances through.

`drishti3d/docs/benchmarks/2026-09-20_f4_targeted_vs_uniform/` — `RESULTS.md`,
`result.json`, `questions_frozen.json`.

## Important Implementation Details

**The question set is frozen and hashed before either arm runs**, and reused on
re-run. A question set chosen after seeing a result is not a test.

**One asymmetry cannot be designed away and is stated instead.** The targeted
arm moves an endpoint off the cloud; the uniform arm rebuilds the cloud under
it. Re-snapping the targeted arm's endpoint would pull it back to where it
started, so the two after-states are not produced by identical code. What is
compared is what both genuinely produce: verdict, reason codes, propagated
sigma, supporting views, measured parallax — all through the same
`questions.evaluate` and `uncertainty` paths.

**Added compute is reported as measured, never assumed equal**, with the
equal-budget truncation alongside. Declaring a winner on unequal budgets without
saying so would have handed the targeted arm a 55% compute advantage and still
lost.

## Commands Executed

```bash
cd drishti3d
.venv/bin/python scripts/run_mission.py --mission agz_dense_pass \
    --max-frames 184 --engine colmap --preset quality --tag colmap_quality
.venv/bin/python -m eval.f4_experiment \
    --baseline colmap_unc --uniform colmap_quality --n-questions 20
.venv/bin/python -m pytest tests/ -q          # 313 passed
```

## Problems Encountered

**Problem** — The first run showed the targeted arm regressing two measurements
to `not_observable` with zero frames recovered and 0.02 s of work — it had not
touched them.

**Cause** — `RefinementEngine.refine` built its before/after evidence with
`for_points(pts)` and no provenances. When an endpoint does not snap to
observation lineage, that falls back to the pessimistic default and reports it
unobserved — disagreeing with the verdict the same measurement gets everywhere
else, where the measurement layer supplies provenance.

**Solution** — `refine()` now takes `provenances` and the backend passes them. A
refined endpoint is additionally marked observed by construction: it is a
position triangulated from image measurements this run just recovered, whether
or not it still lands within snapping distance of a lineage-carrying point.
Targeted regressions fell from 2 to 1 on the re-run against the same frozen
questions. **No other figure changed and the conclusion did not.**

## Approaches That Did Not Work

**The feature itself, against its own gate.** Recorded in full in
[DEC-013](DECISIONS.md) and the benchmark write-up rather than summarised away.
Three reasons uniform wins, only the third specific to this mission:

- A re-reconstruction runs full bundle adjustment. Targeted refinement adds rays
  to one point in isolation and cannot touch poses. The control's 39% median
  sigma reduction is that — median supporting views was 3 in *both* arms.
- More keyframes is also a denser cloud: 52,005 points against 17,898, mean
  track 4.93 against 3.91. Every endpoint snaps to a better-observed point.
- This pass is uniformly under-sampled, so spreading the budget hits something
  useful wherever it lands.

**Tuning the targeted arm until it won was considered and rejected.** The gap is
not marginal — 8 against 2 on 64% of the compute — and two of the three reasons
are structural, not parametric.

## Verification

- 313 tests pass, up from 312.
- The experiment was run twice against the same frozen questions, before and
  after the provenance fix. Both runs reach the same conclusion.
- Both reconstructions are recorded with their own scoring: baseline 81.9 s SfM,
  3.764 m median as-georeferenced; uniform 217.3 s SfM, 4.00 m over 160 scored
  cameras rather than 80.

## Result

**The plan's central innovation hypothesis is not supported on the one mission
where it has been tested.** Targeted same-pass refinement lost to a uniform
budget on every metric, on more compute.

It is now an experimental feature with stated, measured benefits: it recovers
frames for roughly a quarter to a third of weak measurements and raises their
supporting views and parallax when it does. It is not a proven advantage and the
documentation no longer says otherwise.

The retry is specified and is the top of the backlog: give the targeted arm the
local bundle adjustment plan section 5.7 step 4 asks for — which it never had,
while the control re-solves everything — and rerun this exact experiment against
the same frozen questions. A second P1 builds the capture regime this experiment
cannot speak for, to separate mechanism from regime.
