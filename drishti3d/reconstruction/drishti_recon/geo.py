"""Coordinate transforms and robust metric alignment.

Frames used:
  * WGS84 geodetic  (lat[deg], lon[deg], alt[m ellipsoidal])
  * ECEF            (earth-centred earth-fixed, metres)
  * Local ENU       (east, north, up metres) about a fixed WGS84 origin

Never mix geographic degrees with metric coordinates.  The origin is preserved
so ENU points can be converted back to WGS84.
"""
from __future__ import annotations

from dataclasses import dataclass, field
import numpy as np

try:  # pyproj is a hard dependency but keep import failure legible
    from pyproj import Transformer
    _ECEF = Transformer.from_crs("EPSG:4979", "EPSG:4978", always_xy=True)
    _GEO = Transformer.from_crs("EPSG:4978", "EPSG:4979", always_xy=True)
    _HAVE_PYPROJ = True
except Exception:  # pragma: no cover - fallback below
    _HAVE_PYPROJ = False

# WGS84 ellipsoid constants (used by the pure-numpy fallback).
_A = 6378137.0
_F = 1.0 / 298.257223563
_E2 = _F * (2 - _F)


def geodetic_to_ecef(lat, lon, alt):
    """(lat_deg, lon_deg, alt_m) -> (X, Y, Z) ECEF metres. Vectorised."""
    lat = np.asarray(lat, float)
    lon = np.asarray(lon, float)
    alt = np.asarray(alt, float)
    if _HAVE_PYPROJ:
        x, y, z = _ECEF.transform(lon, lat, alt)
        return np.stack([np.atleast_1d(x), np.atleast_1d(y), np.atleast_1d(z)], -1)
    rlat = np.radians(lat)
    rlon = np.radians(lon)
    n = _A / np.sqrt(1 - _E2 * np.sin(rlat) ** 2)
    x = (n + alt) * np.cos(rlat) * np.cos(rlon)
    y = (n + alt) * np.cos(rlat) * np.sin(rlon)
    z = (n * (1 - _E2) + alt) * np.sin(rlat)
    return np.stack([np.atleast_1d(x), np.atleast_1d(y), np.atleast_1d(z)], -1)


def ecef_to_geodetic(xyz):
    """(N,3) ECEF metres -> (N,3) (lat_deg, lon_deg, alt_m)."""
    xyz = np.atleast_2d(np.asarray(xyz, float))
    if _HAVE_PYPROJ:
        lon, lat, alt = _GEO.transform(xyz[:, 0], xyz[:, 1], xyz[:, 2])
        return np.stack([np.atleast_1d(lat), np.atleast_1d(lon), np.atleast_1d(alt)], -1)
    # Bowring's method
    x, y, z = xyz[:, 0], xyz[:, 1], xyz[:, 2]
    lon = np.arctan2(y, x)
    p = np.hypot(x, y)
    lat = np.arctan2(z, p * (1 - _E2))
    for _ in range(6):
        n = _A / np.sqrt(1 - _E2 * np.sin(lat) ** 2)
        alt = p / np.cos(lat) - n
        lat = np.arctan2(z, p * (1 - _E2 * n / (n + alt)))
    return np.stack([np.degrees(lat), np.degrees(lon), alt], -1)


def _enu_rotation(lat0_deg: float, lon0_deg: float) -> np.ndarray:
    lat0 = np.radians(lat0_deg)
    lon0 = np.radians(lon0_deg)
    sl, cl = np.sin(lat0), np.cos(lat0)
    so, co = np.sin(lon0), np.cos(lon0)
    # rows: East, North, Up in ECEF
    return np.array([
        [-so, co, 0.0],
        [-sl * co, -sl * so, cl],
        [cl * co, cl * so, sl],
    ])


