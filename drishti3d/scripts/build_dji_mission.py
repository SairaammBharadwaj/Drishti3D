#!/usr/bin/env python3
"""Build a mission from a DJI video plus its SRT telemetry.

DJI writes one SRT block per video frame carrying GPS, altitude and camera
settings. That is the de-facto standard for georeferenced drone video --
OpenDroneMap uses the same `video.mp4` + `video.srt` pairing -- and it is the
only public source of native long-form drone video with telemetry we found.

The SRT is converted to the mission's `telemetry.csv` schema using the
project's own parser, so a format quirk is fixed in one place rather than
twice. Telemetry timestamps are the SRT block times, which are frame-accurate
by construction.

The video is **copied, not re-encoded**. Every other mission builder here
assembles a video from stills and must encode; this one already has the
original camera bitstream, and re-encoding it would throw away the thing that
makes this capture worth having.

Usage:
  python scripts/build_dji_mission.py --video ~/Downloads/DJI_1003_1080p.mp4 \
      --srt ~/Downloads/DJI_1003.srt --name dji_1003 --overwrite
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parents[2]
APP = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(APP / "reconstruction"))

TELEMETRY_COLUMNS = [
    "timestamp", "timestamp_ns", "time_basis", "latitude", "longitude",
    "altitude", "latitude_deg", "longitude_deg", "altitude_m",
    "altitude_reference", "sigma_e_m", "sigma_n_m", "sigma_u_m",
    "fix_type", "gps_accuracy", "num_satellites", "imgid",
]

#: DJI SRT altitude kinds mapped to what the pipeline understands. "unspecified"
#: is carried through rather than guessed: newer firmware writes a bare
#: `altitude` and does not say which datum it uses.
ALT_REFERENCE = {"msl": "MSL", "relative_to_takeoff": "RELATIVE_TO_TAKEOFF",
                 "unspecified": "UNSPECIFIED", "missing": "UNKNOWN"}


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def probe(video: Path) -> dict:
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "v:0",
         "-show_entries", "stream=width,height,r_frame_rate,nb_frames",
         "-show_entries", "format=duration", "-of", "json", str(video)],
        capture_output=True, text=True, check=True).stdout
    d = json.loads(out)
    st = d["streams"][0]
    num, den = st["r_frame_rate"].split("/")
    return {"width": int(st["width"]), "height": int(st["height"]),
            "fps": float(num) / float(den),
            "n_frames": int(st.get("nb_frames") or 0),
            "duration_s": float(d["format"]["duration"])}


def main() -> int:
    from drishti_recon import telemetry as tel

    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--video", required=True)
    ap.add_argument("--srt", default=None,
                    help="defaults to the video path with a .srt suffix, or the "
                         "video's own embedded subtitle track")
    ap.add_argument("--name", required=True)
    ap.add_argument("--set", default="field_clips")
    ap.add_argument("--overwrite", action="store_true")
    a = ap.parse_args()

    video = Path(a.video).expanduser().resolve()
    if not video.is_file():
        raise SystemExit(f"no video at {video}")
    srt = Path(a.srt).expanduser().resolve() if a.srt else None
    if srt is None:
        cand = video.with_suffix(".srt")
        srt = cand if cand.is_file() else video       # fall back to embedded
    report = tel.load(srt)
    if not report.ok:
        raise SystemExit(f"telemetry unusable: {len(report.samples)} valid samples")

    info = probe(video)
    mission = REPO / "datasets" / "public" / a.set / a.name
    if mission.exists():
        if not a.overwrite:
            raise SystemExit(f"{mission} exists; pass --overwrite")
        shutil.rmtree(mission)
    (mission / "raw").mkdir(parents=True)

    dst = mission / "raw" / f"video{video.suffix}"
    shutil.copy2(video, dst)
    if dst.suffix != ".mp4":
        dst = dst.rename(mission / "raw" / "video.mp4")

    s = report.samples
    t0 = s[0].timestamp
    alt_ref = ALT_REFERENCE.get(
        s[0].extra.get("altitude_kind", "missing"), "UNKNOWN")
    with open(mission / "raw" / "telemetry.csv", "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=TELEMETRY_COLUMNS)
        w.writeheader()
        for smp in s:
            w.writerow({
                "timestamp": f"{smp.timestamp - t0:.6f}",
                "timestamp_ns": int(round((smp.timestamp - t0) * 1e9)),
                "time_basis": "video_pts_s",
                "latitude": f"{smp.latitude:.8f}",
                "longitude": f"{smp.longitude:.8f}",
                "altitude": f"{smp.altitude:.3f}",
                "latitude_deg": f"{smp.latitude:.8f}",
                "longitude_deg": f"{smp.longitude:.8f}",
                "altitude_m": f"{smp.altitude:.3f}",
                "altitude_reference": alt_ref,
                # DJI's SRT carries no per-sample GNSS covariance. Empty means
                # unknown, which is not the same as small.
                "sigma_e_m": "", "sigma_n_m": "", "sigma_u_m": "",
                "fix_type": "", "gps_accuracy": "", "num_satellites": "",
                "imgid": "",
            })

    lat = np.array([x.latitude for x in s])
    lon = np.array([x.longitude for x in s])
    alt = np.array([x.altitude for x in s])
    mlat = float(np.mean(lat))
    span_n = float(np.ptp(lat) * 111320)
    span_e = float(np.ptp(lon) * 111320 * np.cos(np.radians(mlat)))

    # `run_mission.py` requires a calibration file even when there is no
    # calibration, so the absence is recorded explicitly rather than left as a
    # missing file. DJI's SRT carries `focal_len`, but in undocumented units
    # and with no principal point or distortion -- not enough to calibrate
    # from, and DEC-038 measured what a 1.45% focal error costs. Guessing here
    # would be worse than the documented fallback.
    (mission / "calibration").mkdir(parents=True, exist_ok=True)
    focal_raw = s[0].extra.get("focal_len_mm")
    (mission / "calibration" / "camera.json").write_text(json.dumps({
        "model": "UNKNOWN",
        "source": "none - DJI SRT carries no usable camera calibration",
        "image_width": info["width"], "image_height": info["height"],
        "srt_focal_len_raw": focal_raw,
        "notes": [
            "No fx/fy/cx/cy, so the pipeline estimates focal = 0.9*max(w,h) "
            "and says so in its own warnings.",
            "The SRT reports focal_len but not its units, sensor size, "
            "principal point or distortion. It is recorded here unconverted "
            "so a later calibration can use it, and is deliberately not fed "
            "to the reconstruction.",
        ],
    }, indent=2))

    manifest = {
        "mission_id": a.name,
        "schema_version": 1,
        "built_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "built_by": "drishti3d/scripts/build_dji_mission.py",
        "dataset": "DJI video with SRT telemetry",
        "source_video": str(video),
        "video_sha256": sha256(dst),
        "video": info,
        "video_note": ("original camera bitstream, copied not re-encoded"),
        "telemetry": {
            "source": str(srt),
            "n_samples": len(s),
            "altitude_reference": alt_ref,
            "altitude_note": (
                "DJI writes a bare `altitude` without stating its datum; "
                "carried through as UNSPECIFIED rather than assumed to be MSL"
                if alt_ref == "UNSPECIFIED" else ""),
            "warnings": report.warnings[:5],
        },
        "capture": {
            "duration_s": round(info["duration_s"], 2),
            "n_frames": info["n_frames"],
            "footprint_m": [round(span_e, 1), round(span_n, 1)],
            "altitude_min_m": round(float(alt.min()), 1),
            "altitude_max_m": round(float(alt.max()), 1),
            "altitude_range_m": round(float(np.ptp(alt)), 1),
        },
    }
    (mission / "manifest.json").write_text(json.dumps(manifest, indent=2))

    print(f"mission {a.name}")
    print(f"  video      {info['width']}x{info['height']} @ {info['fps']:.2f} fps, "
          f"{info['duration_s']:.1f} s ({info['duration_s']/60:.1f} min), "
          f"{info['n_frames']:,} frames")
    print(f"  telemetry  {len(s):,} samples, altitude reference {alt_ref}")
    print(f"  footprint  {span_e:.0f} x {span_n:.0f} m, "
          f"altitude range {np.ptp(alt):.1f} m")
    print(f"  -> {mission}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
