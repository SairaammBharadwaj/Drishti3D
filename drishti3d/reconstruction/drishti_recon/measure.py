"""Metric measurements on the reconstructed cloud.

All measurements operate in metric ENU.  By default only OBSERVED_HIGH_CONFIDENCE
geometry is used; touching low-confidence or AI-assisted geometry raises a
warning flag recorded with the measurement.
"""
from __future__ import annotations

from dataclasses import dataclass, field
import numpy as np

from . import uncertainty as unc
from .provenance import Provenance


@dataclass
class Measurement:
    kind: str                        # point | distance | height | area
    value: float | None
    unit: str
    points_enu: list                 # input points (ENU)
    confidence_note: str = ""
    used_inferred: bool = False
    warnings: list = field(default_factory=list)
    extra: dict = field(default_factory=dict)
    #: Propagated 1-sigma uncertainty of ``value``, in ``unit``.  ``None`` when
    #: the cloud carries no uncertainty; ``inf`` when an endpoint is not
    #: observable, which must be shown rather than hidden.
    sigma: float | None = None
    #: Half-width of the 95% interval, i.e. what to write after the "+/-".
    ci95: float | None = None
    meets_tolerance: bool | None = None

    def to_dict(self):
        return {"kind": self.kind, "value": self.value, "unit": self.unit,
                "points_enu": [list(map(float, p)) for p in self.points_enu],
                "confidence_note": self.confidence_note,
                "used_inferred": self.used_inferred,
                "warnings": self.warnings, "extra": self.extra,
                "sigma": None if self.sigma is None else _jsonable(self.sigma),
                "ci95": None if self.ci95 is None else _jsonable(self.ci95),
                "meets_tolerance": self.meets_tolerance}

    def format(self) -> str:
        """Human-readable value with its interval, or an honest refusal."""
        if self.value is None:
            return "—"
        if self.sigma is None:
            return f"{self.value:.3f} {self.unit}"
        if not np.isfinite(self.sigma):
            return f"{self.value:.3f} {self.unit} (uncertainty unknown)"
        return f"{self.value:.3f} +/- {self.ci95:.3f} {self.unit} (95%)"


def _jsonable(v):
    """inf/nan are not valid JSON; emit null rather than an invalid document."""
    v = float(v)
    return v if np.isfinite(v) else None


def _snap(cloud, p, allow_inferred: bool):
    """Snap a picked point to the nearest measurable cloud point.

    Returns ``(position, provenance, sigma_major)`` where the third element is
    that point's worst-axis 1-sigma uncertainty (``inf`` if unknown).
    """
    from scipy.spatial import cKDTree
    mask = np.ones(len(cloud.points), bool)
    if not allow_inferred:
        mask = cloud.provenance != int(Provenance.AI_ASSISTED)
    pts = cloud.points[mask]
    if len(pts) == 0:
        return np.asarray(p, float), int(Provenance.UNOBSERVED), float("inf")
    tree = cKDTree(pts)
    d, i = tree.query(np.asarray(p, float))
    prov = cloud.provenance[mask][i]
    sig = float("inf")
    if getattr(cloud, "sigma_major", None) is not None:
        sig = float(np.asarray(cloud.sigma_major)[mask][i])
    return pts[i], int(prov), sig


def _cov(sigma):
    """Conservative isotropic covariance from a worst-axis sigma.

    The full 3x3 covariance is not carried through fusion, so measurements use
    the worst-constrained axis in every direction. That overstates uncertainty
    across the well-constrained directions, which is the correct way to be wrong
    for a number someone will act on.
    """
    if sigma is None or not np.isfinite(sigma):
        return np.full((3, 3), np.nan)
    return np.eye(3) * (float(sigma) ** 2)


def _note(provs) -> tuple[str, list]:
    warns = []
    if any(pr == int(Provenance.AI_ASSISTED) for pr in provs):
        warns.append("measurement touches AI-assisted geometry")
    if any(pr == int(Provenance.OBSERVED_LOW_CONFIDENCE) for pr in provs):
        warns.append("measurement touches low-confidence geometry")
    note = "high-confidence" if not warns else "reduced confidence"
    return note, warns


def measure_point(cloud, p, *, allow_inferred=False):
    sp, prov, sig = _snap(cloud, p, allow_inferred)
    note, warns = _note([prov])
    m = Measurement("point", None, "m", [sp], note,
                    prov == int(Provenance.AI_ASSISTED), warns,
                    {"coordinate_enu": list(map(float, sp)),
                     "position_sigma_m": _jsonable(sig)})
    m.sigma = sig
    m.ci95 = sig * 1.96 if np.isfinite(sig) else float("inf")
    return m