@dataclass
class ENUFrame:
    """A local tangent-plane frame anchored at a WGS84 origin."""

    lat0: float
    lon0: float
    alt0: float
    _origin_ecef: np.ndarray = field(default=None, repr=False)
    _R: np.ndarray = field(default=None, repr=False)

    def __post_init__(self):
        self._origin_ecef = geodetic_to_ecef(self.lat0, self.lon0, self.alt0)[0]
        self._R = _enu_rotation(self.lat0, self.lon0)

    @classmethod
    def from_points(cls, lat, lon, alt) -> "ENUFrame":
        """Anchor at the mean of provided WGS84 points."""
        return cls(float(np.mean(lat)), float(np.mean(lon)), float(np.mean(alt)))

    def geodetic_to_enu(self, lat, lon, alt) -> np.ndarray:
        ecef = geodetic_to_ecef(lat, lon, alt)
        return (self._R @ (ecef - self._origin_ecef).T).T

    def enu_to_geodetic(self, enu) -> np.ndarray:
        enu = np.atleast_2d(np.asarray(enu, float))
        ecef = (self._R.T @ enu.T).T + self._origin_ecef
        return ecef_to_geodetic(ecef)

    def to_dict(self) -> dict:
        return {"lat0": self.lat0, "lon0": self.lon0, "alt0": self.alt0}


@dataclass
class Sim3:
    """Similarity transform y = s * R @ x + t (source -> target)."""

    scale: float
    R: np.ndarray
    t: np.ndarray

    def apply(self, pts) -> np.ndarray:
        pts = np.atleast_2d(np.asarray(pts, float))
        return self.scale * (self.R @ pts.T).T + self.t

    def to_dict(self) -> dict:
        return {"scale": float(self.scale), "R": self.R.tolist(), "t": self.t.tolist()}


def umeyama_sim3(src: np.ndarray, dst: np.ndarray, with_scale: bool = True,
                 weights=None) -> Sim3:
    """Least-squares similarity aligning src->dst (Umeyama 1991).

    ``weights`` (optional, ``(N,)``) are per-correspondence weights.  For GNSS
    correspondences the correct weight is **inverse variance**, ``1/sigma**2``,
    not ``1/sigma``: a fix twice as noisy should count a quarter as much, not
    half as much.  Weights are the standard extension of Umeyama's closed form --
    every mean, covariance and variance below becomes its weighted counterpart.
    """
    src = np.asarray(src, float)
    dst = np.asarray(dst, float)
    n = src.shape[0]
    if weights is None:
        w = np.ones(n)
    else:
        w = np.asarray(weights, float).ravel()
        if w.shape[0] != n:
            raise ValueError(f"weights has length {w.shape[0]}, expected {n}")
        if np.any(w < 0):
            raise ValueError("weights must be non-negative")
    wsum = float(w.sum())
    if wsum <= 0:
        raise ValueError("weights sum to zero")
    w = w / wsum                                  # normalised, so W == 1

    mu_s = (w[:, None] * src).sum(0)
    mu_d = (w[:, None] * dst).sum(0)
    sc = src - mu_s
    dc = dst - mu_d
    cov = (dc * w[:, None]).T @ sc
    u, d, vt = np.linalg.svd(cov)
    s = np.eye(3)
    if np.linalg.det(u) * np.linalg.det(vt) < 0:
        s[2, 2] = -1
    R = u @ s @ vt
    if with_scale:
        var_s = float((w[:, None] * sc ** 2).sum())
        scale = float((d * np.diag(s)).sum() / max(var_s, 1e-12))
    else:
        scale = 1.0
    t = mu_d - scale * R @ mu_s
    return Sim3(scale, R, t)


@dataclass
class Sim3Result:
    transform: Sim3
    inliers: np.ndarray            # boolean mask over correspondences
    rmse: float                    # 3D RMSE over inliers (metres)
    rmse_h: float                  # horizontal RMSE (metres)
    rmse_v: float                  # vertical RMSE (metres)
    n_inliers: int
    n_total: int
    # --- uncertainty and conditioning (added with weighted alignment) -------
    #: RMS of Mahalanobis residuals over inliers.  Dimensionless: ~1.0 means the
    #: fit is consistent with the stated GNSS sigmas, >>1 means the residuals are
    #: larger than the receiver claims (bad sync, lever arm, or optimistic
    #: accuracy figures), <<1 means the sigmas are pessimistic.
    normalized_rmse: float | None = None
    #: 1-sigma uncertainty of the recovered metric scale, from the fit geometry.
    scale_sigma: float | None = None
    #: True when the camera track cannot constrain all 7 DOF (e.g. a straight
    #: line, or a constant-altitude pass).  The transform is still returned, but
    #: its unconstrained directions are not trustworthy.
    degenerate: bool = False
    degeneracy: str | None = None
    #: Diagnostics: trajectory extent along its principal axes, and the weighting
    #: actually used.
    conditioning: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "scale": float(self.transform.scale),
            "n_inliers": int(self.n_inliers), "n_total": int(self.n_total),
            "alignment_rmse_3d_m": self.rmse,
            "alignment_rmse_horizontal_m": self.rmse_h,
            "alignment_rmse_vertical_m": self.rmse_v,
            "normalized_rmse": self.normalized_rmse,
            "scale_sigma": self.scale_sigma,
            "degenerate": self.degenerate, "degeneracy": self.degeneracy,
            "conditioning": self.conditioning,
        }


