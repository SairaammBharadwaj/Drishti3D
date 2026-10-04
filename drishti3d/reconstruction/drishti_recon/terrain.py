"""Terrain analytics on the observed rasters: volume, profile, slope, line of sight.

They read the grids :mod:`rasters` writes (``rasters.npz``), which hold
observed points only, and keep its rules: an empty cell is unknown, never
interpolated. Every answer reports how much of what it needed was observed,
and refuses (``status: "refused"``) below :data:`COVERAGE_MIN` rather than
giving a number made mostly of gaps.

* **Volume and profile use the mean height per cell** (``zmean``), not the
  DSM: the highest point in a cell is biased upward by noise, and summing that
  bias over thousands of cells inflates a stockpile.
* **Line of sight uses the DSM**: an obstruction is the top of whatever stands
  there. A ray that clears every observed cell but crosses unobserved ones is
  ``unknown``, not visible; a cell within two sigma of the ray is marginal and
  also makes it ``unknown`` unless something clearly blocks it.
* Sigma is the cells' propagated, uncalibrated estimate (as in the cloud).

Coordinates in and out are the grid's (UTM metres of ``rasters.json``'s CRS);
the API converts the viewer's local ENU picks.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np

from .rasters import Grid

#: Below this share of observed cells an analysis refuses.
COVERAGE_MIN = 0.8
#: |surface - ray| within this many sigma is marginal for line of sight.
LOS_SIGMA_K = 2.0


@dataclass
class Surfaces:
    grid: Grid
    dsm: np.ndarray
    zmean: np.ndarray
    sigma: np.ndarray
    count: np.ndarray
    epsg: int

    @classmethod
    def load(cls, path) -> "Surfaces":
        d = np.load(Path(path))
        x0, y1, res, h, w = d["grid"]
        return cls(Grid(float(x0), float(y1), float(res), int(h), int(w)),
                   d["dsm"].astype(float), d["zmean"].astype(float),
                   d["sigma"].astype(float), d["count"], int(d["epsg"][0]))


def _refuse(reason: str, **kw) -> dict:
    return {"status": "refused", "reason": reason, **kw}


def _polygon_mask(grid: Grid, polygon) -> np.ndarray:
    """Cells whose centre lies inside the polygon (even-odd rule)."""
    poly = np.asarray(polygon, float).reshape(-1, 2)
    if len(poly) < 3:
        raise ValueError("a polygon needs at least three vertices")
    X, Y = grid.centres()
    inside = np.zeros(X.shape, bool)
    j = len(poly) - 1
    for i in range(len(poly)):
        xi, yi = poly[i]
        xj, yj = poly[j]
        cross = (yi > Y) != (yj > Y)
        with np.errstate(divide="ignore", invalid="ignore"):
            xint = (xj - xi) * (Y - yi) / (yj - yi) + xi
        inside ^= cross & (X < xint)
        j = i
    return inside


def _polygon_area(poly) -> float:
    p = np.asarray(poly, float).reshape(-1, 2)
    x, y = p[:, 0], p[:, 1]
    return float(0.5 * abs(np.dot(x, np.roll(y, -1)) - np.dot(y, np.roll(x, -1))))


def _samples(a, b, res, step=None):
    a, b = np.asarray(a, float), np.asarray(b, float)
    length = float(np.hypot(*(b[:2] - a[:2])))
    step = float(step or res / 2)
    n = max(2, int(np.ceil(length / step)) + 1)
    t = np.linspace(0.0, 1.0, n)
    return t, a[None, :2] + t[:, None] * (b[:2] - a[:2])[None], length


# ---------------------------------------------------------------------- volume
def volume(s: Surfaces, polygon, *, base: str = "edge", base_z: float | None = None,
           coverage_min: float = COVERAGE_MIN) -> dict:
    """Volume above (cut) and below (fill) a base surface inside a polygon.

    ``base`` is ``"edge"`` (a plane fitted to the observed cells on the
    polygon's boundary: the usual stockpile toe), ``"lowest"`` (the lowest
    observed mean height inside) or ``"fixed"`` (``base_z``, on the cloud's
    vertical datum). Uses the mean height per cell.
    """
    g = s.grid
    inside = _polygon_mask(g, polygon)
    n_cells = int(inside.sum())
    if n_cells == 0:
        return _refuse("the polygon contains no grid cell")
    obs = inside & np.isfinite(s.zmean)
    coverage = float(obs.sum() / n_cells)
    base_info = {"kind": base}
    if coverage < coverage_min:
        return _refuse(f"only {coverage:.0%} of the polygon was observed "
                       f"(needs {coverage_min:.0%}); empty cells are not interpolated",
                       coverage=coverage, cells=n_cells)
    X, Y = g.centres()
    z = s.zmean
    if base == "fixed":
        if base_z is None:
            raise ValueError("base='fixed' needs base_z")
        plane = np.full(z.shape, float(base_z))
        base_info["z"] = float(base_z)
    elif base == "lowest":
        zb = float(np.nanmin(z[obs]))
        plane = np.full(z.shape, zb)
        base_info["z"] = zb
    elif base == "edge":
        from scipy import ndimage
        ring = inside & ~ndimage.binary_erosion(inside) & np.isfinite(z)
        if ring.sum() < 3:
            return _refuse("fewer than three observed cells on the polygon's edge to "
                           "fit a base plane", coverage=coverage)
        A = np.c_[X[ring], Y[ring], np.ones(ring.sum())]
        coef, *_ = np.linalg.lstsq(A, z[ring], rcond=None)
        plane = coef[0] * X + coef[1] * Y + coef[2]
        resid = z[ring] - A @ coef
        base_info.update({"plane": [float(c) for c in coef],
                          "edge_cells": int(ring.sum()),
                          "edge_rms_m": float(np.sqrt(np.mean(resid ** 2)))})
    else:
        raise ValueError(f"unknown base {base!r}")

    cell = g.res ** 2
    dz = (z - plane)[obs]
    cut = float(dz[dz > 0].sum() * cell)
    fill = float(-dz[dz < 0].sum() * cell)
    # The unobserved share is scaled in at the observed cells' mean, and said so.
    scale = n_cells / obs.sum()
    sig = s.sigma[obs]
    sig = sig[np.isfinite(sig)]
    sig_ind = float(cell * np.sqrt(np.sum(sig ** 2)) * scale) if len(sig) else None
    sig_cor = float(cell * np.sum(sig) * scale) if len(sig) else None
    if base == "edge" and base_info["edge_rms_m"] is not None:
        # A base-plane error moves every cell together.
        b = base_info["edge_rms_m"] / np.sqrt(base_info["edge_cells"])
        sig_ind = None if sig_ind is None else float(np.hypot(sig_ind, b * n_cells * cell))
    return {
        "status": "ok",
        "net_m3": (cut - fill) * scale, "cut_m3": cut * scale, "fill_m3": fill * scale,
        "observed_net_m3": cut - fill,
        "area_m2": n_cells * cell, "polygon_area_m2": _polygon_area(polygon),
        "coverage": coverage, "cells": n_cells, "cell_size_m": g.res,
        "base": base_info, "surface": "mean height per cell (zmean), observed points only",
        "sigma_m3": {"independent_cells": sig_ind, "fully_correlated_bound": sig_cor,
                     "note": "propagated point sigma, uncalibrated; the true error lies "
                             "between the independent and correlated figures"},
        "unobserved_note": (None if coverage >= 1 else
                            f"{1 - coverage:.0%} of the cells were not observed; the "
                            "totals scale the observed cells up to the full area"),
    }


# --------------------------------------------------------------------- profile
def profile(s: Surfaces, a, b, *, step: float | None = None,
            coverage_min: float = COVERAGE_MIN) -> dict:
    """Mean surface height along a line, with gaps left as ``None``."""
    t, xy, length = _samples(a, b, s.grid.res, step)
    z = s.grid.sample(s.zmean, xy)
    sg = s.grid.sample(s.sigma, xy)
    have = np.isfinite(z)
    coverage = float(have.mean())
    pts = [{"d_m": float(ti * length), "x": float(p[0]), "y": float(p[1]),
            "z": float(zi) if np.isfinite(zi) else None,
            "sigma_m": float(si) if np.isfinite(si) else None}
           for ti, p, zi, si in zip(t, xy, z, sg)]
    if coverage < coverage_min:
        return _refuse(f"only {coverage:.0%} of the line was observed "
                       f"(needs {coverage_min:.0%})", coverage=coverage, samples=pts,
                       length_m=length)
    zz = z[have]
    d = t[have] * length
    rise = float(zz[-1] - zz[0]) if len(zz) > 1 else 0.0
    return {"status": "ok", "length_m": length, "coverage": coverage, "samples": pts,
            "surface": "mean height per cell (zmean), observed points only",
            "min_z": float(zz.min()), "max_z": float(zz.max()),
            "net_rise_m": rise,
            "mean_grade_pct": float(100 * rise / max(d[-1] - d[0], 1e-9)) if len(d) > 1 else 0.0,
            "gaps": int((~have).sum())}


# ----------------------------------------------------------------------- slope
def slope_grid(s: Surfaces) -> np.ndarray:
    """Slope in degrees; NaN wherever a neighbour needed by the gradient is empty."""
    z = s.zmean
    res = s.grid.res
    p = np.pad(z, 1, constant_values=np.nan)
    gx = (p[1:-1, 2:] - p[1:-1, :-2]) / (2 * res)
    gy = (p[:-2, 1:-1] - p[2:, 1:-1]) / (2 * res)       # rows run south
    return np.degrees(np.arctan(np.hypot(gx, gy)))


def slope(s: Surfaces, polygon, *, coverage_min: float = COVERAGE_MIN) -> dict:
    """Slope statistics inside a polygon, from cells with every neighbour observed."""
    inside = _polygon_mask(s.grid, polygon)
    n = int(inside.sum())
    if n == 0:
        return _refuse("the polygon contains no grid cell")
    sl = slope_grid(s)[inside]
    ok = np.isfinite(sl)
    coverage = float(ok.mean())
    if coverage < coverage_min:
        return _refuse(f"slope is known for only {coverage:.0%} of the polygon "
                       f"(needs {coverage_min:.0%})", coverage=coverage)
    v = sl[ok]
    return {"status": "ok", "coverage": coverage, "cells": n,
            "mean_deg": float(v.mean()), "median_deg": float(np.median(v)),
            "p90_deg": float(np.percentile(v, 90)), "max_deg": float(v.max()),
            "surface": "mean height per cell; central differences over observed cells only"}


# ---------------------------------------------------------------- line of sight
def line_of_sight(s: Surfaces, observer, target, *, observer_height: float = 1.7,
                  target_height: float = 0.0, step: float | None = None) -> dict:
    """Whether ``target`` is visible from ``observer`` over the DSM.

    ``observer``/``target`` are (x, y) or (x, y, z); without z the point is
    placed on the DSM there (and refuses if that cell is empty). Heights are
    added above it. Returns ``visible``, ``blocked`` (with the first clear
    obstruction) or ``unknown`` (unobserved or marginal cells, none blocking).
    """
    g = s.grid
    ends = []
    for p, hgt, name in ((observer, observer_height, "observer"),
                         (target, target_height, "target")):
        p = np.asarray(p, float).ravel()
        if len(p) >= 3 and np.isfinite(p[2]):
            z = p[2]
        else:
            z = float(g.sample(s.dsm, p[None, :2])[0])
            if not np.isfinite(z):
                return _refuse(f"the {name} stands on an unobserved cell; give its height")
        ends.append(np.array([p[0], p[1], z + hgt]))
    a, b = ends
    t, xy, length = _samples(a, b, g.res, step)
    # Ignore the cells the ends stand on: the ground under an observer is not
    # an obstruction.
    margin = 1.5 * g.res / max(length, 1e-9)
    mid = (t > margin) & (t < 1 - margin)
    t, xy = t[mid], xy[mid]
    ray = a[2] + t * (b[2] - a[2])
    dsm = g.sample(s.dsm, xy)
    sig = g.sample(s.sigma, xy)
    sig = np.where(np.isfinite(sig), sig, 0.0)
    have = np.isfinite(dsm)
    clear_k = LOS_SIGMA_K * sig
    blocks = have & (dsm > ray + clear_k)
    marginal = have & ~blocks & (dsm > ray - clear_k)
    out = {"length_m": length, "observer": a.tolist(), "target": b.tolist(),
           "samples": int(len(t)), "unobserved_samples": int((~have).sum()),
           "marginal_samples": int(marginal.sum()),
           "surface": "DSM: highest observed point per cell"}
    if blocks.any():
        i = int(np.argmax(blocks))
        out.update(status="ok", result="blocked",
                   obstruction={"x": float(xy[i, 0]), "y": float(xy[i, 1]),
                                "z": float(dsm[i]), "ray_z": float(ray[i]),
                                "clearance_m": float(ray[i] - dsm[i]),
                                "distance_m": float(t[i] * length)})
        return out
    if (~have).any() or marginal.any():
        why = []
        if (~have).any():
            why.append(f"the ray crosses {int((~have).sum())} unobserved sample(s)")
        if marginal.any():
            why.append(f"{int(marginal.sum())} sample(s) lie within "
                       f"{LOS_SIGMA_K:g} sigma of the ray")
        out.update(status="ok", result="unknown", reason="; ".join(why))
        return out
    out.update(status="ok", result="visible",
               min_clearance_m=float(np.min(ray - dsm)) if len(t) else None)
    return out


__all__ = ["Surfaces", "volume", "profile", "slope", "slope_grid", "line_of_sight",
           "COVERAGE_MIN"]
