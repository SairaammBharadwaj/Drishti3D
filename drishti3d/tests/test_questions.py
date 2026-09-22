"""Acceptance rules for measurement questions (plan F2 / F5).

These tests pin the decisions that make the Tolerance Lens honest rather than
decorative. Each one corresponds to a way a measurement product can quietly
overstate what it knows.
"""
from __future__ import annotations

import numpy as np
import pytest

from drishti_recon import questions as q
from drishti_recon import uncertainty as unc


def good_evidence(**kw):
    base = dict(n_supporting_views=7, max_ray_separation_deg=15.0,
                view_support_basis="triangulated_observations",
                touches_inferred=False, endpoints_observed=True,
                endpoints_within_coverage=True, dynamic_contamination=False,
                scale_source="gps", scale_sigma_rel=0.005)
    base.update(kw)
    return q.Evidence(**base)


#: The regime the test profile is fitted for. `evaluate` now checks a profile
#: against the capture it is being applied to, so a test that wants a
#: calibrated verdict has to say which capture it is measuring.
REGIME = "uav_oblique/gps"


def usable_profile(n=40, k95=1.6):
    """A profile that has been through the whole lifecycle.

    `validated=True` used to be settable directly at construction. It is now
    derived from the state, and reaching RELEASED requires a held-out
    evaluation on missions disjoint from the fitting set and a named approver
    -- so a test that wants a usable profile has to build one that could
    actually exist.
    """
    return (q.CalibrationProfile(regime=REGIME, n_samples=n,
                                 conformal_factors={95: k95},
                                 coverage_observed={95: 0.95},
                                 source="test", fit_missions=("fit_a",))
            .evaluated(coverage_heldout={95: 0.94}, eval_missions=("eval_b",),
                       reference_sigma_m=0.002)
            .released(approved_by="test"))


# --- the central rule ------------------------------------------------------ #
def test_uncalibrated_system_cannot_claim_meets_requirement():
    """A narrow predicted interval is not a calibrated one.

    Without a validated profile the interval is a sensitivity estimate, so the
    strongest honest verdict is ESTIMATED_ONLY even though 0.118 m sits well
    inside the 0.20 m asked for.
    """
    v = q.evaluate(q.MeasurementQuestion("distance", tolerance_m=0.20),
                   value=3.42, sigma=0.06, evidence=good_evidence())
    assert v.status is q.Status.ESTIMATED_ONLY
    assert q.Reason.INTERVAL_NOT_CALIBRATED in v.reasons
    assert v.interval_basis == "uncalibrated_sensitivity"
    assert not v.status.exportable_as_accepted


def test_calibrated_profile_permits_acceptance():
    v = q.evaluate(q.MeasurementQuestion("distance", tolerance_m=0.20),
                   value=3.42, sigma=0.06, evidence=good_evidence(),
                   profile=usable_profile(), regime=REGIME)
    assert v.status is q.Status.MEETS_REQUIREMENT
    assert v.interval_basis == "calibrated"
    assert v.interval_half_width == pytest.approx(0.096)
    assert v.status.exportable_as_accepted


def test_small_calibration_sample_blocks_acceptance():
    """Ten samples cannot substantiate a 95% interval."""
    p = q.CalibrationProfile(regime="uav_oblique/gps", n_samples=10,
                             conformal_factors={95: 1.6},
                             state=q.CalibrationState.RELEASED)
    v = q.evaluate(q.MeasurementQuestion("distance", tolerance_m=0.20),
                   value=3.42, sigma=0.06, evidence=good_evidence(), profile=p)
    assert v.status is q.Status.ESTIMATED_ONLY
    assert q.Reason.CALIBRATION_SAMPLE_TOO_SMALL in v.reasons


