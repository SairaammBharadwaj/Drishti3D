"""Same-pass evidence recovery (plan F4 / section 5.7).

The feature's claim is that compute spent on *one* measurement recovers evidence
a uniform budget missed. These tests pin the parts that make that claim
falsifiable: what is rejected and why, that ranking follows parallax rather than
proximity, that a refined endpoint is not snapped back to where it started, and
that a run which achieves nothing says so.
"""
from __future__ import annotations

import json

import numpy as np
import pytest

from drishti_recon import refinement as rf
from drishti_recon import questions as qmod
from drishti_recon.evidence import ReconstructionEvidence


def _arc_cams(frame_indices, radius=12.0, target=(0.0, 0.0, 0.0), spread=1.2):
    cams, t = [], np.asarray(target, float)
    n = len(frame_indices)
    for k, fi in enumerate(frame_indices):
        a = -spread / 2 + spread * (k / max(n - 1, 1))
        C = t + np.array([radius * np.sin(a), -radius * np.cos(a), 4.0])
        fwd = t - C
        fwd /= np.linalg.norm(fwd)
        right = np.cross(fwd, [0, 0, 1.0])
        right /= np.linalg.norm(right)
        down = np.cross(fwd, right)
        cams.append({"frame_index": int(fi), "C": C.tolist(),
                     "R": np.stack([right, down, fwd]).tolist()})
    return cams


def _project(cam, K, p):
    R = np.asarray(cam["R"], float)
    C = np.asarray(cam["C"], float)
    v = R @ (np.asarray(p, float) - C)
    return np.array([K[0][0] * v[0] / v[2] + K[0][2],
                     K[1][1] * v[1] / v[2] + K[1][2]], np.float32)


K = [[900.0, 0, 640.0], [0, 900.0, 360.0], [0, 0, 1.0]]


def _fixture(tmp_path, *, registered=(0, 4, 8), n_decoded=13, point=(0, 0, 0),
             measured=None):
    """A reconstruction whose pass has unused frames between registered ones.

    ``measured`` defaults to the first two registered frames -- a point seen
    from two of the three cameras, which is the shape refinement exists for.
    """
    measured = tuple(registered[:2]) if measured is None else measured
    art = tmp_path
    art.mkdir(parents=True, exist_ok=True)
    cams = _arc_cams(registered)
    (art / "trajectory.json").write_text(json.dumps({
        "frame": {"lat0": 47.0, "lon0": 8.0, "alt0": 400.0},
        "K": K, "image_size": [1280, 720], "cameras_enu": cams}))
    (art / "manifest.json").write_text(json.dumps({
        "version": "0.1.0", "created": 1.0, "video_sha256": "d" * 64,
        "params": {"proc_max_width": 1280, "intrinsics": {}},
        "alignment": {"scale_source": "gps", "scale": 10.0,
                      "scale_sigma": 0.05}}))

    pts = np.vstack([np.asarray(point, float)[None, :],
                     np.random.default_rng(4).uniform(-1, 1, (40, 3)) + 6.0])
    np.savez_compressed(art / "cloud.npz", points=pts,
                        sigma=np.full(len(pts), 0.03),
                        sigma_major=np.full(len(pts), 0.05))

    frames, uvs = [], []
    by_frame = {c["frame_index"]: c for c in cams}
    for fi in measured:
        frames.append(fi)
        uvs.append(_project(by_frame[fi], K, point))
    np.savez_compressed(
        art / "observations.npz",
        point_index=np.zeros(len(frames), np.int32),
        keyframe_index=np.arange(len(frames), dtype=np.int32),
        frame_index=np.asarray(frames, np.int32),
        uv=np.asarray(uvs, np.float32),
        image_width=np.array([1280], np.int32),
        image_height=np.array([720], np.int32))

    (art / "frame_metrics.json").write_text(json.dumps([
        {"frame_index": i, "timestamp": float(i), "blur": 400.0,
         "accepted": True} for i in range(n_decoded)]))
    (art / "keyframes.json").write_text(json.dumps(
        [{"frame_index": int(i), "timestamp": float(i)} for i in registered]))
    return ReconstructionEvidence.load(art), art


