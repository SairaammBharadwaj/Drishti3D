"""Observation space: what the cameras actually established, and what they did not.

Why this is a separate layer
----------------------------
Both committed quality reports show zero points classified `UNOBSERVED` and zero
`DYNAMIC_EXCLUDED`, and that is not a bug in the classifier — it is a category
error. A surface nobody photographed produces **no point at all**, and a masked
moving object produces no point either. Neither absence can be represented as a
point carrying a label, so the legend promised something the data model could
never deliver.

The information is real, though, and it is exactly what a measurement product
needs: *which parts of this scene did the flight actually establish?* That
question is about **space**, not about points, so it needs a spatial structure of
its own. This module builds one.

How it works
------------
A voxel grid is laid over the scene. Each cell is classified by what the cameras
could have seen there:

* ``OBSERVED``      — reconstructed surface is present and at least two cameras
                      have an unobstructed line of sight to it.
* ``WEAK``          — surface present but supported by a single view, or seen
                      only at a grazing incidence, so its geometry is poorly
                      constrained.
* ``OCCLUDED``      — inside a camera frustum, but every line of sight is blocked
                      by nearer reconstructed geometry. The classic hidden wall.
* ``UNSEEN``        — never entered any camera frustum. The flight simply did not
                      look there.
* ``EMPTY``         — swept by camera rays and found to contain no surface. This
                      is a *positive* result: free space that was checked.

Visibility is evaluated with a per-camera depth buffer built from the
reconstructed cloud, which is the standard z-buffer test and costs one pass per
camera rather than a ray march per cell.

The point of the distinction
----------------------------
``UNSEEN`` and ``OCCLUDED`` are the cells where a mesher would happily
interpolate a surface and a user would happily measure it. Marking them lets the
product refuse: :meth:`CoverageGrid.is_measurable` is the gate, and it answers
"no" for space the flight never established rather than inventing a number.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import IntEnum

import numpy as np


class Coverage(IntEnum):
    """Per-cell observation status. Ordering is meaningful: higher is better."""

    UNSEEN = 0          # never inside any camera frustum
    OCCLUDED = 1        # in frustum, but the line of sight is blocked
    #: Seen only through pixels masked as dynamic (moving objects). The cameras
    #: *did* look here, but the observation was deliberately discarded, so this
    #: is neither established geometry nor unexplored space -- a distinction the
    #: point cloud could never carry, because a masked pixel produces no point.
    DYNAMIC_EXCLUDED = 2
    EMPTY = 3           # swept by rays, verified to hold no surface
    WEAK = 4            # surface present, but single-view or grazing incidence
    OBSERVED = 5        # surface present, >= 2 unobstructed views

    @property
    def measurable(self) -> bool:
        return self is Coverage.OBSERVED

    @property
    def color(self) -> tuple:
        return {
            Coverage.UNSEEN: (90, 90, 90),
            Coverage.OCCLUDED: (200, 60, 60),
            Coverage.DYNAMIC_EXCLUDED: (231, 76, 60),
            Coverage.EMPTY: (30, 40, 60),
            Coverage.WEAK: (230, 170, 40),
            Coverage.OBSERVED: (60, 200, 90),
        }[self]


@dataclass
class CoverageGrid:
    """A sparse voxel field describing what the capture established."""

    origin: np.ndarray            # (3,) ENU coordinate of cell (0,0,0)'s corner
    voxel: float                  # cell edge length, metres
    shape: tuple                  # (nx, ny, nz)
    status: np.ndarray            # (nx,ny,nz) uint8 of Coverage
    view_count: np.ndarray        # (nx,ny,nz) uint16 unobstructed views
    best_incidence_deg: np.ndarray  # (nx,ny,nz) float32, 0 = face-on
    meta: dict = field(default_factory=dict)

    # ---- queries ---------------------------------------------------------- #
    def cell_of(self, points) -> np.ndarray:
        """Integer cell indices for ENU points; ``-1`` where outside the grid."""
        p = np.atleast_2d(np.asarray(points, float))
        idx = np.floor((p - self.origin) / self.voxel).astype(int)
        inside = np.all((idx >= 0) & (idx < np.array(self.shape)), axis=1)
        idx[~inside] = -1
        return idx

    def status_at(self, points) -> np.ndarray:
        """Coverage status at each ENU point (``UNSEEN`` outside the grid)."""
        idx = self.cell_of(points)
        out = np.full(len(idx), int(Coverage.UNSEEN), np.uint8)
        ok = np.all(idx >= 0, axis=1)
        if ok.any():
            i = idx[ok]
            out[ok] = self.status[i[:, 0], i[:, 1], i[:, 2]]
        return out

    def is_measurable(self, points) -> np.ndarray:
        """True where the capture established geometry well enough to measure.

        Anything the flight did not see, could not see, or saw only once is
        refused. Refusing is the useful behaviour: a confident number from
        unobserved space is worse than no number.
        """
        return self.status_at(points) == int(Coverage.OBSERVED)

    def counts(self) -> dict:
        vals, cnt = np.unique(self.status, return_counts=True)
        out = {c.name: 0 for c in Coverage}
        for v, n in zip(vals, cnt):
            out[Coverage(int(v)).name] = int(n)
        return out

    def summary(self) -> dict:
        c = self.counts()
        total = int(np.prod(self.shape))
        # "Explained" = cells the capture actually resolved one way or the other:
        # surface found, or free space verified. Unseen/occluded are the gaps.
        explained = c["OBSERVED"] + c["WEAK"] + c["EMPTY"]
        surface = c["OBSERVED"] + c["WEAK"]
        return {
            "voxel_m": self.voxel,
            "grid_shape": list(self.shape),
            "n_cells": total,
            "counts": c,
            "fraction_explained": explained / total if total else None,
            "fraction_unseen": c["UNSEEN"] / total if total else None,
            "fraction_occluded": c["OCCLUDED"] / total if total else None,
            "surface_cells": surface,
            "measurable_surface_fraction": (c["OBSERVED"] / surface) if surface else None,
            "note": ("UNSEEN and OCCLUDED are space the flight did not establish. "
                     "They are not reconstructed geometry and are excluded from "
                     "measurement by default."),
        }

    def to_npz(self, path):
        np.savez_compressed(
            path, origin=self.origin, voxel=np.array([self.voxel]),
            shape=np.array(self.shape), status=self.status,
            view_count=self.view_count, best_incidence_deg=self.best_incidence_deg)
        return str(path)


# --------------------------------------------------------------------------- #
# construction
# --------------------------------------------------------------------------- #
def _depth_buffer(points_cam, width, height, K, scale, dilate: int = 2):
    """Nearest-depth z-buffer of the cloud as seen by one camera.

    Rendered at reduced resolution, then **dilated**: a sparse cloud projects to
    isolated pixels with gaps between them, and without dilation a sight line
    slips between two points of a solid wall and reports the space behind it as
    free. Measured on the hidden-wall fixture, an undilated buffer classified a
    fully occluded wall as visible in 100% of cells.

    Dilation is a minimum filter, so it can only make occlusion *more* likely --
    the conservative direction for a layer whose job is to refuse unestablished
    space.
    """
    w = max(int(width * scale), 8)
    h = max(int(height * scale), 8)
    buf = np.full((h, w), np.inf, np.float32)
    z = points_cam[:, 2]
    front = z > 1e-6
    if not front.any():
        return buf, w, h
    p = points_cam[front]
    u = (K[0, 0] * p[:, 0] / p[:, 2] + K[0, 2]) * scale
    v = (K[1, 1] * p[:, 1] / p[:, 2] + K[1, 2]) * scale
    ui = np.floor(u).astype(int)
    vi = np.floor(v).astype(int)
    ok = (ui >= 0) & (ui < w) & (vi >= 0) & (vi < h)
    if not ok.any():
        return buf, w, h
    np.minimum.at(buf, (vi[ok], ui[ok]), p[ok, 2].astype(np.float32))
    if dilate > 0:
        try:
            from scipy.ndimage import minimum_filter
            buf = minimum_filter(buf, size=2 * dilate + 1, mode="nearest")
        except Exception:
            # Fall back to a manual shift-and-min so the guarantee holds even
            # without scipy.ndimage.
            out = buf.copy()
            for dy in range(-dilate, dilate + 1):
                for dx in range(-dilate, dilate + 1):
                    out = np.minimum(out, np.roll(np.roll(buf, dy, 0), dx, 1))
            buf = out
    return buf, w, h


def build(cloud_points, cameras, K, image_size, *,
          masks=None,
          voxel: float = 1.0, margin: float = 2.0,
          depth_scale: float = 0.15, occlusion_tol: float = 1.5,
          max_cells: int = 4_000_000,
          weak_incidence_deg: float = 75.0,
          normals=None) -> CoverageGrid:
    """Build the coverage field for a reconstruction.

    Parameters
    ----------
    cloud_points
        ``(N,3)`` reconstructed points, in the same frame as the cameras.
    cameras
        Sequence with ``.R`` (world->camera), ``.t`` and ``.center``.
    K, image_size
        Intrinsics and ``(width, height)`` the cameras were solved at.
    voxel
        Cell size. Coverage is a *coarse* question -- which regions did the
        flight establish -- so this is deliberately much larger than the point
        spacing.
    occlusion_tol
        Depth slack, in metres, before a cell counts as hidden behind geometry.
        Sparse clouds have gaps, so a tight tolerance would report spurious
        occlusion on surfaces that were seen perfectly well.
    """
    pts = np.asarray(cloud_points, float).reshape(-1, 3)
    if len(pts) == 0 or not len(cameras):
        raise ValueError("coverage needs points and at least one camera")

    cams_c = np.array([np.asarray(c.center, float).ravel() for c in cameras])
    lo = np.minimum(pts.min(0), cams_c.min(0)) - margin
    hi = np.maximum(pts.max(0), cams_c.max(0)) + margin

    # Keep the grid affordable: coarsen rather than allocate an enormous array.
    shape = np.maximum(np.ceil((hi - lo) / voxel).astype(int), 1)
    while int(np.prod(shape)) > max_cells:
        voxel *= 1.5
        shape = np.maximum(np.ceil((hi - lo) / voxel).astype(int), 1)
    nx, ny, nz = (int(s) for s in shape)

    status = np.full((nx, ny, nz), int(Coverage.UNSEEN), np.uint8)
    view_count = np.zeros((nx, ny, nz), np.uint16)
    dyn_count = np.zeros((nx, ny, nz), np.uint16)
    best_inc = np.full((nx, ny, nz), 180.0, np.float32)
    in_frustum = np.zeros((nx, ny, nz), bool)

    # Which cells contain reconstructed surface?
    pidx = np.floor((pts - lo) / voxel).astype(int)
    pidx = pidx[np.all((pidx >= 0) & (pidx < shape), axis=1)]
    has_surface = np.zeros((nx, ny, nz), bool)
    if len(pidx):
        has_surface[pidx[:, 0], pidx[:, 1], pidx[:, 2]] = True

    # Per-cell surface normal by PCA over the points inside each cell. Needed
    # for a real incidence angle: without a normal there is no such thing as
    # "grazing", and any proxy built from the view direction alone measures
    # something else. (An earlier version used view-ray verticality, which
    # scored a horizontal ray hitting a vertical wall -- the face-on case -- as
    # the worst possible incidence.)
    cell_normal = np.full((nx * ny * nz, 3), np.nan)
    inside_pts = np.all((np.floor((pts - lo) / voxel).astype(int) >= 0)
                        & (np.floor((pts - lo) / voxel).astype(int) < shape), axis=1)
    if inside_pts.any():
        ip = pts[inside_pts]
        ci3 = np.floor((ip - lo) / voxel).astype(int)
        flat_ci = np.ravel_multi_index((ci3[:, 0], ci3[:, 1], ci3[:, 2]),
                                       (nx, ny, nz))
        ncell = nx * ny * nz
        cnt = np.bincount(flat_ci, minlength=ncell).astype(float)
        ssum = np.zeros((ncell, 3))
        np.add.at(ssum, flat_ci, ip)
        outer = np.einsum("ni,nj->nij", ip, ip)
        sout = np.zeros((ncell, 3, 3))
        np.add.at(sout, flat_ci, outer)
        enough = cnt >= 4
        if enough.any():
            k = np.where(enough)[0]
            m = ssum[k] / cnt[k, None]
            cov = sout[k] / cnt[k, None, None] - np.einsum("ni,nj->nij", m, m)
            evals, evecs = np.linalg.eigh(cov)
            # smallest-variance direction is the surface normal
            cell_normal[k] = evecs[:, :, 0]

    # Cell centres, evaluated as one flat array per camera.
    gx, gy, gz = np.meshgrid(np.arange(nx), np.arange(ny), np.arange(nz),
                             indexing="ij")
    centres = (np.stack([gx, gy, gz], -1).reshape(-1, 3) + 0.5) * voxel + lo
    flat_surface = has_surface.reshape(-1)

    width, height = image_size
    K = np.asarray(K, float)

    vc_flat = np.zeros(centres.shape[0], np.int32)
    dyn_flat = np.zeros(centres.shape[0], np.int32)
    inc_flat = np.full(centres.shape[0], 180.0, np.float32)
    seen_flat = np.zeros(centres.shape[0], bool)

    for cam_i, cam in enumerate(cameras):
        R = np.asarray(cam.R, float)
        t = np.asarray(cam.t, float).ravel()
        cam_pts = (R @ pts.T).T + t
        buf, bw, bh = _depth_buffer(cam_pts, width, height, K, depth_scale)

        cc = (R @ centres.T).T + t
        z = cc[:, 2]
        front = z > 1e-6
        if not front.any():
            continue
        u = np.full(len(cc), -1.0)
        v = np.full(len(cc), -1.0)
        u[front] = (K[0, 0] * cc[front, 0] / z[front] + K[0, 2]) * depth_scale
        v[front] = (K[1, 1] * cc[front, 1] / z[front] + K[1, 2]) * depth_scale
        ui = np.floor(u).astype(int)
        vi = np.floor(v).astype(int)
        inside = front & (ui >= 0) & (ui < bw) & (vi >= 0) & (vi < bh)
        if not inside.any():
            continue
        seen_flat |= inside            # entered this camera's frustum

        # A ray through a pixel masked as dynamic carries no usable evidence:
        # the observation was thrown away on purpose. Count it separately so a
        # cell seen *only* through masked pixels is not mistaken for either
        # verified free space or unexplored volume.
        if masks is not None and cam_i < len(masks) and masks[cam_i] is not None:
            mk = masks[cam_i]
            mh, mw = mk.shape[:2]
            mu = np.clip((u / depth_scale).astype(int), 0, mw - 1)
            mv = np.clip((v / depth_scale).astype(int), 0, mh - 1)
            masked_here = inside & (mk[mv, mu] == 0)
            dyn_flat += masked_here.astype(np.int32)
            inside = inside & ~masked_here

        # z-buffer visibility: nothing reconstructed sits nearer along this ray
        nearest = np.full(len(cc), np.inf, np.float32)
        nearest[inside] = buf[vi[inside], ui[inside]]
        visible = inside & (z <= nearest + occlusion_tol)
        vc_flat += visible.astype(np.int32)

        # True incidence: the angle between the view ray and the cell's surface
        # normal. 0 deg is face-on. Cells without an estimable normal keep NaN
        # and are simply not incidence-tested, rather than being scored by a
        # stand-in that means something else.
        if visible.any():
            vis_idx = np.where(visible)[0]
            nrm = cell_normal[vis_idx]
            has_n = np.isfinite(nrm).all(axis=1)
            if has_n.any():
                sel = vis_idx[has_n]
                d = centres[sel] - np.asarray(cam.center, float).ravel()
                d /= (np.linalg.norm(d, axis=1, keepdims=True) + 1e-12)
                # |cos| because the normal's sign is arbitrary from PCA
                cos = np.abs(np.sum(d * nrm[has_n], axis=1))
                ang = np.degrees(np.arccos(np.clip(cos, 0, 1)))
                inc_flat[sel] = np.minimum(inc_flat[sel], ang.astype(np.float32))

    view_count = vc_flat.reshape(nx, ny, nz).astype(np.uint16)
    dyn_count = dyn_flat.reshape(nx, ny, nz).astype(np.uint16)
    best_inc = inc_flat.reshape(nx, ny, nz)
    in_frustum = seen_flat.reshape(nx, ny, nz)

    # ---- classify --------------------------------------------------------- #
    st = np.full((nx, ny, nz), int(Coverage.UNSEEN), np.uint8)
    st[in_frustum] = int(Coverage.OCCLUDED)       # in view, but nothing verified
    swept = in_frustum & (view_count > 0)
    st[swept] = int(Coverage.EMPTY)               # ray reached here: free space
    surf_weak = has_surface & (view_count >= 1)
    st[surf_weak] = int(Coverage.WEAK)
    # Cells with no estimable normal keep the 180 sentinel; treat them as
    # passing the incidence test rather than failing a test that was never run.
    inc_ok = (best_inc <= weak_incidence_deg) | (best_inc >= 179.0)
    surf_ok = has_surface & (view_count >= 2) & inc_ok
    st[surf_ok] = int(Coverage.OBSERVED)
    # Surface that no camera can currently reach is hidden, not merely weak.
    st[has_surface & (view_count == 0)] = int(Coverage.OCCLUDED)
    # Cells whose only observations came through masked (dynamic) pixels: the
    # flight looked, and the evidence was deliberately discarded.
    st[(dyn_count > 0) & (view_count == 0) & ~has_surface] = int(
        Coverage.DYNAMIC_EXCLUDED)

    grid = CoverageGrid(origin=lo, voxel=float(voxel), shape=(nx, ny, nz),
                        status=st, view_count=view_count,
                        best_incidence_deg=best_inc,
                        meta={"n_cameras": len(cameras),
                              "n_points": int(len(pts)),
                              "occlusion_tol_m": float(occlusion_tol),
                              "weak_incidence_deg": float(weak_incidence_deg),
                              "depth_buffer_scale": float(depth_scale),
                              "masks_supplied": masks is not None})
    return grid


def recapture_hints(grid: CoverageGrid, *, top: int = 5) -> list[dict]:
    """Where the capture is weakest, as advice a pilot could act on.

    Reports the largest contiguous-ish clusters of unestablished space by simple
    slab aggregation. This is intentionally coarse: the useful output is "the
    north-east side is unseen", not a per-voxel list.
    """
    gaps = np.isin(grid.status, [int(Coverage.UNSEEN), int(Coverage.OCCLUDED)])
    if not gaps.any():
        return []
    nx, ny, nz = grid.shape
    # Aggregate over vertical columns: a pilot flies a horizontal pattern.
    col = gaps.sum(axis=2)
    order = np.dstack(np.unravel_index(np.argsort(col.ravel())[::-1], col.shape))[0]
    out = []
    for ix, iy in order[:top]:
        n = int(col[ix, iy])
        if n == 0:
            break
        centre = grid.origin + (np.array([ix, iy, nz / 2.0]) + 0.5) * grid.voxel
        out.append({"enu": [float(x) for x in centre],
                    "unestablished_cells": n,
                    "height_m": float(n * grid.voxel)})
    return out
