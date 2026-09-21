# Verification of the critical-review fixes

**Reviewed checkout:** `61939db` · **Date:** 21 September 2026  
**Compared with:** `d94ec29` and [the original critical review](NTRO_CRITICAL_REVIEW_AND_IMPROVEMENTS_2026-09-21.md).

**Result: substantial progress, but not ready to mark everything fixed.** All six original executable counterexamples now pass. The existing suite passes **422 tests** and the production frontend builds. However, **nine of fifteen independent follow-up checks fail**, including two newly introduced crashes in important workflows.

This verification changes no application code or saved mission data. It adds this report and a separately runnable audit test file/results under [review_checks](review_checks/test_followup_2026_09_21.py). The failing checks assert required behaviour; they are deliberately not marked as expected failures.

## 1. What is verified

| Check | Fresh result |
|---|---|
| Existing `tests/` suite | **422 passed**, 49 deprecation warnings, 112.82 seconds |
| Frontend TypeScript + Vite production build | **Passed** |
| Original six counterexamples | **6/6 corrected** in independent checks |
| Follow-up checks including adjacent/API cases | **6 passed, 9 failed** |
| Rebuilt dense artifact integrity and LAS consistency | Checked directly; figures below match saved artifacts |
| Complete browser walkthrough | Not performed; no browser automation runtime was available in this environment |
| New field capture, calibrated measurement accuracy | Not established; no stored calibration profiles found |
| New GPU reconstruction during this verification | Not run; inspected the user's rebuilt output directly |
| Clean-machine offline installation, restart/concurrency recovery | Not demonstrated; source-level review only |

### Original counterexamples that now pass

1. A 10 m line with 10% common scale noise keeps **sigma 1.0 m** after adding a collinear midpoint.
2. The original 990 m remote selection is refused on the original three-point fixture.
3. LAS export with a valid Zurich origin declares **EPSG:32632** and preserves provenance, confidence and sigma.
4. Replacing `cloud.npz` causes `load_cloud` to return the replacement geometry.
5. A `[100,200,30]` m global offset is counted as **225.6103 m** absolute position error, rather than zero.
6. Distortion coefficients survive `ProcessRequest.intrinsics` validation.

These fixes are real. Several broader review items remain incomplete because correcting the first counterexample did not finish the whole workflow.

## 2. Blocking failures reproduced in this checkout

### F01 — A refinement that recovers a frame crashes before returning its result

**Severity: P0. New regression in the C06 change.**

The new per-endpoint aggregation in `RefinementEngine.refine` calls `rec.observations_of(q)` and `rec.measured_ray_separation_deg(q)`, but there is no `rec` binding in that method or module. The evidence object is stored on the engine as `self.ev`.

**Observed:** exercising the real `refine()` method through its successful recovery branch raises:

```text
NameError: name 'rec' is not defined
refinement.py:1502
```

The reproduction controls image registration, pixel location and the local fit so it does not require a GPU or real video. It executes the actual orchestration and aggregation code; it does not copy that implementation into the test. This establishes the branch failure, not real-image refinement quality.

**Why 422 tests missed it:** `test_refinement_record.py` defines its own `_aggregate` helper and checks that helper. It reproduces the intended algorithm rather than calling the production branch where the undefined variable exists. Existing refinement tests also cover several no-recovery exits without traversing this new path.

**Required fix:** use the engine's actual evidence object and test successful recovery through the real method. Then verify the persisted endpoints, per-endpoint support and returned evidence together.

**Evidence:** [refinement.py](../reconstruction/drishti_recon/refinement.py), lines 1500–1504; [copied aggregation test](../tests/test_refinement_record.py), `_aggregate`; audit test `test_successful_frame_recovery_finishes_real_refinement_method`.

### F02 — Video-only reconstruction crashes in the new export sidecar code

**Severity: P0. New regression in the C08 change.**

`quality.build_report` returns `alignment=None` when alignment is absent. The new export path calls:

```python
report.get("alignment", {}).get("scale_source")
```

The default `{}` applies only when the key is absent, not when its value is `None`.

**Observed:** calling the real artifact writer with the report shape produced for a video-only run raises:

