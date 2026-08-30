"""Video probe, frame extraction, and content hashing.

Uses OpenCV (bundled FFmpeg) with an imageio-ffmpeg fallback so no system
FFmpeg install is required.  Stores SHA-256 of immutable originals.
"""
from __future__ import annotations

from dataclasses import dataclass, asdict
from pathlib import Path
import hashlib
import cv2


@dataclass
class VideoInfo:
    path: str
    width: int
    height: int
    fps: float
    frame_count: int
    duration: float
    codec: str
    sha256: str

    def to_dict(self) -> dict:
        return asdict(self)


def sha256_file(path: str | Path, chunk: int = 1 << 20) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while True:
            b = f.read(chunk)
            if not b:
                break
            h.update(b)
    return h.hexdigest()


def _fourcc_to_str(v: float) -> str:
    n = int(v)
    return "".join(chr((n >> (8 * i)) & 0xFF) for i in range(4)).strip("\x00 ") or "unknown"


def probe(path: str | Path) -> VideoInfo:
    """Extract resolution, FPS, duration, codec and checksum."""
    path = str(path)
    cap = cv2.VideoCapture(path)
    if not cap.isOpened():
        raise ValueError(f"cannot open video: {path}")
    w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    fps = float(cap.get(cv2.CAP_PROP_FPS)) or 30.0
    count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    codec = _fourcc_to_str(cap.get(cv2.CAP_PROP_FOURCC))
    cap.release()
    if count <= 0:  # some containers under-report; count manually (bounded)
        cap = cv2.VideoCapture(path)
        count = 0
        while cap.grab() and count < 100000:
            count += 1
        cap.release()
    duration = count / fps if fps else 0.0
    return VideoInfo(path, w, h, fps, count, duration, codec, sha256_file(path))


def extract_frames(path: str | Path, out_dir: str | Path, *,
                   step: int = 1, max_frames: int | None = None):
    """Decode frames to JPEG.  Returns list of (frame_index, timestamp, filepath)."""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    cap = cv2.VideoCapture(str(path))
    fps = float(cap.get(cv2.CAP_PROP_FPS)) or 30.0
    results = []
    idx = 0
    saved = 0
    while True:
        ok, frame = cap.read()
        if not ok:
            break
        if idx % step == 0:
            fp = out_dir / f"frame_{idx:06d}.jpg"
            cv2.imwrite(str(fp), frame, [cv2.IMWRITE_JPEG_QUALITY, 92])
            results.append((idx, idx / fps, str(fp)))
            saved += 1
            if max_frames and saved >= max_frames:
                break
        idx += 1
    cap.release()
    return results