def level_rotation(points, *, dist_thresh: float = 1.0, iters: int = 500,
                   max_angle_deg: float = 80.0, min_frac: float = 0.35):
    """Estimate a small rotation that makes the dominant (ground) plane horizontal.

    Nadir mapping flights fly at near-constant altitude, so GPS barely constrains
    the vertical axis and the reconstruction can come out tilted.  We fit the
    dominant plane (the ground) and return the rotation that brings its normal to
    +Z (up), correcting the tilt while preserving horizontal orientation.
    Returns a (3,3) rotation, or None if no confident/plausible correction found.
    """
    points = np.asarray(points, float)
    if len(points) < 200:
        return None
    try:
        import open3d as o3d
    except Exception:
        return None
    pc = o3d.geometry.PointCloud()
    pc.points = o3d.utility.Vector3dVector(points)
    try:
        model, inliers = pc.segment_plane(dist_thresh, 3, iters)
    except Exception:
        return None
    if len(inliers) < min_frac * len(points):
        return None
    n = np.asarray(model[:3], float)
    n /= (np.linalg.norm(n) + 1e-12)
    if n[2] < 0:
        n = -n
    z = np.array([0.0, 0.0, 1.0])
    cos_a = float(np.clip(n @ z, -1, 1))
    ang = np.degrees(np.arccos(cos_a))
    if ang < 1.0 or ang > max_angle_deg:
        return None  # already level, or an implausible correction (not the ground)
    axis = np.cross(n, z)
    axis /= (np.linalg.norm(axis) + 1e-12)
    s = np.sin(np.radians(ang))
    c = np.cos(np.radians(ang))
    Kx = np.array([[0, -axis[2], axis[1]],
                   [axis[2], 0, -axis[0]],
                   [-axis[1], axis[0], 0]])
    return np.eye(3) + s * Kx + (1 - c) * (Kx @ Kx)


def _sigmas_from_weights(weights, n, sigma_h, sigma_v, default_h, default_v):
    """Normalise the several ways a caller can express GNSS uncertainty.

    Returns ``(sigma_h[n], sigma_v[n], source)`` in metres.  Accepts explicit
    per-point sigmas, or legacy ``weights`` where ``weight == 1/sigma_h``.
    """
    if sigma_h is not None:
        sh = np.broadcast_to(np.asarray(sigma_h, float), (n,)).astype(float).copy()
        source = "explicit_sigma"
    elif weights is not None:
        w = np.asarray(weights, float).ravel()
        if w.shape[0] != n:
            raise ValueError(f"weights has length {w.shape[0]}, expected {n}")
        # Legacy contract: callers pass 1/gps_accuracy, i.e. 1/sigma.
        with np.errstate(divide="ignore", invalid="ignore"):
            sh = np.where(w > 0, 1.0 / np.where(w > 0, w, 1.0), default_h)
        source = "weights_as_inverse_sigma"
    else:
        sh = np.full(n, float(default_h))
        source = "uniform_default"

    bad = ~np.isfinite(sh) | (sh <= 0)
    if bad.any():
        sh[bad] = float(default_h)

    if sigma_v is not None:
        sv = np.broadcast_to(np.asarray(sigma_v, float), (n,)).astype(float).copy()
    else:
        # A GNSS receiver's vertical error is characteristically worse than its
        # horizontal error; trusting altitude equally is the classic way to tilt
        # a reconstruction.  1.6x is the conventional planning ratio (VDOP/HDOP).
        sv = sh * 1.6
    bad = ~np.isfinite(sv) | (sv <= 0)
    if bad.any():
        sv[bad] = float(default_v)
    return sh, sv, source


