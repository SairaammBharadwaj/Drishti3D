"""C06: a refined result and the evidence behind it must describe one thing.

Findings from the review: the API persisted the operator's original endpoints
beside the refined value, carried the previous threshold verdict forward
unchanged, and added a one-endpoint view gain to a measurement-wide minimum.
"""
from types import SimpleNamespace

import numpy as np
import pytest

from drishti_recon import questions as qmod
from drishti_recon import refinement as refmod


def test_snapshot_recomputes_the_threshold():
    """A value that crosses the threshold must change sides."""
    q = qmod.MeasurementQuestion(kind="distance", tolerance_m=0.5,
                                 threshold_m=10.0, threshold_direction="at_least")
    ev = qmod.Evidence(n_supporting_views=6, max_ray_separation_deg=30.0,
                       view_support_basis="triangulated_observations",
                       endpoints_observed=True, endpoints_within_coverage=True,
                       scale_source="gps", scale_sigma_rel=0.001)
    below = refmod._snapshot(q, 9.0, 0.05, ev)
    above = refmod._snapshot(q, 11.0, 0.05, ev)
    assert "threshold_result" in below
    assert below["threshold_result"] != above["threshold_result"]


def test_snapshot_threshold_is_absent_when_none_was_asked():
    q = qmod.MeasurementQuestion(kind="distance", tolerance_m=0.5)
    ev = qmod.Evidence(n_supporting_views=6, max_ray_separation_deg=30.0,
                       view_support_basis="triangulated_observations",
                       endpoints_observed=True, endpoints_within_coverage=True)
    assert refmod._snapshot(q, 9.0, 0.05, ev)["threshold_result"] is None


def _aggregate(target, added_rays, gain_deg, tmp_path):
    """Run the **real** ``refine()`` and read back what it aggregated.

    This helper used to reimplement the engine's aggregation loop and assert
    against the copy. That is why 422 tests passed while the production branch
    raised ``NameError: name 'rec' is not defined`` the moment a refinement
    actually recovered a frame: the test reproduced the intended algorithm
    instead of executing the one that ships. A test that contains its own copy
    of the logic can only ever confirm that the copy is self-consistent.

    Only image I/O, registration and the local fit are controlled here, so no
    video or GPU is needed; the orchestration and aggregation being tested are
    the engine's own.
    """
    # Endpoint 0 is well supported (6 views, 40 deg); endpoint 1 is the weak
    # one (3 views, 12 deg). `target` selects which gets the recovered frame.
    views = {0: [1, 2, 3, 4, 5, 6], 1: [1, 2, 3]}
    seps = {0: 40.0, 1: 12.0}

    def which(p):
        return 0 if float(np.asarray(p, float)[0]) < 2.5 else 1

    def for_points(*_a, **_kw):
        return qmod.Evidence(
            n_supporting_views=3, max_ray_separation_deg=12.0,
            view_support_basis="triangulated_observations",
            endpoints_observed=True, endpoints_within_coverage=True,
            scale_source="gps", scale_sigma_rel=0.01)

    ev = SimpleNamespace(
        K=np.eye(3), rotations=np.stack([np.eye(3)] * 2),
        centres=np.array([[-1.0, 0, -10], [1.0, 0, -10]]),
        frame_indices=[0, 2], _camera_of_frame={0: 0, 2: 1},
        has_lineage=True, for_points=for_points,
        measured_ray_separation_deg=lambda p: seps[which(p)],
        within_coverage=lambda p: True,
        observations_of=lambda p: {
            "frame_index": np.array(views[which(p)], np.int32),
            "uv": np.zeros((len(views[which(p)]), 2))})

    eng = refmod.RefinementEngine(ev, tmp_path)
    # `target` is chosen by the engine as the weaker endpoint; drive it by
    # making only that endpoint's anchors available.
    eng.candidates = lambda p: [refmod.Candidate(1, 1.0) for _ in range(added_rays)]
    eng._endpoint_anchors = lambda p: [(0, 0, [0, 0])]
    eng._pnp_anchors = lambda f: []
    eng._register = lambda *a: (np.eye(3), np.array([5.0, 0, -10]), 30, 1.0,
                                None, None, np.array([0]), np.array([[0, 0]]))
    eng._locate = lambda *a, **kw: np.array([-0.5, 0])
    eng._local_bundle = lambda *a: {
        "point": np.array([0.1, 0, 0]), "sigma": 0.02, "n_cameras": 3,
        "n_points": 10, "n_observations": 30,
        "rmse_before": 1.0, "rmse_after": 0.5}

    run = eng.refine(
        qmod.MeasurementQuestion("distance", tolerance_m=0.5),
        [[0.0, 0, 0], [5.0, 0, 0]],
        value_fn=refmod.measurement_value_fn("distance", [0.05, 0.05]),
        budget_frames=added_rays, max_decode=added_rays, provenances=[0, 0])
    return run


def test_a_successful_recovery_completes_through_the_real_method(tmp_path):
    """The branch that crashed: refine() reaching its post-recovery path.

    `NameError: name 'rec' is not defined` -- the engine's evidence object is
    `self.ev`, and the aggregation referred to a name from the API router I
    had been reading. Nothing reached this branch until a refinement actually
    recovered a frame.
    """
    run = _aggregate(target=1, added_rays=1, gain_deg=15.0, tmp_path=tmp_path)
    assert len(run.added_frames) == 1
    assert run.after is not None
    assert run.after["value"] is not None


def test_support_is_the_minimum_over_endpoints_not_a_total(tmp_path):
    """The review's counterexample: 3 + 4 must not report 7."""
    run = _aggregate(target=1, added_rays=1, gain_deg=15.0, tmp_path=tmp_path)
    # The weaker endpoint has 3 views before the recovery; the stronger has 6.
    # Whatever the recovery adds, the reported figure is a minimum over both
    # ends and can never exceed the stronger endpoint's own count.
    assert run.after["n_supporting_views"] <= 6
    assert run.before["n_supporting_views"] <= run.after["n_supporting_views"]


def test_refined_endpoints_are_recorded_by_the_real_method(tmp_path):
    run = _aggregate(target=1, added_rays=1, gain_deg=15.0, tmp_path=tmp_path)
    assert len(run.refined_points_enu) == 2
    d = run.to_dict()
    assert len(d["refined_points_enu"]) == 2


def test_refined_points_are_carried_in_the_run_record():
    run = refmod.RefinementRun(question_kind="distance", tolerance_m=0.2,
                               budget_frames=4)
    run.refined_points_enu = [np.array([1.0, 2.0, 3.0]), np.array([4.0, 5.0, 6.0])]
    d = run.to_dict()
    assert d["refined_points_enu"] == [[1.0, 2.0, 3.0], [4.0, 5.0, 6.0]]