# --- planning -------------------------------------------------------------- #
def test_the_unused_frames_of_the_pass_are_the_candidate_pool(tmp_path):
    ev, art = _fixture(tmp_path / "a")
    eng = rf.RefinementEngine(ev, art)
    cands = eng.candidates([0.0, 0.0, 0.0])
    assert len(cands) == 13
    used = [c for c in cands if c.rejected == rf.REJECT_ALREADY_USED]
    assert {c.frame_index for c in used} == {0, 4, 8}


def test_every_rejection_names_a_reason_and_explains_it(tmp_path):
    ev, art = _fixture(tmp_path / "b")
    eng = rf.RefinementEngine(ev, art)
    for c in eng.candidates([0.0, 0.0, 0.0]):
        if c.rejected:
            assert c.rejected in rf.REJECT_GUIDANCE
            assert c.to_dict()["rejection_explanation"]


def test_frames_outside_the_registered_span_cannot_be_posed(tmp_path):
    """Extrapolating past the last camera would invent a trajectory."""
    ev, art = _fixture(tmp_path / "c", registered=(2, 4, 6), n_decoded=9)
    eng = rf.RefinementEngine(ev, art)
    by = {c.frame_index: c for c in eng.candidates([0.0, 0.0, 0.0])}
    assert by[0].rejected == rf.REJECT_NO_BRACKET
    assert by[8].rejected == rf.REJECT_NO_BRACKET
    assert by[3].rejected != rf.REJECT_NO_BRACKET


def test_blurred_frames_are_rejected_before_anything_is_decoded(tmp_path):
    ev, art = _fixture(tmp_path / "d")
    metrics = json.loads((art / "frame_metrics.json").read_text())
    for m in metrics:
        if m["frame_index"] in (1, 2):
            m["accepted"] = False
    (art / "frame_metrics.json").write_text(json.dumps(metrics))
    eng = rf.RefinementEngine(ev, art)
    by = {c.frame_index: c for c in eng.candidates([0.0, 0.0, 0.0])}
    assert by[1].rejected == rf.REJECT_QUALITY
    assert by[2].rejected == rf.REJECT_QUALITY


def test_a_view_parallel_to_an_existing_one_adds_nothing(tmp_path):
    """Redundancy is not evidence; the gate is angular, not a frame count."""
    ev, art = _fixture(tmp_path / "e", registered=(0, 4, 8), n_decoded=9,
                       measured=(0, 4, 8))
    eng = rf.RefinementEngine(ev, art)
    # A very tight arc: every unused frame sits between measuring frames that
    # already look from almost the same direction.
    cams = _arc_cams((0, 4, 8), spread=0.02)
    traj = json.loads((art / "trajectory.json").read_text())
    traj["cameras_enu"] = cams
    (art / "trajectory.json").write_text(json.dumps(traj))
    ev2 = ReconstructionEvidence.load(art)
    eng = rf.RefinementEngine(ev2, art)
    cands = eng.candidates([0.0, 0.0, 0.0])
    assert all(c.rejected is not None for c in cands)
    assert any(c.rejected == rf.REJECT_NO_PARALLAX_GAIN for c in cands)


def test_ranking_follows_parallax_not_frame_order(tmp_path):
    ev, art = _fixture(tmp_path / "f", registered=(0, 6, 12), n_decoded=13,
                       measured=(0, 6))
    eng = rf.RefinementEngine(ev, art)
    usable = [c for c in eng.candidates([0.0, 0.0, 0.0]) if c.rejected is None]
    assert usable, "this geometry should leave usable candidates"
    gains = [c.parallax_gain_deg for c in usable]
    assert gains == sorted(gains, reverse=True) or \
        [c.score for c in usable] == sorted([c.score for c in usable],
                                            reverse=True)
    assert usable[0].parallax_gain_deg >= rf.MIN_PARALLAX_GAIN_DEG


