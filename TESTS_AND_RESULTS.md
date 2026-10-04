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

## 2026-09-22 — Honouring the supplied calibration: error cut 4×

`colmap_adapter.reconstruct_frames` accepted a camera matrix and never passed
it to COLMAP, which self-calibrated instead ([DEC-038](DECISIONS.md)). Same
mission, same settings, same 1600 px processing width; the only change is that
the calibration is now fixed rather than discarded.

| metric | self-calibrated | **calibration fixed** | improvement |
|---|---:|---:|---:|
| Surface RMSE vs LiDAR | 1.283 m | **0.324 m** | 4.0× |
| Surface median | 1.360 m | **0.284 m** | 4.8× |
| Surface p90 | 1.640 m | **0.441 m** | 3.7× |
| Vertical bias | +1.245 m | **+0.243 m** | 5.1× |
| Sparse SfM point bias | +0.605 m | **+0.021 m** | 29× |
| Dense MVS point bias | +1.261 m | **+0.244 m** | 5.2× |
| Camera-pair distance, median abs | 0.359 m | **0.042 m** | 8.5× |
| Camera-pair distance, RMSE | 0.598 m | **0.068 m** | 8.8× |
| Implied scale error | −0.033% | +0.040% | — |
| Camera absolute position, 3D median | 0.532 m | **0.288 m** | 1.8× |
| Interval coverage @ 1.96σ | 4.6% | **29.9%** | 6.5× |
| Completeness within 0.5 m | 4.2% | **67.9%** | 16× |
| Points | 2,138,943 | 2,098,913 | — |

Camera matrix actually used, against the calibration file: focal deviation
**+0.0000%**, principal point exact. Previously −1.45%, with the principal
point reset to the image centre.

Dimensional figures from `scripts/score_camera_dimensions.py`, which re-runs
its injection validation on every invocation: **+1% recovered as +1.04%, +5% as
+5.04%**.

### The high-resolution experiment that located it

Tried first, on the theory that 1600 px from 7952 px discarded detail. It made
things worse, and that is what exposed the cause:

| stage | 1600 px | 3200 px |
|---|---:|---:|
| camera centres | +0.268 m | +0.270 m |
| sparse SfM points | +0.605 m | **+1.139 m** |
| dense MVS points | +1.261 m | +1.467 m |

Cameras unmoved, triangulation twice as wrong — a free focal drifting further
at higher resolution, with depth following it.

### Against the organiser's target

**0.324 m RMSE** on this capture, against a stated **≤ 1 m**. The organiser has
not defined whether the statistic is RMSE, a percentile or a maximum, so this
is reported as surface distance to an independent LiDAR reference and not
claimed as certified compliance. p90 is 0.441 m and the maximum matched error
is bounded by the 5 m cutoff.

### NOT TESTED

- Any capture without a calibration file. Self-calibration on planar nadir
  geometry will drift the same way; nothing yet detects or refuses that.
- Whether 0.324 m holds on a second site. One flight, one camera.
- Interval coverage remains 29.9% against a nominal 95%. The uncertainty model
  is now wrong by less, not calibrated.

## 2026-09-22 — First benchmark on native 10-minute drone video (DJI_1003)

**The first capture here meeting the organiser's stated input**: 11 min 18 s of
native 1080p60 DJI video, 40,633 frames, with 40,630 per-frame SRT telemetry
samples. Austin TX, Aug 2025. Every study before this used video assembled from
stills.

### Quality — the best result yet on video

| | |
|---|---:|
| Registered | **80 / 80 (100%)** |
| COLMAP restarts | 1 |
| Cloud points | **2,694,027** |
| Sparse points | 84,617 |
| Median reprojection error | **0.303 px** |
| Scale source | **gps** (georeferenced) |
| Alignment RMSE, 3D | 2.833 m |
| Point spacing | 0.379 m |

First 100% registration on real video footage — St Lambertus was 36%, then 67%
after the matcher fix. Achieved **without any camera calibration**, on the
pipeline that now refines rather than freezes an estimated focal.

### Speed — over budget

**1,951.8 s for 677.9 s of video = 2.88×.** The requirement is 15 min for
10 min, i.e. **1.50×**. Nearly 2× over.

| stage | time | % |
|---|---:|---:|
| **densify** | **1585.3 s** | **81.2%** |
| sfm | 253.6 s | 13.0% |
| frames | 60.7 s | 3.1% |
| quality | 23.6 s | 1.2% |
| fusion | 15.9 s | 0.8% |
| all others | 12.5 s | 0.6% |

Reaching 1.50× needs a total near 1,017 s, so densification must fall from
1,585 s to about 650 s — **2.4× faster**. Nothing else is worth touching:
eliminating SfM entirely still leaves 2.5×.

Measured resource use during an equivalent run: the GPU-bound densify phase
runs at **81% GPU / 7.6% CPU**, and the CPU-bound SfM phase at **85% CPU /
1.0% GPU**, on 24 cores. The two heaviest stages use opposite resources and
never overlap.

### What this run cannot claim

`alignment.degenerate` is **true**: altitude varies **5.1 m over a
1,025 × 1,378 m** flight. That is the near-planar geometry that cost UseGeo
1.245 m before [DEC-038](DECISIONS.md), and this footage has no calibration at
all. The measurement gate refuses on it, correctly
([DEC-039](DECISIONS.md)). No independent reference exists for this site, so
**no accuracy figure is claimed** — only that the reconstruction is dense,
complete and georeferenced.

### NOT TESTED

- Accuracy. There is no reference for this site; alignment RMSE measures
  consistency with consumer GPS, not accuracy.
