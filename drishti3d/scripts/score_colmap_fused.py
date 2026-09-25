#!/usr/bin/env python3
"""Georeference a raw COLMAP dense cloud by RTK and score it against a LiDAR.

For a run the pipeline could not finish -- the full-resolution MARS-LVIG run
was OOM-killed in fusion, after 55 minutes of PatchMatch -- the depth maps and
sparse model survive, but no georeference or keyframe list was written. This
recovers both and scores the result, so the expensive part is not thrown away.

1. Keyframe capture times: from the pipeline's ``keyframes.json`` if there is
   one, otherwise by pixel matching. Keyframe images are the decoded,
   undistorted video frames written as JPEG, so each has exactly one
   near-identical analysed frame; the best/second-best error ratio is printed
   so a weak match is visible rather than trusted.
2. A camera-RTK time offset is estimated, not assumed, by minimising the
   alignment residual over a range of shifts.
3. A 7-DoF similarity (Umeyama) maps COLMAP camera centres onto RTK positions
   in the LiDAR's projected CRS; the same transform maps the fused cloud.
4. The cloud is scored exactly as ``score_against_lidar.py`` scores a finished
   run, with the same 5 m match cutoff.

This is not the pipeline's own georeference or point filtering. Run it on a
run that *did* finish (``--keyframes``) to measure how far the two differ
before trusting it on one that did not.

Usage:
  python scripts/score_colmap_fused.py --run mars_hkisland03__first \\
      --mission mars_hkisland03 --keyframes --truth <las> --epsg 32650
  python scripts/score_colmap_fused.py --run mars_hkisland03_win__full \\
      --mission mars_hkisland03_win --match-stride 3 --truth <las> --epsg 32650
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path

import numpy as np

APP = Path(__file__).resolve().parents[1]
REPO = APP.parent
sys.path.insert(0, str(APP / "reconstruction"))
sys.path.insert(0, str(APP / "scripts"))

MAX_MATCH_M = 5.0


def umeyama(src, dst):
    """Similarity (s, R, t) minimising |dst - (s R src + t)|."""
    ms, md = src.mean(0), dst.mean(0)
    a, b = src - ms, dst - md
    U, S, Vt = np.linalg.svd(b.T @ a / len(src))
    D = np.eye(3)
    if np.linalg.det(U) * np.linalg.det(Vt) < 0:
        D[2, 2] = -1
    R = U @ D @ Vt
    s = np.trace(np.diag(S) @ D) / a.var(0).sum()
    return s, R, md - s * R @ ms


def match_keyframes(mission, kf_dir, stride, K, dist):
    """Analysed-frame index of each keyframe image, by pixel matching."""
    import cv2
    from drishti_recon import sensors
    names = sorted(p.name for p in kf_dir.glob("*.jpg"))
    size = (306, 256)
    kfs = [cv2.resize(cv2.imread(str(kf_dir / n), cv2.IMREAD_GRAYSCALE), size)
           .astype(np.float32) for n in names]
    cap = cv2.VideoCapture(str(mission / "raw/video.mp4"))
    thumbs, idxs, i = [], [], 0
    while True:
        ok = cap.grab()
        if not ok:
            break
        if i % stride == 0:
            _, fr = cap.retrieve()
            (fr,), _, _ = sensors.undistort_frames([fr], K, dist)
            thumbs.append(cv2.resize(cv2.cvtColor(fr, cv2.COLOR_BGR2GRAY), size)
                          .astype(np.float32))
            idxs.append(i)
        i += 1
    T = np.stack(thumbs).reshape(len(thumbs), -1)
    out, ratios = [], []
    for k in kfs:
        err = ((T - k.ravel()) ** 2).mean(1)
        o = np.argsort(err)
        out.append(idxs[o[0]])
        ratios.append(err[o[1]] / max(err[o[0]], 1e-9))
    return names, out, np.asarray(ratios)


def main() -> int:
    import pycolmap
    from pyproj import Transformer
    from scipy.spatial import cKDTree
    from drishti_recon import mvs
    import score_against_lidar as sal

    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--run", required=True)
    ap.add_argument("--mission", required=True)
    ap.add_argument("--set", default="mars_lvig")
    ap.add_argument("--keyframes", action="store_true",
                    help="take capture times from the run's keyframes.json")
    ap.add_argument("--match-stride", type=int, default=None,
                    help="recover capture times by pixel matching every Nth frame")
    ap.add_argument("--truth", required=True)
    ap.add_argument("--epsg", type=int, required=True)
    ap.add_argument("--out", default=None)
    a = ap.parse_args()

    run = APP / "data/runs" / a.run
    ws = run / "colmap_workspace"
    mission = REPO / "datasets/public" / a.set / a.mission
    fps = json.loads((mission / "manifest.json").read_text())["video"]["fps"]

    rec = pycolmap.Reconstruction(str(ws / "dense/sparse"))
    centre = {im.name: np.asarray(im.projection_center()) for im in rec.images.values()}

    if a.keyframes:
        kf = json.loads((run / "artifacts/keyframes.json").read_text())
        names = [f"{k:04d}.jpg" for k in range(len(kf))]
        frame_idx = [int(x["frame_index"]) for x in kf]
        ratios = None
    else:
        cam = json.loads((mission / "calibration/camera.json").read_text())
        K = np.array([[cam["fx"], 0, cam["cx"]], [0, cam["fy"], cam["cy"]], [0, 0, 1]])
        dist = [cam["k1"], cam["k2"], cam["p1"], cam["p2"], cam["k3"]]
        names, frame_idx, ratios = match_keyframes(
            mission, ws / "images", a.match_stride, K, dist)
        print(f"pixel match: best/second error ratio min {ratios.min():.1f}, "
              f"median {np.median(ratios):.1f} (1.0 would be ambiguous)")

    rows = list(csv.DictReader(open(mission / "raw/telemetry.csv")))
    tt = np.array([float(r["timestamp"]) for r in rows])
    tf = Transformer.from_crs(4326, a.epsg, always_xy=True)
    e, n = tf.transform([float(r["longitude"]) for r in rows],
                        [float(r["latitude"]) for r in rows])
    rtk = np.c_[e, n, [float(r["altitude"]) for r in rows]]

    keep = [i for i, nm in enumerate(names) if nm in centre]
    src = np.array([centre[names[i]] for i in keep])
    t_frames = np.array([frame_idx[i] / fps for i in keep])

    def fit(dt):
        tq = np.clip(t_frames + dt, tt[0], tt[-1])
        dst = np.c_[[np.interp(tq, tt, rtk[:, j]) for j in range(3)]].T
        s, R, t = umeyama(src, dst)
        res = dst - (s * (R @ src.T).T + t)
        return np.sqrt((res ** 2).sum(1).mean()), (s, R, t), res

    # +-2 s: on HKisland03 the minimum sat at the edge of a +-0.5 s search.
    offsets = np.round(np.arange(-2.0, 2.0001, 0.02), 3)
    scores = [fit(d)[0] for d in offsets]
    best = float(offsets[int(np.argmin(scores))])
    rms, (s, R, t), res = fit(best)
    rms0 = fit(0.0)[0]
    print(f"registered keyframes {len(keep)}/{len(names)}; "
          f"camera-RTK time offset {best:+.2f} s "
          f"(alignment RMSE {rms:.3f} m; at 0 s {rms0:.3f} m)")

    xyz, _ = mvs._read_ply(ws / "dense/fused.ply")
    ours = s * (xyz @ R.T) + t
    lo, hi = ours.min(0), ours.max(0)
    ref = sal.load_lidar_in_box(Path(a.truth), lo, hi)
    print(f"cloud {len(ours):,} points; reference {len(ref):,} LiDAR points")
    tree = cKDTree(ref)
    d, _ = tree.query(ours, workers=4)
    m = d <= MAX_MATCH_M
    dm = d[m]

    def stats(v):
        return {"n": int(len(v)), "median_m": float(np.median(v)),
                "rmse_m": float(np.sqrt(np.mean(v ** 2))),
                "p90_m": float(np.percentile(v, 90)),
                "p95_m": float(np.percentile(v, 95)),
                "p99_m": float(np.percentile(v, 99))}

    rng = np.random.default_rng(0)
    from scipy.spatial import Delaunay
    hull = Delaunay(ours[rng.choice(len(ours), min(len(ours), 50_000), replace=False), :2])
    ri = rng.choice(len(ref), min(len(ref), 2_000_000), replace=False)
    ri = ri[hull.find_simplex(ref[ri][:, :2]) >= 0]
    dc, _ = cKDTree(ours).query(ref[ri], workers=4)

    result = {
        "run": a.run, "method": "raw COLMAP fused.ply, RTK Umeyama sim3 (this script)",
        "n_points": int(len(ours)), "unmatched_fraction": float(1 - m.mean()),
        "camera_rtk_time_offset_s": best,
        "alignment_rmse_m": float(rms), "alignment_scale": float(s),
        "match_ratio_min": None if ratios is None else float(ratios.min()),
        "accuracy_recon_to_lidar": stats(dm),
        "completeness_within_0_25m": float((dc <= 0.25).mean()),
        "completeness_within_0_50m": float((dc <= 0.5).mean()),
    }
    print(json.dumps(result, indent=2))
    if a.out:
        Path(a.out).write_text(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
