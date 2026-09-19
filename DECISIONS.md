# Architectural and Technical Decisions

New decisions are appended. Superseded decisions are marked, never rewritten.

---

## DEC-001 — Build the measurement and evidence layer on the existing pipeline rather than rebuilding the stack

**Date:** 2026-09-19

**Status:** Accepted

### Context

The repository already contains a working reconstruction stack: FastAPI backend,
React/Three.js viewer, two SfM engines, bundle adjustment, georeferencing,
uncertainty propagation, coverage, masking and an evaluation harness. The MVP
plan (`DRISHTI3D_MVP_PLAN.md`) asks for a product whose differentiation is
tolerance-aware measurement acceptance, evidence traceability and same-pass
refinement — none of which is reconstruction work.

### Options Considered

#### Option A — Rebuild the reconstruction stack around the new data contracts

Design `Mission`, `FrameObservation`, `SurfaceEvidence` and the rest first, then
reimplement geometry against them.

Advantages:
- Clean lineage from the start; no retrofit of observation IDs.
- The schema versioning the plan asks for falls out naturally.

Disadvantages:
- Discards a large body of measured work, including several fixes whose
  rationale is recorded in `drishti3d/docs/WORK_LOG.md` and would be relearned.
- Spends the whole budget on geometry that already exists and is not the
  differentiator.
- No working system at any intermediate point, so no measurable progress.

#### Option B — Add the measurement/evidence layer above the existing pipeline

Keep `pipeline.run` and its artifacts, add `questions.py`, `evidence.py` and the
API above them, and retrofit lineage where it is actually needed.

Advantages:
- The system stays runnable at every step, so each change is measurable against
  the previous one on real data.
- Effort goes to the differentiating features.
- The existing test suite keeps guarding the geometry.

Disadvantages:
- Observation lineage has to be retrofitted through fusion's downsampling and
  outlier removal, which is genuinely awkward.
- The artifact set was not designed as a schema-versioned contract, so
  compatibility is by convention until it is formalised.

### Decision

Option B. Plan section 8.3 (work packages WP1–WP7) is followed as a set of
additions to the existing modules.

### Why

The plan's own assessment is that this is "a product and measurement-model
upgrade, with reconstruction improvements where benchmark evidence justifies
them", and that rebuilding "would consume effort without creating
differentiation". Measuring on real data confirmed the existing geometry is
sound enough to build on: the COLMAP path reconstructs the AGZ single-pass
mission in 86 s with 0.32 m median shape error against the published reference.
That is a working foundation, not a liability.

### Consequences

- Observation lineage (WP1) is now the single blocking item for evidence replay,
  same-pass refinement and acceptance on view support. It is tracked as P0 in
  `NEXT_STEPS.md`.
- Artifact compatibility is by convention; a schema version field exists in
  `manifest.json` but nothing enforces it yet.
- Progress is measurable from day one against `datasets/truth/`.

### Related Files

`drishti3d/reconstruction/drishti_recon/pipeline.py`,
`questions.py`, `evidence.py`, `backend/app/routers/questions.py`

---

## DEC-002 — Reference data is physically separated from mission input

**Date:** 2026-09-19

**Status:** Accepted

### Context

The AGZ dataset ships reference camera positions alongside the imagery and logs.
If those positions reach the reconstruction — as GCPs, as an alignment target,
or as a hyperparameter selection signal — then scoring against them measures
nothing.

### Options Considered

#### Option A — Keep everything in one mission folder and rely on discipline

Advantages:
- Simpler layout; one place to look.

Disadvantages:
- A single careless `--telemetry truth.csv` invalidates every result produced
  afterwards, silently and irreversibly.
- The plan explicitly warns that "folder names alone do not prevent leakage",
  and discipline is not a mechanism.

#### Option B — Two roots, and the worker is only ever given one

`datasets/public/<set>/<mission>/` holds video, telemetry and calibration.
`datasets/truth/<mission>/` holds reference positions and any measured
dimensions. `run_mission.py` passes only the mission folder to `pipeline.run`,
then loads truth afterwards in a separate scoring function.

Advantages:
- Leakage requires an explicit code change in a named function, not a typo.
- The evaluator role is visible in the call structure.

