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
| Before 2026-09-19 | 223 passed | 111 s |
| After the measurement gate | 264 passed | 140 s |
| After observation lineage | 277 passed | 112 s |
| After same-pass refinement | 301 passed | 191 s |
| After COLMAP uncertainty | 312 passed | 199 s |
| After the F4 experiment | 313 passed | 196 s |
| After the local bundle refit | 314 passed | 109 s |
| After the transfer locator | 318 passed | 117 s |
| After the Tolerance Lens UI and dense MVS | **333 passed, 0 failed** | 116 s |

110 tests were added. No test was removed, skipped or weakened.

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

#### `tests/test_lineage.py` — 7 tests, all PASS

Lineage survives fusion's reindexing.

| Test | Asserts | Result |
|---|---|---|
| `test_fuse_reports_where_every_surviving_point_came_from` | `source_index` is complete and injective — two fused points cannot claim the same source row | PASS |
| `test_source_index_actually_points_at_the_right_geometry` | Every survivor is within one voxel diagonal of the row it claims | PASS |
| `test_observations_are_remapped_onto_the_fused_indices` | 40 observations remap correctly; the one belonging to a point fusion discarded is dropped, not reassigned | PASS |
| `test_both_frame_numberings_are_recorded` | Keyframes 1 and 3 with `sel = [0,2,4,6,…]` emit decoded frames 2 and 6, and both numbers are stored | PASS |
| `test_no_lineage_in_means_no_lineage_out` | An engine that recorded nothing yields `None`, distinguishable from "this point has no observations" | PASS |
| `test_inferred_points_carry_no_source_row` | AI-proposed points get `source_index = -1`; row 0 is not "nothing" | PASS |
| `test_remap_ignores_inferred_rows_when_inverting` | The `-1` sentinel is never read as an index | PASS |

#### `tests/test_evidence.py` — 6 further lineage tests, all PASS

| Test | Asserts | Result |
|---|---|---|
| `test_lineage_parallax_is_measured_not_available` | Nine cameras see the point, two measured it; measured parallax is strictly less than the arc's full spread | PASS |
| `test_lineage_lifts_the_frustum_stamp` | With lineage on every endpoint the basis becomes `triangulated_observations` | PASS |
| `test_frame_numbering_is_not_guessed_between` | Observations resolve through the decoded frame index; keying on the keyframe index would find no camera and report zero parallax | PASS |
| `test_a_selection_far_from_any_point_inherits_no_lineage` | 50 m from the cloud → no lineage, rather than borrowing a distant point's evidence | PASS |
| `test_one_endpoint_without_lineage_downgrades_the_whole_measurement` | Mixed bases report as `frustum_upper_bound` | PASS |
| `test_supporting_frames_carry_the_measured_pixel` | Only the measuring frames are listed, each with the pixel it was measured at | PASS |

#### `tests/test_refinement.py` — 21 tests, all PASS

| Test | Asserts | Result |
|---|---|---|
| `test_the_unused_frames_of_the_pass_are_the_candidate_pool` | Frames in `keyframes.json` are excluded; the rest are candidates | PASS |
| `test_every_rejection_names_a_reason_and_explains_it` | Every rejected candidate carries a stable code and operator text | PASS |
| `test_frames_outside_the_registered_span_cannot_be_posed` | Frames before the first or after the last registered camera are refused rather than extrapolated | PASS |
| `test_blurred_frames_are_rejected_before_anything_is_decoded` | Quality rejection happens on the index, not after a decode | PASS |
| `test_a_view_parallel_to_an_existing_one_adds_nothing` | A 0.02 rad arc leaves no usable candidate; the gate is angular, not a frame count | PASS |
| `test_ranking_follows_parallax_not_frame_order` | Ordering is by score, and the best clears the 2° floor | PASS |
| `test_triangulation_recovers_a_known_point` | Three rays recover a known point to 1 mm with a finite sigma | PASS |
| `test_an_inflated_ray_pulls_less_on_the_solution` | A 20 px-wrong observation with inflated sigma moves the answer less than a trusted one — the inflation is real, not cosmetic | PASS |
| `test_a_runaway_solve_is_refused_not_returned` | A solve landing 200 m from the seed returns `None` | PASS |
| `test_near_parallel_rays_report_a_large_positional_sigma` | Weak conditioning shows in the sigma, not only in the guard (>10× wider) | PASS |
| `test_value_fn_does_not_snap_the_refined_endpoint_back` | Moving an endpoint 0.4 m moves the answer 0.4 m | PASS |
| `test_value_fn_carries_the_scale_term` | A 2% scale on a 40 m span widens sigma as `hypot(s0, 0.8)` | PASS |
| `test_improvement_is_not_judged_on_interval_width_alone` | A cleared blocking reason with an unchanged interval is an improvement | PASS |
| `test_a_wider_interval_with_nothing_cleared_is_not_an_improvement` | Refinement can make things worse, and it shows | PASS |
| 7 further cases | Other question kinds, missing video, empty candidate pools, the run record | PASS |

#### `tests/test_questions_api.py` — 12 tests, all PASS

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

### Same-pass refinement versus a uniform budget (plan F4 gate)

**Run five times against one frozen question set as the targeted arm was built
out. It now produces a higher answer yield than the control, on more compute.**
Full write-up:
[`docs/benchmarks/2026-09-20_f4_targeted_vs_uniform/RESULTS.md`](drishti3d/docs/benchmarks/2026-09-20_f4_targeted_vs_uniform/RESULTS.md).

20 distance questions, ±0.30 m, frozen and hashed before either arm ran.
Baseline: COLMAP, 80 keyframes, 81.9 s SfM. Uniform arm: the same pipeline at
`preset="quality"`, 160 keyframes, 217.3 s SfM. Targeted arm: 4-frame budget per
question against the baseline.

| Metric | no refit | + local refit | + transfer locator | **+ cost work** | Uniform |
|---|---:|---:|---:|---:|---:|
| Added compute | 210.5 s | 219.8 s | 206.7 s | **88.6 s** | 135.4 s |
| Blocked only by calibration (from 8) | 7 | 10 | 14 | **15** | 10 |
| Questions with any frame recovered | 5 | 5 | 16 | **17** | n/a |
| Measurements regressed | 1 | 0 | 0 | **0** | 5 |
| Narrower interval | 1 | 4 | 14 | **15** | 14 |
| Verdict moved up | 0 | 2 | 5 | **6** | 4 |
| Median measurement sigma | 0.151 | 0.128 | 0.101 | 0.104 | **0.092** |
| Median supporting views | 3 → 3 | 3 → 3 | 3 → 6.5 | 3 → **6.0** | 3 → 3 |
| Median measured parallax | 10.35° | 10.42° | 26.75° | **26.23°** | 10.26° |
| Blockers cleared per added minute | 0.57 | 0.55 | 2.03 | **5.42** | 3.55 |

