"""Absolute accuracy against surveyed points: checkpoints, GCP correction, leave-one-out.

A surveyed point is a **GCP** if it may be used to correct the model, or a
**checkpoint** if it is held back to judge it. The two must not be confused:
a correction fitted to some points will agree with those points better than
with any others, so residuals at the points that fitted it say how well the
transform could bend, not how accurate the model is. This module keeps the
cases apart and labels every number with whether it is independent:

``raw``
    The model as reconstructed, against every surveyed point. Independent of
    any correction (nothing was fitted), though the truth is only as good as
    the survey.
``correction``
    Fitted to the GCPs: a translation for one or two, a 7-parameter
    similarity (Umeyama 1991) for three or more that are not collinear.
``fit_residuals``
    Residuals at the GCPs after the fit. **Not independent**: those points
    made the fit.
``leave_one_out``
    Each GCP in turn is left out, the correction refitted on the rest and
    scored on the one left out. A fairer estimate than the fit residuals but
    still drawn from the GCP set, and with few GCPs it reverts to a
    translation; labelled cross-validated, not independent.
``checkpoints``
    The corrected model against the checkpoints, which the fit never saw.
    This is the only corrected number that may be called independent.

Statistics follow the usual mapping conventions: per-axis RMSE, horizontal
RMSE ``RMSE_r = sqrt(RMSE_E^2 + RMSE_N^2)``, CE90 ``= 1.5175 * RMSE_r`` and
LE90 ``= 1.6449 * RMSE_U`` (both assume unbiased normal errors, circular
horizontally; NSSDA/ASPRS 2014), plus the empirical 90th percentiles when
there are at least ten points. ASPRS (2014) asks for at least 30 checkpoints
before an accuracy class is claimed; fewer are reported, with a flag.

Coordinates are local ENU metres in the mission's frame. Truth given as
latitude/longitude/height or UTM is converted with that frame; its height
must be on the mission's vertical datum, or be converted with EGM2008, which
refuses (``position.GeoidUnavailable``) rather than guessing.
"""
from __future__ import annotations

import csv
import io
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

from .geo import ENUFrame

#: ASPRS Positional Accuracy Standards (2014): minimum checkpoints for a claim.
ASPRS_MIN_CHECKPOINTS = 30
CE90_FACTOR = 1.5175
LE90_FACTOR = 1.6449
#: Smallest second/first singular value of the GCP spread for a similarity fit.
#: Collinear GCPs leave the rotation about their line undetermined.
COLLINEAR_RATIO = 0.05

GCP, CHECK = "gcp", "check"


@dataclass
class SurveyPoint:
    """One surveyed point: where it really is, and where the model put it."""
    id: str
    truth: np.ndarray            # (3,) ENU metres
    measured: np.ndarray         # (3,) ENU metres, picked in the model
    role: str = CHECK            # "gcp" or "check"
    truth_sigma_m: float | None = None

    def __post_init__(self):
        self.truth = np.asarray(self.truth, float).reshape(3)
        self.measured = np.asarray(self.measured, float).reshape(3)
        self.role = str(self.role).strip().lower()
        if self.role in ("control", "gcps"):
            self.role = GCP
        if self.role in ("checkpoint", "checkpoints", "cp", "chk"):
            self.role = CHECK
        if self.role not in (GCP, CHECK):
            raise ValueError(f"point {self.id}: role must be 'gcp' or 'check', "
                             f"not {self.role!r}")


# ------------------------------------------------------------------ statistics
def error_stats(err: np.ndarray) -> dict:
    """Accuracy statistics of (n, 3) ENU errors (measured minus truth)."""
    err = np.asarray(err, float).reshape(-1, 3)
    n = len(err)
    if n == 0:
        return {"n": 0}
    rms = np.sqrt(np.mean(err ** 2, axis=0))
    rmse_r = float(np.hypot(rms[0], rms[1]))
    horiz = np.hypot(err[:, 0], err[:, 1])
    out = {
        "n": n,
        "mean_m": {"e": float(err[:, 0].mean()), "n": float(err[:, 1].mean()),
                   "u": float(err[:, 2].mean())},
        "rmse_m": {"e": float(rms[0]), "n": float(rms[1]), "u": float(rms[2]),
                   "horizontal": rmse_r, "3d": float(np.sqrt(np.sum(rms ** 2)))},
        "max_abs_m": {"horizontal": float(horiz.max()),
                      "u": float(np.abs(err[:, 2]).max())},
        "ce90_m": CE90_FACTOR * rmse_r,
        "le90_m": LE90_FACTOR * float(rms[2]),
    }
    if n >= 10:
        out["ce90_empirical_m"] = float(np.percentile(horiz, 90))
        out["le90_empirical_m"] = float(np.percentile(np.abs(err[:, 2]), 90))
    return out