Disadvantages:
- Two paths to keep in step when a mission is rebuilt.

### Decision

Option B. `scripts/build_agz_mission.py` writes the two roots and refuses to
place any reference value in the mission folder. `scripts/run_mission.py` calls
`pipeline.run(mission_dir/raw/...)` and only then calls `score(mission_dir,
truth_dir, artifacts)`.

### Why

The separation is cheap to build and the failure it prevents is unrecoverable:
a leaked reference produces results that look excellent and mean nothing, and
there is no later test that detects it. `datasets/truth/<mission>/README.md`
additionally records that the AGZ references are Pix4D photogrammetry by the
dataset authors, not independent survey truth — so even correct use of them is
an agreement measure, not an accuracy class.

### Consequences

- Scores are reported twice: as-georeferenced (translation removed only) and
  after a similarity fit. Reporting only the second is the usual way a drifting
  reconstruction is made to look accurate, so both appear together.
- When field data with real checkpoints arrives, the same two roots hold it
  without change.

### Related Files

`drishti3d/scripts/build_agz_mission.py`, `drishti3d/scripts/run_mission.py`,
`datasets/truth/agz_dense_pass/README.md`

---

## DEC-003 — Acceptance requires a validated calibration profile

**Date:** 2026-09-19

**Status:** Accepted

### Context

`uncertainty.py` propagates a 1-sigma for every measurement. The obvious
acceptance rule is "accept when 1.96·sigma ≤ tolerance". But a propagated sigma
is a *sensitivity model*: it accounts for the error sources that were modelled,
and says nothing about the ones that were not — pose error, calibration
residual, endpoint selection, correlated GNSS bias. Whether its intervals
actually contain the truth 95% of the time is an empirical question that has
not been answered for any capture regime here.

### Options Considered

#### Option A — Accept on the propagated interval, and label it "estimated"

Advantages:
- The product has a working green state immediately; the demo shows acceptance.
- The label arguably discloses the limitation.

Disadvantages:
- "Meets requirement" is read as a guarantee no matter what label sits beside
  it. Users act on the status, not the footnote.
- It is a calibrated-probability claim made without any coverage measurement.
- Nothing then forces the calibration work to happen.

#### Option B — Acceptance requires a `CalibrationProfile` for the capture regime, fitted on at least 20 independent samples and validated

Advantages:
- The strongest verdict the system can reach honestly is the strongest verdict
  it reaches.
- The missing work is visible in the product itself, as a reason code on every
  card, rather than buried in documentation.
- Calibration machinery already exists (`uncertainty.calibrate`,
  `conformal_factors`), so the profile is a wrapper, not new science.

Disadvantages:
- Today, **no measurement anywhere in the system can be accepted**. Every
  verdict is `estimated_only` or worse.
- A demo cannot show a green "meets requirement" card without first doing the
  calibration work.

### Decision

Option B. `questions.evaluate()` returns `MEETS_REQUIREMENT` only when a
`CalibrationProfile` is supplied, `profile.usable()` is true
(`validated` and `n_samples >= MIN_CALIBRATION_SAMPLES = 20` and conformal
factors present), and no blocking reason applies. The backend currently passes
`profile=None` unconditionally.

### Why

Twenty is not a statistical guarantee; it is the floor below which a 95% claim
is obviously unsupportable, since a distribution-free 95% bound needs at least
19 samples to exist at all. The plan states the rule directly: "Without
validated interval calibration, show an estimated range and **estimated only**,
not a calibrated probability claim", and "Disable the 'calibrated' label outside
supported regimes and until sample size is adequate."

The cost is real and was accepted deliberately: a system that cannot yet say
"yes" is more useful than one that says "yes" without grounds, because the first
can be fixed by data and the second cannot be distinguished from a correct one.

### Consequences

- Fitting and validating a calibration profile is on the critical path for any
  acceptance claim, and is P1 in `NEXT_STEPS.md`.
- `test_questions_api.py::test_uncalibrated_deployment_never_reports_meets_requirement`
  asserts this end to end: no tolerance, however loose, produces acceptance.
- A `CalibrationProfile` carries a `regime` string. Applying a profile outside
  its regime cannot be detected inside `evaluate()`; that remains the caller's
  responsibility and is a known weakness.

### Related Files

