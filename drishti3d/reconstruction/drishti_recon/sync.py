"""Frame <-> telemetry synchronization.

Maps each frame timestamp to interpolated telemetry.  Positions are
interpolated linearly in a local ENU frame; orientation (yaw) is interpolated
angle-aware.  Records a per-frame synchronization residual/confidence and
supports a configurable video-to-telemetry time offset.
"""
from __future__ import annotations

from dataclasses import dataclass
import numpy as np

from .geo import ENUFrame
from .telemetry import TelemetrySample


@dataclass
class SyncedFrame:
    frame_index: int
    timestamp: float
    enu: np.ndarray            # (3,) east, north, up metres
    yaw: float | None
    gps_accuracy: float | None
    residual: float            # seconds to nearest telemetry sample
    confidence: float          # [0,1]


def _angle_interp(a0, a1, w):
    if a0 is None or a1 is None:
        return a0 if a0 is not None else a1
    d = ((a1 - a0 + 180) % 360) - 180
    return (a0 + w * d) % 360


def build_enu_frame(samples: list[TelemetrySample]) -> ENUFrame:
    lat = [s.latitude for s in samples]
    lon = [s.longitude for s in samples]
    alt = [s.altitude for s in samples]
    return ENUFrame.from_points(lat, lon, alt)


def synchronize(frame_times, samples: list[TelemetrySample], frame: ENUFrame,
                *, offset: float = 0.0):
    """Interpolate telemetry to each frame time.

    frame_times: iterable of (frame_index, timestamp_seconds).
    Returns list[SyncedFrame].  ``offset`` shifts video time relative to
    telemetry time (t_tel = t_video + offset).
    """
    if len(samples) < 1:
        raise ValueError("no telemetry samples")
    ts = np.array([s.timestamp for s in samples])
    enu = frame.geodetic_to_enu([s.latitude for s in samples],
                                [s.longitude for s in samples],
                                [s.altitude for s in samples])
    yaws = [s.yaw for s in samples]
    accs = [s.gps_accuracy for s in samples]
    span = float(ts[-1] - ts[0]) or 1.0

    out = []
    for fi, t in frame_times:
        tt = t + offset
        j = int(np.searchsorted(ts, tt))
        if j <= 0:
            e, yaw, acc, resid = enu[0], yaws[0], accs[0], abs(tt - ts[0])
        elif j >= len(ts):
            e, yaw, acc, resid = enu[-1], yaws[-1], accs[-1], abs(tt - ts[-1])
        else:
            t0, t1 = ts[j - 1], ts[j]
            w = (tt - t0) / (t1 - t0) if t1 > t0 else 0.0
            e = enu[j - 1] * (1 - w) + enu[j] * w
            yaw = _angle_interp(yaws[j - 1], yaws[j], w)
            a0, a1 = accs[j - 1], accs[j]
            acc = None if a0 is None or a1 is None else a0 * (1 - w) + a1 * w
            resid = min(abs(tt - t0), abs(tt - t1))
        # confidence decays with residual relative to sample span
        conf = float(np.clip(1.0 - resid / (0.5 * span + 1e-6), 0.0, 1.0))
        out.append(SyncedFrame(fi, t, np.asarray(e, float), yaw, acc, float(resid), conf))
    return out