# --- tolerance is the only thing a tolerance change may move --------------- #
def test_tightening_tolerance_changes_status_not_the_measurement():
    ev, prof = good_evidence(), usable_profile()
    loose = q.evaluate(q.MeasurementQuestion("distance", tolerance_m=0.20),
                       value=3.42, sigma=0.06, evidence=ev, profile=prof,
                       regime=REGIME)
    tight = q.evaluate(q.MeasurementQuestion("distance", tolerance_m=0.05),
                       value=3.42, sigma=0.06, evidence=ev, profile=prof,
                       regime=REGIME)
    assert loose.status is q.Status.MEETS_REQUIREMENT
    assert tight.status is q.Status.NEEDS_REFINEMENT
    assert q.Reason.INTERVAL_EXCEEDS_TOLERANCE in tight.reasons
    # The number and its interval are properties of the model, not of the ask.
    assert loose.interval_half_width == tight.interval_half_width
    assert loose.detail["value"] == tight.detail["value"]


# --- refusals name the missing evidence ------------------------------------ #
@pytest.mark.parametrize("kw,reason", [
    (dict(endpoints_observed=False), q.Reason.ENDPOINT_NOT_OBSERVED),
    (dict(endpoints_within_coverage=False),
     q.Reason.OUTSIDE_ESTABLISHED_COVERAGE),
    (dict(touches_inferred=True), q.Reason.TOUCHES_INFERRED_GEOMETRY),
])
def test_hard_refusals_are_not_observable(kw, reason):
    v = q.evaluate(q.MeasurementQuestion("distance", tolerance_m=0.20),
                   value=3.42, sigma=0.06, evidence=good_evidence(**kw),
                   profile=usable_profile())
    assert v.status is q.Status.NOT_OBSERVABLE
    assert reason in v.reasons
    assert v.dominant_limitation == reason.value


def test_infinite_sigma_is_not_observable():
    v = q.evaluate(q.MeasurementQuestion("distance", tolerance_m=0.20),
                   value=3.42, sigma=float("inf"), evidence=good_evidence(),
                   profile=usable_profile())
    assert v.status is q.Status.NOT_OBSERVABLE
    assert q.Reason.UNCERTAINTY_UNDEFINED in v.reasons


def test_low_parallax_blocks_acceptance_even_with_many_views():
    """Fifty views along one direction are still one direction."""
    v = q.evaluate(q.MeasurementQuestion("distance", tolerance_m=0.20),
                   value=3.42, sigma=0.06,
                   evidence=good_evidence(n_supporting_views=50,
                                          max_ray_separation_deg=0.4),
                   profile=usable_profile())
    assert v.status is q.Status.ESTIMATED_ONLY
    assert q.Reason.DEGENERATE_VIEW_GEOMETRY in v.reasons
    assert v.dominant_limitation == q.Reason.DEGENERATE_VIEW_GEOMETRY.value


def test_missing_scale_source_blocks_acceptance():
    v = q.evaluate(q.MeasurementQuestion("distance", tolerance_m=0.20),
                   value=3.42, sigma=0.06,
                   evidence=good_evidence(scale_source="none",
                                          scale_sigma_rel=float("nan")),
                   profile=usable_profile())
    assert v.status is q.Status.ESTIMATED_ONLY
    assert q.Reason.SCALE_NOT_ESTABLISHED in v.reasons


def test_scale_uncertainty_dominating_is_reported_separately():
    """A 5% scale error on a 40 m span is 2 m; local refinement cannot fix it."""
    v = q.evaluate(q.MeasurementQuestion("distance", tolerance_m=0.20),
                   value=40.0, sigma=0.05,
                   evidence=good_evidence(scale_sigma_rel=0.05),
                   profile=usable_profile())
    assert q.Reason.SCALE_UNCERTAINTY_DOMINATES in v.reasons
    assert v.status is not q.Status.MEETS_REQUIREMENT
    guidance = {g["reason"]: g["next_action"] for g in v.to_dict()["guidance"]}
    assert "scale source" in guidance[
        q.Reason.SCALE_UNCERTAINTY_DOMINATES.value]


