"""Fill reconstruction holes with a labelled, non-measurable surface.

Photogrammetry cannot triangulate open water: the surface moves between
frames, it mirrors the sky and the banks (so a match lands on a reflection,
metres below the real surface), and calm water has no texture to match at all.
The fused cloud is therefore correct to leave it empty -- but a model with a
river-shaped hole through it reads as broken.

The standard remedy in survey practice is hydro-flattening: a still water body
is level and sits at the height of its own shoreline, and the shoreline *was*
reconstructed. So each hole is filled with the smoothest surface (a membrane,
Laplace's equation) that meets the observed *ground* all the way round its rim
-- level when the shoreline is level, tilting with it when the terrain or the
reconstruction tilts. Buildings and trees on the bank are removed from the rim
first by a morphological opening, so a river through a city is not lifted to
rooftop height.

What this is not: an observation. Fill points are returned separately from
the cloud and never enter it, so no measurement, coverage figure, or accuracy
evaluation can touch them unless a caller deliberately merges them; they carry
their own provenance class (``INFERRED_FILL``), zero confidence and infinite
sigma. The per-hole record gives the spread of the ground around each rim: a
still water body has a near-constant shoreline, and a large spread says the
surface across that hole is an interpolation rather than a water level.

Where a hole is. A cell is only a hole if cameras actually looked at it: the
domain is the ground area inside at least two camera footprints (two, because
a single view cannot triangulate anything, so a one-view strip at the edge of
the survey is "outside", not "missed"). Empty cells inside that domain are
holes; empty cells outside it are simply not part of the survey.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
from scipy import ndimage

#: Block size of the coarse regional ground model the rim is checked against.
#: Wider than a city block's tallest building footprint.
DTM_BLOCK_M = 60.0
#: How far a rim cell may sit above the regional ground and still be taken as
#: bank. A shoreline wall or a low bank passes; a roof or a tree does not.
BANK_ABOVE_GROUND_M = 3.0
#: Low percentile of point heights inside an occupied cell -- the ground under
#: vegetation rather than the canopy on it.
CELL_GROUND_PCT = 20.0


@dataclass
class HoleFill:
    points: np.ndarray                     # (M,3) ENU metres
    hole_id: np.ndarray                    # (M,) int32, index into ``holes``
    holes: list = field(default_factory=list)
    cell_m: float = 0.0
    domain_cells: int = 0
    empty_cells: int = 0

    def summary(self) -> dict:
        area = self.cell_m ** 2
        return {
            "method": "membrane fill from rim ground (hydro-flattening when the rim is level)",
            "measurable": False,
            "cell_m": self.cell_m,
            "surveyed_area_m2": round(self.domain_cells * area, 1),
            "filled_area_m2": round(self.empty_cells * area, 1),
            "filled_fraction": (round(self.empty_cells / self.domain_cells, 4)
                                if self.domain_cells else 0.0),
            "n_holes": len(self.holes),
            "n_points": int(len(self.points)),
            "holes": self.holes,
        }


def auto_cell(points: np.ndarray, target_per_cell: float = 8.0) -> float:
    """A grid cell big enough that solid ground almost never reads as empty."""
    xy = np.asarray(points, float)[:, :2]
    lo, hi = np.percentile(xy, 1, axis=0), np.percentile(xy, 99, axis=0)
    area = max(float(np.prod(np.maximum(hi - lo, 1.0))), 1.0)
    density = len(xy) / area
    return float(np.clip(np.sqrt(target_per_cell / max(density, 1e-9)), 0.5, 5.0))


def _footprint(C, R, K, image_size, z_ground, max_range):
    """Ground-plane polygon of one camera's image, or None if it misses."""
    w, h = image_size
    Kinv = np.linalg.inv(K)
    corners = []
    for u, v in ((0, 0), (w, 0), (w, h), (0, h)):
        d = R.T @ (Kinv @ np.array([u, v, 1.0]))      # camera -> world ray
        if d[2] >= -1e-6:                            # at or above the horizon
            return None
        t = (z_ground - C[2]) / d[2]
        if t <= 0:
            return None
        p = C + t * d
        if np.hypot(*(p[:2] - C[:2])) > max_range:
            return None
        corners.append(p[:2])
    return np.array(corners)


