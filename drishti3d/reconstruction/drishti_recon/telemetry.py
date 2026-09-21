"""Telemetry ingestion and validation.

Accepts CSV, JSON, or SRT (DJI-style) telemetry.  Required fields:
``timestamp, latitude, longitude, altitude``.  Optional: roll, pitch, yaw,
velocity, barometric_altitude, focal_length, fx, fy, cx, cy, distortion,
rtk_status, gps_accuracy.  Returns a normalised list of samples plus a
validation report -- missing/invalid rows are reported, never silently dropped.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
import csv
import json
import re
import math


@dataclass
class TelemetrySample:
    timestamp: float
    latitude: float
    longitude: float
    altitude: float
    roll: float | None = None
    pitch: float | None = None
    yaw: float | None = None
    velocity: float | None = None
    gps_accuracy: float | None = None
    rtk_status: str | None = None
    extra: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        d = {k: v for k, v in self.__dict__.items() if k != "extra"}
        d.update(self.extra)
        return d


#: A mission is labelled RTK only if this fraction of its samples carry a fixed
#: RTK solution. Scale is fitted over the whole contributing track, so a track
#: that is mostly float or autonomous is not an RTK-derived scale however many
#: fixed samples it also contains.
RTK_FRACTION_REQUIRED = 0.9

_RTK_FIXED_LABELS = ("RTK", "FIXED", "4", "RTK_FIXED")
_RTK_FLOAT_LABELS = ("FLOAT", "5", "RTK_FLOAT")


@dataclass
class TelemetryReport:
    samples: list[TelemetrySample]
    n_input_rows: int
    n_valid: int
    warnings: list[str]
    #: Fraction of samples carrying a fixed RTK solution, 0.0 to 1.0.
    #: This used to be a bare ``has_rtk`` boolean set by ``any()``, so a single
    #: RTK-labelled row among thousands made the pipeline label the mission's
    #: scale source "rtk" -- a claim about the accuracy of the whole track made
    #: on the evidence of one sample.
    rtk_fixed_fraction: float = 0.0
    #: Counts by fix quality, so "unknown" stays distinguishable from "poor".
    fix_quality_counts: dict = field(default_factory=dict)
    intrinsics: dict | None = None  # fx,fy,cx,cy if present in telemetry

    @property
    def ok(self) -> bool:
        return self.n_valid >= 2

    @property
    def has_rtk(self) -> bool:
        """Whether this mission's scale may be described as RTK-derived."""
        return self.rtk_fixed_fraction >= RTK_FRACTION_REQUIRED


_ALIASES = {
    "timestamp": ["timestamp", "time", "t", "ts", "seconds", "frame_time"],
    "latitude": ["latitude", "lat", "gps_lat"],
    "longitude": ["longitude", "lon", "lng", "long", "gps_lon"],
    "altitude": ["altitude", "alt", "height", "gps_alt", "ellipsoidal_altitude"],
    "roll": ["roll"], "pitch": ["pitch", "gimbal_pitch"],
    "yaw": ["yaw", "heading", "compass_heading"],
    "velocity": ["velocity", "speed", "ground_speed"],
    "gps_accuracy": ["gps_accuracy", "hdop", "accuracy", "hacc"],
    "rtk_status": ["rtk_status", "rtk", "fix_type"],
}


def _norm_key(k: str) -> str | None:
    kl = k.strip().lower()
    for canon, al in _ALIASES.items():
        if kl in al:
            return canon
    return None


def _to_float(v):
    try:
        return float(str(v).strip())
    except (ValueError, TypeError):
        return None


def _valid_row(lat, lon, alt) -> bool:
    return (lat is not None and lon is not None and alt is not None
            and -90 <= lat <= 90 and -180 <= lon <= 180
            and math.isfinite(alt))


