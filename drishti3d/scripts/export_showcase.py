#!/usr/bin/env python3
"""Export finished missions as a bundle for a read-only public showcase.

The whole data directory is ~74 GB: source videos, intermediate runs, and every
mission ever processed. A showcase needs a few finished missions, and of those
only what viewing and measuring read -- the cloud, its observation lineage and
coverage, the trajectory, the reports. This writes exactly that to a new data
directory, which the backend serves with ``DRISHTI_READ_ONLY=1``.

What goes in, per mission:

* every top-level artifact file except the bulky downloads (PLY, LAS, mesh),
  which ``--with-exports`` adds (~0.9 GB for the default set);
* the mission's database rows -- project, jobs, questions, measurements and
  refinement runs -- and nobody else's.

What does not: source videos and telemetry (``uploads/``), so the showcase
cannot replay footage or run refinement, which re-reads frames.

Artifact files are copied with their modification times, because the artifact
revision that stored answers are checked against is built from sizes and times
(``storage.artifact_revision``); ``showcase.json`` records both so the server
can put the times back after an upload resets them (``backend/app/showcase``).
Reports that embed this machine's paths have them replaced. The files that
make up the revision are never rewritten; if one of them embeds a path, the
export says so and leaves it.

Every mission needs a credit for its source: most are third-party datasets
whose licences require attribution on a public page (MODEL_LICENSE_MANIFEST.md).

Usage (from the drishti3d directory):
  .venv/bin/python scripts/export_showcase.py --out data/showcase --dry-run
  .venv/bin/python scripts/export_showcase.py --out data/showcase
  .venv/bin/python scripts/export_showcase.py --out data/showcase --replace \\
      --project 288ca0888eee49f8b64446e5ffe6d6d0:mars_lvig

Serve it:
  DRISHTI_READ_ONLY=1 DRISHTI_DATA_DIR=data/showcase \\
      .venv/bin/uvicorn backend.app.main:app --port 8001
"""
from __future__ import annotations

import argparse
import json
import shutil
import sqlite3
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

APP = Path(__file__).resolve().parents[1]           # drishti3d/
WORKSPACE = APP.parent                               # the checkout
sys.path.insert(0, str(APP / "backend"))

from app import showcase                              # noqa: E402
from app.storage import _REVISION_FILES               # noqa: E402

#: What each source requires on a public page. Licences are from
#: MODEL_LICENSE_MANIFEST.md; AGZ's terms are in AGZ_subset/readme.txt.
CREDITS = {
    "mars_lvig": "Hong Kong flights: MARS-LVIG dataset, MaRS Lab, The "
                 "University of Hong Kong (CC BY-NC-SA 4.0).",
    "usegeo": "UseGeo 1: UseGeo dataset, 3DOM, Fondazione Bruno Kessler "
              "(CC BY-NC-SA 4.0).",
    "airlock": "Austin DJI videos: AirLock-WACV2026 dataset (CC BY 4.0).",
    "agz": "AGZ: Zurich Urban Micro Aerial Vehicle dataset, A. L. Majdik, "
           "Y. Albers-Schoenberg and D. Scaramuzza, ETH Zurich (academic "
           "research use).",
}

#: The default set: the LiDAR-scored flights first, then the long native-video
#: passes and a dense MVS run on a third source.
#:
#: St Lambertus (6deda6c8...) is deliberately absent. It was cut from a
#: Wikimedia Commons video whose licence and author were never recorded
#: (WORK_LOG 2026-09-06), so there is no credit to publish it under. Record
#: them in the licence manifest, add a key above, and pass it with --project.
DEFAULT_MISSIONS = [
    ("288ca0888eee49f8b64446e5ffe6d6d0", "mars_lvig"),   # HKisland03 single pass
    ("a9fb1f4b3bf843a18eaf60d0f6417217", "mars_lvig"),   # HKisland02 single pass
    ("0ebb0458077e44d6a8878113d5e35560", "usegeo"),      # UseGeo 1, calibration fixed
    ("051960beb15a4e1a8b851a8fa5bcc6e1", "airlock"),     # DJI_1003, the home-page scene
    ("0fe6744fad1740f4beac6a9f7d24a77f", "airlock"),     # DJI_1001, same settings
    ("c99c7e2f8a7449cd951308cb2628468e", "agz"),         # AGZ dense (MVS)
]

