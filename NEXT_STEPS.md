# Next Steps

If you are picking this repository up now, read
[PROJECT_OVERVIEW.md](PROJECT_OVERVIEW.md) then start at the top of P0.

Last updated: 2026-09-19.

**The one-line summary of where the project stands:** reconstruction works on
real single-pass aerial video and is measured against a real reference; every
measurement can name the frames and pixels that produced it, and can spend a
bounded budget recovering more from the same pass. Nothing can be *accepted*
yet, because there is no validated interval calibration — that needs field
data, not code. Two gaps are code, though: the COLMAP path ships no per-point
uncertainty, and the refinement hypothesis has not been tested against a
uniform-budget control.

---

## P0 — Critical

### Wire per-point uncertainty into the COLMAP path

**Status:** TODO
**Priority:** P0

**Why it matters**

The faster, more accurate engine ([DEC-008](DECISIONS.md)) produces
reconstructions on which **no measurement can be reported at all**.
`cloud.npz` from a COLMAP run has no `sigma` or `sigma_major`, so every endpoint
snaps to an infinite sigma and `questions.evaluate` returns `not_observable`
with `uncertainty_undefined`. Every measurement and refinement result recorded
so far had to use the in-repo engine instead. See
[DEC-011](DECISIONS.md#dec-011--the-colmap-path-ships-no-per-point-uncertainty-so-its-measurements-cannot-be-reported).

**Current state**

`colmap_adapter.reconstruct_frames` leaves `ReconResult.point_cov`,
`point_sigma` and `point_sigma_major` as `None`. Only the in-repo engine runs
the `uncertainty.point_covariances` pass.

**Recommended implementation**

`uncertainty.point_covariances(points, cam_idx, pt_idx, uv, rvecs, tvecs, K)`
needs observations, poses and intrinsics — all of which the COLMAP adapter now
has, since observation lineage landed. Feed `obs_point`, `obs_frame` and
`obs_uv` straight in. This is wiring, not new mathematics.

Do **not** substitute a default sigma as a stopgap: a made-up interval flows
directly into acceptance once calibration exists, which is exactly what
[DEC-003](DECISIONS.md) exists to prevent.

Afterwards, check whether COLMAP's longer mean track length (3.91 vs 2.78
observations per point) gives it better per-point uncertainty than the engine
currently in use, and re-run the measurement and refinement surveys on it.

**Relevant files**

`reconstruction/drishti_recon/colmap_adapter.py`, `uncertainty.py`,
`pipeline.py` fusion stage

**Dependencies/blockers**

None.

---

## P1 — Important

### Fit and validate an interval calibration profile

**Status:** BLOCKED — needs missions with measured reference dimensions
**Priority:** P1

**Why it matters**

