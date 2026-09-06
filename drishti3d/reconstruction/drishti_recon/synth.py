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
    n = np.linalg.norm(right)
    if n < 1e-8:
        # Straight-down (nadir) view: the world-up reference is parallel to the
        # view direction, so it cannot define a heading.  Fall back to north,
        # which fixes the image roll without changing any oblique pose.
        right = np.cross(fwd, np.array([0.0, 1.0, 0.0]))
        n = np.linalg.norm(right)
    right = right / n
    down = np.cross(fwd, right)
    # rows map world vectors into camera axes
    return np.stack([right, down, fwd], axis=0)


def _build_scene(tex_offset: int = 0) -> tuple[list[Surface], dict]:
    """Ground plane + a box building. Returns surfaces and metadata.

    ``tex_offset`` shifts every texture seed so that different benchmark
    seeds render a genuinely different scene appearance (not merely different
    GPS noise on identical pixels), which is what makes repeated trials
    independent rather than cosmetic.
    """
    surfaces: list[Surface] = []
    # Ground: 60m x 60m centred at origin, z=0
    g = 30.0
    ground = np.array([[-g, -g, 0], [g, -g, 0], [g, g, 0], [-g, g, 0]], float)
    surfaces.append(Surface(ground, _procedural_texture(1 + tex_offset, 1024)))

    # Building box: footprint 12 (E) x 8 (N), height 9, centred near origin
    cx, cy = 2.0, -1.0
    ex, ny, h = 6.0, 4.0, 9.0
    x0, x1 = cx - ex, cx + ex
    y0, y1 = cy - ny, cy + ny
    roof = np.array([[x0, y0, h], [x1, y0, h], [x1, y1, h], [x0, y1, h]], float)
    surfaces.append(Surface(roof, _procedural_texture(2 + tex_offset)))
    walls = [
        np.array([[x0, y0, 0], [x1, y0, 0], [x1, y0, h], [x0, y0, h]], float),  # south
        np.array([[x1, y0, 0], [x1, y1, 0], [x1, y1, h], [x1, y0, h]], float),  # east
        np.array([[x1, y1, 0], [x0, y1, 0], [x0, y1, h], [x1, y1, h]], float),  # north
        np.array([[x0, y1, 0], [x0, y0, 0], [x0, y0, h], [x0, y1, h]], float),  # west
    ]
    for i, w in enumerate(walls):
        surfaces.append(Surface(w, _procedural_texture(10 + tex_offset + i)))

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


# --------------------------------------------------------------------------- #
# capture regimes
# --------------------------------------------------------------------------- #
#: Named capture regimes.  A regime fixes the *flight geometry*, which is the
#: dominant driver of reconstructability -- baseline-to-depth ratio, triangulation
#: angle and how well GPS constrains the vertical axis.  Benchmarking across
#: regimes (rather than one favourable pass) is what makes a reported accuracy
#: number meaningful; see docs/BENCHMARK.md.
REGIMES = ("oblique_pass", "nadir_grid", "orbit", "low_parallax")


def _trajectory(regime: str, n_frames: int):
    """Return (centres (N,3) ENU, targets (N,3) ENU aim points) for a regime.

    ``targets`` is per-frame so nadir passes can look straight down while
    oblique/orbit passes keep the building framed.
    """
    t = np.linspace(0, 1, n_frames)
    building = np.array([2.0, -1.0, 4.0])

    if regime == "oblique_pass":
        # Single oblique pass flying east, descending gently, building framed.
        centres = np.stack([-22 + 44 * t,
                            -14 + 6 * np.sin(t * np.pi),
                            46 - 6 * t], 1)
        targets = np.tile(building, (n_frames, 1))

    elif regime == "nadir_grid":
        # Lawn-mower nadir mapping grid at constant altitude, camera straight
        # down.  This is the hard case: constant altitude means GPS barely
        # constrains the vertical axis, and the view directions are nearly
        # parallel, so triangulation angles come only from the baseline.
        strips, alt = 3, 45.0
        u = t * strips                      # 0..strips along the boustrophedon
        leg = np.floor(np.clip(u, 0, strips - 1e-9)).astype(int)
        frac = u - leg
        span = 24.0
        east = np.where(leg % 2 == 0, -span + 2 * span * frac,
                        span - 2 * span * frac)
        north = -16.0 + leg * 16.0
        centres = np.stack([east, north, np.full(n_frames, alt)], 1)
        # look straight down: aim at the ground point directly below
        targets = np.stack([east, north, np.zeros(n_frames)], 1)

    elif regime == "orbit":
        # Circular orbit around the building looking inward -- the strongest
        # possible parallax for a single pass, and the regime a pilot would be
        # told to fly if the goal is measurable geometry.
        radius, alt = 26.0, 30.0
        ang = 2 * np.pi * t
        centres = np.stack([building[0] + radius * np.cos(ang),
                            building[1] + radius * np.sin(ang),
                            np.full(n_frames, alt)], 1)
        targets = np.tile(building, (n_frames, 1))

    elif regime == "low_parallax":
        # High, fast, nearly-straight pass: short baseline relative to depth, so
        # triangulation angles are small and depth is weakly observed.  This is
        # the failure-mode probe -- a system that only reports its best regime is
        # not reporting its field behaviour.
        centres = np.stack([-10 + 20 * t,
                            -18 + 1.5 * t,
                            np.full(n_frames, 78.0)], 1)
        targets = np.tile(building, (n_frames, 1))

    else:
        raise ValueError(f"unknown regime {regime!r}; expected one of {REGIMES}")

    return centres, targets