**At the control's budget** (135.4 s) the targeted arm now reaches **all 20**
questions and clears 8 blockers — the same 8 the control clears. Break-even
moved from 13.1 questions to 30.6.

**Result: the gate is met on this test bed.** Higher answer yield (15 against
10) *and* less compute (88.6 s against 135.4 s). The feature stays experimental
because all test beds are partitions of one flight, not because of the gate.
Recorded as [DEC-013](DECISIONS.md) … [DEC-017](DECISIONS.md).

#### The same gate on two further test beds

Full write-up:
[`docs/benchmarks/2026-09-20_f4_second_capture/RESULTS.md`](drishti3d/docs/benchmarks/2026-09-20_f4_second_capture/RESULTS.md).

The one genuinely separate AGZ segment, `agz_segment_two`, **cannot run this
experiment**: at a 2.8 m median baseline `keyframes.select` keeps all 62 frames
at every preset, so the targeted arm has no candidate pool and the uniform arm
has nowhere to go. 19 of 62 frames register there, against 80 of 184 on the
dense pass. The fallback was `agz_dense_pass` split into two halves by image id
— different scene content, same flight.

Answer yield (measurements blocked only by calibration), 20 frozen questions each:

| Test bed | Baseline | **Targeted** | Uniform | Targeted regressions | Uniform regressions |
|---|---:|---:|---:|---:|---:|
| `agz_dense_pass` (full) | 8 | **15** | 10 | **0** | 5 |
| `agz_dense_firsthalf` | 7 | **13** | 5 | **0** | 7 |
| `agz_dense_secondhalf` | 9 | **15** | 9 | **0** | 4 |

| Test bed | Targeted compute | Uniform compute | Break-even | Median sigma t / u |
|---|---:|---:|---:|---|
| `agz_dense_pass` | **88.6 s** | 135.4 s | 30.6 | 0.104 / **0.092** m |
| `agz_dense_firsthalf` | 75.6 s | **57.2 s** | 15.1 | **0.126** / 0.260 m |
| `agz_dense_secondhalf` | 62.5 s | **58.2 s** | 18.6 | **0.125** / 0.132 m |

At the control's own budget the targeted arm clears 8 against 8 on the full
pass, 6 against 1 on the first half, and 6 against 5 on the second.

Supporting views went 3 → 7.0 on both halves against the control's 3 → 3;
measured parallax 8.18° → 27.58° and 9.08° → 26.74° against 4.93° and 7.48°.

**The uniform arm made measurements worse**, which did not appear on the full
pass. On the first half it took yield from 7 to 5, regressed seven measurements
(four newly `outside_established_coverage`) and raised median measurement sigma
from 0.183 m to 0.260 m. A denser reconstruction is a different cloud, not a
strictly better one.

**Result: PASS for reproducibility of direction, NOT ESTABLISHED for
generalisation.** All three test beds are partitions of one flight. Recorded as
[DEC-016](DECISIONS.md).

### Dense multi-view stereo

Full write-up:
[`docs/benchmarks/2026-09-21_dense_mvs/RESULTS.md`](drishti3d/docs/benchmarks/2026-09-21_dense_mvs/RESULTS.md).

COLMAP 4.1.0 built with CUDA, RTX 5060 Laptop. Mission `agz_dense_pass`.

| | Sparse only | **Dense (MVS)** |
|---|---:|---:|
| Points in the shipped cloud | 17,898 | **251,998** |
| Median point spacing | 0.167 m | **0.099 m** |
| `AI_ASSISTED` | 0 | **0** |
| Position error, as georeferenced | 3.764 m | 3.764 m |
| … after Sim(3) | 0.322 m | 0.318 m |
| Wall clock | 94.7 s | 1231 s |

1,386,161 points before the 0.15 m voxel downsample. Accuracy is unchanged,
which is correct: dense stereo adds detail to a model, it does not move it.

**Result: PASS**, and it closes the gap that made the clouds look broken.

#### Dense points carry observation lineage

Without it, a dense point falls back to the frustum basis and is refused
`view_geometry_unverified` — a blocking reason. On a 60-measurement sample the
dense cloud produced better intervals than the sparse one and **every
measurement was refused**. COLMAP's `fused.ply.vis` sidecar records which images
each point was fused from; the first implementation kept only the count.

All 251,785 points now carry a track: 1,331,016 observations, median 5 per
point, 99.9% reprojecting inside the image that claims them.

| 60 in-coverage distance measurements | Sparse | **Dense** |
|---|---:|---:|
| Median measurement sigma | 0.0647 m | **0.0619 m** |
| Median supporting views | 3 | **4** |
| Median measured parallax | 16.6° | **27.9°** |
| Blocked by `insufficient_views` | 12 | **1** |
| Blocked by `interval_exceeds_tolerance` | 7 | **0** |
| Blocked by `view_geometry_unverified` | 1 | **0** |
| **Blocked only by calibration** | 40 / 60 | **59 / 60** |
| `needs_refinement` | 10 | **0** |

**Result: PASS.** Recorded as [DEC-020](DECISIONS.md).

Three of my own errors surfaced getting there, each returning a plausible wrong
number without raising: a validation using PINHOLE's `fx, fy, cx, cy` as
`f, cx, cy` (reported 59%, actual 99.9%); `source_index` used as a bijection when
the Open3D fusion path makes it a nearest-point mapping (21.5%); and ENU points
projected through reconstruction-frame cameras, the cheirality test silently
discarding the rest (17%).

#### The uncertainty bug the first run caught

Dense points initially reported a **median sigma of 0.0052 m against the sparse
points' 0.0364 m** — seven times more certain than the bundle-adjusted geometry
they were triangulated from.

| | Sparse only | Dense, before | **Dense, after** |
|---|---:|---:|---:|
| p10 | 0.0123 m | 0.0035 m | 0.0371 m |
| median | 0.0364 m | 0.0052 m | **0.0379 m** |
| p90 | 0.1367 m | 0.0116 m | 0.0450 m |

