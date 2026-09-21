"""C10: calibration must be a release process, not a sample counter.

The review's finding: `CalibrationProfile.from_calibration` marked a profile
validated from `n >= MIN_CALIBRATION_SAMPLES`, so reaching twenty measurements
was equivalent to being independently validated -- and regime matching was left
entirely to callers.
"""
import pytest

from drishti_recon import questions as q
from drishti_recon import uncertainty as unc


def _fitted(n=40, missions=("agz_dense_pass",)):
    res = unc.CalibrationResult(
        n=n, conformal_factors={95: 1.6, 80: 1.2}, scale_factor=1.1,
        coverage_conformal={95: 0.95, 80: 0.80}, coverage={95: 0.7})
    return q.CalibrationProfile.from_calibration(
        res, regime="uav_oblique/gps", source="test", fit_missions=missions)


def test_a_fresh_fit_is_not_validated_however_many_samples():
    p = _fitted(n=10_000)
    assert p.state == q.CalibrationState.FITTED
    assert p.validated is False
    assert p.usable() is False


def test_evaluation_requires_disjoint_missions():
    p = _fitted(missions=("m1", "m2"))
    with pytest.raises(ValueError, match="overlap"):
        p.evaluated(coverage_heldout={95: 0.93}, eval_missions=("m2", "m3"))


def test_evaluation_requires_some_held_out_data():
    with pytest.raises(ValueError, match="at least one mission"):
        _fitted().evaluated(coverage_heldout={95: 0.93}, eval_missions=())


def test_evaluated_is_still_not_usable():
    p = _fitted().evaluated(coverage_heldout={95: 0.93}, eval_missions=("m9",))
    assert p.state == q.CalibrationState.EVALUATED
    assert p.usable() is False


def test_release_requires_evaluation_first():
    with pytest.raises(ValueError, match="only an evaluated profile"):
        _fitted().released(approved_by="someone")


def test_release_requires_a_named_approver():
    p = _fitted().evaluated(coverage_heldout={95: 0.93}, eval_missions=("m9",))
    with pytest.raises(ValueError, match="named approver"):
        p.released(approved_by="")


def test_a_released_profile_is_usable_and_records_its_lineage():
    p = (_fitted(missions=("m1",))
         .evaluated(coverage_heldout={95: 0.93}, eval_missions=("m9",),
                    reference_sigma_m=0.002)
         .released(approved_by="naveen"))
    assert p.usable() is True
    assert p.validated is True
    assert p.fit_missions == ("m1",)
    assert p.eval_missions == ("m9",)
    assert p.coverage_heldout == {95: 0.93}
    assert p.reference_sigma_m == 0.002
    assert p.approved_by == "naveen"


def test_held_out_coverage_is_kept_apart_from_in_sample_coverage():
    """In-sample coverage is always flattering and must not stand in for it."""
    p = _fitted().evaluated(coverage_heldout={95: 0.88}, eval_missions=("m9",))
    assert p.coverage_observed[95] == 0.95      # what the fit saw
    assert p.coverage_heldout[95] == 0.88       # what it achieved elsewhere


def test_regime_mismatch_is_refused():
    p = (_fitted().evaluated(coverage_heldout={95: 0.93}, eval_missions=("m9",))
         .released(approved_by="x"))
    assert p.applies_to("uav_oblique/gps") is True
    assert p.applies_to("uav_nadir/rtk") is False
    assert p.applies_to("") is False


def test_unsupported_interval_level_is_refused_not_substituted():
    """Answering a 99% request with a 95%-shaped factor is a silent lie."""
    p = (_fitted().evaluated(coverage_heldout={95: 0.93}, eval_missions=("m9",))
         .released(approved_by="x"))
    assert p.interval(0.05, level=95) == pytest.approx(0.08)
    assert p.interval(0.05, level=80) == pytest.approx(0.06)
    assert p.interval(0.05, level=99) == float("inf")


# --------------------------------------------------------------------------- #
# Regime matching is enforced, not delegated
# --------------------------------------------------------------------------- #
def _released(regime="uav_oblique/gps"):
    res = unc.CalibrationResult(
        n=40, conformal_factors={95: 1.6}, scale_factor=1.1,
        coverage_conformal={95: 0.95}, coverage={95: 0.7})
    return (q.CalibrationProfile.from_calibration(
                res, regime=regime, source="test", fit_missions=("m1",))
            .evaluated(coverage_heldout={95: 0.94}, eval_missions=("m9",))
            .released(approved_by="test"))


def _good_evidence():
    return q.Evidence(
        n_supporting_views=8, max_ray_separation_deg=35.0,
        view_support_basis="triangulated_observations",
        endpoints_observed=True, endpoints_within_coverage=True,
        scale_source="gps", scale_sigma_rel=1e-5)


def _verdict(profile, regime):
    return q.evaluate(q.MeasurementQuestion(kind="distance", tolerance_m=1.0),
                      value=10.0, sigma=0.01, evidence=_good_evidence(),
                      profile=profile, regime=regime)


def test_a_matching_regime_can_reach_meets_requirement():
    v = _verdict(_released(), "uav_oblique/gps")
    assert v.status == q.Status.MEETS_REQUIREMENT
    assert v.interval_basis == "calibrated"


def test_a_mismatched_regime_is_refused_by_evaluate():
    """Not left to the caller: a profile cannot know where it is used."""
    v = _verdict(_released("uav_oblique/gps"), "uav_nadir/rtk")
    assert v.status != q.Status.MEETS_REQUIREMENT
    assert "calibration_regime_mismatch" in v.to_dict()["reasons"]
    assert v.interval_basis == "uncalibrated_sensitivity"


def test_an_unknown_regime_cannot_be_shown_to_match():
    v = _verdict(_released(), None)
    assert v.status != q.Status.MEETS_REQUIREMENT
    assert "calibration_regime_mismatch" in v.to_dict()["reasons"]


def test_regime_mismatch_has_operator_guidance():
    v = _verdict(_released(), "other/regime")
    codes = [g["reason"] for g in v.to_dict()["guidance"]]
    assert "calibration_regime_mismatch" in codes


def test_no_profile_still_reports_not_calibrated_not_mismatch():
    v = _verdict(None, "uav_oblique/gps")
    reasons = v.to_dict()["reasons"]
    assert "interval_not_calibrated" in reasons
    assert "calibration_regime_mismatch" not in reasons