# --- triangulation --------------------------------------------------------- #
def test_triangulation_recovers_a_known_point():
    truth = np.array([1.0, 2.0, 3.0])
    cams = _arc_cams((0, 5, 10), radius=15.0, target=truth, spread=1.4)
    rays, sigmas = [], []
    for c in cams:
        rays.append((np.asarray(c["R"], float), np.asarray(c["C"], float),
                     _project(c, K, truth).astype(float)))
        sigmas.append(1.0)
    X, sig = rf._triangulate(rays, sigmas, np.asarray(K, float), truth)
    assert X is not None
    assert np.allclose(X, truth, atol=1e-3)
    assert np.isfinite(sig) and sig > 0


def test_an_inflated_ray_pulls_less_on_the_solution():
    """A PnP-recovered camera must genuinely count for less, not just say so."""
    truth = np.array([0.0, 0.0, 0.0])
    cams = _arc_cams((0, 5, 10), radius=15.0, target=truth, spread=1.4)
    good = [(np.asarray(c["R"], float), np.asarray(c["C"], float),
             _project(c, K, truth).astype(float)) for c in cams]
    # A fourth, badly-placed observation: 20 px off.
    bad_cam = _arc_cams((20,), radius=15.0, target=truth, spread=0.0)[0]
    bad = (np.asarray(bad_cam["R"], float), np.asarray(bad_cam["C"], float),
           _project(bad_cam, K, truth).astype(float) + np.float32([20.0, 20.0]))

    trusted, _ = rf._triangulate(good + [bad], [1.0] * 4,
                                 np.asarray(K, float), truth)
    inflated, _ = rf._triangulate(
        good + [bad], [1.0] * 3 + [rf.POSE_UNCERTAINTY_INFLATION * 5.0],
        np.asarray(K, float), truth)
    assert np.linalg.norm(inflated - truth) < np.linalg.norm(trusted - truth)


def test_a_runaway_solve_is_refused_not_returned():
    """A point that leaves the scene is a solver artefact, not a refinement.

    Both cameras are aimed at the seed but their observations point at something
    200 m away. The least-squares answer is confidently wrong, so it is refused
    rather than returned as a refined endpoint.
    """
    seed = np.array([0.0, 0.0, 0.0])
    cams = _arc_cams((0, 1), radius=15.0, target=seed, spread=1.2)
    far = np.array([0.0, 200.0, 0.0])
    rays = [(np.asarray(c["R"], float), np.asarray(c["C"], float),
             _project(c, K, far).astype(float)) for c in cams]
    X, _ = rf._triangulate(rays, [1.0, 1.0], np.asarray(K, float), seed)
    assert X is None


def test_near_parallel_rays_report_a_large_positional_sigma():
    """Weak conditioning must show up in the uncertainty, not only in the guard."""
    truth = np.array([0.0, 0.0, 0.0])
    wide = _arc_cams((0, 1), radius=15.0, target=truth, spread=1.4)
    narrow = _arc_cams((0, 1), radius=15.0, target=truth, spread=0.01)

    def rays_for(cams):
        return [(np.asarray(c["R"], float), np.asarray(c["C"], float),
                 _project(c, K, truth).astype(float)) for c in cams]

    _, s_wide = rf._triangulate(rays_for(wide), [1.0, 1.0],
                                np.asarray(K, float), truth)
    _, s_narrow = rf._triangulate(rays_for(narrow), [1.0, 1.0],
                                  np.asarray(K, float), truth)
    assert s_narrow > s_wide * 10


def test_fewer_than_two_rays_is_not_a_triangulation():
    assert rf._triangulate([], [], np.asarray(K, float), [0, 0, 0]) == (None, None)


# --- the value function ---------------------------------------------------- #
def test_value_fn_does_not_snap_the_refined_endpoint_back():
    """Re-snapping would silently undo the refinement and report success.

    `measure.measure_distance` snaps to the nearest cloud point, which is right
    for an operator clicking in space and fatal for a moved endpoint.
    """
    fn = rf.measurement_value_fn("distance", [0.05, 0.05])
    v0, _ = fn([np.array([0.0, 0.0, 0.0]), np.array([5.0, 0.0, 0.0])])
    v1, _ = fn([np.array([0.4, 0.0, 0.0]), np.array([5.0, 0.0, 0.0])])
    assert v0 == pytest.approx(5.0)
    assert v1 == pytest.approx(4.6), "the moved endpoint must move the answer"


