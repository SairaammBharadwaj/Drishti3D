"""Phase 6: multi-view verification of inferred geometry, and capture guidance.

The verification tests are built so that the *right answer differs between two
inputs that look identical to a single view*: a point placed on the true surface
and a point floating off it. A test that only fed correct points through would
pass on code that verified nothing.
"""
from __future__ import annotations

import numpy as np
import pytest

cv2 = pytest.importorskip("cv2")

from drishti_recon import capture, verify                 # noqa: E402
from drishti_recon.fusion import PointCloud               # noqa: E402
from drishti_recon.provenance import Provenance           # noqa: E402


class _Cam:
    def __init__(self, R, t):
        self.R = np.asarray(R, float)
        self.t = np.asarray(t, float).ravel()

    @property
    def center(self):
        return -self.R.T @ self.t


def _look_at(C, target):
    C = np.asarray(C, float)
    fwd = np.asarray(target, float) - C
    fwd /= np.linalg.norm(fwd)
    right = np.cross(fwd, [0, 0, 1.0])
    if np.linalg.norm(right) < 1e-8:
        right = np.cross(fwd, [0, 1.0, 0])
    right /= np.linalg.norm(right)
    R = np.stack([right, np.cross(fwd, right), fwd])
    return _Cam(R, -R @ C)


K = np.array([[500.0, 0, 320.0], [0, 500.0, 240.0], [0, 0, 1.0]])
IMG = (640, 480)


def _scene():
    """A ground plane observed by four cameras from above."""
    xs = np.arange(-10, 10, 0.25)
    ys = np.arange(-10, 10, 0.25)
    X, Y = np.meshgrid(xs, ys, indexing="ij")
    observed = np.stack([X.ravel(), Y.ravel(), np.zeros(X.size)], 1)
    colors = np.full((len(observed), 3), 120.0)
    cams = [_look_at(np.array([dx, dy, 25.0]), np.array([0.0, 0.0, 0.0]))
            for dx, dy in ((-6, -6), (6, -6), (6, 6), (-6, 6))]
    return observed, colors, cams


def test_inferred_points_on_the_surface_are_verified():
    observed, colors, cams = _scene()
    # Inferred points sitting on the true plane, offset from the observed grid
    # so they are not merely duplicates of it.
    inferred = np.stack([np.linspace(-5, 5, 60),
                         np.linspace(-4, 4, 60),
                         np.zeros(60)], 1)
    icols = np.full((60, 3), 120.0)
    res = verify.verify_inferred(inferred, icols, observed, colors, cams, K, IMG)
    assert res.verified.mean() > 0.8, res.summary()
    assert (res.n_views_agreeing[res.verified] >= 2).all()


def test_inferred_points_floating_off_the_surface_are_rejected():
    """The discriminating case: geometry a single view could not falsify."""
    observed, colors, cams = _scene()
    floating = np.stack([np.linspace(-5, 5, 60),
                         np.linspace(-4, 4, 60),
                         np.full(60, 8.0)], 1)      # 8 m above the ground
    icols = np.full((60, 3), 120.0)
    res = verify.verify_inferred(floating, icols, observed, colors, cams, K, IMG)
    assert res.verified.mean() < 0.2, res.summary()


def test_verification_separates_good_from_bad_in_one_call():
    observed, colors, cams = _scene()
    good = np.stack([np.linspace(-5, 5, 30), np.zeros(30), np.zeros(30)], 1)
    bad = np.stack([np.linspace(-5, 5, 30), np.zeros(30), np.full(30, 10.0)], 1)
    pts = np.vstack([good, bad])
    cols = np.full((60, 3), 120.0)
    res = verify.verify_inferred(pts, cols, observed, colors, cams, K, IMG)
    assert res.verified[:30].mean() > 0.7
    assert res.verified[30:].mean() < 0.3


def test_min_views_is_enforced():
    """Requiring more corroborating views must be strictly harder to satisfy."""
    observed, colors, cams = _scene()
    pts = np.stack([np.linspace(-5, 5, 40), np.zeros(40), np.zeros(40)], 1)
    cols = np.full((40, 3), 120.0)
    lax = verify.verify_inferred(pts, cols, observed, colors, cams, K, IMG,
                                 min_views=1)
    strict = verify.verify_inferred(pts, cols, observed, colors, cams, K, IMG,
                                    min_views=4)
    assert strict.verified.sum() <= lax.verified.sum()


def test_apply_verification_promotes_only_verified_points():
    """Promotion must change provenance and nothing else."""
    pts = np.zeros((6, 3))
    cloud = PointCloud(pts, np.zeros((6, 3), np.uint8), np.zeros(6),
                       np.array([0, 0, 2, 2, 2, 2]), None,
                       sigma=np.array([.1, .1, np.inf, np.inf, np.inf, np.inf]),
                       sigma_major=np.array([.1, .1, np.inf, np.inf, np.inf, np.inf]))
    inferred_mask = cloud.provenance == int(Provenance.AI_ASSISTED)
    res = verify.VerificationResult(
        verified=np.array([True, False, True, False]),
        n_views_agreeing=np.array([3, 0, 2, 1]),
        depth_residual=np.zeros(4), color_residual=np.zeros(4))
    before_sigma = cloud.sigma.copy()
    verify.apply_verification(cloud, res, inferred_mask)

    assert cloud.provenance[2] == int(Provenance.AI_GEOMETRICALLY_VERIFIED)
    assert cloud.provenance[4] == int(Provenance.AI_GEOMETRICALLY_VERIFIED)
    assert cloud.provenance[3] == int(Provenance.AI_ASSISTED)
    assert cloud.provenance[0] == int(Provenance.OBSERVED_HIGH_CONFIDENCE)
    # verification is not measurement: uncertainty is untouched
    assert np.array_equal(np.nan_to_num(cloud.sigma, posinf=-1),
                          np.nan_to_num(before_sigma, posinf=-1))


