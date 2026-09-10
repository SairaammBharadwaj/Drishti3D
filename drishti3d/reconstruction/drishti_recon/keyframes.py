"""Adaptive keyframe selection.

Combines temporal spacing, optical-flow magnitude and GPS displacement so that
consecutive keyframes keep enough parallax/overlap for SfM while avoiding
redundant near-duplicate frames.  Presets: fast / balanced / quality.
"""
from __future__ import annotations

from dataclasses import dataclass
import numpy as np
import cv2


@dataclass
class KeyframePreset:
    name: str
    min_flow: float          # min mean optical-flow px to accept a new keyframe
    min_gap: int             # min frame gap
    max_gap: int             # force a keyframe after this many frames
    target_max: int          # cap total keyframes


PRESETS = {
    "fast": KeyframePreset("fast", 18.0, 3, 25, 40),
    "balanced": KeyframePreset("balanced", 10.0, 2, 18, 80),
    "quality": KeyframePreset("quality", 6.0, 1, 12, 160),
}


def _median_shift_fraction(frames, accepted, probe_n: int = 12):
    """Median consecutive-frame displacement, as a fraction of image width.

    Uses phase correlation rather than Farneback optical flow. Farneback is a
    *small-motion* estimator: measured on the real Bellus aerial set it reported
    2.1 px where the true displacement was ~57 px, because a shift of a third of
    the frame is far outside its operating range. The selector then concluded the
    frames were near-duplicates and thinned a capture that had no overlap to
    spare. Phase correlation handles large global translation directly, which is
    exactly the regime that matters for this decision.
    """
    probe = accepted[: min(len(accepted), probe_n)]
    if len(probe) < 2:
        return None
    shifts = []
    for a, b in zip(probe[:-1], probe[1:]):
        g0 = cv2.cvtColor(frames[a][2], cv2.COLOR_BGR2GRAY)
        g1 = cv2.cvtColor(frames[b][2], cv2.COLOR_BGR2GRAY)
        h, w = g0.shape[:2]
        sw = 256
        sh = max(int(h * sw / w), 8)
        a0 = cv2.resize(g0, (sw, sh)).astype(np.float32)
        a1 = cv2.resize(g1, (sw, sh)).astype(np.float32)
        try:
            (dx, dy), _resp = cv2.phaseCorrelate(a0, a1)
        except Exception:
            continue
        shifts.append(float(np.hypot(dx, dy)) / sw)
    return float(np.median(shifts)) if shifts else None


def select(frames, metrics, *, preset: str = "balanced",
           gps_enu=None, sparse_shift_frac: float = 0.15):
    """Select keyframes.

    frames: list of (frame_index, timestamp, bgr_image) -- typically the
            quality-accepted frames.
    metrics: aligned list[FrameMetrics] (same order) for accept flags.
    gps_enu: optional (N,3) ENU positions aligned to frames for displacement.
    sparse_shift_frac: if consecutive frames already move by more than this
            fraction of the image width, the capture is a photo survey rather
            than video and is returned untouched -- see
            :func:`_median_shift_fraction`.
    Returns list of selected indices into ``frames`` and a timeline list.
    """
    p = PRESETS.get(preset, PRESETS["balanced"])
    accepted = [i for i, m in enumerate(metrics) if m.accepted]
    if not accepted:
        accepted = list(range(len(frames)))

    # A capture that is *already* sparse must not be thinned further. Video
    # arrives with far more overlap than reconstruction needs, so dropping frames
    # is free; a photo survey does not -- each image was taken at the minimum
    # overlap the pilot planned for, and halving it destroys the reconstruction.
    #
    # Measured on the real Bellus aerial set: consecutive frames verified with
    # ~363 inliers and produced 5339 multi-view tracks, while every-second-frame
    # produced *zero* verified pairs. Thinning took that capture from workable to
    # unreconstructable.
    if len(accepted) >= 3:
        shift = _median_shift_fraction(frames, accepted)
        if shift is not None and shift >= sparse_shift_frac:
            timeline = [{"frame_index": frames[i][0], "timestamp": frames[i][1]}
                        for i in accepted]
            return accepted, timeline
    selected = [accepted[0]]
    prev_gray = cv2.cvtColor(frames[accepted[0]][2], cv2.COLOR_BGR2GRAY)
    prev_small = cv2.resize(prev_gray, (160, 90))
    last = accepted[0]

    for i in accepted[1:]:
        gap = i - last
        if gap < p.min_gap:
            continue
        gray = cv2.cvtColor(frames[i][2], cv2.COLOR_BGR2GRAY)
        small = cv2.resize(gray, (160, 90))
        flow = cv2.calcOpticalFlowFarneback(
            prev_small, small, None, 0.5, 2, 15, 2, 5, 1.1, 0)
        mag = float(np.mean(np.hypot(flow[..., 0], flow[..., 1])))
        gps_disp = 0.0
        if gps_enu is not None:
            gps_disp = float(np.linalg.norm(gps_enu[i] - gps_enu[last]))
        take = (mag >= p.min_flow) or (gap >= p.max_gap) or (gps_disp >= 1.0)
        if take:
            selected.append(i)
            prev_small = small
            last = i

    # floor: guarantee enough keyframes to attempt registration even on slow or
    # hovering flights (small optical flow / near-static GPS).  Undersampling
    # here starves SfM -- it was the cause of near-empty urban reconstructions.
    floor = min(len(accepted), 30)
    if len(selected) < floor:
        extra = np.linspace(0, len(accepted) - 1, floor).astype(int)
        selected = sorted(set(selected) | {accepted[int(k)] for k in extra})

    # cap total keyframes by uniform subsampling if needed
    if len(selected) > p.target_max:
        idx = np.linspace(0, len(selected) - 1, p.target_max).astype(int)
        selected = [selected[k] for k in idx]

    timeline = [{"frame_index": frames[i][0], "timestamp": frames[i][1]}
                for i in selected]
    return selected, timeline