def _robust_sigma(residuals: np.ndarray) -> float:
    """Robust 1-sigma scale of a residual distribution (normalised MAD).

    The median absolute deviation is used rather than the standard deviation
    because the input is expected to contain the very outliers we are trying to
    reject; an SD would be inflated by them and defeat the purpose.
    """
    r = np.asarray(residuals, float).ravel()
    r = r[np.isfinite(r)]
    if r.size == 0:
        return 0.0
    mad = float(np.median(np.abs(r - np.median(r))))
    return 1.4826 * mad


def _trajectory_conditioning(pts: np.ndarray) -> tuple[bool, str | None, dict]:
    """Can this camera track constrain a full 7-DOF similarity?

    A straight flight line leaves the roll about that line unobservable; a
    constant-altitude pass constrains the vertical scale only through the (much
    weaker) horizontal geometry.  Both are normal drone captures, so this is
    detected and reported rather than treated as an error.
    """
    c = pts - pts.mean(0)
    if len(pts) < 3:
        return True, "fewer than 3 correspondences", {}
    sv = np.linalg.svd(c, compute_uv=False) / np.sqrt(len(pts))
    extent = sv.tolist()
    info = {"principal_extent_m": [float(x) for x in extent],
            "vertical_extent_m": float(np.ptp(pts[:, 2]))}
    if sv[0] < 1e-9:
        return True, "all correspondences coincide", info
    # ratios of the 2nd/3rd principal extents to the 1st
    r1 = float(sv[1] / sv[0])
    r2 = float(sv[2] / sv[0])
    info["extent_ratios"] = [r1, r2]
    if r1 < 0.02:
        return True, "collinear trajectory (rotation about the flight line is unobservable)", info
    if r2 < 0.02:
        return True, "planar trajectory (out-of-plane geometry is weakly constrained)", info
    return False, None, info


