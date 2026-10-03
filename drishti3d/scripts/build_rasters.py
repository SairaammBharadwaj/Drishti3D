#!/usr/bin/env python3
"""Build the raster products for missions that were reconstructed before them.

New runs get DSM, DTM, orthophoto, sigma and land cover from the pipeline
(``drishti_recon.rasters``). This makes the same files from a finished
mission's saved artifacts, so existing missions gain them without a
reconstruction rerun. It reads ``cloud.npz``, ``trajectory.json`` (the ENU
frame) and ``georeference.json`` (whether the pipeline judged the cloud
georeferenced), and writes only new files. The artifacts that stored answers
are checked against (``storage.artifact_revision``) are never touched.

A mission that is not georeferenced is skipped: its "metres" are
reconstruction units and it has no place on the earth to rasterise into.

Usage (from the drishti3d directory):
  .venv/bin/python scripts/build_rasters.py --project 288ca0888eee49f8b64446e5ffe6d6d0
  .venv/bin/python scripts/build_rasters.py --all
  .venv/bin/python scripts/build_rasters.py --all --las    # also rewrite LAS with classes
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import numpy as np

APP = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(APP / "reconstruction"))

from drishti_recon import exports, rasters                  # noqa: E402
from drishti_recon.geo import ENUFrame                      # noqa: E402


class _Cloud:
    """The fields export_las reads, from cloud.npz."""

    def __init__(self, d):
        self.points = d["points"]
        self.colors = d["colors"]
        self.confidence = d["confidence"]
        self.provenance = d["provenance"]
        self.sigma = d["sigma"] if "sigma" in d.files else None
        self.sigma_major = d["sigma_major"] if "sigma_major" in d.files else None


def build(art: Path, *, las: bool, res: float | None, max_window_m: float) -> dict:
    geo = json.loads((art / "georeference.json").read_text())
    if not geo.get("georeferenced"):
        return {"skipped": "not georeferenced (relative scale)"}
    frame = ENUFrame(**json.loads((art / "trajectory.json").read_text())["frame"])
    cloud = _Cloud(np.load(art / "cloud.npz"))
    sigma = cloud.sigma_major if cloud.sigma_major is not None else cloud.sigma
    t0 = time.time()
    utm, epsg = exports.enu_to_utm(frame, cloud.points)
    out = rasters.build_products(utm, cloud.colors, sigma, cloud.provenance, epsg, art,
                                 res=res, max_window_m=max_window_m)
    if las:
        exports.export_las(art / "point_cloud.las", cloud, frame,
                           classification=out["point_classes"])
    s = out["summary"]
    return {"seconds": round(time.time() - t0, 1), "cell_size_m": s["cell_size_m"],
            "footprint_coverage": s["footprint_coverage"], "crs": s["crs"],
            "class_shares": {k: round(v, 3) for k, v in s["class_shares"].items()},
            "files": sorted(Path(p).name for p in out["artifacts"].values())}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--data", type=Path, default=APP / "data")
    ap.add_argument("--project", action="append", default=[])
    ap.add_argument("--all", action="store_true", help="every finished project")
    ap.add_argument("--las", action="store_true",
                    help="also rewrite point_cloud.las with ASPRS classes")
    ap.add_argument("--res", type=float, default=None,
                    help="cell size in metres (default: chosen from the data)")
    ap.add_argument("--max-window", type=float, default=40.0,
                    help="largest ground-filter window, metres (default 40)")
    args = ap.parse_args()

    projects = args.data / "projects"
    ids = args.project or (sorted(p.name for p in projects.iterdir()
                                  if (p / "artifacts" / "cloud.npz").is_file())
                           if args.all else [])
    if not ids:
        ap.error("give --project ID or --all")
    for pid in ids:
        art = projects / pid / "artifacts"
        try:
            result = build(art, las=args.las, res=args.res, max_window_m=args.max_window)
        except Exception as exc:                 # report and carry on with the rest
            result = {"error": f"{type(exc).__name__}: {exc}"}
        print(pid[:8], json.dumps(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