def parse_csv(path: Path, warnings: list[str]) -> tuple[list[TelemetrySample], dict | None]:
    samples = []
    intr = {}
    with open(path, newline="") as f:
        reader = csv.DictReader(f)
        if reader.fieldnames is None:
            raise ValueError("empty CSV")
        colmap = {c: _norm_key(c) for c in reader.fieldnames}
        for i, row in enumerate(reader):
            data = {}
            extra = {}
            for col, val in row.items():
                canon = colmap.get(col)
                if canon:
                    data[canon] = val
                elif col and col.strip().lower() in ("fx", "fy", "cx", "cy", "focal_length"):
                    fv = _to_float(val)
                    if fv is not None:
                        intr[col.strip().lower()] = fv
                elif val not in (None, ""):
                    extra[col] = val
            lat = _to_float(data.get("latitude"))
            lon = _to_float(data.get("longitude"))
            alt = _to_float(data.get("altitude"))
            ts = _to_float(data.get("timestamp"))
            if ts is None:
                ts = float(i)
            if not _valid_row(lat, lon, alt):
                warnings.append(f"row {i}: invalid/missing lat/lon/alt, skipped")
                continue
            samples.append(TelemetrySample(
                timestamp=ts, latitude=lat, longitude=lon, altitude=alt,
                roll=_to_float(data.get("roll")), pitch=_to_float(data.get("pitch")),
                yaw=_to_float(data.get("yaw")), velocity=_to_float(data.get("velocity")),
                gps_accuracy=_to_float(data.get("gps_accuracy")),
                rtk_status=data.get("rtk_status"), extra=extra))
    return samples, (intr or None)


def parse_json(path: Path, warnings: list[str]):
    obj = json.loads(Path(path).read_text())
    rows = obj["samples"] if isinstance(obj, dict) and "samples" in obj else obj
    if not isinstance(rows, list):
        raise ValueError("JSON telemetry must be a list or {'samples': [...]}")
    samples = []
    for i, row in enumerate(rows):
        data = {}
        for k, v in row.items():
            canon = _norm_key(k)
            if canon:
                data[canon] = v
        lat = _to_float(data.get("latitude"))
        lon = _to_float(data.get("longitude"))
        alt = _to_float(data.get("altitude"))
        ts = _to_float(data.get("timestamp"))
        if ts is None:
            ts = float(i)
        if not _valid_row(lat, lon, alt):
            warnings.append(f"row {i}: invalid/missing lat/lon/alt, skipped")
            continue
        samples.append(TelemetrySample(ts, lat, lon, alt,
                       roll=_to_float(data.get("roll")), pitch=_to_float(data.get("pitch")),
                       yaw=_to_float(data.get("yaw")), velocity=_to_float(data.get("velocity")),
                       gps_accuracy=_to_float(data.get("gps_accuracy")),
                       rtk_status=data.get("rtk_status")))
    return samples, None


_SRT_TIME = re.compile(r"(\d{2}):(\d{2}):(\d{2})[,.](\d{3})")
_SRT_LAT = re.compile(r"\blatitude\s*[:=]?\s*(-?\d+\.\d+)", re.I)
_SRT_LON = re.compile(r"\blong?itude\s*[:=]?\s*(-?\d+\.\d+)", re.I)
# DJI writes BOTH rel_alt (above take-off) and abs_alt (above MSL) on one line.
# They are metres apart and mean different things, so match each explicitly
# rather than letting one alternation pick whichever appears first.
_SRT_ABS_ALT = re.compile(r"\babs_?alt(?:itude)?\s*[:=]?\s*(-?\d+\.?\d*)", re.I)
_SRT_REL_ALT = re.compile(r"\brel_?alt(?:itude)?\s*[:=]?\s*(-?\d+\.?\d*)", re.I)
# Gimbal attitude -- the camera's actual pointing, without which the frame
# chain in frames.py cannot be built. DJI uses gb_* and Autel gimbal_*.
_SRT_GB_YAW = re.compile(r"\b(?:gb|gimbal)_?yaw\s*[:=]?\s*(-?\d+\.?\d*)", re.I)
_SRT_GB_PITCH = re.compile(r"\b(?:gb|gimbal)_?pitch\s*[:=]?\s*(-?\d+\.?\d*)", re.I)
_SRT_GB_ROLL = re.compile(r"\b(?:gb|gimbal)_?roll\s*[:=]?\s*(-?\d+\.?\d*)", re.I)
# Airframe attitude, when present (needed for the lever arm).
_SRT_FL_YAW = re.compile(r"\b(?:fl|flight|drone)_?yaw\s*[:=]?\s*(-?\d+\.?\d*)", re.I)
_SRT_FL_PITCH = re.compile(r"\b(?:fl|flight|drone)_?pitch\s*[:=]?\s*(-?\d+\.?\d*)", re.I)
_SRT_FL_ROLL = re.compile(r"\b(?:fl|flight|drone)_?roll\s*[:=]?\s*(-?\d+\.?\d*)", re.I)
_SRT_FOCAL = re.compile(r"\bfocal_?len\w*\s*[:=]?\s*(-?\d+\.?\d*)", re.I)


