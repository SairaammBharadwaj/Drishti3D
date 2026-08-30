"""Per-frame quality analysis: blur, exposure, motion, duplicates.

All metrics are computed from real pixel data; thresholds are configurable.
Frames failing thresholds are marked rejected with an explicit reason.
"""
from __future__ import annotations

from dataclasses import dataclass, asdict
import numpy as np
import cv2


@dataclass
class QualityThresholds:
    min_blur: float = 40.0            # variance of Laplacian
    min_brightness: float = 25.0
    max_brightness: float = 235.0
    max_dark_frac: float = 0.55       # fraction of clipped-dark pixels
    max_bright_frac: float = 0.35     # fraction of clipped-bright pixels
    max_duplicate_sim: float = 0.995  # normalised cross-correlation


@dataclass
class FrameMetrics:
    frame_index: int
    timestamp: float
    blur: float
    brightness: float
    dark_frac: float
    bright_frac: float
    motion: float
    accepted: bool
    reasons: list

    def to_dict(self) -> dict:
        return asdict(self)


def _blur(gray) -> float:
    return float(cv2.Laplacian(gray, cv2.CV_64F).var())


def _exposure(gray):
    brightness = float(gray.mean())
    dark_frac = float((gray < 16).mean())
    bright_frac = float((gray > 240).mean())
    return brightness, dark_frac, bright_frac


def analyze(frames, thresholds: QualityThresholds | None = None):
    """frames: list of (frame_index, timestamp, bgr_image). Returns list[FrameMetrics]."""
    th = thresholds or QualityThresholds()
    out = []
    prev_small = None
    prev_gray_small = None
    for fi, ts, img in frames:
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        blur = _blur(gray)
        brightness, dark_frac, bright_frac = _exposure(gray)

        small = cv2.resize(gray, (64, 64)).astype(np.float32)
        small = (small - small.mean()) / (small.std() + 1e-6)
        motion = 0.0
        if prev_small is not None:
            motion = float(np.mean(np.abs(small - prev_small)))
        prev_small = small

        reasons = []
        if blur < th.min_blur:
            reasons.append("blurry")
        if brightness < th.min_brightness:
            reasons.append("underexposed")
        if brightness > th.max_brightness:
            reasons.append("overexposed")
        if dark_frac > th.max_dark_frac:
            reasons.append("clipped_dark")
        if bright_frac > th.max_bright_frac:
            reasons.append("clipped_bright")
        # near-duplicate: extremely low motion vs previous
        if prev_gray_small is not None and motion < (1 - th.max_duplicate_sim):
            reasons.append("duplicate")
        prev_gray_small = small

        out.append(FrameMetrics(fi, ts, blur, brightness, dark_frac,
                                bright_frac, motion, len(reasons) == 0, reasons))
    return out
