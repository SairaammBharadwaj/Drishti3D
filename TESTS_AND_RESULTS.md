# Tests and Results

What has actually been run, and what it produced. Anything not run says
`NOT TESTED`.

Last updated: 2026-09-19.

**Environment for every result below:** Linux 7.2.6-arch2-1 x86_64, Python
3.12.14, NumPy 2.5.2, SciPy, OpenCV 5.0.0, PyCOLMAP 4.2.0, PyTorch 2.11.0+cu128,
FastAPI 0.141.1, pyproj 3.7.2, RTX 5060 Laptop (8151 MiB).

---

## Unit and integration tests

### Full suite

Command: `cd drishti3d && .venv/bin/python -m pytest tests/ -q`

| Run | Result | Duration |
|---|---|---|
| Before this session's changes | 223 passed | 111 s |
| After this session's changes | **264 passed, 0 failed** | 140 s |

41 tests were added. No test was removed, skipped or weakened.

### New test files

#### `tests/test_timing_and_freespace.py` — 6 tests, all PASS

| Test | Asserts | Result |
|---|---|---|
| `test_post_read_pts_adopted_when_pre_read_lags` | A pre-read PTS series that duplicates at the start and lags by one frame is rejected, and the post-read series is adopted with a warning naming the convention | PASS |
| `test_pre_read_pts_wins_when_both_are_usable` | A backend reporting the documented pre-read convention is not overridden | PASS |
| `test_all_zero_pts_still_falls_back_to_nominal` | A container with no timing keeps `frame_index/fps` | PASS |
| `test_no_depth_return_is_not_verified_free_space` | Every `EMPTY` cell has a ray that reached a finite depth; no `EMPTY` cell lies behind the surface that terminated its rays | PASS |
| `test_free_space_stops_short_of_the_surface` | `occlusion_tol` is subtracted for free space, not added: the uncertain metre before a wall is not declared clear | PASS |
| `test_free_count_survives_the_npz_round_trip` | `free_count` is persisted in `coverage.npz` | PASS |

#### `tests/test_questions.py` — 18 tests, all PASS

Covers the acceptance rules. Highlights:

| Test | Asserts | Result |
|---|---|---|
| `test_uncalibrated_system_cannot_claim_meets_requirement` | A 0.118 m interval inside a 0.20 m tolerance still yields `estimated_only` without a validated profile | PASS |
| `test_calibrated_profile_permits_acceptance` | With a 40-sample validated profile (k95 = 1.6), the same measurement reaches `meets_requirement` with a 0.096 m interval | PASS |
| `test_small_calibration_sample_blocks_acceptance` | A 10-sample profile is refused; reason `calibration_sample_too_small` | PASS |
| `test_tightening_tolerance_changes_status_not_the_measurement` | 0.20 m → `meets_requirement`, 0.05 m → `needs_refinement`, identical value and interval | PASS |
| `test_low_parallax_blocks_acceptance_even_with_many_views` | 50 views at 0.4° separation → `estimated_only`, dominant limitation `degenerate_view_geometry` | PASS |
| `test_scale_uncertainty_dominating_is_reported_separately` | 5% scale on a 40 m span raises `scale_uncertainty_dominates`, whose guidance names a better scale source rather than refinement | PASS |
| `test_threshold_uses_the_interval_not_the_point_estimate` | 3.42±0.10 vs 3.20 → `above`; 3.25±0.10 → `indeterminate`; 3.00±0.10 → `below` | PASS |
| `test_verdict_dict_is_json_safe_with_infinite_interval` | An infinite interval serialises as `null` plus an explicit flag, never as invalid JSON `Infinity` | PASS |
| `test_frustum_derived_view_support_cannot_license_acceptance` | `view_support_basis="frustum_upper_bound"` blocks acceptance even with a valid profile | PASS |
| 9 further parametrised refusal cases | Each hard refusal yields `not_observable` with the matching reason as dominant limitation | PASS |

#### `tests/test_evidence.py` — 8 tests, all PASS