# --- threshold queries keep the interval ----------------------------------- #
@pytest.mark.parametrize("value,half,expect", [
    (3.42, 0.10, "above"),        # whole interval clears 3.20
    (3.00, 0.10, "below"),        # whole interval below
    (3.25, 0.10, "indeterminate"),  # straddles 3.20
])
def test_threshold_uses_the_interval_not_the_point_estimate(value, half, expect):
    sigma = half / 1.96
    v = q.evaluate(q.MeasurementQuestion("distance", tolerance_m=1.0,
                                         threshold_m=3.20),
                   value=value, sigma=sigma, evidence=good_evidence(),
                   profile=None)
    assert v.threshold_result == expect


def test_at_most_threshold_direction():
    v = q.evaluate(q.MeasurementQuestion("height", tolerance_m=1.0,
                                         threshold_m=10.0,
                                         threshold_direction="at_most"),
                   value=8.0, sigma=0.2, evidence=good_evidence())
    assert v.threshold_result == "below"


# --- serialisation --------------------------------------------------------- #
def test_verdict_dict_is_json_safe_with_infinite_interval():
    import json
    v = q.evaluate(q.MeasurementQuestion("distance", tolerance_m=0.2),
                   value=3.0, sigma=float("inf"), evidence=good_evidence())
    d = v.to_dict()
    assert d["interval_half_width"] is None
    assert d["interval_half_width_is_infinite"] is True
    json.dumps(d)          # must not raise: inf is not valid JSON


def test_profile_from_calibration_result_respects_sample_floor():
    rng = np.random.default_rng(0)
    sig = np.full(8, 0.1)
    err = np.abs(rng.normal(0, 0.1, 8))
    p = q.CalibrationProfile.from_calibration(
        unc.calibrate(err, sig), regime="test", source="unit test")
    assert p.n_samples == 8
    assert not p.usable()


def test_frustum_derived_view_support_cannot_license_acceptance():
    """An upper bound on parallax is not evidence that the parallax exists.

    Until per-point observation lineage is persisted, view support can only be
    inferred from camera frustums, which counts cameras that may never have
    contributed an observation to the point. The verdict says so by name rather
    than quietly accepting.
    """
    v = q.evaluate(q.MeasurementQuestion("distance", tolerance_m=0.20),
                   value=3.42, sigma=0.06,
                   evidence=good_evidence(
                       view_support_basis="frustum_upper_bound"),
                   profile=usable_profile())
    assert v.status is q.Status.ESTIMATED_ONLY
    assert q.Reason.VIEW_GEOMETRY_UNVERIFIED in v.reasons


# --- a fit through coplanar cameras cannot license acceptance (DEC-036) ---- #
def test_degenerate_alignment_blocks_acceptance():
    """Measured: 5.7 cm vertical alignment RMSE, 1.25 m of actual error."""
    v = q.evaluate(q.MeasurementQuestion("distance", tolerance_m=0.20),
                   value=3.42, sigma=0.06,
                   evidence=good_evidence(alignment_degenerate=True),
                   profile=usable_profile(), regime=REGIME)
    assert v.status is not q.Status.MEETS_REQUIREMENT
    assert q.Reason.ALIGNMENT_DEGENERATE in v.reasons


def test_a_sound_alignment_still_accepts():
    v = q.evaluate(q.MeasurementQuestion("distance", tolerance_m=0.20),
                   value=3.42, sigma=0.06,
                   evidence=good_evidence(alignment_degenerate=False),
                   profile=usable_profile(), regime=REGIME)
    assert v.status is q.Status.MEETS_REQUIREMENT


def test_degeneracy_is_the_reported_limitation_over_calibration():
    """It has to outrank the softer reasons, or nobody acts on it."""
    v = q.evaluate(q.MeasurementQuestion("distance", tolerance_m=0.20),
                   value=3.42, sigma=0.06,
                   evidence=good_evidence(alignment_degenerate=True),
                   profile=None)
    assert v.dominant_limitation == "alignment_degenerate"
    codes = [g["reason"] for g in v.to_dict()["guidance"]]
    assert "alignment_degenerate" in codes
