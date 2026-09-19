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