def _raster_polygon(poly, x0, y0, cell, shape):
    """Boolean mask of grid cells whose centres lie inside a convex quad."""
    from matplotlib.path import Path
    ny, nx = shape
    lo = np.floor((poly.min(0) - [x0, y0]) / cell).astype(int)
    hi = np.ceil((poly.max(0) - [x0, y0]) / cell).astype(int)
    lo = np.clip(lo, 0, [nx, ny]); hi = np.clip(hi, 0, [nx, ny])
    out = np.zeros(shape, bool)
    if (hi <= lo).any():
        return out
    gx, gy = np.meshgrid(np.arange(lo[0], hi[0]), np.arange(lo[1], hi[1]))
    centres = np.c_[x0 + (gx.ravel() + 0.5) * cell, y0 + (gy.ravel() + 0.5) * cell]
    inside = Path(poly).contains_points(centres).reshape(gx.shape)
    out[lo[1]:hi[1], lo[0]:hi[0]] = inside
    return out


def _regional_ground(P, x0, y0, cell, shape):
    """Coarse ground surface on the fine grid: low block heights, towers removed.

    Each ``DTM_BLOCK_M`` block takes the 5th percentile of its point heights.
    A block entirely covered by one roof still reads as roof, so a grey
    opening over the block grid removes isolated high blocks, empty blocks take
    their nearest neighbour, and the result is bilinearly resampled to the
    fine grid. It only has to be right to a few metres: it caps rim heights,
    it is never itself exported.
    """
    ny, nx = shape
    bs = max(DTM_BLOCK_M, 4 * cell)
    bx = np.clip(((P[:, 0] - x0) / bs).astype(int), 0, None)
    by = np.clip(((P[:, 1] - y0) / bs).astype(int), 0, None)
    mbx, mby = int(np.ceil(nx * cell / bs)) + 1, int(np.ceil(ny * cell / bs)) + 1
    bx, by = np.minimum(bx, mbx - 1), np.minimum(by, mby - 1)
    flat = by * mbx + bx
    order = np.lexsort((P[:, 2], flat))
    fs, zs = flat[order], P[order, 2]
    starts = np.r_[0, np.flatnonzero(np.diff(fs)) + 1]
    ends = np.r_[starts[1:], len(fs)]
    blk = np.full(mbx * mby, np.nan)
    enough = (ends - starts) >= 20
    blk[fs[starts[enough]]] = zs[starts[enough] + ((ends - starts)[enough] * 0.05).astype(int)]
    blk = blk.reshape(mby, mbx)
    if np.isfinite(blk).sum() == 0:
        return np.full(shape, np.inf)
    # Nearest valid block for empty ones, then remove isolated highs.
    miss = ~np.isfinite(blk)
    if miss.any():
        _, (iy, ix) = ndimage.distance_transform_edt(miss, return_indices=True)
        blk = blk[iy, ix]
    blk = ndimage.grey_opening(blk, size=(3, 3), mode="nearest")
    # Block centres sit at (i + 0.5) * bs; fine cell centres at (j + 0.5) * cell.
    fy = ((np.arange(ny) + 0.5) * cell / bs) - 0.5
    fx = ((np.arange(nx) + 0.5) * cell / bs) - 0.5
    gy, gx = np.meshgrid(fy, fx, indexing="ij")
    return ndimage.map_coordinates(blk, [gy, gx], order=1, mode="nearest")


def _membrane(unknown, known, value):
    """Solve Laplace's equation over ``unknown`` cells with ``known`` values.

    The fill is the smoothest surface that meets the observed ground all the
    way round the hole: level when the shoreline is level, tilting with it
    when the reconstruction (or the terrain) tilts. Unknown cells bordering
    neither known cells nor other unknowns stay NaN.
    """
    from scipy.sparse import coo_matrix
    from scipy.sparse.linalg import spsolve
    ny, nx = unknown.shape
    known = known & np.isfinite(value)
    idx = -np.ones(unknown.shape, np.int64)
    uy, ux = np.nonzero(unknown)
    idx[uy, ux] = np.arange(len(uy))
    out = np.full(unknown.shape, np.nan)
    if not len(uy):
        return out
    rows, cols, vals = [], [], []
    b = np.zeros(len(uy))
    deg = np.zeros(len(uy))
    for dy, dx in ((0, 1), (0, -1), (1, 0), (-1, 0)):
        yy, xx = uy + dy, ux + dx
        ok = (yy >= 0) & (yy < ny) & (xx >= 0) & (xx < nx)
        yy_c, xx_c = np.clip(yy, 0, ny - 1), np.clip(xx, 0, nx - 1)
        nu = ok & unknown[yy_c, xx_c]
        nk = ok & known[yy_c, xx_c]
        deg += nu | nk
        r = np.flatnonzero(nu)
        rows.append(r); cols.append(idx[yy_c[r], xx_c[r]]); vals.append(-np.ones(len(r)))
        b[nk] += value[yy_c[nk], xx_c[nk]]
    solvable = _reaches_known(unknown, known)[uy, ux]
    r = np.arange(len(uy))
    # Cells that cannot reach any observed ground are pinned (identity rows)
    # and discarded after the solve, keeping the system non-singular.
    diag = np.where(solvable & (deg > 0), deg, 1.0)
    keep = np.concatenate([np.r_[rr] for rr in rows])
    keep_c = np.concatenate(cols); keep_v = np.concatenate(vals)
    live = solvable[keep]
    A = coo_matrix((np.r_[keep_v[live], diag], (np.r_[keep[live], r], np.r_[keep_c[live], r])),
                   shape=(len(uy), len(uy))).tocsr()
    b = np.where(solvable, b, 0.0)
    z = spsolve(A, b)
    z[~solvable] = np.nan
    out[uy, ux] = z
    return out


