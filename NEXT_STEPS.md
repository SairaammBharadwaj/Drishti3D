# Next Steps

If you are picking this repository up now, read
[PROJECT_OVERVIEW.md](PROJECT_OVERVIEW.md) then start at the top of P0.

Last updated: 2026-09-23.

**Dense geometry landed 2026-09-21.** COLMAP PatchMatch stereo gives 252k
observed points at 0.100 m spacing against 17.9k at 0.167 m, with full
observation lineage — and on the dense cloud **59 of 60 sampled measurements are
blocked only by calibration**, against 40 of 60 sparse. Calibration is now
almost the only thing standing between this system and an accepted measurement,
and it needs field data.

**Read this first:** the plan's central innovation hypothesis — that targeted
same-pass refinement beats a uniform budget — **now passes its own gate on all
three test beds tried**: higher answer yield (15 against 10, 13 against 5, 15
against 9) with **zero regressions** against the control's four to seven, at
comparable or lower compute after the cost work. All three test beds are
partitions of **one flight**, and the only genuinely separate segment cannot run
the comparison, so the feature stays experimental. **One thing would settle it:
a field capture.** That also unblocks interval calibration, which is still the
only thing between this system and an accepted measurement.

**The one-line summary of where the project stands:** reconstruction works on
real single-pass aerial video and is measured against a real reference; every
measurement can name the frames and pixels that produced it, and can spend a
bounded budget recovering more from the same pass. Both engines now produce
measurable reconstructions, and on COLMAP **51 of 60 sampled measurements have
nothing blocking them but calibration**. That calibration is the one thing left
between this system and an accepted measurement, and it needs field data, not
code.

---

## P0 — Critical

**Reopened 2026-09-21.** "P0: Nothing" was wrong, and a critical review
([docs/NTRO_CRITICAL_REVIEW_AND_IMPROVEMENTS_2026-09-21.md](drishti3d/docs/NTRO_CRITICAL_REVIEW_AND_IMPROVEMENTS_2026-09-21.md))
found ten correctness findings, six with counterexamples that all reproduced.
Dense MVS having landed does not make the system correct; it made a different
set of defects reachable.

### Closed by DEC-021 … DEC-030 on 2026-09-21

| ID | Finding | Decision |
|---|---|---|
| C01 | Two incompatible definitions of a stored measurement | [DEC-021](DECISIONS.md) |
| C02 | Scale uncertainty applied per segment; subdividing a line narrowed it | [DEC-022](DECISIONS.md) |
| C03 | Unbounded snapping relocated a selection 990 m without refusal | [DEC-023](DECISIONS.md) |
| C04 | Dense depth uncertainty ignored triangulation angle | [DEC-025](DECISIONS.md) |
| C05 | Projected dense pixels indistinguishable from measured feature pixels | [DEC-029](DECISIONS.md) |
| C06 | Refined results stored the operator's original endpoints | [DEC-030](DECISIONS.md) |
| C07 | Caches keyed by project id returned superseded geometry | [DEC-026](DECISIONS.md) |
| C08 | LAS ignored its frame, declared no CRS, dropped sigma | [DEC-027](DECISIONS.md) |
| C09 | `as_georeferenced` removed the offset it was reporting | [DEC-024](DECISIONS.md) |
| C10 | Calibration marked itself validated from a sample count | [DEC-028](DECISIONS.md) |

411 tests pass, up from 335. Seven new regression modules.

### Reopened and closed again on 2026-09-21 by the follow-up verification

[CRITICAL_REVIEW_VERIFICATION_2026-09-21.md](drishti3d/docs/CRITICAL_REVIEW_VERIFICATION_2026-09-21.md)
checked the work above and found **nine failures in fifteen independent
checks**, two of them crashes introduced by the fixes themselves. Its
conclusion — that the table above "overstates closure" — was correct.

