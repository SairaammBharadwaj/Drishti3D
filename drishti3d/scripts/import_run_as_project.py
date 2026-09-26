#!/usr/bin/env python3
"""Open a `run_mission.py` result in the web workspace as a project.

Reconstructions produced for benchmarking live under `data/runs/`, outside the
application's project store, so nothing built there is reachable from the UI.
This registers one as a project: a database row, the artifacts, and the
inputs -- the source video, which same-pass refinement needs since it re-reads
frames the reconstruction never used, and the telemetry and camera calibration
the run was given.

The inputs used to stop at the video. A georeferenced DJI run then showed in
the UI as "Video only · relative scale", and processing it again from the web
would have run without GPS. `--mission` takes all three from the built mission
directory, exactly as `run_mission.py` reads them.

Artifacts are **copied, not linked**. A benchmark run is a record of what was
measured; a project is something the UI writes measurements against, and they
should not be the same bytes.

Usage:
  python scripts/import_run_as_project.py --run dji_1003__perf_final \
      --mission datasets/public/field_clips/dji_1003 --name "DJI_1003 pass"

  # attach inputs to a project imported before --mission existed
  python scripts/import_run_as_project.py --project 051960be... \
      --mission datasets/public/field_clips/dji_1003 --no-artifacts

  # the original form still works (video only)
  python scripts/import_run_as_project.py --run agz_dense_pass__colmap_unc \
      --video datasets/public/zurich_mav/agz_dense_pass/raw/video.mp4 \
      --name "AGZ single pass (GNSS)"
"""
from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
APP = REPO / "drishti3d"
sys.path.insert(0, str(APP / "backend"))
sys.path.insert(0, str(APP / "reconstruction"))


def intrinsics_from_camera(cam: dict) -> dict | None:
    """The project's intrinsics from a mission's ``calibration/camera.json``.

    Mirrors `run_mission.py`: no fx/fy/cx/cy means no calibration (the DJI
    missions), and distortion is carried only when the file gives
    coefficients. UseGeo's images are already undistorted and carry none.
    """
    if not all(k in cam for k in ("fx", "fy", "cx", "cy")):
        return None
    out = {"fx": cam["fx"], "fy": cam["fy"], "cx": cam["cx"], "cy": cam["cy"],
           "model": cam.get("model", "PINHOLE")}
    if "k1" in cam:
        out["distortion"] = [cam["k1"], cam["k2"], cam["p1"], cam["p2"],
                             cam.get("k3", 0.0)]
    if cam.get("image_width") and cam.get("image_height"):
        out["source_width"] = int(cam["image_width"])
        out["source_height"] = int(cam["image_height"])
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--run", help="directory name under data/runs/")
    src = ap.add_mutually_exclusive_group(required=True)
    src.add_argument("--mission",
                     help="built mission directory (raw/video.mp4, "
                          "raw/telemetry.csv, calibration/camera.json), "
                          "relative to the repository root")
    src.add_argument("--video", help="source clip, relative to the repository root")
    tgt = ap.add_mutually_exclusive_group(required=True)
    tgt.add_argument("--name", help="project name; an existing project of that "
                                    "name is reused")
    tgt.add_argument("--project", help="existing project id")
    ap.add_argument("--description", default="")
    ap.add_argument("--no-artifacts", action="store_true",
                    help="attach inputs only; leave the project's artifacts as "
                         "they are")
    a = ap.parse_args()
    if not a.no_artifacts and not a.run:
        ap.error("--run is required unless --no-artifacts")

    from app.db import SessionLocal, init_db
    from app.models import Project
    from app import storage

    if a.mission:
        mdir = REPO / a.mission
        video = mdir / "raw/video.mp4"
        telemetry = mdir / "raw/telemetry.csv"
        telemetry = telemetry if telemetry.is_file() else None
        cam_path = mdir / "calibration/camera.json"
        intrinsics = (intrinsics_from_camera(json.loads(cam_path.read_text()))
                      if cam_path.is_file() else None)
    else:
        video, telemetry, intrinsics = REPO / a.video, None, None
    if not video.is_file():
        raise SystemExit(f"no video at {video}")

    art_src = None
    if not a.no_artifacts:
        art_src = APP / "data/runs" / a.run / "artifacts"
        if not art_src.is_dir():
            raise SystemExit(f"no artifacts at {art_src}")

    init_db()
    db = SessionLocal()
    try:
        if a.project:
            p = db.get(Project, a.project)
            if p is None:
                raise SystemExit(f"no project {a.project}")
            print(f"updating project {p.id} ({p.name})")
        else:
            p = db.query(Project).filter(Project.name == a.name).first()
            if p is not None:
                print(f"reusing project {p.id} ({a.name})")
            else:
                p = Project(name=a.name, description=a.description, status="done")
                db.add(p)
                db.commit()
                db.refresh(p)

        n = 0
        if art_src is not None:
            art_dst = storage.artifacts_dir(p.id)
            art_dst.mkdir(parents=True, exist_ok=True)
            for f in sorted(art_src.iterdir()):
                if f.is_file():
                    shutil.copy2(f, art_dst / f.name)
                    n += 1
            p.status = "done"

        up = storage.uploads_dir(p.id)
        up.mkdir(parents=True, exist_ok=True)
        dst_video = up / f"video{video.suffix}"
        if not dst_video.exists():
            shutil.copy2(video, dst_video)
        p.video_filename = dst_video.name
        if telemetry is not None:
            dst_tel = up / f"telemetry{telemetry.suffix}"
            shutil.copy2(telemetry, dst_tel)
            p.telemetry_filename = dst_tel.name
        if intrinsics is not None:
            p.intrinsics = intrinsics
        db.commit()
        # A stale cached frame would make a refinement match against whatever
        # video previously sat at this path.
        from drishti_recon.refinement import clear_detect_cache
        clear_detect_cache()
        print(f"project {p.id}\n  name        {p.name}")
        if art_src is not None:
            print(f"  artifacts   {n} files -> {storage.artifacts_dir(p.id)}")
        print(f"  video       {dst_video}")
        print(f"  telemetry   {p.telemetry_filename or 'none'}")
        print(f"  intrinsics  {'supplied' if p.intrinsics else 'none (estimated)'}")
        print(f"  open        /projects/{p.id}")
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