def _reaches_known(unknown, known):
    """Unknown cells whose connected component touches at least one known cell."""
    lab, n = ndimage.label(unknown)
    touch = ndimage.binary_dilation(known) & unknown
    good = np.zeros(n + 1, bool)
    good[np.unique(lab[touch])] = True
    good[0] = False
    return good[lab]


def fill_holes(points, cameras, K, image_size, *, cell: float | None = None,
               min_views: int = 2, spacing: float | None = None,
               max_hole_area_m2: float | None = None) -> HoleFill:
    """Find holes inside the surveyed ground and fill each from its rim.

    ``cameras`` are dicts with ``C`` (centre) and ``R`` (world->camera
    rotation), the shape stored in ``trajectory.json``. ``spacing`` is the fill
    point spacing (defaults to half a cell).
    """
    P = np.asarray(points, float)
    K = np.asarray(K, float)
    if len(P) < 100 or not cameras:
        return HoleFill(np.zeros((0, 3)), np.zeros(0, np.int32), cell_m=cell or 0.0)
    cell = float(cell) if cell else auto_cell(P)
    spacing = float(spacing) if spacing else cell / 2.0

    z_ground = float(np.median(P[:, 2]))
    Cs = np.array([np.asarray(c["C"], float) for c in cameras])
    height = float(np.median(Cs[:, 2]) - z_ground)
    max_range = max(4.0 * abs(height), 50.0)

    lo = np.minimum(P[:, :2].min(0), Cs[:, :2].min(0)) - max_range
    hi = np.maximum(P[:, :2].max(0), Cs[:, :2].max(0)) + max_range
    # Bound the grid to the cloud's own extent plus a margin: a footprint that
    # runs off into the distance must not blow the raster up.
    plo, phi = P[:, :2].min(0) - 5 * cell, P[:, :2].max(0) + 5 * cell
    lo, hi = np.maximum(lo, plo), np.minimum(hi, phi)
    x0, y0 = float(lo[0]), float(lo[1])
    nx = int(np.ceil((hi[0] - x0) / cell)) + 1
    ny = int(np.ceil((hi[1] - y0) / cell)) + 1

    views = np.zeros((ny, nx), np.int32)
    for c in cameras:
        poly = _footprint(np.asarray(c["C"], float), np.asarray(c["R"], float),
                          K, image_size, z_ground, max_range)
        if poly is not None:
            views += _raster_polygon(poly, x0, y0, cell, (ny, nx))
    domain = views >= min_views

    ix = np.clip(((P[:, 0] - x0) / cell).astype(int), 0, nx - 1)
    iy = np.clip(((P[:, 1] - y0) / cell).astype(int), 0, ny - 1)
    flat = iy * nx + ix
    counts = np.bincount(flat, minlength=nx * ny).reshape(ny, nx)
    occupied = counts > 0

    # Per-cell ground height: a low percentile of the heights in the cell.
    order = np.lexsort((P[:, 2], flat))
    fs, zs = flat[order], P[order, 2]
    starts = np.r_[0, np.flatnonzero(np.diff(fs)) + 1]
    ends = np.r_[starts[1:], len(fs)]
    ground = np.full(nx * ny, np.nan)
    pick = starts + ((ends - starts - 1) * CELL_GROUND_PCT / 100.0).astype(int)
    ground[fs[starts]] = zs[pick]
    ground = ground.reshape(ny, nx)

    empty = domain & ~occupied
    labels, n = ndimage.label(empty, structure=np.ones((3, 3)))
    # Boundary heights: the ground, not whatever stands on the bank. Each rim
    # cell's own low height is kept where it is near the regional ground, and
    # capped at it where it is not -- a rooftop or canopy on the bank would
    # otherwise lift the fill across a river to roof height (DJI_1003, where
    # east downtown reconstructed as rooftops with no street between them).
    dtm = _regional_ground(P, x0, y0, cell, (ny, nx))
    bank = np.where(occupied, np.minimum(ground, dtm + BANK_ABOVE_GROUND_M), np.nan)

    z_fill = _membrane(empty, occupied, bank)

    holes, pts_out, ids_out = [], [], []
    ring = np.ones((5, 5), bool)
    objects = ndimage.find_objects(labels)
    n_empty = 0
    k = max(1, int(round(cell / spacing)))
    off = (np.arange(k) + 0.5) / k
    ox, oy = np.meshgrid(off, off)
    for lab in range(1, n + 1):
        sl = objects[lab - 1]
        y_a, y_b = max(sl[0].start - 3, 0), min(sl[0].stop + 3, ny)
        x_a, x_b = max(sl[1].start - 3, 0), min(sl[1].stop + 3, nx)
        m = labels[y_a:y_b, x_a:x_b] == lab
        zf = z_fill[y_a:y_b, x_a:x_b][m]
        if not np.isfinite(zf).all():
            continue                      # no observed ground anywhere around it
        area = float(m.sum()) * cell * cell
        if max_hole_area_m2 is not None and area > max_hole_area_m2:
            continue
        rim = ndimage.binary_dilation(m, ring) & occupied[y_a:y_b, x_a:x_b]
        rz = bank[y_a:y_b, x_a:x_b][rim]
        rz = rz[np.isfinite(rz)]
        if len(rz) < 3:
            continue
        # Bilinear surface over the cells' sub-grid, so a large hole is not a
        # staircase of cell-sized terraces.
        hy, hx = np.nonzero(m)
        gx = (hx[:, None] + x_a + ox.ravel()[None]).ravel()
        gy = (hy[:, None] + y_a + oy.ravel()[None]).ravel()
        fz = ndimage.map_coordinates(np.nan_to_num(z_fill, nan=np.nanmean(zf)),
                                     [gy - 0.5, gx - 0.5], order=1, mode="nearest")
        pts_out.append(np.c_[x0 + gx * cell, y0 + gy * cell, fz])
        ids_out.append(np.full(len(fz), len(holes), np.int32))
        n_empty += int(m.sum())
        holes.append({
            "id": len(holes),
            "area_m2": round(area, 1),
            "centroid_enu": [round(float(pts_out[-1][:, 0].mean()), 2),
                             round(float(pts_out[-1][:, 1].mean()), 2)],
            "rim_cells": int(len(rz)),
            # How much the ground around the hole disagrees with itself. A
            # still water body has a near-constant shoreline; a large spread
            # says the surface across it is an interpolation, not a level.
            "rim_ground_spread_m": round(float(np.percentile(rz, 90)
                                               - np.percentile(rz, 10)), 3),
            "fill_z_range_m": [round(float(fz.min()), 3), round(float(fz.max()), 3)],
        })

    if pts_out:
        pts = np.vstack(pts_out); ids = np.concatenate(ids_out)
    else:
        pts = np.zeros((0, 3)); ids = np.zeros(0, np.int32)
    holes.sort(key=lambda h: -h["area_m2"])
    return HoleFill(pts, ids, holes, cell, int(domain.sum()), n_empty)