| Test | Asserts | Result |
|---|---|---|
| `test_relative_scale_uncertainty_is_divided_by_the_scale_factor` | 0.1943 / 16.95 = 1.15%, not 19.4% | PASS |
| `test_missing_alignment_leaves_scale_unknown_not_zero` | No alignment block → `scale_sigma_rel` is NaN, not 0 | PASS |
| `test_visible_cameras_needs_intrinsics_and_returns_nothing_without_them` | No `K` → empty candidate set, never a distance-based guess | PASS |
| `test_parallax_is_measured_between_rays_not_counted_in_cameras` | 9 cameras on an arc → >40°; 9 cameras on a 2 m line at 400 m range → <1° | PASS |
| `test_evidence_is_stamped_as_an_upper_bound` | Every record carries `view_support_basis="frustum_upper_bound"` | PASS |
| `test_the_weakest_endpoint_sets_the_support` | One endpoint behind every camera → 0 supporting views for the whole measurement | PASS |
| `test_inferred_geometry_is_flagged` | `AI_ASSISTED` provenance → `touches_inferred`, `endpoints_observed=False` | PASS |
| `test_supporting_frames_are_ranked_for_diversity_not_proximity` | 4 frames chosen from 11 span more than 3 indices | PASS |

#### `tests/test_questions_api.py` — 9 tests, all PASS

End-to-end through FastAPI against a synthetic project whose artifacts are
written the way the pipeline writes them (cloud with per-point sigma, trajectory
with `K`, `R` and `image_size`, manifest with an alignment block).

| Test | Asserts | Result |
|---|---|---|
| `test_question_returns_a_value_an_interval_and_a_status` | 5.6 m width recovered within 0.3 m, with a finite sigma and an interval | PASS |
| `test_uncalibrated_deployment_never_reports_meets_requirement` | Tolerances 0.01, 0.2, 5.0 and 100.0 m all fail to produce acceptance | PASS |
| `test_changing_tolerance_moves_the_status_not_the_value` | `PATCH` from 5.0 m to 0.001 m flips `estimated_only` → `needs_refinement` with identical value, interval and result id | PASS |
| `test_every_refusal_carries_an_actionable_reason` | Every reason code carries an explanation and a next action; the dominant limitation is among the reasons | PASS |
| `test_threshold_query_reports_indeterminate_when_the_interval_straddles` | Threshold results are interval-based | PASS |
| `test_evidence_lists_candidate_frames_and_admits_what_it_is` | `support_basis` is `frustum_upper_bound`, the note says "upper bound", both endpoints list frames | PASS |
| `test_measurement_on_a_project_without_a_reconstruction_is_refused` | 404, not a fabricated answer | PASS |
| `test_tolerance_must_be_positive` | 400 | PASS |
| `test_delete_removes_the_question_and_its_results` | Cascade delete | PASS |

### Pre-existing suites

`test_api_storage`, `test_bundle`, `test_coverage`, `test_eval`,
`test_features`, `test_frames`, `test_gaussians`, `test_geo`,
`test_integration`, `test_intel_metrics`, `test_kalman`,
`test_masking_backends`, `test_pose_graph`, `test_quality_measure`,
`test_sensors`, `test_srt_telemetry`, `test_telemetry_sync`, `test_trust`,
`test_uncertainty`, `test_verify_capture` — all pass unchanged, including
`test_coverage.py`'s 31 assertions after the free-space rule change.

---

## End-to-end reconstruction on real data

### AGZ single-pass engine comparison

Full write-up:
[`drishti3d/docs/benchmarks/2026-09-19_agz_single_pass_engines/RESULTS.md`](drishti3d/docs/benchmarks/2026-09-19_agz_single_pass_engines/RESULTS.md)

**Input:** mission `agz_dense_pass` — 184 frames, 184.4 s, 233.1 m flown,
1.17 m median baseline, GNSS 3D fix throughout with 9.43 m median `eph`.
Video sha256 `3b9bd9754db9c188…`.

**Reference:** 184 published AGZ camera positions (EPSG:32632). *Not
independent* — Pix4D photogrammetry by the dataset authors, uncertainty not
published. Never given to the reconstruction.

