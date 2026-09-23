#!/usr/bin/env python3
"""Score a reconstruction's dense cloud against an independent LiDAR surface.

This is the first reference available to this project that was not produced by
photogrammetry. Every accuracy number recorded so far has been against either
the authors' own photogrammetric poses (AGZ's Pix4D reference) or the
reconstruction's own internal estimates, and neither can tell us whether a
reported uncertainty is honest. A RIEGL miniVUX-3UAV cloud can.

Three things are measured, and they answer different questions:

* **Accuracy** -- distance from each reconstructed point to the nearest LiDAR
  point. This is one-sided: a reconstruction that produces a tiny patch of
  perfect geometry scores perfectly here.
* **Completeness** -- distance from each LiDAR point to the nearest
  reconstructed point, inside the region we actually covered. This is what
  catches the tiny-perfect-patch case.
* **Interval coverage** -- how often the true error falls inside the interval
  the system claimed for that point. This is the number
  [DEC-031](../../DECISIONS.md) has never been checked against, and the only
  one that says whether the uncertainty model is calibrated or merely plausible.

The comparison is done in the dataset's own projected CRS rather than in ENU,
because the LiDAR is published in that frame and reprojecting the reference
would put our own transform inside the thing being used to check us.

Usage:
  python scripts/score_against_lidar.py --run usegeo_1__first \
      --truth ../datasets/truth/usegeo_1/reference_lidar.las --epsg 32632
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parents[2]
APP = Path(__file__).resolve().parents[1]

#: Beyond this, a "nearest LiDAR point" is not the same surface and the
#: distance measures absence rather than error. Reported separately as
#: unmatched rather than folded into the error distribution.
MAX_MATCH_M = 5.0


def load_reconstruction(run_dir: Path):
    import sys
    sys.path.insert(0, str(APP / "reconstruction"))
    from drishti_recon.geo import ENUFrame

    art = run_dir / "artifacts"
    cloud = np.load(art / "cloud.npz")
    traj = json.loads((art / "trajectory.json").read_text())
    f = traj["frame"]
    return (cloud["points"], cloud.get("sigma_major"),
            ENUFrame(f["lat0"], f["lon0"], f["alt0"]))


def to_utm(frame, points_enu, epsg: int) -> np.ndarray:
    import pyproj
    geo = frame.enu_to_geodetic(np.asarray(points_enu, float))
    tr = pyproj.Transformer.from_crs("EPSG:4326", f"EPSG:{epsg}",
                                     always_xy=True)
    x, y = tr.transform(geo[:, 1], geo[:, 0])
    return np.column_stack([x, y, geo[:, 2]])


def load_lidar_in_box(path: Path, lo: np.ndarray, hi: np.ndarray,
                      *, pad: float = 20.0) -> np.ndarray:
    """LiDAR points inside our own bounding box, read in chunks.

    The full cloud is 105.9 M points; cropping while reading keeps this to the
    part that could possibly match and makes a KD-tree affordable.
    """
    import laspy
    lo, hi = lo - pad, hi + pad
    keep = []
    with laspy.open(str(path)) as fh:
        for chunk in fh.chunk_iterator(5_000_000):
            p = np.column_stack([np.asarray(chunk.x), np.asarray(chunk.y),
                                 np.asarray(chunk.z)])
            m = np.all((p >= lo) & (p <= hi), axis=1)
            if m.any():
                keep.append(p[m])
    if not keep:
        raise SystemExit("no LiDAR points inside the reconstruction's extent; "
                         "check --epsg and that these are the same site")
    return np.vstack(keep)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--run", required=True, help="directory under data/runs/")
    ap.add_argument("--truth", required=True, help="reference .las")
    ap.add_argument("--epsg", type=int, default=32632)
    ap.add_argument("--sample", type=int, default=200_000,
                    help="reconstructed points to score (0 = all)")
    ap.add_argument("--out", default=None, help="write JSON here")
    a = ap.parse_args()

    from scipy.spatial import cKDTree

    run_dir = APP / "data/runs" / a.run
    pts_enu, sigma, frame = load_reconstruction(run_dir)
    print(f"reconstruction: {len(pts_enu):,} points")

    ours = to_utm(frame, pts_enu, a.epsg)
    lo, hi = ours.min(0), ours.max(0)
    print(f"extent (EPSG:{a.epsg}) "
          f"E {lo[0]:.0f}..{hi[0]:.0f}  N {lo[1]:.0f}..{hi[1]:.0f}  "
          f"Z {lo[2]:.0f}..{hi[2]:.0f}")

    ref = load_lidar_in_box(Path(a.truth), lo, hi)
    print(f"reference: {len(ref):,} LiDAR points in that extent")

    rng = np.random.default_rng(0)
    idx = np.arange(len(ours))
    if a.sample and len(ours) > a.sample:
        idx = rng.choice(len(ours), a.sample, replace=False)

    ref_tree = cKDTree(ref)
    d_acc, _ = ref_tree.query(ours[idx])
    matched = d_acc <= MAX_MATCH_M

    # Completeness, inside our own footprint only. The first version of this
    # sampled the whole cropped box, which includes ground a 60-frame subset
    # never flew over -- it reported a 24 m mean and was measuring the flight
    # plan, not the reconstruction. Restricting to the horizontal convex hull
    # of what we produced asks the question that was intended: where we did
    # reconstruct, how much of the surface did we capture.
    from scipy.spatial import Delaunay
    hull = Delaunay(ours[rng.choice(len(ours), min(len(ours), 50_000),
                                    replace=False), :2])
    ref_idx = rng.choice(len(ref), min(len(ref), a.sample or len(ref)),
                         replace=False)
    inside = hull.find_simplex(ref[ref_idx][:, :2]) >= 0
    ref_idx = ref_idx[inside]
    our_tree = cKDTree(ours)
    d_comp, _ = our_tree.query(ref[ref_idx])

    # The bias is reported before anything is removed. On the first UseGeo run
    # the raw error was 1.36 m and almost all of it was one vertical offset;
    # quoting only the offset-removed figure would have hidden the finding,
    # which is the same mistake DEC-024 found in `as_georeferenced`.
    def stats(d):
        return {"n": int(len(d)), "median_m": float(np.median(d)),
                "mean_m": float(d.mean()),
                "p90_m": float(np.percentile(d, 90)),
                "p95_m": float(np.percentile(d, 95)),
                "p99_m": float(np.percentile(d, 99)),
                "rmse_m": float(np.sqrt((d ** 2).mean()))}

    _, nn = ref_tree.query(ours[idx])
    delta = ours[idx] - ref[nn]
    bias = np.median(delta[matched], axis=0)
    debiased = ours[idx][matched] - bias
    d_deb, _ = ref_tree.query(debiased)

    out = {
        "run": a.run, "epsg": a.epsg,
        "n_reconstructed": int(len(ours)),
        "n_reference_in_extent": int(len(ref)),
        "accuracy_recon_to_lidar": stats(d_acc[matched]),
        "unmatched_fraction": float((~matched).mean()),
        "unmatched_note": (f"points further than {MAX_MATCH_M} m from any "
                           "LiDAR return; excluded from the error "
                           "distribution because they measure absence, not "
                           "error"),
        "completeness_lidar_to_recon": stats(d_comp),
        "completeness_note": ("reference points inside the horizontal convex "
                              "hull of the reconstruction only; outside it a "
                              "distance measures where we did not fly"),
        "systematic_offset_m": {
            "east": float(bias[0]), "north": float(bias[1]), "up": float(bias[2]),
            "note": ("median signed offset of the reconstruction from the "
                     "reference; a planar flight leaves the vertical weakly "
                     "constrained and this is where that shows"),
        },
        "accuracy_after_removing_offset": stats(d_deb),
        "completeness_within_0_25m": float((d_comp <= 0.25).mean()),
        "completeness_within_0_50m": float((d_comp <= 0.50).mean()),
    }

    # The claim under test: does the reported interval contain the truth as
    # often as it says? 1.96 sigma is the uncalibrated 95% sensitivity band.
    if sigma is not None:
        s = np.asarray(sigma, float)[idx][matched]
        e = d_acc[matched]
        fin = np.isfinite(s)
        if fin.any():
            out["interval_check"] = {
                "n": int(fin.sum()),
                "median_predicted_sigma_m": float(np.median(s[fin])),
                "median_actual_error_m": float(np.median(e[fin])),
                "ratio_actual_over_predicted": float(
                    np.median(e[fin]) / max(np.median(s[fin]), 1e-9)),
                "coverage_at_1_96_sigma": float((e[fin] <= 1.96 * s[fin]).mean()),
                "note": ("nominal coverage is 0.95; this is one-sided "
                         "point-to-surface distance, not a signed dimensional "
                         "error, so it is a first check and not a calibration"),
            }

    print(json.dumps(out, indent=2))
    dest = Path(a.out) if a.out else run_dir / "lidar_score.json"
    dest.write_text(json.dumps(out, indent=2))
    print(f"\nwritten to {dest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
