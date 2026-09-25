#!/usr/bin/env python3
"""Signed vertical error of a run against flat cells of a LiDAR height map.

Cloud-to-cloud nearest-point distance (``score_against_lidar.py``) slides along
surfaces: injected into a real MARS-LVIG cloud, a +0.30 m vertical shift read as
+0.05 m and a +1 m horizontal shift as +0.025 m (TESTS_AND_RESULTS 2026-09-25).
This compares heights at the same horizontal position instead.

The LiDAR is binned into ``--cell`` metre cells. Only cells with at least
``--min-returns`` returns and height std under ``--max-std`` are used -- flat,
unambiguous ground and roofs, where a height has one meaning. Each
reconstructed point in such a cell gets dZ = z - cell mean.

``--inject`` adds known vertical shifts and reports how much of each is
recovered, so every run re-checks the metric instead of trusting it once.
Validated: +0.30 / +1.00 / -0.10 m recovered as +0.300 / +0.998 / -0.100 m.

Horizontal error is not measured here.

Usage:
  python scripts/score_vertical_dsm.py --run mars_hkisland03_win__budget \\
      --truth ../datasets/truth/mars_hkisland03_win/reference_lidar.las --epsg 32650
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np

APP = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(APP / "scripts"))


def main() -> int:
    import score_against_lidar as sal

    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--run", required=True)
    ap.add_argument("--truth", required=True)
    ap.add_argument("--epsg", type=int, required=True)
    ap.add_argument("--cell", type=float, default=0.5)
    ap.add_argument("--max-std", type=float, default=0.05)
    ap.add_argument("--min-returns", type=int, default=4)
    ap.add_argument("--inject", type=float, nargs="*", default=[0.30, 1.00, -0.10])
    ap.add_argument("--crop-to-run", default=None,
                    help="score only points inside this other run's horizontal "
                         "footprint (convex hull), for like-for-like comparisons")
    ap.add_argument("--out", default=None)
    a = ap.parse_args()

    pts, _sig, frame = sal.load_reconstruction(APP / "data/runs" / a.run)
    ours = sal.to_utm(frame, pts, a.epsg)
    if a.crop_to_run:
        from scipy.spatial import Delaunay
        cp, _s, cf = sal.load_reconstruction(APP / "data/runs" / a.crop_to_run)
        other = sal.to_utm(cf, cp, a.epsg)
        rng = np.random.default_rng(0)
        hull = Delaunay(other[rng.choice(len(other), min(len(other), 50_000),
                                         replace=False), :2])
        ours = ours[hull.find_simplex(ours[:, :2]) >= 0]
    ref = sal.load_lidar_in_box(Path(a.truth), ours.min(0) - 5, ours.max(0) + 5)

    def key(xy):
        ij = np.floor(xy / a.cell).astype(np.int64)
        return ij[:, 0] * 10_000_000 + ij[:, 1]

    k = key(ref[:, :2])
    order = np.argsort(k)
    k, z = k[order], ref[order, 2]
    cells, start, count = np.unique(k, return_index=True, return_counts=True)
    s = np.add.reduceat(z, start)
    s2 = np.add.reduceat(z * z, start)
    mean = s / count
    std = np.sqrt(np.maximum(s2 / count - mean ** 2, 0))
    flat = (std < a.max_std) & (count >= a.min_returns)

    def dz_of(p):
        kk = key(p[:, :2])
        pos = np.searchsorted(cells, kk)
        pos = np.clip(pos, 0, len(cells) - 1)
        ok = (cells[pos] == kk) & flat[pos]
        dz = p[ok, 2] - mean[pos[ok]]
        return dz[np.abs(dz) < 5.0]

    dz = dz_of(ours)
    ad = np.abs(dz)
    res = {
        "run": a.run, "cropped_to": a.crop_to_run, "cell_m": a.cell, "flat_cells": int(flat.sum()),
        "n_points": int(len(dz)),
        "bias_median_dz_m": float(np.median(dz)),
        "rmse_dz_m": float(np.sqrt(np.mean(dz ** 2))),
        "abs_dz_p50_m": float(np.percentile(ad, 50)),
        "abs_dz_p90_m": float(np.percentile(ad, 90)),
        "abs_dz_p99_m": float(np.percentile(ad, 99)),
        "injection": {},
    }
    for sh in a.inject:
        got = float(np.median(dz_of(ours + [0.0, 0.0, sh]))) - res["bias_median_dz_m"]
        res["injection"][f"{sh:+.2f}"] = round(got, 4)
    print(json.dumps(res, indent=2))
    bad = {k_: v for k_, v in res["injection"].items() if abs(v - float(k_)) > 0.02}
    if bad:
        print(f"WARNING: injected shifts not recovered within 2 cm: {bad}")
    if a.out:
        Path(a.out).write_text(json.dumps(res, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