`drishti3d/reconstruction/drishti_recon/questions.py`,
`uncertainty.py`, `backend/app/routers/questions.py`,
`drishti3d/tests/test_questions.py`, `drishti3d/tests/test_questions_api.py`

---

## DEC-004 — Verified free space requires a finite depth return

**Date:** 2026-09-19

**Status:** Accepted

### Context

`coverage.py` classified a voxel as `EMPTY` — "swept by rays, verified to hold
no surface" — whenever any camera had an unobstructed line of sight to it. The
visibility test was `z <= nearest + occlusion_tol`, where `nearest` comes from a
per-camera z-buffer initialised to `+inf`. A pixel through which nothing was
ever reconstructed therefore reported `nearest = inf`, the comparison passed,
and the cell was published as verified free space.

`EMPTY` is the one class in the field that is a *positive* claim about the
world. Everything else says "we did not establish this". So a sparse cloud's
holes were being converted into assertions that a volume is clear.

The MVP plan identified this by code reading (section 3.2) before any test was
run: "A hole in a sparse cloud does not prove a clear corridor."

### Options Considered

#### Option A — Leave it, and rely on `is_measurable` refusing `EMPTY` anyway

Advantages:
- No change; no risk of shrinking coverage statistics that appear in reports.

Disadvantages:
- `fraction_explained` and the free-space overlay are both published, and both
  were overstated.
- The class is meant to support exactly the question "is this corridor clear",
  which is the question where a wrong answer matters most.

#### Option B — Require the ray to terminate on a finite, supported depth

Track a separate `free_count`: a ray contributes only where `nearest` is finite
**and** `z < nearest - occlusion_tol`. Classify `EMPTY` from `free_count`, not
from `view_count`.

Advantages:
- Free space becomes what it claims to be.
- The slack that forgives sparse occlusion is subtracted rather than added, so
  the uncertain metre in front of a surface is not declared clear either.
- Cells crossed only by no-return rays fall through to `OCCLUDED`, which reads
  as "we looked and established nothing" — the accurate statement.

Disadvantages:
- Reported free space shrinks substantially, which will look like a regression
  to anyone comparing coverage numbers across the change.

### Decision

Option B.

### Why

A coverage field whose free-space class cannot be trusted is worse than no
free-space class, because it is used precisely where the stakes are highest.
The shrink is not a regression; the earlier figure was counting unknown volume.

### Consequences

- `CoverageGrid` gained a `free_count` array, persisted in `coverage.npz`.
- `meta["free_space_requires_finite_depth"] = True` marks grids built under the
  new rule, so an old artifact is distinguishable from a new one.
- Coverage statistics are not comparable across this change. On the AGZ mission
  after the fix, `EMPTY` is 145,399 of 2,463,552 cells (5.9%).
- Three regression tests pin the behaviour, including one asserting that no
  `EMPTY` cell lies behind the surface that terminated its rays.

### Related Files

`drishti3d/reconstruction/drishti_recon/coverage.py`,
`drishti3d/tests/test_timing_and_freespace.py`

---

## DEC-005 — Frame timestamps are read after decode, and the backend convention is detected rather than assumed

**Date:** 2026-09-19

**Status:** Accepted

### Context

The pipeline read `CAP_PROP_POS_MSEC` *before* each `cap.read()`, on the
documented reading that the property refers to the frame about to be decoded.
Measured on OpenCV 5.0.0 in this checkout, that is not what happens: the
pre-read series starts with a duplicate zero and lags the true presentation
timestamp by exactly one frame. `_adopt_pts` then rejected it for not being
strictly increasing and silently fell back to `frame_index / fps`.

For constant-rate video the fallback is correct and the bug is invisible. For
the variable-frame-rate missions built from AGZ stride subsamples, frames are
one second apart, so the error is a full second per frame — about 1.2 m of
drone travel, paired against the wrong GNSS sample.

### Options Considered

#### Option A — Switch to reading after `read()`

Advantages:
- Correct on this build, and one line.

Disadvantages:
- Backends genuinely differ. A build where the post-read value is the *next*
  frame's timestamp would then be shifted one frame the other way, and nothing
  would detect it.

#### Option B — Sample both sides and pick the self-consistent series