# ----------------------------------------------------------------- correction
@dataclass
class Correction:
    """``x_corrected = scale * R @ x + t`` on ENU metres."""
    kind: str                         # "none" | "translation" | "similarity"
    scale: float = 1.0
    R: np.ndarray = field(default_factory=lambda: np.eye(3))
    t: np.ndarray = field(default_factory=lambda: np.zeros(3))
    n_points: int = 0
    note: str | None = None

    def apply(self, x: np.ndarray) -> np.ndarray:
        x = np.asarray(x, float).reshape(-1, 3)
        return self.scale * x @ self.R.T + self.t

    def to_dict(self) -> dict:
        ang = np.degrees(np.arccos(np.clip((np.trace(self.R) - 1) / 2, -1, 1)))
        return {"kind": self.kind, "n_points": self.n_points,
                "scale": float(self.scale), "scale_ppm": float((self.scale - 1) * 1e6),
                "rotation_deg": float(ang), "rotation": self.R.tolist(),
                "translation_m": self.t.tolist(), "note": self.note}


def _umeyama(src: np.ndarray, dst: np.ndarray):
    """Least-squares similarity dst ~ s R src + t (Umeyama 1991)."""
    mu_s, mu_d = src.mean(0), dst.mean(0)
    a, b = src - mu_s, dst - mu_d
    cov = b.T @ a / len(src)
    U, D, Vt = np.linalg.svd(cov)
    S = np.eye(3)
    if np.linalg.det(U) * np.linalg.det(Vt) < 0:
        S[2, 2] = -1
    R = U @ S @ Vt
    var = (a ** 2).sum() / len(src)
    s = float(np.trace(np.diag(D) @ S) / var) if var > 0 else 1.0
    return s, R, mu_d - s * R @ mu_s


def fit_correction(measured, truth, *, allow_similarity: bool = True) -> Correction:
    """Translation for 1-2 points, 7-parameter similarity for 3+ non-collinear."""
    m = np.asarray(measured, float).reshape(-1, 3)
    t = np.asarray(truth, float).reshape(-1, 3)
    n = len(m)
    if n == 0:
        return Correction("none", note="no GCPs: the model is reported as reconstructed")
    if n >= 3 and allow_similarity:
        sv = np.linalg.svd(m[:, :2] - m[:, :2].mean(0), compute_uv=False)
        if sv[0] > 0 and sv[1] / sv[0] >= COLLINEAR_RATIO:
            s, R, tt = _umeyama(m, t)
            return Correction("similarity", s, R, tt, n)
        note = (f"{n} GCPs are nearly collinear (spread ratio {sv[1] / max(sv[0], 1e-12):.3f}); "
                "rotation about their line is undetermined, so only a translation was fitted")
    elif n < 3:
        note = f"{n} GCP{'s' if n > 1 else ''}: translation only (a similarity needs 3+)"
    else:
        note = "translation only (similarity disabled)"
    return Correction("translation", t=(t - m).mean(0), n_points=n, note=note)


# --------------------------------------------------------------------- report
def _per_point(points, err):
    return [{"id": p.id, "role": p.role,
             "error_m": {"e": float(e[0]), "n": float(e[1]), "u": float(e[2]),
                         "horizontal": float(np.hypot(e[0], e[1]))}}
            for p, e in zip(points, err)]


