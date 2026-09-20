#!/usr/bin/env python3
"""Build a mission from a bare video clip: no telemetry, no reference data.

`build_agz_mission.py` joins frames to flight logs. These clips have neither
logs nor EXIF intrinsics, so a mission built here is deliberately poorer:

* **Relative scale only.** Without telemetry the pipeline reconstructs shape in
  arbitrary units. Every measurement on it carries `scale_not_established`, and
  no distance in metres can be read off it.
* **Estimated intrinsics.** The pipeline falls back to focal = 0.9*max(w,h) and
  says so in its warnings.
* **No reference data at all**, so nothing here can be scored against truth.

What such a mission *is* good for is a comparison whose metric is common to both
arms -- the F4 targeted-versus-uniform gate -- because a blocker both arms carry
equally cancels out of it. It is the only way to test that comparison on a
second flight with the data in this checkout.

The window arguments exist because these clips contain scene cuts, which the
reconstruction cannot bridge and must not invent motion across. The cut-free
window per clip was identified in `docs/WORK_LOG.md`.

Usage:
  python scripts/build_clip_mission.py --source data/real_drone/st_lambertus.webm \
      --name lambertus --start 182 --end 223.5 --overwrite
"""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
APP = REPO / "drishti3d"


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _probe(path: Path) -> dict:
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
         "stream=width,height,avg_frame_rate,codec_name:format=duration",
         "-of", "json", str(path)],
        capture_output=True, text=True, check=True)
    j = json.loads(out.stdout)
    s = (j.get("streams") or [{}])[0]
    f = j.get("format") or {}
    return {"codec": s.get("codec_name"), "width": s.get("width"),
            "height": s.get("height"),
            "avg_frame_rate": s.get("avg_frame_rate"),
            "duration_s": float(f["duration"]) if f.get("duration") else None}


def build(source: Path, name: str, start, end, overwrite: bool,
          crf: int) -> dict:
    mission = REPO / "datasets/public/field_clips" / name
    if mission.exists():
        if not overwrite:
            raise SystemExit(f"{mission} exists; pass --overwrite")
        shutil.rmtree(mission)
    (mission / "raw").mkdir(parents=True, exist_ok=True)
    (mission / "calibration").mkdir(parents=True, exist_ok=True)

    src_info = _probe(source)
    video = mission / "raw" / "video.mp4"
    # Re-encoded rather than stream-copied: a copy would start at the nearest
    # keyframe before --start, which is not the window that was checked for
    # scene cuts.
    cmd = ["ffmpeg", "-y", "-v", "error"]
    if start is not None:
        cmd += ["-ss", str(start)]
    if end is not None:
        cmd += ["-to", str(end)]
    cmd += ["-i", str(source), "-an", "-c:v", "libx264", "-preset", "slow",
            "-crf", str(crf), "-pix_fmt", "yuv420p", str(video)]
    subprocess.run(cmd, check=True)
    out_info = _probe(video)

    (mission / "calibration" / "camera.json").write_text(json.dumps({
        "model": "UNKNOWN",
        "source": "none - this clip carries no EXIF or calibration data",
        "image_width": out_info["width"], "image_height": out_info["height"],
        "notes": ["The pipeline will estimate focal = 0.9*max(w,h) and warn. "
                  "That is a guess, not a calibration."],
    }, indent=2))

    manifest = {
        "mission_id": name,
        "schema_version": 1,
        "built_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "built_by": "drishti3d/scripts/build_clip_mission.py",
        "dataset": "public drone footage, no telemetry",
        "source_clip": str(source.relative_to(REPO)),
        "source_info": src_info,
        "window_s": [start, end],
        "capture": {"duration_s": out_info["duration_s"],
                    "frame_rate": out_info["avg_frame_rate"],
                    "width": out_info["width"], "height": out_info["height"]},
        "artifacts": {"video": {"path": "raw/video.mp4",
                                "sha256": _sha256(video),
                                "bytes": video.stat().st_size,
                                "encoder": f"libx264 crf={crf}"}},
        "telemetry": None,
        "reference": None,
        "known_deviations": [
            "No telemetry: the reconstruction has relative scale only, and "
            "every measurement carries scale_not_established.",
            "No camera calibration: intrinsics are estimated from frame size.",
            "Re-encode of already-compressed footage.",
            "The window was chosen as the longest cut-free run; cuts elsewhere "
            "in the source clip cannot be bridged by reconstruction.",
        ],
        "allowed_claims": [
            "Relative reconstruction, and comparisons whose metric is common "
            "to both arms being compared.",
        ],
        "prohibited_claims": [
            "Any distance in metres, any geographic position, any accuracy "
            "figure. There is no scale source and no reference data.",
        ],
    }
    (mission / "manifest.json").write_text(json.dumps(manifest, indent=2))
    return manifest


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--source", required=True)
    ap.add_argument("--name", required=True)
    ap.add_argument("--start", type=float, default=None)
    ap.add_argument("--end", type=float, default=None)
    ap.add_argument("--overwrite", action="store_true")
    ap.add_argument("--crf", type=int, default=14)
    a = ap.parse_args()
    src = Path(a.source)
    if not src.is_absolute():
        src = (REPO / src) if (REPO / src).exists() else (APP / src)
    m = build(src.resolve(), a.name, a.start, a.end, a.overwrite, a.crf)
    print(json.dumps({"mission": m["mission_id"], **m["capture"],
                      "bytes": m["artifacts"]["video"]["bytes"]}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
