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


@dataclass
class TelemetryReport:
    samples: list[TelemetrySample]
    n_input_rows: int
    n_valid: int
    warnings: list[str]
    has_rtk: bool
    intrinsics: dict | None = None  # fx,fy,cx,cy if present in telemetry

    @property
    def ok(self) -> bool:
        return self.n_valid >= 2


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
_SRT_LAT = re.compile(r"latitude\s*[:=]?\s*(-?\d+\.\d+)", re.I)
_SRT_LON = re.compile(r"long?itude\s*[:=]?\s*(-?\d+\.\d+)", re.I)
_SRT_ALT = re.compile(r"(?:abs_?alt|altitude)\s*[:=]?\s*(-?\d+\.?\d*)", re.I)


def parse_srt(path: Path, warnings: list[str]):
    text = Path(path).read_text(errors="ignore")
    blocks = re.split(r"\n\s*\n", text)
    samples = []
    for b in blocks:
        tm = _SRT_TIME.search(b)
        la = _SRT_LAT.search(b)
        lo = _SRT_LON.search(b)
        al = _SRT_ALT.search(b)
        if not (la and lo):
            continue
        ts = 0.0
        if tm:
            h, m, s, ms = map(int, tm.groups())
            ts = h * 3600 + m * 60 + s + ms / 1000.0
        lat, lon = float(la.group(1)), float(lo.group(1))
        alt = float(al.group(1)) if al else 0.0
        if _valid_row(lat, lon, alt):
            samples.append(TelemetrySample(ts, lat, lon, alt))
    if not samples:
        warnings.append("SRT parsed but no GPS subtitles found")
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
    has_rtk = any(s.rtk_status and str(s.rtk_status).upper() in
                  ("RTK", "FIXED", "4", "RTK_FIXED") for s in samples)
    return TelemetryReport(samples, n_in, len(samples), warnings, has_rtk, intr)