def _srt_num(rx, block):
    m = rx.search(block)
    return float(m.group(1)) if m else None


def parse_srt(path: Path, warnings: list[str]):
    text = Path(path).read_text(errors="ignore")
    blocks = re.split(r"\n\s*\n", text)
    samples = []
    for b in blocks:
        tm = _SRT_TIME.search(b)
        la = _SRT_LAT.search(b)
        lo = _SRT_LON.search(b)

        if not (la and lo):
            continue
        ts = 0.0
        if tm:
            h, m, s, ms = map(int, tm.groups())
            ts = h * 3600 + m * 60 + s + ms / 1000.0
        lat, lon = float(la.group(1)), float(lo.group(1))
        abs_alt = _srt_num(_SRT_ABS_ALT, b)
        rel_alt = _srt_num(_SRT_REL_ALT, b)
        # Prefer absolute (MSL) altitude; fall back to relative and say so,
        # because a relative altitude silently treated as MSL puts the whole
        # reconstruction hundreds of metres out vertically.
        alt = abs_alt if abs_alt is not None else (rel_alt or 0.0)
        if abs_alt is None and rel_alt is not None:
            alt_kind = "relative_to_takeoff"
        elif abs_alt is not None:
            alt_kind = "msl"
        else:
            alt_kind = "missing"

        gb = [_srt_num(r, b) for r in
              (_SRT_GB_ROLL, _SRT_GB_PITCH, _SRT_GB_YAW)]
        fl = [_srt_num(r, b) for r in
              (_SRT_FL_ROLL, _SRT_FL_PITCH, _SRT_FL_YAW)]
        focal = _srt_num(_SRT_FOCAL, b)

        extra = {"altitude_kind": alt_kind}
        if rel_alt is not None:
            extra["rel_alt"] = rel_alt
        if abs_alt is not None:
            extra["abs_alt"] = abs_alt
        if any(v is not None for v in gb):
            extra["gimbal_rpy_deg"] = gb
        if focal is not None:
            extra["focal_len_mm"] = focal

        if _valid_row(lat, lon, alt):
            samples.append(TelemetrySample(
                ts, lat, lon, alt,
                roll=fl[0], pitch=fl[1], yaw=fl[2], extra=extra))
    if not samples:
        warnings.append("SRT parsed but no GPS subtitles found")
    else:
        kinds = {s_.extra.get("altitude_kind") for s_ in samples}
        if "relative_to_takeoff" in kinds:
            warnings.append(
                "SRT altitude is relative to take-off, not MSL; absolute "
                "vertical position will be offset by the launch elevation")
        if not any("gimbal_rpy_deg" in s_.extra for s_ in samples):
            warnings.append(
                "SRT has no gimbal attitude; camera pointing cannot be "
                "derived from telemetry alone")
    return samples, None