#: Downloads only; nothing the viewer or the measurement layer reads.
BULKY_EXPORTS = {"point_cloud.ply", "point_cloud.las", "mesh.glb"}
#: A mission without these cannot be opened in the workspace.
REQUIRED = {"viewer.json", "cloud.npz", "manifest.json", "trajectory.json",
            "quality_report.json"}
TEXT_SUFFIXES = {".json", ".html", ".geojson", ".csv"}


def fail(msg: str) -> None:
    sys.exit(f"export_showcase: {msg}")


def parse_missions(specs: list[str] | None) -> list[tuple[str, str]]:
    if not specs:
        return DEFAULT_MISSIONS
    out = []
    for spec in specs:
        pid, _, dataset = spec.partition(":")
        if dataset not in CREDITS:
            fail(f"--project {spec}: give the source as ID:DATASET, one of "
                 f"{sorted(CREDITS)} (add a credit to CREDITS for a new one)")
        out.append((pid, dataset))
    return out


def plan(data: Path, db: sqlite3.Connection, missions, with_exports: bool):
    """Per mission: its name and the artifact files to copy, checked."""
    out = []
    for pid, dataset in missions:
        row = db.execute("select name, status from projects where id = ?",
                         (pid,)).fetchone()
        if row is None:
            fail(f"no project {pid} in {data / 'drishti3d.db'}")
        name, status = row
        if status != "done":
            fail(f"{pid} ({name}) is '{status}', not a finished mission")
        art = data / "projects" / pid / "artifacts"
        files = sorted(f for f in art.iterdir() if f.is_file()
                       and (with_exports or f.name not in BULKY_EXPORTS))
        missing = REQUIRED - {f.name for f in files}
        if missing:
            fail(f"{pid} ({name}) lacks {sorted(missing)}")
        skipped = sorted(f.name for f in art.iterdir() if f.is_dir())
        if skipped:
            print(f"  note: {pid[:8]} subdirectories not exported: {skipped}")
        out.append({"id": pid, "name": name, "dataset": dataset,
                    "files": files})
    return out


def export_db(src: Path, dst: Path, ids: list[str]) -> None:
    """A copy of the database holding only the exported missions' rows."""
    s = sqlite3.connect(f"file:{src}?mode=ro", uri=True)
    d = sqlite3.connect(dst)
    try:
        s.backup(d)
        keep = ",".join("?" * len(ids))
        tables = [t for (t,) in d.execute(
            "select name from sqlite_master where type = 'table'")]
        for t in tables:
            cols = {c[1] for c in d.execute(f"pragma table_info({t})")}
            if "project_id" in cols:
                d.execute(f"delete from {t} where project_id not in ({keep})",
                          ids)
        d.execute(f"delete from projects where id not in ({keep})", ids)
        d.commit()
        d.execute("vacuum")
    finally:
        s.close()
        d.close()


def redact(text: str) -> str:
    return (text.replace(str(WORKSPACE), "<workspace>")
                .replace(str(Path.home()), "~"))


def copy_artifact(f: Path, dst: Path) -> None:
    shutil.copy2(f, dst)
    if f.suffix not in TEXT_SUFFIXES:
        return
    text = f.read_text(errors="surrogateescape")
    if redact(text) == text:
        return
    if f.name in _REVISION_FILES:
        # Rewriting it would change the artifact revision and mark every
        # stored answer superseded. Report it instead.
        print(f"  warning: {f.parent.parent.name[:8]}/{f.name} contains local "
              f"paths and is part of the artifact revision; left as is")
        return
    dst.write_text(redact(text), errors="surrogateescape")
    shutil.copystat(f, dst)


