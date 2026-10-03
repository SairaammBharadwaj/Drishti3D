"""Raster products (drishti_recon.rasters) on a synthetic site with known answers.

The site: ground sloping 2% eastward at 500 m, a 20 x 10 m building 9 m tall,
a tree 6 m tall, a 3 m soil cone, 3 cm noise, an unsurveyed patch, and 5% of
points AI-assisted and planted 50 m up -- they must never reach a product.
"""
from __future__ import annotations

import numpy as np
import pytest

from drishti_recon import rasters as R
from drishti_recon.provenance import Provenance

AI = int(Provenance.AI_ASSISTED)


def site(n=300_000, seed=1):
    rng = np.random.default_rng(seed)
    x, y = rng.uniform(0, 100, n), rng.uniform(0, 100, n)
    hole = (x > 85) & (y > 85)                       # never surveyed
    x, y = x[~hole], y[~hole]
    n = len(x)
    ground = 500 + 0.02 * x
    z = ground.copy()
    bld = (x > 20) & (x < 40) & (y > 20) & (y < 30)
    z[bld] += 9
    tree = np.hypot(x - 70, y - 30) < 4
    z[tree] += 6 + rng.normal(0, 0.6, tree.sum())
    r = np.hypot(x - 70, y - 70)
    pile = r < 5
    z[pile] += 3 * (1 - r[pile] / 5)
    z += rng.normal(0, 0.03, n)
    C = np.tile([150, 140, 120], (n, 1))
    C[bld] = [200, 60, 60]
    C[tree] = [40, 150, 40]
    prov = np.zeros(n, np.uint8)
    ai = rng.random(n) < 0.05
    prov[ai] = AI
    z[ai] += 50                                      # would wreck any product
    return np.c_[x, y, z], C.astype(np.uint8), np.full(n, 0.05), prov, ground


def products(res=0.5):
    P, C, S, prov, _ = site()
    r = R.rasterize(P, C, S, prov, res)
    ground = R.ground_filter(r["zmin"], res)
    dtm = np.where(ground, r["zmin"], np.nan)
    cls, hag, terrain = R.classify(r["dsm"], dtm, r["rgb"])
    X, Y = r["grid"].centres()
    return r, ground, dtm, cls, hag, terrain, X, Y


def test_classes_and_heights_match_the_site():
    r, ground, dtm, cls, hag, _, X, Y = products()
    bld = (X > 21) & (X < 39) & (Y > 21) & (Y < 29)
    assert (cls[bld] == R.BUILDING).mean() > 0.95
    assert abs(np.nanmedian(hag[bld]) - 9) < 0.2
    assert (cls[np.hypot(X - 70, Y - 30) < 3] == R.HIGH_VEGETATION).mean() > 0.90
    open_ground = (X > 50) & (X < 60) & (Y > 45) & (Y < 60)
    assert (cls[open_ground] == R.GROUND).mean() > 0.95


def test_ai_assisted_points_never_reach_a_product():
    r, *_ = products()
    # The tallest real thing is the building's roof, < 500 + 2 + 9 + noise.
    assert np.nanmax(r["dsm"]) < 512
    assert np.nanmax(r["zmean"]) < 512


def test_unsurveyed_cells_stay_nodata_in_every_product():
    r, ground, dtm, cls, *_ , X, Y = products()
    hole = (X > 86) & (Y > 86)
    for grid in (r["dsm"], r["zmin"], r["zmean"], r["sigma"], dtm):
        assert np.isnan(grid[hole]).all()
    assert (cls[hole] == 0).all() and not ground[hole].any()


def test_dtm_is_the_ground_and_empty_under_the_building():
    r, ground, dtm, *_ , X, Y = products()
    open_ground = (X > 50) & (X < 60) & (Y > 45) & (Y < 60)
    truth = 500 + 0.02 * X
    assert np.nanmedian(np.abs(dtm[open_ground] - truth[open_ground])) < 0.05
    interior = (X > 22) & (X < 38) & (Y > 22) & (Y < 28)
    assert np.isnan(dtm[interior]).mean() > 0.95


