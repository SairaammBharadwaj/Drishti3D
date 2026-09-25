"""Sensor-model corrections between the camera and the GNSS/IMU it flies with.

The reconstruction and the telemetry describe the same flight, but they do not
describe it from the same place or at the same instant. Three offsets sit between
them, and each one biases georegistration in a way no downstream stage can detect
because the result still looks self-consistent:

* **Time offset.** The video clock and the GNSS clock start independently. A
  constant offset slides every frame onto the wrong GNSS sample, which the
  aligner then absorbs as a spurious translation along the flight direction.
* **Lever arm.** The GNSS antenna is not the camera. On a small drone the two are
  10-30 cm apart, and as the aircraft yaws that fixed body-frame offset sweeps a
  circle in world coordinates.
* **Rolling shutter.** Most consumer drone cameras expose the image one row at a
  time. Under fast rotation the top and bottom of a frame are taken from
  measurably different poses, which violates the single-pose assumption the whole
  pipeline rests on.

This module estimates the first, corrects the second, and *detects and reports*
the third. Detection rather than correction is deliberate: a rolling-shutter
bundle adjustment is a much larger change, and a warning that the assumption is
being violated is more honest than silently producing a number.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np


# --------------------------------------------------------------------------- #
# time offset
# --------------------------------------------------------------------------- #
@dataclass
class TimeOffsetResult:
    offset_s: float                  # add to video time to reach telemetry time
    correlation: float               # peak normalised correlation, [-1, 1]
    confidence: float                # [0,1]: peak height and how much it stands out
    accepted: bool                   # whether it should be applied
    reason: str = ""
    search_s: float = 0.0
    n_samples: int = 0
    curve: list = field(default_factory=list)   # (offset, correlation) pairs
    #: Half-width of the offsets the data cannot tell apart (V3.1 plan section
    #: 8: store synchronisation uncertainty, do not assume perfect sync). Set by
    #: the alignment refinement: offsets whose residual is within 10% + 2 cm of
    #: the minimum, at least half a search step. None when not estimated.
    uncertainty_s: float | None = None

    def to_dict(self) -> dict:
        return {"offset_s": self.offset_s, "correlation": self.correlation,
                "confidence": self.confidence, "accepted": self.accepted,
                "reason": self.reason, "search_s": self.search_s,
                "n_samples": self.n_samples, "uncertainty_s": self.uncertainty_s}


def _speed_profile(times, positions, grid):
    """Resample |velocity| onto a uniform time grid.

    Speed is used rather than position because it is invariant to the unknown
    rigid transform between the reconstruction frame and ENU -- only the scale
    survives, and normalising removes that too. So the two profiles can be
    compared before any alignment has been computed.
    """
    times = np.asarray(times, float)
    positions = np.asarray(positions, float)
    order = np.argsort(times)
    times, positions = times[order], positions[order]
    if len(times) < 3:
        return None
    dt = np.diff(times)
    good = dt > 1e-9
    if not good.any():
        return None
    v = np.linalg.norm(np.diff(positions, axis=0), axis=1)[good] / dt[good]
    t_mid = (times[:-1] + times[1:])[good] / 2.0
    prof = np.interp(grid, t_mid, v, left=np.nan, right=np.nan)
    return prof


def _normalise(x):
    x = np.asarray(x, float)
    ok = np.isfinite(x)
    if ok.sum() < 3:
        return None
    y = np.where(ok, x, np.nan)
    mu = np.nanmean(y)
    sd = np.nanstd(y)
    if not np.isfinite(sd) or sd < 1e-12:
        return None
    return (y - mu) / sd


def estimate_time_offset(video_times, cam_centers, tel_times, tel_positions, *,
                         search_s: float = 2.0, step_s: float = 0.02,
                         min_correlation: float = 0.5,
                         min_confidence: float = 0.3,
                         max_search_fraction: float = 0.25,
                         min_overlap_fraction: float = 0.6) -> TimeOffsetResult:
    """Estimate the constant video-to-telemetry time offset.

    Cross-correlates the *speed profile* of the reconstructed camera track
    against the speed profile of the GNSS track. Both are normalised, so neither
    the unknown metric scale nor the unknown orientation matters -- which is what
    makes this usable before georegistration rather than after it.

    Returns the offset to **add to video timestamps** to reach telemetry time.

    An offset is only ``accepted`` when the correlation peak is both high and
    *distinct*: a flight at constant speed has a flat correlation curve and
    genuinely cannot reveal its own timing, so reporting a confident number there
    would be inventing information.

    Two guards keep the search honest on short clips, both added after a 2-second
    fixture produced a confident +1.8 s offset that collapsed its georegistration:

    * ``max_search_fraction`` caps the search at a fraction of the overlapping
      span. Scanning +/-2 s across a 2 s flight is not a measurement.
    * ``min_overlap_fraction`` discards candidate offsets that leave too little
      of the two profiles overlapping. Correlation computed over a handful of
      surviving samples is noisy and biased upward, so large shifts otherwise win
      on luck rather than evidence.
    """
    video_times = np.asarray(video_times, float)
    tel_times = np.asarray(tel_times, float)
    if len(video_times) < 4 or len(tel_times) < 4:
        return TimeOffsetResult(0.0, 0.0, 0.0, False, "too few samples",
                                search_s, 0)

    lo = max(video_times.min(), tel_times.min() - search_s)
    hi = min(video_times.max(), tel_times.max() + search_s)
    if hi - lo < 3 * step_s:
        return TimeOffsetResult(0.0, 0.0, 0.0, False, "no overlapping time span",
                                search_s, 0)

    span = float(hi - lo)
    # Never search further than a fraction of the data actually available.
    search_s = float(min(search_s, max(max_search_fraction * span, step_s)))
    grid = np.arange(lo, hi, max(step_s, span / 2000.0))
    cam_prof = _speed_profile(video_times, cam_centers, grid)
    if cam_prof is None:
        return TimeOffsetResult(0.0, 0.0, 0.0, False, "no camera speed profile",
                                search_s, 0)
    cam_n = _normalise(cam_prof)
    if cam_n is None:
        return TimeOffsetResult(0.0, 0.0, 0.0, False,
                                "camera speed is constant; timing unobservable",
                                search_s, 0)

    offsets = np.arange(-search_s, search_s + step_s, step_s)
    n_cam_valid = int(np.isfinite(cam_n).sum())
    min_overlap = max(5, int(min_overlap_fraction * n_cam_valid))
    corrs = []
    for off in offsets:
        # Shifting the telemetry sampling times by -off is equivalent to adding
        # off to the video times, which is the sign convention we return.
        tel_prof = _speed_profile(tel_times - off, tel_positions, grid)
        if tel_prof is None:
            corrs.append(np.nan)
            continue
        tel_n = _normalise(tel_prof)
        if tel_n is None:
            corrs.append(np.nan)
            continue
        ok = np.isfinite(cam_n) & np.isfinite(tel_n)
        # Require a substantial overlap: a correlation measured over a sliver of
        # the flight is not comparable with one measured over all of it.
        corrs.append(float(np.mean(cam_n[ok] * tel_n[ok]))
                     if ok.sum() >= min_overlap else np.nan)
    corrs = np.asarray(corrs, float)
    if not np.isfinite(corrs).any():
        return TimeOffsetResult(0.0, 0.0, 0.0, False, "correlation undefined",
                                search_s, int(len(grid)))

    k = int(np.nanargmax(corrs))
    peak = float(corrs[k])
    best = float(offsets[k])

    # Sub-step refinement by fitting a parabola through the peak and its
    # neighbours; the sampling step would otherwise floor the resolution.
    if 0 < k < len(corrs) - 1 and np.isfinite(corrs[k - 1]) and np.isfinite(corrs[k + 1]):
        y0, y1, y2 = corrs[k - 1], corrs[k], corrs[k + 1]
        denom = (y0 - 2 * y1 + y2)
        if abs(denom) > 1e-12:
            best = float(offsets[k] + 0.5 * (y0 - y2) / denom * step_s)

    # Distinctness: how far the peak stands above the rest of the curve. A flat
    # curve means the motion carries no timing information, whatever its height.
    others = corrs[np.isfinite(corrs)]
    spread = float(others.std())
    prominence = (peak - float(others.mean())) / spread if spread > 1e-9 else 0.0
    confidence = float(np.clip(min(max(peak, 0.0), 1.0) * np.clip(prominence / 3.0, 0, 1), 0, 1))

    # A peak pinned to the edge of the search window means the true offset may
    # lie outside it; the estimate is not trustworthy either way.
    at_edge = k in (0, len(corrs) - 1) or not np.isfinite(corrs).all()
    edge_pinned = bool(k <= 1 or k >= len(corrs) - 2)
    accepted = bool(peak >= min_correlation and confidence >= min_confidence
                    and not edge_pinned)
    reason = "" if accepted else (
        "correlation peak sits at the edge of the search window; the true "
        "offset may lie outside it" if edge_pinned and peak >= min_correlation
        else
        f"peak correlation {peak:.2f} / confidence {confidence:.2f} below "
        f"thresholds ({min_correlation}, {min_confidence}); "
        "motion may be too uniform to reveal timing")
    return TimeOffsetResult(best, peak, confidence, accepted, reason,
                            search_s, int(len(grid)),
                            curve=[(float(o), float(c)) for o, c in
                                   zip(offsets, corrs) if np.isfinite(c)])


def refine_time_offset_by_alignment(video_times, cam_centers, tel_times,
                                    tel_positions, *, start_s: float = 0.0,
                                    search_s: float = 2.0, step_s: float = 0.02,
                                    max_search_fraction: float = 0.25,
                                    min_cameras: int = 8,
                                    min_gain: float = 0.8) -> TimeOffsetResult:
    """Refine the video-to-telemetry offset by where the positions agree best.

    :func:`estimate_time_offset` correlates speed profiles, which carry almost
    no timing information on a constant-speed survey: on MARS-LVIG HKisland03
    (8.9 m/s throughout) it found -0.21 s at confidence 0.38, while the DJI RTK
    messages actually lag the camera by ~0.6 s -- 5 m along track -- and the
    georegistration absorbed the rest as a 2.28 m residual.

    Here each candidate offset re-samples the GNSS track at the keyframe times
    and fits the same 7-DoF similarity georegistration fits; the offset with the
    smallest residual wins. Positions, unlike speeds, differ between offsets on
    every straight leg, so a lawnmower survey is well conditioned. Returns the
    offset to **add to video timestamps**, like :func:`estimate_time_offset`.

    Accepted only when all of these hold, so it never overrides the speed
    estimate on data that cannot support it:

    * at least ``min_cameras`` cameras spanning two dimensions (a straight line
      leaves the similarity's roll free, so the residual cannot resolve time);
    * the minimum is not on the edge of the search window;
    * it beats the residual at ``start_s`` by the factor ``min_gain``.

    Uses only the reconstruction and the telemetry -- never a reference.
    """
    from .geo import umeyama_sim3

    vt = np.asarray(video_times, float)
    cc = np.asarray(cam_centers, float)
    tt = np.asarray(tel_times, float)
    tp = np.asarray(tel_positions, float)

    def fail(reason):
        return TimeOffsetResult(float(start_s), 0.0, 0.0, False, reason,
                                search_s, int(len(vt)))

    if len(vt) < min_cameras or len(tt) < 4:
        return fail(f"fewer than {min_cameras} cameras")
    sv = np.linalg.svd(cc - cc.mean(0), compute_uv=False)
    if sv[0] <= 0 or sv[1] / sv[0] < 0.05:
        return fail("camera path is nearly a straight line; the similarity "
                    "cannot resolve timing")
    span = float(vt.max() - vt.min())
    search_s = float(min(search_s, max(max_search_fraction * span, step_s)))
    order = np.argsort(tt)
    tt, tp = tt[order], tp[order]

    def residual(off):
        tq = vt + off
        inside = (tq >= tt[0]) & (tq <= tt[-1])
        if inside.sum() < min_cameras:
            return np.nan
        dst = np.column_stack([np.interp(tq[inside], tt, tp[:, j]) for j in range(3)])
        sim = umeyama_sim3(cc[inside], dst)
        r = dst - sim.apply(cc[inside])
        return float(np.sqrt((r ** 2).sum(1).mean()))

    offsets = np.round(start_s + np.arange(-search_s, search_s + step_s / 2, step_s), 6)
    res = np.array([residual(o) for o in offsets])
    if not np.isfinite(res).any():
        return fail("no offset leaves enough cameras inside the telemetry")
    k = int(np.nanargmin(res))
    best = float(offsets[k])
    # Sub-step refinement through the minimum and its neighbours.
    if 0 < k < len(res) - 1 and np.isfinite(res[k - 1]) and np.isfinite(res[k + 1]):
        y0, y1, y2 = res[k - 1], res[k], res[k + 1]
        denom = y0 - 2 * y1 + y2
        if denom > 1e-12:
            best = float(offsets[k] + 0.5 * (y0 - y2) / denom * step_s)
    r0 = residual(start_s)
    rb = float(res[k])
    gain = rb / r0 if r0 and np.isfinite(r0) and r0 > 0 else 1.0
    edge = k <= 1 or k >= len(res) - 2
    accepted = bool(not edge and gain <= min_gain)
    reason = "" if accepted else (
        "residual minimum at the edge of the search window" if edge else
        f"residual {rb:.3f} m is not clearly below {r0:.3f} m at the speed-based "
        f"offset (ratio {gain:.2f} > {min_gain})")
    # Offsets within 10% (plus 2 cm, about RTK noise) of the best residual are
    # not distinguishable; never report less than half the search step.
    near = offsets[np.isfinite(res) & (res <= 1.10 * rb + 0.02)]
    half_width = (max(float((near.max() - near.min()) / 2), step_s / 2)
                  if len(near) else None)
    # `correlation` does not apply here; the residuals are in `curve`
    # (offset, RMSE m), and confidence is the relative residual reduction.
    return TimeOffsetResult(best, 0.0, float(np.clip(1.0 - gain, 0, 1)), accepted,
                            reason, search_s, int(len(vt)),
                            curve=[(float(o), float(r)) for o, r in
                                   zip(offsets, res) if np.isfinite(r)],
                            uncertainty_s=half_width)


# --------------------------------------------------------------------------- #
# lever arm
# --------------------------------------------------------------------------- #
def body_to_enu(roll_deg, pitch_deg, yaw_deg) -> np.ndarray:
    """Rotation from body axes (x forward, y right, z down) to ENU.

    Yaw is a compass heading: 0 deg = north, increasing clockwise (east).
    """
    r = np.radians(float(roll_deg or 0.0))
    p = np.radians(float(pitch_deg or 0.0))
    y = np.radians(float(yaw_deg or 0.0))
    cr, sr = np.cos(r), np.sin(r)
    cp, sp = np.cos(p), np.sin(p)
    cy, sy = np.cos(y), np.sin(y)
    # body -> NED
    R_nb = np.array([
        [cp * cy, sr * sp * cy - cr * sy, cr * sp * cy + sr * sy],
        [cp * sy, sr * sp * sy + cr * cy, cr * sp * sy - sr * cy],
        [-sp,     sr * cp,                cr * cp],
    ])
    # NED -> ENU swaps north/east and flips down
    R_en = np.array([[0.0, 1.0, 0.0], [1.0, 0.0, 0.0], [0.0, 0.0, -1.0]])
    return R_en @ R_nb


def apply_lever_arm(gps_enu, lever_body, roll=None, pitch=None, yaw=None):
    """Move GNSS antenna positions to the camera's optical centre.

    ``lever_body`` is the camera's position relative to the antenna, in body axes
    (x forward, y right, z down), metres. As the aircraft rotates, that fixed
    offset traces a path in world coordinates -- which is exactly why ignoring it
    on a yawing flight injects a rotating bias rather than a constant one that
    alignment could absorb.

    Attitude is required: without it the body offset cannot be placed in the
    world, and the positions are returned unchanged.
    """
    gps_enu = np.asarray(gps_enu, float).reshape(-1, 3)
    lever = np.asarray(lever_body, float).ravel()
    if lever.shape != (3,) or not np.any(lever):
        return gps_enu.copy(), False
    n = len(gps_enu)
    if roll is None and pitch is None and yaw is None:
        return gps_enu.copy(), False

    def _col(v):
        if v is None:
            return np.zeros(n)
        a = np.asarray(v, float).ravel()
        return np.full(n, a[0]) if a.size == 1 else a[:n]

    r, p, y = _col(roll), _col(pitch), _col(yaw)
    out = gps_enu.copy()
    for i in range(n):
        out[i] = gps_enu[i] + body_to_enu(r[i], p[i], y[i]) @ lever
    return out, True


# --------------------------------------------------------------------------- #
# rolling shutter
# --------------------------------------------------------------------------- #
@dataclass
class RollingShutterCheck:
    max_rate_deg_s: float
    p95_rate_deg_s: float
    readout_s: float
    worst_smear_deg: float
    severity: str                 # none | mild | severe
    message: str = ""

    def to_dict(self) -> dict:
        return {"max_rate_deg_s": self.max_rate_deg_s,
                "p95_rate_deg_s": self.p95_rate_deg_s,
                "readout_s": self.readout_s,
                "worst_smear_deg": self.worst_smear_deg,
                "severity": self.severity, "message": self.message}


def detect_rolling_shutter(rotations, times, *, readout_s: float = 1 / 60.0,
                           mild_deg: float = 0.15,
                           severe_deg: float = 0.5) -> RollingShutterCheck:
    """Flag captures where a global-shutter assumption is being violated.

    ``rotations`` are per-frame world->camera matrices, ``times`` their
    timestamps. The angular rate between consecutive frames, multiplied by the
    sensor readout time, gives how far the scene rotates between the first and
    last row of one image. Beyond a fraction of a degree that motion is larger
    than the feature-matching precision the reconstruction depends on.

    This reports rather than corrects: rolling-shutter bundle adjustment
    estimates motion *during* readout and is a much larger change. Saying the
    assumption is violated is more useful than a silently degraded number.
    """
    if readout_s is not None and readout_s <= 0:
        # A global shutter exposes every row at once: there is no readout skew
        # to estimate. MARS-LVIG's global-shutter camera was warned about as
        # "mild smear" under the 1/60 s default, a false alarm (DEC-043).
        return RollingShutterCheck(0.0, 0.0, 0.0, 0.0, "none",
                                   "global shutter declared; not applicable")
    R = [np.asarray(m, float) for m in rotations]
    t = np.asarray(times, float)
    if len(R) < 2 or len(t) != len(R):
        return RollingShutterCheck(0.0, 0.0, readout_s, 0.0, "none",
                                   "too few poses to assess")
    rates = []
    for i in range(1, len(R)):
        dt = float(t[i] - t[i - 1])
        if dt <= 1e-9:
            continue
        rel = R[i] @ R[i - 1].T
        c = (np.trace(rel) - 1.0) / 2.0
        ang = float(np.degrees(np.arccos(np.clip(c, -1.0, 1.0))))
        rates.append(ang / dt)
    if not rates:
        return RollingShutterCheck(0.0, 0.0, readout_s, 0.0, "none",
                                   "no usable frame intervals")
    rates = np.asarray(rates, float)
    mx = float(rates.max())
    p95 = float(np.percentile(rates, 95))
    smear = p95 * readout_s
    if smear >= severe_deg:
        sev = "severe"
        msg = (f"rolling-shutter smear ~{smear:.2f} deg per frame at the 95th "
               f"percentile turn rate ({p95:.1f} deg/s, readout {readout_s*1000:.1f} ms). "
               "Poses and reprojection residuals are biased; treat measurements "
               "from fast-yaw segments as unreliable.")
    elif smear >= mild_deg:
        sev = "mild"
        msg = (f"rolling-shutter smear ~{smear:.2f} deg per frame ({p95:.1f} deg/s). "
               "Small but above feature-matching precision; fly slower turns for "
               "measurement-grade capture.")
    else:
        sev = "none"
        msg = ""
    return RollingShutterCheck(mx, p95, float(readout_s), float(smear), sev, msg)


# --------------------------------------------------------------------------- #
# lens distortion
# --------------------------------------------------------------------------- #
def undistort_frames(frames, K, dist, *, inplace=False):
    """Undistort frames so the rest of the pipeline can assume a pinhole camera.

    Correcting once, up front, is preferable to threading distortion coefficients
    through triangulation, PnP, bundle adjustment and uncertainty propagation --
    every one of which would otherwise need its own distortion-aware variant, and
    any that was missed would fail silently.

    Returns ``(frames, K_new, applied)``. ``K_new`` is the intrinsic matrix valid
    for the undistorted images, which is *not* the input K. With ``inplace``
    each array is overwritten and the same list is returned, so at most one
    extra frame is in memory instead of a copy of every frame.
    """
    import cv2

    dist = np.asarray(dist, float).ravel() if dist is not None else None
    if dist is None or dist.size == 0 or not np.any(dist):
        return frames, np.asarray(K, float), False
    if not frames:
        return frames, np.asarray(K, float), False

    K = np.asarray(K, float)
    h, w = frames[0].shape[:2]
    # alpha=0 crops to the all-valid region, so no black border pixels enter
    # feature detection and masquerade as texture.
    K_new, _roi = cv2.getOptimalNewCameraMatrix(K, dist, (w, h), 0)
    map1, map2 = cv2.initUndistortRectifyMap(K, dist, None, K_new, (w, h),
                                             cv2.CV_16SC2)
    if inplace:
        # remap cannot write over its own source, so go through one temporary.
        for f in frames:
            f[...] = cv2.remap(f, map1, map2, cv2.INTER_LINEAR)
        return frames, np.asarray(K_new, float), True
    out = [cv2.remap(f, map1, map2, cv2.INTER_LINEAR) for f in frames]
    return out, np.asarray(K_new, float), True