Three causes, fixed in [DEC-019](DECISIONS.md): the sparse reprojection residual
used as a disparity precision (feature localisation is far tighter than window
correlation); `sqrt(n_views)` treating consecutive frames of one pass as
independent; and no floor from the sparse model's own accuracy, which is the one
that mattered.

Dense is now marginally *worse* than sparse, which is the correct ordering.
**NOT TESTED:** whether either figure is right — no reference dimensions exist,
and plausible is not correct.

#### Per-question cost, profiled rather than guessed

| Phase | Share of a refinement | Per call |
|---|---:|---:|
| `_register` | 62% | 1.05 s |
| `_locate` | 26% | 0.48 s |
| `_local_bundle` | 12% | 2.22 s |

Inside `_register`: detection 94%, matching 6%. Inside detection:

| | Per frame |
|---|---:|
| `gray()` — seek, decode, resize, undistort | **339 ms** |
| SIFT detect, 4000 features | 47 ms |
| SIFT detect, 1200 features | 38 ms |
| **Sequential decode** (no seek) | **8 ms** |

The cost was seeking in H.264, not vision. A question's top-ten candidates span
a median of 16 frames, so the span is read in one pass.

| Test bed | Before | After | Speedup |
|---|---:|---:|---:|
| `agz_dense_pass` | 206.7 s | **88.6 s** | 2.33× |
| `agz_dense_firsthalf` | 239.3 s | **75.6 s** | 3.17× |
| `agz_dense_secondhalf` | 223.9 s | **62.5 s** | 3.58× |

Quality unchanged or slightly better (yield 14 → 15 on the full pass, still zero
regressions). `MAX_REFIT_POINTS` was measured and **left at 400**: dropping it to
100 is 13% faster, one refit fewer in eight, and 4.6% worse median sigma —
[DEC-017](DECISIONS.md).

#### Endpoint location, measured on 75 candidates from 25 weak endpoints

| Locator | Endpoint located | Refit accepted |
|---|---:|---:|
| Descriptor match against a measuring frame | 1.3% | 4% |
| Descriptors chained through intermediate frames | 10.7% | 20% |
| **Transfer through dense correspondences** | **40.0%** | **36%** |

Why re-identification fails, measured: COLMAP's stored observations sit a median
**8.9 px** from a fresh OpenCV SIFT detection (212 of 1,852 within 3 px), and at
the final match the best-to-second descriptor ratio has a median of **0.93** —
no clearer than chance. Computing descriptors directly at the stored pixel was
tried and rejected: upright SIFT at an arbitrary pixel separates true
correspondences from random ones by 1.6–1.9× against roughly 4× at detected
keypoints.

**Five runs, one frozen question set.** (1) No refit, 2 regressions — one an
artefact of `refine` building evidence without provenances. (2) Provenances
fixed: regressions fell to 1. (3) With the local refit and the two corrections
it needed ([DEC-014](DECISIONS.md)). (4) With the transfer locator — reported
4,665 s, which was one question taking 74 minutes because each engine loaded its
own LightGlue model onto an 8 GB card. (5) Matcher shared at module scope: 206.7
s, the numbers above. The conclusion changed at run 4.

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

Since observation lineage landed this is the **only** remaining blocker on real
reconstructions — measured above.

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

### Observation lineage on the real reconstruction

Both engines, mission `agz_dense_pass`.

| | COLMAP (184 frames) | OpenCV (60 frames) |
|---|---:|---:|
| Observations recorded | 69,173 | 7,750 |
| Cloud points | 17,897 | 3,184 |
| Median observations per point | 3 | 2 |
| Points with no lineage | 32 (0.2%) | 0 |
| Pixel range | within 1280×720 | within 1280×720 |
| Keyframe → decoded frame map | correct (kf 1 → frame 2) | correct |

**Result: PASS.** Both engines emit lineage; it survives fusion; the two frame
numberings resolve correctly.

### How much the frustum basis was overstating

400 points sampled uniformly from the COLMAP reconstruction, comparing what
camera geometry reports against what the measurements actually provided.

| | Measured (lineage) | Frustum (upper bound) | Overstatement |
|---|---:|---:|---:|
| Supporting views, median | 3 | 11 | **3.0×** |
| Parallax, median | 20.5° | 81.1° | **3.7×** |
| Points meeting the 3-view floor | 359 / 400 | 399 / 400 | — |
| Points clearing the 2° degeneracy gate on frustum evidence but failing on measurements | — | — | 1 / 400 |

**Result: PASS**, and it is the measured justification for
[DEC-006](DECISIONS.md) and [DEC-009](DECISIONS.md). The frustum basis is a
usable ranking signal and an unusable acceptance signal.

### Same-pass refinement: measured outcomes

**Environment:** mission `agz_dense_pass`, in-repo (OpenCV) engine, 184 decoded
frames of which 80 were used by the reconstruction, leaving a 104-frame
candidate pool. 30 weak measurements (endpoints with 2+ observations and under
15° of measured parallax), 4-frame budget, 10 candidates decoded at most.

| Outcome | Result |
|---|---:|
| Recovered at least one frame | **10 / 30** |
| Cleared a blocking reason | **10 / 30** |
| Recovered nothing | 20 / 30 |
| Median wall clock per measurement | 13.7 s |

| Reasons cleared | Count |
|---|---:|
| `insufficient_views` | 9 |
| `outside_established_coverage` | 1 |

For the 10 that recovered evidence:

| | Before | After |
|---|---:|---:|
| Supporting views (median) | 2 | **4** |
| Measured parallax (median) | 8.1° | **15.5°** |
| Frames added (median / max) | — | 2 / 4 |
| Absolute change in reported value (median) | — | 0.032 m |

**Why the other 20 failed**, tallied across every candidate processed:

| Rejection during processing | Count |
|---|---:|
| `endpoint_not_located_in_image` | 243 |
| `pose_recovery_failed` | 22 |

Pose recovery succeeds 92% of the time. Locating the endpoint in the recovered
frame is the bottleneck: descriptor matching across a changed viewpoint fails,
which is the honest ceiling of the method rather than a tuning problem.

**Result: PASS** for the mechanism, **NOT TESTED** for the plan's F4 gate. That
gate asks for targeted versus uniform refinement at *equal added compute*; this
is an outcome survey of the targeted arm alone. The hypothesis is supported and
untested. The survey reproduced exactly on a second run.

#### The same survey on a COLMAP reconstruction

Repeated on `agz_dense_pass__colmap_unc` once the COLMAP path carried
uncertainty. Both columns use the corrected improvement metric of
[DEC-012](DECISIONS.md); the in-repo survey was re-run under it and is
unchanged.