def test_highest_point_wins_whatever_the_input_order():
    P, C, S, prov, _ = site(n=50_000)
    a = R.rasterize(P, C, S, prov, 0.5)
    rng = np.random.default_rng(7)
    o = rng.permutation(len(P))
    b = R.rasterize(P[o], C[o], S[o], prov[o], 0.5)
    assert np.array_equal(a["dsm"], b["dsm"], equal_nan=True)
    assert np.array_equal(a["rgb"], b["rgb"])
    # ...and it is the highest: an independent per-cell maximum agrees.
    keep = prov != AI
    row, col, _ = a["grid"].cell(P[keep, :2])
    top = np.full(a["dsm"].shape, -np.inf)
    np.maximum.at(top, (row, col), P[keep, 2])
    top[np.isinf(top)] = np.nan
    assert np.allclose(a["dsm"], top, equal_nan=True, atol=1e-4)


def test_resolution_is_where_most_of_the_footprint_has_a_point():
    # 4 points per square metre, uniform: a cell of side r is occupied with
    # probability 1 - exp(-4 r^2): 63% at 0.5 m, 89% at 0.75 m.
    rng = np.random.default_rng(2)
    xy = rng.uniform(0, 200, (160_000, 2))
    res, coverage = R.choose_resolution(xy)
    assert res == 0.75 and 0.8 < coverage < 0.95


def test_point_classes():
    r, ground, dtm, cls, hag, terrain, X, Y = products()
    grid = r["grid"]
    pts = np.array([[55.0, 50.0, 500 + 0.02 * 55],          # open ground
                    [30.0, 25.0, 500 + 0.02 * 30 + 9],      # roof
                    [70.0, 30.0, 500 + 0.02 * 70],          # ground under the tree
                    [70.0, 30.0, 500 + 0.02 * 70 + 6]])     # canopy
    got = R.classify_points(pts, grid, cls, terrain)
    assert got.tolist() == [R.GROUND, R.BUILDING, R.GROUND, R.HIGH_VEGETATION]


def test_geotiffs_carry_crs_nodata_mask_and_palette(tmp_path):
    rasterio = pytest.importorskip("rasterio")
    P, C, S, prov, _ = site(n=80_000)
    out = R.build_products(P, C, S, prov, 32644, tmp_path, res=1.0)
    arts = out["artifacts"]
    for key in ("dsm_tif", "dtm_tif", "ortho_tif", "sigma_tif", "landcover_tif",
                "rasters_npz", "rasters_json", "ortho_preview", "landcover_preview"):
        assert key in arts
    with rasterio.open(arts["dsm_tif"]) as d:
        assert d.crs.to_epsg() == 32644 and d.nodata == R.NODATA
        assert d.transform.a == 1.0 and d.transform.e == -1.0
        band = d.read(1)
        assert (band == R.NODATA).any() and np.isfinite(band).all()
        assert "ellipsoidal" in d.tags()["VERTICAL_REFERENCE"]
    with rasterio.open(arts["ortho_tif"]) as o:
        assert o.count == 3 and (o.read_masks(1) == 0).any()
    with rasterio.open(arts["landcover_tif"]) as lc:
        assert lc.colormap(1)[R.BUILDING][:3] == R._CLASS_COLOURS[R.BUILDING][:3]
    assert len(out["point_classes"]) == len(P)
    assert (out["point_classes"][prov == AI] == R.UNCLASSIFIED).all()
    assert out["summary"]["cell_size_m"] == 1.0


def test_cloth_filter_finds_the_same_ground():
    pytest.importorskip("CSF")
    P, C, S, prov, _ = site(n=150_000)
    r = R.rasterize(P, C, S, prov, 0.5)
    ground = R.ground_filter_csf(r["zmin"], r["grid"])
    dtm = np.where(ground, r["zmin"], np.nan)
    cls, hag, _ = R.classify(r["dsm"], dtm, r["rgb"])
    X, Y = r["grid"].centres()
    bld = (X > 21) & (X < 39) & (Y > 21) & (Y < 29)
    open_ground = (X > 50) & (X < 60) & (Y > 45) & (Y < 60)
    assert (cls[bld] == R.BUILDING).mean() > 0.95
    assert (cls[open_ground] == R.GROUND).mean() > 0.95
    assert np.isnan(dtm[bld]).mean() > 0.95


def test_canopy_over_visible_ground_is_not_ground():
    # One cell: its lowest point is ground, its top is a tree 6 m up.
    dsm = np.full((5, 5), 100.0); dsm[2, 2] = 106.0
    dtm = np.full((5, 5), 100.0)                     # the ground filter kept it
    rgb = np.full((5, 5, 3), 120, np.uint8); rgb[2, 2] = [40, 150, 40]
    cls, _, _ = R.classify(dsm, dtm, rgb)
    assert cls[2, 2] == R.HIGH_VEGETATION and cls[0, 0] == R.GROUND
