"""Synthetic single-pass drone dataset generator.

Renders a *known* 3D scene (textured ground plane + a rectangular building)
from a moving oblique drone camera, producing:

  * an MP4 video (via imageio/ffmpeg),
  * a telemetry CSV (timestamp, lat, lon, alt, roll, pitch, yaw, ...),
  * a ground-truth JSON (camera trajectory, scene points, reference distances).

Because the geometry is known exactly, this fixture lets the pipeline compute
*real* accuracy (not fabricated) and guarantees the demo has strong parallax
and texture for feature-based SfM.  No external assets or network required.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import json
import numpy as np
import cv2

from .geo import ENUFrame


def _procedural_texture(seed: int, size: int = 512) -> np.ndarray:
    """High-frequency colour texture so feature detectors find many corners."""
    rng = np.random.default_rng(seed)
    small = rng.integers(0, 255, (size // 8, size // 8, 3), dtype=np.uint8)
    tex = cv2.resize(small, (size, size), interpolation=cv2.INTER_NEAREST)
    # overlay a grid to add strong repeatable corners
    grid = (size // 8)
    tex[::grid, :, :] = 20
    tex[:, ::grid, :] = 20
    noise = rng.integers(-20, 20, tex.shape, dtype=np.int16)
    return np.clip(tex.astype(np.int16) + noise, 0, 255).astype(np.uint8)


@dataclass
class Surface:
    """A textured 3D quad. corners: (4,3) world ENU metres, CCW."""
    corners: np.ndarray
    texture: np.ndarray


def _look_at(cam_c: np.ndarray, target: np.ndarray) -> np.ndarray:
    """World->camera rotation for a camera at cam_c looking at target.

    Camera convention: +Z forward, +X right, +Y down (OpenCV).
    """
    fwd = target - cam_c
    fwd = fwd / np.linalg.norm(fwd)
    world_up = np.array([0.0, 0.0, 1.0])
    right = np.cross(fwd, world_up)
    right /= np.linalg.norm(right)
    down = np.cross(fwd, right)
    # rows map world vectors into camera axes
    return np.stack([right, down, fwd], axis=0)


def _build_scene() -> tuple[list[Surface], dict]:
    """Ground plane + a box building. Returns surfaces and metadata."""
    surfaces: list[Surface] = []
    # Ground: 60m x 60m centred at origin, z=0
    g = 30.0
    ground = np.array([[-g, -g, 0], [g, -g, 0], [g, g, 0], [-g, g, 0]], float)
    surfaces.append(Surface(ground, _procedural_texture(1, 1024)))

    # Building box: footprint 12 (E) x 8 (N), height 9, centred near origin
    cx, cy = 2.0, -1.0
    ex, ny, h = 6.0, 4.0, 9.0
    x0, x1 = cx - ex, cx + ex
    y0, y1 = cy - ny, cy + ny
    roof = np.array([[x0, y0, h], [x1, y0, h], [x1, y1, h], [x0, y1, h]], float)
    surfaces.append(Surface(roof, _procedural_texture(2)))
    walls = [
        np.array([[x0, y0, 0], [x1, y0, 0], [x1, y0, h], [x0, y0, h]], float),  # south
        np.array([[x1, y0, 0], [x1, y1, 0], [x1, y1, h], [x1, y0, h]], float),  # east
        np.array([[x1, y1, 0], [x0, y1, 0], [x0, y1, h], [x1, y1, h]], float),  # north
        np.array([[x0, y1, 0], [x0, y0, 0], [x0, y0, h], [x0, y1, h]], float),  # west
    ]
    for i, w in enumerate(walls):
        surfaces.append(Surface(w, _procedural_texture(10 + i)))

    meta = {
        "building": {"cx": cx, "cy": cy, "ex": ex, "ny": ny, "height": h},
        # Known reference distances for dimensional-accuracy evaluation.
        "reference_distances": [
            {"name": "building_width_E", "meters": 2 * ex,
             "a": [x0, y0, 0.0], "b": [x1, y0, 0.0]},
            {"name": "building_depth_N", "meters": 2 * ny,
             "a": [x0, y0, 0.0], "b": [x0, y1, 0.0]},
            {"name": "building_height", "meters": h,
             "a": [x0, y0, 0.0], "b": [x0, y0, h]},
        ],
    }
    return surfaces, meta


def _project(K, R, C, pts):
    """Project world pts (N,3) with extrinsic (R world->cam, camera centre C)."""
    cam = (R @ (pts - C).T).T           # (N,3)
    z = cam[:, 2]
    uv = (K @ cam.T).T
    uv = uv[:, :2] / uv[:, 2:3]
    return uv, z


def _render_frame(K, R, C, surfaces, w, h):
    img = np.zeros((h, w, 3), np.uint8)
    # painter's algorithm: sort by mean depth, far first
    order = []
    for s in surfaces:
        cam = (R @ (s.corners - C).T).T
        order.append(cam[:, 2].mean())
    for idx in np.argsort(order)[::-1]:
        s = surfaces[idx]
        uv, z = _project(K, R, C, s.corners)
        if np.any(z <= 0.1):
            continue
        th, tw = s.texture.shape[:2]
        src = np.array([[0, 0], [tw, 0], [tw, th], [0, th]], np.float32)
        dst = uv.astype(np.float32)
        H = cv2.getPerspectiveTransform(src, dst)
        warped = cv2.warpPerspective(s.texture, H, (w, h))
        mask = cv2.warpPerspective(np.full((th, tw), 255, np.uint8), H, (w, h))
        img[mask > 0] = warped[mask > 0]
    return img


def generate(out_dir: str | Path, *, n_frames: int = 90, fps: int = 30,
             width: int = 960, height: int = 540,
             origin=(28.6139, 77.2090, 220.0), seed: int = 0) -> dict:
    """Generate the synthetic dataset into ``out_dir``.

    Returns a manifest dict with paths and the camera intrinsics used.
    """
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    rng = np.random.default_rng(seed)

    surfaces, meta = _build_scene()

    focal = 0.9 * max(width, height)
    K = np.array([[focal, 0, width / 2.0],
                  [0, focal, height / 2.0],
                  [0, 0, 1.0]], float)

    # Single-pass oblique trajectory: fly east across the scene at ~45 m,
    # descending gently, camera looking down-forward at the building.
    t = np.linspace(0, 1, n_frames)
    east = -22 + 44 * t
    north = -14 + 6 * np.sin(t * np.pi)      # gentle lateral drift
    up = 46 - 6 * t
    centres = np.stack([east, north, up], 1)
    target = np.array([2.0, -1.0, 4.0])      # aim at the building

    frames = []
    cam_gt = []
    for i in range(n_frames):
        C = centres[i]
        R = _look_at(C, target)
        img = _render_frame(K, R, C, surfaces, width, height)
        frames.append(img)
        # store ground-truth pose
        cam_gt.append({"frame": i, "t": i / fps,
                       "C_enu": C.tolist(), "R_wc": R.tolist()})

    # Dense ground-truth surface points for completeness/accuracy scoring.
    gt_points = []
    for s in surfaces:
        p0, p1, p2, p3 = s.corners
        for a in np.linspace(0, 1, 25):
            for b in np.linspace(0, 1, 25):
                p = (p0 * (1 - a) * (1 - b) + p1 * a * (1 - b)
                     + p2 * a * b + p3 * (1 - a) * b)
                gt_points.append(p)
    gt_points = np.array(gt_points)

    # Write video
    video_path = out_dir / "synthetic_flight.mp4"
    import imageio.v2 as imageio
    writer = imageio.get_writer(video_path, fps=fps, codec="libx264",
                                quality=8, macro_block_size=None)
    for img in frames:
        writer.append_data(cv2.cvtColor(img, cv2.COLOR_BGR2RGB))
    writer.close()

    # Telemetry: convert ENU camera centres to WGS84 about the origin.
    frame = ENUFrame(*origin)
    geo = frame.enu_to_geodetic(centres)
    tel_path = out_dir / "synthetic_telemetry.csv"
    with open(tel_path, "w", newline="") as f:
        f.write("timestamp,latitude,longitude,altitude,roll,pitch,yaw,gps_accuracy\n")
        for i in range(n_frames):
            lat, lon, alt = geo[i]
            # small realistic GPS noise (~0.3 m) added to challenge alignment
            nlat = lat + rng.normal(0, 3e-6)
            nlon = lon + rng.normal(0, 3e-6)
            nalt = alt + rng.normal(0, 0.3)
            f.write(f"{i / fps:.4f},{nlat:.8f},{nlon:.8f},{nalt:.3f},"
                    f"0.0,-35.0,90.0,0.5\n")

    gt_path = out_dir / "ground_truth.json"
    with open(gt_path, "w") as f:
        json.dump({
            "origin_wgs84": {"lat": origin[0], "lon": origin[1], "alt": origin[2]},
            "intrinsics": {"fx": focal, "fy": focal, "cx": width / 2,
                           "cy": height / 2, "width": width, "height": height},
            "cameras_enu": cam_gt,
            "reference_distances": meta["reference_distances"],
            "scene_points_enu": gt_points.tolist(),
        }, f, indent=2)

    return {
        "video": str(video_path),
        "telemetry": str(tel_path),
        "ground_truth": str(gt_path),
        "n_frames": n_frames, "fps": fps,
        "intrinsics": {"fx": focal, "fy": focal,
                       "cx": width / 2, "cy": height / 2,
                       "width": width, "height": height},
    }


if __name__ == "__main__":
    import sys
    out = sys.argv[1] if len(sys.argv) > 1 else "sample_data/synthetic"
    m = generate(out)
    print(json.dumps(m, indent=2))