def test_verified_inferred_geometry_is_still_not_measurable():
    """Corroborated is not triangulated -- the whole point of the class."""
    assert not Provenance.AI_GEOMETRICALLY_VERIFIED.measurable
    assert not Provenance.AI_ASSISTED.measurable
    assert Provenance.OBSERVED_HIGH_CONFIDENCE.measurable


def test_verification_handles_empty_input():
    observed, colors, cams = _scene()
    res = verify.verify_inferred(np.zeros((0, 3)), None, observed, colors,
                                 cams, K, IMG)
    assert len(res.verified) == 0
    assert res.summary()["n_inferred"] == 0


# --------------------------------------------------------------------------- #
# capture assessment
# --------------------------------------------------------------------------- #
def test_good_capture_grades_well():
    a = capture.assess(
        recon_stats={"mean_tri_angle": 12.0, "registered_fraction": 1.0,
                     "mean_track_length": 6.0},
        coverage_summary={"fraction_explained": 0.55,
                          "measurable_surface_fraction": 0.95},
        uncertainty_summary={"sigma_major_m": {"median": 0.05}})
    assert a.grade in ("excellent", "good"), a.to_dict()
    assert a.score > 0.6


def test_low_parallax_capture_is_diagnosed_as_such():
    """The limiting factor must be named, not just a low score returned."""
    a = capture.assess(
        recon_stats={"mean_tri_angle": 1.2, "registered_fraction": 1.0,
                     "mean_track_length": 6.0},
        coverage_summary={"fraction_explained": 0.5,
                          "measurable_surface_fraction": 0.9})
    assert a.limiting_factor == "parallax"
    assert any("parallax" in m for m in a.messages)


def test_partial_registration_is_diagnosed():
    a = capture.assess(
        recon_stats={"mean_tri_angle": 11.0, "registered_fraction": 0.35,
                     "mean_track_length": 6.0},
        coverage_summary={"fraction_explained": 0.5,
                          "measurable_surface_fraction": 0.9})
    assert a.limiting_factor == "registration"


def test_requirement_gate_reports_when_accuracy_is_unreachable():
    a = capture.assess(
        recon_stats={"mean_tri_angle": 10.0, "registered_fraction": 1.0},
        uncertainty_summary={"sigma_major_m": {"median": 0.40}},
        required_sigma_m=0.05)
    assert a.meets_requirement is False
    assert any("exceeds the required" in m for m in a.messages)


def test_missing_inputs_are_not_scored_as_zero():
    """A factor we could not measure must not silently drag the score down."""
    partial = capture.assess(recon_stats={"mean_tri_angle": 12.0,
                                          "registered_fraction": 1.0})
    assert partial.score > 0.8, partial.to_dict()
    assert "coverage" not in partial.factors


def test_assess_with_no_data_says_so():
    a = capture.assess()
    assert a.grade == "unknown" and a.score == 0.0


# --------------------------------------------------------------------------- #
# recapture planning
# --------------------------------------------------------------------------- #
def test_plan_addresses_the_limiting_factor():
    a = capture.assess(
        recon_stats={"mean_tri_angle": 1.1, "registered_fraction": 1.0,
                     "mean_track_length": 6.0},
        coverage_summary={"fraction_explained": 0.5,
                          "measurable_surface_fraction": 0.9})
    plan = capture.plan_recapture(a)
    assert plan.actions
    joined = " ".join(plan.actions).lower()
    assert "orbit" in joined or "angle" in joined
    assert "parallax" in plan.expected_gain


def test_plan_separates_unfixable_problems_from_actions():
    """Telling someone to refly a sensor problem is worse than saying nothing."""

    class _M:
        accepted = False

    a = capture.assess(
        recon_stats={"mean_tri_angle": 12.0, "registered_fraction": 1.0,
                     "mean_track_length": 6.0},
        coverage_summary={"fraction_explained": 0.6,
                          "measurable_surface_fraction": 0.95},
        frame_metrics=[_M()] * 10)
    plan = capture.plan_recapture(a)
    assert plan.unfixable
    assert any("blur" in u or "exposure" in u for u in plan.unfixable)


def test_good_capture_gets_no_busywork():
    a = capture.assess(
        recon_stats={"mean_tri_angle": 14.0, "registered_fraction": 1.0,
                     "mean_track_length": 8.0},
        coverage_summary={"fraction_explained": 0.7,
                          "measurable_surface_fraction": 0.98})
    plan = capture.plan_recapture(a)
    assert not plan.actions
    assert "unlikely to help" in plan.expected_gain
