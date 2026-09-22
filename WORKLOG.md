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

---

# 2026-09-20 (final) — The local bundle refit: the gap narrows, the verdict holds

## Objective

Retry the F4 gate on equal mechanism. The previous run compared an arm with a
bundle adjustment against one without: plan section 5.7 step 4 asks for "local
re-match and refit with a connected boundary to the global model", and that had
never been built. Until it was, "targeted refinement loses" said more about the
scope of what existed than about targeting.

## Work Completed

### `RefinementEngine._local_bundle`

Collects the connected neighbourhood — the recovered cameras, the registered
cameras sharing observations with them, and up to 400 points nearest the
endpoint — and bundle-adjusts it. `_register` now returns its PnP inliers so a
recovered camera arrives with real observations of existing geometry rather than
only a pose.

Three treatments the refit needed to be meaningful, each documented in
[DEC-014](DECISIONS.md):

**Gauge.** `bundle_adjust` has no fixed-camera mask, so the subproblem is solved
free and Sim(3)-re-anchored onto its boundary cameras' stored centres, rejected
if they had to move more than a metre. Measured drift on a representative refit:
0.054 m at scale 0.9993.

**Boundary uncertainty** (plan section 5.7 step 5). The refit alone reported
0.006 m on a point the surrounding cloud knows to 0.036 m. Its covariance is now
combined in quadrature with the neighbourhood's existing `sigma_major`:
refinement can improve where the endpoint sits *within* its neighbourhood, not
where the neighbourhood sits.

**Coverage.** Refined endpoints landed in `OCCLUDED` cells, occluded by their own
stale pre-refinement position still sitting in the grid's z-buffer. The refined
endpoint's coverage now comes from the frames that measured it; every other
endpoint is still checked against the grid.

### The refined sigma now reaches the interval

`measurement_value_fn`'s callable takes optional per-endpoint sigma overrides.
Before the refit existed this was deliberately withheld — a standalone ray
intersection gave a sigma an order of magnitude worse than the reconstruction's
— which is why the targeted arm's median interval did not move at all in the
first run.

### The rerun

Same `questions_frozen.json`, third run.

| Metric | No refit | **With refit** | Uniform |
|---|---:|---:|---:|
| Added compute | 210.5 s | 219.8 s | **135.4 s** |
| Blocked only by calibration, after (from 8) | 7 | **10** | **10** |
| Regressed | 1 | **0** | 5 |
| Narrower interval | 1 | 4 | **14** |
| Median sigma | 0.151 → 0.151 m | 0.151 → 0.128 m | 0.151 → **0.092 m** |

## Files Changed

`drishti3d/reconstruction/drishti_recon/refinement.py`
`_local_bundle`, `_call_value_fn`, per-call sigma overrides, `_register`
returning its inliers, `MAX_ENDPOINT_MOVE_M`.

`drishti3d/reconstruction/drishti_recon/evidence.py`
`for_points(endpoints_within_coverage=...)`; loads the stored `sigma_major` so a
refit can see the neighbourhood's own uncertainty.

`drishti3d/docs/benchmarks/2026-09-20_f4_targeted_vs_uniform/RESULTS.md`
Rewritten for all three runs; none discarded.

## Important Implementation Details

The refit is rejected outright when it does not lower reprojection RMSE, when
the boundary drifts more than a metre, or when the endpoint moves more than two
metres — which is a relocation, not a refinement. On rejection the run falls
back to the standalone ray intersection and says so in its notes.

## Commands Executed

```bash
cd drishti3d
.venv/bin/python -m eval.f4_experiment \
    --baseline colmap_unc --uniform colmap_quality --n-questions 20
.venv/bin/python -m pytest tests/ -q          # 314 passed
```

## Problems Encountered

**Problem** — The first refit reported an endpoint sigma of 0.006 m.

**Cause** — `point_covariances` treats poses as fixed, so a subproblem solved
against a held boundary comes back knowing the endpoint an order of magnitude
better than the model it sits in. Precisely what plan section 5.7 step 5 warns
about.

**Solution** — Quadrature with the neighbourhood's stored `sigma_major`.

---

**Problem** — Refined endpoints were refused as `outside_established_coverage`,
turning the feature's successes into regressions.

**Cause** — The coverage grid's z-buffer was built from the pre-refinement
cloud, where the point sat up to a metre nearer along the same ray. It was
occluding itself.

**Solution** — Take the refined endpoint's coverage from the frames that
measured it. This loosens a safety gate and is flagged in DEC-014 as the change
most worth re-examining if refined measurements later prove unreliable.

## Approaches That Did Not Work

**The feature, again, against its own gate** — though much less badly. It now
ties on answer yield with zero regressions against the control's five, and still
needs 1.6× the compute to get there. The gate asks for better yield *or* the
same yield faster; neither holds.

**Adding a fixed-camera mask to `bundle_adjust`** was considered and rejected
for this change: it means restructuring the parameter packing, sparsity pattern
and analytic Jacobian of the solver every reconstruction depends on. The Sim(3)
re-anchor is a workaround and is recorded as such, with the clean fix noted at
P2.

## Verification

- 314 tests pass, up from 313.
- The gate was rerun against the same frozen question set. On the 5 questions
  the targeted arm could reach: 4 of 5 intervals improved, 2 cleared blockers,
  none regressed, and q004's sigma fell 47% (0.201 → 0.106 m).
- A representative refit: 21 cameras, 400 points, 3,377 observations,
  reprojection RMSE 1.31 → 0.77 px.

## Result

**The refit worked and the verdict held.** Median sigma now moves where it did
not, regressions fell to zero, and answer yield ties the control — at 1.6× the
compute. DEC-013's demotion to experimental stands.

The binding constraint has moved. It is no longer the refit; it is **reach**.
Fifteen of twenty questions had no frame recovered at all, because the endpoint
could not be matched into a recovered frame. On the five it reached, the feature
works well. Making endpoint location succeed more often is now the top of the
backlog and the single change most likely to alter this result.

Worth stating on its own: the two arms differ in risk profile, not only in
throughput. The control clears more (8 against 2) *and* breaks more (5 against
0). For a product whose whole claim is that it does not overstate what it knows,
that is not a neutral trade.

---

# 2026-09-20 (last) — Endpoint location: stop re-identifying, start transferring

## Objective

Lift the binding constraint on same-pass refinement. After the local refit,
15 of 20 questions in the F4 gate still had no frame recovered because the
endpoint could not be found in a recovered frame. Measured directly on 75
candidates from 25 weak endpoints, the shipping locator succeeded on **1.3%**.

## Work Completed

### Diagnosis first

Counting where each attempt died gave two causes, both measured:

- **The endpoint's own descriptor often cannot be read.** The reconstruction's
  observations sit at *its* detector's keypoints. COLMAP's observations are a
  median 8.9 px from a fresh OpenCV SIFT detection; only 212 of 1,852 have a
  redetected keypoint within 3 px. This killed 31 of 60 attempts.
- **Where it can be read, it does not discriminate.** At the final match the
  best-to-second ratio has a median of 0.93, with the best descriptor distance
  at 388 against the ~123 seen between adjacent frames.