def robust_sim3(src: np.ndarray, dst: np.ndarray, *, weights=None,
                sigma_h=None, sigma_v=None,
                iters: int = 500, threshold: float = 2.0,
                n_sigma: float = 3.0,
                default_sigma_h: float = 2.5, default_sigma_v: float = 4.0,
                refine: bool = True,
                min_samples: int = 3, seed: int = 0) -> Sim3Result:
    """Uncertainty-weighted robust Sim(3) aligning camera centres to GNSS ENU.

    Previously ``weights`` was accepted and then never read, so a reported GNSS
    accuracy had no effect on the solution.  It now drives three things:

    1. **Inlier scoring is normalised.** A correspondence is judged by its
       Mahalanobis distance rather than by a single metric threshold.  A 3 m
       residual on a 10 m-accuracy fix is consistent; the same residual on an RTK
       fix is not, and one absolute threshold in metres cannot express that.

       The normalising sigma is the *total* expected residual,
       ``sqrt(sigma_gnss^2 + sigma_recon^2)``, where ``sigma_recon`` is estimated
       robustly from a first permissive fit.  Gating on the GNSS sigma alone
       assumes the reconstruction is exact; measured on the benchmark, that
       assumption discarded good correspondences and made metric scale error
       worse on well-reconstructed captures.
    2. **The refit is inverse-variance weighted**, so precise fixes pull harder.
    3. **Horizontal and vertical are separated.** GNSS altitude is
       characteristically worse than horizontal position, and weighting them
       equally tilts the reconstruction.

    ``weights`` keeps its legacy meaning (``1/sigma_h``); prefer passing
    ``sigma_h`` / ``sigma_v`` in metres directly.  ``threshold`` remains the
    metric fallback used when no uncertainty information is available at all.

    Also returns conditioning diagnostics: a straight or constant-altitude flight
    cannot constrain all seven degrees of freedom, and the result says so instead
    of quietly reporting a confident transform.
    """
    src = np.asarray(src, float)
    dst = np.asarray(dst, float)
    n = src.shape[0]
    if n < min_samples:
        raise ValueError(f"need >= {min_samples} correspondences, got {n}")
    if dst.shape[0] != n:
        raise ValueError("src and dst must have the same length")

    sh, sv, sigma_source = _sigmas_from_weights(
        weights, n, sigma_h, sigma_v, default_sigma_h, default_sigma_v)
    have_uncertainty = sigma_source != "uniform_default"

    rng = np.random.default_rng(seed)

    def _collinear(idx) -> bool:
        p = src[idx]
        return np.linalg.norm(np.cross(p[1] - p[0], p[2] - p[0])) < 1e-6

    def _metric_resid(model) -> np.ndarray:
        return np.linalg.norm(model.apply(src) - dst, axis=1)

    def _ransac(score_fn, cutoff, w) -> np.ndarray:
        best_inliers, best_count, best_cost = None, -1, np.inf
        for _ in range(iters):
            idx = rng.choice(n, min_samples, replace=False)
            if _collinear(idx):
                continue
            try:
                m = umeyama_sim3(src[idx], dst[idx], weights=w[idx])
            except (np.linalg.LinAlgError, ValueError):
                continue
            r = score_fn(m)
            inliers = r < cutoff
            count = int(inliers.sum())
            # Break ties on total inlier residual so a marginally-equal consensus
            # set does not win on sampling luck alone.
            cost = float(r[inliers].sum()) if count else np.inf
            if count > best_count or (count == best_count and cost < best_cost):
                best_count, best_cost, best_inliers = count, cost, inliers
            if count == n and cost <= best_cost:
                break
        if best_inliers is None or best_count < min_samples:
            best_inliers = np.ones(n, bool)   # degrade to plain least squares
        return best_inliers

    # ---- stage 1: uncertainty-agnostic consensus --------------------------
    # A camera-centre-to-GNSS residual is GNSS noise PLUS reconstruction error,
    # and on a good reconstruction the second term dominates.  Gating on the GNSS
    # sigma alone would assume the reconstruction is perfect and throw away good
    # correspondences, so the scale of the reconstruction error is measured first
    # from a permissive metric fit.
    uniform = np.ones(n)
    inl0 = _ransac(_metric_resid, threshold, uniform)
    model0 = umeyama_sim3(src[inl0], dst[inl0], weights=uniform[inl0])
    sigma_recon = _robust_sigma(_metric_resid(model0)[inl0])

    # ---- stage 2: gate and weight on the TOTAL expected residual ----------
    # sigma_total = sqrt(sigma_gnss^2 + sigma_recon^2).  When reconstruction
    # error dominates this correctly compresses the differences between GNSS
    # fixes -- their relative quality matters less when it is not the limiting
    # term -- while still preferring the better fixes.
    sh_t = np.sqrt(sh ** 2 + sigma_recon ** 2)
    sv_t = np.sqrt(sv ** 2 + sigma_recon ** 2)
    inv_var = 1.0 / (sh_t ** 2)

    def _norm_resid(model) -> np.ndarray:
        d = model.apply(src) - dst
        return np.sqrt((d[:, 0] / sh_t) ** 2 + (d[:, 1] / sh_t) ** 2
                       + (d[:, 2] / sv_t) ** 2)

    # With no stated uncertainty a normalised threshold would be arbitrary, so
    # keep the metric one rather than inventing a sigma.
    if have_uncertainty:
        inl = _ransac(_norm_resid, n_sigma, inv_var)
    else:
        inl, inv_var = inl0, uniform

    # Weighted refit on the consensus set.
    model = umeyama_sim3(src[inl], dst[inl], weights=inv_var[inl])

    # Anisotropic refinement: the closed form can only take an isotropic weight,
    # so a final nonlinear step minimises the properly normalised residual with
    # horizontal and vertical sigmas treated separately.
    if refine and have_uncertainty and inl.sum() >= min_samples:
        model = _refine_sim3(model, src[inl], dst[inl], sh_t[inl], sv_t[inl]) or model

    aligned = model.apply(src)
    diff = aligned - dst
    rmse = float(np.sqrt((diff[inl] ** 2).sum(1).mean()))
    rmse_h = float(np.sqrt((diff[inl][:, :2] ** 2).sum(1).mean()))
    rmse_v = float(np.sqrt((diff[inl][:, 2] ** 2).mean()))
    nrmse = float(np.sqrt((_norm_resid(model)[inl] ** 2).mean())) if have_uncertainty else None

    degenerate, why, cond = _trajectory_conditioning(dst[inl])
    cond["sigma_source"] = sigma_source
    cond["median_sigma_h_m"] = float(np.median(sh))
    cond["median_sigma_v_m"] = float(np.median(sv))
    cond["scored_in"] = "mahalanobis" if have_uncertainty else "metres"
    # Reported so a reader can see which term actually limits the alignment: if
    # sigma_recon >> the GNSS sigmas, better GNSS would not improve this result.
    cond["sigma_recon_m"] = float(sigma_recon)
    cond["median_sigma_total_h_m"] = float(np.median(sh_t))
    cond["error_budget"] = ("reconstruction_dominated"
                            if sigma_recon > float(np.median(sh))
                            else "gnss_dominated")

    # Scale uncertainty: propagate the inlier residual through the trajectory's
    # own extent.  A short track pins scale far less well than a long one, and a
    # single number for "scale error" hides that entirely.
    #
    # Units matter here and got this wrong once: ``src`` is in the arbitrary
    # reconstruction frame, while ``rmse`` is in metres.  The extent must be
    # converted to metres (multiply by the fitted scale) before dividing, or the
    # relative uncertainty comes out inflated by the scale factor itself -- which
    # produced a reported 10% scale uncertainty on a fit good to ~0.2%.
    spread_recon = float(np.sqrt(((src[inl] - src[inl].mean(0)) ** 2).sum(1).mean()))
    spread_m = spread_recon * float(model.scale)
    dof = np.sqrt(max(int(inl.sum()) - 1, 1))
    # relative 1-sigma on scale, then expressed as an absolute sigma
    rel = rmse / (spread_m * dof) if spread_m > 1e-9 else None
    scale_sigma = float(model.scale * rel) if rel is not None else None

    return Sim3Result(model, inl, rmse, rmse_h, rmse_v, int(inl.sum()), n,
                      normalized_rmse=nrmse, scale_sigma=scale_sigma,
                      degenerate=degenerate, degeneracy=why, conditioning=cond)