```text
AttributeError: 'NoneType' object has no attribute 'get'
pipeline.py:1152
```

This occurs after cloud/PLY/LAS writing and before viewer/report completion, so it can leave a partial artifact set. The existing integration run supplies telemetry and does not exercise this case.

**Required fix:** handle null alignment and explicitly preserve relative units. There is a second source-confirmed issue to address at the same time: the pipeline creates `ENUFrame(0,0,0)` for missing telemetry and passes it to LAS export. The new exporter interprets any supplied frame as a geographic origin. Merely fixing `.get()` would still allow an arbitrary-scale reconstruction to receive an invented UTM placement and metre labels. Decide geographic export eligibility from established scale/alignment, not the existence of a frame object.

**Evidence:** [artifact writer](../reconstruction/drishti_recon/pipeline.py), lines 1144–1152 and no-telemetry frame initialization near line 172; [quality report](../reconstruction/drishti_recon/quality.py), `build_report`; audit test `test_video_only_artifact_export_completes`.

### F03 — Question results still label arbitrary-scale geometry in metres

**Severity: P0. C01 is only partly fixed.**

The new `results.compute` correctly changes a nonmetric result's unit and warning. `/measurements` calls it. `/questions` still runs the old duplicated `_answer` implementation and stores `m.unit` directly. The new module's claim that both routes call `compute` is not true in this checkout.

**Observed on the same isolated project without alignment:**

| Route | Returned unit |
|---|---|
| `POST /measurements` | `reconstruction units` |
| `POST /questions` | `m` |

The question gate still refuses calibrated acceptance; this finding is about inconsistent physical units, not a claim that the production API currently grants calibrated acceptance.

**Required fix:** make both routes store the same shared result contract. Preserve unit dimensionality for area as well. Update the ordinary Workspace result card: it still renders the old value/confidence-note presentation and does not display all newly returned trust fields.

**Evidence:** [results.py](../backend/app/results.py), `compute`; [questions route](../backend/app/routers/questions.py), `_answer` at line 69; [Workspace](../frontend/src/views/Workspace.tsx); audit test `test_both_routes_use_nonmetric_units_without_scale`.

### F04 — Refinement metadata makes subsequent tolerance changes fail

**Severity: P1. New integration failure in C06.**

The refinement route now adds `endpoints_moved_m` into the persisted `evidence` dictionary. `PATCH /questions/{id}` reconstructs the evidence dataclass using `qmod.Evidence(**prior.evidence)`. That dataclass has no `endpoints_moved_m` field.

**Observed:** seed precisely the metadata shape the refinement route writes, then change the tolerance: **HTTP 500**. The extra key is incompatible with the dataclass constructor. This remains a failure even after F01 is repaired.

**Required fix:** give evidence a schema and separate refinement diagnostics from gate inputs, or deserialize them explicitly. Add an API sequence test: create → successful refine → change tolerance → reload → inspect evidence. Do not test only isolated snapshot dictionaries.

**Evidence:** [questions route](../backend/app/routers/questions.py), line 281 and `endpoints_moved_m` at line 477; audit test `test_refined_result_metadata_does_not_break_tolerance_changes`.

### F05 — Unsupported interval levels are rejected on create but persisted on update

**Severity: P1. Incomplete validation fix.**

Creation checks supported interval levels. Updating a question does not. The PATCH path commits the supplied level before `evaluate()` raises for an unsupported level.

**Observed:** patch a valid question from 95 to 97:

```text
HTTP status: 500
Stored question interval_level after the failed request: 97
```

**Required fix:** apply shared validation before modifying or committing the question. Commit requirement/result changes atomically. Invalid input must produce a useful 4xx response and leave the stored question unchanged. A library exception after persistence is not successful API validation.

**Evidence:** [questions route](../backend/app/routers/questions.py), lines 254–266; audit test `test_invalid_patch_level_is_rejected_without_persisting`.

## 3. Additional failures and unresolved correctness boundaries

### F06 — Cache identity and saved-result identity use different revisions

**Severity: P1. C07 remains partial.**

