#!/usr/bin/env python3
"""Build a mission from a MARS-LVIG ROS bag, with its same-flight L1 LiDAR as truth.

MARS-LVIG (HKU, IJRR 2024; https://mars.hku.hk/dataset.html) flies a DJI M300
RTK carrying a 2448x2048 global-shutter camera triggered at 10 Hz and, on the
gimbal, a DJI Zenmuse L1 survey LiDAR recording *simultaneously*. The L1 cloud,
post-processed by DJI Terra, is stated at 10 cm horizontal / 5 cm vertical.
That is the first reference here captured in the same flight as the imagery:
no construction change, no seasonal change, no second aircraft.

What this writes:

- ``raw/video.mp4`` -- the camera frames, encoded at their true 10 Hz. The bag
  stores one JPEG per frame with no inter-frame compression; the pipeline takes
  video, so the frames are encoded once, near-losslessly. Frame timing is
  checked first and the build refuses if frames were dropped, because a
  constant-rate encode would then misplace every later frame in time.
- ``raw/telemetry.csv`` -- ``/dji_osdk_ros/rtk_position`` on the video clock.
  Camera and RTK share the bag's clock, so ``t - first_frame`` is exact.
- ``calibration/camera.json`` -- the published chessboard calibration.
- ``datasets/truth/<mission>/reference_lidar.las`` -- only when ``--truth-las``
  is given. ``run_mission.py`` never reads ``datasets/truth``.

Only pair a bag with the L1 cloud of the *same* flight. The L1 file names carry
their capture time; the bag's start time is printed and recorded so a mismatch
is visible rather than silent.

Usage:
  python scripts/build_mars_lvig_mission.py --bag ~/Downloads/HKisland03.bag \\
      --calib HKisland --name mars_hkisland03 \\
      --truth-las ../datasets/public/mars_lvig/truth/HKisland03/lidars/terra_las/cloudec958e035b8a264c.las
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parents[2]

TELEMETRY_COLUMNS = [
    "timestamp", "timestamp_ns", "time_basis", "latitude", "longitude",
    "altitude", "latitude_deg", "longitude_deg", "altitude_m",
    "altitude_reference", "sigma_e_m", "sigma_n_m", "sigma_u_m",
    "fix_type", "gps_accuracy", "num_satellites", "imgid",
]

#: Camera calibrations as published in UAVScenes' ``calibration_results.py``
#: (github.com/sijieaaa/UAVScenes), which reproduces MARS-LVIG's chessboard
#: calibration per scene. K is row-major; distortion is k1, k2, p1, p2, k3.
CALIBRATIONS = {
    "HKisland": {"K": [1444.43, 0.0, 1177.8, 0.0, 1444.34, 1043.6],
                 "dist": [-0.053, 0.121, 0.00127, 0.00043, -0.06495]},
    "HK_GNSS": {"K": [1444.43, 0.0, 1179.50, 0.0, 1444.34, 1044.90],
                "dist": [-0.0560, 0.1180, 0.00122, 0.00064, -0.0627]},
    "HKairport": {"K": [1451.28, 0.0, 1177.5, 0.0, 1451.29, 1043.5],
                  "dist": [-0.0572, 0.1209, 0.00124, -0.00018, -0.06327]},
    "AMtown": {"K": [1453.72, 0.0, 1172.18, 0.0, 1453.28, 1041.78],
               "dist": [-0.121, 0.1113, 0.0016, 0.00013, -0.062353]},
    "AMvalley": {"K": [1453.88, 0.0, 1182.53, 0.0, 1452.85, 1045.82],
                 "dist": [-0.052, 0.1168, 0.0015, 0.00013, -0.068564]},
}

CAMERA_TOPIC = "/left_camera/image/compressed"
RTK_TOPIC = "/dji_osdk_ros/rtk_position"
RTK_INFO_TOPIC = "/dji_osdk_ros/rtk_info_position"
#: DJI OSDK position-solution codes. 50 is NARROW_INT, a fixed RTK solution.
RTK_FIXED_CODES = {50}
#: DJI M300 RTK stated accuracy: 1 cm + 1 ppm horizontal, 1.5 cm + 1 ppm
#: vertical. MARS-LVIG states the base was under 5 km away, so the bound at
#: 5 km is used. A manufacturer bound, not a per-sample covariance: the bag's
#: NavSatFix covariance is all zeros, which means "not reported", not "exact".
RTK_SIGMA_H_M = 0.01 + 5000e-6
RTK_SIGMA_V_M = 0.015 + 5000e-6


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def stamp(msg) -> float:
    return msg.header.stamp.sec + msg.header.stamp.nanosec * 1e-9


def main() -> int:
    from rosbags.rosbag1 import Reader
    from rosbags.typesys import Stores, get_typestore

    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--bag", required=True)
    ap.add_argument("--calib", required=True, choices=sorted(CALIBRATIONS))
    ap.add_argument("--name", required=True)
    ap.add_argument("--set", default="mars_lvig")
    ap.add_argument("--truth-las", default=None,
                    help="the same flight's L1 cloud (terra_las/*.las)")
    ap.add_argument("--crf", type=int, default=20,
                    help="x264 quality; lower is larger. 20 keeps the file near the source JPEG size")
    ap.add_argument("--utc-start", default=None,
                    help="keep frames from this UTC time (ISO 8601), e.g. the "
                         "reference LiDAR's first gps_time; takeoff and climb "
                         "then do not spend the frame budget")
    ap.add_argument("--utc-end", default=None, help="keep frames up to this UTC time")
    ap.add_argument("--overwrite", action="store_true")
    a = ap.parse_args()

    bag = Path(a.bag).expanduser().resolve()
    mission = REPO / "datasets" / "public" / a.set / a.name
    if mission.exists():
        if not a.overwrite:
            raise SystemExit(f"{mission} exists; pass --overwrite")
        shutil.rmtree(mission)
    (mission / "raw").mkdir(parents=True)
    (mission / "calibration").mkdir()

    ts = get_typestore(Stores.ROS1_NOETIC)

    def _utc(v):
        if v is None:
            return None
        d = datetime.fromisoformat(v)
        return (d if d.tzinfo else d.replace(tzinfo=timezone.utc)).timestamp()
    win_lo, win_hi = _utc(a.utc_start), _utc(a.utc_end)

    def in_window(t):
        return (win_lo is None or t >= win_lo) and (win_hi is None or t <= win_hi)

    # Pass 1: timing and telemetry only, so a bad bag fails before the encode.
    frame_t: list[float] = []
    rtk: list[tuple[float, float, float, float]] = []
    info: list[tuple[float, int]] = []
    with Reader(bag) as r:
        bag_start = r.start_time / 1e9
        conns = [c for c in r.connections
                 if c.topic in (CAMERA_TOPIC, RTK_TOPIC, RTK_INFO_TOPIC)]
        for c, t, raw in r.messages(connections=conns):
            if c.topic == CAMERA_TOPIC:
                # Only the header is needed; skip decoding the JPEG payload.
                st = stamp(ts.deserialize_ros1(raw, c.msgtype))
                if in_window(st):
                    frame_t.append(st)
            elif c.topic == RTK_TOPIC:
                m = ts.deserialize_ros1(raw, c.msgtype)
                rtk.append((stamp(m), m.latitude, m.longitude, m.altitude))
            else:
                info.append((t / 1e9, int(ts.deserialize_ros1(raw, c.msgtype).data)))

    ft = np.asarray(frame_t)
    if len(ft) < 2:
        raise SystemExit(f"{bag}: no camera frames on {CAMERA_TOPIC}")
    dt = np.diff(ft)
    period = float(np.median(dt))
    fps = 1.0 / period
    if (dt > 1.5 * period).any() or (dt <= 0).any():
        raise SystemExit(
            f"{bag}: {(dt > 1.5 * period).sum()} dropped-frame gaps and "
            f"{(dt <= 0).sum()} non-increasing stamps; a constant-rate encode "
            "would misplace frames in time")
    t0 = float(ft[0])
    duration = float(ft[-1] - t0 + period)

    # RTK status arrives on its own topic; take the latest code at each fix.
    it = np.asarray([x[0] for x in info]) if info else np.zeros(0)
    ic = np.asarray([x[1] for x in info]) if info else np.zeros(0, int)
    rows = []
    for (st, lat, lon, alt) in rtk:
        tv = st - t0
        if tv < 0 or tv > duration:
            continue
        k = np.searchsorted(it, st, side="right") - 1
        code = int(ic[k]) if k >= 0 else None
        rows.append((tv, lat, lon, alt, code))
    if not rows:
        raise SystemExit(f"{bag}: no RTK samples inside the video span")
    fixed = sum(1 for r_ in rows if r_[4] in RTK_FIXED_CODES)

    with open(mission / "raw" / "telemetry.csv", "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=TELEMETRY_COLUMNS)
        w.writeheader()
        for tv, lat, lon, alt, code in rows:
            ok = code in RTK_FIXED_CODES
            w.writerow({
                "timestamp": f"{tv:.6f}",
                "timestamp_ns": int(round(tv * 1e9)),
                "time_basis": "video_pts_s",
                "latitude": f"{lat:.9f}", "longitude": f"{lon:.9f}",
                "altitude": f"{alt:.3f}",
                "latitude_deg": f"{lat:.9f}", "longitude_deg": f"{lon:.9f}",
                "altitude_m": f"{alt:.3f}",
                # DJI OSDK documents the RTK altitude only as metres. It is
                # WGS84 ellipsoidal by measurement (DEC-047): the same-flight
                # L1 LiDAR, which these altitudes match within 0.06 m, puts the
                # sea at -1.0 m while the tide was at mean sea level -- the
                # ellipsoidal height of the sea here, not 0.
                "altitude_reference": "ELLIPSOIDAL",
                "sigma_e_m": f"{RTK_SIGMA_H_M:.3f}" if ok else "",
                "sigma_n_m": f"{RTK_SIGMA_H_M:.3f}" if ok else "",
                "sigma_u_m": f"{RTK_SIGMA_V_M:.3f}" if ok else "",
                "fix_type": "RTK_FIXED" if ok else (f"DJI_{code}" if code is not None else ""),
                "gps_accuracy": "", "num_satellites": "", "imgid": "",
            })

    # Pass 2: stream the JPEGs straight into the encoder; nothing is written
    # to disk per frame. ffmpeg's image2pipe demuxer takes a JPEG stream.
    video = mission / "raw" / "video.mp4"
    enc = subprocess.Popen(
        ["ffmpeg", "-v", "error", "-y", "-f", "image2pipe", "-c:v", "mjpeg",
         "-framerate", f"{fps:.6f}", "-i", "-",
         "-c:v", "libx264", "-preset", "medium", "-crf", str(a.crf),
         "-pix_fmt", "yuv420p", "-movflags", "+faststart", str(video)],
        stdin=subprocess.PIPE)
    n = 0
    with Reader(bag) as r:
        conns = [c for c in r.connections if c.topic == CAMERA_TOPIC]
        for c, _, raw in r.messages(connections=conns):
            m = ts.deserialize_ros1(raw, c.msgtype)
            if in_window(stamp(m)):
                enc.stdin.write(bytes(m.data))
                n += 1
    enc.stdin.close()
    if enc.wait() != 0:
        raise SystemExit("ffmpeg failed")

    cal = CALIBRATIONS[a.calib]
    K, d = cal["K"], cal["dist"]
    (mission / "calibration" / "camera.json").write_text(json.dumps({
        "model": "OPENCV",
        "source": (f"MARS-LVIG chessboard calibration, scene '{a.calib}', as "
                   "published in UAVScenes calibration_results.py"),
        "image_width": 2448, "image_height": 2048,
        "fx": K[0], "fy": K[4], "cx": K[2], "cy": K[5],
        "k1": d[0], "k2": d[1], "p1": d[2], "p2": d[3], "k3": d[4],
        "distortion_applied_to_images": False,
        # Hikvision CA-050-11UC4: global shutter (MARS-LVIG, IJRR 2024, s.3).
        "shutter": "global",
        # Calibrated, not measured: the mean constant vertical offset of four
        # HKisland02/03 runs against the L1 (+0.19..+0.36 m, DEC-044). Accuracy
        # claims on those flights use the other flight's value; other MARS-LVIG
        # flights are held out from it.
        "gnss_antenna_above_camera_m": 0.29,
        "notes": [
            "Chessboard calibration by the dataset authors, independent of the "
            "L1 reference and of any reconstruction.",
            "The publisher states no calibration uncertainty.",
        ],
    }, indent=2))

    truth = None
    if a.truth_las:
        src = Path(a.truth_las).expanduser().resolve()
        tdir = REPO / "datasets" / "truth" / a.name
        tdir.mkdir(parents=True, exist_ok=True)
        dst = tdir / "reference_lidar.las"
        shutil.copy2(src, dst)
        truth = {"path": str(dst.relative_to(REPO)), "source": str(src),
                 "sha256": sha256(dst)}
        (tdir / "provenance.json").write_text(json.dumps({
            "reference": "DJI Zenmuse L1 LiDAR, same flight as the imagery",
            "processing": "DJI Terra 3.6.7 (as released by MARS-LVIG)",
            "stated_accuracy_m": {"horizontal": 0.10, "vertical": 0.05},
            "stated_accuracy_source": "MARS-LVIG, IJRR 2024, section 3",
            "source_file": str(src),
            "sha256": truth["sha256"],
            "bag_start_utc": datetime.fromtimestamp(bag_start, timezone.utc).isoformat(),
        }, indent=2))

    lat = np.asarray([r_[1] for r_ in rows])
    lon = np.asarray([r_[2] for r_ in rows])
    alt = np.asarray([r_[3] for r_ in rows])
    span_n = float(np.ptp(lat) * 111320)
    span_e = float(np.ptp(lon) * 111320 * np.cos(np.radians(lat.mean())))
    manifest = {
        "mission_id": a.name,
        "schema_version": 1,
        "built_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "built_by": "drishti3d/scripts/build_mars_lvig_mission.py",
        "dataset": "MARS-LVIG (HKU), CC BY-NC-SA 4.0",
        "source_bag": str(bag),
        "bag_start_utc": datetime.fromtimestamp(bag_start, timezone.utc).isoformat(),
        "window_utc": [a.utc_start, a.utc_end],
        "first_frame_utc": datetime.fromtimestamp(t0, timezone.utc).isoformat(),
        "video_sha256": sha256(video),
        "video": {"width": 2448, "height": 2048, "fps": fps,
                  "n_frames": n, "duration_s": duration},
        "video_note": (f"per-frame JPEGs from {CAMERA_TOPIC} encoded once with "
                       f"x264 crf {a.crf}; frame period {period:.4f} s, no drops"),
        "telemetry": {
            "source": f"{RTK_TOPIC} (+ {RTK_INFO_TOPIC})",
            "n_samples": len(rows),
            "present": True,
            "rtk_fixed_fraction": round(fixed / len(rows), 4),
            "altitude_reference": "ELLIPSOIDAL",
            "altitude_note": "established by measurement, not documented by DJI (DEC-047)",
            "sigma_note": ("sigmas are the DJI M300 RTK specification at a 5 km "
                           "baseline, not per-sample covariances"),
        },
        "truth": truth,
        "capture": {
            "duration_s": round(duration, 2), "n_frames": n,
            "footprint_m": [round(span_e, 1), round(span_n, 1)],
            "altitude_min_m": round(float(alt.min()), 1),
            "altitude_max_m": round(float(alt.max()), 1),
            "altitude_range_m": round(float(np.ptp(alt)), 1),
        },
    }
    (mission / "manifest.json").write_text(json.dumps(manifest, indent=2))

    print(f"mission {a.name}  (bag start {manifest['bag_start_utc']})")
    print(f"  video      2448x2048 @ {fps:.3f} fps, {duration:.1f} s, {n:,} frames, "
          f"{video.stat().st_size/1e6:.0f} MB")
    print(f"  telemetry  {len(rows):,} RTK samples, {fixed/len(rows):.0%} fixed")
    print(f"  footprint  {span_e:.0f} x {span_n:.0f} m, altitude {alt.min():.1f}"
          f"..{alt.max():.1f} m")
    print(f"  truth      {truth['path'] if truth else 'none'}")
    print(f"  -> {mission}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