### Three locators, measured on the same 75 candidates

| Locator | Located | Refit accepted |
|---|---:|---:|
| Descriptor match against a measuring frame | 1.3% | 4% |
| Descriptors chained through intermediates | 10.7% | 20% |
| **Transfer through dense correspondences** | **40.0%** | **36%** |

Transfer matches the two frames densely (LightGlue returns 700–1,600
correspondences where SIFT returns 90–190), fits a local affine from the
correspondences near the endpoint's known pixel, and pushes the pixel through
it. No keypoint has to be found twice. It is accepted only when it agrees to
25 px with the pose-projected prediction, which shares none of its inputs.

### The F4 gate, rerun

| Metric | Before this change | **After** | Uniform |
|---|---:|---:|---:|
| Questions with a frame recovered | 5 / 20 | **16 / 20** | n/a |
| Blocked only by calibration (from 8) | 10 / 20 | **14 / 20** | 10 / 20 |
| Regressed | 0 | **0** | 5 |
| Median supporting views | 3 → 3 | 3 → **6.5** | 3 → 3 |
| Median measured parallax | 9.56° → 10.42° | 9.56° → **26.75°** | 9.56° → 10.26° |
| Added compute | 219.8 s | 206.7 s | **135.4 s** |

**For the first time the targeted arm wins something.** Higher answer yield than
the control, zero regressions against its five — at 1.53× the compute, and level
at matched budget (4 blockers cleared against 5 on the same twelve questions).

## Files Changed

`drishti3d/reconstruction/drishti_recon/refinement.py`
`_locate_by_transfer`, `_transfer_backend` (module-scope cached),
`_detect_cached`, `_chained_descriptors`, `_descriptors_at`,
`_match_in_window`, `_chain_path`.

`drishti3d/eval/f4_experiment.py`
The equal-budget block now compares the uniform arm on **the same** questions
the targeted arm reached, and reports the break-even question count.

`drishti3d/tests/test_refinement.py` — 4 tests.

## Important Implementation Details

The transfer's output is an image measurement, not a projection: it is built
from where the detector independently found features in both frames. The
projection is used only as an agreement check, because accepting it directly
would make the new ray pass through the estimate that produced it.

The local affine fit assumes the surface is locally planar over
`TRANSFER_RADIUS_PX` = 160 px. On a depth discontinuity it is wrong and the
25 px agreement check is the only thing that catches it.

## Commands Executed

```bash
cd drishti3d
.venv/bin/python -m eval.f4_experiment \
    --baseline colmap_unc --uniform colmap_quality --n-questions 20
.venv/bin/python -m pytest tests/ -q          # 318 passed
```

## Problems Encountered

**Problem** — The first run with the transfer locator reported 4,665 s of added
compute, 21× the previous run.

**Cause** — One question took 74 minutes against a median of 12 seconds.
`RefinementEngine` loaded its own LightGlue model per instance and an engine is
created per measurement, so twenty of them filled the 8 GB card and it began
thrashing. Reproducing that question alone took 9 s, which is what showed the
cost was cumulative rather than in the question.

**Solution** — Cache the matcher at module scope. The backend is stateless with
respect to the engine, so there was never a reason for more than one. 206.7 s on
the rerun. This would have hit every API request too, not only the benchmark.

---

**Problem** — The equal-budget comparison charged the targeted arm for questions
it was never given the budget to answer: 12 questions of targeted against 20 of
uniform, reported as 4 cleared against 8.

**Cause** — My own summary code compared the targeted arm's prefix against the
uniform arm's whole set.

**Solution** — Compare the uniform arm on the same prefix. The honest figure is
4 against 5 — level — not 4 against 8.

## Approaches That Did Not Work

**Computing the descriptor directly at the stored pixel.** The obvious way round
the detector mismatch, and measured as a dead end: upright SIFT at an arbitrary
pixel separates true correspondences from random ones by only 1.6–1.9×, against
roughly 4× for descriptors at detected keypoints. An arbitrary pixel is often on
texture that is not distinctive.

**Widening the radius to take the nearest keypoint's descriptor.** A keypoint
8 px away is a different feature; tracking it would measure a different 3D point
and attribute the result to the endpoint — about 0.18 m of error at this range.

**Chaining descriptors through intermediate frames.** Built and measured:
1.3% → 10.7%. Real, and not enough — the chain completed zero hops in the median
case, because each hop still needs a descriptor read that the detector mismatch
defeats. Kept as the fallback when transfer cannot be fitted.

**Using LightGlue to re-identify the stored keypoint directly.** It returns 5–10×
more matches than SIFT but recovers 0 of the known correspondences, because DISK
keypoints do not coincide with the stored observations either. That result is
what reframed the problem from identification to transfer.

## Verification

- 318 tests pass, up from 314.
- Three locators measured on identical inputs; each located pixel was also put
  through the refit, which rejects on rising reprojection RMSE or an implausible
  move, so a locator producing wrong matches would show as located-but-rejected
  rather than as success.
- The gate was rerun against the same frozen question set, fifth run.

## Result

The problem was misframed for three iterations. Re-identifying one keypoint
across a large viewpoint change is a hard problem this system does not need to
solve: it already knows where the endpoint is in the anchor frame and needs the
same location in another. That is a transfer problem, and a dense correspondence
field solves it without identification.

Reach went from 5 of 20 questions to 16, and with it the gate's result. Targeted
refinement now produces a higher answer yield than the uniform control with zero
regressions against its five — on 1.53× the compute, level at matched budget.

It stays experimental: one mission, twenty questions, no truth to score error
against, and the advantage depends on the locator succeeding at 40% of
candidates on this particular imagery. A second capture is the top of the
backlog, and after that the per-question cost, which is the whole of the
remaining gap.

---

# 2026-09-20 (second capture) — The advantage reproduces; the test beds do not generalise

## Objective

Find out whether the F4 yield advantage is a property of the method or of one
capture. The plan: build missions from `agz_pass` and `agz_seg2`, reconstruct
each at two keyframe densities, and run the gate on each with its own frozen
question set.

## Work Completed

### The second capture could not run the experiment

`agz_segment_two` (ids 64531–70021, 62 frames, 2.8 m median baseline) keeps
**all 62 frames at every keyframe preset** — fast, balanced and quality alike.
`keyframes.select` declines to thin a capture whose inter-frame image shift
already exceeds its sparse-capture guard, which exists because thinning a
photo-survey-like capture destroys it.

So the targeted arm has no candidate pool (every frame is already a keyframe)
and the uniform arm has nowhere to go (no denser preset adds frames). No denser
frame set for those image ids exists on disk. Only 19 of 62 frames register
there, against 80 of 184 on the dense pass.

`agz_sparse_pass` is worse than useless as an independent test: it covers the
*same* image-id range as `agz_dense_pass` at a coarser stride, so it is the same
route.

**The finding to keep: the F4 comparison only means anything on a capture that
is over-sampled relative to what reconstruction needs.**

### What was used instead

