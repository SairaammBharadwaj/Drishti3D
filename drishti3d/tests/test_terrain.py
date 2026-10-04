"""Volume, profile, slope and line of sight on observed-only grids."""
import numpy as np
import pytest

from drishti_recon import rasters as R, terrain as T
from drishti_recon.provenance import Provenance

OBS = int(Provenance.OBSERVED_HIGH_CONFIDENCE)


def surfaces(res=0.25, hole=None, wall=None):
    """A 2% ramp with a cone (r 5 m, h 3 m: 78.54 m3) at (20, 20)."""
    x = np.arange(0, 40, res) + res / 2
    X, Y = np.meshgrid(x, x)
    Z = 100 + 0.02 * X
    r = np.hypot(X - 20, Y - 20)
    Z += np.clip(3 * (1 - r / 5), 0, None)
    if wall is not None:
        Z[(X > wall[0]) & (X < wall[0] + 1)] += wall[1]
    P = np.c_[X.ravel(), Y.ravel(), Z.ravel()]
    if hole is not None:
        P = P[~hole(P[:, 0], P[:, 1])]
    n = len(P)
    r = R.rasterize(P, np.full((n, 3), 128), np.full(n, 0.02), np.full(n, OBS), res)
    return T.Surfaces(r["grid"], r["dsm"], r["zmean"], r["sigma"], r["count"], 32643)


SQUARE = [(12, 12), (28, 12), (28, 28), (12, 28)]


def test_cone_volume_on_a_sloping_base():
    out = T.volume(surfaces(), SQUARE, base="edge")
    assert out["status"] == "ok"
    assert out["net_m3"] == pytest.approx(np.pi * 25 * 3 / 3, rel=0.03)
    assert out["fill_m3"] < 0.5
    assert out["coverage"] == 1.0
    assert out["sigma_m3"]["independent_cells"] < out["sigma_m3"]["fully_correlated_bound"]


def test_fixed_and_lowest_bases():
    s = surfaces()
    tri = [(18, 18), (22, 18), (20, 22)]
    lo = T.volume(s, tri, base="lowest")
    fx = T.volume(s, tri, base="fixed", base_z=lo["base"]["z"])
    assert fx["net_m3"] == pytest.approx(lo["net_m3"])
    with pytest.raises(ValueError):
        T.volume(s, tri, base="fixed")


def test_volume_refuses_a_mostly_unobserved_polygon():
    s = surfaces(hole=lambda x, y: (x > 12) & (x < 26))
    out = T.volume(s, SQUARE)
    assert out["status"] == "refused" and "observed" in out["reason"]


def test_partial_coverage_is_scaled_and_said():
    s = surfaces(hole=lambda x, y: (x > 27) & (x < 28) & (y > 12) & (y < 28))
    out = T.volume(s, SQUARE, base="lowest")
    assert out["status"] == "ok" and out["coverage"] < 1
    assert "not observed" in out["unobserved_note"]


def test_volume_uses_mean_not_max():
    rng = np.random.default_rng(0)
    res = 0.5
    x = rng.uniform(0, 20, (40000, 2))
    z = 10 + rng.normal(0, 0.1, len(x))          # flat, noisy
    P = np.c_[x, z]
    r = R.rasterize(P, np.full((len(P), 3), 0), None, np.full(len(P), OBS), res)
    s = T.Surfaces(r["grid"], r["dsm"], r["zmean"], r["sigma"], r["count"], 32643)
    out = T.volume(s, [(2, 2), (18, 2), (18, 18), (2, 18)], base="fixed", base_z=10.0)
    # The DSM would be ~0.15 m high everywhere: ~38 m3 of phantom volume.
    assert abs(out["net_m3"]) < 2.0


def test_profile_crosses_the_cone_and_reports_gaps():
    s = surfaces(hole=lambda x, y: (x > 30) & (x < 32))
    out = T.profile(s, (5, 20), (35, 20), step=0.25)
    assert out["status"] == "ok"
    assert out["max_z"] == pytest.approx(100 + 0.4 + 3, abs=0.15)
    assert out["gaps"] > 0
    assert any(p["z"] is None for p in out["samples"])
    bad = T.profile(surfaces(hole=lambda x, y: x > 10), (5, 20), (35, 20))
    assert bad["status"] == "refused"


def test_slope():
    s = surfaces()
    flat = T.slope(s, [(1, 1), (8, 1), (8, 8), (1, 8)])
    assert flat["mean_deg"] == pytest.approx(np.degrees(np.arctan(0.02)), abs=0.05)
    cone = T.slope(s, [(17, 17), (23, 17), (23, 23), (17, 23)])
    assert cone["median_deg"] == pytest.approx(np.degrees(np.arctan(3 / 5)), abs=2)


def test_line_of_sight_visible_blocked_unknown():
    s = surfaces(wall=(30, 10))
    assert T.line_of_sight(s, (2, 5), (10, 5))["result"] == "visible"
    blk = T.line_of_sight(s, (25, 5), (36, 5))
    assert blk["result"] == "blocked"
    assert 30 <= blk["obstruction"]["x"] <= 31.5
    gap = surfaces(hole=lambda x, y: (x > 6) & (x < 7))
    unk = T.line_of_sight(gap, (2, 5), (10, 5))
    assert unk["result"] == "unknown" and "unobserved" in unk["reason"]
    # A measured obstruction is decisive even if other cells are unobserved.
    both = surfaces(wall=(30, 10), hole=lambda x, y: (x > 27) & (x < 28))
    assert T.line_of_sight(both, (25, 5), (36, 5))["result"] == "blocked"


def test_los_refuses_an_unobserved_observer():
    s = surfaces(hole=lambda x, y: (x < 3) & (y < 8))
    out = T.line_of_sight(s, (1, 5), (10, 5))
    assert out["status"] == "refused"
    ok = T.line_of_sight(s, (1, 5, 101.7), (10, 5))
    assert ok["status"] == "ok"


def test_load_round_trips_rasters_npz(tmp_path):
    rng = np.random.default_rng(1)
    P = np.c_[rng.uniform(0, 50, (20000, 2)), np.full(20000, 7.0)]
    n = len(P)
    R.build_products(P, np.full((n, 3), 90), np.full(n, 0.03), np.full(n, OBS),
                     32643, tmp_path, res=1.0)
    s = T.Surfaces.load(tmp_path / "rasters.npz")
    assert s.epsg == 32643 and s.grid.res == 1.0
    assert np.nanmax(s.zmean) == pytest.approx(7.0)