| | in-repo | COLMAP |
|---|---:|---:|
| Recovered at least one frame | 10 / 30 | 11 / 30 |
| **Improved** | **10 / 30** | **6 / 30** |
| Regressed to `not_observable` | 0 | **2** |
| Supporting views (median) | 2 → 4 | 3 → 5 |
| Measured parallax (median) | 8.1° → 15.5° | 10.0° → 16.3° |
| Median wall clock | 12.9 s | 13.0 s |
| `endpoint_not_located_in_image` | 243 | 253 |
| `pose_recovery_failed` | 22 | 10 |

**Result: PASS, and it cuts against the feature.** Refinement helps *less* on
the better engine — 6 improvements against 10 — because COLMAP's longer tracks
mean fewer measurements had `insufficient_views` to clear in the first place.
Fixing the engine's uncertainty reduced the need for the feature built to work
around the gap. Both regressions came from a re-triangulated endpoint landing
outside established coverage, which the coverage gate correctly refused.

This strengthens the case for running the plan's actual F4 gate: the targeted
arm's value depends heavily on what it is compared against.

#### Worked example

A 3.01 m span whose near endpoint had 2 supporting views and 5.99° of parallax.

| | Before | After |
|---|---|---|
| Value | 3.0095 m | 2.9055 m |
| Sigma | 0.0994 m | 0.0990 m |
| Interval half-width | 0.1949 m | 0.1941 m |
| Supporting views | 2 | 5 |
| Measured parallax | 5.99° | 11.46° |
| Status | `estimated_only` | `estimated_only` |
| Dominant limitation | `insufficient_views` | `interval_not_calibrated` |

Frames 89, 90 and 91 were recovered, with 571–761 PnP inliers at 1.26–1.30 px
reprojection RMSE; the endpoint moved 0.152 m.

The interval barely moved — it is dominated by the *other* endpoint and by the
1.15% metric scale term — while the value moved 0.104 m, inside the interval.
Judging this run on interval width would have called it a failure; it cleared
the reason that was blocking the measurement.

Its refined endpoint sigma is 0.216 m, *larger* than the reconstruction's
propagated 0.037 m, because that comes from full bundle adjustment and this from
a standalone ray intersection. It is reported alongside and deliberately not
substituted into the interval.

### PnP pose recovery against the existing model

| Check | Observed |
|---|---|
| Self-PnP: recover a known camera from its own stored observations | centre to 2 mm, 544/546 inliers |
| PnP on recovered frames (3 candidates) | 75–1378 inliers, 1.0–2.3 px RMSE |
| Recovered centre vs the interpolated tentative pose | agree to 0.09–0.38 m |

**Result: PASS.** The agreement between an independently recovered pose and the
interpolated guess is a check that neither is wildly wrong.

### COLMAP per-point uncertainty (was a FAIL, now fixed)

Until 2026-09-20, `cloud.npz` from a COLMAP run carried no `sigma` or
`sigma_major`, so every endpoint snapped to an infinite sigma and returned
`not_observable` with `uncertainty_undefined`. `colmap_adapter` now runs the
same covariance pass the in-repo engine uses.

| Engine | `sigma_px` estimated | Points with covariance | `sigma_major` median | p90 |
|---|---:|---:|---:|---:|
| COLMAP | 0.486 px | 22,649 | 0.0364 m | 0.1367 m |
| In-repo (OpenCV) | — | 19,080 | 0.0370 m | — |

`sigma_px` comes from each reconstruction's own reprojection residuals via a
normalised MAD floored at 0.05 px — the same estimator on both engines, so an
engine comparison is not also a comparison of two noise models.

**Measurement outcomes**, 60 in-coverage distance measurements per engine,
±0.30 m tolerance:

| | COLMAP | in-repo |
|---|---:|---:|
| Median measurement sigma | **0.0638 m** | 0.0687 m |
| Dominant limitation `interval_not_calibrated` (only calibration left) | **51 / 60** | 10 / 60 |
| Dominant limitation `insufficient_views` | 4 / 60 | 50 / 60 |
| Dominant limitation `degenerate_view_geometry` | 1 / 60 | 0 / 60 |
| `needs_refinement` | 5 / 60 | 5 / 60 |

**Result: PASS.** COLMAP's longer mean track length (3.91 vs 2.78 observations
per point) means far more measurements clear the three-view floor: 51 of 60 have
nothing but the calibration blocker left, against 10 of 60 on the in-repo engine.
Reconstruction quality is unaffected (94.7 s wall, 3.764 m median
as-georeferenced — matching the earlier runs).

#### The unit tests that pin it — `tests/test_colmap_uncertainty.py`, 8 tests, all PASS

Run against synthetic geometry, so they do not require PyCOLMAP.

| Test | Asserts | Result |
|---|---|---|
| `test_a_well_observed_point_gets_a_finite_sigma` | Five arc cameras give every point a finite, positive, observable sigma | PASS |
| `test_sigma_major_is_the_worst_axis_not_the_best` | The reported axis is the worst-constrained one | PASS |
| `test_a_narrow_arc_is_more_uncertain_than_a_wide_one` | Five cameras at 0.02 rad are >5× more uncertain than five at 1.2 rad — parallax, not view count | PASS |
| `test_a_point_with_one_observation_is_not_observable` | In a mixed cloud, the single-observation point gets infinity while the others keep finite sigmas | PASS |
| `test_observations_are_matched_to_cameras_by_frame_index` | Cameras numbered 0,7,14,21,28 give identical uncertainty to the same geometry numbered 0..4 | PASS |
| `test_observations_of_unregistered_frames_are_dropped_not_misindexed` | A frame with no camera is skipped, not allowed to select the wrong pose | PASS |
| `test_empty_inputs_report_why_rather_than_raising_or_going_silent` | A failure returns a reason string, not a bare `None` | PASS |
| `test_sigma_px_is_estimated_from_this_reconstruction_not_assumed` | Exact projections floor at 0.05 px; 2 px of injected noise raises it >5× | PASS |

### Which blocker remains

A well-supported 3.0 m span on the COLMAP reconstruction (4 measuring views,
15.7° measured parallax, within coverage, GNSS scale at 1.15% relative):

| Tolerance | Status | Reasons |
|---|---|---|
| ±0.20 m | `estimated_only` | `interval_not_calibrated` |
| ±2.00 m | `estimated_only` | `interval_not_calibrated` |
| ±2.00 m, with a hypothetical validated profile | `meets_requirement` | none |

