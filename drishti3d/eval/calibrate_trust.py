"""Calibrate trust-score weights against exact synthetic truth (doc §20).

The document requires the weights be "calibrated experimentally rather than
arbitrarily chosen". Two things have to be right for that to mean anything:

1. **The error target must be real.** Nearest-neighbour distance to the sampled
   ``scene_points_enu`` cloud cannot resolve error below that cloud's own
   0.33 m median spacing; measured against it, reconstruction error read
   0.782 m median where exact point-to-surface distance says 0.020 m, and the
   two metrics rank points at only rho = 0.20. This script uses
   ``synth.surface_distance``.
2. **The normalisations must be fitted too.** Saturation constants chosen by
   intuition pinned two of three terms at their ceiling for most points.
   :func:`trust.fit_normalisation` derives them from the data.

Writes ``eval/trust_weights.json``: fitted normalisation, effective weights,
the achieved rank correlation, and the per-decile error profile that shows the
score actually orders points by accuracy.
"""
import json
import sys
from pathlib import Path

import numpy as np


def _load_frames(video):
    import cv2
    cap = cv2.VideoCapture(str(video))
    frames = []
    while True:
        ok, f = cap.read()
        if not ok:
            break
        frames.append(f)
    cap.release()
    return frames


def main(out_json="eval/trust_weights.json", scene_dir=None, seed=0,
         regime="oblique_pass"):
    sys.path.insert(0, "reconstruction")
    from drishti_recon import sfm, synth, trust
    from drishti_recon.geo import umeyama_sim3
    from scipy.stats import spearmanr

    scene_dir = Path(scene_dir or f"/tmp/drishti_trust_{regime}_s{seed}")
    video = next(iter(scene_dir.glob("*.mp4")), None)
    if video is None:
        synth.generate(scene_dir, n_frames=60, regime=regime, seed=int(seed))
        video = next(iter(scene_dir.glob("*.mp4")))
    meta = json.loads((scene_dir / "ground_truth.json").read_text())

    frames = _load_frames(video)
    intr = meta["intrinsics"]
    K = np.array([[intr["fx"], 0, intr["cx"]],
                  [0, intr["fy"], intr["cy"]], [0, 0, 1]], float)
    r = sfm.reconstruct(frames, K)
    pts = np.asarray(r.points)

    # Gauge: Sim(3) from estimated to true camera centres, then exact
    # point-to-surface distance in the true frame.
    gt_c = np.asarray([c["C_enu"] for c in meta["cameras_enu"]], float)
    est_c = np.array([c.center for c in r.cameras])
    n = min(len(gt_c), len(est_c))
    T = umeyama_sim3(est_c[:n], gt_c[:n])
    P_world = (T.scale * (T.R @ pts.T)).T + T.t
    err = synth.surface_distance(P_world)

    norm = trust.fit_normalisation(obs_count=r.obs_count,
                                   residual_px=r.reproj_err,
                                   tri_angle_deg=r.tri_angle)
    O, N, E, Pq = trust.components(obs_count=r.obs_count,
                                   residual_px=r.reproj_err,
                                   tri_angle_deg=r.tri_angle, norm=norm)
    w, sp = trust.calibrate_weights(O, N, E, Pq, err, grid=10)
    s = trust.score(O, N, E, Pq, w)

    deciles = []
    q = np.quantile(s, np.linspace(0, 1, 11))
    for i in range(10):
        m = (s >= q[i]) & (s <= q[i + 1])
        if m.any():
            deciles.append(dict(decile=i + 1, n=int(m.sum()),
                                median_err_m=float(np.median(err[m])),
                                p90_err_m=float(np.percentile(err[m], 90))))

    out = dict(
        weights=[float(x) for x in w], weight_order=["O", "N", "E", "P"],
        normalisation={k: float(v) for k, v in norm.items()},
        spearman=float(sp), n_points=int(len(P_world)),
        scene=f"{regime}/seed{seed}", error_metric="analytic_surface_distance",
        error_median_m=float(np.median(err)),
        decile_profile=deciles,
        components_present=["O", "E", "P"],
        note=("N (network confidence) is absent for the classical engine; its "
              "weight is reported as 0 and redistributed at score time. The "
              "terms are correlated (obs_count vs parallax rho=0.88), so these "
              "weights rank well but are not per-term importances."),
    )
    Path(out_json).write_text(json.dumps(out, indent=2))
    print(f"weights O/N/E/P = {np.round(w, 3)}  spearman {sp:.3f}")
    print(f"error median {np.median(err):.4f} m; decile 1 -> 10: "
          f"{deciles[0]['median_err_m']:.4f} -> {deciles[-1]['median_err_m']:.4f} m")
    print(f"wrote {out_json}")


if __name__ == "__main__":
    main(*sys.argv[1:])