`agz_dense_pass` split into two halves by image id, each built as its own
mission. `scripts/build_agz_mission.py` gained `--imgid-min/--imgid-max` for it.
Different scene content, same flight; their georeferencing differs sharply
(0.41 m against 4.73 m median as-georeferenced error), so they are not the same
scene twice.

| Test bed | Baseline | Targeted | Uniform | Targeted regressions | Uniform regressions |
|---|---:|---:|---:|---:|---:|
| `agz_dense_pass` (full) | 8 | **14** | 10 | **0** | 5 |
| `agz_dense_firsthalf` | 7 | **13** | 5 | **0** | 7 |
| `agz_dense_secondhalf` | 9 | **15** | 9 | **0** | 4 |

Break-even falls to 4.8 and 5.2 questions on the halves, against 13.1 on the
full pass: the uniform arm's fixed cost is smaller there while the targeted
arm's per-question cost is unchanged.

## Files Changed

`drishti3d/scripts/build_agz_mission.py` — `--imgid-min/--imgid-max`.

`drishti3d/eval/f4_experiment.py` — `--mission`/`--set`, the video path derived
from the mission, and `--out` resolved before use.

`drishti3d/docs/benchmarks/2026-09-20_f4_second_capture/` — write-up, both
frozen question sets, both result records.

## Important Implementation Details

Each half gets its own frozen, hashed question set, written before either arm
runs and reused on re-run.

## Commands Executed

```bash
cd drishti3d
.venv/bin/python scripts/build_agz_mission.py --source data/real_drone/agz_seg2 \
    --name agz_segment_two --overwrite
for p in fast balanced quality; do
  .venv/bin/python scripts/run_mission.py --mission agz_segment_two \
      --max-frames 62 --engine colmap --preset $p --tag seg2_$p
done
.venv/bin/python scripts/build_agz_mission.py --source data/real_drone/agz_dense \
    --name agz_dense_firsthalf --imgid-max 59941 --overwrite
# ... secondhalf, four reconstructions, two gate runs
.venv/bin/python -m pytest tests/ -q          # 318 passed
```

## Problems Encountered

**Problem** — Both gate runs crashed at the very end, after both arms had run:
`'docs/...' is not in the subpath of '/home/naveen/Drishti3D'`.

**Cause** — `--out` was given as a relative path, and the result record computes
`qfile.relative_to(REPO)`.

**Solution** — Resolve `out_dir` before use and fall back to the absolute path
when the file is outside the repository. Both arms' compute was wasted once; the
frozen question sets survived, so the rerun scored the same questions.

## Approaches That Did Not Work

**Using `agz_segment_two` as the second capture.** Not a bug and not a null
result — an inapplicable one, for a specific and recordable reason. Recorded
rather than worked around, because manufacturing a pool there (by forcing a
thinner preset) would have tested a capture the pipeline deliberately refuses to
thin.

**Using `agz_sparse_pass`.** Same image-id range as the dense pass. It would
have looked like a second capture in the results table and been the same route.

## Verification

- 318 tests pass.
- Three reconstructions of `agz_segment_two` at three presets, all keeping 62 of
  62 frames — the finding is not one preset's behaviour.
- Four reconstructions of the halves, all registering 100% of their keyframes.
- Two gate runs, each against its own question set frozen before either arm ran.

## Result

**The direction reproduced on both halves, with a larger margin than the
original.** Targeted refinement beat the uniform control on answer yield in all
three test beds and regressed nothing in any of them, against the control's four
to seven regressions.

**And all three test beds are partitions of one flight.** Splitting a capture
and calling the pieces independent evidence is exactly the move this project's
documentation has spent its whole trail refusing, so the experimental label
stays. The honest statement is that the result is not an artefact of one
question set or one part of the scene, and may still be a property of this
flight, camera or site.

One finding that did not appear on the full pass: **the uniform arm made
measurements worse.** On the first half, doubling the keyframes took answer
yield from 7 down to 5, regressed seven measurements — four newly
`outside_established_coverage` — and raised median measurement sigma from
0.183 m to 0.260 m. A denser reconstruction is a different cloud, not a strictly
better one: endpoints re-snap elsewhere and the coverage grid's boundaries move.
The targeted arm regressed nothing anywhere, because it does not rebuild the
cloud and so cannot move what it was not asked about.

Two things would settle the hypothesis, and one of them needs a site visit: a
field capture dense enough to run the comparison, and halving the per-question
cost. Both are P1.

---

# 2026-09-20 (cost) — The per-question cost was frame seeking, not vision

## Objective

Close the last thing targeted refinement lost on. After the second-capture runs
it beat the uniform control on answer yield everywhere but cost 2–4× more, with
break-even at 5–13 questions. Since the control's price is fixed and the
targeted arm's is per question, that break-even *is* the comparison.

## Work Completed

### Profiled first, rather than optimising the obvious thing

| Phase | Share | Per call |
|---|---:|---:|
| `_register` | 62% | 1.05 s |
| `_locate` | 26% | 0.48 s |
| `_local_bundle` | 12% | 2.22 s |

Inside `_register`: **detection 94%, matching 6%**. Inside detection:

| | Per frame |
|---|---:|
| `gray()` — seek, decode, resize, undistort | **339 ms** |
| SIFT detect, 4000 features | 47 ms |
| SIFT detect, 1200 features | 38 ms |
| **Sequential decode, no seek** | **8 ms** |

The cost was never the vision. It was seeking in an H.264 stream, which decodes
from the nearest keyframe every time — 48× more than reading forward. A
question's top-ten candidates span a median of 16 frames.

### Two changes

**`FrameSource.prefetch`** reads the whole span a refinement will look at —
candidates, their PnP anchors, the endpoint's anchors — in one sequential pass,
bounded so it cannot read through the clip for two scattered frames.

**`_DETECT_CACHE` is module-level**, LRU-bounded, keyed by (backend name, video
path, frame). It was per engine, and an engine is created per measurement, so it
was discarded exactly when it would start paying. `_register` did not use it at
all, re-detecting each anchor once per candidate.

### Result, all three test beds, same frozen questions

| Test bed | Before | After | Speedup | Yield t / u |
|---|---:|---:|---:|---|
| `agz_dense_pass` | 206.7 s | **88.6 s** | 2.33× | 15 / 10 |
| `agz_dense_firsthalf` | 239.3 s | **75.6 s** | 3.17× | 13 / 5 |
| `agz_dense_secondhalf` | 223.9 s | **62.5 s** | 3.58× | 15 / 9 |