**Result: PASS.** `VIEW_GEOMETRY_UNVERIFIED` no longer fires. Calibration
(DEC-003) is now the sole blocker on real data, exactly as intended.

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

## 2026-09-21 — Questions asked through the app (seeded)

24 distance questions per project via `scripts/seed_questions.py`, asked over
the HTTP API so the results are the application's own, not library calls.
Endpoints sampled from each project's own cloud: at least two observations,
inside coverage, across three baseline bands. Seed 7.

| 25 answered questions | Sparse AGZ | Dense AGZ |
|---|---:|---:|
| median sigma | 0.2480 m | 0.1843 m |
| median supporting views | 3 | 4 |
| median parallax | 15.0° | 25.8° |
| `insufficient_views` | 4 | 0 |
| `view_support_basis` | triangulated_observations 25/25 | triangulated_observations 25/25 |
| `estimated_only` | 1 | 2 |
| `needs_refinement` | 24 | 23 |
| `meets_requirement` | 0 | 0 |

Every question on both projects carries `interval_not_calibrated`, so none can
reach `meets_requirement`. This is the designed refusal (DEC-002), not a test
failure.

**NOT TESTED:** whether these intervals cover the true dimensions. No
independently measured reference dimension exists for this flight, which is
exactly what `interval_not_calibrated` is reporting.

Suite: 335 passed.

## 2026-09-21 — Critical review findings: reproduction and regression

A simulated critical evaluator review
([docs/NTRO_CRITICAL_REVIEW_AND_IMPROVEMENTS_2026-09-21.md](drishti3d/docs/NTRO_CRITICAL_REVIEW_AND_IMPROVEMENTS_2026-09-21.md))
was run against `d94ec29` and reported ten P0 correctness findings, six with
executable counterexamples. **Each of the six was independently reproduced here
before any change was made**, rather than accepted on the review's word.

### Reproduced before the fix

| Check | Observed | Finding |
|---|---|---|
| 10 m line, 10% scale, zero endpoint noise; 2 vs 3 vertices | sigma 1.000 m → **0.707 m** | C02 |
| Select `[1000,0,0]`, nearest cloud point `[10,0,0]` | snapped **990 m**, no refusal, no warning | C03 |
| `export_las(..., frame=...)` then `header.parse_crs()` | **`None`**; no provenance/sigma dimensions | C08 |
| Replace `cloud.npz` after a cached `load_cloud` | returned the **previous** points | C07 |
| Reference trajectory shifted `[100,200,30]` m | `as_georeferenced` returned **0** at every statistic | C09 |
| `Intrinsics` with distortion coefficients | validated, **distortion silently dropped** | U02 |

### After the fix

| Check | Result |
|---|---|
| Subdividing a straight line (2, 3 and 5 vertices) | sigma 1.000 m, unchanged |
| Monte Carlo, 20k trials, one shared scale draw | predicted vs sampled sigma within **5%**, on straight, right-angled and wandering polylines |
| Collinear interior vertex | contributes exactly zero endpoint variance |
| Corner vertex | contributes strictly more than a collinear one |
| Selection 990 m from geometry | refused; sigma `inf`; displacement and tolerance reported |
| Ordinary grid-aligned pick | resolved, displacement < 1e-6 m, no warnings |
| LAS with a Zurich frame | `EPSG:32632`; origin round-trips within **0.05 m**; 100 m offset preserved within **0.2 m** |
| LAS/PLY fields | `provenance`, `confidence`, `sigma` present; NaN where the cloud carried none |
| `cloud.npz` replaced | new points returned; one cache entry retained per project |
| Global `[100,200,30]` m offset | `as_georeferenced` median **225.61 m**; `after_translation_fit` 0 and reports the removed vector |
| Distortion, camera model, source resolution | survive validation; unknown fields **refused**, not dropped |
| 4K calibration on 1080p video | rescaled by source resolution, substitution reported |
| Mismatched aspect ratio | flagged rather than scaled |

### Dense depth uncertainty against triangulation geometry (C04)

At 50 m range, `sigma_px = 1.0`, `focal = 1000`:

| Baseline | Parallax | sigma |
|---:|---:|---:|
| 50 m | 53.13° | 0.030 m |
| 20 m | 22.62° | 0.087 m |
| 5 m | 5.72° | 0.353 m |
| 1 m | 1.15° | 1.768 m |

Tighter baselines can no longer look more certain. Previously all four returned
the same value, because the model consulted a view *count* and never the angle.

### Absolute position error, rescored (C09)

Offline from saved artifacts, AGZ dense pass, 80 scored cameras. **No
reconstruction was re-run for this**; only the metric changed.

| | COLMAP | OpenCV | onboard GPS |
|---|---:|---:|---:|
| `as_georeferenced` median | **5.270 m** | **5.547 m** | **5.155 m** |
| `after_translation_fit` median | 3.764 m | 3.702 m | 4.595 m |
| `after_similarity_fit` median | 0.322 m | 0.679 m | — |
| removed translation | 4.111 m | 4.112 m | — |

The 3.764 m this project has been quoting as georeferenced accuracy is the
**translation-fitted** figure. The absolute figure is 5.270 m, and the
reconstruction is at the accuracy of the GPS it was georeferenced from (5.155 m),
which is the honest ceiling. The removed translation is dominated by a −3.91 m
northing component common to both engines *and* the raw GPS — a systematic
offset, not a reconstruction error.

**NOT INDEPENDENT:** the reference is Pix4D photogrammetry, not survey truth.
This was true before the change and remains true.

### Suite

**411 passed** (was 335 at `d94ec29`), 49 warnings, 113 s.
Frontend `tsc --noEmit`: clean.

New regression modules: `test_measurement_contract.py` (20),
`test_export_georeference.py` (12), `test_result_contract.py` (13),
`test_calibration_lifecycle.py` (10), `test_artifact_revision.py` (6),
`test_refinement_record.py` (6), `test_observation_kinds.py` (4).

### NOT TESTED

- Whether any reported interval covers a true dimension. No independently
  measured reference dimension exists for any capture here. This is what
  `interval_not_calibrated` reports on every question in the system.
- Dense surface accuracy and completeness against a held-out reference.
- The corrected dense uncertainty against measured error. C04 makes the model
  respond to geometry; it does not show the resulting numbers are right.
- A browser walkthrough. `tsc` passing is not a usability test.
- Clean-machine offline install, restart recovery, or concurrent-job behaviour.