def colorize(fill_pts, cameras, K, image_size, get_image, *, default=(90, 110, 125)):
    """Colour fill points from the most nadir view that sees each one.

    ``get_image(i)`` returns the BGR frame for ``cameras[i]`` at the
    processing resolution, or None. Occlusion is not tested: a fill point is
    only ever where the cloud has nothing, so there is nothing in front of it
    to test against. Points no camera sees keep ``default`` (a slate blue-grey,
    deliberately not a real-looking colour).
    """
    X = np.asarray(fill_pts, float)
    K = np.asarray(K, float)
    w, h = image_size
    out = np.tile(np.array(default, np.uint8), (len(X), 1))
    best = np.full(len(X), np.inf)
    cx, cy = K[0, 2], K[1, 2]
    for i, c in enumerate(cameras):
        R = np.asarray(c["R"], float); C = np.asarray(c["C"], float)
        Xc = (X - C) @ R.T
        z = Xc[:, 2]
        ok = z > 0
        uv = np.full((len(X), 2), -1.0)
        uv[ok] = (Xc[ok] @ K.T)[:, :2] / z[ok, None]
        inside = ok & (uv[:, 0] >= 0) & (uv[:, 0] < w - 1) & (uv[:, 1] >= 0) & (uv[:, 1] < h - 1)
        # Distance from the image centre: the most nadir look, least glint-prone
        # at the edges and least distorted.
        score = np.hypot(uv[:, 0] - cx, uv[:, 1] - cy)
        take = inside & (score < best)
        if not take.any():
            continue
        img = get_image(i)
        if img is None:
            continue
        u = uv[take, 0].astype(int); v = uv[take, 1].astype(int)
        out[take] = img[v, u][:, ::-1]           # BGR -> RGB
        best[take] = score[take]
    return out