def _refine_sim3(model: Sim3, src, dst, sh, sv):
    """Nonlinear refit minimising per-axis normalised residuals.

    Parameterised as (rotation vector, translation, log-scale) so scale stays
    positive.  Returns ``None`` if the refinement fails or does not improve.
    """
    try:
        from scipy.optimize import least_squares
    except Exception:
        return None

    def _rodrigues(rv):
        th = float(np.linalg.norm(rv))
        if th < 1e-12:
            return np.eye(3)
        k = rv / th
        Kx = np.array([[0, -k[2], k[1]], [k[2], 0, -k[0]], [-k[1], k[0], 0]])
        return np.eye(3) + np.sin(th) * Kx + (1 - np.cos(th)) * (Kx @ Kx)

    def _log_rot(R):
        c = (np.trace(R) - 1) / 2
        th = float(np.arccos(np.clip(c, -1, 1)))
        if th < 1e-9:
            return np.zeros(3)
        return th / (2 * np.sin(th)) * np.array(
            [R[2, 1] - R[1, 2], R[0, 2] - R[2, 0], R[1, 0] - R[0, 1]])

    x0 = np.concatenate([_log_rot(model.R), model.t, [np.log(max(model.scale, 1e-12))]])

    def resid(x):
        R = _rodrigues(x[:3])
        d = (np.exp(x[6]) * (R @ src.T).T + x[3:6]) - dst
        return np.concatenate([d[:, 0] / sh, d[:, 1] / sh, d[:, 2] / sv])

    r0 = float(np.sum(resid(x0) ** 2))
    try:
        sol = least_squares(resid, x0, method="lm", max_nfev=500)
    except Exception:
        return None
    if not np.all(np.isfinite(sol.x)) or float(np.sum(sol.fun ** 2)) > r0:
        return None                      # never return a worse fit than we had
    return Sim3(float(np.exp(sol.x[6])), _rodrigues(sol.x[:3]), sol.x[3:6])
