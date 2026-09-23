#!/usr/bin/env python3
"""Fill the holes in a finished project's cloud (water, untextured ground).

Writes ``artifacts/fill.npz`` (points, colours, hole ids) and
``artifacts/fill.json`` (per-hole record) beside the cloud. The cloud itself is
not touched: fill points are inferred, not observed, and are kept out of every
measurement by living in a separate file. See ``drishti_recon.holefill``.

    .venv/bin/python scripts/fill_holes.py data/projects/<id>
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "reconstruction"))
from drishti_recon import holefill  # noqa: E402


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("project_dir", type=Path)
    ap.add_argument("--cell", type=float, default=None,
                    help="grid cell in metres (default: from point density)")
    ap.add_argument("--no-color", action="store_true",
                    help="skip sampling colours from the video")
    a = ap.parse_args()

    art = a.project_dir / "artifacts"
    traj = json.loads((art / "trajectory.json").read_text())
    cloud = np.load(art / "cloud.npz")
    cams, K, size = traj["cameras_enu"], np.array(traj["K"]), traj["image_size"]

    t0 = time.time()
    res = holefill.fill_holes(cloud["points"], cams, K, size, cell=a.cell)
    t_fill = time.time() - t0

    colors = np.tile(np.array([90, 110, 125], np.uint8), (len(res.points), 1))
    video = next((a.project_dir / "uploads").glob("video.*"), None)
    if len(res.points) and video is not None and not a.no_color:
        import cv2
        cap = cv2.VideoCapture(str(video))

        def get_image(i):
            cap.set(cv2.CAP_PROP_POS_FRAMES, int(cams[i]["frame_index"]))
            ok, img = cap.read()
            if not ok:
                return None
            return cv2.resize(img, tuple(size), interpolation=cv2.INTER_AREA)

        colors = holefill.colorize(res.points, cams, K, size, get_image)
        cap.release()

    np.savez_compressed(art / "fill.npz", points=res.points.astype(np.float32),
                        colors=colors, hole_id=res.hole_id)
    summary = res.summary()
    summary["seconds"] = round(time.time() - t0, 1)
    summary["seconds_geometry"] = round(t_fill, 1)
    (art / "fill.json").write_text(json.dumps(summary, indent=2))
    top = summary["holes"][:5]
    print(json.dumps({k: v for k, v in summary.items() if k != "holes"}, indent=2))
    for h in top:
        print(h)


if __name__ == "__main__":
    main()
