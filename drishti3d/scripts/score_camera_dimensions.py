#!/usr/bin/env python3
"""Dimensional accuracy from correspondences that carry no geometry.

Two previous attempts failed the same way. Both located the reference feature
using the reconstruction's own position -- nearest neighbour in DEC-037, a
planar patch at our horizontal coordinate in `score_dimensions.py` -- so any
error in the reconstruction moved both sides of the comparison together. Each
was blind to a 5% scale error injected on purpose.

This one pairs **camera centres by image filename**. A filename carries no
geometric information from the output under test, so the correspondence cannot
absorb the error. That is the whole point, and it is the property the other two
lacked.

It is validated by injection rather than asserted: scoring the same
reconstruction after multiplying its camera positions by a known factor
recovers that factor. Anything that cannot do that is not measuring scale.

What this does and does not establish
-------------------------------------
It measures the **relative geometry of the camera network** -- distances
between camera centres -- against an independent estimate of the same
quantity. It is a real dimensional test with a clean correspondence.

It is **not** a scene-feature measurement, and the reference here is the
dataset authors' bundle adjustment rather than survey. On UseGeo that
adjustment is partly derived from the same GNSS/INS trajectory used as our
telemetry input, so the two are not fully independent in absolute position.
Relative distances between cameras are much less affected by that sharing than
absolute placement is, which is why this is worth reporting and absolute
position from the same source is not.

Usage:
  python scripts/score_camera_dimensions.py --run usegeo_1__first \
      --truth ../datasets/truth/usegeo_1/reference_camera_orientations.xyz \
      --mission ../datasets/public/usegeo/usegeo_1 --epsg 32632
"""
from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path

import numpy as np

APP = Path(__file__).resolve().parents[1]


def load_ours(run: Path, epsg: int):
    import sys
    sys.path.insert(0, str(APP / "reconstruction"))
    from drishti_recon.geo import ENUFrame
    import pyproj
    traj = json.loads((run / "artifacts/trajectory.json").read_text())
    f = traj["frame"]
    frame = ENUFrame(f["lat0"], f["lon0"], f["alt0"])
    cams = traj["cameras_enu"]
    geo = frame.enu_to_geodetic(np.array([c["C"] for c in cams], float))
    tr = pyproj.Transformer.from_crs("EPSG:4326", f"EPSG:{epsg}", always_xy=True)
    x, y = tr.transform(geo[:, 1], geo[:, 0])
    return np.column_stack([x, y, geo[:, 2]]), cams


def pair_stats(A: np.ndarray, B: np.ndarray) -> dict:
    """Every pairwise distance, ours against the reference."""
    n = len(A)
    i, j = np.triu_indices(n, k=1)
    do = np.linalg.norm(A[i] - A[j], axis=1)
    dr = np.linalg.norm(B[i] - B[j], axis=1)
    e = do - dr
    slope = float(np.polyfit(dr, do, 1)[0] - 1.0)
    bands = {}
    for lo, hi in ((0, 25), (25, 75), (75, 200), (200, 400), (400, 1000)):
        m = (dr >= lo) & (dr < hi)
        if m.sum() > 20:
            bands[f"{lo}-{hi}m"] = {
                "n": int(m.sum()),
                "median_abs_m": float(np.median(np.abs(e[m]))),
                "median_relative_pct": float(
                    100 * np.median(np.abs(e[m]) / dr[m])),
            }
    return {
        "n_pairs": int(len(e)),
        "baseline_range_m": [float(dr.min()), float(dr.max())],
        "signed_median_m": float(np.median(e)),
        "median_abs_m": float(np.median(np.abs(e))),
        "p90_abs_m": float(np.percentile(np.abs(e), 90)),
        "rmse_m": float(np.sqrt((e ** 2).mean())),
        "implied_scale_error_pct": float(100 * slope),
        "by_baseline": bands,
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--run", required=True)
    ap.add_argument("--truth", required=True, help="reference orientations .xyz")
    ap.add_argument("--mission", required=True, help="mission dir with frame_index.csv")
    ap.add_argument("--epsg", type=int, default=32632)
    ap.add_argument("--out", default=None)
    a = ap.parse_args()

    run = APP / "data/runs" / a.run
    ours, cams = load_ours(run, a.epsg)

    ref = {}
    for line in Path(a.truth).read_text().splitlines():
        if line.startswith("#") or not line.strip():
            continue
        p = line.split()
        ref[Path(p[0]).stem] = np.array([float(p[1]), float(p[2]), float(p[3])])

    stem = {}
    with open(Path(a.mission) / "raw/frame_index.csv") as fh:
        for r in csv.DictReader(fh):
            stem[int(r["encoded_frame_index"])] = r["imgid"]

    A, B, names = [], [], []
    for row, c in zip(ours, cams):
        s = stem.get(int(c["frame_index"]))
        if s and s in ref:
            A.append(row); B.append(ref[s]); names.append(s)
    A, B = np.array(A), np.array(B)
    if len(A) < 4:
        raise SystemExit(f"only {len(A)} cameras paired by filename")

    out = {
        "run": a.run, "epsg": a.epsg,
        "correspondence": "image filename -- carries no geometry from the output",
        "n_cameras_paired": int(len(A)),
        "dimensional": pair_stats(A, B),
        "absolute_position": {
            "median_3d_m": float(np.median(np.linalg.norm(A - B, axis=1))),
            "median_signed": {
                k: float(np.median((A - B)[:, i])) for i, k in enumerate("ENU")},
            "note": ("the reference adjustment is partly derived from the same "
                     "trajectory used as our telemetry, so absolute agreement "
                     "here is not independent; the pairwise distances above "
                     "are far less affected by that sharing"),
        },
        # Validation, run every time rather than claimed once: inject a known
        # scale error and confirm it comes back out.
        "injection_validation": {},
    }
    centre = A.mean(0)
    for k in (1.01, 1.05):
        st = pair_stats(centre + (A - centre) * k, B)
        out["injection_validation"][f"injected_{100*(k-1):+.0f}pct"] = {
            "detected_scale_pct": st["implied_scale_error_pct"],
            "median_abs_m": st["median_abs_m"],
        }

    print(json.dumps(out, indent=2))
    dest = Path(a.out) if a.out else run / "camera_dimension_score.json"
    dest.write_text(json.dumps(out, indent=2))
    print(f"\nwritten to {dest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