| ID | Finding | Decision |
|---|---|---|
| F01 | `refine()` raised `NameError` on its success path | [DEC-032](DECISIONS.md) |
| F02 | Video-only export crashed, and would have geo-placed arbitrary scale | [DEC-032](DECISIONS.md) |
| F03 | `/questions` never used the shared result service | [DEC-033](DECISIONS.md) |
| F04 | Refinement diagnostics broke the next tolerance change | [DEC-033](DECISIONS.md) |
| F05 | `PATCH` persisted an interval level it then failed on | [DEC-033](DECISIONS.md) |
| F06 | Cache identity and answer identity could disagree | [DEC-033](DECISIONS.md) |
| F07 | A one-point cloud had no snap bound at all | [DEC-023](DECISIONS.md) |
| F08 | `1/tan` gave zero sigma at 90° and negative beyond | [DEC-031](DECISIONS.md) |

All 15 audit checks pass; 431 tests pass, up from 422.

**The lesson is about the closure table, not the findings.** C01 was marked
closed because the service existed and one route used it. Writing a decision
record is not evidence the decision was applied everywhere.

### New P0 from the first independent check (2026-09-22)

**A planar flight leaves the vertical unconstrained, the system detects it, and
nothing downstream acts on it.** Scoring UseGeo dataset 1 against its LiDAR
found a **+1.245 m systematic vertical bias** while the reconstruction reported
a 0.093 m sigma — interval coverage of **4.6%** against a nominal 95%
([DEC-036](DECISIONS.md)).

`alignment.degenerate` and `alignment.degeneracy` already reach the manifest.
Nothing reads them. The fix needs designing rather than patching:

1. **Uncertainty has to carry direction.** A scalar sigma per point cannot
   express "well constrained horizontally, poorly constrained vertically",
   which is exactly this capture's condition. The covariance machinery in
   `uncertainty.py` already handles 3x3; the dense path collapses it to a
   scalar.
2. **A degenerate alignment needs a blocking acceptance reason**, in the way
   `view_geometry_unverified` blocks an unverified support count. A measurement
   whose out-of-plane component is unconstrained must not be accepted on the
   strength of a well-fitted camera plane.
3. **The alignment RMSE must stop being read as accuracy.** The report already
   says it is not; the 5.7 cm vertical RMSE on this run is the counterexample
   that proves it.

This matters more than AGZ suggested: a constant-altitude nadir survey is the
*more* common commercial pattern, and it is the one that breaks.

### Still open at P0

**The corrected numbers are not validated numbers.** C04 makes dense
uncertainty respond to geometry and C09 reports absolute error honestly; neither
shows the resulting figures are right. That needs field data, and it is the same
site visit as the calibration work below.

Two parts of C06 remain: the evidence endpoint rebuilds from on-disk lineage
that does not contain recovered frames, and the frontend caches its evidence
response across a refinement. Both are visible to an operator as a
before/after that does not name the frames the refinement actually added.

---

## P1 — Important


### Get data that can actually validate a calibration profile

**Status:** READY TO DOWNLOAD — no drone needed
**Priority:** P1, and the longest lead time of anything in this backlog

**Why it matters**

Every measurement in the system reports `interval_not_calibrated`, and that is
the only thing still between it and an accepted measurement. Fitting a profile
needs reference dimensions measured by something that is **not** this pipeline,
with a stated instrument uncertainty. Nothing on disk has that.

What is on disk, re-checked 2026-09-21: five AGZ entries, all derived from
**one Zurich flight**, whose reference is Pix4D photogrammetry — the dataset
authors' own words, not survey truth. Plus `goetheanum`, `gym_pass`,
`lambertus` (video, no truth at all), `monterey_strip` and `odm_data_bellus`.
631 MB total. There is no second independent flight and no measured dimension.

**Recommended downloads, in order**