def measure_distance(cloud, pts, *, allow_inferred=False,
                     scale_sigma_rel: float = 0.0, tolerance: float | None = None):
    """3D polyline length through the given points.

    ``scale_sigma_rel`` is the relative uncertainty of the metric scale (from the
    GNSS alignment). It multiplies the measured length, so it dominates long
    measurements while the endpoint term does not.
    """
    snapped, provs, sigs = [], [], []
    for p in pts:
        sp, pr, sg = _snap(cloud, p, allow_inferred)
        snapped.append(sp)
        provs.append(pr)
        sigs.append(sg)
    total = 0.0
    var = 0.0
    for (a, sa), (b, sb) in zip(zip(snapped[:-1], sigs[:-1]),
                                zip(snapped[1:], sigs[1:])):
        d, s = unc.distance_uncertainty(a, b, _cov(sa), _cov(sb),
                                        scale_sigma_rel=scale_sigma_rel)
        total += d
        # Segment errors are treated as independent, which is the standard
        # assumption for a polyline through independently triangulated points.
        var = np.inf if (not np.isfinite(s) or not np.isfinite(var)) else var + s * s
    note, warns = _note(provs)
    m = Measurement("distance", float(total), "m", snapped, note,
                    any(pr == int(Provenance.AI_ASSISTED) for pr in provs), warns)
    m.sigma = float(np.sqrt(var)) if np.isfinite(var) else float("inf")
    m.ci95 = m.sigma * 1.96 if np.isfinite(m.sigma) else float("inf")
    if not np.isfinite(m.sigma):
        warns.append("uncertainty unavailable: an endpoint is not observable")
    if tolerance is not None:
        ok, why = unc.meets_requirement(total, m.sigma, tolerance)
        m.meets_tolerance = ok
        if not ok:
            warns.append(f"does not meet the requested tolerance: {why}")
    return m


def measure_height(cloud, a, b, *, allow_inferred=False,
                   scale_sigma_rel: float = 0.0, tolerance: float | None = None):
    """Vertical (up-axis) difference between two picked points."""
    sa, pa, ga = _snap(cloud, a, allow_inferred)
    sb, pb, gb = _snap(cloud, b, allow_inferred)
    h, sig = unc.height_uncertainty(sa, sb, _cov(ga), _cov(gb),
                                    scale_sigma_rel=scale_sigma_rel)
    note, warns = _note([pa, pb])
    m = Measurement("height", float(h), "m", [sa, sb], note,
                    int(Provenance.AI_ASSISTED) in (pa, pb), warns)
    m.sigma = sig
    m.ci95 = sig * 1.96 if np.isfinite(sig) else float("inf")
    if tolerance is not None:
        ok, why = unc.meets_requirement(h, sig, tolerance)
        m.meets_tolerance = ok
        if not ok:
            warns.append(f"does not meet the requested tolerance: {why}")
    return m


def measure_area(cloud, pts, *, allow_inferred=False,
                 scale_sigma_rel: float = 0.0):
    """Polygon area projected onto a best-fit plane through the points."""
    snapped, provs, sigs = [], [], []
    for p in pts:
        sp, pr, sg = _snap(cloud, p, allow_inferred)
        snapped.append(sp)
        provs.append(pr)
        sigs.append(sg)
    P = np.asarray(snapped, float)
    if len(P) < 3:
        return Measurement("area", None, "m^2", snapped, "insufficient points",
                           False, ["need >= 3 points"])
    c = P.mean(0)
    _, _, vt = np.linalg.svd(P - c)
    u, v = vt[0], vt[1]           # in-plane basis
    xy = np.stack([(P - c) @ u, (P - c) @ v], 1)
    x, y = xy[:, 0], xy[:, 1]
    area = 0.5 * abs(np.dot(x, np.roll(y, -1)) - np.dot(y, np.roll(x, -1)))
    note, warns = _note(provs)
    _, sig = unc.area_uncertainty(P, [_cov(g) for g in sigs],
                                  scale_sigma_rel=scale_sigma_rel)
    m = Measurement("area", float(area), "m^2", snapped, note,
                    any(pr == int(Provenance.AI_ASSISTED) for pr in provs), warns)
    m.sigma = sig
    m.ci95 = sig * 1.96 if np.isfinite(sig) else float("inf")
    return m
