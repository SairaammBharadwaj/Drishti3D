"""WGS84/ECEF/ENU conversion and robust Sim(3) alignment."""
import numpy as np
from drishti_recon.geo import (ENUFrame, geodetic_to_ecef, ecef_to_geodetic,
                               umeyama_sim3, robust_sim3, Sim3)


def test_ecef_roundtrip():
    lat, lon, alt = 28.6139, 77.2090, 220.0
    ecef = geodetic_to_ecef(lat, lon, alt)
    back = ecef_to_geodetic(ecef)[0]
    assert abs(back[0] - lat) < 1e-6
    assert abs(back[1] - lon) < 1e-6
    assert abs(back[2] - alt) < 1e-3


def test_enu_origin_is_zero():
    f = ENUFrame(28.6139, 77.2090, 220.0)
    enu = f.geodetic_to_enu([28.6139], [77.2090], [220.0])
    assert np.allclose(enu[0], [0, 0, 0], atol=1e-6)


def test_enu_east_north_signs():
    f = ENUFrame(0.0, 0.0, 0.0)
    east = f.geodetic_to_enu([0.0], [0.001], [0.0])[0]   # +lon -> +east
    north = f.geodetic_to_enu([0.001], [0.0], [0.0])[0]  # +lat -> +north
    assert east[0] > 0 and abs(east[1]) < 1e-3
    assert north[1] > 0 and abs(north[0]) < 1e-3


def test_enu_roundtrip():
    f = ENUFrame(12.9716, 77.5946, 900.0)
    lat = [12.9716, 12.9720, 12.9700]
    lon = [77.5946, 77.5950, 77.5930]
    alt = [900, 905, 890]
    enu = f.geodetic_to_enu(lat, lon, alt)
    back = f.enu_to_geodetic(enu)
    assert np.allclose(back[:, 0], lat, atol=1e-6)
    assert np.allclose(back[:, 1], lon, atol=1e-6)
    assert np.allclose(back[:, 2], alt, atol=1e-2)


def test_umeyama_recovers_transform():
    rng = np.random.default_rng(1)
    src = rng.normal(0, 3, (30, 3))
    R, _ = np.linalg.qr(rng.normal(0, 1, (3, 3)))
    if np.linalg.det(R) < 0:
        R[:, 0] *= -1
    true = Sim3(1.7, R, np.array([2.0, -5.0, 3.0]))
    dst = true.apply(src)
    est = umeyama_sim3(src, dst)
    assert abs(est.scale - 1.7) < 1e-6
    assert np.allclose(est.apply(src), dst, atol=1e-6)


def test_robust_sim3_rejects_outliers():
    rng = np.random.default_rng(2)
    src = rng.normal(0, 5, (25, 3))
    R = np.eye(3)
    true = Sim3(2.0, R, np.array([1.0, 2.0, 3.0]))
    dst = true.apply(src) + rng.normal(0, 0.05, (25, 3))
    dst[:4] += 40  # gross outliers
    res = robust_sim3(src, dst, threshold=1.0)
    assert abs(res.transform.scale - 2.0) < 0.05
    assert res.n_inliers >= 20
    assert res.rmse < 0.5


def test_robust_sim3_requires_three_points():
    import pytest
    with pytest.raises(ValueError):
        robust_sim3(np.zeros((2, 3)), np.zeros((2, 3)))


# --------------------------------------------------------------------------- #
# Uncertainty-weighted alignment (roadmap P1)
#
# The acceptance experiment stated in the roadmap: under heteroscedastic GNSS,
# weighted alignment must beat unweighted alignment on *clean held-out* camera
# positions, and must report wider uncertainty when the geometry is degenerate.
# --------------------------------------------------------------------------- #
def _heteroscedastic_case(seed=7, n=40, good_sigma=0.25, bad_sigma=8.0,
                          bad_frac=0.3):
    """A true Sim(3) observed through GNSS fixes of two very different qualities."""
    rng = np.random.default_rng(seed)
    # A well-conditioned track: spread in all three axes.
    src = rng.normal(0, 6, (n, 3))
    ang = 0.7
    R = np.array([[np.cos(ang), -np.sin(ang), 0],
                  [np.sin(ang), np.cos(ang), 0],
                  [0, 0, 1.0]])
    true = Sim3(2.0, R, np.array([10.0, -4.0, 3.0]))
    clean = true.apply(src)                      # noise-free truth

    sigma = np.full(n, good_sigma)
    bad = rng.choice(n, int(bad_frac * n), replace=False)
    sigma[bad] = bad_sigma
    noisy = clean + rng.normal(0, 1, (n, 3)) * sigma[:, None]
    return src, clean, noisy, sigma, true


def _transform_error(model, src, clean):
    """RMS error of the fitted transform against the *noise-free* positions."""
    return float(np.sqrt(((model.apply(src) - clean) ** 2).sum(1).mean()))


def test_weighted_alignment_beats_unweighted_under_heteroscedastic_gps():
    src, clean, noisy, sigma, _ = _heteroscedastic_case()

    unweighted = robust_sim3(src, noisy, threshold=5.0)
    weighted = robust_sim3(src, noisy, sigma_h=sigma, sigma_v=sigma)

    err_u = _transform_error(unweighted.transform, src, clean)
    err_w = _transform_error(weighted.transform, src, clean)
    assert err_w < err_u, (
        f"weighting must help: unweighted {err_u:.3f} m vs weighted {err_w:.3f} m")


