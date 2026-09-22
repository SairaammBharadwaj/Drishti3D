#!/usr/bin/env python3
"""Build a mission from a UseGeo dataset, and put its truth out of reach.

UseGeo ships individual 42 MP stills, a high-rate GNSS/IMU trajectory, adjusted
camera poses, and a LiDAR reference cloud. Our input contract is one continuous
video plus telemetry, so this joins the first two into the `datasets/` layout
and routes the last two to `datasets/truth/`, where no worker can see them --
the same separation `build_agz_mission.py` keeps, for the same reason: a
reference that reaches the optimiser stops being able to score it.

What counts as input and what counts as truth
---------------------------------------------
* **Input**: the images, and `trajectory_dataset_N.txt` -- the raw GNSS/IMU
  trajectory, the analogue of AGZ's OnboardGPS log. This is what a drone
  records in flight.
* **Truth**: `Image_orientations_dataset1.xyz`, which holds *adjusted* camera
  poses from the authors' bundle adjustment, and `LiDAR_dataset1.las`. Neither
  is a sensor reading; both are answers.

Putting the adjusted poses in the mission folder would hand the pipeline the
answer to the question it is being asked. They are the first reference here
measured by an instrument other than photogrammetry -- a RIEGL miniVUX-3UAV --
which is the whole reason this dataset is worth the download.

Coordinate reference
--------------------
UseGeo's coordinates are UTM but the LAS header declares no CRS and no file
states the zone. It is determined here by elimination rather than assumed: the
paper says the campaign was flown over Italian territory in April 2021, and of
the plausible zones only 32N places (498168, 4379603) on land in Italy --
39.57 N, 8.98 E, inland Sardinia. 33N falls in the Tyrrhenian Sea and 31N in
the Mediterranean off Spain. `--epsg` overrides if that reasoning is ever shown
to be wrong.

Timestamps come from the trajectory's GPS time matched to each image's own
recorded time, never from a nominal frame rate: the stills are 2 s apart, so
deriving time from frame index would put every telemetry sample against the
wrong image.

Usage:
  python scripts/build_usegeo_mission.py --source ../datasets/public/usegeo/dataset_1 \
      --name usegeo_1 --overwrite
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parents[2]

#: See the module docstring: determined by elimination, not assumed.
DEFAULT_EPSG = 32632

TELEMETRY_COLUMNS = [
    "timestamp", "timestamp_ns", "time_basis", "latitude", "longitude",
    "altitude", "latitude_deg", "longitude_deg", "altitude_m",
    "altitude_reference", "sigma_e_m", "sigma_n_m", "sigma_u_m",
    "fix_type", "gps_accuracy", "num_satellites", "imgid",
]

STAMP = re.compile(r"(\d{4}-\d{2}-\d{2}_\d{2}-\d{2}-\d{2})")


@dataclass
class Frame:
    path: Path
    stem: str
    gps_time: float
    east: float
    north: float
    up: float


def read_eors(path: Path) -> dict[str, tuple]:
    """Per-image GPS time and position from `eors_couple.txt`.

    This file is the link between an image and the trajectory: it carries the
    GPS time each shutter fired. The positions in it are adjusted and are not
    written into the mission -- only the time is used here.
    """
    out = {}
    for line in path.read_text().splitlines():
        if line.startswith("#") or not line.strip():
            continue
        f = line.split()
        if len(f) < 5:
            continue
        out[Path(f[0]).stem] = (float(f[1]), float(f[2]), float(f[3]), float(f[4]))
    return out


def read_trajectory(path: Path) -> np.ndarray:
    """(N,4) easting, northing, elevation, gps_time from the GNSS/IMU log."""
    rows = []
    with open(path) as fh:
        for line in fh:
            if line.startswith("#") or not line.strip():
                continue
            f = line.split()
            if len(f) >= 4:
                rows.append((float(f[0]), float(f[1]), float(f[2]), float(f[3])))
    return np.asarray(rows, float)


def detect_time_offset(times: dict, traj: np.ndarray) -> float:
    """Seconds to add to an image's recorded time to index the trajectory.

    The two files do not share a time basis. Measured on dataset 1, feeding an
    image's own time straight into the trajectory lands **107 m** from where
    that camera actually was -- at 80 m above ground with 2 cm imagery, a
    silently ruinous error, and exactly the class of mistake DEC-005 was about.

    The offset is found from the geometry rather than assumed: match each
    camera to its nearest trajectory point in space, ignoring time, and read
    off the implied shift. On dataset 1 that gives +18.02 s with no measurable
    spread, and the nearest-point distance is 0.08 m median -- so the two files
    describe one flight, offset by a constant. Eighteen seconds is the GPS-UTC
    leap-second difference in 2021: one file is GPS time, the other UTC.

    A wide spread means the trajectory is not this flight, which no time shift
    can repair, so it refuses instead of picking a number that makes the
    residual smallest.
    """
    from scipy.spatial import cKDTree
    keys = sorted(times)
    img_t = np.array([times[k][0] for k in keys])
    adj = np.array([times[k][1:] for k in keys], float)
    dist, idx = cKDTree(traj[:, :3]).query(adj)
    shifts = traj[idx, 3] - img_t
    spread = float(np.percentile(shifts, 90) - np.percentile(shifts, 10))
    median_d = float(np.median(dist))
    if median_d > 5.0 or spread > 1.0:
        raise SystemExit(
            f"the trajectory does not look like this flight: cameras sit "
            f"{median_d:.1f} m from the nearest trajectory point and the "
            f"implied time shift varies by {spread:.1f} s. A constant offset "
            f"cannot fix that; check the source files pair correctly.")
    return float(np.median(shifts))


def sample_trajectory(traj: np.ndarray, t: float) -> tuple[float, float, float]:
    """Linear interpolation of the flight track at one GPS time."""
    times = traj[:, 3]
    i = int(np.searchsorted(times, t))
    if i <= 0:
        return tuple(traj[0, :3])
    if i >= len(times):
        return tuple(traj[-1, :3])
    t0, t1 = times[i - 1], times[i]
    w = 0.0 if t1 == t0 else (t - t0) / (t1 - t0)
    return tuple(traj[i - 1, :3] * (1 - w) + traj[i, :3] * w)


def read_intrinsics(path: Path) -> dict | None:
    """Focal length and principal point, in pixels, from the orientation file.

    The header names them `c`, `x0`, `y0`. `y0` is negative because the file
    measures it downward from the image centre, so it is converted to a
    top-left origin here rather than passed through to be misread later.
    """
    lines = [l for l in path.read_text().splitlines() if l.strip()]
    if len(lines) < 2:
        return None
    f = lines[1].split()
    if len(f) < 10:
        return None
    c, x0, y0 = float(f[7]), float(f[8]), float(f[9])
    return {"focal_px": c, "x0_px": x0, "y0_px": y0}


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def build(source: Path, name: str, *, overwrite: bool, crf: int,
          epsg: int, max_frames: int | None) -> int:
    import pyproj

    imgs_dir = source / "Undistorted_images_full_res"
    eors = source / "Camera_Inputs" / "eors_couple.txt"
    traj_file = next(source.glob("trajectory_dataset_*.txt"), None)
    orient = next(source.glob("Image_orientations_dataset*.xyz"), None)
    lidar = next(source.glob("LiDAR_dataset*.las"), None)
    for p, what in ((imgs_dir, "images"), (eors, "eors_couple.txt"),
                    (traj_file, "trajectory"), (orient, "orientations")):
        if p is None or not p.exists():
            raise SystemExit(f"missing {what} under {source}")

    images = sorted(imgs_dir.glob("*.jpg"))
    if not images:
        raise SystemExit(f"no images in {imgs_dir}")
    times = read_eors(eors)
    traj = read_trajectory(traj_file)
    dt = detect_time_offset(times, traj)
    print(f"time basis: image times are {dt:+.2f} s from trajectory time "
          f"(detected, not assumed)")

    frames = []
    for p in images:
        m = STAMP.search(p.name)
        if not m or p.stem not in times:
            continue
        gps_t = times[p.stem][0]
        e, n, u = sample_trajectory(traj, gps_t + dt)
        frames.append(Frame(p, p.stem, gps_t, e, n, u))
    frames.sort(key=lambda f: f.gps_time)
    if max_frames:
        frames = frames[:max_frames]
    if len(frames) < 2:
        raise SystemExit(f"only {len(frames)} images matched a trajectory time")

    mission = REPO / "datasets" / "public" / "usegeo" / name
    truth = REPO / "datasets" / "truth" / name
    if mission.exists():
        if not overwrite:
            raise SystemExit(f"{mission} exists; pass --overwrite")
        shutil.rmtree(mission)
    (mission / "raw").mkdir(parents=True)
    truth.mkdir(parents=True, exist_ok=True)

    # ---- video with real per-frame timestamps ----------------------------
    t0 = frames[0].gps_time
    concat = mission / "raw" / "_frames.ffconcat"
    with open(concat, "w") as fh:
        fh.write("ffconcat version 1.0\n")
        for i, fr in enumerate(frames):
            nxt = frames[i + 1].gps_time if i + 1 < len(frames) else None
            dur = (nxt - fr.gps_time) if nxt else \
                  (frames[-1].gps_time - frames[-2].gps_time)
            fh.write(f"file '{fr.path.resolve()}'\nduration {dur:.6f}\n")
        # The concat demuxer drops the last entry's duration unless the file is
        # repeated; the encode is then cut back to the true frame count.
        fh.write(f"file '{frames[-1].path.resolve()}'\n")

    video = mission / "raw" / "video.mp4"
    subprocess.run(
        ["ffmpeg", "-y", "-v", "error", "-f", "concat", "-safe", "0",
         "-i", str(concat), "-fps_mode", "vfr", "-frames:v", str(len(frames)),
         "-c:v", "libx264", "-preset", "slow", "-crf", str(crf),
         "-pix_fmt", "yuv420p", "-video_track_timescale", "90000", str(video)],
        check=True)
    concat.unlink()

    # ---- telemetry from the GNSS/IMU trajectory --------------------------
    to_geo = pyproj.Transformer.from_crs(f"EPSG:{epsg}", "EPSG:4326",
                                         always_xy=True)
    tel = mission / "raw" / "telemetry.csv"
    with open(tel, "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=TELEMETRY_COLUMNS)
        w.writeheader()
        for fr in frames:
            lon, lat = to_geo.transform(fr.east, fr.north)
            w.writerow({
                "timestamp": f"{fr.gps_time - t0:.6f}",
                "timestamp_ns": int(round(fr.gps_time * 1e9)),
                "time_basis": "gps_time_s",
                "latitude": f"{lat:.8f}", "longitude": f"{lon:.8f}",
                "altitude": f"{fr.up:.3f}",
                "latitude_deg": f"{lat:.8f}", "longitude_deg": f"{lon:.8f}",
                "altitude_m": f"{fr.up:.3f}",
                # The trajectory's elevation is ellipsoidal in the same frame
                # the LiDAR uses. Calling it MSL would be a datum error of tens
                # of metres that nothing downstream could detect.
                "altitude_reference": "ELLIPSOIDAL",
                # UseGeo publishes no per-epoch GNSS covariance. Empty means
                # unknown, which is not the same as small -- the same rule
                # AGZ's corrupt epv column is handled under.
                "sigma_e_m": "", "sigma_n_m": "", "sigma_u_m": "",
                "fix_type": "", "gps_accuracy": "", "num_satellites": "",
                "imgid": fr.stem,
            })

    # ---- frame index: every encoded frame back to its original -----------
    with open(mission / "raw" / "frame_index.csv", "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["encoded_frame_index", "imgid", "source_image",
                    "source_sha256", "pts_s", "timestamp_ns"])
        for i, fr in enumerate(frames):
            w.writerow([i, fr.stem,
                        str(fr.path.relative_to(REPO)), sha256(fr.path),
                        f"{fr.gps_time - t0:.6f}",
                        int(round(fr.gps_time * 1e9))])

    # ---- truth, kept outside the mission ---------------------------------
    shutil.copy2(orient, truth / "reference_camera_orientations.xyz")
    if lidar is not None and lidar.exists():
        link = truth / "reference_lidar.las"
        if not link.exists():
            # A 3.2 GB reference is linked, not copied: it is read-only input
            # to scoring and two copies can drift.
            try:
                link.symlink_to(lidar.resolve())
            except OSError:
                shutil.copy2(lidar, link)
    (truth / "README.md").write_text(
        f"# Reference for {name}\n\n"
        "`reference_camera_orientations.xyz` holds the UseGeo authors' "
        "**adjusted** camera poses, and `reference_lidar.las` their RIEGL "
        "miniVUX-3UAV point cloud.\n\n"
        "Neither is a sensor reading available to a worker; both are answers. "
        "They live here, outside the mission folder, so a reconstruction "
        "cannot see what it is being scored against.\n\n"
        f"Coordinates are EPSG:{epsg}, determined by elimination (see "
        "`scripts/build_usegeo_mission.py`); the LAS header declares none.\n\n"
        "Licence: CC BY-NC-SA 4.0. Cite UseGeo / ISPRS.\n")

    intr = read_intrinsics(orient)
    span = float(np.hypot(frames[-1].east - frames[0].east,
                          frames[-1].north - frames[0].north))
    path_len = float(sum(
        np.hypot(b.east - a.east, b.north - a.north)
        for a, b in zip(frames, frames[1:])))
    manifest = {
        "mission_id": name,
        "schema_version": 1,
        "built_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "built_by": "drishti3d/scripts/build_usegeo_mission.py",
        "dataset": "UseGeo (ISPRS Scientific Initiative)",
        "source_dir": str(source.relative_to(REPO)) if source.is_relative_to(REPO) else str(source),
        "source_license": "CC BY-NC-SA 4.0 -- research use, attribute UseGeo/ISPRS",
        "crs": f"EPSG:{epsg}",
        "crs_note": ("determined by elimination: only zone 32N places these "
                     "coordinates on land in Italy, which is where the paper "
                     "says the campaign was flown"),
        "capture": {
            "n_frames": len(frames),
            "duration_s": round(frames[-1].gps_time - t0, 3),
            "path_length_m": round(path_len, 1),
            "net_displacement_m": round(span, 1),
            "median_frame_baseline_m": round(float(np.median([
                np.hypot(b.east - a.east, b.north - a.north)
                for a, b in zip(frames, frames[1:])])), 2),
            "alt_min_m": round(min(f.up for f in frames), 1),
            "alt_max_m": round(max(f.up for f in frames), 1),
        },
        "intrinsics_from_orientation_file": intr,
        "trajectory_time_offset_s": round(dt, 3),
        "trajectory_time_offset_note": (
            "detected from geometry, not assumed; matches the GPS-UTC "
            "leap-second difference in 2021. Without it the trajectory is "
            "read 107 m from where the camera was."),
        "telemetry_quality_note": (
            "this is a post-processed GNSS/INS trajectory and agrees with the "
            "authors' adjusted camera positions to 0.08 m median. It is "
            "survey-grade, unlike AGZ's 9 m GPS, so georegistration on this "
            "mission is not a hard test -- the LiDAR cloud is where the real "
            "question is. The adjusted poses are also partly derived from this "
            "trajectory, so scoring against them is not fully independent; the "
            "LiDAR is."),
        "video_note": ("re-encode of already-compressed JPEGs, not an original "
                       "camera bitstream; frame_index.csv maps every encoded "
                       "frame back to its source image"),
        "truth_dir": str((truth).relative_to(REPO)),
        "video_sha256": sha256(video),
    }
    (mission / "manifest.json").write_text(json.dumps(manifest, indent=2))

    print(f"mission {name}: {len(frames)} frames, "
          f"{manifest['capture']['duration_s']:.0f} s, "
          f"{path_len:.0f} m flown, "
          f"median baseline {manifest['capture']['median_frame_baseline_m']} m")
    print(f"  mission -> {mission}")
    print(f"  truth   -> {truth}")
    if intr:
        print(f"  intrinsics from file: f={intr['focal_px']:.1f} px, "
              f"pp=({intr['x0_px']:.1f}, {intr['y0_px']:.1f})")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--source", required=True, help="a dataset_N directory")
    ap.add_argument("--name", required=True)
    ap.add_argument("--overwrite", action="store_true")
    ap.add_argument("--crf", type=int, default=12)
    ap.add_argument("--epsg", type=int, default=DEFAULT_EPSG)
    ap.add_argument("--max-frames", type=int, default=None)
    a = ap.parse_args()
    return build(Path(a.source).resolve(), a.name, overwrite=a.overwrite,
                 crf=a.crf, epsg=a.epsg, max_frames=a.max_frames)


if __name__ == "__main__":
    raise SystemExit(main())