**The only remaining blocker on acceptance.** Measured on the AGZ mission after
lineage landed, a well-supported 3 m span returns `estimated_only` with the
single reason `interval_not_calibrated`. Fix this and the product can say "yes"
([DEC-003](DECISIONS.md#dec-003--acceptance-requires-a-validated-calibration-profile)).

**Current state**

All the machinery exists and is unit-tested: `uncertainty.calibrate`,
`conformal_factors`, `coverage_report`, `CalibrationProfile.from_calibration`,
and the `MIN_CALIBRATION_SAMPLES = 20` floor. What is missing is measurement
error samples — pairs of (predicted sigma, actual error) — and those need truth
dimensions that no dataset here has.

**Recommended implementation**

1. Collect the Field Pack v1 minimum from plan section 6.3: one site, three
   passes, ten independently measured dimensions with instrument uncertainty.
2. Add `eval/calibrate_measurements.py` producing `(error, sigma)` pairs per
   measurement, split **by mission**, never by adjacent frames — nearby points
   in one flight are not independent samples.
3. Fit with `uncertainty.calibrate`, wrap with
   `CalibrationProfile.from_calibration(regime="<camera>/<pattern>/<scale source>")`.
4. Store profiles as JSON; have the backend select one by regime and pass it to
   `questions.evaluate` instead of the current unconditional `None`.
5. Report empirical coverage, interval width and sample count on untouched test
   missions before enabling the label.

**Relevant files**

`reconstruction/drishti_recon/uncertainty.py`, `questions.py`,
`backend/app/routers/questions.py`, `eval/`

**Dependencies/blockers**

Field data. This is the long pole and it starts with a site visit, not with
code.

---

### Recover the 56% of the pass that keyframe selection discards

**Status:** TODO
**Priority:** P1

**Why it matters**

On the AGZ mission, 80 of 184 frames reached SfM and all 80 registered. Over
half a single-pass capture contributed nothing, on a problem statement whose
whole premise is that there is only one pass. It also caps what same-pass
refinement can later recover, since those frames are exactly its candidate pool.

**Current state**

`keyframes.select` chose 80. Both engines then registered 100% of what they were
given, so the loss is entirely in selection. Whether the discarded frames are
redundant, blurry, or wrongly rejected is **not established**.

**Recommended implementation**

1. Instrument `keyframes.select` to record a per-frame rejection reason, and
   write it into `keyframes.json`.
2. Re-run the AGZ mission and tabulate the reasons. This is a diagnostic, not a
   fix; do it before changing any threshold.
3. If the rejections are quality-driven, check them against
   `frame_metrics.json`. If they are redundancy-driven, the 1.17 m median
   baseline suggests the redundancy test is calibrated for denser video.
4. Measure any threshold change on the same mission, both engines, against the
   same reference. Do not change thresholds and geometry in the same run.

**Relevant files**

`reconstruction/drishti_recon/keyframes.py`, `frame_quality.py`,
`scripts/run_mission.py`

---

### Test the refinement hypothesis against a uniform-budget control

**Status:** TODO
**Priority:** P1

**Why it matters**

Same-pass refinement is built and measured, but the plan's F4 gate is a
*comparison*: "on frozen questions and equal added compute budgets, targeted
refinement improves correct accepted-answer yield or reaches the same quality
faster than uniform refinement." Only the targeted arm exists. Until the control
runs, the central innovation hypothesis is supported and untested — and the plan
is explicit that a negative result is acceptable and must be visible.

**Current state**

`refinement.RefinementEngine` and the outcome survey in `TESTS_AND_RESULTS.md`:
10 of 30 weak measurements recovered evidence, all 10 clearing a blocking
reason, median 13.7 s each.

**Recommended implementation**

1. A frozen question set: fix the endpoints and tolerances once, in a file, and
   do not touch them again.
2. The uniform arm: spend the same added compute by re-running the
   reconstruction with N more keyframes selected uniformly, then re-measure the
   same questions.
3. Equalise on *measured* wall clock, not frame count.
4. Report accepted-answer yield, cleared blocking reasons, and error against
   whatever truth exists, for both arms.
5. Publish the result either way. If targeted refinement does not win, keep it
   as an experimental feature and say so in `PROJECT_OVERVIEW.md`.

**Relevant files**

`reconstruction/drishti_recon/refinement.py`, `keyframes.py`, `eval/`

**Dependencies/blockers**

None. This is the highest-value experiment left in the plan.

---

### Improve endpoint location in recovered frames

**Status:** TODO
**Priority:** P1

**Why it matters**

It is the binding constraint on refinement. Across the survey, pose recovery
succeeded 92% of the time (22 failures) while endpoint location failed 243
times. Two thirds of refinement attempts recover nothing for this one reason.

**Current state**

`_locate` projects the endpoint through the recovered pose to bound a 40 px
window, then matches an independently detected keypoint in it against the
endpoint's descriptors from a frame that measured it, with a 0.7 ratio test.
Descriptor matching across a changed viewpoint is where it fails — which is
also why ranking peaks at `MATCHABLE_GAIN_DEG = 25°` rather than at maximum
parallax.

**Recommended implementation**

Worth trying, in order of expected value per effort:

1. **Affine-normalised patch matching** in the window instead of raw SIFT
   descriptors. The recovered pose and the local surface normal give the
   warp, which is exactly the viewpoint change defeating the descriptor.
2. **Chain through an intermediate frame**: match the recovered frame to a
   temporal neighbour that already measured the endpoint, rather than jumping
   straight to a frame 25 frames away.
3. **LightGlue/DISK** for the guided match — `features.create("lightglue")`
   already exists and is markedly more viewpoint-robust than SIFT.

Measure each against the same 30-measurement survey; the recovery rate is the
metric.

**Relevant files**

`reconstruction/drishti_recon/refinement.py` (`_locate`,
`_endpoint_descriptors`), `features.py`

---

### Same-pass evidence recovery — now built, kept here for the UI half

**Status:** IN PROGRESS
**Priority:** P1

**Why it matters**

Plan feature F4, and the principal engineering contribution of the product.

**Why it matters**

The backend recovers evidence and records every run, but an operator cannot
press "Improve this measurement".

**Current state**

`refinement.py` and `POST …/questions/{qid}/refine` are built, tested and
measured ([DEC-010](DECISIONS.md)). `GET …/questions/{qid}/refinements` returns
the history. Not implemented: the dynamic masking and scene-cut rejection plan
section 5.7 step 2 also calls for, and the reserved corroboration set of step 7
— refinement currently draws from all unused frames without holding any back.

**Recommended implementation**

1. An "Improve this measurement" control on the measurement card, with a budget
   selector, calling `refine` and rendering `before` / `after` side by side.
2. Show `reasons_cleared`, `value_change_m` and `interval_narrowed` as three
   separate facts — the run record already keeps them apart precisely so the
   UI cannot collapse them into one misleading arrow.
3. List the recovered frames with their PnP inlier counts and located pixels,
   and the rejection tally beneath, so a run that recovered nothing explains
   itself.
4. Then add the reserved corroboration set (step 7): keep frames outside the
   fit, rotate the reserve when a reserved frame is used, and never report a
   fitting frame as withheld evidence.

**Relevant files**

`frontend/src/views/Workspace.tsx`, `frontend/src/api.ts`,
`reconstruction/drishti_recon/refinement.py`

**Dependencies/blockers**

Shares the Tolerance Lens UI work below.

---

### Tolerance Lens UI

**Status:** TODO
**Priority:** P1

**Why it matters**

The backend gate is complete and tested, but an operator cannot reach it. Plan
F2's exit gate requires an operator to go question → evidence → report without
shell access.

**Current state**

`POST/GET/PATCH/DELETE /api/projects/{id}/questions` and
`GET …/questions/{qid}/evidence` all work and are covered by
`tests/test_questions_api.py`. The frontend has no view for them.

**Recommended implementation**

1. Add the endpoints to `frontend/src/api.ts`.
2. A measurement card per question showing value, interval, a status chip, the
   dominant limitation, and the `next_action` text for each reason code — the
   API already returns all of it in `guidance`.
3. A tolerance slider that issues `PATCH` and re-renders. The card must not
   recompute a status locally; render exactly what the API returns.
4. An evidence panel listing the frames from `…/evidence`. Each row carries
   `measured` and, when true, the `pixel` the measurement was made at — enough
   for Evidence Replay to draw a marker on the source frame. Show
   `support_basis` verbatim so an upper-bound caveat reaches the operator when
   the fallback path is in use.

**Relevant files**

`frontend/src/api.ts`, `frontend/src/views/Workspace.tsx`,
`frontend/src/styles.css`

---

### Decide whether COLMAP becomes the pipeline default

**Status:** TODO
**Priority:** P1

**Why it matters**

[DEC-008](DECISIONS.md#dec-008--colmap-is-the-reconstruction-engine-to-develop-against)
made COLMAP the engine to develop against on measured grounds, but
`PipelineParams.engine` still defaults to `"opencv"`, so the backend and every
default run use the slower, less accurate path.

**Current state**

Measured on one mission. One scene is not enough to flip a default.

**Recommended implementation**

Run both engines on `agz_pass` and `agz_seg2` as well, plus the synthetic
regimes in `eval/cases.py` to check nothing regresses there. If COLMAP holds,
change the default and make the OpenCV engine an explicit fallback when
PyCOLMAP import fails. Keep both tested either way.

**Relevant files**

`reconstruction/drishti_recon/pipeline.py` (`PipelineParams.engine`),
`colmap_adapter.py`, `eval/`

---

## P2 — Improvements

### Measurement passport and offline verifier

**Status:** TODO
**Priority:** P2

Plan F3's second half: a standalone evidence bundle a verifier can recompute the
reported number from, and validate artifact hashes against, without the running
backend. Unblocked as of 2026-09-19 — `observations.npz` supplies the real
supporting frames and pixels the bundle has to carry, and the mission's
`frame_index.csv` maps those frames back to original source JPEGs with hashes.
Expected new module `passport.py`. Arguably belongs at P1 now that it is
buildable.

---

### Schema-versioned artifact contract

**Status:** TODO
**Priority:** P2

`manifest.json` carries `"version": "0.1.0"` but nothing reads it, and the
artifact set is compatible by convention. Plan section 5.9 asks for
schema-versioned `Mission`, `FrameObservation`, `SurfaceEvidence`,
`MeasurementQuestion`, `MeasurementResult`, `CalibrationProfile`,
`RefinementRun` and `ArtifactManifest` records. Add version checks at load
time so an old artifact is refused with a clear message rather than
misinterpreted.

**Relevant files:** `pipeline.py` (`_write_manifest`), `evidence.py`,
`backend/app/routers/`

---

### Alembic migrations

**Status:** TODO
**Priority:** P2

`db._add_missing_columns` handles additive changes only
([DEC-007](DECISIONS.md#dec-007--additive-startup-migration-for-the-development-sqlite-database)).
The first rename, retype or data migration must introduce Alembic.

---

### Investigate the gravity-levelling rejection

**Status:** TODO
**Priority:** P2

Levelling would have more than doubled the GNSS alignment residual on a normal
oblique pass (6.14 → 14.97 m). The rejection is correct behaviour; the estimate
being that wrong is unexplained. Check the ground-plane fit against the cloud's
actual dominant plane, and whether the oblique viewing angle is being mistaken
for terrain slope.

**Relevant files:** `reconstruction/drishti_recon/pipeline.py` levelling stage,
`geo.py`

---

### Build the remaining missions and the split manifests

**Status:** TODO
**Priority:** P2

`agz_pass` and `agz_seg2` are inventoried and usable but not built into
missions. `datasets/splits/{development,calibration,test_locked}.json` are
specified in plan section 6.5 and do not exist. Until they do, "held out" is a
claim rather than a mechanism.

```bash
scripts/build_agz_mission.py --source data/real_drone/agz_pass  --name agz_sparse_pass
scripts/build_agz_mission.py --source data/real_drone/agz_seg2 --name agz_segment_two
```

---

### Undistortion round-trip test

**Status:** TODO
**Priority:** P2

`sensors.undistort_frames` replaces `K` and the pipeline assumes a pinhole
thereafter. Nothing tests that a point projected with the original `K` and
distortion lands where the undistorted `K` says it should. The failure mode —
undistorting twice, or carrying the wrong `K` — is silent and degrades every
downstream number.

---

## P3 — Future Ideas

### Bounded learned-model evaluation

Plan section 5.4 allocates at most two engineer-days to MapAnything's Apache
checkpoint as a coarse preview or initialisation candidate, kept only if it
improves registration, useful coverage or time to first useful result without
measurement regression. MASt3R and VGGT adapters already exist in the
repository but are research options, and VGGT's licence excludes military
applications from its commercial-use allowance — unsuitable as an unexamined
default for this stakeholder.

### Missing-evidence acquisition guidance

Plan's optional P1: rank a small set of candidate additional views for a
rejected question. Explicitly outside the single-pass benchmark; any result
using extra images must be labelled *augmented capture*.

### Licence manifest

Plan section 5.4 asks for code, weights and dataset licences pinned separately
and reviewed before field distribution. Nothing tracks this today.

### Dense reconstruction on the supported ROI

`densify` is `"none"` by default and the supported path is sparse. Multi-view
stereo on a selected ROI would raise measurable surface coverage, which is
4.3% of grid cells on the AGZ mission.
