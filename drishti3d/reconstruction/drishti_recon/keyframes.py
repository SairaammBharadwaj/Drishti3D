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


def select(frames, metrics, *, preset: str = "balanced",
           gps_enu=None):
    """Select keyframes.

    frames: list of (frame_index, timestamp, bgr_image) -- typically the
            quality-accepted frames.
    metrics: aligned list[FrameMetrics] (same order) for accept flags.
    gps_enu: optional (N,3) ENU positions aligned to frames for displacement.
    Returns list of selected indices into ``frames`` and a timeline list.
    """
    p = PRESETS.get(preset, PRESETS["balanced"])
    accepted = [i for i, m in enumerate(metrics) if m.accepted]
    if not accepted:
        accepted = list(range(len(frames)))
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