- Whether 2.88× is representative. A second 11-minute capture (DJI_1001) is
  running to establish that.


## 2026-09-23 — DJI_1001 benchmark, and the hole fill

### DJI_1001 (second native 11-minute flight)
80/80 registered, 3.27 M points, **2.83×** processing ratio (densify 1,593.7 s,
82.1%). This matches DJI_1003's 2.88×, so the 2.88× figure is representative
of this hardware. Altitude range is 1.1 m and alignment is degenerate, so as
for DJI_1003 **no accuracy is claimed**.

### Hole fill (DEC-040)
| | DJI_1003 | DJI_1001 |
|---|---:|---:|
| surveyed (≥ 2 footprints) | 141.4 ha | 129.2 ha |
| filled | 44.2 ha (31%) | 26.0 ha (20%) |
| holes | 3,375 | 4,892 |
| fill points | 399,720 | 364,304 |
| time | 22.8 s | 26.4 s |

Colour sampling checked by projecting observed points into keyframe 40 of
DJI_1003: r = 0.944 / 0.936 / 0.930 per channel against the cloud's own colours.
Viewed in Chrome: the river renders as a surface; in provenance mode it is the
blue class; the unsurveyed central square stays empty.

Unit tests (`tests/test_holefill.py`): level river at bank height (±0.3 m);
60 m roofs along the bank do not lift the water (< 4 m); unseen ground not
filled; no hole, no fill; colour taken from the pixel under the point;
class not measurable; API appends fill as class 6 and omits it with
`fill=false`; a synthetic end-to-end pipeline run writes `fill.npz`/`fill.json`
without a warning and leaves no class-6 point in `cloud.npz`. Full suite 479
passed.

### NOT TESTED
- Fill **height accuracy** on real water. There is no water-level reference for
  either site, and on DJI_1003 the fill inherits the ~50 m bowing the
  degenerate alignment allows.
- The fill inside a full pipeline run on **real** footage. On the DJI projects
  it was run afterwards with `scripts/fill_holes.py`; stage 14b has only been
  exercised end to end on the synthetic scene.
- Moving water (rivers with slope, surf). The fill assumes the membrane
  between banks is the right shape.


## 2026-09-23 — Performance: dense ladder and end-to-end timing (DEC-041)

### UseGeo dense ladder (LiDAR-scored, fixed sparse model, one run each)
B0 1212.7 s / RMSE 0.3238 / p95 0.4865 / complete 68.0%;
D1 12 src 1093.8 / 0.3179 / 0.4762 / 69.3%; D2 10 src 1028.6 / 0.3110 / 0.4664 / 70.6%;
D3 step 2 610.1 / 0.3265 / 0.4817 / 65.5%; D4 3 iter 742.4 / 0.3239 / 0.4831 / 67.1%;
D5 1280 px 911.3 / 0.3472 / 0.5306 / 63.2% (fail); G2 two workers 1371.6 s (slower, not scored);
C1 (D2+D3+D4) 314.6 / 0.3137 / 0.4570 / 67.3%; **C1m4 (C1, fuse at 4) 315.7 / 0.3160 / 0.4613 / 70.0%**.
The harness reproduces the archived full run (RMSE 0.3238 vs 0.3237).

### DJI_1003 fresh end-to-end run with the new defaults
**733.7 s wall (1.08x the 677.9 s video).** decode 39.8, SfM 177.4 (features 19.3,
matching 73.1, mapping 69.2), dense 409.4 (PatchMatch 381.4, fusion 18.6),
exports 49.5 (observations 13.2, files 18.2, hole fill 17.9). 80/80 registered,
reprojection 0.303 px, 3,124,856 points. Against the old cloud: 95.6% of 10 m
and 92.0% of 2 m cells kept; 97.7% of points within 1 m of an old point.
Peak RSS during a run: 10.5 GB.

### SfM (DJI_1003 keyframes, `scripts/sfm_trial.py`)
4 threads 242.9 s; 12 threads 181.7 s, same 80/80 and focal (1615.4 / 1615.2 px);
12 threads + GPU matching 154.0 s, focal 1614.4 px, +1.8% points (not adopted).

### Equivalence checks
Visibility reader, CSR translation and parallax equal the old code on 2.63 M
DJI points (parallax 8.7e-13 deg max). Dense observations are identical on
150 k rows. `grab()` decode gives bit-identical kept frames and timestamps.
Threaded frame quality gives identical metrics. Binary PLY round-trips exactly
through Open3D. `tests/test_dense_perf.py` pins these against per-point
references. 487 passed.

### NOT TESTED
- Accuracy of the new defaults on any second reference scene; only UseGeo has LiDAR.
- Run-to-run spread: one end-to-end run, not three.
- DJI_1001 with the new defaults. (Done later the same day: see below.)
- Interval coverage of the new dense uncertainty on the LiDAR.
- Any GPU other than this RTX 5060 laptop.


## 2026-09-23 — DJI_1001 with the DEC-041 defaults

Fresh end-to-end run, same parameters as the original DJI_1001 run apart from
the new dense defaults.

| | before | after |
|---|---:|---:|
| complete job | > 1,939.9 s (exports untimed) | **765.6 s (12.8 min, 1.12x the 685.3 s video)** |
| decode | 54.6 s | 40.3 s |
| frame quality | 16.1 s | 0.1 s |
| SfM | 251.1 s | 188.5 s |
| dense | 1,593.7 s | 413.4 s (PatchMatch 384.1) |
| exports incl. hole fill | untimed | 61.9 s |
| cameras / reprojection | 80/80, 0.3387 px | 80/80, 0.3387 px |
| cloud | 3.27 M | 3.92 M |