## 2026-09-21 — AGZ dense rebuilt against the corrected uncertainty model

The dense reconstruction was rebuilt so the demo artifacts reflect
[DEC-025](DECISIONS.md) (depth uncertainty from measured triangulation angle)
and [DEC-029](DECISIONS.md) (observation rows labelled by kind). 1,271 s wall,
252,127 points, 1,388,164 dense points before fusion, no error.

### What the corrected model changed

Per-point `sigma_major`, same flight, same settings:

| | median | p10 | p90 | p99 |
|---|---:|---:|---:|---:|
| previous (pre-C04) | 0.0363 m | 0.0355 m | 0.0437 m | 0.0832 m |
| rebuilt (C04) | 0.0385 m | 0.0345 m | **0.0909 m** | **0.3255 m** |

**The median barely moves; the tail widens 2–4×.** That is the correction
behaving as it should. Well-observed points are dominated by the sparse-model
floor either way, so their figures are almost unchanged. The points that change
are the ones whose contributing views are nearly collinear — which the previous
model could not distinguish at all, because it consulted a view count and never
the angle.

### Observation lineage, now labelled

1,332,620 rows: **20,143** `sparse_feature_observation` and **1,312,477**
`dense_fusion_contributor`. The evidence API and the Tolerance Lens report the
split per endpoint, and a sampled endpoint shows 3 views all of which are dense
contributors — support that establishes the images contributed, with pixels
projected rather than measured there.

### Questions re-answered on the rebuilt geometry

All 27 stored questions flagged `superseded` on the artifact change and were
re-asked. Sparse is unchanged and shown for comparison.

| 27 / 25 answered | Sparse | Dense (rebuilt) |
|---|---:|---:|
| median sigma | 0.2480 m | 0.2009 m |
| median interval half-width | 0.4860 m | 0.4008 m |
| median supporting views | 3 | **4** |
| median parallax | 15.0° | **31.1°** |
| `view_support_basis` | triangulated 25/25 | triangulated 27/27 |
| `insufficient_views` | 4 | **0** |
| `not_observable` | 0 | **3** |

**The dense advantage survives the correction.** Sigma widened from 0.1843 m to
0.2009 m against the pre-C04 artifacts, and is still narrower than sparse.

**Three questions became `not_observable`**, all `outside_established_coverage`.
This is **not** caused by the fixes. COLMAP's incremental mapping is not
deterministic, and the rebuilt coverage volume is (145, 217, 77) voxels against
(143, 217, 76) before — three endpoints that sat near the boundary fell outside
it in this run. The system refuses them rather than extrapolating, which is the
intended behaviour, but it does mean **question outcomes near a coverage edge
are not reproducible across rebuilds of the same flight.** That is a property of
the pipeline worth knowing before any result is quoted.

### NOT TESTED

Whether the widened intervals are *correct*. C04 makes uncertainty respond to
geometry; only measured reference dimensions can show the resulting numbers are
right. Every question here still reports `interval_not_calibrated`.

Suite: **422 passed**.

## 2026-09-21 — Follow-up verification of the DEC-021…030 fixes

`docs/CRITICAL_REVIEW_VERIFICATION_2026-09-21.md` ran fifteen independent checks
against `61939db`. **Nine failed.** All nine were reproduced here before any
change; all nine held.

| ID | Check | Before | After |
|---|---|---|---|
| F01 | `refine()` through its successful-recovery branch | `NameError: 'rec' is not defined` | passes |
| F02 | video-only artifact export completes | `AttributeError: 'NoneType'` | passes |
| F03 | both routes report non-metric units without scale | `/questions` returned `m` | both return `reconstruction units` |
| F04 | tolerance change after a refinement | HTTP 500 | HTTP 200 |
| F05 | invalid PATCH level rejected without persisting | 500, level stored as 97 | 400, level unchanged |
| F06 | `cloud.npz` replaced → stored answer superseded | `superseded=False` | `superseded=True` |
| F07 | one-point cloud refuses a remote snap | accepted a 1,000 m move | refused |
| F08 | sigma positive at an obtuse view angle | **negative** | positive |
| F08 | near-parallel geometry not finitely constrained | finite 4.0513 | `inf` |

**15 / 15 audit checks pass.** Suite: **431 passed** (was 422). Production
frontend build (`npm run build`): passes.

### Dense uncertainty across the angular domain

`sigma_px = 1.0`, `focal = 1536`, range 20 m, 2 views:

| Parallax | `1/tan` (DEC-025) | `1/sin` (DEC-031) |
|---:|---:|---:|
| 0.0° | 4.0513 (clamped) | **inf** |
| 5° | 0.40411 | 0.40566 |
| 26° | 0.07249 | 0.08065 |
| 45° | 0.03536 | 0.05000 |
| 90° | **0.00000** | 0.03536 |
| 120° | **−0.02041** | 0.04082 |
| 170° | **−0.20051** | 0.20360 |

Checked over 400 angles in [0.5°, 179.5°]: strictly positive, finite,
minimised at 90°, and exactly symmetric about it — `s(60°) == s(120°)` and
`s(30°) == s(150°)` to 1e-9. Agreement with the previous form at 5° is within
0.4%, so the narrow-angle regime that dominates a drone pass is unchanged.

### NOT TESTED

- Whether any interval covers a true dimension. Unchanged and still the
  binding limitation.
- Complete browser walkthrough. `tsc` and `npm run build` pass; neither is a
  usability test.
- The rebuilt artifacts under the `1/sin` model, at the time of writing. The
  figures above are from the function, not from a mission.

## 2026-09-21 — AGZ dense rebuilt under the `eps/sin` model and re-imported

Second rebuild of the same flight, so the demo artifacts match
[DEC-031](DECISIONS.md). 1,701 s wall, 1,385,668 dense points before fusion,
**251,504** after, no error.

### Per-point uncertainty across the three models

| `sigma_major` | median | p90 | p99 | negative | unconstrained |
|---|---:|---:|---:|---:|---:|
| no angle (DEC-019) | 0.0363 m | 0.0437 m | 0.0832 m | 0 | 0 |
| `1/tan` (DEC-025) | 0.0385 m | 0.0909 m | 0.3255 m | 0 | 0 |
| **`eps/sin` (DEC-031)** | **0.0409 m** | **0.0937 m** | **0.3288 m** | **0** | **0** |