def evaluate(points: list[SurveyPoint], *, allow_similarity: bool = True,
             truth_source: str | None = None, vertical_datum: str | None = None) -> dict:
    """The full accuracy report for a set of GCPs and checkpoints."""
    if not points:
        raise ValueError("no surveyed points")
    ids = [p.id for p in points]
    if len(set(ids)) != len(ids):
        raise ValueError("surveyed point ids must be unique")
    gcps = [p for p in points if p.role == GCP]
    checks = [p for p in points if p.role == CHECK]

    def M(ps):
        return np.array([p.measured for p in ps]).reshape(-1, 3)

    def T(ps):
        return np.array([p.truth for p in ps]).reshape(-1, 3)

    raw_err = M(points) - T(points)
    report = {
        "truth_source": truth_source,
        "vertical_datum": vertical_datum,
        "n_gcp": len(gcps), "n_check": len(checks),
        "raw": {"label": "as reconstructed, all surveyed points; no correction fitted",
                "independent": True, "stats": error_stats(raw_err),
                "points": _per_point(points, raw_err)},
    }
    corr = fit_correction(M(gcps), T(gcps), allow_similarity=allow_similarity)
    report["correction"] = corr.to_dict()

    if gcps:
        fit_err = corr.apply(M(gcps)) - T(gcps)
        report["fit_residuals"] = {
            "label": "residuals at the GCPs that fitted the correction: NOT independent "
                     "accuracy; these points were used for the fit",
            "independent": False, "stats": error_stats(fit_err),
            "points": _per_point(gcps, fit_err)}
    if len(gcps) >= 2:
        loo = []
        kinds = set()
        for i, p in enumerate(gcps):
            rest = gcps[:i] + gcps[i + 1:]
            c = fit_correction(M(rest), T(rest), allow_similarity=allow_similarity)
            kinds.add(c.kind)
            loo.append(c.apply(p.measured)[0] - p.truth)
        loo = np.array(loo)
        report["leave_one_out"] = {
            "label": "leave-one-out over the GCPs: each scored by a correction fitted "
                     "without it. Cross-validated, not an independent checkpoint test",
            "independent": False, "correction_kinds": sorted(kinds),
            "stats": error_stats(loo), "points": _per_point(gcps, loo)}
    if checks:
        chk_err = corr.apply(M(checks)) - T(checks)
        report["checkpoints"] = {
            "label": ("independent checkpoints, never used for the fit, after the "
                      f"{corr.kind} correction" if corr.kind != "none" else
                      "independent checkpoints; no correction applied"),
            "independent": True, "stats": error_stats(chk_err),
            "points": _per_point(checks, chk_err)}

    n_indep = len(checks)
    report["asprs"] = {
        "min_checkpoints": ASPRS_MIN_CHECKPOINTS,
        "independent_checkpoints": n_indep,
        "sample_sufficient": n_indep >= ASPRS_MIN_CHECKPOINTS,
        "note": (None if n_indep >= ASPRS_MIN_CHECKPOINTS else
                 f"{n_indep} independent checkpoint(s): below the {ASPRS_MIN_CHECKPOINTS} "
                 "ASPRS (2014) asks for before an accuracy class is claimed"),
    }
    headline = "checkpoints" if checks else "raw"
    report["headline"] = {
        "block": headline,
        "independent": True,
        "text": _headline_text(report[headline], corr if checks else None),
    }
    if not checks and gcps:
        report["headline"]["warning"] = (
            "every surveyed point was used to fit the correction; the corrected model "
            "has no independent accuracy figure. Hold some points back as checkpoints")
    return report


def _headline_text(block: dict, corr: Correction | None) -> str:
    s = block["stats"]
    txt = (f"RMSE horizontal {s['rmse_m']['horizontal']:.3f} m, vertical "
           f"{s['rmse_m']['u']:.3f} m, CE90 {s['ce90_m']:.3f} m, LE90 {s['le90_m']:.3f} m "
           f"over {s['n']} point(s)")
    if corr is not None and corr.kind != "none":
        txt += f", after a {corr.kind} correction on {corr.n_points} GCP(s)"
    return txt


# ---------------------------------------------------------------------- input
_TRUTH_LL = ("lat", "lon", "h")
_TRUTH_UTM = ("easting", "northing", "h")
_TRUTH_ENU = ("e", "n", "u")
_MEASURED = ("model_e", "model_n", "model_u")
_ALIASES = {"latitude": "lat", "longitude": "lon", "lng": "lon", "height": "h",
            "alt": "h", "altitude": "h", "z": "h", "x": "easting", "y": "northing",
            "type": "role", "name": "id", "point": "id", "sigma": "truth_sigma_m",
            "truth_sigma": "truth_sigma_m"}