1. **UseGeo** — <https://github.com/3DOM-FBK/UseGeo> (README is on the
   `master` branch, not `main`). Three datasets of 224 / 328 / 277 images,
   **acquired over three different areas** — verified in the source paper, so
   they are genuinely independent captures, not blocks of one flight. That is
   what F4 generalisation needs and what nothing on disk provides.

   Each carries a **LiDAR reference cloud** (~50 pts/m²) from a RIEGL
   miniVUX-3UAV, ground-truth depth maps, camera poses and interior
   parameters. Images are Sony A7R III, 7952x5304, GSD under 2 cm, 80/60%
   overlap giving a minimum of 8 images per object point.

   The LiDAR being a **separate instrument** is the point: it is the first
   reference here not derived from photogrammetry, so it can validate
   [DEC-031](DECISIONS.md)'s dense uncertainty and V04's surface accuracy,
   neither of which anything in this repository can currently check.

   **Verified 2026-09-21:** all three links return HTTP 200 and are live. Two
   practical snags. The host's TLS certificate **expired on 30 August 2024**
   (a genuine University of Twente certificate from GEANT, simply not renewed),
   so a browser shows a warning to click through and `curl` needs `-k`. And the
   authors note institutional firewalls often block port 5001 — use a home
   connection if it stalls. Exact sizes need a browser session; expect tens of
   GB for all three.

   **Licence: CC BY-NC-SA 4.0.** Non-commercial and share-alike. Validation and
   published numbers are fine; shipping the data, or clouds derived from it, as
   part of anything commercial is not. Worth deciding before it is embedded in
   a demo.

2. **ISPRS/EuroSDR Benchmark on Multi-Platform Photogrammetry** —
   <https://www2.isprs.org/commissions/comm2/icwg-2-1a/benchmark_main/>.
   Dortmund and Zurich, with TLS, ALS **and surveyed check points from
   topographic networks and GNSS**. This is the only listed source of truly
   independent measured coordinates, which is what a calibration profile needs
   and what a LiDAR surface only approximates. **Requires a registration form,
   so start it now** — the same reasoning the original review gave for starting
   field arrangements alongside the code work.

3. **Hessigheim 3D (H3D)** —
   <https://ifpwww.ifp.uni-stuttgart.de/benchmark/hessigheim/default.aspx>.
   UAV LiDAR at 800 pts/m² over three epochs. A much denser reference surface
   than UseGeo, but it is built for semantic segmentation and is more work to
   reduce to what we need. Worth it only if UseGeo's reference proves too
   coarse.

**The caveat that applies to all three**

They are **image sets, not video**. Drishti3D's premise is single-pass video,
and a pipeline validated only on stills has not validated its video-specific
parts: PTS timing ([DEC-005](DECISIONS.md)), rolling-shutter detection,
keyframe selection, or motion blur. These datasets can validate the
*geometry and uncertainty* claims, which is the binding constraint today. They
cannot retire V01, and the backlog should not pretend otherwise.

**Done when**

A calibration profile is fitted on one mission, evaluated on a disjoint one
([DEC-028](DECISIONS.md) enforces the disjointness), released, and some
measurement somewhere legitimately reads `meets_requirement`.

**Relevant files**

`drishti3d/scripts/inventory_datasets.py`, `build_agz_mission.py`,
`drishti3d/eval/`, `drishti3d/reconstruction/drishti_recon/questions.py`


### Seed questions on the remaining missions

**Status:** READY — `scripts/seed_questions.py`
**Priority:** P1

**Why it matters**

Until now every measurement comparison lived in the benchmark record, computed
offline against `drishti_recon`. The app itself held one question per project,
so the workspace understated the pipeline: a reconstruction whose claim is that
it can be measured showed an empty Tolerance Lens.

`scripts/seed_questions.py` asks a project real questions through the HTTP API
across three baseline bands. It is run on the dense and sparse AGZ projects; the
dense advantage reproduced on script-chosen geometry (median sigma 0.184 m vs
0.248 m, 4 views vs 3, 25.8 deg parallax vs 15.0, zero `insufficient_views`
against four).

**Recommended implementation**

Import the remaining telemetry-bearing missions (`agz_dense_firsthalf`,
`agz_dense_secondhalf`, `agz_sparse_pass`, `agz_segment_two`) and seed each.
Dense reconstruction is ~21 min of GPU time per mission; seeding is seconds.

**Relevant files**

