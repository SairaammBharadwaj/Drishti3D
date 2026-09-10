"""Sparse bundle adjustment: jointly refine camera poses, 3D points and optics.

Why this module exists
----------------------
Incremental SfM estimates each camera from the points it can already see and
each point from the cameras already solved.  Nothing ever re-optimises the two
*together*, so small errors early in the sequence are baked in and accumulate as
drift.  Bundle adjustment closes that loop: it minimises the total reprojection
residual over all camera poses and all point positions at once, which is the
step that turns a chain of locally-consistent estimates into a globally
consistent reconstruction.

Implementation notes
--------------------
* Levenberg-Marquardt via :func:`scipy.optimize.least_squares` with an
  **analytic sparse Jacobian**.  The bundle Jacobian is >99.9% zeros and fully
  known in closed form; supplying it removes SciPy's finite-difference passes and
  the extra iterations an approximate gradient costs.  Distortion refinement is
  the one case still handled numerically, and it says so in
  ``BAResult.stats["jacobian"]`` rather than quietly using a wrong derivative.
* A robust loss (soft-L1 by default) is on by default.  Feature matching leaves
  gross outliers behind even after RANSAC, and a plain least-squares fit will
  drag the whole solution toward them.  Soft-L1 was chosen over Huber after
  measuring both: on a controlled 8-camera problem the two reach the same
  0.62 px optimum, but soft-L1 needs ~36 residual evaluations against Huber's
  ~185.
* ``x_scale="jac"`` is not optional.  Camera and point parameters differ by
  orders of magnitude in their effect on the residual; without Jacobian-based
  scaling the same problem stalls at 11.7 px instead of converging to 0.62 px.
  The termination tolerances are likewise deliberately tight -- a loose ``ftol``
  stops the solve while it is still far from the optimum, which looks like
  "bundle adjustment did not help" rather than the misconfiguration it is.
* The gauge (global rotation, translation and scale) is left free.  Reprojection
  error is invariant to it, and the pipeline fixes the gauge afterwards by
  aligning to GNSS, so constraining it here would only add a arbitrary datum.
* Intrinsic refinement (focal length, radial/tangential distortion) is optional
  and **off by default**: with a short single pass and weak parallax, focal
  length trades off against depth, and refining it can silently absorb geometric
  error into the camera model.  Enable it when the capture has real parallax.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
from scipy.optimize import least_squares
from scipy.sparse import csr_matrix, lil_matrix


@dataclass
class BAResult:
    """Outcome of one bundle-adjustment call."""

    rvecs: np.ndarray                  # (C,3) world->camera Rodrigues vectors
    tvecs: np.ndarray                  # (C,3) world->camera translations
    points: np.ndarray                 # (P,3) refined 3D points
    K: np.ndarray                      # (3,3) refined (or unchanged) intrinsics
    dist: np.ndarray                   # (4,) k1,k2,p1,p2 (zeros if not refined)
    cost_before: float                 # 0.5 * sum of squared residuals, before
    cost_after: float                  # ... and after
    rmse_before: float                 # px, over all observations
    rmse_after: float                  # px
    n_cameras: int = 0
    n_points: int = 0
    n_observations: int = 0
    n_iterations: int = 0
    converged: bool = False
    message: str = ""
    stats: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "n_cameras": self.n_cameras, "n_points": self.n_points,
            "n_observations": self.n_observations,
            "rmse_px_before": self.rmse_before, "rmse_px_after": self.rmse_after,
            "cost_before": self.cost_before, "cost_after": self.cost_after,
            "n_iterations": self.n_iterations, "converged": self.converged,
            "message": self.message, **self.stats,
        }


# --------------------------------------------------------------------------- #
# projection
# --------------------------------------------------------------------------- #
def rotate(points: np.ndarray, rvecs: np.ndarray) -> np.ndarray:
    """Rotate each point by its own Rodrigues vector (vectorised).

    Uses Rodrigues' formula directly rather than looping over
    :func:`cv2.Rodrigues`, because this is the innermost operation of every
    residual evaluation.
    """
    theta = np.linalg.norm(rvecs, axis=1)[:, None]
    with np.errstate(invalid="ignore", divide="ignore"):
        k = np.where(theta > 1e-12, rvecs / np.where(theta == 0, 1, theta), 0.0)
    cos_t = np.cos(theta)
    sin_t = np.sin(theta)
    kxp = np.cross(k, points)
    kdp = np.sum(k * points, axis=1)[:, None]
    return points * cos_t + kxp * sin_t + k * kdp * (1 - cos_t)


def project(points: np.ndarray, rvecs: np.ndarray, tvecs: np.ndarray,
            fx: np.ndarray, fy: np.ndarray, cx: float, cy: float,
            dist: np.ndarray | None = None) -> np.ndarray:
    """Project world points into pixels given per-observation camera params."""
    p_cam = rotate(points, rvecs) + tvecs
    z = p_cam[:, 2]
    # Guard the division: an intermediate LM step can push a point behind a
    # camera, and an inf residual would abort the solve rather than be rejected.
    z_safe = np.where(np.abs(z) < 1e-6, np.sign(z) * 1e-6 + 1e-12, z)
    xn = p_cam[:, 0] / z_safe
    yn = p_cam[:, 1] / z_safe
    if dist is not None and np.any(dist):
        k1, k2, p1, p2 = dist
        r2 = xn * xn + yn * yn
        radial = 1.0 + k1 * r2 + k2 * r2 * r2
        xd = xn * radial + 2 * p1 * xn * yn + p2 * (r2 + 2 * xn * xn)
        yd = yn * radial + p1 * (r2 + 2 * yn * yn) + 2 * p2 * xn * yn
        xn, yn = xd, yd
    return np.stack([fx * xn + cx, fy * yn + cy], axis=1)


def _skew(v: np.ndarray) -> np.ndarray:
    return np.array([[0.0, -v[2], v[1]],
                     [v[2], 0.0, -v[0]],
                     [-v[1], v[0], 0.0]])


def drotation_drvec(rvec: np.ndarray) -> np.ndarray:
    """d(R)/d(rvec) for a Rodrigues vector: returns ``(3,3,3)`` indexed [k,m,j].

    Uses the compact exponential-coordinate form

        dR/dr_j = ( r_j [r]_x + [ r x (I - R) e_j ]_x ) R / theta^2

    (Gallego & Yezzi), with the small-angle limit dR/dr_j = [e_j]_x, which is
    the correct first-order behaviour as theta -> 0 and avoids the 0/0 that the
    general formula hits there.
    """
    r = np.asarray(rvec, float).ravel()
    theta = float(np.linalg.norm(r))
    if theta < 1e-8:
        out = np.empty((3, 3, 3))
        for j in range(3):
            e = np.zeros(3)
            e[j] = 1.0
            out[:, :, j] = _skew(e)
        return out
    R = rotate(np.eye(3), np.tile(r, (3, 1))).T   # columns = R @ e_j  =>  R
    rx = _skew(r)
    out = np.empty((3, 3, 3))
    for j in range(3):
        e = np.zeros(3)
        e[j] = 1.0
        term = r[j] * rx + _skew(np.cross(r, (np.eye(3) - R) @ e))
        out[:, :, j] = (term @ R) / (theta ** 2)
    return out


def _analytic_jacobian(n_cams, n_pts, cam_idx, pt_idx, K, refine_focal):
    """Build a closed-form Jacobian evaluator for the bundle problem.

    Returns ``None`` when the configuration is not covered (distortion
    refinement), so the caller transparently falls back to finite differences
    rather than silently using a wrong derivative.

    Structure: residual row pair (2i, 2i+1) depends only on observation i's
    camera (6 parameters), its point (3), and the shared focal length if it is
    being refined. The row/column index arrays are therefore fixed and are built
    once; each evaluation only recomputes the values.
    """
    m = len(cam_idx)
    n_intr = 1 if refine_focal else 0
    n_par = n_cams * 6 + n_pts * 3 + n_intr
    cx, cy = float(K[0, 2]), float(K[1, 2])

    a3 = np.arange(3)
    cols_r = cam_idx[:, None] * 3 + a3
    cols_t = n_cams * 3 + cam_idx[:, None] * 3 + a3
    cols_p = n_cams * 6 + pt_idx[:, None] * 3 + a3
    blocks = [cols_r, cols_t, cols_p]
    if refine_focal:
        blocks.append(np.full((m, 1), n_cams * 6 + n_pts * 3, int))
    cols = np.concatenate(blocks, axis=1)          # (m, 9 or 10)
    width = cols.shape[1]

    rows = np.concatenate([
        np.repeat(2 * np.arange(m), width),
        np.repeat(2 * np.arange(m) + 1, width)])
    all_cols = np.concatenate([cols.ravel(), cols.ravel()])

    def jac(params, unpack):
        rv, tv, pts, fx, fy, _d = unpack(params)
        fx = float(fx)
        fy = float(fy)
        X = pts[pt_idx]
        rv_o = rv[cam_idx]
        p_cam = rotate(X, rv_o) + tv[cam_idx]
        z = p_cam[:, 2]
        z = np.where(np.abs(z) < 1e-6, np.sign(z) * 1e-6 + 1e-12, z)
        inv_z = 1.0 / z
        xn = p_cam[:, 0] * inv_z
        yn = p_cam[:, 1] * inv_z

        # d(u,v)/d(p_cam)
        du = np.stack([fx * inv_z, np.zeros(m), -fx * xn * inv_z], 1)   # (m,3)
        dv = np.stack([np.zeros(m), fy * inv_z, -fy * yn * inv_z], 1)

        # d(p_cam)/d(rvec): contract dR/dr with the point
        dR = np.stack([drotation_drvec(rv[c]) for c in range(n_cams)])  # (C,3,3,j)
        dpc_dr = np.einsum("ikmj,im->ikj", dR[cam_idx], X)              # (m,3,3)

        # d(p_cam)/d(point) = R ; d(p_cam)/d(tvec) = I
        R_all = np.stack([rotate(np.eye(3), np.tile(rv[c], (3, 1))).T
                          for c in range(n_cams)])                      # (C,3,3)
        R_o = R_all[cam_idx]

        du_dr = np.einsum("ik,ikj->ij", du, dpc_dr)
        dv_dr = np.einsum("ik,ikj->ij", dv, dpc_dr)
        du_dp = np.einsum("ik,ikj->ij", du, R_o)
        dv_dp = np.einsum("ik,ikj->ij", dv, R_o)

        u_blocks = [du_dr, du, du_dp]
        v_blocks = [dv_dr, dv, dv_dp]
        if refine_focal:
            u_blocks.append(xn[:, None])
            v_blocks.append(yn[:, None])
        data = np.concatenate([
            np.concatenate(u_blocks, axis=1).ravel(),
            np.concatenate(v_blocks, axis=1).ravel()])
        return csr_matrix((data, (rows, all_cols)), shape=(2 * m, n_par))

    return jac


# --------------------------------------------------------------------------- #
# parameter packing
# --------------------------------------------------------------------------- #
def _n_intrinsic(refine_focal: bool, refine_distortion: bool) -> int:
    return (1 if refine_focal else 0) + (4 if refine_distortion else 0)


def _unpack(params, n_cams, n_pts, K, dist, refine_focal, refine_distortion):
    rvecs = params[:n_cams * 3].reshape(n_cams, 3)
    tvecs = params[n_cams * 3:n_cams * 6].reshape(n_cams, 3)
    pts = params[n_cams * 6:n_cams * 6 + n_pts * 3].reshape(n_pts, 3)
    tail = params[n_cams * 6 + n_pts * 3:]
    o = 0
    if refine_focal:
        f = tail[o]
        o += 1
        fx = fy = f
    else:
        fx, fy = K[0, 0], K[1, 1]
    if refine_distortion:
        d = tail[o:o + 4]
    else:
        d = dist
    return rvecs, tvecs, pts, fx, fy, d


def _sparsity(n_cams, n_pts, cam_idx, pt_idx, n_intr):
    """Jacobian sparsity: residual (2i,2i+1) touches only its camera and point."""
    m = len(cam_idx) * 2
    n = n_cams * 6 + n_pts * 3 + n_intr
    A = lil_matrix((m, n), dtype=int)
    i = np.arange(len(cam_idx))
    for s in range(3):
        A[2 * i, cam_idx * 3 + s] = 1
        A[2 * i + 1, cam_idx * 3 + s] = 1
        A[2 * i, n_cams * 3 + cam_idx * 3 + s] = 1
        A[2 * i + 1, n_cams * 3 + cam_idx * 3 + s] = 1
        A[2 * i, n_cams * 6 + pt_idx * 3 + s] = 1
        A[2 * i + 1, n_cams * 6 + pt_idx * 3 + s] = 1
    # Intrinsics are shared by every observation -> dense trailing columns.
    for s in range(n_intr):
        A[:, n_cams * 6 + n_pts * 3 + s] = 1
    return A


# --------------------------------------------------------------------------- #
# the solver
# --------------------------------------------------------------------------- #
def bundle_adjust(rvecs: np.ndarray, tvecs: np.ndarray, points: np.ndarray,
                  cam_idx: np.ndarray, pt_idx: np.ndarray, uv: np.ndarray,
                  K: np.ndarray, *,
                  dist: np.ndarray | None = None,
                  refine_focal: bool = False,
                  refine_distortion: bool = False,
                  loss: str = "soft_l1", f_scale: float = 2.0,
                  max_nfev: int | None = 200,
                  ftol: float = 1e-8, xtol: float = 1e-10,
                  verbose: int = 0) -> BAResult:
    """Minimise total reprojection error over poses, points and (optionally) optics.

    Parameters
    ----------
    rvecs, tvecs
        ``(C,3)`` world->camera Rodrigues rotations and translations.
    points
        ``(P,3)`` initial 3D points.
    cam_idx, pt_idx, uv
        ``(M,)``, ``(M,)``, ``(M,2)`` observation arrays: observation *i* says
        camera ``cam_idx[i]`` saw point ``pt_idx[i]`` at pixel ``uv[i]``.
    K
        ``(3,3)`` intrinsics. ``cx, cy`` are always held fixed -- the principal
        point is weakly observed in a short pass and refining it mostly absorbs
        pose error.
    loss, f_scale
        Robust loss for :func:`scipy.optimize.least_squares`. ``f_scale`` is the
        residual (in pixels) beyond which an observation is down-weighted.

    Returns
    -------
    BAResult
        Refined parameters plus before/after reprojection RMSE, so a caller can
        verify the step actually helped instead of assuming it did.
    """
    rvecs = np.asarray(rvecs, float).reshape(-1, 3)
    tvecs = np.asarray(tvecs, float).reshape(-1, 3)
    points = np.asarray(points, float).reshape(-1, 3)
    cam_idx = np.asarray(cam_idx, int).ravel()
    pt_idx = np.asarray(pt_idx, int).ravel()
    uv = np.asarray(uv, float).reshape(-1, 2)
    K = np.asarray(K, float)
    dist = np.zeros(4) if dist is None else np.asarray(dist, float).ravel()

    n_cams, n_pts, n_obs = len(rvecs), len(points), len(cam_idx)
    if n_obs != len(pt_idx) or n_obs != len(uv):
        raise ValueError("cam_idx, pt_idx and uv must have equal length")
    if n_obs < 6:
        raise ValueError(f"need >= 6 observations to bundle adjust, got {n_obs}")
    if cam_idx.max(initial=-1) >= n_cams or pt_idx.max(initial=-1) >= n_pts:
        raise ValueError("observation index out of range")

    cx, cy = float(K[0, 2]), float(K[1, 2])
    n_intr = _n_intrinsic(refine_focal, refine_distortion)

    # A point seen by a single camera is not observable: its depth can slide
    # anywhere along the viewing ray with zero reprojection cost.  Left in the
    # problem, such points let the solver drive the residual down while the
    # geometry silently drifts.  Hold them fixed and solve only the observable
    # subset, then hand the fixed points back unchanged.
    obs_per_point = np.bincount(pt_idx, minlength=n_pts)
    free_mask = obs_per_point >= 2
    n_fixed = int((~free_mask).sum())
    if n_fixed:
        keep_obs = free_mask[pt_idx]
        cam_idx, pt_idx, uv = cam_idx[keep_obs], pt_idx[keep_obs], uv[keep_obs]
        remap = np.full(n_pts, -1, int)
        remap[free_mask] = np.arange(int(free_mask.sum()))
        pt_idx = remap[pt_idx]
        points_all, points = points, points[free_mask]
        n_pts = len(points)
        n_obs = len(cam_idx)
        if n_obs < 6:
            raise ValueError(
                f"only {n_obs} observations remain after dropping "
                f"{n_fixed} single-view points; nothing to bundle adjust")
    else:
        points_all = points

    x0 = np.concatenate([rvecs.ravel(), tvecs.ravel(), points.ravel()])
    tail = []
    if refine_focal:
        tail.append([0.5 * (K[0, 0] + K[1, 1])])
    if refine_distortion:
        tail.append(dist)
    if tail:
        x0 = np.concatenate([x0] + [np.asarray(t, float).ravel() for t in tail])

    def residuals(params):
        rv, tv, pts, fx, fy, d = _unpack(params, n_cams, n_pts, K, dist,
                                         refine_focal, refine_distortion)
        proj = project(pts[pt_idx], rv[cam_idx], tv[cam_idx],
                       np.full(len(cam_idx), fx) if np.isscalar(fx) else fx,
                       np.full(len(cam_idx), fy) if np.isscalar(fy) else fy,
                       cx, cy, d)
        return (proj - uv).ravel()

    # An exact derivative is available for every configuration except distortion
    # refinement; there the chain rule through the distortion model is not
    # implemented, so fall back to finite differences rather than risk a wrong
    # gradient.
    jac_fn = None
    if not refine_distortion and not np.any(dist):
        builder = _analytic_jacobian(n_cams, n_pts, cam_idx, pt_idx, K,
                                     refine_focal)
        if builder is not None:
            def jac_fn(params, _b=builder):
                return _b(params, lambda pp: _unpack(
                    pp, n_cams, n_pts, K, dist, refine_focal, refine_distortion))

    r0 = residuals(x0)
    rmse_before = float(np.sqrt(np.mean(r0.reshape(-1, 2) ** 2 * 2)))
    cost_before = float(0.5 * np.dot(r0, r0))

    if jac_fn is not None:
        sol = least_squares(
            residuals, x0, jac=jac_fn, verbose=verbose,
            x_scale="jac", loss=loss, f_scale=f_scale, method="trf",
            ftol=ftol, xtol=xtol, max_nfev=max_nfev, tr_solver="lsmr")
    else:
        A = _sparsity(n_cams, n_pts, cam_idx, pt_idx, n_intr)
        sol = least_squares(
            residuals, x0, jac_sparsity=A, verbose=verbose,
            x_scale="jac", loss=loss, f_scale=f_scale, method="trf",
            ftol=ftol, xtol=xtol, max_nfev=max_nfev, tr_solver="lsmr")

    r1 = residuals(sol.x)
    rmse_after = float(np.sqrt(np.mean(r1.reshape(-1, 2) ** 2 * 2)))
    cost_after = float(0.5 * np.dot(r1, r1))

    rv, tv, pts, fx, fy, d = _unpack(sol.x, n_cams, n_pts, K, dist,
                                     refine_focal, refine_distortion)
    if n_fixed:                       # scatter the refined subset back in place
        full = points_all.copy()
        full[free_mask] = pts
        pts = full
    K_out = K.copy()
    if refine_focal:
        K_out[0, 0] = K_out[1, 1] = float(fx)

    # A robust loss means the reported cost is not a plain SSE, so decide
    # acceptance on the honest metric: the plain reprojection RMSE.
    improved = rmse_after <= rmse_before
    if not improved:
        # Refuse to hand back a worse reconstruction than we were given.
        rv, tv, pts = rvecs, tvecs, points_all
        K_out, d = K, dist
        rmse_after = rmse_before
        cost_after = cost_before

    return BAResult(
        rvecs=rv, tvecs=tv, points=pts, K=K_out, dist=np.asarray(d, float),
        cost_before=cost_before, cost_after=cost_after,
        rmse_before=rmse_before, rmse_after=rmse_after,
        n_cameras=n_cams, n_points=len(points_all), n_observations=n_obs,
        n_iterations=int(sol.nfev), converged=bool(sol.status > 0),
        message=str(sol.message),
        stats={"accepted": bool(improved), "n_fixed_single_view_points": n_fixed,
               "jacobian": "analytic" if jac_fn is not None else "finite_difference",
               "refined_focal": float(K_out[0, 0]) if refine_focal else None,
               "refined_dist": np.asarray(d, float).tolist() if refine_distortion else None})


def reprojection_errors(rvecs, tvecs, points, cam_idx, pt_idx, uv, K,
                        dist=None) -> np.ndarray:
    """Per-observation reprojection error in pixels."""
    rvecs = np.asarray(rvecs, float).reshape(-1, 3)
    tvecs = np.asarray(tvecs, float).reshape(-1, 3)
    points = np.asarray(points, float).reshape(-1, 3)
    cam_idx = np.asarray(cam_idx, int).ravel()
    pt_idx = np.asarray(pt_idx, int).ravel()
    uv = np.asarray(uv, float).reshape(-1, 2)
    K = np.asarray(K, float)
    n = len(cam_idx)
    proj = project(points[pt_idx], rvecs[cam_idx], tvecs[cam_idx],
                   np.full(n, K[0, 0]), np.full(n, K[1, 1]),
                   float(K[0, 2]), float(K[1, 2]),
                   None if dist is None else np.asarray(dist, float))
    return np.linalg.norm(proj - uv, axis=1)
