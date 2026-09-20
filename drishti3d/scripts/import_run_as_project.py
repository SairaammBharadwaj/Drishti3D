#!/usr/bin/env python3
"""Open a `run_mission.py` result in the web workspace as a project.

Reconstructions produced for benchmarking live under `data/runs/`, outside the
application's project store, so nothing built there is reachable from the UI.
This registers one as a project: a database row, the artifacts, and the source
video -- which same-pass refinement needs, since it re-reads frames the
reconstruction never used.

Artifacts are **copied, not linked**. A benchmark run is a record of what was
measured; a project is something the UI writes measurements against, and they
should not be the same bytes.

Usage:
  python scripts/import_run_as_project.py --run agz_dense_pass__colmap_unc \
      --video datasets/public/zurich_mav/agz_dense_pass/raw/video.mp4 \
      --name "AGZ single pass (GNSS)"
"""
from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
APP = REPO / "drishti3d"
sys.path.insert(0, str(APP / "backend"))
sys.path.insert(0, str(APP / "reconstruction"))


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--run", required=True, help="directory name under data/runs/")
    ap.add_argument("--video", required=True,
                    help="source clip, relative to the repository root")
    ap.add_argument("--name", required=True)
    ap.add_argument("--description", default="")
    a = ap.parse_args()

    from app.db import SessionLocal, init_db
    from app.models import Project
    from app import storage

    run_dir = APP / "data/runs" / a.run
    art_src = run_dir / "artifacts"
    if not art_src.is_dir():
        raise SystemExit(f"no artifacts at {art_src}")
    video = REPO / a.video
    if not video.is_file():
        raise SystemExit(f"no video at {video}")

    init_db()
    db = SessionLocal()
    try:
        existing = db.query(Project).filter(Project.name == a.name).first()
        if existing is not None:
            print(f"reusing project {existing.id} ({a.name})")
            p = existing
        else:
            p = Project(name=a.name, description=a.description, status="done")
            db.add(p)
            db.commit()
            db.refresh(p)

        art_dst = storage.artifacts_dir(p.id)
        art_dst.mkdir(parents=True, exist_ok=True)
        n = 0
        for f in sorted(art_src.iterdir()):
            if f.is_file():
                shutil.copy2(f, art_dst / f.name)
                n += 1

        up = storage.uploads_dir(p.id)
        up.mkdir(parents=True, exist_ok=True)
        dst_video = up / f"video{video.suffix}"
        if not dst_video.exists():
            shutil.copy2(video, dst_video)
        p.video_filename = dst_video.name
        p.status = "done"
        db.commit()

        # A stale cached frame would make a refinement match against whatever
        # video previously sat at this path.
        from drishti_recon.refinement import clear_detect_cache
        clear_detect_cache()

        print(f"project {p.id}\n  name      {p.name}\n  artifacts {n} files -> "
              f"{art_dst}\n  video     {dst_video}")
        print(f"  open      /projects/{p.id}")
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
