#!/usr/bin/env python3
"""Build a plan-conformant mission from a Zurich Urban MAV (AGZ) frame subset.

Why this exists
---------------
The product's input contract is *one continuous video plus telemetry*, but AGZ
ships individual JPEG frames plus logs keyed by ``imgid``.  This script joins
the two into the ``datasets/`` layout of plan section 6.6, so the same pipeline
that will one day take a field capture can be exercised on real aerial imagery
with real GNSS today.

Three things it is careful about
--------------------------------
1. **Timestamps are taken from the log, not from a nominal frame rate.**  The
   frames in a segment are a stride subsample of a 30 Hz capture, so the real
   spacing is seconds, not 33 ms.  The video is written with explicit per-frame
   presentation timestamps from ``OnboardGPS.csv`` and the pipeline reads them
   back through ``CAP_PROP_POS_MSEC``.  Deriving time from frame index would
   put every telemetry sample against the wrong image.
2. **Uncertainty columns carry only what the log actually supports.**  AGZ's
   ``eph_m`` is a horizontal DOP in metres and is written to ``sigma_e_m`` and
   ``sigma_n_m``.  Its ``epv_m`` column is corrupt in the published release
   (values around 1e-43), so ``sigma_u_m`` is written empty -- unknown, which
   is not the same as small.
3. **Reference positions never enter the mission folder.**  The published Pix4D
   camera positions go to ``datasets/truth/<mission>/``, outside anything a
   worker is given, because a reference that reaches the optimiser stops being
   able to score it.

The written video is a re-encode of already-compressed JPEGs, not the original
camera bitstream; ``manifest.json`` records that, and ``frame_index.csv`` maps
every encoded frame back to its source JPEG so evidence can cite original
pixels rather than the re-encode.

Usage:
  python scripts/build_agz_mission.py --source data/real_drone/agz_dense \
      --name agz_dense_pass --overwrite
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from agz_logs import read_gps, read_truth   # noqa: E402

REPO = Path(__file__).resolve().parents[2]
APP = REPO / "drishti3d"
AGZ = APP / "data/real_drone/AGZ_subset"
LOGS = AGZ / "Log Files"

#: Plan section 6.6 normalised telemetry columns, plus the two the reconstruction
#: telemetry loader consumes directly.  Both spellings are written so the file is
#: both the archival record and directly ingestible.
TELEMETRY_COLUMNS = [
    "timestamp", "timestamp_ns", "time_basis",
    "latitude", "longitude", "altitude",
    "latitude_deg", "longitude_deg", "altitude_m", "altitude_reference",
    "sigma_e_m", "sigma_n_m", "sigma_u_m", "fix_type",
    "gps_accuracy", "num_satellites", "imgid",
]


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _camera_json(out: Path) -> dict:
    """Factory intrinsics and distortion from the publisher's calibration.

    AGZ frames are *distorted*: k1 = -0.281 is strong barrel.  A previous
    session in this repository measured 90 m median position error feeding raw
    frames to a dense model versus 7.6 m after undistortion, so the coefficients
    are propagated here rather than left for a later guess.
    """
    d = np.load(AGZ / "calibration_data.npz")
    K = d["intrinsic_matrix"]
    dist = d["distCoeff"].ravel()
    cam = {
        "model": "OPENCV",
        "source": "AGZ_subset/calibration_data.npz (publisher factory "
                  "calibration from 30 checkerboard images)",
        "image_width": 1920, "image_height": 1080,
        "fx": float(K[0, 0]), "fy": float(K[1, 1]),
        "cx": float(K[0, 2]), "cy": float(K[1, 2]),
        "k1": float(dist[0]), "k2": float(dist[1]),
        "p1": float(dist[2]), "p2": float(dist[3]), "k3": float(dist[4]),
        "distortion_applied_to_images": False,
        "notes": [
            "Intrinsics are for the full 1920x1080 frame; scale them if the "
            "pipeline processes at a reduced width.",
            "Strong barrel distortion (k1=-0.281). Images in raw/ are NOT "
            "undistorted; undistort once and carry the new intrinsics, never "
            "twice.",
            "The publisher does not state a calibration uncertainty.",
        ],
    }
    out.write_text(json.dumps(cam, indent=2))
    return cam


def build(source: Path, name: str, overwrite: bool, crf: int) -> dict:
    if not LOGS.exists():
        raise SystemExit(f"AGZ logs not found at {LOGS}")
    images = sorted((p for p in source.iterdir()
                     if p.suffix.lower() in {".jpg", ".jpeg"} and p.stem.isdigit()),
                    key=lambda p: int(p.stem))
    if len(images) < 2:
        raise SystemExit(f"{source} holds fewer than 2 numerically named JPEGs")

    gps = read_gps(LOGS)
    truth = read_truth(LOGS)
    missing = [p.stem for p in images if int(p.stem) not in gps]
    if missing:
        raise SystemExit(f"{len(missing)} frames have no telemetry row "
                         f"(first: {missing[0]}); refusing to invent timing")

    mission = REPO / "datasets/public/zurich_mav" / name
    truth_dir = REPO / "datasets/truth" / name
    if mission.exists():
        if not overwrite:
            raise SystemExit(f"{mission} exists; pass --overwrite to rebuild")
        shutil.rmtree(mission)
    shutil.rmtree(truth_dir, ignore_errors=True)
    for sub in ("raw", "calibration", "annotations"):
        (mission / sub).mkdir(parents=True, exist_ok=True)
    truth_dir.mkdir(parents=True, exist_ok=True)

    rows = [gps[int(p.stem)] for p in images]
    t0_us = rows[0].timestamp_us

    # ---- video: real presentation timestamps, from the log ---------------
    # ffconcat carries an explicit duration per frame, which is how a
    # non-uniformly sampled set becomes a video whose PTS mean something.
    concat = mission / "raw" / "_frames.ffconcat"
    with open(concat, "w") as fh:
        fh.write("ffconcat version 1.0\n")
        for i, (p, r) in enumerate(zip(images, rows)):
            nxt = rows[i + 1].timestamp_us if i + 1 < len(rows) else None
            dur = (nxt - r.timestamp_us) / 1e6 if nxt else \
                  (rows[-1].timestamp_us - rows[-2].timestamp_us) / 1e6
            fh.write(f"file '{p.resolve()}'\nduration {dur:.6f}\n")
        # The concat demuxer drops the final entry's `duration` unless the file
        # is repeated, so repeat it and then cut the encode back to exactly
        # len(images) frames -- otherwise the clip ends with a duplicate frame
        # carrying a timestamp no telemetry row belongs to.
        fh.write(f"file '{images[-1].resolve()}'\n")

    video = mission / "raw" / "video.mp4"
    cmd = ["ffmpeg", "-y", "-v", "error", "-f", "concat", "-safe", "0",
           "-i", str(concat), "-fps_mode", "vfr", "-frames:v", str(len(images)),
           "-c:v", "libx264",
           "-preset", "slow", "-crf", str(crf), "-pix_fmt", "yuv420p",
           "-video_track_timescale", "90000", str(video)]
    subprocess.run(cmd, check=True)
    concat.unlink()

    # ---- telemetry: normalised schema, honest sigmas ---------------------
    tel = mission / "raw" / "telemetry.csv"
    with open(tel, "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=TELEMETRY_COLUMNS)
        w.writeheader()
        for r in rows:
            t_s = (r.timestamp_us - t0_us) / 1e6
            w.writerow({
                "timestamp": f"{t_s:.6f}",
                "timestamp_ns": int(round(r.timestamp_us * 1000)),
                "time_basis": "autopilot_monotonic_us",
                "latitude": f"{r.lat:.7f}", "longitude": f"{r.lon:.7f}",
                "altitude": f"{r.alt_msl_m:.3f}",
                "latitude_deg": f"{r.lat:.7f}", "longitude_deg": f"{r.lon:.7f}",
                "altitude_m": f"{r.alt_msl_m:.3f}",
                "altitude_reference": "MSL",
                "sigma_e_m": f"{r.eph_m:.3f}", "sigma_n_m": f"{r.eph_m:.3f}",
                "sigma_u_m": "",              # epv_m is corrupt: unknown, not small
                "fix_type": r.fix_type,
                "gps_accuracy": f"{r.eph_m:.3f}",
                "num_satellites": r.num_sat, "imgid": r.imgid,
            })

    # ---- frame index: encoded frame -> original JPEG ---------------------
    index = mission / "raw" / "frame_index.csv"
    with open(index, "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["encoded_frame_index", "imgid", "source_image",
                    "source_sha256", "pts_s", "timestamp_ns"])
        for i, (p, r) in enumerate(zip(images, rows)):
            w.writerow([i, r.imgid, str(p.relative_to(REPO)), _sha256(p),
                        f"{(r.timestamp_us - t0_us) / 1e6:.6f}",
                        int(round(r.timestamp_us * 1000))])

    cam = _camera_json(mission / "calibration" / "camera.json")

    # ---- reference positions: truth folder only --------------------------
    n_ref = 0
    with open(truth_dir / "reference_camera_positions.csv", "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["imgid", "x_utm32n_m", "y_utm32n_m", "z_m",
                    "omega_deg", "phi_deg", "kappa_deg",
                    "x_gps_utm32n_m", "y_gps_utm32n_m", "z_gps_m"])
        for r in rows:
            t = truth.get(r.imgid)
            if t is None:
                continue
            n_ref += 1
            w.writerow([t.imgid, t.x_gt, t.y_gt, t.z_gt, t.omega_deg,
                        t.phi_deg, t.kappa_deg, t.x_gps, t.y_gps, t.z_gps])
    (truth_dir / "README.md").write_text(
        f"# Reference data for mission `{name}`\n\n"
        "`reference_camera_positions.csv` holds the camera positions the AGZ\n"
        "authors published in `GroundTruthAGL.csv`, restricted to this\n"
        "mission's frames. CRS: WGS 84 / UTM zone 32N (EPSG:32632), heights in\n"
        "metres as published.\n\n"
        "**These are not independent survey truth.** The publisher produced\n"
        "them with Pix4D over the full image set, using loop closures this\n"
        "single pass does not have. Scoring against them measures agreement\n"
        "with another photogrammetric reconstruction whose own uncertainty is\n"
        "not stated. They are adequate for regression and for detecting gross\n"
        "failure; they cannot substantiate a positional accuracy class.\n\n"
        "This folder must never be mounted into the reconstruction worker.\n")

    # ---- flown geometry, recomputed here so the manifest stands alone ----
    lat0 = sum(r.lat for r in rows) / len(rows)
    mx = 111320.0 * math.cos(math.radians(lat0))
    xy = [((r.lon - rows[0].lon) * mx, (r.lat - rows[0].lat) * 110540.0)
          for r in rows]
    steps = [math.dist(xy[i], xy[i + 1]) for i in range(len(xy) - 1)]
    ss = sorted(steps)

    manifest = {
        "mission_id": name,
        "schema_version": 1,
        "built_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "built_by": "drishti3d/scripts/build_agz_mission.py",
        "dataset": "Zurich Urban Micro Aerial Vehicle (AGZ)",
        "source_image_dir": str(source.relative_to(REPO)),
        "source_license": "AGZ MAV imagery: academic research use, per "
                          "AGZ_subset/readme.txt",
        "capture": {
            "n_frames": len(images),
            "imgid_first": rows[0].imgid, "imgid_last": rows[-1].imgid,
            "imgid_stride": rows[1].imgid - rows[0].imgid,
            "duration_s": round((rows[-1].timestamp_us - t0_us) / 1e6, 3),
            "path_length_m": round(sum(steps), 1),
            "net_displacement_m": round(math.dist(xy[0], xy[-1]), 1),
            "median_frame_baseline_m": round(ss[len(ss) // 2], 2),
            "alt_msl_min_m": round(min(r.alt_msl_m for r in rows), 1),
            "alt_msl_max_m": round(max(r.alt_msl_m for r in rows), 1),
            "gnss_fix_types": sorted({r.fix_type for r in rows}),
            "gnss_eph_m_median": round(
                sorted(r.eph_m for r in rows)[len(rows) // 2], 2),
        },
        "artifacts": {
            "video": {"path": "raw/video.mp4", "sha256": _sha256(video),
                      "bytes": video.stat().st_size,
                      "encoder": f"libx264 crf={crf} preset=slow, VFR from "
                                 f"log presentation timestamps"},
            "telemetry": {"path": "raw/telemetry.csv",
                          "sha256": _sha256(tel), "rows": len(rows)},
            "frame_index": {"path": "raw/frame_index.csv",
                            "sha256": _sha256(index)},
            "camera": {"path": "calibration/camera.json",
                       "sha256": _sha256(mission / "calibration/camera.json")},
        },
        "reference": {
            "path": str((truth_dir).relative_to(REPO)),
            "n_reference_positions": n_ref,
            "crs": "EPSG:32632 (WGS 84 / UTM zone 32N)",
            "independence": "NOT independent. Pix4D photogrammetry by the "
                            "dataset authors over the full image set with loop "
                            "closures; uncertainty not published.",
        },
        "known_deviations": [
            "video.mp4 is an H.264 re-encode of already-JPEG-compressed frames, "
            "not an original camera bitstream. Compression artefacts are "
            "therefore double-applied. Use raw/frame_index.csv to cite the "
            "original JPEG for any evidence display.",
            "The frame set is a stride subsample of a 30 Hz capture; the video "
            "is variable-frame-rate with the real log spacing between frames. "
            "Frames between the sampled ids exist in the full AGZ archive and "
            "are the natural candidate pool for same-pass refinement, but are "
            "not present in this checkout.",
            "sigma_u_m is empty: AGZ's epv_m column is corrupt in the published "
            "release. Vertical GNSS accuracy is unknown.",
            "Images are distorted; camera.json carries k1..k3,p1,p2 and "
            "distortion_applied_to_images is false.",
        ],
        "allowed_claims": [
            "Relative reconstruction and metric reconnaissance on real aerial "
            "imagery with real consumer-grade GNSS.",
        ],
        "prohibited_claims": [
            "Any independently validated survey deliverable. There are no "
            "independent checkpoints and no reference dimensions for this site.",
            "Any positional accuracy class: agreement with the AGZ reference is "
            "not an accuracy assessment.",
        ],
        "camera": cam,
    }
    (mission / "manifest.json").write_text(json.dumps(manifest, indent=2))
    (mission / "manifest.yaml").write_text(
        "# Mirror of manifest.json in the layout of plan section 6.6.\n"
        "# manifest.json is authoritative; this file is for reading.\n" +
        __import__("yaml").safe_dump(manifest, sort_keys=False, width=100))
    return manifest


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--source", required=True,
                    help="directory of numerically named AGZ JPEGs, relative "
                         "to the repository root or absolute")
    ap.add_argument("--name", required=True, help="mission id")
    ap.add_argument("--overwrite", action="store_true")
    ap.add_argument("--crf", type=int, default=12,
                    help="x264 quality (lower is better; 12 is near-visually-"
                         "lossless and keeps the re-encode from dominating)")
    a = ap.parse_args()
    src = Path(a.source)
    if not src.is_absolute():
        src = (REPO / src) if (REPO / src).exists() else (APP / src)
    m = build(src.resolve(), a.name, a.overwrite, a.crf)
    print(json.dumps({"mission": m["mission_id"], **m["capture"],
                      "video_bytes": m["artifacts"]["video"]["bytes"],
                      "reference_positions":
                          m["reference"]["n_reference_positions"]}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
