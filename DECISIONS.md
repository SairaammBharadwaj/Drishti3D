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

---

## DEC-012 — A refinement that degrades the verdict is never counted as an improvement

**Date:** 2026-09-20

**Status:** Accepted

### Context

Wiring per-point uncertainty into the COLMAP path (the remedy DEC-011 chose)
made COLMAP reconstructions measurable, so the refinement survey could be run on
a second engine for the first time. It reported 8 improvements in 30 — and two
of them were measurements that had become **unusable**.

The cause is in `questions.evaluate`: a hard refusal returns early carrying only
its hard-refusal reasons. A measurement that drops to `not_observable` therefore
sheds every soft reason it had, and a set difference over the reason lists reads
that as a clean sweep:

```
needs_refinement -> not_observable
  cleared: ["interval_exceeds_tolerance", "interval_not_calibrated"]
  interval_narrowed: true
```

Both statements are literally true. The measurement is worse.

It happens for a real reason, not a spurious one: a re-triangulated endpoint can
land outside established coverage, and the coverage gate then correctly refuses
it. Refinement genuinely can make a measurement unusable, and that has to be
visible.

### Options Considered

#### Suppress cleared reasons when the status regresses

Advantages: `reasons_cleared` then only ever means good news.

Disadvantages: hides that the reasons really did change, and the *why* — which
reason list a regressed run ended with — is exactly what diagnosing it needs.

#### Report the literal set difference, and gate `improved` on the status

Keep `reasons_cleared` as what it says. Add `reasons_added` and
`status_regressed`. Define `improved` as: no regression, **and** (a reason
cleared or the interval narrowed).

Advantages: every fact stays reportable, and the summary verdict cannot be
gamed by a degradation.

Disadvantages: three fields where a reader might want one.

### Decision

The second. `RefinementRun` exposes `reasons_cleared`, `reasons_added`,
`interval_narrowed`, `status_regressed` and `value_change_m` separately, with
`improved` derived from all of them. Verdicts are ordered
`not_observable < needs_refinement < estimated_only < meets_requirement`; an
unrecognised status is not treated as a regression.

### Why

