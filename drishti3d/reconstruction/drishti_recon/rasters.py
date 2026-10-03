"""Raster products from the observed cloud: DSM, DTM, orthophoto, sigma, land cover.

The cloud's honesty rules carry over into raster form:

* Only observed points (``OBSERVED_HIGH_CONFIDENCE``, ``OBSERVED_LOW_CONFIDENCE``)
  go in. AI-assisted, corroborated, dynamic and unobserved points never do,
  and the inferred hole fill lives in its own file and is not read here.
* A cell without an observed point is NoData. Nothing is interpolated into a
  product. The one place gaps are filled -- terrain under buildings, which is
  needed to decide what stands on it -- stays internal and is never written.
* The cell size comes from the data: the smallest size on a fixed ladder at
  which at least 75% of the surveyed footprint holds an observed point
  (:func:`choose_resolution`). A grid finer than the points is mostly holes;
  the six showcase missions need 0.25 m (UseGeo) to 2 m (AGZ's facades).
* Heights are WGS84 ellipsoidal, as in the LAS export. They are not heights
  above sea level.
* Land cover is rule-based: a ground filter, height above that ground,
  greenness and roughness. None of the reference LiDAR available to the
  project is classified, so it has not been validated against labelled truth.

:func:`build_products` writes, beside the other artifacts:

=================  ===========================================================
``dsm.tif``        top surface: the highest observed point in each cell
``dtm.tif``        bare earth: the lowest observed point in cells the ground
                   filter keeps; NoData under buildings and trees
``ortho.tif``      colour of the highest point in each cell, empty cells
                   masked. A point-cloud orthophoto, not camera-projected
``sigma.tif``      mean worst-axis 1-sigma of the cell's points (uncalibrated,
                   like the cloud's)
``landcover.tif``  ASPRS codes 1 unclassified, 2 ground, 5 high vegetation,
                   6 building; 0 is NoData
``rasters.npz``    the same grids, for the API
``rasters.json``   cell size, coverage, CRS, vertical reference, class shares
``*_preview.png``  small images for the workspace
=================  ===========================================================
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from scipy import ndimage

from .provenance import Provenance

OBSERVED = (int(Provenance.OBSERVED_HIGH_CONFIDENCE),
            int(Provenance.OBSERVED_LOW_CONFIDENCE))
NODATA = -9999.0
#: Candidate cell sizes, metres. Coarse enough at the top that a sparse cloud
#: still gets a usable map; fine enough at the bottom for a dense survey.
RES_LADDER = (0.1, 0.15, 0.25, 0.35, 0.5, 0.75, 1.0, 1.5, 2.0)
#: ASPRS LAS classification codes used here.
UNCLASSIFIED, GROUND, HIGH_VEGETATION, BUILDING = 1, 2, 5, 6
VERTICAL_REFERENCE = "WGS84 ellipsoidal height, metres; not above sea level"


# --------------------------------------------------------------------- grid
@dataclass(frozen=True)
class Grid:
    """North-up grid: ``x0`` is the west edge, ``y1`` the north edge."""
    x0: float
    y1: float
    res: float
    h: int
    w: int

    @classmethod
    def covering(cls, xy: np.ndarray, res: float) -> "Grid":
        """The grid, aligned to multiples of ``res``, that holds every point."""
        lo, hi = xy.min(axis=0), xy.max(axis=0)
        x0 = np.floor(lo[0] / res) * res
        y1 = np.ceil(hi[1] / res) * res
        w = int(np.floor((hi[0] - x0) / res)) + 1
        h = int(np.floor((y1 - lo[1]) / res)) + 1
        return cls(float(x0), float(y1), float(res), h, w)

    def cell(self, xy: np.ndarray):
        """Row, column and in-grid mask of each point. Floors, never truncates."""
        xy = np.asarray(xy, float).reshape(-1, 2)
        col = np.floor((xy[:, 0] - self.x0) / self.res).astype(np.int64)
        row = np.floor((self.y1 - xy[:, 1]) / self.res).astype(np.int64)
        inside = (row >= 0) & (row < self.h) & (col >= 0) & (col < self.w)
        return row, col, inside

    def sample(self, grid: np.ndarray, xy: np.ndarray) -> np.ndarray:
        """Grid values at points; NaN outside the grid."""
        row, col, inside = self.cell(xy)
        out = np.full(len(row), np.nan)
        out[inside] = grid[row[inside], col[inside]]
        return out

    def centres(self):
        x = self.x0 + (np.arange(self.w) + 0.5) * self.res
        y = self.y1 - (np.arange(self.h) + 0.5) * self.res
        return np.meshgrid(x, y)

    def to_dict(self) -> dict:
        return {"x0": self.x0, "y1": self.y1, "res": self.res,
                "height": self.h, "width": self.w}


def _occupied_cells(xy: np.ndarray, res: float, origin: np.ndarray) -> int:
    c = np.floor((xy - origin) / res).astype(np.int64)
    return int(np.unique(c[:, 1] * (int(c[:, 0].max()) + 1) + c[:, 0]).size)


def choose_resolution(xy: np.ndarray, *, target: float = 0.75,
                      footprint_m: float = 5.0, ladder=RES_LADDER):
    """Smallest cell size at which ``target`` of the footprint holds a point.

    The footprint is the set of ``footprint_m`` cells with any point in them;
    coverage at a candidate size is its occupied cells over the cells that
    footprint would hold. Edge cells of the footprint are only partly
    surveyed, so this reads a little low. Returns ``(res, coverage)``; if no
    size on the ladder reaches the target, the coarsest, with its coverage.
    """
    xy = np.asarray(xy, float).reshape(-1, 2)
    origin = xy.min(axis=0)
    footprint = _occupied_cells(xy, footprint_m, origin)
    coverage = 0.0
    for res in ladder:
        coverage = _occupied_cells(xy, res, origin) / (footprint * (footprint_m / res) ** 2)
        if coverage >= target:
            return float(res), float(coverage)
    return float(ladder[-1]), float(coverage)


# --------------------------------------------------------------- rasterise
def rasterize(xyz, colors, sigma, provenance, res: float) -> dict:
    """Per-cell surfaces from the observed points.

    ``dsm`` is the highest point, ``zmin`` the lowest, ``zmean`` the mean (the
    unbiased surface for volumes: the highest point is biased upward by
    noise), ``rgb`` the colour of the highest point, ``sigma`` the mean point
    sigma, ``count`` the number of points. The highest point is chosen by a
    sort, not by "last write wins" fancy indexing, whose order NumPy does not
    guarantee.
    """
    keep = np.isin(np.asarray(provenance), OBSERVED)
    P = np.asarray(xyz, float)[keep]
    if not len(P):
        raise ValueError("no observed points to rasterise")
    C = np.asarray(colors, np.uint8).reshape(-1, 3)[keep]
    S = (np.full(len(P), np.nan) if sigma is None
         else np.asarray(sigma, float)[keep])
    grid = Grid.covering(P[:, :2], res)
    row, col, _ = grid.cell(P[:, :2])
    idx = row * grid.w + col
    n = grid.h * grid.w

    count = np.bincount(idx, minlength=n)
    zmean = np.full(n, np.nan, np.float32)
    have = count > 0
    zmean[have] = (np.bincount(idx, weights=P[:, 2], minlength=n)[have]
                   / count[have])

    order = np.lexsort((P[:, 2], idx))          # by cell, then by height
    sidx = idx[order]
    first = np.r_[True, sidx[1:] != sidx[:-1]]
    last = np.r_[sidx[1:] != sidx[:-1], True]
    dsm = np.full(n, np.nan, np.float32)
    dsm[sidx[last]] = P[order[last], 2]
    zmin = np.full(n, np.nan, np.float32)
    zmin[sidx[first]] = P[order[first], 2]
    rgb = np.zeros((n, 3), np.uint8)
    rgb[sidx[last]] = C[order[last]]

    ok = np.isfinite(S)
    s_sum = np.bincount(idx[ok], weights=S[ok], minlength=n)
    s_cnt = np.bincount(idx[ok], minlength=n)
    sig = np.full(n, np.nan, np.float32)
    sig[s_cnt > 0] = s_sum[s_cnt > 0] / s_cnt[s_cnt > 0]

    shape = (grid.h, grid.w)
    return {"grid": grid, "dsm": dsm.reshape(shape), "zmin": zmin.reshape(shape),
            "zmean": zmean.reshape(shape), "rgb": rgb.reshape(grid.h, grid.w, 3),
            "sigma": sig.reshape(shape), "count": count.reshape(shape).astype(np.int32)}


# ------------------------------------------------------------- ground / DTM
def ground_filter(zmin: np.ndarray, res: float, *, max_window_m: float = 40.0,
                  slope: float = 0.15, dh0: float = 0.3, dh_max: float = 2.5):
    """Progressive morphological filter (Zhang et al. 2003) on the lowest points.

    Opens the lowest-point surface with windows of 3, 5, 9, 17, ... cells. A
    cell is non-ground once its lowest point stands more than ``dh_k`` above
    the opened surface, with ``dh_k = dh0 + slope * (w_k - w_{k-1}) * res``
    capped at ``dh_max``: on terrain of gradient ``slope``, an opening of
    half-width ``r`` drops by about ``slope * r``, which is what the threshold
    allows. Buildings wider than ``max_window_m`` survive as ground, so it
    must exceed the largest roof; 40 m covers ordinary blocks, not
    warehouses. Empty cells are never ground.
    """
    have = np.isfinite(zmin)
    if not have.any():
        return have
    # Holes are filled high so they can never pull the opened surface down.
    z = np.where(have, zmin, np.nanmax(zmin)).astype(np.float64)
    nonground = np.zeros(zmin.shape, bool)
    surface, prev, k = z, 1, 0
    while True:
        size = 2 * 2 ** k + 1
        if size * res > max_window_m and k > 0:
            break
        opened = ndimage.grey_opening(surface, size=(size, size))
        dh = dh0 if k == 0 else min(dh0 + slope * (size - prev) * res, dh_max)
        nonground |= (z - opened) > dh
        surface, prev, k = opened, size, k + 1
    return have & ~nonground


def _fill_nearest(grid: np.ndarray) -> np.ndarray:
    """Nearest-cell fill. Internal: never written into a product."""
    bad = ~np.isfinite(grid)
    if not bad.any() or bad.all():
        return grid
    _, (r, c) = ndimage.distance_transform_edt(bad, return_indices=True)
    return grid[r, c]


def _local_std(v: np.ndarray, size: int = 3) -> np.ndarray:
    """Standard deviation over a size x size window, ignoring NaN, vectorised."""
    m = np.isfinite(v).astype(float)
    x = np.where(m > 0, v, 0.0).astype(float)
    n = ndimage.uniform_filter(m, size)
    with np.errstate(invalid="ignore", divide="ignore"):
        mean = ndimage.uniform_filter(x, size) / n
        var = ndimage.uniform_filter(x * x, size) / n - mean ** 2
    return np.sqrt(np.clip(var, 0, None))


def classify(dsm, ground, rgb, *, dtm=None, min_height: float = 2.0,
             exg_thresh: float = 0.05, rough_thresh: float = 0.75):
    """Rule-based land cover per cell, in ASPRS codes.

    * ground (2): cells the ground filter keeps;
    * building (6) / high vegetation (5): other cells standing more than
      ``min_height`` above the terrain, split by colour and texture --
      vegetation if the top point is green (excess-green index over
      ``exg_thresh``) or the surface is rough (3x3 height std over
      ``rough_thresh``), building otherwise;
    * unclassified (1): anything else with data (low objects, cars, walls);
    * 0: no data.

    The terrain under elevated cells is the ground filled in from the nearest
    ground cell -- an inference used only for this decision. Roads are not
    separated from other ground; that needs image semantics.
    Returns ``(classes, height_above_ground, terrain)``; ``terrain`` is the
    filled ground and must stay internal.
    """
    dtm = np.where(ground, dsm if dtm is None else dtm, np.nan)
    terrain = _fill_nearest(dtm)
    hag = dsm - terrain
    have = np.isfinite(dsm)
    f = rgb.astype(float) / 255.0
    exg = (2 * f[..., 1] - f[..., 0] - f[..., 2]) / (f.sum(-1) + 1e-6)
    rough = _local_std(dsm, 3)
    cls = np.zeros(dsm.shape, np.uint8)
    cls[have] = UNCLASSIFIED
    cls[have & ground] = GROUND
    elevated = have & ~ground & (hag > min_height)
    veg = elevated & ((exg > exg_thresh) | (rough > rough_thresh))
    cls[veg] = HIGH_VEGETATION
    cls[elevated & ~veg] = BUILDING
    return cls, hag.astype(np.float32), terrain.astype(np.float32)


def classify_points(xyz, grid: Grid, cls, terrain, *, ground_tol: float = 0.5,
                    min_height: float = 2.0) -> np.ndarray:
    """ASPRS class per point, for the LAS export.

    A point within ``ground_tol`` of the terrain is ground; one standing more
    than ``min_height`` above it takes its cell's class when that is building
    or vegetation (so the ground under a tree stays ground); the rest are
    unclassified. Callers set non-observed points to unclassified.
    """
    xyz = np.asarray(xyz, float)
    t = grid.sample(terrain, xyz[:, :2])
    c = grid.sample(cls.astype(float), xyz[:, :2])
    out = np.full(len(xyz), UNCLASSIFIED, np.uint8)
    dz = xyz[:, 2] - t
    out[np.isfinite(dz) & (np.abs(dz) <= ground_tol)] = GROUND
    tall = np.isfinite(dz) & (dz > min_height)
    out[tall & (c == BUILDING)] = BUILDING
    out[tall & (c == HIGH_VEGETATION)] = HIGH_VEGETATION
    return out


# ------------------------------------------------------------------ writing
_CLASS_COLOURS = {0: (0, 0, 0, 0), UNCLASSIFIED: (160, 160, 160, 255),
                  GROUND: (196, 164, 112, 255), HIGH_VEGETATION: (46, 139, 87, 255),
                  BUILDING: (200, 70, 60, 255)}


def write_geotiff(path, arr, grid: Grid, epsg: int, *, description: str,
                  mask=None, colormap=None, nodata=NODATA) -> str:
    """One GeoTIFF: float grids with NoData, uint8 bands with a mask or palette."""
    import rasterio
    from rasterio.transform import from_origin
    a = np.asarray(arr)
    bands = a[None] if a.ndim == 2 else np.moveaxis(a, -1, 0)
    is_float = bands.dtype.kind == "f"
    if is_float:
        bands = np.where(np.isfinite(bands), bands, nodata).astype("float32")
    profile = dict(driver="GTiff", height=grid.h, width=grid.w,
                   count=bands.shape[0], dtype=bands.dtype,
                   crs=f"EPSG:{epsg}",
                   transform=from_origin(grid.x0, grid.y1, grid.res, grid.res),
                   compress="deflate", tiled=True, blockxsize=256, blockysize=256)
    if is_float:
        profile["nodata"] = nodata
    elif colormap is not None:
        profile["nodata"] = 0
    elif bands.shape[0] == 3:
        profile["photometric"] = "RGB"
    with rasterio.open(path, "w", **profile) as dst:
        dst.write(bands)
        dst.update_tags(DESCRIPTION=description, VERTICAL_REFERENCE=VERTICAL_REFERENCE,
                        SOURCE="Drishti3D observed points only; empty cells are not interpolated")
        if mask is not None:
            dst.write_mask(np.where(mask, 255, 0).astype("uint8"))
        if colormap is not None:
            dst.write_colormap(1, colormap)
    return str(path)


def _hillshade(z: np.ndarray, res: float, azimuth=315.0, altitude=45.0):
    """Shaded relief in [0, 1]; NaN where there is no height."""
    zz = _fill_nearest(z)
    gy, gx = np.gradient(zz, res)
    slope = np.arctan(np.hypot(gx, gy))
    aspect = np.arctan2(-gx, gy)
    az, alt = np.radians(azimuth), np.radians(altitude)
    shade = (np.sin(alt) * np.cos(slope)
             + np.cos(alt) * np.sin(slope) * np.cos(az - aspect))
    return np.where(np.isfinite(z), np.clip(shade, 0, 1), np.nan)


def _write_preview(path, rgba: np.ndarray, max_px: int = 1024) -> str:
    from PIL import Image
    img = Image.fromarray(rgba, "RGBA")
    scale = max_px / max(img.size)
    if scale < 1:
        img = img.resize((max(1, int(img.width * scale)), max(1, int(img.height * scale))),
                         Image.Resampling.NEAREST)
    img.save(path, optimize=True)
    return str(path)


def _relief_rgba(z, res):
    """Hillshade tinted by height, transparent where empty."""
    shade = _hillshade(z, res)
    have = np.isfinite(z)
    lo, hi = (np.nanpercentile(z, 2), np.nanpercentile(z, 98)) if have.any() else (0, 1)
    t = np.clip((np.nan_to_num(z, nan=lo) - lo) / max(hi - lo, 1e-6), 0, 1)
    tint = np.stack([0.35 + 0.65 * t, 0.55 + 0.25 * t, 0.85 - 0.55 * t], -1)
    rgb = (np.nan_to_num(shade)[..., None] * 0.75 + 0.25) * tint
    out = np.zeros(z.shape + (4,), np.uint8)
    out[..., :3] = (np.clip(rgb, 0, 1) * 255).astype(np.uint8)
    out[..., 3] = np.where(have, 255, 0)
    return out


def build_products(utm_xyz, colors, sigma, provenance, epsg: int, out_dir,
                   *, res: float | None = None, max_window_m: float = 40.0) -> dict:
    """Compute and write every raster product; return paths and point classes.

    ``utm_xyz`` are the cloud's points in the UTM zone ``epsg``, heights
    ellipsoidal (``exports.enu_to_utm``). Returns ``{"artifacts": {...},
    "point_classes": uint8 array, "summary": dict}``; GeoTIFFs are skipped,
    with a note in the summary, if rasterio is not installed.
    """
    out_dir = Path(out_dir)
    prov = np.asarray(provenance)
    observed = np.isin(prov, OBSERVED)
    xyz = np.asarray(utm_xyz, float)
    coverage = None
    if res is None:
        res, coverage = choose_resolution(xyz[observed, :2])
    r = rasterize(xyz, colors, sigma, prov, res)
    grid = r["grid"]
    ground = ground_filter(r["zmin"], res, max_window_m=max_window_m)
    dtm = np.where(ground, r["zmin"], np.nan).astype(np.float32)
    cls, hag, terrain = classify(r["dsm"], ground, r["rgb"], dtm=dtm)
    point_classes = classify_points(xyz, grid, cls, terrain)
    point_classes[~observed] = UNCLASSIFIED

    have = cls > 0
    shares = {name: float((cls == code).sum() / max(have.sum(), 1))
              for name, code in [("ground", GROUND), ("building", BUILDING),
                                 ("high_vegetation", HIGH_VEGETATION),
                                 ("unclassified", UNCLASSIFIED)]}
    summary = {
        "cell_size_m": res,
        "footprint_coverage": coverage,
        "cells_with_data": int(have.sum()),
        "crs": f"EPSG:{epsg}",
        "grid": grid.to_dict(),
        "vertical_reference": VERTICAL_REFERENCE,
        "class_shares": shares,
        "class_codes": {"0": "no data", "1": "unclassified", "2": "ground",
                        "5": "high vegetation", "6": "building"},
        "method": {
            "points": "observed only (provenance 0-1); empty cells are NoData",
            "dtm": f"progressive morphological filter (Zhang et al. 2003) on the "
                   f"lowest point per cell, windows up to {max_window_m:g} m",
            "landcover": "rule-based: ground filter, height above ground > 2 m, "
                         "excess-green index, 3x3 roughness. Not validated "
                         "against labelled truth.",
            "ortho": "colour of the highest point per cell; not camera-projected",
        },
    }

    arts = {}
    np.savez_compressed(out_dir / "rasters.npz", dsm=r["dsm"], zmean=r["zmean"],
                        dtm=dtm, sigma=r["sigma"], landcover=cls,
                        count=r["count"], epsg=np.array([epsg]),
                        grid=np.array([grid.x0, grid.y1, grid.res, grid.h, grid.w]))
    arts["rasters_npz"] = str(out_dir / "rasters.npz")
    try:
        import rasterio  # noqa: F401
        arts["dsm_tif"] = write_geotiff(out_dir / "dsm.tif", r["dsm"], grid, epsg,
                                        description="DSM: highest observed point per cell")
        arts["dtm_tif"] = write_geotiff(out_dir / "dtm.tif", dtm, grid, epsg,
                                        description="DTM: lowest observed point in ground "
                                                    "cells; NoData under buildings and trees")
        arts["ortho_tif"] = write_geotiff(out_dir / "ortho.tif", r["rgb"], grid, epsg,
                                          description="Point-cloud orthophoto: colour of the "
                                                      "highest point per cell",
                                          mask=r["count"] > 0)
        arts["sigma_tif"] = write_geotiff(out_dir / "sigma.tif", r["sigma"], grid, epsg,
                                          description="Mean worst-axis 1-sigma of the cell's "
                                                      "points, metres; uncalibrated")
        arts["landcover_tif"] = write_geotiff(out_dir / "landcover.tif", cls, grid, epsg,
                                              description="Rule-based land cover, ASPRS codes",
                                              colormap=_CLASS_COLOURS)
    except ImportError:
        summary["geotiff"] = "skipped: rasterio not installed (pip install rasterio)"

    try:
        ortho = np.zeros(cls.shape + (4,), np.uint8)
        ortho[..., :3] = r["rgb"]
        ortho[..., 3] = np.where(r["count"] > 0, 255, 0)
        lc = np.array([_CLASS_COLOURS.get(i, (0, 0, 0, 0)) for i in range(256)], np.uint8)[cls]
        arts["ortho_preview"] = _write_preview(out_dir / "ortho_preview.png", ortho)
        arts["dsm_preview"] = _write_preview(out_dir / "dsm_preview.png",
                                             _relief_rgba(r["dsm"], res))
        arts["dtm_preview"] = _write_preview(out_dir / "dtm_preview.png",
                                             _relief_rgba(dtm, res))
        arts["landcover_preview"] = _write_preview(out_dir / "landcover_preview.png", lc)
    except ImportError:
        summary["previews"] = "skipped: Pillow not installed"

    (out_dir / "rasters.json").write_text(json.dumps(summary, indent=2))
    arts["rasters_json"] = str(out_dir / "rasters.json")
    return {"artifacts": arts, "point_classes": point_classes, "summary": summary}