The `1/tan` → `eps/sin` change moves this mission very little, which is the
expected result and worth stating plainly: AGZ's dense parallax is
narrow-angle dominated, and the two forms agree to 0.4% at 5° and about 10% at
26°. The correction matters for *correctness over the domain*, not for these
numbers.

**No dense point in this mission falls below `MIN_PARALLAX_DEG`**, so the new
`inf` path costs no coverage here. That is a property of this capture, not a
general guarantee — a slower or more nadir pass would produce unconstrained
points, and they would now be refused rather than measured.

### Lineage

1,330,150 rows: **20,019** `sparse_feature_observation`, **1,310,131**
`dense_fusion_contributor`. Verified live through the evidence API: a sampled
question reports 5 and 3 views per endpoint, all dense contributors,
`kinds_recorded: true`.

### Georeference sidecar

`projected_crs EPSG:32632`, `georeferenced true`, `units metres`,
`scale_source gps`, vertical reference stated as WGS84 ellipsoidal. Exports
available through the API: geojson, **georeference**, las, mesh_glb, ply,
report_html, report_json, trajectory_csv, viewer.

### Scoring (unchanged by the uncertainty model, as it must be)

`as_georeferenced` 5.269 m · `after_translation_fit` 3.763 m ·
`after_similarity_fit` 0.322 m.

### Questions re-answered

All 27 dense and all 25 sparse questions flagged `superseded` and were re-asked.
Sparse was flagged because `artifact_version` gained its revision component
([DEC-033](DECISIONS.md)) — a one-time effect of the format change, not a
geometry change.

| answered | Sparse | Dense (`eps/sin`) |
|---|---:|---:|
| median sigma | 0.2480 m | **0.1983 m** |
| median interval half-width | 0.4860 m | **0.3856 m** |
| median supporting views | 3 | **4** |
| median parallax | 15.0° | **25.2°** |
| `view_support_basis` | triangulated 25/25 | triangulated 27/27 |
| `insufficient_views` | 4 | **0** |
| `not_observable` | 0 | 1 |

**One question is `not_observable` this time, against three after the previous
rebuild** — both `outside_established_coverage`, both from coverage-volume
variation between non-deterministic COLMAP runs. This is the second observation
of that effect and confirms it: **outcomes for endpoints near a coverage
boundary are not stable across rebuilds of the same flight.**

### NOT TESTED

Whether any of these intervals covers a true dimension. All 52 questions across
both projects still report `interval_not_calibrated`.

## 2026-09-22 — UseGeo dataset 1 scored against LiDAR (first independent check)

**The first accuracy measurement in this project against an instrument that is
not photogrammetry.** RIEGL miniVUX-3UAV reference, 105.9 M points; 60-frame
contiguous subset of UseGeo dataset 1; COLMAP + dense MVS.

### Reconstruction

| | |
|---|---:|
| Frames registered | 60 / 60 |
| Dense points (pre-fusion / cloud) | 2,740,959 / 2,138,943 |
| Median point spacing | 0.129 m |
| Median reprojection error | 0.271 px |
| Points with finite sigma | 2,138,943 (100%) |
| Reported sigma p10 / median / p90 | 0.076 / 0.093 / 0.174 m |

### Accuracy against the LiDAR

| | |
|---|---:|
| Raw point-to-surface error, median | **1.360 m** (p90 1.640) |
| Systematic offset: East / North | −0.004 m / −0.005 m |
| Systematic offset: **Up** | **+1.245 m** |
| After removing that offset, median | **0.299 m** (p90 0.466, p99 0.664) |
| Unmatched (>5 m from any return) | 0.02% |

By LiDAR classification — the bias is the same on both, so it is **not** a
photogrammetry-above-canopy effect:

| Reference class | points | vertical offset | debiased median |
|---|---:|---:|---:|
| unclassified / hard surface | 78.3 M | +1.267 m | 0.291 m |
| medium vegetation | 7.3 M | +1.166 m | 0.308 m |

### Camera positions against the authors' adjusted poses

| axis | median | std |
|---|---:|---:|
| East | −0.109 m | 0.324 |
| North | −0.070 m | 0.380 |
| Up | +0.268 m | 0.055 |
| **3D median** | **0.532 m** | |

Cameras are placed well. The ground 80 m below them is not — the surface bias
is over four times the camera bias, so this is not a camera-placement error.

### Interval check — the number this dataset was downloaded for

| | |
|---|---:|
| Median predicted sigma | 0.093 m |
| Median actual error (raw) | 1.360 m → **14.7× too optimistic** |
| Median actual error (debiased) | 0.299 m → **3.2× too optimistic** |
| **Coverage at 1.96 sigma** | **4.6%** (nominal 95%) |

### Completeness

Reference points inside the reconstruction's own horizontal convex hull, after
removing the bias (114,891 points):

| within | |
|---|---:|
| 0.10 m | 1.4% |
| 0.25 m | 13.3% |
| 0.50 m | 66.0% |
| 1.00 m | 87.7% |
| median | 0.420 m |

### Cause

The run's own manifest recorded it before anyone looked:
`degenerate: true`, `degeneracy: "planar trajectory (out-of-plane geometry is
weakly constrained)"`, `alignment_rmse_vertical_m: 0.057`.

A constant-altitude nadir survey. The Sim(3) fit places cameras in a plane onto
a plane with 5.7 cm vertical RMSE and constrains the ground beneath them barely
at all. **The degeneracy reaches the manifest and nothing downstream reads it**
— no uncertainty widens, no measurement is refused. See
[DEC-036](DECISIONS.md).

### NOT TESTED

- Whether the bias persists on a non-planar flight. AGZ varies 449–474 m in
  altitude and shows nothing like it, which is consistent with the diagnosis
  but is not a controlled test.
- Dimensional accuracy. This is point-to-surface distance, not a measured
  length between identified features, so it constrains the uncertainty model
  but is not yet a calibration.
- Datasets 2 and 3 of UseGeo, which would make it three independent sites.

## 2026-09-22 — Dimensional accuracy against LiDAR (UseGeo 1) — **WITHDRAWN**

> **These figures are withdrawn. The method could not measure what it claimed.**
> Endpoints were matched to their nearest LiDAR point, so with a dense
> reference the "reference distance" is the reconstruction's own distance
> echoed back. A 5% scale error scores as 1.5e-13 m under it. The flatness
> across 1-400 m baselines was the nearest-neighbour snap residual, not
> accuracy. See [DEC-037](DECISIONS.md). Retained below only so the withdrawal
> is auditable; **do not quote any number in this section.**