def test_stated_accuracy_actually_changes_the_solution():
    """Regression: `weights` was accepted and silently ignored."""
    src, _, noisy, sigma, _ = _heteroscedastic_case()
    flat = robust_sim3(src, noisy, sigma_h=np.full(len(sigma), 1.0),
                       sigma_v=np.full(len(sigma), 1.0))
    informed = robust_sim3(src, noisy, sigma_h=sigma, sigma_v=sigma)
    assert not np.isclose(flat.transform.scale, informed.transform.scale), \
        "per-point GNSS accuracy had no effect on the fitted scale"


def test_legacy_weights_are_honoured():
    """The old `weights = 1/accuracy` contract must still drive the fit."""
    src, clean, noisy, sigma, _ = _heteroscedastic_case()
    via_weights = robust_sim3(src, noisy, weights=1.0 / sigma)
    via_sigma = robust_sim3(src, noisy, sigma_h=sigma)
    assert np.isclose(via_weights.transform.scale, via_sigma.transform.scale,
                      rtol=1e-6)
    assert via_weights.conditioning["sigma_source"] == "weights_as_inverse_sigma"


def test_normalized_residual_is_calibrated_when_sigmas_are_honest():
    """Mahalanobis RMSE should sit near 1 when the stated sigmas are truthful."""
    src, _, noisy, sigma, _ = _heteroscedastic_case()
    honest = robust_sim3(src, noisy, sigma_h=sigma, sigma_v=sigma)
    assert honest.normalized_rmse is not None
    assert 0.3 < honest.normalized_rmse < 3.0, honest.normalized_rmse
    # ...and with truthful sigmas nearly every fix should be explainable.
    assert honest.n_inliers >= 0.8 * honest.n_total


def test_overclaimed_accuracy_shows_up_as_a_collapsed_consensus_set():
    """Sigmas far tighter than reality cannot be hidden by the fit.

    Note what this does *not* assert: that the normalised RMSE blows up. It is
    computed over inliers, and an over-tight sigma simply rejects everything that
    does not already fit, so the surviving residuals stay small by construction.
    The honest symptom of over-claimed precision is that almost nothing qualifies
    as an inlier.
    """
    src, _, noisy, sigma, _ = _heteroscedastic_case()
    honest = robust_sim3(src, noisy, sigma_h=sigma, sigma_v=sigma)
    optimistic = robust_sim3(src, noisy, sigma_h=np.full(len(sigma), 0.05),
                             sigma_v=np.full(len(sigma), 0.05))
    assert optimistic.n_inliers < 0.5 * honest.n_inliers, (
        f"{optimistic.n_inliers} vs {honest.n_inliers} inliers")


def test_collinear_trajectory_is_flagged_degenerate():
    """A straight flight line cannot constrain roll about that line."""
    rng = np.random.default_rng(3)
    t = np.linspace(0, 50, 30)
    src = np.stack([t, 0.001 * t, np.zeros_like(t)], 1)
    dst = src * 1.5 + np.array([3.0, 1.0, 2.0]) + rng.normal(0, 0.02, src.shape)
    res = robust_sim3(src, dst, sigma_h=np.full(30, 0.3))
    assert res.degenerate
    assert "collinear" in (res.degeneracy or "")


def test_well_conditioned_trajectory_is_not_flagged():
    src, _, noisy, sigma, _ = _heteroscedastic_case()
    res = robust_sim3(src, noisy, sigma_h=sigma, sigma_v=sigma)
    assert not res.degenerate, res.degeneracy


def test_scale_uncertainty_widens_for_a_shorter_track():
    """Scale is pinned by the trajectory's extent; a short track pins it less."""
    rng = np.random.default_rng(11)
    def fit(extent):
        src = rng.normal(0, extent, (30, 3))
        dst = Sim3(2.0, np.eye(3), np.zeros(3)).apply(src) + rng.normal(0, 0.3, (30, 3))
        return robust_sim3(src, dst, sigma_h=np.full(30, 0.3))
    long_track = fit(20.0)
    short_track = fit(2.0)
    assert short_track.scale_sigma > long_track.scale_sigma


def test_vertical_is_trusted_less_than_horizontal_by_default():
    """GNSS altitude is characteristically worse; the default must reflect that."""
    src, _, noisy, sigma, _ = _heteroscedastic_case()
    res = robust_sim3(src, noisy, sigma_h=sigma)      # sigma_v defaulted
    assert res.conditioning["median_sigma_v_m"] > res.conditioning["median_sigma_h_m"]


def test_umeyama_weighted_ignores_a_zero_weighted_outlier():
    """A correspondence given zero weight must not move the fit at all."""
    rng = np.random.default_rng(5)
    src = rng.normal(0, 4, (20, 3))
    true = Sim3(1.3, np.eye(3), np.array([1.0, 2.0, 3.0]))
    dst = true.apply(src)
    dst_bad = dst.copy()
    dst_bad[0] += 500.0
    w = np.ones(20)
    w[0] = 0.0
    est = umeyama_sim3(src, dst_bad, weights=w)
    assert abs(est.scale - 1.3) < 1e-6
    assert np.allclose(est.apply(src[1:]), dst[1:], atol=1e-6)