Record pre- and post-read values. Prefer the pre-read series when it is usable
(strictly increasing, not all zero) since that is the documented reading; fall
back to the post-read series when the pre-read one is not. Keep the existing
all-zero, non-monotonic and span-sanity rejections.

Advantages:
- Correct on both conventions, and which one was used is reported in the run
  warnings.
- The failure mode is a fallback to the nominal clock, not a silent one-frame
  shift.

Disadvantages:
- One extra property read per decoded frame — negligible against decoding cost.

### Decision

Option B.

### Why

The cost of the general solution is one function call per frame. The cost of
guessing wrong is every frame paired with the wrong telemetry sample, with no
symptom other than a slightly worse reconstruction that would be attributed to
something else.

### Consequences

- Run warnings now state which convention was used: *"video timestamps read
  after decode: this backend reports POS_MSEC for the frame just returned"*.
- Variable-frame-rate missions are correctly timed for the first time; the AGZ
  run reports a 1.264 s divergence from the nominal clock, which is exactly the
  error that was previously being absorbed.
- Three regression tests pin all three paths.

### Related Files

`drishti3d/reconstruction/drishti_recon/pipeline.py`
(`_adopt_pts`, `_usable_pts`, the decode loop),
`drishti3d/tests/test_timing_and_freespace.py`

---

## DEC-006 — View support is stamped with its basis, and a frustum-derived basis cannot license acceptance

**Date:** 2026-09-19

**Status:** Accepted

### Context

The acceptance rules need to know how many views support a measurement and how
much parallax they provide. The point cloud cannot answer this: `cloud.npz`
stores positions, colours, confidence and provenance, and fusion's voxel
downsample and statistical outlier removal reindex the cloud without carrying
track identity across. There is no lineage from a point back to the image
observations that produced it.

What *can* be computed today is camera geometry: which cameras have the point in
front of them and inside the image, and whether the coverage grid says the
sight line is clear. That counts cameras which may never have contributed an
observation, so the parallax it yields is an upper bound.

### Options Considered

#### Option A — Use the frustum figures as if they were support

Advantages:
- Measurements get plausible view counts immediately; the evidence panel looks
  complete.

Disadvantages:
- An upper bound on parallax used as evidence of parallax is optimistic in
  exactly the direction that matters. A point seen along one direction by
  cameras that happen to have it in frame would clear the degeneracy check.

#### Option B — Report the figures, stamp their basis, and treat a non-lineage basis as blocking

`Evidence.view_support_basis` is `"frustum_upper_bound"` or
`"triangulated_observations"`. Anything other than the latter adds
`Reason.VIEW_GEOMETRY_UNVERIFIED`, which is in the blocking set.

Advantages:
- The numbers are still shown, and they are genuinely informative for ranking
  candidate frames.
- The reason code names the actual gap rather than mislabelling it as
  degenerate view geometry.
- When WP1 lands, flipping the stamp lifts the block with no rule change.

Disadvantages:
- Another reason why nothing can be accepted today, on top of DEC-003.

### Decision

Option B.

### Why

The distinction between "cameras that could have seen this" and "observations
that produced this" is the whole difference between evidence and plausibility,
and it is the distinction the product exists to maintain. Naming it precisely
costs one enum value.

### Consequences

- `GET /api/projects/{id}/questions/{qid}/evidence` returns
  `support_basis: "frustum_upper_bound"` and says so in its `note`.
- Acceptance now has two independent blockers: no calibration profile
  (DEC-003) and no observation lineage (this one). Both are tracked in
  `NEXT_STEPS.md`.

### Related Files

`drishti3d/reconstruction/drishti_recon/evidence.py`, `questions.py`,
`backend/app/routers/questions.py`

---

## DEC-007 — Additive startup migration for the development SQLite database

**Date:** 2026-09-19

**Status:** Accepted

### Context

Adding acceptance columns to `measurements` and a new `measurement_questions`
table broke existing databases: `Base.metadata.create_all()` creates missing
*tables* and silently leaves existing ones alone, so the first query against an
older database raised `OperationalError: no such column`.

### Options Considered

#### Option A — Adopt Alembic now

Advantages:
- The right answer for anything that ships to more than one machine.
- A reviewable migration history.