| Metric | OpenCV | COLMAP | Onboard GPS |
|---|---:|---:|---:|
| Wall clock | 310.7 s | 86.4 s | — |
| Keyframes / registered | 80 / 80 | 80 / 80 | — |
| Registered as a fraction of 184 decoded frames | 43.5% | 43.5% | — |
| Mean track length | 2.78 | 3.91 | — |
| Median reprojection error | 0.231 px | 0.326 px | — |
| Position error vs reference, as georeferenced (median) | 3.70 m | 3.76 m | 4.60 m |
| … p90 | 6.91 m | 6.84 m | 11.32 m |
| … max | 9.99 m | 10.93 m | 25.08 m |
| Position error after Sim(3) (median) | 0.68 m | **0.32 m** | — |
| Relative scale 1-sigma | 1.17% | 1.15% | — |
| GNSS alignment RMSE | 6.29 m | 6.14 m | — |

**Result: PASS** against the G1 exit gate in plan section 8.2 ("repeatable
metric result on development data, explicit low-parallax failure, baseline
report") for the reconstruction half. Reproducibility was confirmed: the COLMAP
run was executed twice, 86.1 s and 86.4 s wall, medians 3.7627 m and 3.7635 m.

**Observed failures in the same run**, all correctly reported as warnings rather
than absorbed:

- Time-offset estimation declined: peak correlation −0.07, confidence 0.00
  against thresholds 0.5 / 0.3. The pipeline says "motion may be too uniform to
  reveal timing" and applies no offset.
- Gravity levelling rejected: it would have raised the GNSS alignment residual
  from 6.14 m to 14.97 m.
- Variable-frame-rate timing detected: real timestamps diverge from
  `frame_index/fps` by up to 1.264 s. Before this session's fix this run would
  have silently used the nominal clock.

### Measurement accuracy on real data

`NOT TESTED`. There are no reference dimensions for this site. Distance, height
and area error against ground truth is entirely unmeasured.

### Same-pass refinement (plan F4)

`NOT TESTED` — not implemented.

### Measurement passport and offline verifier (plan F3)

`NOT TESTED` — not implemented.

---

## Uncertainty calibration

`NOT TESTED`. No `CalibrationProfile` has been fitted or validated for any
capture regime. Empirical interval coverage on held-out missions has never been
measured.

This is why **no measurement in the system can currently be accepted**. The
strongest verdict reachable is `estimated_only`, and
`test_uncalibrated_deployment_never_reports_meets_requirement` asserts it end to
end. See [DEC-003](DECISIONS.md#dec-003--acceptance-requires-a-validated-calibration-profile).

The machinery exists and is unit-tested (`uncertainty.calibrate`,
`conformal_factors`, `coverage_report`, `CalibrationProfile.from_calibration`);
only the data does not.

---

## Manual verification

### Video presentation timestamps round-trip

Built `datasets/public/zurich_mav/agz_dense_pass/raw/video.mp4` with per-frame
durations from the AGZ log, decoded it with OpenCV and compared against
`frame_index.csv`.

| | Expected | Observed |
|---|---|---|
| Frame count | 184 | 184 (was 185 before the trailing-duplicate fix) |
| PTS, post-read | matches `pts_s` | max deviation ~8 ms, median ~1 ms |
| PTS, pre-read | matches `pts_s` | lags by one frame; first two both 0.000 |

**Result: PASS**, and it is what produced [DEC-005](DECISIONS.md).

The same pre-read lag was then confirmed on two unrelated constant-rate videos
(`gymnasium_single_pass.mp4`, `sample_data/synthetic/synthetic_flight.mp4`), so
it is a property of this OpenCV build and not of the generated file.

### Evidence assembly on the real reconstruction

Loaded `ReconstructionEvidence` from the COLMAP run's artifacts and queried a
point near the cloud centroid.

| Field | Observed |
|---|---|
| Cameras loaded | 80, with rotations |
| `K`, image size | present, 1280×720 |
| Candidate views for the sample point | 8 |
| Max ray separation | 78.45° |
| Within established coverage | true |
| Scale source / relative sigma | `gps` / 1.146% |
| Verdict at ±0.20 m | `estimated_only`, dominant limitation `scale_uncertainty_dominates`, reasons `[view_geometry_unverified, interval_not_calibrated, scale_uncertainty_dominates]` |

**Result: PASS.** The evidence path works end to end on real artifacts, and the
verdict names the real binding constraint.

### Dataset inventory

`scripts/inventory_datasets.py` over 16 entries, 2.4 GB hashed.

| Check | Observed |
|---|---|
| Unfetched Git-LFS pointers | **0** across all entries |
| AGZ bundled MAV frames (1–350) flown geometry | 6.07 m path, 0.66 m net displacement over 11.6 s |
| `agz_dense` flown geometry | 233.1 m path, 201.9 m net, 1.17 m median baseline, 184 reference positions |
| `agz_pass` | 228.8 m path, 3.48 m median baseline, 62 reference positions |
| `agz_seg2` | 174.8 m path, 2.80 m median baseline, 62 reference positions |
| AGZ `epv_m` column | median 1.29e-43 — corrupt, not metres |

**Result: PASS.** This corrected a stale note in the project's working memory
claiming the bundled binaries were unfetched LFS pointers; in this checkout they
are real data.

---

## Security tests

Pre-existing and passing in `tests/test_api_storage.py`: filename sanitisation,
project-ID path-traversal rejection, upload validation.

No security review has been run against the new question endpoints beyond the
project-ID resolution they inherit. `NOT TESTED`: authentication (there is
none), rate limiting, hostile-media handling in the decoder.

---

## Performance

Measured on the AGZ mission, 184 frames at 1280 px processing width, CPU only.

| Stage | OpenCV | COLMAP |
|---|---:|---:|
| ingestion | 0.21 s | 0.21 s |
| telemetry | 0.002 s | 0.002 s |
| frames (decode) | 1.14 s | 1.13 s |
| quality | 0.60 s | 0.61 s |
| sync | 0.002 s | 0.002 s |
| keyframes | 0.20 s | 0.21 s |
| **sfm** | **290.6 s** | **77.7 s** |
| georegistration | 0.06 s | 0.06 s |
| fusion | 0.05 s | 0.04 s |
| mesh | 0.90 s | 0.90 s |
| report | 0.04 s | 0.02 s |
| exports | 0.25 s | 0.17 s |
| **total wall** | **310.7 s** | **86.4 s** |

SfM is 90% of the runtime in both cases. GPU memory: unused — neither engine
touches the GPU. `NOT TESTED`: VRAM under the optional learned backends, and
throughput at 4K processing width.

---

## Known Failures

### Registration uses 43.5% of the pass

Keyframe selection kept 80 of 184 decoded frames and SfM registered all 80, so
104 frames contributed nothing. The loss is in selection, before either engine
sees the data. **Suspected cause:** `keyframes.select` thresholds tuned on
denser video; not yet confirmed. Tracked as P1 in `NEXT_STEPS.md`.

### Gravity levelling is wrong on this capture

Both engines' levelling would have more than doubled the GNSS alignment
residual, and both correctly declined it. The rejection is the right behaviour,
but the levelling estimate being that wrong on a normal oblique pass is not
explained. **Cause unknown.**

### Time-offset estimation is uninformative here

Peak correlation −0.07 with confidence 0.00. The pipeline's own diagnosis —
motion too uniform to identify the offset — is plausible for a steady traverse
but has not been confirmed against a capture with a known offset. **Cause not
independently verified.**

### Scale uncertainty blocks any tight tolerance

1.15% relative scale 1-sigma is ±46 cm on a 40 m span before any other error
source. A ±20 cm tolerance is unreachable beyond about 9 m from this capture.
This is a correctly reported property of a 9.4 m `eph` receiver, not a defect —
but it means the AGZ mission cannot demonstrate a tight-tolerance acceptance
even once calibration exists.
