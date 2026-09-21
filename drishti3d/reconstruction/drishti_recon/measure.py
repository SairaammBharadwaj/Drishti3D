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


#: A selection is allowed to move this many times the cloud's own median point
#: spacing before it stops being "the operator meant that surface". Three
#: spacings covers picking error and the gap between neighbouring points;
#: beyond it, the nearest point is a different feature, or there is no feature.
SNAP_SPACING_FACTOR = 3.0
#: Floor for the above, so a very dense cloud does not refuse ordinary picks.
MIN_SNAP_TOLERANCE_M = 0.10


def snap_tolerance(cloud, *, allow_inferred: bool = True) -> float:
    """How far a selection may be from measurable geometry, in metres.

    Derived from the cloud's own median nearest-neighbour spacing rather than
    fixed, because the same absolute displacement means different things in a
    0.10 m dense cloud and a 0.17 m sparse one.
    """
    cached = getattr(cloud, "_snap_tolerance_m", None)
    if cached is not None:
        return float(cached)
    from scipy.spatial import cKDTree
    pts = np.asarray(cloud.points, float)
    if len(pts) < 2:
        return float("inf")
    rng = np.random.default_rng(0)
    sample = pts if len(pts) <= 20000 else pts[rng.choice(len(pts), 20000, replace=False)]
    d, _ = cKDTree(sample).query(sample, k=2)
    spacing = float(np.median(d[:, 1]))
    tol = max(SNAP_SPACING_FACTOR * spacing, MIN_SNAP_TOLERANCE_M)
    try:
        cloud._snap_tolerance_m = tol
    except Exception:
        pass
    return tol


@dataclass
class Snap:
    """What the operator selected, and what the cloud could offer for it."""
    requested: np.ndarray
    position: np.ndarray
    provenance: int
    sigma_major: float
    displacement_m: float
    tolerance_m: float
    resolved: bool

    def to_dict(self):
        return {"requested_enu": list(map(float, self.requested)),
                "resolved_enu": list(map(float, self.position)),
                "snap_displacement_m": _jsonable(self.displacement_m),
                "snap_tolerance_m": _jsonable(self.tolerance_m),
                "resolved": bool(self.resolved)}


def snap(cloud, p, allow_inferred: bool, *, max_snap_m: float | None = None) -> Snap:
    """Resolve a selected position onto measurable geometry, or refuse.

    Snapping used to be unconditional: the nearest measurable point won however
    far away it was, so a selection at ``[1000, 0, 0]`` against a cloud ending
    at ``[10, 0, 0]`` silently moved 990 m and was then measured, and evidence
    was assembled, at a place the operator never chose. The distance was
    computed and discarded.

    Out-of-tolerance selections now keep the operator's own position, report
    ``UNOBSERVED`` and an infinite sigma -- which the measurement layer already
    reads as "not observable" -- and carry the displacement so the refusal can
    say how far away the nearest geometry was.
    """
    from scipy.spatial import cKDTree
    q = np.asarray(p, float).reshape(3)
    tol = float(max_snap_m) if max_snap_m is not None else snap_tolerance(cloud)
    mask = np.ones(len(cloud.points), bool)
    if not allow_inferred:
        mask = cloud.provenance != int(Provenance.AI_ASSISTED)
    pts = cloud.points[mask]
    if len(pts) == 0:
        return Snap(q, q, int(Provenance.UNOBSERVED), float("inf"),
                    float("inf"), tol, False)
    d, i = cKDTree(pts).query(q)
    d = float(d)
    if d > tol:
        return Snap(q, q, int(Provenance.UNOBSERVED), float("inf"), d, tol, False)
    prov = cloud.provenance[mask][i]
    sig = float("inf")
    if getattr(cloud, "sigma_major", None) is not None:
        sig = float(np.asarray(cloud.sigma_major)[mask][i])
    return Snap(q, pts[i], int(prov), sig, d, tol, True)


def _snap(cloud, p, allow_inferred: bool, *, max_snap_m: float | None = None):
    """Back-compatible tuple form of :func:`snap`."""
    sn = snap(cloud, p, allow_inferred, max_snap_m=max_snap_m)
    return sn.position, sn.provenance, sn.sigma_major


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


def _snap_warnings(snaps) -> list:
    """One warning per selection that could not be resolved onto geometry."""
    out = []
    for n, sn in enumerate(snaps):
        if sn.resolved:
            continue
        where = ("no measurable geometry in this cloud"
                 if not np.isfinite(sn.displacement_m)
                 else f"nearest measurable point is {sn.displacement_m:.2f} m "
                      f"away, past the {sn.tolerance_m:.2f} m selection "
                      f"tolerance")
        out.append(f"point {n + 1} is not on measurable geometry: {where}")
    return out