Caches use `storage.artifact_revision`, which reflects cloud/lineage/coverage file changes. Stored answers use `results.artifact_version`, which is only a video-hash prefix plus a rounded manifest creation time.

**Observed:** replace `cloud.npz` without replacing the manifest. The cloud loader correctly reads the new data, but listing the previous question returns `superseded=False` and its old artifact version. A partial/failed rerun can produce this state, since files are still written in place. PATCH can also reuse the old result when this manifest-based version is unchanged.

**Required fix:** a shared immutable run identity for cloud, evidence and answers; publish complete artifact sets atomically. The new superseded indicator correctly handles changed manifest identity, but it does not prove complete revision safety. Input replacement and ordinary measurement-list staleness also remain outside that indicator.

**Evidence:** [storage.py](../backend/app/storage.py), `artifact_revision`; [results.py](../backend/app/results.py), `artifact_version` at line 56; audit test `test_cloud_replacement_marks_stored_question_superseded`.

### F07 — The remote-snap fix fails for a one-point cloud

**Severity: P2 for the reproduced edge case; C03 remains partial.**

`snap_tolerance` returns infinity when the cloud has fewer than two points.

**Observed:** a cloud containing `[0,0,0]` accepts `[1000,0,0]`, moving the selection **1,000 m** with `resolved=True` and infinite tolerance. This does not mean the original three-point case is still broken; that case now passes.

**Required fix:** when there is insufficient geometry to estimate spacing, refuse or require a bounded explicit selection tolerance. Also review the current global-spacing estimate: it computes neighbour spacing within a random subset, which can inflate the estimate on large clouds, and its `allow_inferred` argument is not used. It still excludes only the AI-assisted class rather than using an explicit allowed-provenance set.

**Evidence:** [measure.py](../reconstruction/drishti_recon/measure.py), `snap_tolerance` at line 70 and `snap`; audit test `test_single_point_cloud_must_also_refuse_remote_snap`.

### F08 — Dense uncertainty now responds to baseline, but its angular domain is unsafe

**Severity: P1 model issue; two independent checks fail.**

The new angle-dependent term is a useful correction in the tested narrow-angle regime. It still uses `1 / tan(angle)` without handling the full range returned by `contributing_parallax_deg`.

**Observed:**

- Two camera centres and a point forming a genuine **120°** contributing angle produce a **negative sigma** when no floor is supplied. The check computes the angle from the geometry; it does not invent an inconsistent angle argument.
- Coincident cameras with **0°** parallax produce finite sigma **4.0513** in reconstruction units, because the angle is clamped upward to 0.5°. This contradicts the documented claim that below-threshold geometry is unconstrained.

A supplied floor hides the negative sign through `hypot`, but does not repair the geometry; near 90° the stereo term approaches zero. Existing question-level parallax refusals provide some additional protection for tiny angles. These tests do not show that the saved AGZ cloud contains negative sigma—it does not.

**Required fix:** use a triangulation/Jacobian-based uncertainty model over the supported geometry, or explicitly refuse unsupported configurations. Do not convert unknown/zero baseline into a convenient minimum baseline. Test zero, missing, near-parallel, wide and obtuse configurations through the actual helper and pipeline. Empirical coverage validation remains required after numerical corrections.

**Evidence:** [mvs.py](../reconstruction/drishti_recon/mvs.py), `depth_uncertainty`, especially lines 226–240; audit tests `test_dense_depth_sigma_is_positive_for_obtuse_view_angle` and `test_dense_near_parallel_geometry_is_not_reported_finitely_constrained`.

## 4. Saved dense reconstruction: independent file checks

Inspected `data/runs/agz_dense_pass__c04_parallax/artifacts/` directly. These are integrity and consistency checks, not independent surface-accuracy measurements.