`scripts/seed_questions.py`, `scripts/import_run_as_project.py`


### Validate dense uncertainty against measured dimensions

**Status:** BLOCKED — needs field data
**Priority:** P1

**Why it matters**

Dense MVS works: 251,998 observed points at 0.099 m spacing against 17,898 at
0.167 m, `AI_ASSISTED: 0`, accuracy unchanged ([DEC-019](DECISIONS.md)). But a
dense point's uncertainty is a **geometric estimate floored by the sparse
model's accuracy**, not a propagated covariance — the first run had it seven
times too optimistic, and the fix makes the numbers *plausible*, not *verified*.

The distribution is now tight (p10 0.037, p90 0.045) because the floor dominates
it, which means a dense point's reported uncertainty currently says more about
the model than about that point.

**Recommended implementation**

With measured reference dimensions, compare predicted sigma against observed
error for dense endpoints specifically, separately from sparse ones. If dense
intervals under-cover, the floor or the pixel sigma is wrong. This is the same
site visit as the calibration task.

A partial check needing no field data: `stereo_fusion` can be asked for a
visibility sidecar, and a per-point covariance could be approximated from the
contributing cameras' geometry rather than from range alone. That would separate
"this point is well seen" from "the model is good here".

**Relevant files**

`reconstruction/drishti_recon/mvs.py`, `eval/`

---

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

### Capture a flight that can actually test generalisation

**Status:** BLOCKED — needs field data
**Priority:** P1 — the top of the backlog

**Why it matters**

The F4 advantage reproduced on three test beds, and **all three are partitions
of one flight** ([DEC-016](DECISIONS.md)). The only genuinely separate AGZ
segment cannot run the comparison at all: at a 2.8 m median baseline
`keyframes.select` correctly declines to thin it, so there is no unused frame
pool and no denser arm. No denser frame set for those image ids exists on disk.

Until a second flight is tested, "targeted refinement beats a uniform budget" is
a statement about one capture.

**What the capture has to be**

The comparison only means anything on a pass that is **over-sampled relative to
what reconstruction needs** — `agz_dense_pass` at a 1.17 m median baseline is;
`agz_segment_two` at 2.8 m is not. So: continuous video, not a stride subsample,
at a frame spacing well under a metre. That is the normal output of a drone
flying and recording, which is the point.

The Field Pack v1 specification in plan section 6.3 already asks for this, and
its reference dimensions would also let both arms be scored on **error against
truth** rather than on measurement standing — which no run so far has been able
to do.

**Relevant files**

`eval/f4_experiment.py`, `scripts/build_agz_mission.py`,
`reconstruction/drishti_recon/keyframes.py` (the sparse-capture guard that makes
the regime explicit)

**Dependencies/blockers**

A field capture. Shares a site visit with the calibration task above.

---

### Build a capture where targeting could plausibly pay off

**Status:** TODO
**Priority:** P1 — the diagnostic that says whether the F4 loss is mechanism or regime

**Why it matters**

The F4 experiment's third explanation for the loss is regime, not mechanism: the
AGZ pass is a continuous traverse decimated to 80 of 184 frames, so it is short
of views nearly everywhere and spreading the budget hits something useful
wherever it lands. Targeting should pay off where *most* of the scene is
adequately covered and a few measurements are not — a regime no capture in this
repository tests.

**Recommended implementation**

Construct it from AGZ rather than waiting for field data: reconstruct at
`preset="quality"` but hold out a contiguous window of frames covering one part
of the scene, so that region alone is under-observed. Freeze questions inside
and outside the window, and rerun the F4 experiment. If targeting wins inside
the window and loses outside it, the mechanism works and the AGZ result is about
regime; if it loses in both, it is about the mechanism.

**Relevant files**

`eval/f4_experiment.py`, `scripts/run_mission.py`, `keyframes.py`

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

### Finish the operator surface beyond the Tolerance Lens

**Status:** TODO
**Priority:** P1

**Why it matters**