Disadvantages:
- A migration history nobody maintains is worse than none, and there is one
  developer and one database today.
- Every schema change during rapid MVP work becomes a migration file.

#### Option B — Delete and recreate the development database on schema change

Advantages:
- Trivial.

Disadvantages:
- Destroys stored measurements, which are becoming the product's actual output.

#### Option C — An idempotent, additive-only `ALTER TABLE` pass at startup

Compare the declared columns against `inspect(engine)` and add what is missing.
Never drop, never retype.

Advantages:
- Existing databases keep working through additive changes without ceremony.
- Refuses to do the destructive half, so it cannot silently lose data.

Disadvantages:
- Does not handle renames, type changes or data migrations at all, and will
  quietly do nothing useful when one is needed.

### Decision

Option C now; Alembic when the project leaves a single workstation or needs its
first non-additive change.

### Why

Every schema change so far has been additive. The failure mode of Option C is
loud (`OperationalError` on a non-additive change) rather than silent data loss.

### Consequences

- `db.init_db()` calls `_add_missing_columns()` after `create_all`.
- The first non-additive schema change must introduce Alembic; this is recorded
  in `NEXT_STEPS.md` as P2.

### Related Files

`drishti3d/backend/app/db.py`, `drishti3d/backend/app/models.py`

---

## DEC-008 — COLMAP is the reconstruction engine to develop against

**Date:** 2026-09-19

**Status:** Accepted

### Context

The repository carries two SfM engines. Plan section 5.3 recommends starting the
field reference implementation with COLMAP and keeping the in-repo OpenCV engine
as a transparent CPU fallback, but the repository's own history records changes
that looked reasonable and made reconstruction worse, so the recommendation
needed measuring on this data rather than adopting.

### Options Considered

Both engines were run on the identical AGZ single-pass mission, 184 frames,
identical intrinsics, distortion coefficients and epipolar band.

| | OpenCV engine | COLMAP engine |
|---|---|---|
| Wall clock | 291 s | 86 s |
| SfM stage | 274 s | 78 s |
| Keyframes / registered | 80 / 80 | 80 / 80 |
| Error vs reference, as georeferenced | 3.70 m median | 3.76 m median |
| Error vs reference, after Sim(3) | 0.68 m median | **0.32 m median** |
| Mean track length | 2.78 | 3.90 |
| Median reprojection error | 0.23 px | 0.33 px |
| Fitted scale | 0.978 | 0.978 |

### Decision

COLMAP becomes the engine new work is developed and benchmarked against. The
OpenCV engine is retained, tested, and remains the fallback where PyCOLMAP is
unavailable. The pipeline default is unchanged for now — changing it is a
separate change with its own regression run.

### Why

COLMAP is 3.4× faster and halves the shape error on the same input. The longer
mean track length (3.90 vs 2.78 observations per point) is the mechanism: more
views per point is what makes triangulation better conditioned, and it is also
what a future observation-lineage layer has to work with.

The as-georeferenced figures being indistinguishable (3.70 vs 3.76 m) is the
more important reading: at ±9.4 m eph, absolute accuracy is set by the receiver,
not by the engine. Choosing an engine on that number would have found no
difference at all.

### Consequences

- Benchmarks default to `--engine colmap`.
- PyCOLMAP becomes a hard dependency for the reference path; the OpenCV engine
  keeps the software runnable without it.
- Both engines registered only 80 of 184 frames — keyframe selection discarded
  the rest before SfM saw them. That is an engine-independent problem and is P1
  in `NEXT_STEPS.md`.

### Related Files

`drishti3d/reconstruction/drishti_recon/colmap_adapter.py`, `sfm.py`,
`pipeline.py`, `drishti3d/scripts/run_mission.py`,
`drishti3d/docs/benchmarks/2026-09-19_agz_single_pass_engines/RESULTS.md`

---

## DEC-009 — Observation lineage is carried as a separate artifact, and a merged-away point donates nothing

**Date:** 2026-09-19

**Status:** Accepted

### Context

