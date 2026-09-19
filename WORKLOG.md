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