def test_value_fn_carries_the_scale_term():
    plain = rf.measurement_value_fn("distance", [0.01, 0.01])
    scaled = rf.measurement_value_fn("distance", [0.01, 0.01],
                                     scale_sigma_rel=0.02)
    _, s0 = plain([[0, 0, 0], [40, 0, 0]])
    _, s1 = scaled([[0, 0, 0], [40, 0, 0]])
    assert s1 > s0
    assert s1 == pytest.approx(np.hypot(s0, 0.02 * 40.0), rel=0.05)


@pytest.mark.parametrize("kind,pts", [
    ("height", [[0, 0, 0], [0, 0, 7.0]]),
    ("area", [[0, 0, 0], [4, 0, 0], [4, 3, 0]]),
])
def test_value_fn_handles_the_other_question_kinds(kind, pts):
    fn = rf.measurement_value_fn(kind, [0.05] * len(pts))
    v, s = fn([np.asarray(p, float) for p in pts])
    assert v is not None and v > 0
    assert np.isfinite(s)


# --- the run record -------------------------------------------------------- #
def test_refining_without_a_video_terminates_with_a_reason(tmp_path):
    ev, art = _fixture(tmp_path / "g")
    eng = rf.RefinementEngine(ev, art)          # no video_path
    q = qmod.MeasurementQuestion("distance", tolerance_m=0.2)
    run = eng.refine(q, [[0.0, 0.0, 0.0], [5.0, 0.0, 0.0]],
                     value_fn=rf.measurement_value_fn("distance", [0.05, 0.05]),
                     budget_frames=2, max_decode=2)
    assert run.termination_reason
    assert run.after == run.before or run.after["value"] == run.before["value"]
    assert not run.improved


def test_a_run_that_achieves_nothing_says_so(tmp_path):
    """No improvement is a valid result and must be visible, not hidden."""
    ev, art = _fixture(tmp_path / "h", registered=(0, 1, 2), n_decoded=3)
    eng = rf.RefinementEngine(ev, art)
    q = qmod.MeasurementQuestion("distance", tolerance_m=0.2)
    run = eng.refine(q, [[0.0, 0.0, 0.0], [5.0, 0.0, 0.0]],
                     value_fn=rf.measurement_value_fn("distance", [0.05, 0.05]))
    d = run.to_dict()
    assert d["n_added"] == 0
    assert d["termination_reason"]
    assert d["before"]["value"] == d["after"]["value"]
    assert run.improved is False


def test_the_run_record_names_which_endpoint_it_worked_on(tmp_path):
    ev, art = _fixture(tmp_path / "i")
    eng = rf.RefinementEngine(ev, art)
    q = qmod.MeasurementQuestion("distance", tolerance_m=0.2)
    run = eng.refine(q, [[0.0, 0.0, 0.0], [5.0, 0.0, 0.0]],
                     value_fn=rf.measurement_value_fn("distance", [0.05, 0.05]))
    assert any("refining endpoint" in n for n in run.notes)
    assert run.to_dict()["rejected"], "rejections are reported, not dropped"


def test_improvement_is_not_judged_on_interval_width_alone():
    """Clearing a blocking reason is an improvement even if the interval holds.

    Measured on the AGZ mission: three recovered frames moved the value by
    0.10 m and the interval by 0.001 m, because the interval was dominated by
    the other endpoint and the metric scale -- but they cleared
    `insufficient_views`, which was what blocked the measurement.
    """
    run = rf.RefinementRun(question_kind="distance", tolerance_m=0.3,
                           budget_frames=4)
    run.before = {"value": 3.010, "sigma": 0.09944,
                  "reasons": ["insufficient_views", "interval_not_calibrated"]}
    run.after = {"value": 2.906, "sigma": 0.09901,
                 "reasons": ["interval_not_calibrated"]}
    assert run.reasons_cleared == ["insufficient_views"]
    assert run.improved is True
    assert run.value_change_m == pytest.approx(-0.104, abs=1e-3)


