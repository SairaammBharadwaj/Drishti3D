# Next Steps

If you are picking this repository up now, read
[PROJECT_OVERVIEW.md](PROJECT_OVERVIEW.md) then start at the top of P0.

Last updated: 2026-09-19.

**The one-line summary of where the project stands:** reconstruction works on
real single-pass aerial video and is measured against a real reference; every
measurement can name the frames and pixels that produced it; but nothing can be
*accepted* yet, because there is no validated interval calibration — and that
one needs field data, not code.

---

## P0 — Critical

Nothing. Observation lineage, the previous P0, landed on 2026-09-19 — see
[DEC-009](DECISIONS.md) and the
[WORKLOG entry](WORKLOG.md). The top of the backlog is now P1.

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

### Same-pass evidence recovery — "Improve this measurement"

**Status:** TODO
**Priority:** P1

**Why it matters**

Plan feature F4, and the principal engineering contribution of the product.

**Current state**

Nothing implemented, but both halves it depends on now exist.
`evidence.supporting_frames` does the candidate ranking, diversity-ranked by
added angular spread. `observations.npz` says which frames already measured a
point, which is exactly the set a scheduler must *exclude* when looking for new
evidence.

**Recommended implementation**

Follow plan section 5.7. Build `refinement.py` with: candidate retrieval from a
full-clip frame index, rejection of cuts/blur/dynamic/incompatible frames,
ranking by useful baseline and expected variance reduction, a bounded batch of
4–8 frames, local re-match and refit with a connected boundary to the global
model, and recomputation of the measurement and its verdict. Persist a
`RefinementRun` record with parent and result versions, added and excluded
frames, budget, actual runtime, before/after result and termination reason.

The experiment that matters is the paired comparison in plan F4: targeted
refinement versus uniform refinement at equal added compute. **A negative result
is a valid outcome and must be published**, not buried.

**Relevant files**

New `reconstruction/drishti_recon/refinement.py`; `keyframes.py`,
`features.py`, `bundle.py`, `evidence.py`, `backend/app/routers/questions.py`

**Dependencies/blockers**

None remaining — observation lineage landed 2026-09-19. This is the largest
open piece of engineering in the plan.

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