def _snap_extra(snaps) -> dict:
    """Record what was selected against what was measured."""
    return {"selection": [sn.to_dict() for sn in snaps],
            "max_snap_displacement_m": _jsonable(max(
                (sn.displacement_m for sn in snaps), default=0.0)),
            "all_selections_resolved": all(sn.resolved for sn in snaps)}


def measure_point(cloud, p, *, allow_inferred=False, max_snap_m=None):
    sn = snap(cloud, p, allow_inferred, max_snap_m=max_snap_m)
    note, warns = _note([sn.provenance])
    warns = _snap_warnings([sn]) + warns
    extra = {"coordinate_enu": list(map(float, sn.position)),
             "position_sigma_m": _jsonable(sn.sigma_major)}
    extra.update(_snap_extra([sn]))
    m = Measurement("point", None, "m", [sn.position], note,
                    sn.provenance == int(Provenance.AI_ASSISTED), warns, extra)
    m.sigma = sn.sigma_major
    m.ci95 = m.sigma * 1.96 if np.isfinite(m.sigma) else float("inf")
    return m


def measure_distance(cloud, pts, *, allow_inferred=False,
                     scale_sigma_rel: float = 0.0, tolerance: float | None = None,
                     max_snap_m=None):
    """3D polyline length through the given points.

    ``scale_sigma_rel`` is the relative uncertainty of the metric scale (from the
    GNSS alignment). It multiplies the measured length, so it dominates long
    measurements while the endpoint term does not.
    """
    snaps = [snap(cloud, p, allow_inferred, max_snap_m=max_snap_m) for p in pts]
    snapped = [sn.position for sn in snaps]
    provs = [sn.provenance for sn in snaps]
    sigs = [sn.sigma_major for sn in snaps]
    # Propagated over the whole polyline rather than segment by segment: scale
    # is one error common to the entire length, and interior vertices are
    # shared between adjacent segments.  See polyline_length_uncertainty.
    total, sigma = unc.polyline_length_uncertainty(
        snapped, [_cov(g) for g in sigs], scale_sigma_rel=scale_sigma_rel)
    note, warns = _note(provs)
    warns = _snap_warnings(snaps) + warns
    m = Measurement("distance", float(total), "m", snapped, note,
                    any(pr == int(Provenance.AI_ASSISTED) for pr in provs), warns,
                    _snap_extra(snaps))
    m.sigma = float(sigma)
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
                   scale_sigma_rel: float = 0.0, tolerance: float | None = None,
                   max_snap_m=None):
    """Vertical (up-axis) difference between two picked points."""
    na = snap(cloud, a, allow_inferred, max_snap_m=max_snap_m)
    nb = snap(cloud, b, allow_inferred, max_snap_m=max_snap_m)
    sa, pa, ga = na.position, na.provenance, na.sigma_major
    sb, pb, gb = nb.position, nb.provenance, nb.sigma_major
    h, sig = unc.height_uncertainty(sa, sb, _cov(ga), _cov(gb),
                                    scale_sigma_rel=scale_sigma_rel)
    note, warns = _note([pa, pb])
    warns = _snap_warnings([na, nb]) + warns
    m = Measurement("height", float(h), "m", [sa, sb], note,
                    int(Provenance.AI_ASSISTED) in (pa, pb), warns,
                    _snap_extra([na, nb]))
    m.sigma = sig
    m.ci95 = sig * 1.96 if np.isfinite(sig) else float("inf")
    if tolerance is not None:
        ok, why = unc.meets_requirement(h, sig, tolerance)
        m.meets_tolerance = ok
        if not ok:
            warns.append(f"does not meet the requested tolerance: {why}")
    return m


def measure_area(cloud, pts, *, allow_inferred=False,
                 scale_sigma_rel: float = 0.0, max_snap_m=None):
    """Polygon area projected onto a best-fit plane through the points."""
    snaps = [snap(cloud, p, allow_inferred, max_snap_m=max_snap_m) for p in pts]
    snapped = [sn.position for sn in snaps]
    provs = [sn.provenance for sn in snaps]
    sigs = [sn.sigma_major for sn in snaps]
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
    warns = _snap_warnings(snaps) + warns
    m = Measurement("area", float(area), "m^2", snapped, note,
                    any(pr == int(Provenance.AI_ASSISTED) for pr in provs), warns,
                    _snap_extra(snaps))
    m.sigma = sig
    m.ci95 = sig * 1.96 if np.isfinite(sig) else float("inf")
    return m