[DEC-006](#dec-006--view-support-is-stamped-with-its-basis-and-a-frustum-derived-basis-cannot-license-acceptance)
predicted that flipping the view-support stamp would lift its block "with no
rule change" once lineage existed. Building it raised four questions the
prediction did not settle.

Measured on the AGZ mission, the gap being closed is not academic. Over 400
sampled points, frustum geometry reports a median of 11 supporting views where
the measurements provide 3 (3.0×), and a median parallax of 81.1° where the
measurements provide 20.5° (3.7×).

### Options Considered

#### Where lineage lives

Inside `cloud.npz`, or beside it.

Lineage is one row per *observation*, not per point — 69,173 rows against
17,897 points on the AGZ mission. Packing ragged per-point lists into the
per-point archive would either pad to the maximum track length or store object
arrays, and every consumer that wants only geometry would pay to load it.

**Decided:** a separate `observations.npz` with flat parallel arrays
(`point_index`, `keyframe_index`, `frame_index`, `uv`).

#### What a voxel-merged point inherits

Voxel downsampling keeps one representative per cell and drops the rest.

*Union the merged points' observations into the survivor* — maximises apparent
support, but the survivor is a different position, and the discarded points'
measurements were of different surface. That is precisely the overstatement the
whole path exists to prevent, arriving by a new route.

*The survivor keeps only its own observations* — understates support for a
point that stands in for several, and drops the discarded points' measurements
entirely.

**Decided:** the survivor keeps only its own. Understating is the safe
direction; overstating is not recoverable by any later check.

#### Which frame number a measurement is keyed by

The solver numbers frames by *keyframe index*; the exported cameras and the
mission's `frame_index.csv` use the *decoded frame index*. Keyframe selection
decimates, so on the AGZ mission keyframe 1 is decoded frame 2.

Storing one and deriving the other at read time is how the two get confused. It
was confused during implementation: the camera lookup was keyed by decoded index
while observations were looked up by keyframe index, which resolved to no camera
at all and reported **zero** parallax on points measured from a wide baseline —
a failure that looks exactly like a correctly detected degenerate capture.

**Decided:** store both, in every observation row. `_camera_of_frame` is keyed
by the decoded index and observations are resolved through `frame_index`.
`test_frame_numbering_is_not_guessed_between` pins it.

#### How far a selection may sit from a point and still inherit its lineage

An operator clicks in 3D space, not on a cloud point.

**Decided:** snap within `LINEAGE_SNAP_FACTOR = 2.0` times the cloud's median
nearest-neighbour spacing, and fall back to the frustum basis beyond that.
Roughly "the selection is on this point". A cloud too small to have a spacing at
all requires an exact hit rather than admitting everything or nothing.

### Decision

All four as above. `ReconResult` gained `obs_point` / `obs_frame` / `obs_uv`,
produced by both engines; `PointCloud` gained `source_index`;
`pipeline._remap_observations` inverts that map onto the fused cloud;
`evidence.py` prefers lineage and stamps `triangulated_observations`.

### Why

The decisions share one rule: where the honest answer is unknown, take the
option that understates support. Merged points donate nothing, a distant
selection inherits nothing, an ambiguous frame number is never guessed. Each
costs some measurements that would have been accepted; the alternative costs
the meaning of acceptance.

### Consequences

- `VIEW_GEOMETRY_UNVERIFIED` no longer fires on either engine's output. On the
  AGZ mission the only remaining blocker is `INTERVAL_NOT_CALIBRATED`, so
  acceptance now depends solely on the calibration work in DEC-003.
- Evidence Replay (plan F3) and same-pass refinement (F4) are unblocked: every
  measurement can name its frames and the pixel each was measured at.
- `observations.npz` adds roughly 1.1 MB per mission at AGZ's density.
- A measurement whose *worst* endpoint lacks lineage is reported as
  frustum-derived in full. Mixing the two bases within one measurement would
  produce a figure belonging to neither.
- Lineage covers triangulated geometry only. Depth-prior points carry
  `source_index = -1` and are unaffected, as they were never triangulated.

### Related Files

`drishti3d/reconstruction/drishti_recon/sfm.py`, `colmap_adapter.py`,
`fusion.py`, `pipeline.py` (`_remap_observations`, `_write_artifacts`),
`evidence.py`, `backend/app/routers/questions.py`,
`drishti3d/tests/test_lineage.py`, `drishti3d/tests/test_evidence.py`

---

## DEC-010 — Same-pass refinement recovers frames by PnP against the existing model, and is judged on what it unblocks

**Date:** 2026-09-20

**Status:** Accepted

### Context

Plan feature F4. Keyframe selection discards most of a single pass — 104 of 184
decoded frames on the AGZ development mission. Those frames were flown and
never processed. The claim to test is that spending a bounded budget on the
frames that would help *one* measurement beats spreading the same budget
uniformly.

Building it raised four questions.

### Options Considered

#### How a recovered frame gets a pose

*Re-run global SfM with the extra frames* — correct, and far outside any
interactive budget; it also changes the geometry every stored measurement was
taken against.

*Interpolate between the registered cameras that bracket it in time* — free,
but it is a guess about where a camera was, and nothing measured against it
would be evidence.

*PnP against the existing model* — matches into temporally neighbouring
registered frames land on pixels whose 3D points the model already knows, which
turns 2D-2D matches into the 2D-3D correspondences PnP needs.

**Decided:** all three, in their proper roles. Interpolation gives *tentative*
visibility, used only to decide what is worth decoding. PnP gives the real pose.
Global re-solving is out of scope and named as such. Measured on AGZ, PnP
recovers 571–1378 inliers at 1.2–1.3 px reprojection RMSE, and the recovered
centres agree with the interpolated ones to 0.09–0.38 m — an independent check
that the tentative poses were reasonable and the recovered ones are real.

#### How the endpoint is located in a recovered frame

*Project it through the recovered pose and accept that pixel* — circular. The
new ray would pass exactly through the estimate it came from, adding no
information while narrowing the interval. That is worse than not refining.

*Match the recovered frame against a frame that measured the endpoint* — the
frames that measured an endpoint can sit anywhere in the pass. On AGZ the
nearest were 25 frames away, about 32 m of flight, and matching across that
returned 74 matches out of 4000 keypoints, almost all wrong.

**Decided:** pose-guided search. The projection bounds a
:data:`LOCATE_SEARCH_PX` window; what is accepted is a keypoint the detector
found *independently* inside it whose descriptor matches the endpoint's
appearance in a frame that measured it, passing a ratio test. The prediction is
a prior on where to look, never the measurement.

#### Which candidate to spend the budget on

*Maximum parallax gain* — the obvious answer, and wrong. The frames that add
the most parallax are the same frames whose view of the surface has changed the
most. On AGZ the top-ranked candidate added 70° of parallax and produced a
best-to-second descriptor ratio of 0.85: correctly refused as ambiguous, and a
wasted decode. Every one of the top candidates failed the same way.

**Decided:** rank by parallax gain discounted past
:data:`MATCHABLE_GAIN_DEG` = 25°, where descriptor matching starts to fail.
The ranking peaks at usable geometry rather than at maximum geometry.

#### What counts as an improvement

*A narrower interval* — the natural definition, and it would have called the
feature a failure. A run that recovered three frames moved the value by 0.104 m
and the interval by 0.001 m, because the interval was dominated by the *other*
endpoint and by the 1.15% metric scale term. It nonetheless cleared
`insufficient_views`, which was the reason blocking that measurement.

**Decided:** report `reasons_cleared`, `interval_narrowed` and `value_change_m`
separately, and define `improved` as either a cleared blocking reason or a
narrower interval. The plan says it directly: "a narrower interval alone is not
proof of improvement."

### Decision

All four as above, in `reconstruction/drishti_recon/refinement.py`, exposed as
`POST /api/projects/{id}/questions/{qid}/refine` and persisted as
`RefinementRun` rows whether or not they achieved anything.

### Why

Every choice resolves the same tension: refinement must add *independent*
evidence or it adds nothing. A pose that came from interpolation, a pixel that
came from a projection, or an interval that narrowed because a recovered camera
was treated as exact would each produce a more confident answer built on no new
observation. Recovered cameras therefore carry
:data:`POSE_UNCERTAINTY_INFLATION` times the baseline pixel sigma, so adding
views narrows the interval by less than the geometry alone would suggest.

### Consequences

- **Measured outcome, 30 weak measurements on the AGZ mission, 4-frame budget,
  median 12.8 s each:** 10 of 30 recovered at least one frame and every one of
  those cleared a blocking reason (9 × `insufficient_views`, 1 ×
  `outside_established_coverage`). For those, supporting views went from a
  median of 2 to 4 and measured parallax from 8.1° to 15.5°. Median absolute
  change in the reported value was 0.032 m.
- **Two thirds recovered nothing**, overwhelmingly because the endpoint could
  not be matched into the recovered frame. That is the honest ceiling of
  descriptor matching across a changed viewpoint, not a tuning problem, and it
  is reported per frame with a reason rather than as a silent no-op.
- The refined endpoint's own triangulation sigma (~0.22 m on the worked
  example) is *larger* than the reconstruction's propagated sigma (~0.04 m),
  because the reconstruction's comes from full bundle adjustment and this comes
  from a standalone ray intersection. It is reported as `endpoint_sigma`
  alongside, and deliberately not substituted into the measurement's interval.
