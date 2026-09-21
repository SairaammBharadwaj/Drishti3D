"""Propagated measurement uncertainty, and its empirical calibration.

Why this module exists
----------------------
The shipped per-point "confidence" is a hand-weighted blend of track length,
reprojection error and triangulation angle. It orders points plausibly, but the
number has no units and no empirical meaning: nothing establishes that a point
scoring 0.8 is accurate to any particular distance. For a product whose output is
a *measurement*, that is the difference between a decoration and a specification.

This module replaces it with a quantity that can be checked: the covariance of
each 3D point, propagated from the pixel noise and camera geometry that actually
produced it, then carried through to the uncertainty of a distance, height or
area the user measures.

The estimator
-------------
A triangulated point is the least-squares solution of its reprojection
residuals. Near that solution the residual is locally linear in the point
position, so the covariance of the estimate is

    Cov(X) = sigma_px^2 * (J^T J)^-1

where ``J`` stacks the 2x3 derivatives of each observation's projection with
respect to ``X``. This is the standard first-order (Gauss-Newton) propagation.
It captures exactly the geometry that matters: a point seen from a wide
triangulation angle has a well-conditioned ``J^T J`` and a tight covariance; a
point seen from nearly parallel rays has a near-singular one and an enormous
uncertainty along the viewing direction.

What it deliberately does not model
-----------------------------------
* **Camera pose uncertainty.** Poses are treated as fixed. After bundle
  adjustment their errors are correlated with the points in a way a per-point
  marginal cannot express, so including a crude pose term would overstate rigour
  rather than add it. The consequence is that raw intervals are optimistic, which
  is why :func:`calibrate` exists and why its scale factor is applied.
* **Systematic error.** Calibration bias, unmodelled distortion, an uncorrected
  time offset or a lever arm produce errors that are not random across
  observations and will not shrink with more views. Nothing here detects them.

Because of both, a predicted interval is only trustworthy after
:func:`calibrate` has compared it against withheld truth and
:func:`coverage_report` has shown it achieves its stated coverage.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

#: Default assumed image-measurement noise, in pixels (1 sigma). SIFT keypoint
#: localisation on well-textured imagery is typically a few tenths of a pixel;
#: this is deliberately not optimistic.
DEFAULT_SIGMA_PX = 0.5


@dataclass
class PointUncertainty:
    """Per-point positional uncertainty in the reconstruction frame."""

    cov: np.ndarray               # (N,3,3) covariance matrices
    sigma: np.ndarray             # (N,) isotropic-equivalent 1-sigma, metres
    sigma_major: np.ndarray       # (N,) 1-sigma along the worst-constrained axis
    major_axis: np.ndarray        # (N,3) unit vector of that axis
    condition: np.ndarray         # (N,) anisotropy: sigma_major / sigma_minor
    observable: np.ndarray        # (N,) bool: enough well-conditioned views
    sigma_px: float = DEFAULT_SIGMA_PX
    scale_factor: float = 1.0     # applied calibration multiplier

    def __len__(self) -> int:
        return int(self.sigma.shape[0])

    def to_dict(self) -> dict:
        s = self.sigma[self.observable] if self.observable.any() else self.sigma
        return {
            "n_points": len(self),
            "n_observable": int(self.observable.sum()),
            "sigma_px_assumed": float(self.sigma_px),
            "calibration_scale_factor": float(self.scale_factor),
            "sigma_m": {
                "median": float(np.median(s)) if len(s) else None,
                "p90": float(np.percentile(s, 90)) if len(s) else None,
                "max": float(s.max()) if len(s) else None,
            },
        }


def projection_jacobians(points, rvecs, tvecs, K):
    """d(u,v)/dX for each observation: returns ``(M,2,3)``.

    ``points``/``rvecs``/``tvecs`` are per-observation (already gathered), so
    this is a flat vectorised evaluation rather than a loop over cameras.
    """
    from .bundle import rotate

    points = np.asarray(points, float)
    rvecs = np.asarray(rvecs, float)
    tvecs = np.asarray(tvecs, float)
    K = np.asarray(K, float)
    fx, fy = float(K[0, 0]), float(K[1, 1])

    p_cam = rotate(points, rvecs) + tvecs
    z = p_cam[:, 2]
    z = np.where(np.abs(z) < 1e-9, np.sign(z) * 1e-9 + 1e-12, z)
    inv_z = 1.0 / z
    xn = p_cam[:, 0] * inv_z
    yn = p_cam[:, 1] * inv_z

    m = len(points)
    # d(u,v)/d(p_cam)
    d_uv = np.zeros((m, 2, 3))
    d_uv[:, 0, 0] = fx * inv_z
    d_uv[:, 0, 2] = -fx * xn * inv_z
    d_uv[:, 1, 1] = fy * inv_z
    d_uv[:, 1, 2] = -fy * yn * inv_z

    # d(p_cam)/dX = R, built per observation from its Rodrigues vector
    R = np.stack([rotate(np.eye(3), np.tile(r, (3, 1))).T for r in rvecs])
    return d_uv @ R


def point_covariances(points, cam_idx, pt_idx, uv, rvecs, tvecs, K, *,
                      sigma_px: float = DEFAULT_SIGMA_PX,
                      min_obs: int = 2,
                      max_sigma: float = 1e3) -> PointUncertainty:
    """First-order covariance of every triangulated point.

    ``uv`` is accepted for interface symmetry with the bundle-adjustment arrays
    and to make the call site obvious; the covariance of a least-squares estimate
    depends on the geometry and the noise model, not on the residual values.
    """
    points = np.asarray(points, float).reshape(-1, 3)
    cam_idx = np.asarray(cam_idx, int).ravel()
    pt_idx = np.asarray(pt_idx, int).ravel()
    rvecs = np.asarray(rvecs, float).reshape(-1, 3)
    tvecs = np.asarray(tvecs, float).reshape(-1, 3)
    n = len(points)

    J = projection_jacobians(points[pt_idx], rvecs[cam_idx], tvecs[cam_idx], K)
    # Normal-equation matrix per point: sum over its observations of J^T J.
    blocks = np.einsum("mij,mik->mjk", J, J)
    info = np.zeros((n, 3, 3))
    np.add.at(info, pt_idx, blocks)

    counts = np.bincount(pt_idx, minlength=n)
    cov = np.full((n, 3, 3), np.nan)
    sigma = np.full(n, np.inf)
    sigma_major = np.full(n, np.inf)
    major_axis = np.zeros((n, 3))
    condition = np.full(n, np.inf)
    observable = np.zeros(n, bool)

    ok = counts >= min_obs
    if ok.any():
        idx = np.where(ok)[0]
        A = info[idx]
        # Eigen-decomposition rather than a plain inverse: it is stable for the
        # near-singular case (parallel rays) and directly yields the worst-
        # constrained direction, which is the number a user should be shown.
        evals, evecs = np.linalg.eigh(A)
        evals = np.maximum(evals, 0.0)
        tiny = evals <= (evals.max(axis=1, keepdims=True) * 1e-12)
        inv_evals = np.where(tiny, np.inf, 1.0 / np.where(tiny, 1.0, evals))
        var = sigma_px ** 2 * inv_evals                    # variance per axis
        finite = np.isfinite(var).all(axis=1)

        cov_idx = np.einsum("nij,nj,nkj->nik", evecs, var, evecs,
                            optimize=True)
        cov[idx] = np.where(finite[:, None, None], cov_idx, np.nan)

        # eigh returns ascending eigenvalues -> the smallest eigenvalue is the
        # worst-constrained direction (largest variance).
        s_major = np.sqrt(var[:, 0])
        s_minor = np.sqrt(var[:, 2])
        sigma[idx] = np.where(finite, np.sqrt(var.sum(axis=1) / 3.0), np.inf)
        sigma_major[idx] = np.where(finite, s_major, np.inf)
        major_axis[idx] = evecs[:, :, 0]
        with np.errstate(divide="ignore", invalid="ignore"):
            condition[idx] = np.where(s_minor > 0, s_major / s_minor, np.inf)
        observable[idx] = finite & (s_major <= max_sigma)

    return PointUncertainty(cov=cov, sigma=sigma, sigma_major=sigma_major,
                            major_axis=major_axis, condition=condition,
                            observable=observable, sigma_px=float(sigma_px))


def transform_covariances(cov: np.ndarray, scale: float, R: np.ndarray) -> np.ndarray:
    """Push covariances through a similarity ``y = s R x + t``.

    Translation drops out; the covariance transforms as ``s^2 R C R^T``.
    """
    cov = np.asarray(cov, float)
    R = np.asarray(R, float)
    return (scale ** 2) * np.einsum("ij,njk,lk->nil", R, cov, R, optimize=True)


# --------------------------------------------------------------------------- #
# measurement-level propagation
# --------------------------------------------------------------------------- #
def distance_uncertainty(a, b, cov_a, cov_b, *, scale_sigma_rel: float = 0.0
                         ) -> tuple[float, float]:
    """1-sigma uncertainty of the distance ``|b - a|``.

    Returns ``(distance, sigma)``.

    Two terms, and for survey work the second usually dominates:

    * **Endpoint geometry.** Only the component of each endpoint's covariance
      *along the measurement direction* matters — error perpendicular to the line
      barely changes its length.
    * **Metric scale.** A relative scale error multiplies the whole distance, so
      it contributes ``d * sigma_scale/scale``. This grows with the measurement
      while the endpoint term does not, so long baselines are scale-limited.
    """
    a = np.asarray(a, float).ravel()
    b = np.asarray(b, float).ravel()
    d_vec = b - a
    d = float(np.linalg.norm(d_vec))
    if d < 1e-12:
        return 0.0, float("inf")
    u = d_vec / d
    var = 0.0
    for c in (cov_a, cov_b):
        if c is None:
            continue
        c = np.asarray(c, float)
        if not np.all(np.isfinite(c)):
            return d, float("inf")
        var += float(u @ c @ u)
    var += (d * float(scale_sigma_rel)) ** 2
    return d, float(np.sqrt(max(var, 0.0)))


def polyline_length_uncertainty(points, covs, *, scale_sigma_rel: float = 0.0
                                ) -> tuple[float, float]:
    """1-sigma uncertainty of the total length of a polyline.

    Returns ``(length, sigma)``.

    Summing per-segment variances is wrong twice over, and both errors make the
    answer look better than it is:

    * **Scale is common to the whole line.** One scale error stretches every
      segment together, so it contributes ``L * sigma_scale`` to the total, not
      an independent term per segment. Summed in quadrature, splitting a 10 m
      line at its midpoint dropped its scale-only sigma from 1.000 m to
      0.707 m -- inserting a vertex manufactured confidence about a line whose
      geometry had not changed.
    * **Interior vertices are shared.** A vertex ends one segment and begins the
      next, so its error enters both. Treating the segments as independent
      double-counts it.

    Both are fixed by propagating the length function itself. For
    ``L = sum |p_{i+1} - p_i|`` the derivative with respect to an interior
    vertex is ``u_{i-1} - u_i`` (the difference of the adjacent unit vectors),
    which vanishes when the vertex lies straight between its neighbours: a
    point added along a straight line contributes nothing, which is the
    behaviour the counterexample above should have had. At a corner the two
    directions do not cancel and the vertex contributes in proportion to how
    sharply the line turns.

    Endpoint covariances are still assumed independent *of each other*. That
    remains an assumption -- neighbouring triangulated points share cameras and
    so share some error -- but it is now the only one, and it is stated.
    """
    P = np.asarray(points, float).reshape(len(points), 3)
    if len(P) < 2:
        return 0.0, float("inf")

    seg = P[1:] - P[:-1]
    lens = np.linalg.norm(seg, axis=1)
    length = float(lens.sum())
    if length < 1e-12:
        return 0.0, float("inf")
    if np.any(lens < 1e-12):
        # A zero-length segment has no direction, so dL/dp is undefined there.
        return length, float("inf")
    u = seg / lens[:, None]

    # dL/dp_i, vertex by vertex: -u_0 at the start, u_{n-1} at the end, and
    # u_{i-1} - u_i in between.
    grad = np.zeros_like(P)
    grad[0] = -u[0]
    grad[-1] = u[-1]
    if len(P) > 2:
        grad[1:-1] = u[:-1] - u[1:]

    var = 0.0
    for g, c in zip(grad, covs):
        if c is None:
            continue
        c = np.asarray(c, float)
        if not np.all(np.isfinite(c)):
            return length, float("inf")
        var += float(g @ c @ g)

    var += (length * float(scale_sigma_rel)) ** 2
    return length, float(np.sqrt(max(var, 0.0)))


def height_uncertainty(a, b, cov_a, cov_b, *, scale_sigma_rel: float = 0.0
                       ) -> tuple[float, float]:
    """1-sigma uncertainty of a vertical difference (the ENU up component)."""
    a = np.asarray(a, float).ravel()
    b = np.asarray(b, float).ravel()
    h = float(abs(b[2] - a[2]))
    var = 0.0
    for c in (cov_a, cov_b):
        if c is None:
            continue
        c = np.asarray(c, float)
        if not np.all(np.isfinite(c)):
            return h, float("inf")
        var += float(c[2, 2])
    var += (h * float(scale_sigma_rel)) ** 2
    return h, float(np.sqrt(max(var, 0.0)))


def area_uncertainty(points, covs, *, scale_sigma_rel: float = 0.0
                     ) -> tuple[float, float]:
    """1-sigma uncertainty of a planar polygon area.

    Propagated through the shoelace formula by finite differences on the vertex
    positions, which is simpler and less error-prone than the closed form and
    costs nothing at these sizes. Scale enters quadratically: an area scales as
    ``s^2``, so a relative scale error contributes ``2 * A * sigma_s/s``.
    """
    P = np.asarray(points, float).reshape(-1, 3)
    if len(P) < 3:
        return 0.0, float("inf")

    def _area(Q):
        c = Q.mean(0)
        _, _, vt = np.linalg.svd(Q - c)
        u, v = vt[0], vt[1]
        x = (Q - c) @ u
        y = (Q - c) @ v
        return 0.5 * abs(np.dot(x, np.roll(y, -1)) - np.dot(y, np.roll(x, -1)))

    A = float(_area(P))
    var = 0.0
    eps = 1e-4
    for i, c in enumerate(covs):
        if c is None:
            continue
        c = np.asarray(c, float)
        if not np.all(np.isfinite(c)):
            return A, float("inf")
        for k in range(3):
            Q = P.copy()
            Q[i, k] += eps
            g = (float(_area(Q)) - A) / eps
            var += (g ** 2) * c[k, k]
    var += (2.0 * A * float(scale_sigma_rel)) ** 2
    return A, float(np.sqrt(max(var, 0.0)))


# --------------------------------------------------------------------------- #
# calibration: do the intervals mean what they claim?
# --------------------------------------------------------------------------- #
#: z multipliers for two-sided normal intervals.
_Z = {50: 0.6745, 68: 0.9945, 80: 1.2816, 90: 1.6449, 95: 1.9600, 99: 2.5758}


@dataclass
class CalibrationResult:
    """Empirical check that predicted intervals contain the truth as often as claimed."""

    scale_factor: float                  # multiply sigmas by this to reach nominal
    coverage: dict = field(default_factory=dict)      # level -> observed fraction
    coverage_calibrated: dict = field(default_factory=dict)
    n: int = 0
    median_abs_z: float = float("nan")
    #: Per-level conformal multipliers: ``level -> k`` such that the interval
    #: ``value +/- k*sigma`` contained the truth for that fraction of the
    #: calibration set. Distribution-free, unlike the Gaussian ``scale_factor``.
    conformal_factors: dict = field(default_factory=dict)
    coverage_conformal: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {"n": self.n, "scale_factor": self.scale_factor,
                "median_abs_z": self.median_abs_z,
                "coverage_raw": self.coverage,
                "coverage_calibrated": self.coverage_calibrated,
                "conformal_factors": self.conformal_factors,
                "coverage_conformal": self.coverage_conformal}

    def interval(self, sigma: float, level: int = 95) -> float:
        """Half-width of the calibrated interval for a predicted ``sigma``.

        Prefers the conformal multiplier when one has been fitted, because it
        makes no distributional assumption; falls back to the Gaussian one.
        """
        if not np.isfinite(sigma):
            return float("inf")
        k = self.conformal_factors.get(int(level))
        if k is None:
            k = _Z.get(int(level), 1.96) * self.scale_factor
        return float(k) * float(sigma)


def coverage_report(errors, sigmas, *, levels=(50, 80, 95)) -> dict:
    """Fraction of cases where |error| falls inside each nominal interval."""
    errors = np.abs(np.asarray(errors, float).ravel())
    sigmas = np.asarray(sigmas, float).ravel()
    ok = np.isfinite(errors) & np.isfinite(sigmas) & (sigmas > 0)
    if not ok.any():
        return {int(l): None for l in levels}
    e, s = errors[ok], sigmas[ok]
    return {int(l): float(np.mean(e <= _Z[l] * s)) for l in levels}


def conformal_factors(errors, sigmas, *, levels=(50, 80, 95)) -> dict:
    """Distribution-free multipliers achieving each nominal coverage level.

    For level *L*, the multiplier is the *L*-th percentile of the normalised
    residual ``|error| / sigma`` (with the standard finite-sample adjustment
    ``ceil((n+1)L)/n``). Using ``k * sigma`` as the half-width then contains the
    truth for at least *L* of the calibration set, by construction.

    This is preferred over scaling a Gaussian because measurement error here is
    not Gaussian: unmodelled distortion, pose error and calibration bias produce
    a heavier tail, so one scale factor that fixes the median leaves the 95%
    level badly under-covered.
    """
    errors = np.abs(np.asarray(errors, float).ravel())
    sigmas = np.asarray(sigmas, float).ravel()
    ok = np.isfinite(errors) & np.isfinite(sigmas) & (sigmas > 0)
    n = int(ok.sum())
    if n < 3:
        return {}
    z = np.sort(errors[ok] / sigmas[ok])
    out = {}
    for lvl in levels:
        q = min(1.0, np.ceil((n + 1) * (lvl / 100.0)) / n)
        out[int(lvl)] = float(np.quantile(z, q, method="higher"))
    return out


def calibrate(errors, sigmas, *, levels=(50, 80, 95),
              target: int = 68) -> CalibrationResult:
    """Find the multipliers that make predicted sigmas match observed error.

    Returns both:

    * ``scale_factor`` — a single robust Gaussian multiplier (median of
      ``|error|/sigma`` over the normal median 0.6745). Robust to outliers, but
      it can only match one point of the distribution.
    * ``conformal_factors`` — a per-level, distribution-free multiplier. Use
      these for published intervals; see :func:`conformal_factors`.

    A ``scale_factor`` > 1 means the raw model is **optimistic**, the expected
    direction here since pose uncertainty and systematic error are not modelled.
    """
    errors = np.abs(np.asarray(errors, float).ravel())
    sigmas = np.asarray(sigmas, float).ravel()
    ok = np.isfinite(errors) & np.isfinite(sigmas) & (sigmas > 0)
    if ok.sum() < 3:
        return CalibrationResult(scale_factor=1.0, n=int(ok.sum()))
    e, s = errors[ok], sigmas[ok]
    z = e / s
    med = float(np.median(z))
    factor = med / _Z[50] if med > 0 else 1.0
    kf = conformal_factors(e, s, levels=levels)
    cov_conf = {int(l): float(np.mean(e <= kf[int(l)] * s)) for l in levels if int(l) in kf}
    return CalibrationResult(
        scale_factor=float(factor),
        coverage=coverage_report(e, s, levels=levels),
        coverage_calibrated=coverage_report(e, s * factor, levels=levels),
        n=int(ok.sum()), median_abs_z=med,
        conformal_factors=kf, coverage_conformal=cov_conf)


def meets_requirement(value: float, sigma: float, tolerance: float, *,
                      level: int = 95) -> tuple[bool, str]:
    """Can this measurement be trusted to the requested tolerance?

    Returns ``(ok, explanation)``. A measurement whose interval is wider than the
    mission tolerance should be refused rather than reported, which is the whole
    point of carrying uncertainty: the system knows when it does not know.
    """
    if not np.isfinite(sigma):
        return False, "uncertainty is not finite (point is not observable)"
    half = _Z.get(level, 1.96) * float(sigma)
    if half <= tolerance:
        return True, f"{level}% interval +/-{half:.3f} m within +/-{tolerance:.3f} m"
    return False, (f"{level}% interval +/-{half:.3f} m exceeds the required "
                   f"+/-{tolerance:.3f} m")
