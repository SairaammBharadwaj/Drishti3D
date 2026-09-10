"""Does the predicted uncertainty match the error actually observed?

A covariance model is worthless unless its intervals hold empirically, so these
tests are built as Monte-Carlo experiments: perturb the image measurements by a
*known* pixel noise many times, re-triangulate, and compare the spread of the
resulting 3D points against what the model predicted. A model that merely
produces plausible-looking numbers fails here.
"""
from __future__ import annotations

import numpy as np
import pytest

cv2 = pytest.importorskip("cv2")

from drishti_recon import bundle, uncertainty as unc     # noqa: E402


def _rig(n_cams=6, spread=1.0, depth=30.0, seed=0):
    """Cameras on an arc looking at a point cloud ``depth`` metres away."""
    rng = np.random.default_rng(seed)
    K = np.array([[800.0, 0, 480.0], [0, 800.0, 270.0], [0, 0, 1.0]])
    rvecs, tvecs = [], []
    for i in range(n_cams):
        a = spread * np.pi * (i / max(n_cams - 1, 1) - 0.5) * 0.5
        C = np.array([depth * np.sin(a), -depth * np.cos(a), 0.0])
        fwd = -C / np.linalg.norm(C)
        right = np.cross(fwd, [0, 0, 1.0])
        right /= np.linalg.norm(right)
        R = np.stack([right, np.cross(fwd, right), fwd])
        rvecs.append(cv2.Rodrigues(R)[0].ravel())
        tvecs.append((-R @ C).ravel())
    return np.array(rvecs), np.array(tvecs), K, rng


def _triangulate(uv, cam_idx, rvecs, tvecs, K):
    """Least-squares 3D point from its observations (Gauss-Newton on rays)."""
    A = np.zeros((3, 3))
    b = np.zeros(3)
    for m, c in enumerate(cam_idx):
        R = cv2.Rodrigues(rvecs[c])[0]
        C = -R.T @ tvecs[c]
        d = R.T @ np.array([(uv[m, 0] - K[0, 2]) / K[0, 0],
                            (uv[m, 1] - K[1, 2]) / K[1, 1], 1.0])
        d /= np.linalg.norm(d)
        P = np.eye(3) - np.outer(d, d)      # projector onto the ray's normal plane
        A += P
        b += P @ C
    return np.linalg.solve(A, b)


def _monte_carlo(X_true, rvecs, tvecs, K, sigma_px, trials=400, seed=1):
    """Empirical scatter of the triangulated point under known pixel noise."""
    rng = np.random.default_rng(seed)
    cam_idx = np.arange(len(rvecs))
    uv0 = bundle.project(np.tile(X_true, (len(cam_idx), 1)),
                         rvecs[cam_idx], tvecs[cam_idx],
                         np.full(len(cam_idx), K[0, 0]),
                         np.full(len(cam_idx), K[1, 1]), K[0, 2], K[1, 2])
    out = []
    for _ in range(trials):
        uv = uv0 + rng.normal(0, sigma_px, uv0.shape)
        out.append(_triangulate(uv, cam_idx, rvecs, tvecs, K))
    return np.array(out), uv0, cam_idx


def test_predicted_sigma_matches_monte_carlo_scatter():
    """The headline claim: predicted 1-sigma equals the real spread."""
    rvecs, tvecs, K, _ = _rig()
    X_true = np.array([0.5, 0.0, 1.0])
    sigma_px = 0.5
    samples, uv0, cam_idx = _monte_carlo(X_true, rvecs, tvecs, K, sigma_px)

    u = unc.point_covariances(X_true[None, :], cam_idx,
                              np.zeros(len(cam_idx), int), uv0,
                              rvecs, tvecs, K, sigma_px=sigma_px)
    assert u.observable[0]

    empirical_cov = np.cov((samples - X_true).T)
    predicted = u.cov[0]

    # Compare the predicted and observed standard deviation along each principal
    # axis of the predicted covariance -- the direction-resolved check, which a
    # single scalar comparison could hide.
    evals, evecs = np.linalg.eigh(predicted)
    for k in range(3):
        axis = evecs[:, k]
        pred_sd = np.sqrt(max(evals[k], 0.0))
        obs_sd = np.sqrt(axis @ empirical_cov @ axis)
        assert 0.6 < obs_sd / pred_sd < 1.6, (
            f"axis {k}: predicted {pred_sd:.4f} m vs observed {obs_sd:.4f} m")