def _norm(row: dict) -> dict:
    out = {}
    for k, v in row.items():
        if k is None:
            continue
        key = k.strip().lower().replace(" ", "_")
        out[_ALIASES.get(key, key)] = v
    return out


def _f(row, key, i):
    v = row.get(key)
    try:
        f = float(v)
    except (TypeError, ValueError):
        raise ValueError(f"row {i}: '{key}' missing or not a number ({v!r})")
    if not np.isfinite(f):
        raise ValueError(f"row {i}: '{key}' is not finite")
    return f


def _truth_height(h, lat, lon, truth_datum: str, mission_datum: str, i: int) -> float:
    if truth_datum == mission_datum:
        return h
    from .position import orthometric_height
    if truth_datum == "msl" and mission_datum == "ellipsoidal":
        N = -float(orthometric_height(lat, lon, 0.0)[0])
        return h + N
    if truth_datum == "ellipsoidal" and mission_datum == "msl":
        return float(orthometric_height(lat, lon, h)[0])
    raise ValueError(
        f"row {i}: truth heights are {truth_datum} but the mission's are {mission_datum}; "
        "they cannot be compared. Survey heights must be ellipsoidal or above sea level, "
        "and the mission's datum must be known")


def points_from_rows(rows, frame: ENUFrame | None, *, truth_datum: str = "ellipsoidal",
                     mission_datum: str = "ellipsoidal") -> list[SurveyPoint]:
    """Survey points from dict rows (CSV or JSON).

    Each row needs ``id``, ``role`` (gcp/check) and the model position
    ``model_e, model_n, model_u`` (local ENU, as picked in the viewer), plus
    the truth as one of ``lat, lon, h``; ``easting, northing, h, epsg``; or
    ``e, n, u`` (already in the mission frame). Optional ``truth_sigma_m``.
    """
    pts = []
    for i, raw in enumerate(rows):
        row = _norm(dict(raw))
        pid = str(row.get("id") or f"P{i + 1}").strip()
        measured = [_f(row, k, i) for k in _MEASURED]
        if all(row.get(k) not in (None, "") for k in _TRUTH_ENU):
            truth = [_f(row, k, i) for k in _TRUTH_ENU]
            if truth_datum != mission_datum:
                raise ValueError(f"row {i}: ENU truth must already be on the mission's "
                                 "vertical datum")
        else:
            if frame is None:
                raise ValueError("the mission is not georeferenced: truth must be given "
                                 "as e, n, u in its local frame")
            if all(row.get(k) not in (None, "") for k in _TRUTH_LL[:2]):
                lat, lon = _f(row, "lat", i), _f(row, "lon", i)
            elif all(row.get(k) not in (None, "") for k in _TRUTH_UTM[:2]):
                from pyproj import Transformer
                epsg = int(_f(row, "epsg", i))
                tr = Transformer.from_crs(f"EPSG:{epsg}", "EPSG:4326", always_xy=True)
                lon, lat = tr.transform(_f(row, "easting", i), _f(row, "northing", i))
            else:
                raise ValueError(f"row {i}: no truth position (lat/lon/h, "
                                 "easting/northing/h/epsg or e/n/u)")
            h = _truth_height(_f(row, "h", i), lat, lon, truth_datum, mission_datum, i)
            truth = frame.geodetic_to_enu([lat], [lon], [h])[0]
        sig = row.get("truth_sigma_m")
        pts.append(SurveyPoint(pid, truth, measured, row.get("role") or CHECK,
                               float(sig) if sig not in (None, "") else None))
    return pts


def read_csv(text_or_path, frame, **kw) -> list[SurveyPoint]:
    """Survey points from a CSV file path or CSV text."""
    if isinstance(text_or_path, Path) or (isinstance(text_or_path, str)
                                          and "\n" not in text_or_path
                                          and Path(text_or_path).exists()):
        text = Path(text_or_path).read_text()
    else:
        text = str(text_or_path)
    return points_from_rows(csv.DictReader(io.StringIO(text)), frame, **kw)


__all__ = ["SurveyPoint", "Correction", "error_stats", "fit_correction", "evaluate",
           "points_from_rows", "read_csv", "ASPRS_MIN_CHECKPOINTS", "GCP", "CHECK"]
