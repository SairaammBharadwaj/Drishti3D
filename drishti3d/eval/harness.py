"""Turn an :class:`EvalCase` into pipeline inputs, run the verified pipeline,
and return the estimate in a form the scorer can consume.

Design notes
------------
* One video frame per source image, so the pipeline's ``frame_index`` maps
  straight back to the source-image / ground-truth index.
* We NEVER feed ground-truth poses to the pipeline.  When a dataset has no real
  GPS we synthesise a *noisy* GPS track from the GT centres (drone-grade sigma),
  so scale/position accuracy is measured under realistic conditions.  Trajectory
  error is then scored by a post-hoc Sim(3) alignment (see :mod:`.metrics`),
  which is the standard, gauge-free SLAM protocol.
"""
from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np

from drishti_recon import geo, pipeline

from .cases import EvalCase

# A fixed WGS84 anchor for synthesised GPS (Bengaluru); arbitrary but consistent.
_ANCHOR = (12.9716, 77.5946, 900.0)


@dataclass
class Estimate:
    project_dir: Path
    est_frames: np.ndarray       # (K,) source-frame indices that were solved
    est_centers_enu: np.ndarray  # (K,3) estimated camera centres (pipeline ENU)
    cloud_pts: np.ndarray        # (P,3) reconstructed points (ENU)
    report: dict
    warnings: list


def _write_video(images: list[Path], out: Path, fps: float,
                 max_width: int = 1920) -> tuple[int, int]:
    """Assemble one frame per image into a **playable H.264** mp4.

    Uses libx264 + yuv420p (universally playable in browsers / Windows player),
    unlike OpenCV's mp4v which many players reject. Downscales to max_width
    (even dims required by yuv420p); the pipeline re-downscales to its own
    processing width anyway. Returns (width, height) of the video written.
    """
    import imageio.v2 as imageio
    first = cv2.imread(str(images[0]))
    if first is None:
        raise RuntimeError(f"cannot read image {images[0]}")
    h0, w0 = first.shape[:2]
    scale = min(1.0, max_width / w0)
    w = int(round(w0 * scale)) & ~1          # force even
    h = int(round(h0 * scale)) & ~1
    writer = imageio.get_writer(
        str(out), fps=fps, codec="libx264", format="ffmpeg",
        pixelformat="yuv420p", macro_block_size=None,
        ffmpeg_params=["-crf", "20", "-preset", "medium"])
    try:
        for p in images:
            fr = cv2.imread(str(p))
            if fr is None:
                raise RuntimeError(f"cannot read image {p}")
            if fr.shape[:2] != (h, w):
                fr = cv2.resize(fr, (w, h))
            writer.append_data(cv2.cvtColor(fr, cv2.COLOR_BGR2RGB))
    finally:
        writer.close()
    return w, h


def _synthesise_gps(centers: np.ndarray, *, sigma_h: float, sigma_v: float,
                    seed: int) -> tuple[np.ndarray, float]:
    """Map GT centres to an ENU frame at a fixed anchor, add noise, ->geodetic.

    Returns (rows[N,4] lat,lon,alt,acc, horizontal_sigma).
    """
    rng = np.random.default_rng(seed)
    frame = geo.ENUFrame(*_ANCHOR)
    enu = centers.astype(float).copy()
    enu[:, 0] += rng.normal(0, sigma_h, len(enu))
    enu[:, 1] += rng.normal(0, sigma_h, len(enu))
    enu[:, 2] += rng.normal(0, sigma_v, len(enu))
    geo_wgs = frame.enu_to_geodetic(enu)          # (N,3) lat,lon,alt
    acc = np.full(len(enu), float(sigma_h))
    return np.column_stack([geo_wgs, acc]), sigma_h


def _write_telemetry(rows: np.ndarray, out: Path, fps: float,
                     frame_idx: np.ndarray | None = None) -> None:
    with open(out, "w", newline="") as f:
        f.write("timestamp,latitude,longitude,altitude,roll,pitch,yaw,gps_accuracy\n")
        for i, r in enumerate(rows):
            fi = i if frame_idx is None else int(frame_idx[i])
            f.write(f"{fi / fps:.4f},{r[0]:.8f},{r[1]:.8f},{r[2]:.3f},"
                    f"0.0,0.0,0.0,{r[3]:.2f}\n")


def run_case(case: EvalCase, work_dir: str | Path, *,
             fps: float = 5.0, gps_sigma_h: float = 2.5, gps_sigma_v: float = 4.0,
             seed: int = 0, gravity_align: bool | None = None,
             do_mesh: bool = False, max_frames: int = 400,
             params_override: dict | None = None,
             progress=None) -> Estimate:
    work_dir = Path(work_dir)
    proj = work_dir / "project"
    proj.mkdir(parents=True, exist_ok=True)

    # 1) VIDEO + TELEMETRY --------------------------------------------------
    if case.kind == "synthetic" and case.meta.get("video"):
        video = Path(case.meta["video"])
        telemetry = Path(case.meta["telemetry"])
        vw = cv2.VideoCapture(str(video)); vwidth = int(vw.get(3)); vw.release()
    else:
        if not case.images:
            raise ValueError(f"case {case.name} has no images to reconstruct")
        video = work_dir / "capture.mp4"
        vwidth, _ = _write_video(case.images, video, fps)
        telemetry = work_dir / "telemetry.csv"
        if case.has_real_gps:
            _write_telemetry(case.gps, telemetry, fps)
        elif case.gt_centers is not None:
            rows, _ = _synthesise_gps(case.gt_centers, sigma_h=gps_sigma_h,
                                      sigma_v=gps_sigma_v, seed=seed)
            _write_telemetry(rows, telemetry, fps)
        else:
            raise ValueError(f"case {case.name} has neither GPS nor GT poses "
                             "to anchor metric scale")

    # 2) INTRINSICS (scaled to video resolution) ---------------------------
    intr = None
    if case.intrinsics:
        k = case.intrinsics
        native_w = k.get("width", vwidth)
        s = vwidth / native_w
        intr = {"fx": k["fx"] * s, "fy": k["fy"] * s,
                "cx": k["cx"] * s, "cy": k["cy"] * s}

    # 3) RUN PIPELINE -------------------------------------------------------
    galign = gravity_align if gravity_align is not None else (case.kind == "odm")
    params = pipeline.PipelineParams(
        do_mesh=do_mesh, intrinsics=intr, gravity_align=galign,
        max_analyze_frames=max_frames)
    # Ablation hook: the benchmark switches one component at a time by name so a
    # variant is a recorded parameter set, not an edited source tree.
    for key, val in (params_override or {}).items():
        if not hasattr(params, key):
            raise ValueError(f"unknown pipeline parameter {key!r}")
        setattr(params, key, val)
    kw = {"params": params}
    if progress is not None:
        kw["progress"] = progress
    result = pipeline.run(proj, video, telemetry, **kw)

    # 4) LOAD ESTIMATE ------------------------------------------------------
    import json
    traj = json.loads((proj / "artifacts" / "trajectory.json").read_text())
    cams = traj.get("cameras_enu", [])
    est_frames = np.array([c["frame_index"] for c in cams], int)
    est_centers = np.array([c["C"] for c in cams], float).reshape(-1, 3)
    npz = np.load(proj / "artifacts" / "cloud.npz")
    return Estimate(project_dir=proj, est_frames=est_frames,
                    est_centers_enu=est_centers, cloud_pts=npz["points"],
                    report=result.report, warnings=list(result.warnings))