def test_a_narrower_interval_alone_still_counts_but_is_reported_separately():
    run = rf.RefinementRun(question_kind="distance", tolerance_m=0.3,
                           budget_frames=4)
    run.before = {"value": 3.0, "sigma": 0.20, "reasons": ["interval_not_calibrated"]}
    run.after = {"value": 3.0, "sigma": 0.10, "reasons": ["interval_not_calibrated"]}
    assert run.reasons_cleared == []
    assert run.interval_narrowed is True
    assert run.improved is True


def test_a_wider_interval_with_nothing_cleared_is_not_an_improvement():
    """Refinement can make an interval worse, and that must be visible."""
    run = rf.RefinementRun(question_kind="distance", tolerance_m=0.3,
                           budget_frames=4)
    run.before = {"value": 3.0, "sigma": 0.10, "reasons": ["interval_not_calibrated"]}
    run.after = {"value": 3.1, "sigma": 0.18, "reasons": ["interval_not_calibrated"]}
    assert run.improved is False
    assert run.interval_narrowed is False
    assert run.to_dict()["value_change_m"] == pytest.approx(0.1)


def test_a_verdict_that_regressed_is_never_an_improvement():
    """Reasons vanish when a verdict drops to not_observable.

    The hard-refusal path returns only its own reasons, so every soft reason
    disappears from the list. Measured on the AGZ mission, two runs in thirty
    "cleared" reasons this way while making the measurement unusable.
    """
    run = rf.RefinementRun(question_kind="distance", tolerance_m=0.3,
                           budget_frames=4)
    run.before = {"value": 3.0, "sigma": 0.5, "status": "needs_refinement",
                  "reasons": ["interval_exceeds_tolerance",
                              "interval_not_calibrated"]}
    run.after = {"value": 3.1, "sigma": 0.4, "status": "not_observable",
                 "reasons": ["outside_established_coverage"]}
    assert run.reasons_cleared == ["interval_exceeds_tolerance",
                                   "interval_not_calibrated"]
    assert run.reasons_added == ["outside_established_coverage"]
    assert run.status_regressed is True
    assert run.interval_narrowed is True
    assert run.improved is False, "a narrower interval on an unusable answer"


def test_a_verdict_that_improved_still_counts():
    run = rf.RefinementRun(question_kind="distance", tolerance_m=0.3,
                           budget_frames=4)
    run.before = {"value": 3.0, "sigma": 0.2, "status": "needs_refinement",
                  "reasons": ["interval_exceeds_tolerance"]}
    run.after = {"value": 3.0, "sigma": 0.1, "status": "estimated_only",
                 "reasons": ["interval_not_calibrated"]}
    assert run.status_regressed is False
    assert run.improved is True


def test_an_unknown_status_does_not_silently_read_as_a_regression():
    run = rf.RefinementRun(question_kind="distance", tolerance_m=0.3,
                           budget_frames=4)
    run.before = {"value": 3.0, "sigma": 0.2, "reasons": []}
    run.after = {"value": 3.0, "sigma": 0.1, "reasons": []}
    assert run.status_regressed is False
    assert run.improved is True


def test_endpoint_provenance_reaches_the_before_and_after_snapshots(tmp_path):
    """Without provenances the snapshots disagree with the measurement layer.

    `for_points` falls back to a pessimistic default when an endpoint does not
    snap to observation lineage. In the F4 experiment that made two unchanged
    measurements read as regressions to `not_observable`.
    """
    ev, art = _fixture(tmp_path / "prov")
    eng = rf.RefinementEngine(ev, art)
    q = qmod.MeasurementQuestion("distance", tolerance_m=0.2)
    far = [[40.0, 40.0, 40.0], [45.0, 40.0, 40.0]]      # no lineage out here
    vf = rf.measurement_value_fn("distance", [0.05, 0.05])

    without = eng.refine(q, far, value_fn=vf, budget_frames=1, max_decode=1)
    with_prov = eng.refine(q, far, value_fn=vf, budget_frames=1, max_decode=1,
                           provenances=[0, 0])          # OBSERVED_HIGH_CONF
    assert "endpoint_not_observed" in without.before["reasons"]
    assert "endpoint_not_observed" not in with_prov.before["reasons"]
