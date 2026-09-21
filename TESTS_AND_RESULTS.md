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
