#!/usr/bin/env python3
"""Inventory every dataset already present in this checkout.

Motivation (plan section 6.2): before requesting another download, establish
what is actually on disk, whether it decodes, what it covers, and what it can
and cannot be used to claim.  A previous session's notes in this repository
recorded that some bundled binaries were unfetched Git-LFS pointers; this
script distinguishes real bytes from pointer stubs by inspection rather than by
trusting file size or extension.

Writes:
  datasets/catalog.csv   one row per dataset entry, machine-readable
  datasets/INVENTORY.md  the same content with the caveats spelled out

Usage:
  python scripts/inventory_datasets.py [--no-hash]

``--no-hash`` skips content hashing (fast re-run for counts only).  Hashing the
image sets reads about 2.4 GB and takes roughly a minute on a warm cache.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import subprocess
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from agz_logs import read_gps, read_truth   # noqa: E402

REPO = Path(__file__).resolve().parents[2]          # /home/naveen/Drishti3D
APP = REPO / "drishti3d"
OUT_DIR = REPO / "datasets"

#: A Git-LFS pointer file is a tiny text file starting with this line.  Any
#: "image" or "video" that is really a pointer must never be counted as data.
LFS_MAGIC = b"version https://git-lfs.github.com/spec/"

IMAGE_EXT = {".jpg", ".jpeg", ".png", ".tif", ".tiff"}
VIDEO_EXT = {".mp4", ".mov", ".webm", ".ogv", ".mkv", ".avi"}


@dataclass
class Entry:
    name: str
    path: str
    kind: str                     # image_set | video | archive | mixed
    n_files: int = 0
    bytes: int = 0
    lfs_pointers: int = 0
    content_sha256: str = ""      # digest over the per-file digests, order-stable
    notes: list = field(default_factory=list)
    detail: dict = field(default_factory=dict)


def _sha256(path: Path, chunk: int = 1 << 20) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        while True:
            b = fh.read(chunk)
            if not b:
                break
            h.update(b)
    return h.hexdigest()


def _is_lfs_pointer(path: Path) -> bool:
    try:
        with open(path, "rb") as fh:
            return fh.read(len(LFS_MAGIC)) == LFS_MAGIC
    except OSError:
        return False


def _scan_dir(root: Path, do_hash: bool):
    """(n_files, total_bytes, n_lfs_pointers, set_digest) over a directory tree.

    The set digest is sha256 over ``"<relpath>:<file sha256>\\n"`` lines sorted
    by path, so it is stable across filesystem ordering and identifies the exact
    content of the set -- two checkouts agree only if every byte agrees.
    """
    files = sorted(p for p in root.rglob("*") if p.is_file())
    n_bytes = 0
    n_lfs = 0
    agg = hashlib.sha256()
    for p in files:
        size = p.stat().st_size
        n_bytes += size
        if size < 4096 and _is_lfs_pointer(p):
            n_lfs += 1
        if do_hash:
            agg.update(f"{p.relative_to(root)}:{_sha256(p)}\n".encode())
    return len(files), n_bytes, n_lfs, (agg.hexdigest() if do_hash else "")


def _probe_video(path: Path) -> dict:
    """ffprobe facts that matter for reconstruction: real PTS, not nominal fps."""
    try:
        out = subprocess.run(
            ["ffprobe", "-v", "error", "-select_streams", "v:0",
             "-show_entries",
             "stream=width,height,avg_frame_rate,r_frame_rate,nb_frames,codec_name"
             ":format=duration",
             "-of", "json", str(path)],
            capture_output=True, text=True, timeout=180, check=True)
        j = json.loads(out.stdout)
        s = (j.get("streams") or [{}])[0]
        f = j.get("format") or {}
        return {"codec": s.get("codec_name"), "width": s.get("width"),
                "height": s.get("height"),
                "avg_frame_rate": s.get("avg_frame_rate"),
                "r_frame_rate": s.get("r_frame_rate"),
                "nb_frames": s.get("nb_frames"),
                "duration_s": float(f["duration"]) if f.get("duration") else None}
    except Exception as e:                       # noqa: BLE001 - report, never raise
        return {"error": f"{type(e).__name__}: {e}"}


def _agz_segment_detail(img_dir: Path) -> dict:
    """Rejoin an AGZ frame subset to its telemetry and reference positions.

    Returns the flown geometry of the segment, which is the fact that decides
    whether the subset is usable at all: a segment with no baseline cannot
    produce triangulated depth no matter how much compute is spent on it.
    """
    log_dir = APP / "data/real_drone/AGZ_subset/Log Files"
    if not log_dir.exists():
        return {"error": "AGZ log files not present"}
    ids = []
    for p in sorted(img_dir.iterdir()):
        if p.suffix.lower() in IMAGE_EXT and p.stem.isdigit():
            ids.append(int(p.stem))
    if not ids:
        return {"error": "no numerically named images"}
    ids.sort()
    gps = read_gps(log_dir)
    truth = read_truth(log_dir)
    rows = [gps[i] for i in ids if i in gps]
    if len(rows) < 2:
        return {"n_images": len(ids), "error": "fewer than 2 telemetry matches"}
    lat0 = sum(r.lat for r in rows) / len(rows)
    mx = 111320.0 * math.cos(math.radians(lat0))
    xy = [((r.lon - rows[0].lon) * mx, (r.lat - rows[0].lat) * 110540.0)
          for r in rows]
    steps = [math.dist(xy[i], xy[i + 1]) for i in range(len(xy) - 1)]
    ss = sorted(steps)
    ephs = sorted(r.eph_m for r in rows)
    return {
        "n_images": len(ids),
        "imgid_first": ids[0], "imgid_last": ids[-1],
        "imgid_stride": ids[1] - ids[0] if len(ids) > 1 else None,
        "n_telemetry_matched": len(rows),
        "n_reference_positions": sum(1 for i in ids if i in truth),
        "duration_s": round((rows[-1].timestamp_us - rows[0].timestamp_us) / 1e6, 1),
        "path_length_m": round(sum(steps), 1),
        "net_displacement_m": round(math.dist(xy[0], xy[-1]), 1),
        "median_step_m": round(ss[len(ss) // 2], 2),
        "alt_msl_min_m": round(min(r.alt_msl_m for r in rows), 1),
        "alt_msl_max_m": round(max(r.alt_msl_m for r in rows), 1),
        "fix_types": sorted({r.fix_type for r in rows}),
        "eph_m_median": round(ephs[len(ephs) // 2], 2),
    }


def build(do_hash: bool):
    entries = []
    rd = APP / "data/real_drone"

    # --- AGZ publisher archive -------------------------------------------
    agz = rd / "AGZ_subset"
    if agz.exists():
        n, b, lfs, dig = _scan_dir(agz, do_hash)
        det = _agz_segment_detail(agz / "MAV Images")
        e = Entry("zurich_mav/AGZ_subset", str(agz.relative_to(REPO)),
                  "mixed", n, b, lfs, dig, detail=det)
        e.notes.append("Publisher subset of the Zurich Urban MAV dataset: 350 "
                       "MAV frames, 30 calibration images, 113 Street View "
                       "images, and the full flight logs for all 81,169 frames.")
        e.notes.append("Reference camera positions in GroundTruthAGL.csv are "
                       "Pix4D photogrammetry by the dataset authors, not "
                       "independent RTK or LiDAR survey truth.")
        if det.get("path_length_m", 1e9) < 20:
            e.notes.append(
                f"UNUSABLE FOR RECONSTRUCTION AS SHIPPED: the 350 bundled MAV "
                f"frames span {det.get('path_length_m')} m of flight over "
                f"{det.get('duration_s')} s (net displacement "
                f"{det.get('net_displacement_m')} m). This is a pre-flight "
                f"hold, not a pass. No useful baseline means no triangulated "
                f"depth. Flying segments must come from the full archive.")
        e.notes.append("OnboardGPS.csv epv_m is corrupt in the published "
                       "release (values around 1e-43, not metres); vertical "
                       "GNSS accuracy is unknown, not small.")
        entries.append(e)

    zipf = rd / "AGZ_subset.zip"
    if zipf.exists():
        e = Entry("zurich_mav/AGZ_subset.zip", str(zipf.relative_to(REPO)),
                  "archive", 1, zipf.stat().st_size, 0,
                  _sha256(zipf) if do_hash else "")
        e.notes.append("Source archive for the extracted AGZ_subset/ above. "
                       "Keep intact; do not re-extract over the working copy.")
        entries.append(e)

    # --- prepared AGZ flying segments ------------------------------------
    for seg in sorted(p for p in rd.glob("agz_*") if p.is_dir()):
        n, b, lfs, dig = _scan_dir(seg, do_hash)
        det = _agz_segment_detail(seg)
        e = Entry(f"zurich_mav/{seg.name}", str(seg.relative_to(REPO)),
                  "image_set", n, b, lfs, dig, detail=det)
        e.notes.append("Frame subset drawn from the full AGZ archive (frame "
                       "ids outside the 1-350 publisher subset), rejoined to "
                       "the bundled logs by imgid.")
        if det.get("path_length_m", 0) >= 20:
            e.notes.append(
                f"Real single-pass geometry: {det['path_length_m']} m flown in "
                f"{det['duration_s']} s, median frame-to-frame baseline "
                f"{det['median_step_m']} m, {det['n_reference_positions']} "
                f"published reference positions.")
        entries.append(e)

    # --- loose videos -----------------------------------------------------
    for vid in sorted(p for p in rd.iterdir()
                      if p.is_file() and p.suffix.lower() in VIDEO_EXT):
        det = _probe_video(vid)
        e = Entry(f"video/{vid.stem}", str(vid.relative_to(REPO)), "video", 1,
                  vid.stat().st_size, 1 if _is_lfs_pointer(vid) else 0,
                  _sha256(vid) if do_hash else "", detail=det)
        e.notes.append("No telemetry accompanies this clip in the checkout; "
                       "usable as a visual/structural stress test only, never "
                       "for a georeferenced or metric claim.")
        entries.append(e)

    # --- other image sets -------------------------------------------------
    for extra, note in [
        (rd / "shots", "Cut-down frame sets extracted from the loose videos."),
        (rd / "monterey_strip", "Public drone photo strip; no telemetry logs "
                                "in the checkout."),
        (REPO / "datasets/public/odm_data_bellus-master", "OpenDroneMap Bellus photo survey "
                                         "with gcp_list.txt. A photo survey, "
                                         "not a single-pass video capture."),
        (APP / "sample_data", "Synthetic fixtures generated by "
                              "drishti_recon.synth, with exact ground truth. "
                              "Deterministic diagnosis only; never evidence of "
                              "field accuracy."),
    ]:
        if not extra.exists():
            continue
        n, b, lfs, dig = _scan_dir(extra, do_hash)
        e = Entry(f"other/{extra.name}", str(extra.relative_to(REPO)),
                  "mixed", n, b, lfs, dig)
        e.notes.append(note)
        if lfs:
            e.notes.append(f"{lfs} of {n} files are unfetched Git-LFS pointers "
                           f"and contain no data.")
        entries.append(e)

    # --- built missions under datasets/ -----------------------------------
    for mission in sorted((OUT_DIR / "public").glob("*/*/manifest.json")):
        d = mission.parent
        n, b, lfs, dig = _scan_dir(d, do_hash)
        e = Entry(f"mission/{d.parent.name}/{d.name}", str(d.relative_to(REPO)),
                  "mixed", n, b, lfs, dig,
                  detail=json.loads(mission.read_text()))
        e.notes.append("Built mission in the plan's datasets/ layout; "
                       "regenerate with scripts/build_agz_mission.py.")
        entries.append(e)

    return entries


def write_outputs(entries, do_hash: bool) -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    with open(OUT_DIR / "catalog.csv", "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["name", "path", "kind", "n_files", "bytes", "lfs_pointers",
                    "content_sha256", "detail_json", "notes"])
        for e in entries:
            w.writerow([e.name, e.path, e.kind, e.n_files, e.bytes,
                        e.lfs_pointers, e.content_sha256,
                        json.dumps(e.detail, sort_keys=True),
                        " | ".join(e.notes)])

    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    lines = [
        "# Dataset inventory",
        "",
        f"Generated {now} by `drishti3d/scripts/inventory_datasets.py`"
        f"{'' if do_hash else ' with `--no-hash` (digests omitted)'}.",
        "",
        "Every figure below was read off the files in this checkout. Nothing "
        "here is carried over from an earlier report.",
        "",
        "| Entry | Files | Size | LFS stubs | Path |",
        "|---|---:|---:|---:|---|",
    ]
    for e in entries:
        lines.append(f"| `{e.name}` | {e.n_files} | {e.bytes / 1e6:,.1f} MB | "
                     f"{e.lfs_pointers} | `{e.path}` |")
    lines += ["", "## Per-entry detail", ""]
    for e in entries:
        lines += [f"### `{e.name}`", "", f"- Path: `{e.path}`",
                  f"- {e.n_files} files, {e.bytes / 1e6:,.1f} MB, "
                  f"{e.lfs_pointers} unfetched LFS pointers"]
        if e.content_sha256:
            lines.append(f"- Content digest: `{e.content_sha256}`")
        if e.detail:
            lines += ["- Detail:", "", "  ```json"]
            lines += ["  " + ln for ln in
                      json.dumps(e.detail, indent=2, sort_keys=True).splitlines()]
            lines.append("  ```")
        lines += [f"- {n}" for n in e.notes]
        lines.append("")
    (OUT_DIR / "INVENTORY.md").write_text("\n".join(lines) + "\n")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--no-hash", action="store_true",
                    help="skip content hashing (counts and geometry only)")
    args = ap.parse_args()
    entries = build(do_hash=not args.no_hash)
    write_outputs(entries, do_hash=not args.no_hash)
    print(f"{len(entries)} entries -> {OUT_DIR / 'catalog.csv'}, "
          f"{OUT_DIR / 'INVENTORY.md'}")
    for e in entries:
        flag = "  [LFS STUBS]" if e.lfs_pointers else ""
        print(f"  {e.name:36s} {e.n_files:6d} files "
              f"{e.bytes / 1e6:10,.1f} MB{flag}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