Against the old cloud: camera centres agree to a median 0.03 m; 96.0% of 10 m
and 92.3% of 2 m cells kept; 98.5% of new points within 1 m of an old point.
The same pattern as DJI_1003 (95.6% / 92.0% / 97.7%). No independent
reference exists for this site, so this is consistency, not accuracy.


## 2026-09-25 — First same-flight accuracy on native video: MARS-LVIG HKisland03 (DEC-042)

The first reference captured **in the same flight as the imagery**. MARS-LVIG
(HKU, IJRR 2024) flies a DJI M300 RTK with a 2448x2048 global-shutter camera at
10 Hz and, on the gimbal, a DJI Zenmuse L1 LiDAR recording simultaneously
(stated 10 cm H / 5 cm V after DJI Terra). RTK fixed for 100% of samples.
HKisland03: bag starts 2022-11-29 14:16:07 HKT, 380 s, 3,800 frames; the L1
recorded 14:17:44.3–14:21:05.3 (201 s, 14.56 M points, UTM 50N).
Scored with `score_against_lidar.py --epsg 32650 --sample 0` (every point).

### Results

| run | median | RMSE | p90 | p95 | p99 | wall / video |
|---|---:|---:|---:|---:|---:|---:|
| A. whole video, 200 frames analysed, 79 keyframes | 0.401 | **0.720** | 1.092 | 1.398 | 2.253 | 651.7 s / 380 s = 1.7x |
| A'. same run's raw `fused.ply`, RTK time offset re-estimated (-0.50 s) | 0.321 | **0.615** | 0.902 | — | 1.961 | — |
| B. LiDAR window only, 200 frames, 80 keyframes, fusion cache fix | 0.370 | **0.753** | 1.045 | 1.449 | 2.970 | 745.7 s / 201.1 s = 3.7x |
| B'. same run's raw `fused.ply`, same scorer as A' (offset -0.54 s) | 0.360 | 0.741 | 1.022 | — | 2.941 | — |
| C. full resolution (2448 px, 160 keyframes) | — | — | — | — | — | not completed; see below |

Common settings for A and B: COLMAP engine, `balanced`, `--proc-width 1600
--mvs-max-image-size 1300 --sfm-threads 6 --mvs-cache-gb 1 --max-frames 200`,
published chessboard calibration, run through `scripts/run_capped.sh`.

Run A detail: 79/79 registered, reprojection 0.284 px, 1,530,569 points,
1.37% of points > 5 m from any LiDAR return (excluded). Systematic offset
E +0.001 / N -0.013 / U -0.008 m: **georeferencing by RTK is essentially
exact**; the error is surface noise, not bias. Completeness within 0.25 m
23.1%, within 0.5 m 45.8%. Interval coverage at 1.96 sigma 20.7%; actual error
is 5.05x the predicted sigma.

Run A error by terrain (distance to LiDAR, every point):

| subset | share | median | RMSE | p90 |
|---|---:|---:|---:|---:|
| local LiDAR roughness < 0.1 m (smooth) | 77.0% | 0.35 | 0.63 | 0.95 |
| roughness 0.1–0.3 m | 19.9% | 0.54 | 0.87 | 1.31 |
| roughness 0.3–1 m | 3.0% | 0.96 | 1.39 | 2.10 |
| roughness > 1 m | 0.1% | 1.56 | 2.09 | 3.34 |
| height < 1 m (shoreline, surf) | 17.1% | 0.50 | 0.97 | 1.35 |
| height 30–60 m | 6.3% | 0.24 | 0.51 | 0.93 |
| predicted sigma, lowest quartile | 25% | 0.25 | 0.43 | 0.67 |
| predicted sigma, 3rd quartile | 25% | 0.51 | 0.80 | 1.26 |

The uncertainty model ranks points correctly but is about 5x optimistic.

### Camera-RTK time offset (RTK arrives late)

Umeyama sim3 of run A's COLMAP camera centres onto RTK, as a function of the
shift applied to keyframe times (`frame_index / fps`):

| shift | 0 s | -0.3 s | -0.5 s | **-0.6 s** | -0.7 s | -1.0 s |
|---|---:|---:|---:|---:|---:|---:|
| alignment RMSE | 4.384 m | 2.361 m | 1.135 m | **0.772 m** | 0.931 m | 2.731 m |

Ground speed is 8.94 m/s, so ~0.6 s of RTK message latency is ~5.4 m along
track. The pipeline's speed-profile estimator found only -0.212 s
(confidence 0.38) on run A — a constant-speed survey has a nearly flat speed
profile — and reported a 2.28 m alignment RMSE. On run B it found -0.586 s
(confidence 0.35) and reported 1.33 m. A' vs A suggests correct timing is
worth ~0.1 m RMSE on this flight. **Not yet fixed in the pipeline.**
`keyframes.json` also appears to time frames one frame early
(frame 152 -> 15.112 s = 151 / 9.992); the position-based offset absorbs it.

### Full resolution (run C) could not complete on this laptop

