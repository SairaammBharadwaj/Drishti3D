"""Metric measurements on the reconstructed cloud.

All measurements operate in metric ENU.  By default only OBSERVED_HIGH_CONFIDENCE
geometry is used; touching low-confidence or AI-assisted geometry raises a
warning flag recorded with the measurement.
"""
from __future__ import annotations

from dataclasses import dataclass, field
import numpy as np

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

    def to_dict(self):
        return {"kind": self.kind, "value": self.value, "unit": self.unit,
                "points_enu": [list(map(float, p)) for p in self.points_enu],
                "confidence_note": self.confidence_note,
                "used_inferred": self.used_inferred,
                "warnings": self.warnings, "extra": self.extra}


def _snap(cloud, p, allow_inferred: bool):
    """Snap a picked point to the nearest measurable cloud point."""
    from scipy.spatial import cKDTree
    mask = np.ones(len(cloud.points), bool)
    if not allow_inferred:
        mask = cloud.provenance != int(Provenance.AI_ASSISTED)
    pts = cloud.points[mask]
    if len(pts) == 0:
        return np.asarray(p, float), int(Provenance.UNOBSERVED)
    tree = cKDTree(pts)
    d, i = tree.query(np.asarray(p, float))
    prov = cloud.provenance[mask][i]
    return pts[i], int(prov)


def _note(provs) -> tuple[str, list]:
    warns = []
    if any(pr == int(Provenance.AI_ASSISTED) for pr in provs):
        warns.append("measurement touches AI-assisted geometry")
    if any(pr == int(Provenance.OBSERVED_LOW_CONFIDENCE) for pr in provs):
        warns.append("measurement touches low-confidence geometry")
    note = "high-confidence" if not warns else "reduced confidence"
    return note, warns


def measure_point(cloud, p, *, allow_inferred=False):
    sp, prov = _snap(cloud, p, allow_inferred)
    note, warns = _note([prov])
    return Measurement("point", None, "m", [sp], note,
                       prov == int(Provenance.AI_ASSISTED), warns,
                       {"coordinate_enu": list(map(float, sp))})


def measure_distance(cloud, pts, *, allow_inferred=False):
    """3D polyline length through the given points."""
    snapped, provs = [], []
    for p in pts:
        sp, pr = _snap(cloud, p, allow_inferred)
        snapped.append(sp)
        provs.append(pr)
    total = 0.0
    for a, b in zip(snapped[:-1], snapped[1:]):
        total += float(np.linalg.norm(np.asarray(b) - np.asarray(a)))
    note, warns = _note(provs)
    return Measurement("distance", total, "m", snapped, note,
                       any(pr == int(Provenance.AI_ASSISTED) for pr in provs), warns)


def measure_height(cloud, a, b, *, allow_inferred=False):
    """Vertical (up-axis) difference between two picked points."""
    sa, pa = _snap(cloud, a, allow_inferred)
    sb, pb = _snap(cloud, b, allow_inferred)
    h = abs(float(sa[2] - sb[2]))
    note, warns = _note([pa, pb])
    return Measurement("height", h, "m", [sa, sb], note,
                       int(Provenance.AI_ASSISTED) in (pa, pb), warns)


def measure_area(cloud, pts, *, allow_inferred=False):
    """Polygon area projected onto a best-fit plane through the points."""
    snapped, provs = [], []
    for p in pts:
        sp, pr = _snap(cloud, p, allow_inferred)
        snapped.append(sp)
        provs.append(pr)
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
    return Measurement("area", float(area), "m^2", snapped, note,
                       any(pr == int(Provenance.AI_ASSISTED) for pr in provs), warns)
