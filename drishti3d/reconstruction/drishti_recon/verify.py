"""Multi-view verification of inferred geometry.

The problem
-----------
The depth-prior path fits a monocular network's depth to the sparse triangulated
points of **one frame at a time**, then merges every resulting point into the
cloud. Each point is therefore supported by exactly one view and one model
prediction. Monocular depth is a plausible guess about a single image, not a
measurement, and a single-view guess has no way to be wrong in a detectable way.

What this module adds
---------------------
An independent test that the *other* cameras agree. For each inferred point:

1. project it into every neighbouring camera that should see it;
2. compare its distance from that camera against what that camera's own
   reconstruction implies at that pixel (a z-buffer built from the classical,
   triangulated cloud);
3. compare the image colour at that pixel against the colour the point was born
   with.

A point that survives in several views is promoted to
``AI_GEOMETRICALLY_VERIFIED``; one that does not stays ``AI_ASSISTED``.

Why the distinction is not cosmetic
-----------------------------------
"A model produced it" and "several real cameras agree with it" are different
claims, and only the second is evidence. Neither is measurable by default —
verified inferred geometry is *corroborated*, not triangulated, and the roadmap's
rule is that measurement requires multi-view observational support. Promoting it
into the measurable class would be exactly the failure this project exists to
avoid; what promotion buys is an honest middle tier for visualisation and for
deciding where a recapture would actually help.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass
class VerificationResult:
    """Outcome of testing inferred points against the observed reconstruction."""

    verified: np.ndarray          # (N,) bool
    n_views_agreeing: np.ndarray  # (N,) int
    depth_residual: np.ndarray    # (N,) metres, median |predicted - observed|
    color_residual: np.ndarray    # (N,) 0-255, median abs difference

    def summary(self) -> dict:
        n = int(len(self.verified))
        agree = self.n_views_agreeing
        ok = np.isfinite(self.depth_residual)
        return {
            "n_inferred": n,
            "n_verified": int(self.verified.sum()),
            "verified_fraction": float(self.verified.mean()) if n else None,
            "median_views_agreeing": float(np.median(agree)) if n else None,
            "median_depth_residual_m": (float(np.median(self.depth_residual[ok]))
                                        if ok.any() else None),
            "note": ("Verified inferred points are corroborated by independent "
                     "views, not triangulated. They remain excluded from "
                     "measurement by default."),
        }


def _depth_and_color_buffers(points, colors, cam, K, size, scale=0.25,
                             dilate=2):
    """Nearest-depth and colour buffers of the *observed* cloud for one camera.

    Built from the classical, triangulated points only — the whole point is to
    test inferred geometry against something independent of it. Dilated for the
    same reason as in :mod:`coverage`: a sparse cloud leaves gaps that a sight
    line would otherwise slip through, which here would wrongly report agreement
    by finding no occluder at all.
    """
    w = max(int(size[0] * scale), 8)
    h = max(int(size[1] * scale), 8)
    depth = np.full((h, w), np.inf, np.float32)
    color = np.zeros((h, w, 3), np.float32)

    R = np.asarray(cam.R, float)
    t = np.asarray(cam.t, float).ravel()
    pc = (R @ np.asarray(points, float).T).T + t
    z = pc[:, 2]
    front = z > 1e-6
    if not front.any():
        return depth, color, w, h
    p = pc[front]
    u = (K[0, 0] * p[:, 0] / p[:, 2] + K[0, 2]) * scale
    v = (K[1, 1] * p[:, 1] / p[:, 2] + K[1, 2]) * scale
    ui = np.floor(u).astype(int)
    vi = np.floor(v).astype(int)
    ok = (ui >= 0) & (ui < w) & (vi >= 0) & (vi < h)
    if not ok.any():
        return depth, color, w, h
    np.minimum.at(depth, (vi[ok], ui[ok]), p[ok, 2].astype(np.float32))
    if colors is not None:
        c = np.asarray(colors, float)[front][ok]
        color[vi[ok], ui[ok]] = c
    if dilate > 0:
        try:
            from scipy.ndimage import minimum_filter
            depth = minimum_filter(depth, size=2 * dilate + 1, mode="nearest")
        except Exception:
            out = depth.copy()
            for dy in range(-dilate, dilate + 1):
                for dx in range(-dilate, dilate + 1):
                    out = np.minimum(out, np.roll(np.roll(depth, dy, 0), dx, 1))
            depth = out
    return depth, color, w, h


def verify_inferred(inferred_pts, inferred_cols, observed_pts, observed_cols,
                    cameras, K, image_size, *,
                    min_views: int = 2,
                    depth_tol_m: float = 1.0,
                    depth_tol_rel: float = 0.05,
                    color_tol: float = 60.0,
                    buffer_scale: float = 0.25) -> VerificationResult:
    """Test each inferred point for agreement with independent views.

    ``depth_tol_m`` / ``depth_tol_rel`` combine into a distance-scaled tolerance:
    a fixed metric tolerance would be far too strict far from the camera and far
    too loose close to it, since depth uncertainty grows with range.

    A view only *votes* if it can see the point at all. A point outside a
    camera's frustum, or behind observed geometry in that camera, is neither
    agreement nor disagreement — counting an occlusion as a failure would punish
    inferred geometry precisely where it is legitimately hidden.
    """
    inferred_pts = np.asarray(inferred_pts, float).reshape(-1, 3)
    n = len(inferred_pts)
    if n == 0 or not len(cameras):
        return VerificationResult(np.zeros(0, bool), np.zeros(0, int),
                                  np.zeros(0), np.zeros(0))
    K = np.asarray(K, float)
    cols = (np.asarray(inferred_cols, float).reshape(-1, 3)
            if inferred_cols is not None else None)

    agree = np.zeros(n, int)
    dres: list[np.ndarray] = []
    cres: list[np.ndarray] = []

    for cam in cameras:
        depth, color, w, h = _depth_and_color_buffers(
            observed_pts, observed_cols, cam, K, image_size, buffer_scale)
        R = np.asarray(cam.R, float)
        t = np.asarray(cam.t, float).ravel()
        pc = (R @ inferred_pts.T).T + t
        z = pc[:, 2]
        front = z > 1e-6
        u = np.full(n, -1.0)
        v = np.full(n, -1.0)
        u[front] = (K[0, 0] * pc[front, 0] / z[front] + K[0, 2]) * buffer_scale
        v[front] = (K[1, 1] * pc[front, 1] / z[front] + K[1, 2]) * buffer_scale
        ui = np.floor(u).astype(int)
        vi = np.floor(v).astype(int)
        inside = front & (ui >= 0) & (ui < w) & (vi >= 0) & (vi < h)
        if not inside.any():
            continue

        obs_z = np.full(n, np.inf)
        obs_z[inside] = depth[vi[inside], ui[inside]]
        # Only pixels where this camera actually reconstructed something can
        # testify about depth.
        testable = inside & np.isfinite(obs_z)
        if not testable.any():
            continue

        tol = depth_tol_m + depth_tol_rel * np.abs(obs_z)
        dz = np.abs(z - obs_z)
        depth_ok = testable & (dz <= tol)

        col_ok = np.ones(n, bool)
        d_col = np.full(n, np.nan)
        if cols is not None:
            got = np.zeros((n, 3))
            got[testable] = color[vi[testable], ui[testable]]
            d_col[testable] = np.abs(got[testable] - cols[testable]).mean(1)
            # A pixel with no observed colour recorded cannot disagree.
            has_col = testable & np.any(got != 0, axis=1)
            col_ok = ~has_col | (d_col <= color_tol)

        agree += (depth_ok & col_ok).astype(int)
        d = np.full(n, np.nan)
        d[testable] = dz[testable]
        dres.append(d)
        cres.append(d_col)

    depth_residual = (np.nanmedian(np.stack(dres, 0), axis=0)
                      if dres else np.full(n, np.nan))
    color_residual = (np.nanmedian(np.stack(cres, 0), axis=0)
                      if cres else np.full(n, np.nan))
    verified = agree >= int(min_views)
    return VerificationResult(verified, agree, depth_residual, color_residual)


def apply_verification(cloud, result: VerificationResult, inferred_mask):
    """Promote verified inferred points to ``AI_GEOMETRICALLY_VERIFIED``.

    Mutates and returns ``cloud``. Only the provenance changes: the points, their
    positions and their (infinite) uncertainty are untouched, because passing a
    consistency test does not turn an inference into a measurement.
    """
    from .provenance import Provenance

    idx = np.where(np.asarray(inferred_mask, bool))[0]
    if len(idx) == 0 or len(result.verified) != len(idx):
        return cloud
    promote = idx[result.verified]
    if len(promote):
        cloud.provenance[promote] = int(Provenance.AI_GEOMETRICALLY_VERIFIED)
    return cloud