| Quantity | Verified value |
|---|---:|
| Cloud points | 252,127 |
| Finite sigma values | 252,127 |
| Negative sigma values | 0 |
| Sigma p10 / median / p90 / p99 | 0.03452 / 0.03854 / 0.09088 / 0.32553 m |
| Observation rows | 1,332,620 |
| Sparse-feature rows | 20,143 |
| Dense-contributor rows | 1,312,477 |
| Points with lineage | 252,127 |
| Out-of-range observation point indices | 0 |
| Observation rows referencing unknown camera frame IDs | 0 |
| LAS CRS | EPSG:32632 |
| LAS extra dimensions | provenance, confidence, sigma |
| LAS sigma vs NPZ sigma | Matches within numeric conversion tolerance |
| Largest LAS coordinate discrepancy in a 1,000-point projection comparison | 0.000500 m, consistent with millimetre quantization |

These results corroborate the reported rebuilt point count, uncertainty quantiles, observation-kind totals and geographic export improvement. They do **not** prove that the dense-contributor association is the correct surface at a discontinuity, that an interval covers a true dimension, or that field performance generalises.

Read-only inspection of the saved database found **zero stored calibration profiles**, with result statuses `estimated_only`, `needs_refinement` and `not_observable`. It found no stored `meets_requirement` result. That is consistent with the production calibration gate still being disabled.

## 5. Status of every original critical finding

| ID | Verdict | Verified progress and remaining work |
|---|---|---|
| C01 — Shared result contract | **Partial** | Legacy route stores trust fields and corrects relative units; question route still duplicates logic and returns metres without scale. F03. |
| C02 — Polyline covariance | **Fixed for the reviewed defect** | Whole-polyline propagation; original subdivision example passes and existing Monte Carlo tests pass. Correlation between reconstructed points remains a declared modelling assumption. |
| C03 — Remote snapping | **Partial** | Original 990 m example refused; singleton case still unbounded; provenance/local-selection concerns remain. F07. |
| C04 — Dense uncertainty | **Partial, not validated** | Contributing angles now affect estimates; actual rebuilt artifacts verified; angular edge cases fail and field coverage remains unproven. F08. |
| C05 — Dense lineage | **Partial** | Observation-kind flags reach artifacts/API/UI. Nearest dense-neighbour attribution within a voxel diagonal still substitutes contributor lists, without the requested surface-boundary checks or exact fusion identity. |
| C06 — Refinement consistency | **Blocked by regression** | Moved-endpoint persistence and threshold recalculation are present, but real successful recovery crashes. Subsequent tolerance changes also fail on new metadata. Recovered-frame evidence and frontend cache remain incomplete. F01/F04. |
| C07 — Revision safety | **Partial** | Cached geometry refreshes; superseded flag exists for manifest changes. Stored-result identity diverges from cache identity; immutable runs/atomic publication/input replacement handling remain. F06. |
| C08 — Geographic exports | **Working on the metric path; relative path regressed** | Saved AGZ LAS CRS, coordinates and sigma verified; video-only artifact export crashes and needs explicit scale-aware export handling. F02. |
| C09 — Absolute scoring | **Fixed for the reviewed defect** | Absolute residual no longer removes translation; explicit translation and similarity comparisons remain. Independent positional truth is still absent. |
| C10 — Calibration release lifecycle | **Partial** | Fit/evaluation/release states and overlap checks exist; sample count alone no longer releases a profile. Regime matching remains an optional helper, not enforced by `evaluate`; no production profile selection or empirical validation. |

**The backlog's “Closed by DEC-021 … DEC-030” table overstates closure.** Its later admission that two parts of C06 remain open is useful, but it does not cover the new reproduced crashes or the other incomplete acceptance criteria above.

## 6. Remaining operator, validation and deployment items

This is a code/documentation status check for the rest of the original review, not a claim that each was exercised in a live browser or field deployment.

