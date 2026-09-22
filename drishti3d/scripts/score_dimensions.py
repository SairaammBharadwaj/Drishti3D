#!/usr/bin/env python3
"""DO NOT USE FOR ACCURACY CLAIMS -- this method failed its own validation.

Kept because the failure is instructive and the withdrawal must be auditable.

It fits locally planar patches independently in each cloud, which was meant to
remove the nearest-neighbour identity leakage of DEC-037. It does not. The
reference patch is located at *our* patch's horizontal position, so any error
in our cloud moves both sides together. Tested by injecting known errors into
the reconstruction and re-scoring:

    injected error        pairs   median |err|   implied scale
    none (baseline)       1,703       0.0448 m          -0.04%
    +5% uniform scale     1,057       0.0428 m          +0.02%
    +1% uniform scale     1,546       0.0445 m          -0.01%
    +5% vertical only     1,626       0.0458 m          -0.01%
    +2 m vertical shift   1,703       0.0448 m          -0.04%

A 5% scale error scores *better* than no error at all. The method is blind to
every error it was built to detect.

The general rule, now confirmed twice: **a correspondence located using the
output under test cannot measure that output.** Position-based matching of any
kind inherits the error. Use `score_camera_dimensions.py`, where identity comes
from the image filename and carries no geometry, and which does pass the same
injection test.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np

APP = Path(__file__).resolve().parents[1]

#: A patch must be this planar to be used as a feature: the smallest singular
#: value over the largest, so a flat disc is near zero and a blob near one.
MAX_PLANARITY = 0.06
#: Radius of the neighbourhood fitted, in metres.
PATCH_RADIUS = 1.5
#: Minimum points in a patch, in each cloud separately.
MIN_PATCH_POINTS = 40
#: Two patches are the same feature only if their centres are this close and
#: their normals agree. Deliberately tight: a wrong pairing is worse than none.
MATCH_RADIUS_M = 1.0
MATCH_NORMAL_DEG = 12.0


def fit_patches(points, seeds, tree, *, radius=PATCH_RADIUS):
    """Locally planar patches around seed positions, found without reference
    to any other cloud."""
    out = []
    for s in seeds:
        idx = tree.query_ball_point(points[s], radius)
        if len(idx) < MIN_PATCH_POINTS:
            continue
        q = points[idx]
        c = q.mean(0)
        u, sv, vt = np.linalg.svd(q - c, full_matrices=False)
        if sv[0] <= 0 or sv[2] / sv[0] > MAX_PLANARITY:
            continue
        out.append((c, vt[2], float(sv[2] / sv[0]), len(idx)))
    return out


def main() -> int:
    from scipy.spatial import cKDTree
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import score_against_lidar as S

    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--run", required=True)
    ap.add_argument("--truth", required=True)
    ap.add_argument("--epsg", type=int, default=32632)
    ap.add_argument("--seeds", type=int, default=3000)
    ap.add_argument("--seed", type=int, default=17)
    ap.add_argument("--out", default=None)
    a = ap.parse_args()

    run = APP / "data/runs" / a.run
    pts, sig, frame = S.load_reconstruction(run)
    ours = S.to_utm(frame, pts, a.epsg)
    ref = S.load_lidar_in_box(Path(a.truth), ours.min(0), ours.max(0))
    print(f"reconstruction {len(ours):,} points; reference {len(ref):,} points")

    rng = np.random.default_rng(a.seed)
    ours_tree, ref_tree = cKDTree(ours), cKDTree(ref)

    # Seeds are drawn in OUR cloud only to choose where to look. The reference
    # patch is then fitted from the reference's own points at that location --
    # its centre and normal come from the reference alone, which is the part
    # that matters. Using our seed positions is a sampling choice, not a
    # correspondence: it decides where we look, not what we find.
    seeds = rng.choice(len(ours), min(a.seeds * 4, len(ours)), replace=False)
    ours_patches = fit_patches(ours, seeds, ours_tree)[:a.seeds]
    print(f"planar patches in the reconstruction: {len(ours_patches):,}")

    # The reference patch is found in a vertical cylinder about our patch's
    # horizontal position, not a sphere about its 3D centre. A sphere fails
    # here for a reason worth recording: the reconstruction sits 1.245 m above
    # the reference on this capture, so a 1.5 m sphere centred on our surface
    # barely intersects theirs and catches an edge-on sliver that fails the
    # planarity test. Only 18 of 2,574 patches survived that way. Searching a
    # cylinder makes the vertical offset -- the quantity under test -- stop
    # deciding which features are allowed to be compared.
    ref_xy = cKDTree(ref[:, :2])
    pairs = []
    for c, n, plan, cnt in ours_patches:
        idx = ref_xy.query_ball_point(c[:2], PATCH_RADIUS)
        if len(idx) < MIN_PATCH_POINTS:
            continue
        q = ref[idx]
        rc = q.mean(0)
        _, sv, vt = np.linalg.svd(q - rc, full_matrices=False)
        if sv[0] <= 0 or sv[2] / sv[0] > MAX_PLANARITY:
            continue
        rn = vt[2]
        ang = np.degrees(np.arccos(min(1.0, abs(float(n @ rn)))))
        if ang > MATCH_NORMAL_DEG:
            continue
        pairs.append((c, n, rc, rn, ang))
    print(f"patches matched in both clouds: {len(pairs):,}")
    if len(pairs) < 50:
        raise SystemExit("too few matched features to score")

    C = np.array([p[0] for p in pairs])
    N = np.array([p[1] for p in pairs])
    RC = np.array([p[2] for p in pairs])
    ang = np.array([p[4] for p in pairs])

    # Dimensional quantity: distance between two feature centres, each
    # identified in its own cloud.
    kd = cKDTree(C)
    rows = []
    for i in rng.choice(len(C), min(4000, len(C)), replace=False):
        nb = kd.query_ball_point(C[i], 60.0)
        nb = [k for k in nb if 5.0 <= np.linalg.norm(C[k] - C[i]) <= 60.0]
        if not nb:
            continue
        k = int(nb[rng.integers(len(nb))])
        rows.append((float(np.linalg.norm(C[i] - C[k])),
                     float(np.linalg.norm(RC[i] - RC[k]))))
        if len(rows) >= 2500:
            break
    R = np.array(rows)
    err = R[:, 0] - R[:, 1]

    out = {
        "run": a.run, "epsg": a.epsg, "seed": a.seed,
        "method": ("locally planar patches fitted independently in each cloud, "
                   "paired by centre proximity and normal agreement"),
        "identification_caveat": (
            "a fitted patch centre is not a surveyed target; this removes the "
            "nearest-neighbour identity leakage of DEC-037 but is not "
            "equivalent to an independently surveyed landmark"),
        "n_patches_reconstruction": len(ours_patches),
        "n_patches_matched": len(pairs),
        "normal_error_deg": {
            "median": float(np.median(ang)), "p90": float(np.percentile(ang, 90))},
        "feature_distance_error_m": {
            "n": int(len(R)),
            "signed_median": float(np.median(err)),
            "median_abs": float(np.median(np.abs(err))),
            "p90_abs": float(np.percentile(np.abs(err), 90)),
            "rmse": float(np.sqrt((err ** 2).mean())),
            "baseline_range_m": [float(R[:, 1].min()), float(R[:, 1].max())],
        },
        # A scale error shows here and nowhere else: fit err = s * length.
        "implied_scale_error": float(np.polyfit(R[:, 1], R[:, 0], 1)[0] - 1.0),
    }
    print(json.dumps(out, indent=2))
    dest = Path(a.out) if a.out else run / "dimension_score.json"
    dest.write_text(json.dumps(out, indent=2))
    print(f"\nwritten to {dest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