def code_version() -> str:
    try:
        rev = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=APP,
                             capture_output=True, text=True, check=True).stdout
        dirty = subprocess.run(["git", "status", "--porcelain", "--", "."],
                               cwd=APP / "backend", capture_output=True,
                               text=True).stdout
        return rev.strip() + ("+uncommitted-backend" if dirty.strip() else "")
    except (OSError, subprocess.CalledProcessError):
        return "unknown"


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--out", type=Path, required=True,
                    help="new data directory to write the bundle to")
    ap.add_argument("--data", type=Path, default=APP / "data",
                    help="data directory to export from (default: %(default)s)")
    ap.add_argument("--project", action="append", metavar="ID:DATASET",
                    help="export this mission instead of the default set; "
                         "repeatable")
    ap.add_argument("--with-exports", action="store_true",
                    help="also copy the PLY, LAS and mesh downloads")
    ap.add_argument("--replace", action="store_true",
                    help="overwrite --out if it holds an earlier bundle")
    ap.add_argument("--dry-run", action="store_true",
                    help="list what would be exported and stop")
    args = ap.parse_args()

    src_db = args.data / "drishti3d.db"
    if not src_db.is_file():
        fail(f"no database at {src_db}")
    missions = parse_missions(args.project)
    con = sqlite3.connect(f"file:{src_db}?mode=ro", uri=True)
    try:
        chosen = plan(args.data, con, missions, args.with_exports)
    finally:
        con.close()

    total = 0
    for m in chosen:
        size = sum(f.stat().st_size for f in m["files"])
        total += size
        print(f"  {m['id'][:8]}  {size / 1e6:7.0f} MB  {len(m['files']):2d} files"
              f"  [{m['dataset']}]  {m['name']}")
    print(f"  {'total':8s}  {total / 1e6:7.0f} MB")
    if args.dry_run:
        return

    out = args.out
    if out.exists() and any(out.iterdir()):
        if not args.replace:
            fail(f"{out} is not empty; pass --replace to overwrite a bundle")
        if not (out / showcase.MANIFEST).is_file():
            fail(f"{out} is not empty and holds no {showcase.MANIFEST}; "
                 f"refusing to delete something that is not a bundle")
        shutil.rmtree(out)
    out.mkdir(parents=True, exist_ok=True)

    export_db(src_db, out / "drishti3d.db", [m["id"] for m in chosen])
    projects = {}
    for m in chosen:
        dst = out / "projects" / m["id"] / "artifacts"
        dst.mkdir(parents=True)
        files = {}
        for f in m["files"]:
            copy_artifact(f, dst / f.name)
            st = (dst / f.name).stat()
            if f.name in _REVISION_FILES:
                src = f.stat()
                if (st.st_size, st.st_mtime_ns) != (src.st_size, src.st_mtime_ns):
                    fail(f"{m['id']}/{f.name}: copy does not match its source")
            files[f.name] = {"size": st.st_size, "mtime_ns": st.st_mtime_ns}
        projects[m["id"]] = {"name": m["name"], "dataset": m["dataset"],
                             "files": files}

    used = {m["dataset"] for m in chosen}
    manifest = {
        "format": showcase.FORMAT,
        "exported_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "code_version": code_version(),
        "credits": {k: v for k, v in CREDITS.items() if k in used},
        "projects": projects,
    }
    (out / showcase.MANIFEST).write_text(json.dumps(manifest, indent=2) + "\n")
    print(f"\nwrote {len(chosen)} missions to {out}\n\nserve it:\n"
          f"  DRISHTI_READ_ONLY=1 DRISHTI_DATA_DIR={out} "
          f".venv/bin/uvicorn backend.app.main:app --port 8001")


if __name__ == "__main__":
    main()
