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
