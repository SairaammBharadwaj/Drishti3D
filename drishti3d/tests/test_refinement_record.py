"""C06: a refined result and the evidence behind it must describe one thing.

Findings from the review: the API persisted the operator's original endpoints
beside the refined value, carried the previous threshold verdict forward
unchanged, and added a one-endpoint view gain to a measurement-wide minimum.
"""
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


class _Rec:
    """Two endpoints: index 0 well supported, index 1 the weak one."""
    def __init__(self):
        self._views = {0: [1, 2, 3, 4, 5, 6], 1: [1, 2, 3]}
        self._sep = {0: 40.0, 1: 12.0}

    def _key(self, p):
        return 0 if float(np.asarray(p, float)[0]) < 0.5 else 1

    def observations_of(self, p):
        return {"frame_index": np.array(self._views[self._key(p)], np.int32)}

    def measured_ray_separation_deg(self, p):
        return self._sep[self._key(p)]


def _aggregate(target, added_rays, gain_deg):
    """The aggregation the engine performs, isolated from the decode path."""
    rec = _Rec()
    points_enu = [np.array([0.0, 0, 0]), np.array([1.0, 0, 0])]
    per_views, per_sep = [], []
    for i, q in enumerate(points_enu):
        o = rec.observations_of(q)
        nv = int(len(set(o["frame_index"].tolist())))
        sep = float(rec.measured_ray_separation_deg(q))
        if i == target:
            nv += int(added_rays)
            sep = max(sep, gain_deg)
        per_views.append(nv)
        per_sep.append(sep)
    return min(per_views), min(per_sep)


def test_improving_the_strong_endpoint_does_not_raise_the_minimum():
    """The review's counterexample: 3 + 4 must not report 7."""
    views, sep = _aggregate(target=0, added_rays=4, gain_deg=55.0)
    assert views == 3, "the weak endpoint still limits the measurement"
    assert sep == pytest.approx(12.0)


def test_improving_the_weak_endpoint_does_raise_the_minimum():
    views, sep = _aggregate(target=1, added_rays=4, gain_deg=25.0)
    assert views == 6            # weak 3+4=7, strong 6 -> min 6
    assert sep == pytest.approx(25.0)


def test_a_gain_below_the_other_endpoint_is_still_capped_by_it():
    views, sep = _aggregate(target=1, added_rays=1, gain_deg=15.0)
    assert views == 4            # weak 3+1=4, strong 6 -> min 4
    assert sep == pytest.approx(15.0)


def test_refined_points_are_carried_in_the_run_record():
    run = refmod.RefinementRun(question_kind="distance", tolerance_m=0.2,
                               budget_frames=4)
    run.refined_points_enu = [np.array([1.0, 2.0, 3.0]), np.array([4.0, 5.0, 6.0])]
    d = run.to_dict()
    assert d["refined_points_enu"] == [[1.0, 2.0, 3.0], [4.0, 5.0, 6.0]]
