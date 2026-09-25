#!/usr/bin/env python3
"""Horizontal placement of a run against a LiDAR, from sloped surfaces.

Cloud-to-cloud nearest distance reads a 1 m horizontal shift as 2.5 cm
(TESTS_AND_RESULTS 2026-09-25), and the vertical height-map scorer is blind to
horizontal position by construction. On a *slope*, though, a horizontal shift
changes the distance to the surface. This fits one horizontal translation
(dE, dN), plus a vertical one so height bias cannot leak into it, minimising
point-to-plane distance to LiDAR surfaces whose normals are at least
``--min-slope`` degrees from vertical.

It measures global horizontal placement, not per-point horizontal error.
``--inject`` shifts the cloud by known amounts and reports what is recovered,
so the metric re-validates itself on every run.

Usage:
  python scripts/score_horizontal_offset.py --run mars_hkisland03_sp__first \\
      --truth ../datasets/truth/mars_hkisland03_sp/reference_lidar.las --epsg 32650
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np

APP = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(APP / "scripts"))


def lidar_normals(ref, k=16):
    from scipy.spatial import cKDTree
    tree = cKDTree(ref)
    _, nn = tree.query(ref, k=k, workers=4)
    nb = ref[nn] - ref[nn].mean(1, keepdims=True)
    cov = np.einsum("nki,nkj->nij", nb, nb) / k
    w, v = np.linalg.eigh(cov)
    normals = v[:, :, 0]                          # smallest eigenvalue
    planarity = (w[:, 1] - w[:, 0]) / np.maximum(w[:, 2], 1e-12)
    return tree, normals, planarity


def fit_translation(pts, ref, tree, normals, sloped, iters=40, max_d=3.0):
    """Translation t minimising sum((n . (p + t - q))^2) over sloped matches.

    Coarse to fine: the robust (Huber) scale starts at 1 m, so a large offset's
    residuals are not rejected as outliers before the fit has moved, and
    tightens to 0.2 m once it has. A fixed 0.2 m scale recovered only 70-82% of
    injected 0.5-1 m shifts.
    """
    t = np.zeros(3)
    use = np.zeros(0, bool)
    for it in range(iters):
        scale = max(0.2, 1.0 * (0.85 ** it))
        d, i = tree.query(pts + t, workers=4)
        use = (d < max_d) & sloped[i]
        if use.sum() < 200:
            return None, 0
        n = normals[i[use]]
        r = np.einsum("ij,ij->i", n, (pts[use] + t) - ref[i[use]])
        w = np.where(np.abs(r) < scale, 1.0, scale / np.abs(r))
        dt, *_ = np.linalg.lstsq(n * w[:, None], -r * w, rcond=None)
        t = t + dt
        if np.linalg.norm(dt) < 1e-4 and scale <= 0.2:
            break
    return t, int(use.sum())


def main() -> int:
    import score_against_lidar as sal

    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--run", required=True)
    ap.add_argument("--truth", required=True)
    ap.add_argument("--epsg", type=int, required=True)
    ap.add_argument("--min-slope", type=float, default=25.0,
                    help="LiDAR surfaces whose normal is at least this far from vertical")
    ap.add_argument("--sample", type=int, default=150_000)
    ap.add_argument("--inject", type=float, nargs="*", default=[1.0, 0.5])
    ap.add_argument("--out", default=None)
    a = ap.parse_args()

    pts, _s, frame = sal.load_reconstruction(APP / "data/runs" / a.run)
    ours = sal.to_utm(frame, pts, a.epsg)
    ref = sal.load_lidar_in_box(Path(a.truth), ours.min(0) - 5, ours.max(0) + 5)
    rng = np.random.default_rng(0)
    if len(ref) > 3_000_000:
        ref = ref[rng.choice(len(ref), 3_000_000, replace=False)]
    tree, normals, planarity = lidar_normals(ref)
    tilt = np.degrees(np.arccos(np.clip(np.abs(normals[:, 2]), 0, 1)))
    sloped = (tilt >= a.min_slope) & (planarity > 0.3)
    sub = ours[rng.choice(len(ours), min(len(ours), a.sample), replace=False)]

    t, n_used = fit_translation(sub, ref, tree, normals, sloped)
    if t is None:
        print("too few sloped matches"); return 1
    # Reported as the reconstruction's offset from the reference: -correction.
    off = -t
    res = {"run": a.run, "min_slope_deg": a.min_slope, "sloped_lidar_fraction": float(sloped.mean()),
           "n_matches": n_used, "offset_east_m": float(off[0]), "offset_north_m": float(off[1]),
           "offset_up_m": float(off[2]), "offset_horizontal_m": float(np.hypot(off[0], off[1])),
           "injection": {}}
    for s in a.inject:
        for axis, name in ((0, "east"), (1, "north")):
            sh = np.zeros(3); sh[axis] = s
            ti, _ = fit_translation(sub + sh, ref, tree, normals, sloped)
            got = float(-ti[axis] - off[axis]) if ti is not None else None
            res["injection"][f"{name}{s:+.2f}"] = None if got is None else round(got, 3)
    print(json.dumps(res, indent=2))
    bad = {k: v for k, v in res["injection"].items()
           if v is None or abs(v - float(k.lstrip("eastnorth"))) > 0.1}
    if bad:
        print(f"WARNING: injected shifts not recovered within 10 cm: {bad}")
    if a.out:
        Path(a.out).write_text(json.dumps(res, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