| Original item | Current status |
|---|---|
| U01 — Select COLMAP/MVS through new-upload workflow | **Open.** Wizard still offers only sparse or depth-prior densification; no engine selector or MVS option. |
| U02 — Full calibration workflow | **Partial.** JSON schema preserves distortion and source resolution; pipeline rescales intrinsics. Wizard/form route still accepts only fx/fy/cx/cy. Camera-model string is accepted but does not select a different undistortion implementation; unsupported models should be rejected until supported. |
| U03 — Visual Evidence Replay | **Open.** Frame badges and observation-kind counts, not annotated source images/video replay. |
| U04 — Unknown-space overlay | **Open.** Coverage artifacts exist; main viewer still does not render the field. |
| U05 — Measurement passport/offline verifier | **Open.** A georeference sidecar is useful, but is not a portable measurement/evidence verification bundle. |
| U06 — Precision selection | **Open.** No new edge/plane fit, section/picking workflow or operator-repeatability demonstration. |
| U07 — Units and question controls | **Partial.** Area tolerance label improved; create-time point count/interval validation improved. PATCH is unsafe; custom tolerance/threshold workflow remains incomplete. |
| U08 — Refinement budget/history | **Open/blocked.** Fixed four-frame UI request; no complete persistent-history surface; successful recovery regression and stale evidence. |
| U09 — Mission operator summary | **Open.** No new integrated summary addressing this item. |
| U10 — Coherent demo/workflow | **Open.** Prepared prototype/presentation and ordinary upload workflow still expose different capabilities. |
| V01 — Frozen independent field evaluation | **Unverified/open.** No new independent field truth or released profile demonstrated. |
| V02 — Failure/scene matrix | **Open.** Existing fixtures/results are useful; no completed new matrix across independent captures. |
| V03 — External baseline comparison | **Open.** Existing engine/refinement comparisons do not complete the proposed matched-tool/operator evaluation. |
| V04 — Supported textured surface and terrain output | **Open.** Coloured Poisson mesh remains; no new texture atlas, face-support verification or terrain deliverable implementation. |
| V05 — Sensor/dynamic evidence | **Open.** Mission-wide any-RTK labelling and unconditional `dynamic_contamination=False` remain in the inspected source. |
| R01 — Durable jobs and immutable inputs | **Partial at cache cleanup only.** No durable queue/restart recovery or atomic input/run revisions; glob-based input selection remains. |
| R02 — Clean offline installation | **Open.** GPU Docker worker remains a placeholder; no clean-machine demonstration. |
| R03 — Shared deployment access control | **Open.** No new authentication/project authorization/audit implementation. |
| R04 — Larger-scene resource envelope | **Open.** Dense runtime recorded; no new bounded/resumable/tiled resource workflow or scale matrix. |

The original optional showcase ideas also remain largely proposals: visual measurement receipts, visible unknown space, portable verification and supported cross-sections are not complete. Targeted compute and capture/scale limitation reasoning already exist in part, but need the correctness and evaluation work above before they become a dependable demonstration.

## 7. What to fix next

1. **Repair F01 and F02 first:** successful refinement and video-only export must complete. Test metric and relative-scale output separately.
2. **Unify the result path and fix state transitions:** F03–F06. Run create → refine → change tolerance → rerun → list/evidence/export as one sequence, with failed operations leaving stored state intact.
3. **Tighten geometric boundaries:** F07/F08, dense contributor attribution, selection provenance and calibration regime enforcement.
4. **Finish the actual demo workflow:** expose COLMAP/MVS and calibration in the wizard; add annotated evidence replay; show unknown space; deliver a complete evidence export.
5. **Validate against independent dimensions:** the rebuilt artifacts demonstrate consistency, not real measurement accuracy. Keep the calibration acceptance gate disabled until its evidence exists.

## 8. Reproduce this verification

Run the existing suite and frontend build:

```bash
cd drishti3d
.venv/bin/python -m pytest tests/ -q
cd frontend
npm run build
```

Run the independent checks **in a separate pytest invocation**, from `drishti3d/`:

```bash
.venv/bin/python -m pytest \
  docs/review_checks/test_followup_2026_09_21.py \
  -q --tb=short \
  --junitxml=docs/review_checks/followup_2026_09_21.xml
```

At this reviewed commit, a nonzero exit is expected because nine required behaviours fail. After fixes, these assertions should pass without weakening them. The test file uses a fresh temporary database/artifact directory; the successful-refinement check controls expensive recovery inputs while calling the real production orchestration method. The tolerance-after-refinement check seeds the exact persisted metadata shape to isolate that downstream contract.

The recorded results are in [the JUnit report](review_checks/followup_2026_09_21.xml). Test success is not a substitute for real-image accuracy, independent survey truth, browser usability or deployment verification; each has been kept separate in the status tables.