def test_sigma_scales_linearly_with_pixel_noise():
    """Doubling the assumed image noise must double the predicted sigma."""
    rvecs, tvecs, K, _ = _rig()
    X = np.array([[0.0, 0.0, 0.0]])
    ci = np.arange(len(rvecs))
    uv = np.zeros((len(ci), 2))
    a = unc.point_covariances(X, ci, np.zeros(len(ci), int), uv, rvecs, tvecs, K,
                              sigma_px=0.5)
    b = unc.point_covariances(X, ci, np.zeros(len(ci), int), uv, rvecs, tvecs, K,
                              sigma_px=1.0)
    assert np.isclose(b.sigma[0] / a.sigma[0], 2.0, rtol=1e-6)


def test_narrow_baseline_is_far_more_uncertain_than_wide():
    """Weak parallax must produce a visibly larger, anisotropic uncertainty."""
    X = np.array([[0.0, 0.0, 0.0]])
    wide_r, wide_t, K, _ = _rig(spread=1.0)
    narrow_r, narrow_t, _, _ = _rig(spread=0.02)
    ci = np.arange(len(wide_r))
    uv = np.zeros((len(ci), 2))
    wide = unc.point_covariances(X, ci, np.zeros(len(ci), int), uv,
                                 wide_r, wide_t, K)
    narrow = unc.point_covariances(X, ci, np.zeros(len(ci), int), uv,
                                   narrow_r, narrow_t, K)
    assert narrow.sigma_major[0] > 10 * wide.sigma_major[0]
    # ...and the weakly-constrained case must be reported as anisotropic,
    # because the error is concentrated along the viewing direction.
    assert narrow.condition[0] > wide.condition[0]


def test_single_observation_point_is_not_observable():
    """One ray cannot fix a depth, and must not be given a finite uncertainty."""
    rvecs, tvecs, K, _ = _rig()
    X = np.array([[0.0, 0.0, 0.0]])
    u = unc.point_covariances(X, np.array([0]), np.array([0]),
                              np.zeros((1, 2)), rvecs, tvecs, K)
    assert not u.observable[0]
    assert not np.isfinite(u.sigma[0])


def test_distance_uncertainty_is_dominated_by_scale_at_long_range():
    """Scale error grows with the measurement; endpoint error does not."""
    cov = np.eye(3) * (0.01 ** 2)          # 1 cm endpoints
    a = np.zeros(3)
    near = np.array([1.0, 0, 0])
    far = np.array([100.0, 0, 0])
    _, s_near = unc.distance_uncertainty(a, near, cov, cov, scale_sigma_rel=0.002)
    d_far, s_far = unc.distance_uncertainty(a, far, cov, cov, scale_sigma_rel=0.002)
    assert s_far > 10 * s_near
    # at 100 m a 0.2% scale error is 0.2 m and swamps the 1 cm endpoints
    assert abs(s_far - 0.2) < 0.02, s_far


def test_distance_uncertainty_ignores_perpendicular_error():
    """Error across the measurement direction barely changes its length."""
    along = np.diag([0.1 ** 2, 1e-8, 1e-8])
    across = np.diag([1e-8, 0.1 ** 2, 1e-8])
    a, b = np.zeros(3), np.array([10.0, 0, 0])
    _, s_along = unc.distance_uncertainty(a, b, along, along)
    _, s_across = unc.distance_uncertainty(a, b, across, across)
    assert s_along > 50 * s_across


def test_non_observable_endpoint_makes_the_measurement_infinite():
    """A measurement resting on an unobservable point must not report a number."""
    a, b = np.zeros(3), np.array([5.0, 0, 0])
    _, s = unc.distance_uncertainty(a, b, np.full((3, 3), np.nan), np.eye(3) * 1e-4)
    assert not np.isfinite(s)


def test_area_uncertainty_scales_quadratically_with_scale_error():
    """Area goes as s^2, so a relative scale error contributes 2*A*sigma_s/s."""
    sq = np.array([[0, 0, 0], [10.0, 0, 0], [10.0, 10.0, 0], [0, 10.0, 0]])
    covs = [np.eye(3) * 1e-10] * 4        # negligible endpoint error
    A, s = unc.area_uncertainty(sq, covs, scale_sigma_rel=0.01)
    assert abs(A - 100.0) < 1e-6
    assert abs(s - 2 * 100.0 * 0.01) < 0.05, s


def test_calibration_detects_and_corrects_optimistic_sigmas():
    """A model understating error by 3x must be measured as such and fixed."""
    rng = np.random.default_rng(4)
    true_sigma = 0.30
    errors = rng.normal(0, true_sigma, 4000)
    claimed = np.full(4000, true_sigma / 3.0)      # 3x optimistic

    cal = unc.calibrate(errors, claimed)
    assert 2.5 < cal.scale_factor < 3.5, cal.scale_factor
    # raw intervals are far too narrow...
    assert cal.coverage[95] < 0.7
    # ...and calibrated ones hit their nominal level
    for level in (50, 80, 95):
        assert abs(cal.coverage_calibrated[level] - level / 100) < 0.06, (
            level, cal.coverage_calibrated[level])