This is the third time on this feature that the obvious summary metric has been
wrong in the flattering direction — first "the interval got narrower"
([DEC-010](#dec-010--same-pass-refinement-recovers-frames-by-pnp-against-the-existing-model-and-is-judged-on-what-it-unblocks)),
now "a reason went away". Both would have overstated what refinement achieves.
A feature whose whole claim is that it recovers evidence has to be measured by
something that cannot improve when the answer gets worse.

### Consequences

- The COLMAP survey's reported improvements fall from 8 to **6 of 30**, with
  **2 of 30 regressing** to `not_observable`. The in-repo engine's survey was
  re-run under the corrected metric and is unchanged at 10 of 30 with no
  regressions, so the two are comparable.
- Regression is a real outcome of refinement, now visible per run rather than
  counted as success.
- **DEC-011's remedy is implemented and measured.** COLMAP reconstructions now
  carry per-point uncertainty, estimated with the same MAD-based `sigma_px` the
  in-repo engine uses so an engine comparison is not also a comparison of two
  noise models. Measured over 60 in-coverage measurements per engine:

  | | COLMAP | in-repo |
  |---|---:|---:|
  | Median measurement sigma | 0.0638 m | 0.0687 m |
  | Blocked only by calibration | **51 / 60** | 10 / 60 |
  | Blocked by `insufficient_views` | 4 / 60 | 50 / 60 |

  COLMAP's longer mean track length (3.91 vs 2.78 observations per point) is
  what does this: far more measurements clear the three-view floor. Which also
  means **refinement has much less to fix on COLMAP** — 6 improvements in 30
  against 10, because fewer measurements had `insufficient_views` to clear.
  Fixing the engine reduced the need for the feature built to work around it.
- The pipeline default is still the in-repo engine. Changing it remains a
  separate task needing more than one mission.

### Related Files

`drishti3d/reconstruction/drishti_recon/refinement.py` (`RefinementRun`),
`colmap_adapter.py` (`_point_uncertainty`),
`drishti3d/tests/test_refinement.py`, `drishti3d/tests/test_colmap_uncertainty.py`

---

## DEC-013 — Same-pass refinement is demoted to an experimental feature: the F4 hypothesis is not supported

**Date:** 2026-09-20

**Status:** Accepted

### Context

Plan feature F4 is described as the project's "principal engineering
contribution", and its gate is a comparison, not a demonstration: *"on frozen
questions and equal added compute budgets, targeted refinement improves correct
accepted-answer yield or reaches the same quality faster than uniform
refinement."* The targeted arm was built, measured and shipped
([DEC-010](#dec-010--same-pass-refinement-recovers-frames-by-pnp-against-the-existing-model-and-is-judged-on-what-it-unblocks)).
The control had never been run.

It has now been, on 20 questions frozen before either arm executed
(`docs/benchmarks/2026-09-20_f4_targeted_vs_uniform/`).

| Metric | Targeted | Uniform |
|---|---:|---:|
| Added compute | 210.5 s | **135.4 s** |
| Measurements with fewer blockers | 2 / 20 | **8 / 20** |
| Measurements with a narrower interval | 1 / 20 | **14 / 20** |
| Verdict moved up | 0 / 20 | **4 / 20** |
| Median sigma | 0.151 → 0.151 m | 0.151 → **0.092 m** |
| Blockers cleared per added minute | 0.57 | **3.55** |

Truncated to the uniform arm's exact budget, the targeted arm reached 12 of 20
questions and cleared 1 blocker against the uniform arm's 8.

### Options Considered

#### Keep the feature's billing and attribute the loss to tuning

The ranking discount, the budget, the decode cap and the match ratio are all
adjustable, and the endpoint-location failure rate is the obvious lever.

Advantages: the headline claim survives while the parameters are explored.

Disadvantages: the gap is not marginal — 8 against 2 on 64% of the compute —
and three of the reasons uniform wins are structural, not parametric. A global
solve improves every point's covariance at once, a denser cloud gives every
endpoint a better point to snap to, and neither is something the targeted arm
can reach by tuning. Continuing to bill an unproven mechanism as the principal
contribution while searching for a configuration that wins is how a result gets
manufactured.

#### Remove the feature

Advantages: the honest response to a failed hypothesis, if the feature did
nothing.

Disadvantages: it does something measurable. It recovers frames for roughly a
quarter to a third of weak measurements, and when it does it raises supporting
views and measured parallax and clears `insufficient_views`. Removing a working
mechanism because it lost one comparison on one mission overcorrects, and
throws away the infrastructure — full-clip candidate indexing, PnP
re-registration, pose-guided location — that the retry needs.

#### Demote it to experimental, publish the loss, and name the retry

Keep the code and the API. Stop claiming the hypothesis holds. State the
observed benefits and the comparison it lost.

### Decision

The third, which is what the plan's own stop/go rule prescribes: *"If same-pass
refinement does not beat uniform processing, retain it as an experimental
feature and demonstrate only its observed benefits. Do not claim the main
hypothesis succeeded."*

### Why

The result is clear enough not to be explained away and narrow enough not to be
generalised. One mission, one scene, 20 questions, no truth to score error
against — so it does not establish that targeted refinement cannot work. It does
establish that on the one capture where it has been tested, it loses, and that
is the claim the product had been making.

The most likely reason is also the most actionable: the targeted arm was
deliberately denied a local bundle adjustment (DEC-010, scope), so it adds rays
to a single point in isolation while the control re-solves everything. That is a
fair fight only if the targeted arm gets to refine the connected neighbourhood,
which plan section 5.7 step 4 actually calls for and which was not built.

### Consequences

- `PROJECT_OVERVIEW.md` lists same-pass refinement as **experimental**, with the
  loss stated where the feature is described.
- No claim that the innovation hypothesis is supported may be made anywhere,
  including in demonstrations, until the retry below wins a rerun of this gate.
- The retry is specified in `NEXT_STEPS.md`: give the targeted arm the local
  bundle adjustment of plan section 5.7 step 4, and rerun this exact experiment
  against the same frozen questions.
- The regime this experiment cannot speak for is named: a capture where most of
  the scene is adequately covered and a few measurements are not. Building one
  is a separate task.
- `eval/f4_experiment.py` and its frozen question set are kept so the rerun is a
  rerun and not a new experiment.

### Related Files

`drishti3d/eval/f4_experiment.py`,
`drishti3d/docs/benchmarks/2026-09-20_f4_targeted_vs_uniform/`,
`drishti3d/reconstruction/drishti_recon/refinement.py`

---

## DEC-014 — Targeted refinement gets a local refit; it ties on yield and still loses on speed

**Date:** 2026-09-20

**Status:** Accepted

### Context

[DEC-013](#dec-013--same-pass-refinement-is-demoted-to-an-experimental-feature-the-f4-hypothesis-is-not-supported)
recorded the F4 gate's failure and named the most likely cause: the targeted arm
adds rays to a single point in isolation while the control re-solves every pose
and point. Plan section 5.7 step 4 asks for "local re-match and refit with a
connected boundary to the global model", and that had never been built
([DEC-010](#dec-010--same-pass-refinement-recovers-frames-by-pnp-against-the-existing-model-and-is-judged-on-what-it-unblocks),
scope). This is that retry, against the same frozen questions.

### Options Considered

#### How to hold the boundary

`bundle.bundle_adjust` has no fixed-camera mask. Adding one means restructuring
the parameter packing, the sparsity pattern and the analytic Jacobian of a
well-tested solver.

*Restructure the solver.* Faithful to "fixed boundary", and the riskiest change
available to a module every reconstruction depends on.

*Solve the subproblem free, then re-anchor.* A subproblem solved in isolation
drifts in all seven similarity degrees of freedom, so it is Sim(3)-fitted back
onto its boundary cameras' stored centres and rejected if they had to move more
than a metre — which would mean the solve did not stay local.

**Decided:** re-anchor. Measured drift on a representative refit is 0.054 m at
an anchor scale of 0.9993, so the subproblem is not wandering; the rejection
threshold exists for when it does.

#### What the refined endpoint's uncertainty means

Plan section 5.7 step 5: *"Retain global uncertainty at that boundary; fixing
neighbouring cameras must not make the interval artificially certain."*

The refit alone reported **0.006 m** on a point whose surrounding cloud is known
to about 0.036 m — an order of magnitude better than the model it sits in. That
is the artificial certainty the plan warns about, arriving exactly where it said
it would.

**Decided:** combine the refit's own covariance in quadrature with the
neighbourhood's existing uncertainty, taken as the median `sigma_major` of the
refit's points in the stored cloud. Refinement can improve where the endpoint
sits *within* its neighbourhood; it cannot improve where the neighbourhood sits.

#### Whether the coverage gate can judge a moved endpoint

Refined endpoints landed in `OCCLUDED` cells and were refused as
`outside_established_coverage`. The occluder is the endpoint's **own stale
position**: the coverage grid's z-buffer was built from the pre-refinement
cloud, where the point sat up to a metre nearer along the same ray. It occludes
itself.

*Keep the refusal.* Safe, and converts the feature's successes into refusals for
a reason that is an artefact of ordering.

*Rebuild the grid per refinement.* Correct and far outside an interactive
budget.

*Take the refined endpoint's coverage from the frames that measured it.* The run
located the point in each recovered image and re-triangulated it from those
rays; cameras demonstrably see it. That is a stronger statement than a grid
formed before the point moved.

**Decided:** the third, for the refined endpoint only. Every other endpoint is
still checked against the grid. This loosens a safety gate and is the change in
this decision most worth re-examining if refined measurements later prove
unreliable.

### Decision

Build `RefinementEngine._local_bundle`, with all three treatments above, and
rerun the F4 gate against the same `questions_frozen.json`.

### Why

The gate is a comparison, and the previous run compared an arm with a bundle
adjustment against one without. Whatever the answer, it had to be retried on
equal mechanism before "targeted refinement loses" could mean anything about
targeting rather than about the scope of what was built.

### Consequences

| Metric | Targeted, no refit | Targeted, refit | Uniform |
|---|---:|---:|---:|
| Added compute | 210.5 s | 219.8 s | **135.4 s** |
| Blocked only by calibration, after (from 8) | 7 | **10** | **10** |
| Measurements regressed | 1 | **0** | 5 |
| Narrower interval | 1 | 4 | **14** |
| Median sigma | 0.151 → 0.151 m | 0.151 → 0.128 m | 0.151 → **0.092 m** |

- **The refit worked and the verdict held.** The targeted arm now ties the
  control on answer yield and regresses nothing against the control's five, but
  takes 1.6x the compute to get there. The gate asks for better yield *or* the
  same yield faster; it delivers neither. DEC-013's demotion stands.
- **The binding constraint moved.** It is no longer the refit, it is reach: only
  5 of 20 questions had any frame recovered, so 15 were untouchable. On the five
  it reached, four intervals improved, two cleared blockers, none regressed, and
  the worst measurement's sigma fell 47%. Improving endpoint location is now the
  change most likely to alter this result, and is P1.
- A genuine difference in risk profile is now visible: the control clears more
  (8 against 2) *and* breaks more (5 against 0). For a product whose claim is
  that it does not overstate what it knows, that is not a neutral trade.
- Three of this decision's mechanisms are approximations with named failure
  modes — the Sim(3) re-anchor, the quadrature uncertainty combination, and the
  coverage exemption. None is validated against truth, because this mission has
  none.

### Related Files

`drishti3d/reconstruction/drishti_recon/refinement.py` (`_local_bundle`,
`measurement_value_fn`, `_call_value_fn`), `evidence.py`
(`for_points(endpoints_within_coverage=...)`, `sigma_major`),
`drishti3d/eval/f4_experiment.py`,
`drishti3d/docs/benchmarks/2026-09-20_f4_targeted_vs_uniform/`

---

## DEC-015 — Endpoints are located by transferring through dense correspondences, not by re-identifying a keypoint

**Date:** 2026-09-20

**Status:** Accepted

### Context

[DEC-014](#dec-014--targeted-refinement-gets-a-local-refit-it-ties-on-yield-and-still-loses-on-speed)
left reach as the binding constraint on same-pass refinement: 15 of 20 questions
in the F4 gate had no frame recovered at all, because the endpoint could not be
found in a recovered frame. Measured directly on 75 candidates from 25 weak
endpoints, the shipping locator succeeded on **1.3%** of them.

Diagnosis, from counting where each attempt died:

- **The endpoint's own descriptor often cannot be read.** The reconstruction's
  observations sit at *its* detector's keypoints. Matching COLMAP's stored
  observations against a fresh OpenCV SIFT detection gives a median separation
  of 8.9 px; only 212 of 1,852 have a redetected keypoint within 3 px. This
  killed 31 of 60 attempts.
- **Where it can be read, it does not discriminate.** At the final match the
  best-to-second ratio has a median of 0.93, with the best descriptor distance
  at 388 against the ~123 seen between adjacent frames. Across the viewpoint
  change worth recovering, SIFT does not recognise the surface. This killed most
  of the rest.

### Options Considered

#### Compute the descriptor directly at the stored pixel

Sidesteps the detector mismatch by describing the exact location rather than
hunting for a keypoint there.

**Measured and rejected.** Upright SIFT at an arbitrary pixel separates true
correspondences from random pixels by only 1.6–1.9x, against roughly 4x for
descriptors at detected keypoints. An arbitrary pixel is frequently on texture
that is not distinctive, and orientation has to be fixed by convention on both
sides, which loses more.

#### Widen the radius and take the nearest keypoint's descriptor

Cheap, and wrong: a keypoint 8 px away is a different feature. Tracking it would
measure a different 3D point and attribute the result to the endpoint — about
0.18 m of error at this range.

#### Chain the descriptor through intermediate frames

Re-read the descriptor at each registered frame between the measuring frame and
the recovered one, so appearance never has to survive the full viewpoint change
in one step.

**Built and measured: 1.3% → 10.7%.** Real, and not enough. The chain completed
zero hops in the median case, because each hop still needs a descriptor read
that the detector mismatch defeats.

#### Transfer the location through dense correspondences

Match the two frames densely, fit a local affine from the correspondences near
the endpoint's known pixel, and push the pixel through it. No keypoint has to be
found twice.

**Built and measured: 40.0% located, 36% accepted by the refit.**

### Decision

Transfer, with LightGlue as the matcher where available and the PnP matcher as a
fallback. Accepted only when the transferred pixel agrees to
`TRANSFER_AGREEMENT_PX` = 25 px with the pose-projected prediction.

### Why

The problem was misframed for three iterations. Re-identifying one keypoint
across a large viewpoint change is a hard problem that this system does not need
to solve: it already knows where the endpoint is in the anchor frame, and it
needs the same location in another. That is a transfer problem, and a dense
correspondence field solves it without identification.

The agreement check is what keeps it a measurement rather than a projection. The
two estimates share no inputs — one comes from image correspondences, the other
from the recovered pose and the current 3D estimate — so agreement between them
is evidence. Accepting the projection itself would make the new ray pass through
the estimate that produced it, which is the circularity this whole path has been
guarding against since [DEC-010](#dec-010--same-pass-refinement-recovers-frames-by-pnp-against-the-existing-model-and-is-judged-on-what-it-unblocks).

### Consequences

- **Reach went from 5 of 20 questions to 16 of 20**, and with it the F4 gate's
  result: the targeted arm now produces a higher answer yield than the uniform
  control (14 of 20 blocked only by calibration against 10), with zero
  regressions against the control's five. It is still not cheaper — 206.7 s
  against 135.4 s — and at matched budget the two are level.
- Supporting views went 3 → 6.5 and measured parallax 9.56° → 26.75°, against
  the control's 3 → 3 and 9.56° → 10.26°.
- **A learned matcher is now on the refinement path.** LightGlue/DISK is
  Apache-2.0 via kornia, unlike some checkpoints in this repository, but it is a
  new runtime dependency for a feature that previously needed none, and it
  wants a GPU. The fallback to the classical matcher exists and is untested at
  scale.
- The matcher is cached at module scope, not per engine. Per-engine loading
  filled an 8 GB card over twenty questions and took one of them from a
  12-second median to 74 minutes.
- Transfer assumes the surface around the endpoint is locally planar over
  `TRANSFER_RADIUS_PX` = 160 px. On a depth discontinuity the affine fit is
  wrong, and the 25 px agreement check is the only thing that catches it.

### Related Files

`drishti3d/reconstruction/drishti_recon/refinement.py`
(`_locate_by_transfer`, `_transfer_backend`, `_detect_cached`,
`_chained_descriptors`), `features.py`,
`drishti3d/docs/benchmarks/2026-09-20_f4_targeted_vs_uniform/`

---

## DEC-016 — The F4 advantage reproduces on further test beds, but they are one flight

**Date:** 2026-09-20

**Status:** Accepted

### Context

[DEC-015](#dec-015--endpoints-are-located-by-transferring-through-dense-correspondences-not-by-re-identifying-a-keypoint)
left the targeted arm beating the uniform control on answer yield for the first
time — on one mission, twenty questions. The top of the backlog was a second
capture, to find out whether that was a property of the method or of that
particular imagery.

### What happened

**The genuine second capture could not run the experiment.**
`agz_segment_two` (62 frames, 2.8 m median baseline) keeps all 62 frames at
every keyframe preset: `keyframes.select` declines to thin a capture whose
inter-frame image shift already exceeds its sparse-capture guard, which exists
because thinning a photo-survey-like capture destroys it. So the targeted arm
has no candidate pool and the uniform arm has nowhere to go. No denser frame set
for those image ids exists on disk.

That is a finding in itself: **the F4 comparison only means anything on a
capture that is over-sampled relative to what reconstruction needs.**

The fallback was `agz_dense_pass` split into two halves by image id — different
scene content, same flight, and their georeferencing differs sharply (0.41 m
against 4.73 m median as-georeferenced error), so they are not the same scene
twice.

| Test bed | Baseline | Targeted | Uniform | Targeted regressions | Uniform regressions |
|---|---:|---:|---:|---:|---:|
| `agz_dense_pass` (full) | 8 | **14** | 10 | **0** | 5 |
| `agz_dense_firsthalf` | 7 | **13** | 5 | **0** | 7 |
| `agz_dense_secondhalf` | 9 | **15** | 9 | **0** | 4 |

### Options Considered

#### Treat this as confirmation and drop the experimental label

Three test beds, consistent direction, a larger margin than the original, zero
regressions throughout.

Rejected: all three are partitions of **one flight**. Splitting a capture and
calling the pieces independent evidence is the kind of move this project has
spent its whole documentation trail refusing. The most informative test — the
one genuinely separate segment — could not be run.

#### Treat the failure on `agz_segment_two` as a null result and stop

Rejected in the other direction: it is not a null result, it is an
inapplicable one, and the reason is specific and recordable.

#### Report both, name the regime, keep the label

### Decision

The third. Same-pass refinement stays experimental. The benchmark write-up
states what the halves establish and what they cannot, and names the regime the
comparison requires.

### Why

The direction reproduced on two disjoint halves with markedly different
reconstruction quality, which rules out the original result being an artefact of
one question set or one part of the scene. It cannot rule out a property of this
flight, this camera, or this site, and no data in this checkout can.

### Consequences

- **A finding that did not appear on the full pass: the uniform arm made
  measurements worse.** On the first half, doubling the keyframes took answer
  yield from 7 down to 5 and regressed seven measurements — four of them newly
  `outside_established_coverage` — while its median measurement sigma rose from
  0.183 m to 0.260 m. A denser reconstruction is a different cloud, not a
  strictly better one: endpoints re-snap elsewhere and the coverage grid's
  boundaries move. "More frames is better" is not monotone in measurement
  standing.
- The targeted arm regressed nothing on any test bed. It does not rebuild the
  cloud, so it cannot move anything it was not asked about. For a product whose
  claim is that it does not overstate what it knows, that asymmetry is the more
  important half of this result.
- **The compute gap is now the clearer finding.** Break-even falls to about five
  questions on the halves against thirteen on the full pass, because the uniform
  arm's fixed cost is smaller there while the targeted arm's per-question cost
  is unchanged. Reducing that cost is what turns a split result into an
  unambiguous one, and it is P1.
- `scripts/build_agz_mission.py` gained `--imgid-min/--imgid-max`, so one flight
  can be cut into separate missions. Useful, and a tool that makes it easy to
  manufacture test beds that look independent and are not.

### Related Files

`drishti3d/eval/f4_experiment.py`, `drishti3d/scripts/build_agz_mission.py`,
`drishti3d/docs/benchmarks/2026-09-20_f4_second_capture/`,
`drishti3d/reconstruction/drishti_recon/keyframes.py`

---

## DEC-017 — Refinement decodes sequentially and caches detections across measurements

**Date:** 2026-09-20

**Status:** Accepted

### Context

After [DEC-016](#dec-016--the-f4-advantage-reproduces-on-further-test-beds-but-they-are-one-flight)
the only thing targeted refinement lost on was cost: 2–4× the uniform control's
compute, with break-even at 5–13 questions depending on the test bed. Since the
control's price is fixed and the targeted arm's is per question, that break-even
*is* the comparison.

Profiling one refinement, rather than guessing:

| Phase | Share | Per call |
|---|---:|---:|
| `_register` | 62% | 1.05 s |
| `_locate` | 26% | 0.48 s |
| `_local_bundle` | 12% | 2.22 s |

Then inside `_register`, splitting detection from matching: **detection 94%,
matching 6%**. And inside detection, splitting decode from SIFT:

| | Cost per frame |
|---|---:|
| `gray()` — seek, decode, resize, undistort | **339 ms** |
| SIFT detect, 4000 features | 47 ms |
| SIFT detect, 1200 features | 38 ms |

So the cost was never the vision. It was **seeking in an H.264 stream**, which
decodes from the nearest keyframe every time. Sequential reading of the same
video costs 8 ms per frame — 48× less — and a question's top ten candidates span
a median of 16 frames.

### Options Considered

#### Reduce the feature count

The obvious knob, and worth 9 ms of 386. Rejected as irrelevant to the actual
cost.

#### Re-encode missions all-intra so seeking is cheap

Would work, and makes every mission video far larger for a benefit only this one
code path needs.

#### Decode the span sequentially, once per refinement

A refinement knows up front which frames it will look at: its candidate batch,
their PnP anchors, and the endpoint's anchors. Reading that span in one pass
costs the span, not the seeks.

#### Cache detections across measurements, not within one

`_detect_cached` existed but was per engine, and an engine is created per
measurement — so the cache was discarded exactly when it would start paying.
`_register` did not use it at all, re-detecting each anchor once per candidate.

### Decision

The last two. `FrameSource.prefetch` reads a run of frames in one sequential
pass, bounded by `PREFETCH_MAX_SPAN` and `PREFETCH_MAX_WASTE` so it cannot read
through the whole clip for two scattered frames. `_DETECT_CACHE` is module-level,
LRU-bounded, and keyed by (backend name, video path, frame index) — never by
object identity, because two detectors produce different keypoints for the same
image and matching one's features against another's fails silently.

`MAX_REFIT_POINTS` stays at 400. Dropping it to 100 was measured: 13% faster,
one refit fewer in eight, and median sigma 4.6% worse. Interval width is the
feature's remaining weakness, so that is not a trade worth taking.

### Why

The profile said the cost was frame access, not computation, and the fix is the
one the access pattern already implied: refinement looks at a contiguous run of
frames, so it should read them contiguously.

### Consequences

Measured on all three test beds, same frozen questions, same code otherwise:

| Test bed | Before | After | Speedup | Yield, targeted / uniform |
|---|---:|---:|---:|---|
| `agz_dense_pass` | 206.7 s | **88.6 s** | 2.33× | 15 / 10 |
| `agz_dense_firsthalf` | 239.3 s | **75.6 s** | 3.17× | 13 / 5 |
| `agz_dense_secondhalf` | 223.9 s | **62.5 s** | 3.58× | 15 / 9 |

- **The F4 gate's premise is now satisfiable.** At the control's own budget the
  targeted arm reaches all 20 questions on the full pass (8 blockers cleared
  against the control's 8), 14 of 20 on the first half (6 against 1) and 18 of
  20 on the second (6 against 5). It ties once and wins twice at matched
  compute, having previously been unable to finish the question set at all.
- On the full pass it is now **cheaper as well as higher-yield**: 88.6 s against
  135.4 s.
- Break-even moved from 4.8–13.1 questions to 15.1–30.6.
- Quality is unchanged or slightly better — yield 14 → 15 on the full pass,
  still zero regressions everywhere. The speedup came from doing the same work
  fewer times, not from doing less of it.
- A refinement now holds up to 96 decoded frames and 96 detections in
  process-wide caches: roughly 85 MB and a few hundred MB respectively at the
  worst.
- Because the caches are keyed by video path rather than by reconstruction,
  reprocessing a project is safe — the frames are unchanged. The one case that
  is not safe is a **new upload landing at the same path with different
  content**, so `clear_detect_cache()` is called from the video upload handler.
  That is the only point where a cached frame can go stale.

### Related Files

`drishti3d/reconstruction/drishti_recon/refinement.py`
(`FrameSource.prefetch`, `_prepare`, `_store`, `_detect_cached`,
`_DETECT_CACHE`, `clear_detect_cache`)

---

## DEC-018 — Dense geometry comes from multi-view stereo, and is kept distinct from the depth prior

**Date:** 2026-09-20

**Status:** Accepted — built, not yet verified end to end

### Context

The clouds this pipeline ships look like a scattering of corners, because that
is what they are: 17,898 points for 233 m of flight on the AGZ mission, 4,037 on
a 63 s clip, at 0.167 m average spacing and only where features were matched.
Every one of those points is observed — the class counts are
`AI_ASSISTED: 0` on both — so the poor appearance is not inference creeping in.
It is that **no dense stage was ever built**, although plan section 5.3 asks for
one by name: *"Create dense observed geometry using multi-view stereo where the
capture supports it."*

### Options Considered

#### Extend the existing depth-prior path

`densify="depth"` already produces a dense-looking cloud from a monocular depth
model. It is the cheapest route to a better-looking viewer and the wrong one:
those points are predictions from a single image, tagged `AI_ASSISTED` and
excluded from measurement. Making the product look finished by filling it with
geometry nobody may measure is the failure this system exists to avoid.

#### COLMAP PatchMatch stereo

The reference implementation, and genuinely observed: every point comes from
photometric agreement across several real images, so it carries the same
provenance as a sparse point and is measurable under the same rules.

The obstacle is concrete. `pycolmap` exposes `patch_match_stereo`,
`stereo_fusion` and `undistort_images`, but `pycolmap.has_cuda` is `False` and
the call fails with *"Dense stereo reconstruction requires CUDA or HIP, neither
of which is available on your system."* **No CUDA-enabled pycolmap wheel exists
on PyPI** — checked: 4.2.0 publishes only `manylinux` CPU wheels. So the dense
stage must shell out to a separately installed `colmap` executable.

#### Write a GPU plane-sweep in torch

`torch` cu128 already works on this machine, so this needs no system install.
It also reimplements, worse, something COLMAP does well.

### Decision

Shell out to a CUDA-enabled `colmap` binary, behind `densify="mvs"`. Keep the
depth prior as a separate, differently-tagged option. Report availability — and
*why* it is unavailable — through `/api/capabilities`.

If installing a CUDA COLMAP proves impractical, a torch plane-sweep goes behind
the same `mvs` interface rather than changing the contract.

### Why

The distinction between measured and inferred geometry is the product's whole
claim, and a dense stage is where it is easiest to lose. Two options that both
"make the cloud look good" are kept as separate parameters with different
provenance tags, so the choice has to be made explicitly and shows up in the
class counts.

### Consequences

- Dense points are fused into the **same** cloud as the sparse ones, not
  layered beside them like the depth prior, because they are the same kind of
  thing.
- **They carry a geometric uncertainty, not a propagated covariance.** Fusion
  does not report which images agreed at what disparity, so the Jacobian in
  :mod:`uncertainty` cannot be formed. `mvs.depth_uncertainty` estimates
  `range * sigma_px / focal / sqrt(n_views)` instead, and the pipeline raises a
  warning saying so on every run that uses it. That number is what a
  measurement on a dense point would be quoted from, so it must not be quietly
  optimistic.
- When sparse points have a propagated sigma and dense points do not, the
  arrays are dropped rather than concatenated — otherwise a dense point would
  inherit a sparse point's sigma through indexing.
- The COLMAP workspace now survives the sparse stage when `densify="mvs"`
  (`keep_workspace`), because dense stereo needs the images and sparse model
  COLMAP itself wrote. Re-exporting them by hand would risk disagreeing with it.
- **Not yet verified end to end.** No CUDA-enabled COLMAP is installed on this
  machine, so the subprocess path has never run. The module, the plumbing, the
  uncertainty model and the capability reporting are tested; the actual dense
  reconstruction is not. That is stated here rather than implied by the code
  existing.

### Related Files

`drishti3d/reconstruction/drishti_recon/mvs.py`,
`colmap_adapter.py` (`keep_workspace`), `pipeline.py` (densify stage, fusion),
`backend/app/main.py` (`_mvs_status`), `drishti3d/tests/test_mvs.py`

---

## DEC-019 — A dense point's uncertainty is floored by the model it rides on

**Date:** 2026-09-21

**Status:** Accepted

### Context

[DEC-018](#dec-018--dense-geometry-comes-from-multi-view-stereo-and-is-kept-distinct-from-the-depth-prior)
built dense multi-view stereo but could not run it: no CUDA-enabled COLMAP was
installed. One now is, and the first run exposed a defect in the uncertainty
model that the plumbing tests could not have caught.

Dense points came back with a **median sigma of 0.0052 m against the sparse
points' 0.0364 m** — seven times more certain than the bundle-adjusted geometry
they were triangulated from. The estimate was
`range * sigma_px / focal / sqrt(n_views)`, and every term was wrong in the
flattering direction.

### Options Considered

#### Leave it and label dense points unmeasurable

Avoids the bad number by refusing to use it. It also throws away the point of
producing observed dense geometry rather than a depth prior: if dense points
cannot be measured, they are decoration, and the depth prior already does
decoration more cheaply.

#### Propagate a real covariance

The correct answer, and not available: `stereo_fusion` reports fused points and
a visibility count, not which images agreed at what disparity, so the Jacobian
in :mod:`uncertainty` cannot be formed. Recovering it would mean reimplementing
fusion.

#### Fix each wrong term, and floor the result on the sparse model

1. **Pixel sigma.** The sparse reconstruction's reprojection residual (0.49 px
   here) is *feature-localisation* precision: SIFT sits on a corner and finds it
   to a fraction of a pixel. Patch-match correlates a window over whatever
   texture is present. `DENSE_PIXEL_SIGMA = 1.0` px instead.
2. **Independence.** `sqrt(n_views)` over every contributing image treats
   consecutive frames of one pass, seeing the same surface from nearly the same
   place, as independent samples. Capped at `MAX_INDEPENDENT_VIEWS = 4`.
3. **A floor.** A dense point is triangulated from cameras known only to the
   bundle adjustment's accuracy, so it cannot be better known than the model it
   rides on. The sparse cloud's own median `sigma_major` is combined in
   quadrature.

### Decision

The third. The floor is the part that matters: without it the stereo term alone
reports millimetres on a model good to centimetres, and the other two
corrections only change how badly.

### Why

This is the third time on this project that an uncertainty has come out
implausibly small because something was held fixed that is not actually
known — the local refit's boundary cameras in
[DEC-014](#dec-014--targeted-refinement-gets-a-local-refit-it-ties-on-yield-and-still-loses-on-speed),
and now the camera poses under dense stereo. The pattern is worth naming: any
estimate conditioned on a model must carry that model's uncertainty, or it will
claim to know more than the thing it was derived from.

### Consequences

| | Sparse only | Dense, before | **Dense, after** |
|---|---:|---:|---:|
| p10 | 0.0123 m | 0.0035 m | 0.0371 m |
| median | 0.0364 m | 0.0052 m | **0.0379 m** |
| p90 | 0.1367 m | 0.0116 m | 0.0450 m |

- Dense points are now marginally *less* certain than sparse ones, which is the
  correct ordering, and the sparse p10 still beats every dense point — the
  best-constrained sparse points have long tracks and wide baselines that
  generic stereo cannot match.
- The dense distribution is tight (p10 0.037, p90 0.045) because the floor
  dominates it. That is honest but not informative: it means a dense point's
  reported uncertainty is currently more a statement about the model than about
  that point. A propagated covariance would separate them.
- **None of this is validated against truth.** Plausible is not correct, and
  only measured reference dimensions can settle it.
- DEC-018's remedy is confirmed working: 251,998 observed points at 0.099 m
  spacing against 17,898 at 0.167 m, `AI_ASSISTED: 0`, and reconstruction
  accuracy unchanged at 3.764 m as-georeferenced.

### Related Files

`drishti3d/reconstruction/drishti_recon/mvs.py` (`depth_uncertainty`,
`DENSE_PIXEL_SIGMA`, `MAX_INDEPENDENT_VIEWS`), `pipeline.py` densify stage,
`drishti3d/tests/test_mvs.py`,
`drishti3d/docs/benchmarks/2026-09-21_dense_mvs/RESULTS.md`
