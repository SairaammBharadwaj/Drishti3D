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


def umeyama_sim3(src: np.ndarray, dst: np.ndarray, with_scale: bool = True) -> Sim3:
    """Least-squares similarity aligning src->dst (Umeyama 1991)."""
    src = np.asarray(src, float)
    dst = np.asarray(dst, float)
    n = src.shape[0]
    mu_s = src.mean(0)
    mu_d = dst.mean(0)
    sc = src - mu_s
    dc = dst - mu_d
    cov = (dc.T @ sc) / n
    u, d, vt = np.linalg.svd(cov)
    s = np.eye(3)
    if np.linalg.det(u) * np.linalg.det(vt) < 0:
        s[2, 2] = -1
    R = u @ s @ vt
    if with_scale:
        var_s = (sc ** 2).sum() / n
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


def robust_sim3(src: np.ndarray, dst: np.ndarray, *, weights=None,
                iters: int = 500, threshold: float = 2.0,
                min_samples: int = 3, seed: int = 0) -> Sim3Result:
    """RANSAC Sim(3) aligning reconstructed camera centres (src) to GPS ENU (dst).

    Requires >= 3 non-collinear correspondences.  ``threshold`` is the inlier
    distance in metres.  Optional per-point ``weights`` (e.g. 1/gps_accuracy).
    """
    src = np.asarray(src, float)
    dst = np.asarray(dst, float)
    n = src.shape[0]
    if n < min_samples:
        raise ValueError(f"need >= {min_samples} correspondences, got {n}")

    rng = np.random.default_rng(seed)
    best_inliers = None
    best_count = -1

    def _collinear(idx) -> bool:
        p = src[idx]
        v1 = p[1] - p[0]
        v2 = p[2] - p[0]
        return np.linalg.norm(np.cross(v1, v2)) < 1e-6

    for _ in range(iters):
        idx = rng.choice(n, min_samples, replace=False)
        if _collinear(idx):
            continue
        try:
            model = umeyama_sim3(src[idx], dst[idx])
        except np.linalg.LinAlgError:
            continue
        resid = np.linalg.norm(model.apply(src) - dst, axis=1)
        inliers = resid < threshold
        count = int(inliers.sum())
        if count > best_count:
            best_count = count
            best_inliers = inliers
        if count == n:
            break

    if best_inliers is None or best_count < min_samples:
        best_inliers = np.ones(n, bool)  # degrade to plain least squares

    # Refit on all inliers.
    model = umeyama_sim3(src[best_inliers], dst[best_inliers])
    aligned = model.apply(src)
    diff = aligned - dst
    inl = best_inliers
    rmse = float(np.sqrt((diff[inl] ** 2).sum(1).mean()))
    rmse_h = float(np.sqrt((diff[inl][:, :2] ** 2).sum(1).mean()))
    rmse_v = float(np.sqrt((diff[inl][:, 2] ** 2).mean()))
    return Sim3Result(model, inl, rmse, rmse_h, rmse_v, int(inl.sum()), n)