**The gate's premise is now satisfiable.** At the control's own budget the
targeted arm reaches all 20 questions on the full pass (clearing 8 against the
control's 8), 14 of 20 on the first half (6 against 1) and 18 of 20 on the
second (6 against 5). Break-even moved from 4.8–13.1 questions to 15.1–30.6.

## Files Changed

`drishti3d/reconstruction/drishti_recon/refinement.py`
`FrameSource.prefetch`, `_prepare`, `_store`, an LRU gray cache, the
module-level `_DETECT_CACHE` and `clear_detect_cache`, and every detection path
routed through the cache.

`drishti3d/backend/app/routers/projects.py`
`clear_detect_cache()` on video upload.

`drishti3d/tests/test_refinement.py` — 2 tests for the shared cache.

## Important Implementation Details

The detection cache is keyed by backend **name** and video **path**, never by
object identity: two detectors produce different keypoints for the same image,
and matching one's features against another's fails silently.

Reprocessing a project is safe — the frames are unchanged, and the cache is not
keyed by reconstruction. The one unsafe case is a new upload landing at the same
path with different content, which is why `clear_detect_cache()` is called from
the upload handler and not from the reprocess path.

## Commands Executed

```bash
cd drishti3d
.venv/bin/python -m eval.f4_experiment --mission agz_dense_pass \
    --baseline colmap_unc --uniform colmap_quality --n-questions 20 \
    --out "$PWD/docs/benchmarks/2026-09-20_f4_targeted_vs_uniform"
# ... and both halves
.venv/bin/python -m pytest tests/ -q          # 320 passed
```

## Problems Encountered

None worth recording. The first profile run measured `_register` directly rather
than through `refine`, so it missed the prefetch entirely and showed only a 6%
gain; measuring end to end showed 2.4×.

## Approaches That Did Not Work

**Reducing the SIFT feature count.** The obvious knob, worth 9 ms of 386, and
irrelevant to the actual cost. Measured before changing anything.

**Shrinking the local refit.** `MAX_REFIT_POINTS` 400 → 100 is 13% faster, one
refit fewer in eight, and 4.6% worse median sigma. Interval width is the
feature's remaining weakness against the control on the full pass, so trading it
for speed is the wrong direction. Left at 400, and now measured rather than a
guess.

## Verification

- 320 tests pass, up from 318.
- All three gates rerun against their own frozen question sets. Quality
  unchanged or slightly better: yield 14 → 15 on the full pass, still zero
  regressions on all three. The speedup came from doing the same work fewer
  times, not from doing less of it.

## Result

**Targeted refinement now passes its own gate on all three test beds**: higher
answer yield than the uniform control, zero regressions against its four to
seven, at comparable or lower compute. On the full pass it is both cheaper
(88.6 s against 135.4 s) and higher-yield (15 against 10).

It stays experimental, and the reason is no longer the gate. All three test beds
are partitions of one flight, and the only genuinely separate AGZ segment cannot
run the comparison at all because keyframe selection correctly declines to thin
it. A field capture is now the single thing that would settle the hypothesis —
and it is the same site visit that unblocks interval calibration, which remains
the only thing between this system and an accepted measurement.

---

# 2026-09-20 (dense + UI) — The clouds look bad because there is no dense stage

## Objective

Two things asked for: the Tolerance Lens as an operator surface, and an F4 gate
run on a second flight. Then a third, from looking at the result: the point
clouds are sparse enough to look broken.

## Work Completed

### The Tolerance Lens, on screen

`frontend/src/ToleranceLens.tsx` plus the question endpoints in `api.ts`, wired
into the Workspace panel. Everything built over the last several sessions was
reachable only from a command line — the frontend had **zero** references to the
questions API.

A card shows the value with its interval, a status chip, the dominant limitation
and every reason's concrete next action, a tolerance slider that re-decides
without re-measuring, evidence (frames that *measured* the point outlined green,
mere candidates not), and "Improve this measurement" with before/after.

The refinement panel reports `value`, `interval`, `views` and `parallax` as four
separate rows on purpose. Collapsing them into one arrow is how a run that made
things worse reads as a success — the same mistake the metric itself made twice.

`scripts/import_run_as_project.py` registers a benchmark run as an app project,
copying artifacts and the source clip, so a reconstruction can be opened in the
UI. Two demos are loaded: the AGZ mission with GNSS, and a gymnasium clip with
none.

### Second-flight test beds

`scripts/build_clip_mission.py` builds a mission from a bare clip — no
telemetry, no reference data, relative scale. Three built from the cut-free
windows a previous session had identified: `gym_pass`, `lambertus`,
`goetheanum`.

They reconstruct, and the F4 comparison **cannot run fairly on them**: the
flow-based keyframe selector converges to about 40 keyframes whatever the
preset, so `quality` adds 0–5 frames over `balanced` and there is no uniform
arm. A `dense` preset was added as the control for exactly this case.

### The sparse-cloud problem

Measured, because the complaint was that the clouds are full of AI points:

| project | points | spacing | AI-assisted |
|---|---:|---:|---:|
| AGZ | 17,898 | 0.167 m | **0** |
| Gymnasium | 4,037 | 0.092 m | **0** |

Both clouds are 100% observed. The appearance is not inference creeping in — it
is that **the pipeline only ever runs sparse SfM**. No dense stage existed,
though plan section 5.3 asks for one by name.

`reconstruction/drishti_recon/mvs.py` adds it behind `densify="mvs"`: COLMAP
PatchMatch stereo via the `colmap` executable, fused into the same cloud as the
sparse points because it is the same kind of geometry — observed, measurable.
Kept strictly distinct from `densify="depth"`, whose points are predicted from
single images and excluded from measurement.

## Files Changed

`frontend/src/ToleranceLens.tsx` (new), `api.ts`, `views/Workspace.tsx`,
`styles.css` — the operator surface.

`reconstruction/drishti_recon/mvs.py` (new) — dense stereo, its availability
reporting, and a geometric uncertainty model for dense points.

`reconstruction/drishti_recon/colmap_adapter.py` — `keep_workspace`, because
dense stereo needs the images and sparse model COLMAP wrote.

`reconstruction/drishti_recon/pipeline.py` — `densify="mvs"`, its parameters,
and fusion of dense points as observed geometry.

`reconstruction/drishti_recon/keyframes.py` — a `dense` preset, as the F4
control arm on footage where `quality` is not denser than `balanced`.

`backend/app/main.py` — `/api/capabilities` reports *why* dense is unavailable.

`scripts/{build_clip_mission,import_run_as_project}.py` (new),
`run_mission.py` — clip missions have no telemetry and no truth.

`tests/test_mvs.py` (new) — 10 tests.

## Important Implementation Details

Dense points carry a **geometric** uncertainty, not a propagated covariance:
fusion does not report which images agreed at what disparity, so the Jacobian
cannot be formed. `range * sigma_px / focal / sqrt(n_views)` is used instead and
the pipeline warns on every run that uses it, because that number is what a
measurement on a dense point would be quoted from.

Where sparse points have a propagated sigma and dense points do not, the sigma
arrays are dropped rather than concatenated — otherwise a dense point would
inherit a sparse point's sigma through indexing.

## Commands Executed

```bash
cd drishti3d
.venv/bin/python scripts/build_clip_mission.py --source data/real_drone/st_lambertus.webm \
    --name lambertus --start 182 --end 223.5 --overwrite
.venv/bin/python scripts/run_mission.py --mission gym_pass --set field_clips \
    --max-frames 184 --engine colmap --preset balanced --tag balanced
.venv/bin/python scripts/import_run_as_project.py --run agz_dense_pass__colmap_unc \
    --video datasets/public/zurich_mav/agz_dense_pass/raw/video.mp4 --name "..."
.venv/bin/uvicorn backend.app.main:app --port 8000
cd frontend && npm run dev -- --port 5173
.venv/bin/python -m pytest tests/ -q          # 330 passed
```

## Problems Encountered

**Problem** — `pycolmap` exposes `patch_match_stereo` but it fails.

**Cause** — `pycolmap.has_cuda` is `False`; COLMAP's dense stereo is CUDA-only,
and the error is explicit: *"Dense stereo reconstruction requires CUDA or HIP."*
No CUDA-enabled pycolmap wheel exists on PyPI — 4.2.0 publishes `manylinux` CPU
wheels only.

**Solution** — Shell out to a separately installed `colmap` binary. Not yet
installed here, so **the dense path has never run**; that is recorded in
DEC-018 and as the new P0 rather than implied to work by the code existing.

---

**Problem** — The F4 gate cannot run on the clip missions.

**Cause** — The flow-based keyframe selector converges to ~40 keyframes
regardless of preset on this footage, so `quality` is not a denser
reconstruction than `balanced` and there is no uniform arm. A different reason
from `agz_segment_two`'s, same effect.

**Solution** — A `dense` preset as the control. Runs pending.

## Verification

- 330 tests pass, up from 320.
- The UI path was checked end to end through the Vite proxy: a question created
  on the AGZ project returned 3.113 m, `needs_refinement`, dominant limitation
  `interval_exceeds_tolerance`, evidence basis `triangulated_observations` with
  4 measuring frames.
- Dense MVS: module, plumbing, uncertainty model and capability reporting are
  tested. **The subprocess path is not** — no CUDA COLMAP on this machine.

## Result

Everything built over the previous sessions is now reachable by an operator
rather than only from a shell.

The sparse-cloud complaint was right and the cause was not what it looked like:
zero AI-assisted points, and no dense stage at all. One is built and waiting on
a CUDA-enabled COLMAP; if that install proves impractical a torch plane-sweep
goes behind the same interface.

The second-flight F4 test remains open for a third distinct reason — first the
sparse-capture guard on `agz_segment_two`, now keyframe convergence on the
clips. Both are properties of the comparison needing an over-sampled capture,
which is the same thing a field capture would supply.

---

# 2026-09-21 — Dense stereo runs, and three of my own errors on the way

## Objective

Run the dense stage built in DEC-018 now that a CUDA-enabled COLMAP exists, and
make dense geometry actually measurable rather than merely visible.

## Work Completed

### Dense multi-view stereo, end to end

`densify="mvs"` on the AGZ mission: 1,386,161 points out of PatchMatch stereo,
fused to **251,785** at 0.100 m spacing against 17,898 at 0.167 m sparse.
`AI_ASSISTED: 0`. Reconstruction accuracy unchanged at 3.764 m
as-georeferenced — correct, since dense stereo adds detail to a model rather
than moving it. 21 minutes, ~19 of it on the GPU.

### The uncertainty was seven times too optimistic

Dense points first reported a median sigma of 0.0052 m against the sparse
points' 0.0364 m — more certain than the bundle-adjusted geometry they were
triangulated from. Three causes: the sparse reprojection residual used as a
disparity precision (feature localisation is far tighter than window
correlation); `sqrt(n_views)` treating consecutive frames of one pass as
independent; and no floor from the sparse model's own accuracy, which was the
one that mattered. Now 0.0379 m — marginally *worse* than sparse, which is the
right ordering. [DEC-019](DECISIONS.md).

### Dense points had no lineage, so none of them could be measured

With better intervals than the sparse cloud, **all 60 sampled measurements were
refused** `view_geometry_unverified`. `observations.npz` held only sparse SfM
tracks, so a dense point had no record of which images produced it.

COLMAP's `fused.ply.vis` sidecar has exactly that — a dense point's track — and
the first implementation kept only the count. Now all 251,785 points carry one:
1,331,016 observations, median 5 per point, 99.9% reprojecting inside the image
that claims them. [DEC-020](DECISIONS.md).

| 60 in-coverage measurements | Sparse | Dense |
|---|---:|---:|
| Median sigma | 0.0647 m | **0.0619 m** |
| Median supporting views | 3 | **4** |
| Median measured parallax | 16.6° | **27.9°** |
| Blocked by `insufficient_views` | 12 | **1** |
| **Blocked only by calibration** | 40 / 60 | **59 / 60** |

## Files Changed

`drishti3d/reconstruction/drishti_recon/mvs.py`
`DENSE_PIXEL_SIGMA`, `MAX_INDEPENDENT_VIEWS` and a floor in
`depth_uncertainty`; `_read_visibility` keeps the image lists;
`_workspace_frame_order` maps COLMAP's visibility indices to frame numbers.

`drishti3d/reconstruction/drishti_recon/pipeline.py`
`_dense_observations`, and `_remap_observations` merging sparse and dense tracks.

`drishti3d/tests/test_mvs.py` — the floor, the view cap, visibility round-trip.

## Commands Executed

```bash
cd drishti3d
.venv/bin/python scripts/run_mission.py --mission agz_dense_pass \
    --max-frames 184 --engine colmap --densify mvs --tag dense_mvs
.venv/bin/python scripts/import_run_as_project.py --run agz_dense_pass__dense_mvs ...
.venv/bin/python -m pytest tests/ -q          # 335 passed
```

## Problems Encountered

Three errors, all mine, each returning a plausible wrong number without raising
an exception. That is the pattern worth remembering from this session.

**Problem** — Checking that dense points reproject into the images claiming to
have seen them gave 59%, and I read it as a broken image-ordering map and went
looking for the right ordering in `fusion.cfg` and `patch-match.cfg`.

**Cause** — `image_undistorter` emits PINHOLE (`fx, fy, cx, cy`) and my check
read `params[1]` as `cx`. The ordering had been right from the start; all three
candidate orderings gave *identical* results, which should have told me sooner
that the ordering was not the variable.

**Solution** — Project with COLMAP's own camera model: **99.9%**.

---

**Problem** — Dense tracks attached to only 21.5% of the cloud.

**Cause** — Attribution went through `cloud.source_index`, which on the Open3D
fusion path is a nearest-point mapping rather than a bijection — noted in
DEC-009 as acceptable for sigma and confidence, and not acceptable for this.

**Solution** — Match survivors to their dense input spatially, within one voxel
diagonal. 99.7% match.

---

**Problem** — After the spatial fix, lineage got *worse*: 16.7%.

**Cause** — I projected ENU cloud points through reconstruction-frame camera
poses. The cheirality test then discarded most observations in silence. And
`cameras_enu` is keyed by decoded frame index while visibility lists carry
keyframe indices — the third time those two numbering schemes have had to be
separated explicitly (DEC-009, DEC-015).

**Solution** — ENU poses for ENU points, with keyframe indices translated
through `sel`. Validated offline against the saved run *before* spending another
21-minute rebuild: 251,740 of 252,480 survivors matched, 99.9% of observations
in-frame, zero behind camera.

## Approaches That Did Not Work

**Exempting dense points from the lineage requirement.** They are observed
geometry, so the basis stamp looks unnecessary for them. But "observed" is a
provenance class, not evidence of *which* images observed a point, and carving
out an exemption for the class that happens to be failing is how DEC-006's
guarantee stops meaning anything.

## Verification

- 335 tests pass.
- Dense reconstruction reproduced across five runs as the fixes went in; point
  count and accuracy stable at ~252k and 3.764 m throughout.
- The lineage chain was validated offline against saved artifacts before the
  final rebuild, which is what kept the last fix to one run rather than three.

## Result

The clouds no longer look broken, and — more to the point — dense geometry is
*measurable*. On the dense cloud 59 of 60 sampled measurements have nothing
standing between them and acceptance except the calibration profile that does
not exist yet.

Both demo projects are loaded in the app: the AGZ mission with GNSS and metric
scale, sparse and dense side by side.

The honest remaining gap is unchanged and now nearly alone: interval
calibration needs measured reference dimensions, and no dataset in this
checkout has them.

## 2026-09-21 — the Lens was empty because nothing had ever asked it a question

The workspace showed "Tolerance Lens 1" for a reconstruction whose entire claim
is that it can now be measured. Not a UI fault: `ToleranceLens` loads saved
questions on mount and the frontend typechecks clean. The database held one
question per project, because every measurement comparison in the benchmark
record was computed offline against `drishti_recon` and never went through the
app. The evidence for dense lineage existed only in RESULTS.md.

Two smaller things were in the way first. Both servers had exited with the shell
that started them, so nothing was listening at all; the frontend is launched
with `setsid` now. And the URL in the record, `127.0.0.1:5173`, never had a
listener even when Vite was up: Vite defaults to host `localhost`, Node 17+
resolves that to IPv6 first, so it bound `[::1]:5173` only. Bound explicitly to
`127.0.0.1` now — both spellings answer.

`scripts/seed_questions.py` samples point pairs from a project's own cloud --
endpoints with at least two observations, inside coverage -- across three
baseline bands (2-6 m at 50 mm tolerance, 6-18 m at 150 mm, 18-60 m at 500 mm)
and asks each through the HTTP API. Nothing in it computes a measurement; the
results are the app's own, by the code path an operator's clicks take.

24 questions into each of the dense and sparse AGZ projects, same flight:

                          sparse    dense
  median sigma            0.2480   0.1843 m
  median supporting views      3        4
  median parallax          15.0°    25.8°
  insufficient_views           4        0
  view_support_basis      triangulated_observations, 25/25 both

The dense advantage holds on questions chosen by a script that knows nothing
about which cloud it is sampling, which is the first time that comparison has
been made anywhere but my own analysis.

Every question on both projects carries `interval_not_calibrated`. That is the
designed refusal, not a defect (DEC-002), and it is now the visible state of the
system rather than a line in a document: 2 of 25 dense questions reach
`estimated_only`, the rest are held at `needs_refinement`, and none can reach
`meets_requirement` until a calibration profile is fitted against independently
measured dimensions. 335 tests pass.

## 2026-09-21 — Ten findings from a critical review, six with counterexamples

A simulated critical evaluator review of `d94ec29` landed as
`docs/NTRO_CRITICAL_REVIEW_AND_IMPROVEMENTS_2026-09-21.md`. Its verdict: enough
substance to justify serious attention, and it would still withhold a
recommendation for operational use until a reported measurement is tied to the
correct reconstruction revision, survives refinement and export, and agrees with
independent truth.

I reproduced all six executable counterexamples before changing anything. All
six held. Working through them found two more defects of the same kind that the
review had not seen.

### What was actually wrong

The system had **two definitions of a measurement**. `POST /measurements`
computed without scale uncertainty, never checked that metric scale existed, and
stored a row with no sigma, no interval basis, no status and no artifact
identity. `POST /questions` stored all of it. Both returned a number labelled in
metres and the Workspace offered both buttons. The acceptance gate was never
admitting bad measurements — there was simply a second, quieter answer to what a
measurement is, and it was the default one. One result service now (DEC-021).

**Scale was applied per segment.** A 10 m line at 10% scale uncertainty reported
1.000 m; adding a midpoint reported 0.707 m. Inserting a vertex manufactured
confidence about a line whose geometry had not changed. Propagating the length
function itself fixes both that and the shared-vertex double count: the
derivative at an interior vertex is `u[i-1] - u[i]`, which vanishes when the
vertex lies straight between its neighbours. Validated by Monte Carlo over 20k
trials with one shared scale draw, within 5% on straight, right-angled and
wandering polylines (DEC-022).

**Snapping was unbounded.** A selection at `[1000,0,0]` against a cloud ending at
`[10,0,0]` moved 990 m and was then measured, with evidence assembled, where the
operator never pointed. The distance was computed and thrown away. A test
asserted the old behaviour — picking an AI point with inference off was expected
to snap 100 m down to the ground — which is the substitution restated as a
requirement (DEC-023).

**`as_georeferenced` subtracted the offset it was reporting.** A reference
shifted by [100,200,30] m scored zero. The docstring's reasoning was right for a
local frame and false here, because `score()` has already put both sides in UTM.
Rescoring offline: the real absolute median is **5.270 m**, not the 3.764 m this
project has been quoting. Onboard GPS is 5.155 m against the same reference, so
the reconstruction sits at the accuracy of the signal it was georeferenced from
— the honest ceiling, invisible while the offset was being removed. The removed
translation is a −3.91 m northing component common to both engines and the raw
GPS: systematic, not reconstruction error (DEC-024).

**Dense depth uncertainty never consulted the triangulation angle.** The formula
was `r·σ/f`, a transverse localisation scale, used as a depth error — which
silently asserts every dense point was seen from 45° apart. At this mission's
26° median the true figure is 2.1× larger; at 5°, 11× larger. Always optimistic,
and most optimistic where the geometry was weakest. The contributing-camera list
was already on disk and was not being read (DEC-025). This is the fourth
instance of the DEC-019 pattern: an uncertainty that looked implausibly small
because something held fixed was not actually known.

**LAS accepted a frame and ignored it** — `parse_crs()` returned None — while the
overview said exported clouds carried sigma. They carried neither sigma nor
provenance (DEC-027). **Caches keyed by project id** returned superseded geometry
after a rebuild; an `invalidate` helper existed and nothing called it (DEC-026).
**Calibration marked itself validated from a sample count** (DEC-028).
**Refinement stored the operator's original endpoints beside the refined value**,
and added a one-endpoint view gain to a measurement-wide *minimum*, so 3 + 4
reported 7 for a measurement whose other end still had 3 (DEC-030).

### Mistakes I made inside this work

Three, each caught by a test rather than by reading.

Writing the shared result service, I read `status_reasons` off
`Verdict.to_dict()`. It names that field `reasons`. Every stored refusal kept
its status and lost every word explaining why — and the shape was right, so
nothing failed. The same dict has no `evidence` key either, so
`vd.get("evidence", {})` would have stored empty evidence on every measurement.
Both only surfaced because the test asserted the fields were *populated* rather
than present.

Wiring the parallax computation, I mapped `vis_images` through `frame_order` —
following the docstring on `DenseResult.vis_images`, which describes the
untranslated form. `run_colmap` translates before returning, so that would have
double-translated and attributed every dense point to the wrong cameras,
silently, since wrong cameras still yield a plausible angle. The fourth
appearance of the keyframe/decoded-index hazard and the first caused by our own
documentation, which is now corrected.

And twice I killed my own shell with `pkill -f` on a pattern that matched the
command running it. `scripts/serve.sh --restart` resolves ports to PIDs and
kills by PID instead.

### Corrected claims

`PROJECT_OVERVIEW.md` now says 14× *point count* rather than 14× density, states
that unchanged camera-trajectory agreement is not evidence of unchanged dense
surface accuracy, and labels exported heights as WGS84 ellipsoidal. P0 in
`NEXT_STEPS.md` is reopened; "P0: Nothing" was wrong.

411 tests pass, up from 335, across seven new regression modules. Frontend
typechecks clean.

**Still not validated:** every corrected number is a better-founded estimate,
not a verified one. No measured reference dimension exists for any capture here,
which is exactly what `interval_not_calibrated` reports on every question in the
system.

## 2026-09-21 — Dense rebuilt and re-imported under the corrected model

21 minutes of GPU to make the demo artifacts agree with DEC-025 and DEC-029,
then re-imported into the same project so the seeded questions stayed attached.

The uncertainty correction landed exactly where it should. Median `sigma_major`
moved 0.0363 → 0.0385 m, which is almost nothing, because well-observed points
are dominated by the sparse-model floor either way. The p90 went 0.0437 →
0.0909 m and the p99 0.0832 → 0.3255 m. The correction lives in the tail: points
whose contributing views are nearly collinear, which the previous model could
not distinguish from well-triangulated ones because it consulted a view count
and never an angle.

Lineage is labelled now: 20,143 sparse feature observations against 1,312,477
dense fusion contributors, and a sampled endpoint reports three views that are
all dense contributors — images that genuinely contributed, with pixels
projected rather than measured there.

Re-importing exercised the supersede path for real. All 27 stored questions
flagged `superseded` the moment the artifacts changed, and re-asking them gave
median sigma 0.2009 m against sparse's 0.2480 m, 4 views against 3, 31.1° of
parallax against 15.0°. The dense advantage survives the correction; it is
smaller than the 0.1843 m the pre-C04 artifacts reported, which is the point.

**Three questions became `not_observable`, and it is not the fixes.** All three
are `outside_established_coverage`. COLMAP's incremental mapping is not
deterministic: the rebuilt coverage volume is (145, 217, 77) voxels against
(143, 217, 76) before, and three endpoints near the boundary fell outside it
this time. The system refuses rather than extrapolating, which is right — but it
means question outcomes near a coverage edge are **not reproducible across
rebuilds of the same flight**, and that is worth knowing before quoting any
result from one.

Two process notes. The superseded flag existed only because I checked whether
the re-import would silently present stale answers as current — it would have,
and the review had listed that under C07's acceptance criteria without my having
closed it. And I restarted the API against old code twice before noticing that
`serve.sh` skips a port that is already listening; `--restart` resolves ports to
PIDs and kills by PID, because a `pkill -f` pattern broad enough to match the
server also matches the shell running the script.

## 2026-09-21 — A verification of the fixes found nine failures, two of them mine

`docs/CRITICAL_REVIEW_VERIFICATION_2026-09-21.md` checked the DEC-021…030 work
against `61939db` and ran fifteen independent checks. **Nine failed**, including
two crashes the fixes themselves introduced. I reproduced all nine before
changing anything; all nine held. Its central judgement — that my "Closed by
DEC-021 … DEC-030" table overstated closure — was correct, and the sharpest
finding is about how I test rather than what I wrote.

### The two crashes

`refine()` raised `NameError: name 'rec' is not defined` the moment it actually
recovered a frame. The engine's evidence object is `self.ev`; I had been reading
the API router, where the same object is called `rec`, and carried the name
across. The success path had no coverage at all.

**Why 422 tests missed it, which is the part worth keeping:**
`test_refinement_record.py` defined its own `_aggregate` helper that
reimplemented the engine's loop and asserted against the reimplementation. It
confirmed the algorithm was right and could never confirm the code was. A test
containing its own copy of the logic can only show the copy is self-consistent.
The test now drives the real `refine()` through its post-recovery branch,
controlling only image I/O, registration and the local fit.

The second: `report.get("alignment", {}).get("scale_source")` in the export
sidecar. `build_report` emits `alignment=None` for a relative-scale run, and the
`{}` default applies to an absent key, not a null value. A video-only
reconstruction crashed after cloud, PLY and LAS were on disk — a partial set
that looks complete.

**The crash was hiding something worse.** A relative-scale run still builds
`ENUFrame(0, 0, 0)` as a placeholder, and my exporter treated any frame as a
geographic origin. Fixing `.get()` alone would have projected an arbitrary-scale
reconstruction into UTM off the coast of Africa and labelled it in metres.
Geographic eligibility now comes from the alignment, never from a frame object
existing.

### The uncertainty model was wrong a third time

Two checks failed on `depth_uncertainty`. A genuine 120° contributing angle gave
a **negative** sigma; 0° parallax gave a finite 4.05 because I clamped the angle
up to the threshold, contradicting the docstring I had written.

`1/tan` came from the small-baseline derivation `B ≈ r·tan(α)`, valid only for
small angles. At exactly 90° it is **zero** — the model asserted a point could be
known with zero uncertainty — and negative beyond. A supplied floor hid the sign
through `hypot`, which is why the saved cloud has no negative values and nobody
noticed.

The correct general form is `eps / sin(α)`: diverges as rays become parallel,
smallest at 90° where it equals `eps`, symmetric about it, so rays 120° apart
constrain a point exactly as well as rays 60° apart. It agrees with `1/tan` to
0.4% at 5°, so the drone-pass regime is essentially unchanged. Below the
threshold the answer is now `inf` — unconstrained — rather than a flattering
finite number.

**Three successive versions of this one function have been wrong**, each
optimistic differently: no angle, then an angle valid only in a narrow regime,
now a form correct over the domain its input can take. The recurring mistake is
applying a small-angle approximation without checking the range of its argument.

### Four contracts that were half-applied

DEC-021 said both routes call `results.compute`. Only `/measurements` did; I had
extracted the service, pointed one route at it, and written the decision record
as though the work were finished. An ungeoreferenced reconstruction answered
`m` on one route and `reconstruction units` on the other.

Refinement wrote `endpoints_moved_m` into stored evidence; `PATCH` rebuilt the
gate input with `Evidence(**stored)` and returned 500 on the next tolerance
change after any successful refinement. `PATCH` also committed an unsupported
interval level before the code that rejects it ran, leaving a question stored in
a state that failed every later read. And `artifact_version` tracked only the
manifest while caches tracked file bytes, so replacing `cloud.npz` without
rewriting the manifest gave new geometry while stored answers looked current.

All 15 audit checks pass. 431 tests, up from 422. Production frontend build
passes. Rebuilding the dense artifacts again so the demo matches the corrected
angular model.

## 2026-09-21 — Rebuilt under `eps/sin` and re-imported

Second 28-minute rebuild of the same flight so the demo matches DEC-031.
251,504 points, no error, and the numbers barely moved: median `sigma_major`
0.0385 → 0.0409 m, p90 0.0909 → 0.0937, p99 0.3255 → 0.3288.

That is the honest headline. AGZ's dense parallax is narrow-angle dominated,
and `1/tan` and `1/sin` agree to 0.4% at 5° and about 10% at 26°, so for *this*
mission the previous model's numbers were close to right despite being
nonsensical at wide angles. The correction is about the domain, not this
capture — and I would rather say that than present a 6% median shift as though
it vindicated the work.

Zero negative sigmas and zero unconstrained points: no dense point in this
mission falls below the 0.5° threshold, so the new `inf` path costs no coverage
here. A slower or more nadir pass would produce unconstrained points, and they
would now be refused rather than measured.

Re-import exercised the whole chain again. All 27 dense and all 25 sparse
questions flagged superseded — sparse because `artifact_version` gained its
revision component under DEC-033, a format change rather than a geometry
change, which is exactly the one-time effect that decision predicted. Re-asked,
dense gives median sigma 0.1983 m against sparse's 0.2480 m, 4 views against 3,
25.2° of parallax against 15.0°.

Evidence verified live rather than from artifacts: a sampled question reports
5 and 3 views per endpoint, all `dense_fusion_contributor`, `kinds_recorded`
true. The sidecar declares EPSG:32632, `georeferenced: true`, and states the
vertical reference as ellipsoidal. All nine export keys are reachable through
the API.

**One question is `not_observable` this time against three after the previous
rebuild**, both `outside_established_coverage`. That is the second observation
of the coverage-volume variation between non-deterministic COLMAP runs, and two
observations is enough to call it confirmed: outcomes for endpoints near a
coverage boundary are not stable across rebuilds of the same flight. Anyone
quoting a single-run result needs to know that.

## 2026-09-21 — The rest of the verification's open items

Worked through what the verification left open after the nine blocking
failures, taking the ones that are correctness or honesty rather than new
features.

**Sensor claims.** `has_rtk` was `any(sample is RTK)`, so one RTK-labelled row
among thousands made the pipeline describe a whole mission's scale as
RTK-derived. It is now a fraction with a 0.9 supermajority requirement, and the
fix-quality composition travels in the manifest so the label can be checked
rather than trusted. `dynamic_contamination` was hardcoded `False`; it is
derived from endpoint provenance now, with `dynamic_status_known` recording
whether any masker ran — "nothing looked" and "looked and found nothing" were
being reported identically.

Adding that field cost me twenty minutes: I declared it in the middle of
`ReconstructionEvidence`, which shifted every positional argument after it, so
`points` became the flag and 22 tests failed with a `KeyError` on lineage far
from the cause. `load` and several tests construct that class positionally, so
field order is part of its interface. Declared last now, with a comment.

**Calibration regime.** `evaluate`'s docstring said passing a profile fitted
elsewhere "is the caller's error and cannot be detected here". Both halves were
wrong — `applies_to` existed and nothing called it. `evaluate` takes `regime`
and refuses a mismatch, and refuses an unknown regime too, because a profile
that cannot be shown to apply has not been shown to apply. Two existing tests
failed on this, which is the rule working: they now state which capture they
are measuring.

**The sequence test the verification asked for.** `test_question_lifecycle_api.py`
runs create → seed refinement metadata → change tolerance → reload → evidence →
export as one flow, plus a rejected-change test and a rebuilt-cloud test. Three
of the verification's findings were invisible to unit tests because every step
worked alone and only the *transitions* were broken. A sequence test is the
only shape that catches those.

**Frontend.** The evidence panel cached its response and never cleared it after
a refinement, so opening it showed the old frames beside the new value. It now
clears on refinement and on a tolerance change that re-measured.

441 tests pass, 15/15 audit checks pass, production frontend build passes.

## 2026-09-22 — UseGeo arrives and immediately finds a 1.25 m bias

Downloaded 60 contiguous frames of UseGeo dataset 1 plus its LiDAR reference,
built a mission, reconstructed it, and scored the dense cloud against the
RIEGL cloud. All 60 frames registered; 2,138,943 dense points at 0.129 m
spacing; 0.271 px median reprojection error.

Then the first accuracy number this project has ever had against an instrument
that is not photogrammetry: **median error 1.360 m**.

Almost all of it is one number. Horizontally the bias is under a centimetre
(−0.004 m E, −0.005 m N). Vertically it is **+1.245 m**. Remove that single
offset and the residual is 0.299 m.

I checked the obvious explanations and both fail. It is not vegetation: split
by LiDAR classification the offset is +1.267 m over 78.3 M unclassified points
and +1.166 m over 7.3 M classified medium vegetation — the same on hard surface
and canopy. It is not camera placement: our camera centres sit 0.53 m from the
authors' adjusted poses in 3D with only +0.27 m of vertical bias, a quarter of
the surface error.

The run's own manifest had already said why:

    degenerate: true
    degeneracy: planar trajectory (out-of-plane geometry is weakly constrained)
    alignment_rmse_vertical_m: 0.057

A constant-altitude nadir survey. The Sim(3) fit places cameras that lie in a
plane onto a plane with 5.7 cm vertical RMSE and constrains the ground 80 m
beneath them barely at all. The quality report's own warning — "alignment
residual is NOT independent accuracy; it measures consistency between
reconstructed camera centres and GPS" — turns out to be exactly, expensively
right.

**The system detected the degeneracy, wrote it to the manifest, and then
nothing read it.** No uncertainty widened. No measurement was refused. It
reported 0.093 m sigma on geometry that was 1.25 m out: interval coverage of
**4.6%** against a nominal 95%, the first coverage figure in the project's
history and a bad one.

I am quoting both ratios — 14.7× too optimistic raw, 3.2× debiased — because
the debiased number alone would hide precisely the failure this download
existed to find. That is the mistake DEC-024 caught in `as_georeferenced` nine
decisions ago and it would be poor to repeat it in the same week.

AGZ never showed any of this, because its flight varies 449–474 m in altitude.
A flat nadir survey is the more common commercial pattern, so the degeneracy
matters more in practice than the dataset we had been testing on.

Three smaller things fixed on the way. My `score_against_lidar.py` docstring
promised footprint-limited completeness and the code sampled the whole cropped
box, reporting a 24 m mean — it was measuring the flight plan, not the
reconstruction; it uses the convex hull now. The scorer also reported only the
debiased error at first, which is the DEC-024 mistake again, and now reports
the offset itself. And the mission builder's `read_intrinsics` claimed in its
docstring to convert the principal point while returning raw columns, including
a negative y0.
