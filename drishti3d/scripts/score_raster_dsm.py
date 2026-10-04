#!/usr/bin/env python3
"""Vertical accuracy of a mission's raster DSM against flat cells of a LiDAR.

Uses ``score_vertical_dsm.flat_cell_dz`` unchanged -- the metric validated by
injected shifts (TESTS_AND_RESULTS 2026-09-25) -- and scores three surfaces
of the same mission side by side:

* ``cloud``: the reconstructed points themselves. With the published
  correction this reproduces DEC-044's figures, which checks that the
  mission scored is the one those figures describe;
* ``dsm``: the highest observed point per cell (``dsm.tif``);
* ``zmean``: the mean height per cell.

Each raster cell is scored as one point at its centre, so the comparison says
what rasterising adds to the cloud's own error. ``--inject`` re-checks the
metric on the DSM itself.

Usage (from the drishti3d directory):
  .venv/bin/python scripts/score_raster_dsm.py --project 288ca0888eee49f8b64446e5ffe6d6d0 \\
      --truth ../datasets/truth/mars_hkisland03_sp/reference_lidar.las --z-correction 0.324
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np

APP = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(APP / "scripts"))
sys.path.insert(0, str(APP / "reconstruction"))

import score_against_lidar as sal                       # noqa: E402
from score_vertical_dsm import flat_cell_dz              # noqa: E402
from drishti_recon import exports                        # noqa: E402
from drishti_recon.geo import ENUFrame                   # noqa: E402


def stats(dz: np.ndarray) -> dict:
    ad = np.abs(dz)
    return {"n": int(len(dz)), "bias_median_m": round(float(np.median(dz)), 3),
            "rmse_m": round(float(np.sqrt(np.mean(dz ** 2))), 3),
            "abs_p50_m": round(float(np.percentile(ad, 50)), 3),
            "abs_p90_m": round(float(np.percentile(ad, 90)), 3),
            "abs_p99_m": round(float(np.percentile(ad, 99)), 3)}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--project", required=True)
    ap.add_argument("--truth", required=True)
    ap.add_argument("--data", type=Path, default=APP / "data")
    ap.add_argument("--z-correction", type=float, default=0.0,
                    help="subtracted from our heights, as in score_vertical_dsm.py")
    ap.add_argument("--cell", type=float, default=0.5)
    ap.add_argument("--max-std", type=float, default=0.05)
    ap.add_argument("--min-returns", type=int, default=4)
    ap.add_argument("--inject", type=float, nargs="*", default=[0.30, 1.00, -0.10])
    ap.add_argument("--out", default=None)
    a = ap.parse_args()

    art = a.data / "projects" / a.project / "artifacts"
    frame = ENUFrame(**json.loads((art / "trajectory.json").read_text())["frame"])
    cloud = np.load(art / "cloud.npz")
    obs = np.isin(cloud["provenance"], (0, 1))
    ours, epsg = exports.enu_to_utm(frame, cloud["points"][obs])
    ours[:, 2] -= a.z_correction

    r = np.load(art / "rasters.npz")
    if int(r["epsg"][0]) != epsg:
        raise SystemExit(f"raster CRS EPSG:{int(r['epsg'][0])} != cloud EPSG:{epsg}")
    x0, y1, res, h, w = r["grid"]
    X, Y = np.meshgrid(x0 + (np.arange(int(w)) + 0.5) * res,
                       y1 - (np.arange(int(h)) + 0.5) * res)

    def cells(grid):
        ok = np.isfinite(grid)
        return np.column_stack([X[ok], Y[ok], grid[ok] - a.z_correction])

    surfaces = {"cloud": ours, "dsm": cells(r["dsm"]), "zmean": cells(r["zmean"])}
    ref = sal.load_lidar_in_box(Path(a.truth), ours.min(0) - 5, ours.max(0) + 5)
    dz_of = flat_cell_dz(ours, ref, cell=a.cell, max_std=a.max_std,
                         min_returns=a.min_returns)

    out = {"project": a.project, "epsg": epsg, "raster_cell_m": float(res),
           "z_correction_m": a.z_correction, "flat_lidar_cells": dz_of.n_flat,
           "surfaces": {k: stats(dz_of(v)) for k, v in surfaces.items()},
           "injection_on_dsm": {}}
    base = out["surfaces"]["dsm"]["bias_median_m"]
    for sh in a.inject:
        got = float(np.median(dz_of(surfaces["dsm"] + [0.0, 0.0, sh]))) - base
        out["injection_on_dsm"][f"{sh:+.2f}"] = round(got, 4)
    print(json.dumps(out, indent=2))
    bad = {k: v for k, v in out["injection_on_dsm"].items() if abs(v - float(k)) > 0.02}
    if bad:
        print(f"WARNING: injected shifts not recovered within 2 cm: {bad}")
    if a.out:
        Path(a.out).write_text(json.dumps(out, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