def load(path: str | Path) -> TelemetryReport:
    """Auto-detect format by extension and parse."""
    path = Path(path)
    warnings: list[str] = []
    ext = path.suffix.lower()
    if ext == ".csv":
        samples, intr = parse_csv(path, warnings)
    elif ext == ".json":
        samples, intr = parse_json(path, warnings)
    elif ext == ".srt":
        samples, intr = parse_srt(path, warnings)
    else:
        raise ValueError(f"unsupported telemetry format: {ext}")

    n_in = len(samples) + len(warnings)
    samples.sort(key=lambda s: s.timestamp)
    counts = {"fixed": 0, "float": 0, "other": 0, "unknown": 0}
    for smp in samples:
        if not smp.rtk_status:
            counts["unknown"] += 1
            continue
        label = str(smp.rtk_status).upper()
        if label in _RTK_FIXED_LABELS:
            counts["fixed"] += 1
        elif label in _RTK_FLOAT_LABELS:
            counts["float"] += 1
        else:
            counts["other"] += 1
    frac = counts["fixed"] / len(samples) if samples else 0.0
    if 0.0 < frac < RTK_FRACTION_REQUIRED:
        warnings.append(
            f"only {frac:.0%} of telemetry samples carry a fixed RTK solution; "
            f"scale is treated as ordinary GNSS, not RTK")
    return TelemetryReport(samples, n_in, len(samples), warnings,
                           rtk_fixed_fraction=frac, fix_quality_counts=counts,
                           intrinsics=intr)


def kalman_smooth(times, positions, *, sigma_m=5.0, accel_m_s2=1.0):
    """RTS-smoothed positions from a GNSS track (Intelligence Edition §8).

    Forward constant-velocity Kalman filter followed by Rauch–Tung–Striebel
    backward smoothing, per axis. ``sigma_m`` is the per-sample measurement
    sigma (scalar or per-sample array); ``accel_m_s2`` the process noise —
    how hard the vehicle may genuinely accelerate. Returns (smoothed, sigma):
    positions of the same shape and the per-sample posterior sigma, which is
    what downstream consumers (Sim(3) weights, pose-graph priors) should use
    instead of the raw receiver sigma.

    A smoother only removes *uncorrelated* noise; slowly-varying receiver bias
    passes straight through. Validate on data with independent truth before
    trusting the posterior sigmas — eval/agz_dense_eval.py does exactly that.
    """
    import numpy as np
    t = np.asarray(times, float)
    z = np.asarray(positions, float)
    n = len(t)
    if n < 3:
        return z.copy(), np.full(n, float(np.mean(sigma_m)))
    sig = np.broadcast_to(np.asarray(sigma_m, float), (n,)).copy()
    q = float(accel_m_s2) ** 2

    smoothed = np.empty_like(z)
    post_var = np.empty(n)

    for ax in range(z.shape[1]):
        # forward pass
        x = np.array([z[0, ax], 0.0])
        P = np.diag([sig[0] ** 2, 25.0])
        xs_f = np.empty((n, 2)); Ps_f = np.empty((n, 2, 2))
        xs_p = np.empty((n, 2)); Ps_p = np.empty((n, 2, 2))
        xs_f[0], Ps_f[0] = x, P
        xs_p[0], Ps_p[0] = x, P
        for k in range(1, n):
            dt = max(t[k] - t[k - 1], 1e-3)
            F = np.array([[1.0, dt], [0.0, 1.0]])
            Q = q * np.array([[dt ** 4 / 4, dt ** 3 / 2],
                              [dt ** 3 / 2, dt ** 2]])
            x = F @ x
            P = F @ P @ F.T + Q
            xs_p[k], Ps_p[k] = x, P
            # update
            r = sig[k] ** 2
            S = P[0, 0] + r
            K = P[:, 0] / S
            x = x + K * (z[k, ax] - x[0])
            P = P - np.outer(K, P[0, :])
            xs_f[k], Ps_f[k] = x, P
        # RTS backward pass
        xs_s = xs_f.copy(); Ps_s = Ps_f.copy()
        for k in range(n - 2, -1, -1):
            dt = max(t[k + 1] - t[k], 1e-3)
            F = np.array([[1.0, dt], [0.0, 1.0]])
            C = Ps_f[k] @ F.T @ np.linalg.inv(Ps_p[k + 1])
            xs_s[k] = xs_f[k] + C @ (xs_s[k + 1] - xs_p[k + 1])
            Ps_s[k] = Ps_f[k] + C @ (Ps_s[k + 1] - Ps_p[k + 1]) @ C.T
        smoothed[:, ax] = xs_s[:, 0]
        if ax == 0:
            post_var[:] = Ps_s[:, 0, 0]
        else:
            post_var[:] = np.maximum(post_var, Ps_s[:, 0, 0])
    return smoothed, np.sqrt(np.maximum(post_var, 1e-9))