- **The paired experiment the plan's F4 gate actually asks for — targeted
  versus uniform refinement at equal added compute — has not been run.** What
  exists is an outcome survey. Until that experiment runs, the hypothesis is
  supported but not tested. Tracked in `NEXT_STEPS.md`.

### Related Files

`drishti3d/reconstruction/drishti_recon/refinement.py`,
`backend/app/routers/questions.py`, `backend/app/models.py` (`RefinementRun`),
`drishti3d/tests/test_refinement.py`

---

## DEC-011 — The COLMAP path ships no per-point uncertainty, so its measurements cannot be reported

**Date:** 2026-09-20

**Status:** Accepted — as a documented defect, not a resolution

### Context

[DEC-008](#dec-008--colmap-is-the-reconstruction-engine-to-develop-against)
made COLMAP the engine to develop against: 3.5× faster, half the shape error.
Building refinement on top of it exposed that `cloud.npz` from a COLMAP run
contains only `points`, `colors`, `confidence` and `provenance` — no `sigma`,
no `sigma_major`.

`colmap_adapter.reconstruct_frames` never populates `ReconResult.point_cov`,
`point_sigma` or `point_sigma_major`; only the in-repo engine's
`uncertainty.point_covariances` pass does. Every endpoint on a COLMAP
reconstruction therefore snaps to a point whose sigma is infinite, and
`questions.evaluate` correctly returns `not_observable` with
`uncertainty_undefined`.

So the better engine currently produces reconstructions on which **no
measurement can be reported at all**, and the worse one produces measurable
ones. That is the opposite of what DEC-008's benchmark implies.

### Options Considered

#### Fall back to a default sigma on the COLMAP path

Advantages: measurements start working immediately.

Disadvantages: a made-up sigma is a made-up interval, and it would flow
straight into acceptance once calibration exists. This is precisely the failure
DEC-003 exists to prevent, arriving through the back door.

#### Revert DEC-008 and default to the in-repo engine

Advantages: the complete path works today.

Disadvantages: throws away a measured 3.5× speedup and half the shape error to
work around a missing feature rather than building it.

#### Record it, keep both engines, and run the uncertainty pass on COLMAP output

`uncertainty.point_covariances` takes observations, poses and intrinsics — all
of which the COLMAP adapter now has, since observation lineage landed
(DEC-009). It is a wiring job, not new mathematics.

### Decision

The third. DEC-008 stands for reconstruction quality; this decision records
that the engine choice is not yet safe for measurement, and the wiring is P1 in
`NEXT_STEPS.md`. Until it lands, measurement work runs on the in-repo engine
and the limitation is stated wherever engine results are compared.

### Why

The measured case for COLMAP is about geometry and is unaffected. The gap is a
missing uncertainty pass, and the inputs it needs now exist. Substituting a
placeholder sigma would make the product look finished while removing the one
property that makes its numbers worth anything.

### Consequences

- Any measurement or refinement demonstration must use an in-repo-engine
  reconstruction until this is wired.
- `TESTS_AND_RESULTS.md` records which engine produced each measurement result.
- Once wired, DEC-008's recommendation and the measurement path finally agree,
  and the COLMAP path's longer mean track length (3.91 vs 2.78) should give it
  *better* per-point uncertainty than the engine now being used.

### Related Files

`drishti3d/reconstruction/drishti_recon/colmap_adapter.py`,
`uncertainty.py` (`point_covariances`), `pipeline.py` fusion stage