The Tolerance Lens itself is built and on screen: value and interval, status
chip, dominant limitation with each reason's next action, a tolerance slider
that re-decides without re-measuring, evidence with measuring frames marked
apart from candidates, and "Improve this measurement" with a before/after.

What is still missing is everything around it. Plan features F3, F5 and F6 have
no operator surface at all.

**What is left**

1. **Evidence Replay proper (F3).** The panel lists measuring frames and the
   pixel each was measured at, but does not *show* the frame with a marker on
   it. The data is there; `frame_index.csv` maps back to original source images.
2. **The unknown-space map (F5).** `coverage.npz` classifies the mission volume
   into observed / weak / occluded / unseen / verified-empty and nothing renders
   it. This is the feature that makes a refusal legible.
3. **Export and report (F6).** No way to export a measurement set, and no
   comparison report.
4. **A capability notice.** `/api/capabilities` reports whether dense MVS is
   available and why not; the UI ignores it.

**Relevant files**

`frontend/src/ToleranceLens.tsx`, `views/Workspace.tsx`,
`PointCloudViewer.tsx`, `api.ts`

---

### Decide whether COLMAP becomes the pipeline default

**Status:** TODO
**Priority:** P1 — stronger now than when first raised

**Why it matters**

[DEC-008](DECISIONS.md#dec-008--colmap-is-the-reconstruction-engine-to-develop-against)
made COLMAP the engine to develop against on reconstruction grounds, but
`PipelineParams.engine` still defaults to `"opencv"`, so the backend and every
default run use the slower path.

Since per-point uncertainty landed, the case is no longer only about geometry:
on COLMAP, 51 of 60 sampled measurements have nothing blocking them but
calibration, against 10 of 60 on the in-repo engine. The engine choice now
decides whether measurements are usable at all.

**Current state**

Measured on one mission. One scene is not enough to flip a default.

**Recommended implementation**

Run both engines on `agz_pass` and `agz_seg2` as well, plus the synthetic
regimes in `eval/cases.py` to check nothing regresses there. Report the
measurement-standing split (how many measurements are blocked only by
calibration) alongside the position errors, since that is what the engine now
determines. If COLMAP holds, change the default and make the OpenCV engine an
explicit fallback when PyCOLMAP import fails. Keep both tested either way.

**Relevant files**

`reconstruction/drishti_recon/pipeline.py` (`PipelineParams.engine`),
`colmap_adapter.py`, `eval/`

---

## P2 — Improvements

### Performance: consolidate the 12.2 min result (DEC-041)
**Status:** TODO.
- Three fresh runs each of DJI_1003 and DJI_1001, plus a real 600 s clip; report median and max.
- Validate the new dense defaults on a second reference scene before calling them general.
- Stream the decode so peak RAM is not all analysed frames (10.5 GB now).
- GPU matching (`sfm_gpu_matching`) saves ~28 s; validate on UseGeo end to end before enabling.
- A100: run the same defaults; the ladder may afford 20 sources again there.

### Hole fill: tighten the hole definition and test it on a real water level

**Status:** TODO. Fill landed 2026-09-23 ([DEC-040](DECISIONS.md)).
- 31% of DJI_1003's surveyed area is fill at 2.1 m cells, because sparse
  canopy and rooftops count as holes. Consider a minimum hole area, or a
  coarser cell for the hole test only.
- Water detection (flat, low-texture, dark rim-enclosed regions) would let
  the fill say "water" rather than "hole", and let river slope be modelled.
- No water-level reference exists for either site. A capture over a gauged
  lake or reservoir would give one.


### Decide the dense voxel size

**Status:** TODO
**Priority:** P2

Patch-match produced 1,386,161 points; the pipeline's 0.15 m voxel keeps
251,998. That default was chosen for sparse clouds where every point is a
tracked feature, and it has not been revisited for dense output. A finer voxel
keeps more detail at proportionate memory and export cost; the browser viewer
subsamples to 120,000 regardless, so this is about the exported PLY/LAS and
measurement snapping, not about how it looks on screen.

**Relevant files**

`reconstruction/drishti_recon/pipeline.py` (`PipelineParams.voxel`), `fusion.py`

---


Nothing. Per-point uncertainty on the COLMAP path, the previous P0, landed on
2026-09-20 — see [DEC-012](DECISIONS.md) and the
[WORKLOG entry](WORKLOG.md). The top of the backlog is now P1.

---


### Re-examine the three approximations the local refit rests on

**Status:** TODO
**Priority:** P2

**Why it matters**

[DEC-014](DECISIONS.md) introduced three mechanisms with named failure modes,
none validated against truth because this mission has none:

- The **Sim(3) re-anchor** that gauge-fixes the subproblem, instead of a
  fixed-camera mask in `bundle_adjust`. Measured drift is 0.054 m at scale
  0.9993, so it is behaving — but it is a workaround for a solver limitation.
- The **quadrature combination** of the refit's sigma with the neighbourhood's.
  It prevents the refit reporting 0.006 m on a point the model knows to 0.036 m,
  but it assumes the two terms are independent, and they are not entirely.
- The **coverage exemption** for a refined endpoint. This loosens a safety gate
  on the argument that frames demonstrably measured the point. It is the change
  most worth re-examining if refined measurements later prove unreliable.

**Recommended implementation**

The first is the only one with a clean fix: add a `fixed_cameras` mask to
`bundle.bundle_adjust` and drop the re-anchor. The other two need reference
dimensions to validate, so they wait on field data.

**Relevant files**

`reconstruction/drishti_recon/bundle.py`, `refinement.py` (`_local_bundle`)

---

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

---

## Data needed for the two benchmarks we cannot currently run

**Searched 2026-09-22.** The gap is structural, not an oversight: photogrammetry
research datasets ship **image sequences**, because compression hurts SfM, while
public drone *video* datasets exist for detection and tracking and carry no
survey truth. UseGeo, Zurich MAV, EuRoC and Blackbird are all stills. That is
why every saved study here uses video assembled from frames, which the
22 September review correctly flagged.

The two needs separate, and only one of them is hard.

### A — Native video for the speed requirement (20% of the score)

Needs a real 10-minute 1080p/4K drone video with telemetry. **No ground truth
required** — this benchmark is about time, not accuracy, and we have never run
one.

1. **[PinPoint validation dataset](https://zenodo.org/records/22671839)** —
   Zenodo, 1.7 GB, CC BY 4.0. Two VTOL flights, native H.264 video, ArduPilot
   `.BIN` DataFlash logs, ground control campaigns. **Take it for native-video
   ingestion and timing.** Two caveats: the video is 1280x720 at 60 fps, below
   the 1080p/4K the organiser specifies, and its control points are validated
   against PNOA orthophoto at **9.5-12.7 m RMSE** — three orders of magnitude
   coarser than our current 0.324 m, so useless as accuracy truth. `.BIN` needs
   pymavlink to reach our CSV schema.
2. **Any DJI flight with SRT telemetry.** This is the de-facto standard for
   georeferenced drone video — OpenDroneMap uses the identical
   `video.mp4` + `video.srt` convention — and our parser already reads it. A
   single real 10-minute 4K flight would close this benchmark. Consumer footage
   is adequate here because only the clock matters.

### B — Independent accuracy truth (30% of the score)

Harder, and the honest position is that **the combination of native video,
telemetry and sub-metre truth does not appear to exist publicly.**

The best available remains **UseGeo datasets 2 and 3** (see the entry above):
LiDAR reference, two further independent sites, same download path. They are
stills, so they extend accuracy and generalisation evidence but not the
native-video claim.

Surveyed landmarks remain the only way to get a valid *dimensional* figure at
all — every position-based correspondence leaks ([DEC-037](DECISIONS.md)), and
the one valid scorer measures the camera network rather than scene features.

### Done while searching

`telemetry.load()` now accepts a **video path** and extracts an embedded
subtitle track. Newer DJI models carry telemetry inside the MP4 rather than
beside it; requiring the sidecar refused good footage over a packaging detail
the operator has no reason to know about. Tested end to end against a
DJI-shaped embedded track.