def test_calibration_leaves_honest_sigmas_alone():
    rng = np.random.default_rng(5)
    s = 0.2
    cal = unc.calibrate(rng.normal(0, s, 4000), np.full(4000, s))
    assert 0.85 < cal.scale_factor < 1.15, cal.scale_factor


def test_requirement_gate_blocks_measurements_that_are_too_uncertain():
    ok, why = unc.meets_requirement(10.0, sigma=0.01, tolerance=0.05)
    assert ok and "within" in why
    bad, why2 = unc.meets_requirement(10.0, sigma=0.5, tolerance=0.05)
    assert not bad and "exceeds" in why2
    unobs, why3 = unc.meets_requirement(10.0, sigma=float("inf"), tolerance=1.0)
    assert not unobs and "not finite" in why3


def test_covariance_transforms_with_scale_squared():
    """Pushing through a similarity must scale variance by s^2."""
    cov = np.stack([np.diag([0.01, 0.02, 0.03])])
    R = cv2.Rodrigues(np.array([0.3, -0.2, 0.1]))[0]
    out = unc.transform_covariances(cov, 2.0, R)
    assert np.isclose(np.trace(out[0]), 4.0 * np.trace(cov[0]))
    # a similarity preserves symmetry and positive-definiteness
    assert np.allclose(out[0], out[0].T)
    assert (np.linalg.eigvalsh(out[0]) > 0).all()


# --------------------------------------------------------------------------- #
# Conformal (distribution-free) calibration
#
# A single Gaussian scale factor can only match one point of the distribution.
# Real measurement error has heavier tails than a normal — unmodelled distortion
# and pose error are systematic, not Gaussian — so the 95% level stays badly
# under-covered even after the median is fixed. These tests pin the behaviour
# that fixes it.
# --------------------------------------------------------------------------- #
def test_conformal_beats_gaussian_scaling_on_heavy_tails():
    """With a heavy-tailed error distribution, only the conformal factor works."""
    rng = np.random.default_rng(9)
    n = 3000
    sigmas = np.full(n, 0.1)
    # 90% well-behaved, 10% from a much wider component: the classic shape when
    # a subset of measurements is hit by a systematic effect.
    heavy = rng.normal(0, 0.1, n)
    tail = rng.normal(0, 0.8, n)
    pick = rng.random(n) < 0.10
    errors = np.where(pick, tail, heavy)

    cal = unc.calibrate(errors, sigmas)
    # the Gaussian rescale fixes the middle but misses the tail...
    assert abs(cal.coverage_calibrated[50] - 0.50) < 0.08
    assert cal.coverage_calibrated[95] < 0.93
    # ...while the conformal factors hit every level by construction
    for level in (50, 80, 95):
        assert abs(cal.coverage_conformal[level] - level / 100) < 0.03, (
            level, cal.coverage_conformal[level])


def test_conformal_factors_increase_with_level():
    rng = np.random.default_rng(10)
    k = unc.conformal_factors(rng.normal(0, 0.2, 500), np.full(500, 0.2))
    assert k[50] < k[80] < k[95]


def test_conformal_coverage_holds_on_held_out_data():
    """The honest test: fit the factor on one split, score the other."""
    rng = np.random.default_rng(11)
    n = 2000
    sigmas = rng.uniform(0.05, 0.5, n)
    errors = rng.standard_t(df=3, size=n) * sigmas * 0.7   # heavy-tailed
    fit, held = slice(0, n // 2), slice(n // 2, n)
    k = unc.conformal_factors(errors[fit], sigmas[fit])
    for level in (50, 80, 95):
        cov = float(np.mean(np.abs(errors[held]) <= k[level] * sigmas[held]))
        assert abs(cov - level / 100) < 0.06, (level, cov)


def test_calibration_result_interval_prefers_conformal():
    rng = np.random.default_rng(12)
    cal = unc.calibrate(rng.normal(0, 0.3, 400), np.full(400, 0.3))
    assert cal.conformal_factors, "conformal factors should be fitted"
    expected = cal.conformal_factors[95] * 0.3
    assert np.isclose(cal.interval(0.3, 95), expected)
    # an unobservable point has no usable interval
    assert not np.isfinite(cal.interval(float("inf"), 95))


def test_calibration_needs_enough_data_to_fit():
    """Too few samples must not silently produce a confident-looking factor."""
    cal = unc.calibrate(np.array([0.1, 0.2]), np.array([0.1, 0.1]))
    assert cal.n < 3
    assert cal.scale_factor == 1.0
    assert cal.conformal_factors == {}