Point-to-surface distance is not what a measurement is. A measurement is a
*distance between two points*, and a common offset cancels in one. The +1.245 m
vertical bias found above therefore says almost nothing about how accurate a
measured length is, so it was measured directly.

Method: our points matched to their nearest LiDAR return after removing the
known bias; pairs drawn at a range of separations; our distance compared with
the reference distance between the same pair. `correspondence` is how close a
point must be to a LiDAR return to be used, which brackets the selection bias —
the bottom row selects nothing.

| correspondence | points kept | dim. error median | p90 | predicted sigma | actual/predicted |
|---|---:|---:|---:|---:|---:|
| < 0.08 m | 6.4% | 0.031 m | 0.073 | 0.143 m | 0.22× |
| < 0.15 m | 17.0% | 0.049 m | 0.115 | 0.140 m | 0.35× |
| < 0.30 m | 50.3% | 0.071 m | 0.190 | 0.135 m | 0.53× |
| < 0.60 m | 98.2% | 0.086 m | 0.248 | 0.134 m | 0.64× |
| **< 5.0 m (all points)** | **100%** | **0.088 m** | **0.261 m** | **0.135 m** | **0.65×** |

Baselines 5–60 m. **On every point, with no selection at all: 0.088 m median
dimensional error, 0.261 m at p90.**

### Error does not grow with baseline

Best-corresponding points, absolute error by separation:

| baseline | median error | p90 | relative |
|---|---:|---:|---:|
| 1–3 m | 0.031 m | 0.070 | 1.47% |
| 3–10 m | 0.030 m | 0.072 | 0.45% |
| 10–30 m | 0.031 m | 0.071 | 0.15% |
| 30–80 m | 0.030 m | 0.072 | 0.05% |
| 80–200 m | 0.031 m | 0.073 | 0.02% |
| 200–400 m | 0.031 m | 0.071 | 0.01% |

Flat from 1 m to 400 m. That is the signature of endpoint noise with **no
detectable scale error** — a scale error would make absolute error grow
linearly with baseline, and over 400 m even 0.1% would be 0.4 m.

### The two results point opposite ways, and both are true

| | reported | actual | |
|---|---:|---:|---|
| Absolute vertical placement | 0.093 m sigma | 1.245 m bias | **13× optimistic** |
| Dimensional measurement | 0.135 m sigma | 0.088 m error | **1.5× conservative** |

A common translation cancels in a distance, so the same reconstruction is badly
placed and accurately shaped at the same time. Quoting either number alone
misrepresents the system.

### NOT TESTED

- Dimensional accuracy on a non-degenerate capture. AGZ has no independent
  reference, so this figure exists for one flight only.
- Whether the 1.5× conservatism holds anywhere else. One capture is not a
  calibration, and `interval_not_calibrated` is still the correct refusal.
- Correspondence is nearest-LiDAR-return, not a surveyed target. At 0.031 m the
  measurement is approaching the reference's own ~0.07 m sample spacing, so the
  best rows are near the floor of what this method can resolve.

## 2026-09-22 — Dimensional accuracy, third attempt, this one validated

Two methods were built and both failed. The rule they establish: **a
correspondence located using the output under test cannot measure that output.**

### Method 1 — nearest LiDAR point (withdrawn, [DEC-037](DECISIONS.md))

Blind to a 5% scale error by construction against a dense reference.

### Method 2 — planar patches fitted independently in each cloud (failed)

Intended to remove the leakage. It did not: the reference patch is located at
*our* patch's horizontal position, so our error moves both sides. Validated by
injection and it failed:

| injected error | pairs | median abs error | implied scale |
|---|---:|---:|---:|
| none (baseline) | 1,703 | 0.0448 m | −0.04% |
| **+5% uniform scale** | 1,057 | **0.0428 m** | **+0.02%** |
| +1% uniform scale | 1,546 | 0.0445 m | −0.01% |
| +5% vertical only | 1,626 | 0.0458 m | −0.01% |
| +2 m vertical shift | 1,703 | 0.0448 m | −0.04% |

A 5% scale error scores *better* than no error. `scripts/score_dimensions.py`
is retained with a do-not-use banner so the failure stays auditable.

### Method 3 — camera centres paired by image filename (passes)

A filename carries no geometry from the output, so the correspondence cannot
absorb the error. **`scripts/score_camera_dimensions.py` re-runs the injection
test on every invocation** rather than claiming validation once:

| injected | detected | median abs error |
|---|---:|---:|
| +1.0% | **+0.967%** | 1.248 m |
| +5.0% | **+4.966%** | 5.827 m |

Result on `usegeo_1__first`, 60 cameras, 1,770 pairs, baselines 1.4–363.9 m:

| | |
|---|---:|
| Signed median | **−0.027 m** (no length bias) |
| Median absolute | **0.359 m** |
| p90 absolute | 0.962 m |
| RMSE | 0.598 m |
| **Implied scale error** | **−0.033%** |

| baseline | n | median abs | relative |
|---|---:|---:|---:|
| 0–25 m | 98 | 0.046 m | 0.333% |
| 25–75 m | 471 | 0.307 m | 0.732% |
| 75–200 m | 787 | 0.548 m | 0.406% |
| 200–400 m | 414 | 0.420 m | 0.168% |

**Scale is sound** — −0.033% over baselines to 364 m. The error is relative
geometry within the camera network, not a scale or datum problem.

**What this is not.** It measures the camera network, not scene features. The
reference is the dataset authors' bundle adjustment, not survey, and on UseGeo
that adjustment is partly derived from the same GNSS/INS trajectory used as our
telemetry — so absolute agreement is not independent. Pairwise distances are
much less affected by that sharing, which is why they are reported and the
absolute figure is qualified.

### Where the vertical bias enters

Measured per stage against the LiDAR, which needs no correspondence identity:

| stage | vertical bias |
|---|---:|
| camera centres | +0.268 m |
| sparse SfM-triangulated points | **+0.605 m** |
| dense MVS points | **+1.250 m** |

Dense stereo roughly doubles the bias the sparse stage already carries. That
makes MVS a concrete target rather than an unexplained constant, and it rules
out scale (−0.033%) and datum as the cause.

### NOT TESTED

- Dimensional accuracy on **scene features**. No method here achieves it on
  this dataset: the reference is a surface, not identified points, and every
  position-based correspondence leaks. Surveyed landmarks are required.
- Whether the reference bundle adjustment is accurate in absolute terms. It is
  a different estimator over shared inputs, not ground truth.