def generate(out_dir: str | Path, *, n_frames: int = 90, fps: int = 30,
             width: int = 960, height: int = 540,
             origin=(28.6139, 77.2090, 220.0), seed: int = 0,
             regime: str = "oblique_pass",
             gps_sigma_h: float = 0.33, gps_sigma_v: float = 0.30,
             gps_outlier_frac: float = 0.0,
             gps_outlier_sigma_h: float = 6.0,
             gps_outlier_sigma_v: float = 10.0) -> dict:
    """Generate the synthetic dataset into ``out_dir``.

    Parameters
    ----------
    regime
        Capture geometry, one of :data:`REGIMES`.  See :func:`_trajectory`.
    gps_sigma_h, gps_sigma_v
        Nominal GNSS noise (metres) applied in the local ENU frame.  Noise is
        added metrically rather than in degrees so the horizontal sigma means the
        same thing at every latitude.
    gps_outlier_frac
        Fraction of samples degraded to ``gps_outlier_sigma_*``.  Degraded
        samples honestly report their larger sigma in the ``gps_accuracy``
        column, which is what an uncertainty-weighted alignment is supposed to
        exploit.  Keep at 0.0 for a homoscedastic track.

    Returns a manifest dict with paths and the camera intrinsics used.
    """
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    rng = np.random.default_rng(seed)

    surfaces, meta = _build_scene(tex_offset=int(seed) * 1000)

    focal = 0.9 * max(width, height)
    K = np.array([[focal, 0, width / 2.0],
                  [0, focal, height / 2.0],
                  [0, 0, 1.0]], float)

    centres, targets = _trajectory(regime, n_frames)

    frames = []
    cam_gt = []
    for i in range(n_frames):
        C = centres[i]
        R = _look_at(C, targets[i])
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
    # Perturb in ENU metres, then convert -- so sigma_h is metres everywhere.
    sig_h = np.full(n_frames, float(gps_sigma_h))
    sig_v = np.full(n_frames, float(gps_sigma_v))
    if gps_outlier_frac > 0:
        n_bad = int(round(gps_outlier_frac * n_frames))
        if n_bad:
            bad = rng.choice(n_frames, n_bad, replace=False)
            sig_h[bad] = float(gps_outlier_sigma_h)
            sig_v[bad] = float(gps_outlier_sigma_v)
    noisy = centres.copy()
    noisy[:, 0] += rng.normal(0, 1, n_frames) * sig_h
    noisy[:, 1] += rng.normal(0, 1, n_frames) * sig_h
    noisy[:, 2] += rng.normal(0, 1, n_frames) * sig_v
    geo = frame.enu_to_geodetic(noisy)
    tel_path = out_dir / "synthetic_telemetry.csv"
    with open(tel_path, "w", newline="") as f:
        f.write("timestamp,latitude,longitude,altitude,roll,pitch,yaw,gps_accuracy\n")
        for i in range(n_frames):
            lat, lon, alt = geo[i]
            # Report the sigma actually used for this sample: a receiver that
            # knows its fix degraded says so, and the aligner should use it.
            f.write(f"{i / fps:.4f},{lat:.8f},{lon:.8f},{alt:.3f},"
                    f"0.0,-35.0,90.0,{sig_h[i]:.2f}\n")

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
        "n_frames": n_frames, "fps": fps, "regime": regime, "seed": int(seed),
        "gps_noise": {"sigma_h": float(gps_sigma_h), "sigma_v": float(gps_sigma_v),
                      "outlier_frac": float(gps_outlier_frac),
                      "outlier_sigma_h": float(gps_outlier_sigma_h),
                      "outlier_sigma_v": float(gps_outlier_sigma_v)},
        "intrinsics": {"fx": focal, "fy": focal,
                       "cx": width / 2, "cy": height / 2,
                       "width": width, "height": height},
    }


if __name__ == "__main__":
    import sys
    out = sys.argv[1] if len(sys.argv) > 1 else "sample_data/synthetic"
    m = generate(out)
    print(json.dumps(m, indent=2))
