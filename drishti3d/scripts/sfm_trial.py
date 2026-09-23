#!/usr/bin/env python3
"""Time COLMAP SfM on a saved run's keyframes with a given thread count.

Screening for the performance plan: the same 80 images, the same initial
intrinsics, only ``num_threads`` changes. Reports substage timings and the
camera solution, so a speedup that loses cameras is visible.

    .venv/bin/python scripts/sfm_trial.py --run dji_1003__t10 --threads 12
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import cv2
import numpy as np

APP = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(APP / "reconstruction"))


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--run", required=True)
    ap.add_argument("--threads", type=int, required=True)
    ap.add_argument("--gpu-matching", action="store_true")
    ap.add_argument("--focal", type=float, default=None,
                    help="initial focal in px (default 0.9 x max(w, h), refined)")
    a = ap.parse_args()
    from drishti_recon import colmap_adapter

    img_dir = APP / "data/runs" / a.run / "colmap_workspace/images"
    frames = [cv2.imread(str(p)) for p in sorted(img_dir.glob("*.jpg"))]
    h, w = frames[0].shape[:2]
    f = a.focal or 0.9 * max(w, h)
    K = np.array([[f, 0, w / 2], [0, f, h / 2], [0, 0, 1.0]])
    t0 = time.perf_counter()
    rec = colmap_adapter.reconstruct_frames(frames, K, fix_intrinsics=False,
                                            num_threads=a.threads,
                                            gpu_matching=a.gpu_matching)
    wall = time.perf_counter() - t0
    st = rec.stats
    out = {"run": a.run, "threads": a.threads, "gpu_matching": a.gpu_matching,
           "wall_s": round(wall, 1),
           "timings_s": st.get("timings_s"), "n_registered": st["n_registered"],
           "n_keyframes": st["n_keyframes"], "n_points": st["n_points"],
           "median_reproj_err": st["median_reproj_err"],
           "focal_px": float(rec.K[0, 0])}
    dest = APP / "data/perf" / a.run / (f"sfm_t{a.threads}"
                                        + ("_gpu" if a.gpu_matching else "") + ".json")
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps(out, indent=2))
    print(json.dumps(out, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