`quality` preset, 671 frames analysed at 2448 px, 160 keyframes, dense at
2448 px, 9 GB cap. SfM needed `--sfm-threads 3` (6 threads OOM'd in SIFT).
PatchMatch finished all 160 photometric + geometric depth maps in ~33 min
(25 GB, kept in `data/runs/mars_hkisland03_win__full`). Fusion then failed
both ways: without `use_cache` it needs ~16 GB; with it COLMAP fuses on one
thread and slowed from 58 s (image 22) to 840 s (image 23) to > 60 min
(image 24). Abandoned. Wall/video would have been > 30x in any case.

### Processing time

Stages, run B: decode 11.2 s, SfM 170.8 s, dense 510.9 s, exports 22.7 s.
Time is set by the keyframe cap (80), not by clip length: run A (380 s of
video) took 651.7 s and run B (201 s) 745.7 s. On a 10-minute video the same
budget would be ~1.1–1.2x, like DJI_1003 (1.08x); on a 3.4-minute clip it is
3.7x.

### Scorer and memory-change checks

- `scripts/score_colmap_fused.py` recovers keyframe times by pixel matching;
  on run A it matched all 79 keyframes (best/second error ratio >= 79.7) and
  gave the same score as reading `keyframes.json`.
- Disk-backed frame store + in-place undistortion: pixels and undistorted K
  byte-identical to the old path (40 real frames); `frame_metrics.json` and
  `keyframes.json` identical old vs new on a 60-frame run. SfM differed
  (51 vs 50 registered) but two new-code runs also differ from each other
  (reprojection 0.2383091 vs 0.2383291): COLMAP run-to-run variation.
  487 tests pass. Decoding 671 full-resolution frames now uses 580 MB of
  anonymous memory instead of ~10 GB.

### Other runs this session
- HKisland_GNSS03 (2023-10-24, a different flight over the same route):
  79/79, 0.282 px, 1.41 M points, 645.8 s. **Not scored** — its own L1 is in
  `GNSS.7z` (46 GB); the HKisland L1 is 11 months older.
- Austin (AirLock DJI_1001–1007): public StratMap 2021 LiDAR covers all of
  them, but the 4.5-year gap was rejected as a reference.

### NOT TESTED
- A second flight: HKisland01/02 (L1 already in `HKisland.7z`) are
  downloading; Drive quota pauses them.
- Run-to-run spread on the same flight.
- The position-based time offset inside the pipeline.
- Dimensional (point-to-point) accuracy; this is point-to-surface.
- Anything above 1600 px processing on this 15 GB machine.


## 2026-09-25 (later) — Second flight (HKisland02) and methodology verification (DEC-042 corrected)

### HKisland02, same settings as HKisland03 run B

LiDAR window 06:08:26.1–06:13:08.7 UTC (282.6 s, 19.77 M L1 points); bag
starts 06:06:40, first kept frame 06:08:26.10, 2,828 frames: same flight.
Same route as HKisland03 (279 x 431 m, 95.6–95.9 m), flown slower.
80 keyframes, 1,872,524 points, **798.6 s for 282.8 s of video (2.8x)**.

| flight | median | RMSE | p90 | p95 | p99 | cloud-to-cloud offset E/N/Up |
|---|---:|---:|---:|---:|---:|---|
| HKisland02 | 0.413 | 0.809 | 1.146 | 1.552 | 3.137 | -0.016 / -0.018 / -0.051 |
| HKisland03 (run B) | 0.370 | 0.753 | 1.045 | 1.449 | 2.970 | -0.018 / -0.014 / -0.022 |

Cloud-to-cloud (`score_against_lidar.py`, every point). See the injection test
below before reading the offset column.

Camera-RTK time offset on HKisland02: pipeline -0.628 s; position fit -0.50 s
(alignment 3.045 m at 0 s, 0.879 m at -0.50 s). With HKisland03's -0.54 to
-0.6 s, the RTK lag is a property of the feed, not of one flight.

### Methodology checks

1. **Same flight.** Every LiDAR window lies inside its bag, and the kept
   video span matches the LiDAR span (282.8 s vs 282.6 s). Pass.
2. **Truth isolation.** `run_mission.py` passes `pipeline.run` only the video,
   telemetry and parameters; nothing in `reconstruction/` reads
   `datasets/truth`. Pass.
3. **Reference repeatability.** The HKisland02 and HKisland03 L1 surveys are
   independent flights over the same ground. All 19,766,311 points of 02 against
   all 14,555,477 of 03: median 0.052 m, RMSE 0.077 m, p90 0.108 m, p95 0.137 m,
   p99 0.218 m, vertical bias -0.0013 m (a 10% sample gave the same to 1 mm).
   The reference is ~10x finer than the errors being measured. Pass.
4. **Cloud-to-cloud scorer, error injection (HKisland02 cloud):** FAIL for
   offsets.

   | injected | median | RMSE | p90 | reported offset E/N/Up |
   |---|---:|---:|---:|---|
   | none | 0.413 | 0.809 | 1.146 | -0.016 / -0.018 / -0.051 |
   | +1.00 m up | 0.673 | 1.063 | 1.625 | -0.018 / +0.016 / **+0.469** |
   | +0.30 m up | 0.397 | 0.821 | 1.183 | -0.021 / -0.006 / **+0.054** |
   | +1.00 m east | 0.395 | 0.856 | 1.301 | **+0.025** / -0.021 / -0.057 |
   | scale +1% | 0.557 | 1.061 | 1.664 | -0.017 / -0.018 / -0.011 |
   | scale +0.2% | 0.435 | 0.850 | 1.234 | -0.016 / -0.018 / -0.043 |
   | noise 0.30 m/axis | 0.448 | 0.850 | 1.242 | -0.014 / -0.016 / -0.044 |
   | noise 1.00 m/axis | 0.728 | 1.196 | 1.931 | -0.009 / -0.012 / -0.022 |

   Nearest-point distance slides along the surface: a 0.3 m vertical shift is
   invisible and a 1 m horizontal shift reads as 2.5 cm. It still ranks gross
   damage (scale, large noise). **Its "systematic offset" is not a
   measurement**, and the "offset under 2 cm" in DEC-042 is withdrawn.
5. **Vertical height-map scorer (new): Pass.** LiDAR binned to 0.5 m cells;
   only cells with >= 4 returns and height std < 5 cm are kept (flat,
   unambiguous ground and roofs); each reconstructed point in such a cell gets
   dZ = z - cell mean.

   | injected | HKisland02 median dZ | HKisland03 median dZ |
   |---|---:|---:|
   | none | **-0.239** | **-0.136** |
   | +0.30 m | +0.061 (+0.300) | +0.164 (+0.300) |
   | +1.00 m | +0.759 (+0.998) | +0.864 (+1.000) |
   | -0.10 m | -0.339 (-0.100) | -0.236 (-0.100) |

   Real vertical error on flat ground:

   | flight | points | median dZ (bias) | RMSE dZ | abs dZ p50 / p90 / p99 |
   |---|---:|---:|---:|---|
   | HKisland02 | 323,082 | -0.239 | 0.925 | 0.566 / 1.426 / 2.868 |
   | HKisland03 | 335,092 | -0.136 | 0.826 | 0.508 / 1.302 / 2.445 |

   The reconstruction sits 14–24 cm below the LiDAR, and vertical error on
   flat ground is larger than the cloud-to-cloud figures suggested.

### What is and is not measured now
- Vertical: validated metric, two flights. Bias -0.14 to -0.24 m; RMSE 0.83–0.93 m.
- Surface agreement (cloud-to-cloud): 0.75–0.81 m RMSE, ranks damage correctly
  but under-reads shifts; quote it as surface noise, not as accuracy.
- **Horizontal: not validated.** No metric here detects a 1 m horizontal
  shift. Needs identifiable features (edges, painted marks) or surveyed points.
- Horizontal/vertical sources of the -0.14 to -0.24 m bias: not yet known
  (candidates: RTK antenna-to-camera lever arm, RTK time lag, dense-stereo
  bias at 1300 px).


## 2026-09-25 (night) — Timing fix, confidence gating, single-pass test, warp (DEC-043)

All vertical figures below use `scripts/score_vertical_dsm.py`, which re-ran
its injection check on every cloud (+0.30 / +1.00 / -0.10 m recovered within
0.3 mm). Settings as run B unless stated.

### 1. Position-based time offset in the pipeline

| flight | speed estimate | position refinement | camera-RTK alignment RMSE | C2C RMSE | vertical RMSE / bias |
|---|---:|---:|---|---:|---|
| HKisland02 | -0.628 s | -0.409 s | 1.53 -> **0.878 m** | 0.809 -> 0.808 | 0.925 -> 0.921 / -0.239 -> -0.254 |
| HKisland03 | -0.586 s | -0.446 s | 1.33 -> **0.692 m** | 0.753 -> 0.756 | 0.826 -> 0.828 / -0.136 -> -0.134 |

(Pipeline offsets are in its own timestamp convention, one frame early; the
independent scorer found -0.50 and -0.54 s.) The camera track fits RTK about
twice as well. The cloud's measured accuracy did not change: a timing error
moves the model along track, horizontally, and neither validated metric here
measures horizontal position. 495 tests pass (487 before today) with the new unit tests.

### 2. Which points to measure from (threshold chosen on 02, tested on 03)

| subset | HKisland02 keep | C2C p90 | vertical RMSE / p90 | HKisland03 keep | C2C p90 | vertical RMSE / p90 |
|---|---:|---:|---|---:|---:|---|
| all | 100% | 1.146 | 0.925 / 1.426 | 100% | 1.045 | 0.826 / 1.302 |
| HIGH class (confidence >= 0.6) | 86.4% | 1.108 | 0.883 / 1.367 | 86.3% | 1.010 | 0.802 / 1.264 |
| sigma_major <= p25 | 25% | 0.603 | 0.521 / 0.788 | 25% | 0.535 | 0.434 / 0.662 |
| sigma_major <= p50 | 50% | 0.803 | 0.659 / 1.032 | 50% | 0.683 | 0.551 / 0.876 |
| height > 1 m (no surf line) | 75% | 0.962 | 0.948 / 1.477 | 77% | 0.884 | 0.837 / 1.350 |

Cross-validated: sigma_major <= **0.120 m** chosen on 02 (C2C p90 <= 1.0 m,
keeps 83%) keeps **81%** of 03 with C2C RMSE 0.611 / p90 0.853 and vertical RMSE
**0.686** / p90 **1.096** (from 0.826 / 1.302). At 0.087 m: 44% kept, vertical
RMSE 0.523 / p90 0.820. Dense confidence depends on view count alone and fusion
already requires 4 views, which is why the HIGH class barely separates.
Adopted as `measure_max_sigma_major_m = 0.12` (DEC-043).

### 3. Single-pass test (V3.1 plan section 67)

43% (03) and 54% (02) of flight time is over ground already seen more than
30 s earlier, so the multi-pass numbers above are not single-pass numbers. The
first-visit stretch of each flight (no ground revisited) was reconstructed
alone at the same keyframe density (~0.4/s) and compared with the multi-pass
cloud cropped to the same footprint.

| | HKisland03 single (49.4 s, 20 kf) | HKisland03 multi, same ground | HKisland02 single (63.2 s, 25 kf) | HKisland02 multi, same ground |
|---|---:|---:|---:|---:|
| vertical bias | **-0.078** | -0.178 | **-0.052** | -0.310 |
| vertical RMSE | **0.555** | 0.848 | **0.585** | 0.942 |
| abs dZ p50 / p90 | 0.349 / 0.897 | 0.540 / 1.346 | 0.375 / 0.953 | 0.600 / 1.450 |
| abs dZ p99 | 1.602 | 2.469 | 1.601 | 2.868 |
| wall / video | 162.5 s / 49.4 s | — | 216.3 s / 63.2 s | — |

The single pass is **more** accurate on the same ground, on both flights.

### 4. Why: large-scale warp, not layering

Height spread of our points inside flat 1 m LiDAR cells (LiDAR std < 5 cm):
single pass median 0.049 / 0.051 m, multi-pass 0.067 / 0.073 m (03 / 02).
Layering exists but is centimetres.

Median vertical error per 40 m tile, and the RMSE left if each tile's bias
were removed:

| cloud | tiles | tile bias range | tile bias std | RMSE | RMSE without tile bias |
|---|---:|---|---:|---:|---:|
| 02 multi-pass | 55 | -1.22 .. +2.14 m | 0.79 | 0.921 | **0.573** |
| 03 multi-pass | 56 | -1.05 .. +2.01 m | 0.74 | 0.828 | **0.507** |
| 02 single-pass | 29 | -0.81 .. +0.99 m | 0.45 | 0.585 | **0.382** |
| 03 single-pass | 32 | -0.96 .. +0.87 m | 0.45 | 0.555 | **0.347** |

About 40% of the vertical error is low-frequency bending of the model, larger
over longer flights. A single similarity to RTK cannot remove it; RTK used as
pose priors inside bundle adjustment could (DEC-043, future work 1).

### 5. Small fixes
- A declared global shutter (`camera.json: "shutter": "global"`) disables the
  rolling-shutter check, which had warned "mild smear" on MARS-LVIG's
  global-shutter camera. MARS missions now declare it.
- The alignment time offset stores its uncertainty: offsets within 10% + 2 cm
  of the best residual (±0.05 s on HKisland03, from the curve in section 1 of
  the earlier entry).

### NOT TESTED
- Horizontal accuracy (no validated metric).
- The sigma threshold on any other site, camera or altitude.
- Whether keyframe density or dense resolution changes the single- vs
  multi-pass gap.
- Run-to-run spread.


## 2026-09-26 — Future work item 1: the warp was the lens, not the georeferencing (DEC-044)

### Pose priors in bundle adjustment: tried, no gain
`scripts/trial_pose_prior_ba.py` on HKisland03 single pass (20 keyframes).
RTK positions as priors (sigma 5 cm, intrinsics fixed), dense stereo re-run
with the pipeline's settings: vertical RMSE 0.583 -> 0.606, tile-bias std
0.46 -> 0.54 (worse). Even forced, cameras stayed 0.40 m from RTK: the
priors disagree with the images by ~0.5 m (timing ±0.05 s is ±0.45 m at
8.9 m/s; lever arm unmodelled).

### Diagnosis: a lens-distortion bowl across the strip
Vertical error by lateral distance from the flight line (single pass):

| distance | HKisland03 median dZ | HKisland02 median dZ |
|---|---:|---:|
| 0–20 m | -0.215 | -0.238 |
| 20–40 m | +0.200 | +0.210 |
| 40–60 m | +0.304 | +0.399 |
| 60–80 m | -0.272 | -0.242 |

The same wave on two independent flights: residual radial distortion left by
the published chessboard calibration.

### Refining only distortion after mapping (focal and principal point fixed)
Trial (`--no-priors --refine-radial`; similarity to RTK as before):

| cloud | vertical RMSE | p90 | p99 | tile-bias std | refined k1 / k2 |
|---|---|---|---|---|---|
| 03 single | 0.583 -> 0.475 | 0.948 -> 0.708 | 1.684 -> 1.157 | 0.46 -> 0.26 | -0.0021 / +0.0037 |
| 02 single | 0.613 -> 0.487 | 1.011 -> 0.713 | 1.687 -> 1.297 | 0.46 -> 0.27 | -0.0027 / +0.0041 |
| 03 multi | 0.828 -> 0.516 | 1.303 -> 0.776 | 2.407 -> 1.548 | 0.75 -> 0.32 | -0.0011 / +0.0029 |
| 02 multi | 0.914 -> 0.519 | 1.416 -> 0.789 | 2.668 -> 1.704 | 0.79 -> 0.30 | -0.0017 / +0.0036 |

Adding loose RTK priors (0.3 m) on top changed nothing (0.478 vs 0.475).

### In the pipeline (`refine_residual_distortion`, default on), end to end

| run | before: vertical bias / RMSE / p90 / p99 | after | C2C RMSE / p90 before -> after | wall |
|---|---|---|---|---|
| 03 single | -0.078 / 0.555 / 0.897 / 1.602 | +0.356 / 0.495 / 0.737 / 1.114 | 0.758 / 0.905 -> 0.744 / 0.720 | 170.3 s |
| 02 single | -0.052 / 0.585 / 0.953 / 1.601 | +0.324 / 0.497 / 0.739 / 1.222 | 0.820 / 0.998 -> 0.789 / 0.736 | 218.3 s |
| 03 multi | -0.134 / 0.828 / 1.308 / 2.416 | +0.285 / 0.542 / 0.812 / 1.565 | 0.756 / 1.052 -> 0.614 / 0.704 | 749.6 s |
| 02 multi | -0.254 / 0.921 / 1.422 / 3.113* | +0.186 / 0.544 / 0.829 / 1.730 | 0.808 / 1.147 -> 0.618 / 0.720 | 811.8 s |

(*C2C p99.) The pipeline refined the same coefficients as the trial. Camera-to-RTK
residual after timing: 0.30 / 0.30 / 0.45 / 0.69 m (was 0.55–1.53).

### Constant vertical offset: calibrated on the other flight
With the bowl removed a constant +0.19..+0.36 m remains, consistent with the
GNSS antenna sitting above the camera. Each flight corrected with the
**other** flight's offset:

| run | offset used (from) | vertical bias | RMSE | abs dZ p50 | p90 | p99 |
|---|---|---:|---:|---:|---:|---:|
| 03 single | +0.324 (02 single) | +0.033 | **0.377** | 0.181 | 0.572 | 1.303 |
| 02 single | +0.356 (03 single) | -0.033 | **0.418** | 0.225 | 0.632 | 1.395 |
| 03 multi | +0.186 (02 multi) | +0.098 | **0.484** | 0.251 | 0.762 | 1.502 |
| 02 multi | +0.285 (03 multi) | -0.098 | **0.531** | 0.236 | 0.858 | 1.651 |

### Horizontal accuracy: first validated metric
`scripts/score_horizontal_offset.py`: one translation fitted point-to-plane on
LiDAR surfaces sloped >= 25 degrees, coarse-to-fine robust weights. Injected
+1.00 / +0.50 m east and north recovered as 1.00 / 0.50 on every run (a fixed
0.2 m Huber scale recovered only 70–82%, so it was changed).

| run | horizontal offset (E, N) |
|---|---|
| 03 single, before | 0.542 m (+0.30, -0.45) |
| 03 multi, before timing fix / after timing fix | 0.575 (-0.52, -0.24) / 0.535 (-0.44, -0.31) |
| 02 multi, before timing fix / after timing fix | 0.569 (-0.53, -0.22) / 0.536 (-0.43, -0.32) |
| **03 single, distortion refined** | **0.078 m** (+0.07, -0.04) |
| **02 single, distortion refined** | **0.281 m** (+0.24, +0.15) |
| **03 multi, distortion refined** | **0.129 m** (-0.13, +0.00) |
| **02 multi, distortion refined** | **0.065 m** (-0.06, +0.03) |

The persistent ~0.5 m south-west offset was the bowl: a curved surface fitted
to RTK lands shifted. Global offset only; per-point horizontal error is still
not measured.

### Checks
Vertical lever arm end to end (0.29 m, `camera.json`): HKisland03 single-pass
bias +0.356 -> +0.073, RMSE 0.377 (not held out: 0.29 is partly fitted on this
flight). Synthetic test recovers a known k1/k2 with focal fixed. 497 tests pass.

### NOT TESTED
- Any flight outside HKisland02/03 with the 0.29 m value (HKisland01 and other
  MARS-LVIG sites are held out from it).
- Residual-distortion refinement on a camera without a supplied calibration
  (it only runs when one is supplied), and on DJI/UseGeo.
- Per-point horizontal error.

## 2026-10-03 — Raster products: DSM validated, land cover experimental (DEC-045)

`drishti_recon/rasters.py` writes DSM, DTM, orthophoto, sigma and land-cover
GeoTIFFs for georeferenced runs; `scripts/build_rasters.py` made them for the
existing missions (0.4–18 s each). Details in `drishti3d/docs/RASTERS.md`.

### DSM against same-flight LiDAR (`scripts/score_raster_dsm.py`)
Flat-cell vertical metric of DEC-042, DEC-044 antenna offsets (other flight's),
each DSM cell scored as a point at its centre:

| mission | cloud RMSE / bias | DSM RMSE / bias | mean-Z RMSE / bias | cell |
|---|---|---|---|---|
| HKisland03 (corr +0.324) | 0.377 / +0.032 | **0.407 / +0.055** | 0.402 / +0.006 | 0.5 m |
| HKisland02 (corr +0.356) | 0.418 / -0.032 | **0.416 / -0.026** | 0.420 / -0.051 | 0.35 m |
| UseGeo 1 (no corr) | 0.432 / +0.363 | **0.444 / +0.370** | 0.424 / +0.357 | 0.25 m |

The cloud rows reproduce DEC-044 to the millimetre. Injection on each DSM:
+0.30 / +1.00 / -0.10 m recovered within 0.3 mm. **New:** UseGeo 1 sits +0.36 m
high on flat cells (not measured with this metric before).

### Building class against OSM footprints (`scripts/score_landcover_osm.py`)
Footprints from Overpass, OSM data of 2026-10-03, kept in
`datasets/truth/osm_buildings/` with provenance. Tolerance 1.5 m.

| mission | precision | recall | F1 | roofs as ground |
|---|---:|---:|---:|---:|
| UseGeo 1 | 0.766 | 0.863 | 0.812 | 0.020 |
| DJI_1003 | 0.303 | 0.108 | 0.159 | 0.521 |
| DJI_1001 | 0.379 | 0.127 | 0.190 | 0.406 |
| HKisland03 | 0.140 | 0.953 | 0.245 | 0.000 |
| HKisland02 | 0.247 | 0.931 | 0.390 | 0.000 |

Ground-filter window 120 m (tuned on DJI_1003): DJI_1003 F1 0.241, DJI_1001
0.213, UseGeo 0.797, HKisland03 0.155 (precision 0.084), HKisland02 0.105
(precision 0.056; building cells 9,919 -> 46,196). Rejected: cliffs.

### Austin placement against OSM
Elevated-cell (DSM > 5 m above a 120 m local minimum) cross-correlation with
footprints, +-40 m: UseGeo 0.0 m (peak 5.5x median). DJI_1001 quadrants
(E, N): (-4, -19), (-22, -14), (+10, -12), (+20, -40) m. DJI_1003: (0, 0),
(0, 0), (+4.5, +10.5), (-33, +39) m. Inconsistent; not a constant offset.

### Checks
10 new tests (8 in `tests/test_rasters.py`, LAS classes, rasters API), with one
proven by a deliberate bug (highest-point selection swapped for lowest fails
it). End-to-end pipeline test asserts rasters on a georeferenced run.

### NOT TESTED
- The DTM against any ground truth (none available).
- Land cover classes other than building.
- AGZ against OSM (Overpass timed out twice).
- Austin absolute placement (planned: StratMap 2021, horizontal only).

## 2026-10-03 (later) — Land cover: cloth filter, top-surface rule, walls (DEC-046)

All against OSM footprints (`score_landcover_osm.py`, tolerance 1.5 m). F1 per
mission, DJI_1003 / DJI_1001 / UseGeo / HKisland03 / HKisland02:

| configuration | F1 |
|---|---|
| morphological, 40 m (first version) | 0.159 / 0.190 / 0.812 / 0.245 / 0.390 |
| + top-surface rule | 0.168 / 0.191 / 0.814 / 0.245 / 0.390 |
| cloth 2 m, rigidness 2 | 0.274 / 0.263 / 0.887 / 0.054 / 0.057 |
| cloth 2 m, rigidness 1 / 3; cloth 1 m, rigidness 1 | cliffs no better (HK precision 0.03–0.06) |
| morphological + walls 10% (**default**) | 0.166 / 0.187 / 0.810 / 0.250 / 0.412 |
| cloth + walls 10% | 0.259 / 0.247 / 0.885 / 0.628 / 0.665 |
| cloth + walls 5% / 8% / 12% / 15% / 20% | HK03 0.063 / 0.106 / 0.690 / 0.000 / 0.000; HK02 0.623 / 0.665 / 0.007 / 0.007 / 0.007 |

AGZ (held out, footprints fetched after tuning): default 0.455, cloth + walls
0.470, first version 0.446.

Features measured before the wall rule: roof vs cliff plane-fit residual and
slope do not separate (HK rock residual median 0.07–0.10 m, Austin roofs
0.38–0.44 m; slopes 21–22 vs 13–21 deg). Edge-wall share does (HK cliff patches
median 0.01–0.02; real buildings 0.31 UseGeo, 0.54–0.60 Austin, 0.11–0.14 the
two HK buildings).

Visual check that reversed the cloth default: on HKisland03 the cloth DTM kept
only the shoreline, ground fell from 83% to 34% of cells and the grass slopes
became high vegetation; AGZ's ground fell to 0.2%.

## 2026-10-04 — Audit P0/P1: accuracy, RTK, analytics, OBJ/FBX, replay, preview (DEC-048)

Environment: build sandbox, 4-core Xeon, no GPU, Python 3.11, `open3d` 0.20,
`assimp` CLI installed, `torch` not installed, EGM2008 grid not installed (its
download is blocked by the sandbox network policy).

### Suites
- Focused command from the action plan's section 6: **97 passed, 3 skipped**
  (was 83 passed, 2 failed). The two vertical-reference failures are fixed by
  declaring the datum in the fixtures; two new tests pin the unknown state.
- Full suite: **645 passed, 5 skipped, 1 failed.** The failure,
  `test_masking_backends.py::TestUntrainedSemanticRefused`, needs `torch` to
  reach the "no weights" refusal; without it the import fails first. Not
  related to this work.
- Frontend: `tsc` clean; `npm test` (replay interpolation) 4/4.
- New tests: `test_accuracy.py` (10), `test_rtk_pos.py` (11), `test_terrain.py`
  (10), `test_analysis_api.py` (7), `test_mesh_formats.py` (5),
  `test_replay.py` (11), `test_evidence_package.py` (3),
  `test_texture_hero.py` (4), `test_preview_tier.py` (4).

### End to end (synthetic flight, 150 frames, 5 s, through the web API)
- Balanced run with `altitude_reference=ELLIPSOIDAL` telemetry: cloud, DSM,
  DTM, ortho, sigma, land cover, `mesh.obj` (22,065 vertices) and `mesh.fbx`
  via assimp; rasters at 1.5 m, datum ellipsoidal.
- Terrain endpoints on that run: volume ok (95% observed), slope ok, profile
  ok, line of sight blocked. A picked point gave MGRS `43RGM1598767202`,
  ellipsoidal height, and no sea-level height with "geoid grid not installed".
- Accuracy from 12 synthetic points (4 GCP, 8 check, 0.4/0.25/0.3 m offset +
  5 cm noise): raw RMSE_H 0.495 m; checkpoints after similarity 0.089 m H,
  0.058 m V. Synthetic truth: this checks the code, not field accuracy.
- Browser (Playwright, Chromium): volume, profile (with breaks) and line of
  sight from picks; accuracy panel with independent / NOT independent badges;
  video seek to 1.00 s → "Synced", play, pause (pose stable while paused), end
  of video → "No solved camera here". No console errors. Open-source Chromium
  has no H.264, so the clip was re-uploaded as VP9 for this check.
- Preview → full: preview 159 s (36 keyframes, 7,610 points), then the queued
  balanced run 283 s (47 keyframes, 8,023 points) replaced it; project ended
  `done`. CPU only, 5-second clip: not a timing claim for real flights.

### Measured while writing
- Volume bias of the DSM against mean height: flat 256 m², 0.1 m noise,
  ~25 points per 0.5 m cell: DSM 50.2 m³, mean 0.06 m³.

### NOT TESTED
- Any of this on a real flight or on the demo laptop; the evidence package on
  the hero mission.
- Checkpoint accuracy against real surveyed points.
- OpenMVS texturing (OpenMVS unavailable); EGM2008 conversion (grid
  unavailable).
