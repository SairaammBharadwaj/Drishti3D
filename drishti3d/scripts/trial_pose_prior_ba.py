#!/usr/bin/env python3
"""Trial: RTK positions as pose priors inside bundle adjustment.

DEC-043 measured that ~40% of vertical error on MARS-LVIG is large-scale warp:
per-40 m-tile biases span -1.2..+2.1 m, and a single similarity to RTK cannot
remove a bend. The V3.1 plan (sections 24, 130) puts GNSS inside the
optimisation instead. This tests that on a finished run, without touching the
pipeline:

* **baseline** -- the run's own dense cloud, placed by a similarity fitted from
  its camera centres to RTK (what the pipeline does);
* **pose-prior BA** -- the same sparse model re-adjusted with each camera's RTK
  position as a prior (pycolmap pose-prior bundle adjuster, intrinsics held
  fixed), then dense stereo re-run with the pipeline's own ``mvs.run_colmap``
  and its default settings.

Both are scored with the validated vertical metric (flat LiDAR cells, injection
re-checked) and a per-tile bias analysis. Priors use the run's applied time
offset and its keyframe timestamps, so the timing is the pipeline's own.

Usage:
  python scripts/trial_pose_prior_ba.py --run mars_hkisland03_sp__first \\
      --mission mars_hkisland03_sp --truth ../datasets/truth/mars_hkisland03_sp/reference_lidar.las
"""
from __future__ import annotations

import argparse
import csv
import json
import shutil
import sys
import time
from pathlib import Path

import numpy as np

APP = Path(__file__).resolve().parents[1]
REPO = APP.parent
sys.path.insert(0, str(APP / "reconstruction"))
sys.path.insert(0, str(APP / "scripts"))

TILE_M = 40.0


def tile_stats(xy, dz, tile=TILE_M, min_n=300):
    t = np.floor(xy / tile).astype(int)
    keys, inv = np.unique(t, axis=0, return_inverse=True)
    inv = inv.ravel()
    med = np.array([np.median(dz[inv == i]) for i in range(len(keys))])
    big = np.array([(inv == i).sum() >= min_n for i in range(len(keys))])
    resid = dz - med[inv]
    return {"tiles": int(big.sum()),
            "tile_bias_min": float(med[big].min()), "tile_bias_max": float(med[big].max()),
            "tile_bias_std": float(med[big].std()),
            "rmse_without_tile_bias": float(np.sqrt(np.mean(resid ** 2)))}


def score(name, pts_utm, ref, flat_cell_dz):
    dz_of = flat_cell_dz(pts_utm, ref)
    dz, xy = dz_of(pts_utm, return_xy=True)
    inj = {f"{s:+.2f}": round(float(np.median(dz_of(pts_utm + [0, 0, s]))) - float(np.median(dz)), 4)
           for s in (0.30, -0.10)}
    r = {"name": name, "n_points": int(len(pts_utm)), "n_scored": int(len(dz)),
         "bias_median_dz_m": float(np.median(dz)),
         "rmse_dz_m": float(np.sqrt(np.mean(dz ** 2))),
         "abs_dz_p50_m": float(np.percentile(np.abs(dz), 50)),
         "abs_dz_p90_m": float(np.percentile(np.abs(dz), 90)),
         "abs_dz_p99_m": float(np.percentile(np.abs(dz), 99)),
         "injection": inj, **tile_stats(xy, dz)}
    print(f"{name:16s} n {r['n_scored']:>8,d}  bias {r['bias_median_dz_m']:+.3f}  "
          f"RMSE {r['rmse_dz_m']:.3f}  p90 {r['abs_dz_p90_m']:.3f}  p99 {r['abs_dz_p99_m']:.3f}  "
          f"| tiles {r['tiles']} bias {r['tile_bias_min']:+.2f}..{r['tile_bias_max']:+.2f} "
          f"std {r['tile_bias_std']:.2f} -> {r['rmse_without_tile_bias']:.3f}  | inj {inj}")
    return r


def main() -> int:
    import pycolmap
    from pyproj import Transformer
    from drishti_recon import mvs
    from drishti_recon.geo import umeyama_sim3
    import score_against_lidar as sal
    from score_vertical_dsm import flat_cell_dz

    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--run", required=True)
    ap.add_argument("--mission", required=True)
    ap.add_argument("--set", default="mars_lvig")
    ap.add_argument("--truth", required=True)
    ap.add_argument("--epsg", type=int, default=32650)
    ap.add_argument("--sigma-h", type=float, default=0.05,
                    help="prior horizontal std (m): RTK 1-2 cm plus timing")
    ap.add_argument("--sigma-v", type=float, default=0.05)
    ap.add_argument("--no-priors", action="store_true",
                    help="plain bundle adjustment, then a similarity to RTK")
    ap.add_argument("--refine-radial", action="store_true",
                    help="model residual radial distortion (k1, k2) on the already "
                         "undistorted images and refine it; focal and principal "
                         "point stay fixed (DEC-038: a free focal drifts)")
    ap.add_argument("--tag", default="pp")
    a = ap.parse_args()

    run = APP / "data/runs" / a.run
    ws = run / "colmap_workspace"
    mission = REPO / "datasets/public" / a.set / a.mission
    rep = json.loads(next(run.glob("run_*.json")).read_text())
    offset = float(rep["report"]["sensors"]["time_offset"]["offset_s"])
    kf = json.loads((run / "artifacts/keyframes.json").read_text())

    rows = list(csv.DictReader(open(mission / "raw/telemetry.csv")))
    tt = np.array([float(r["timestamp"]) for r in rows])
    tf = Transformer.from_crs(4326, a.epsg, always_xy=True)
    e, n = tf.transform([float(r["longitude"]) for r in rows],
                        [float(r["latitude"]) for r in rows])
    rtk = np.c_[e, n, [float(r["altitude"]) for r in rows]]
    tq = np.array([k["timestamp"] for k in kf]) + offset
    prior = np.c_[[np.interp(tq, tt, rtk[:, j]) for j in range(3)]].T
    origin = np.round(prior.mean(0))
    prior_local = prior - origin
    print(f"{a.run}: {len(kf)} keyframes, applied offset {offset:+.3f} s, "
          f"prior sigma {a.sigma_h}/{a.sigma_v} m")

    rec = pycolmap.Reconstruction(str(ws / "sparse"))
    names = {im.image_id: im.name for im in rec.images.values()}
    idx = {iid: int(Path(nm).stem) for iid, nm in names.items()}

    # ---- baseline: the run's own dense cloud, similarity to RTK -------------
    src = np.array([rec.images[i].projection_center() for i in idx])
    dst = np.array([prior_local[idx[i]] for i in idx])
    sim = umeyama_sim3(src, dst)
    res0 = dst - sim.apply(src)
    print(f"baseline similarity: camera residual RMSE {np.sqrt((res0**2).sum(1).mean()):.3f} m")
    xyz0, _ = mvs._read_ply(ws / "dense/fused.ply")
    base_utm = sim.apply(xyz0) + origin

    # ---- adjusted model -----------------------------------------------------
    rec_pp = pycolmap.Reconstruction(rec)
    if a.refine_radial:
        for cid, cam in list(rec_pp.cameras.items()):
            fx, fy, cx, cy = cam.params
            new = pycolmap.Camera(model="OPENCV", width=cam.width, height=cam.height,
                                  params=[fx, fy, cx, cy, 0.0, 0.0, 0.0, 0.0],
                                  camera_id=cid)
            rec_pp.cameras[cid] = new
    cov = np.diag([a.sigma_h ** 2, a.sigma_h ** 2, a.sigma_v ** 2])
    priors = []
    for iid, k in idx.items():
        p = pycolmap.PosePrior()
        p.pose_prior_id = iid
        p.corr_data_id = rec_pp.images[iid].data_id
        p.position = prior_local[k]
        p.position_covariance = cov
        p.coordinate_system = pycolmap.PosePriorCoordinateSystem.CARTESIAN
        priors.append(p)
    opts = pycolmap.BundleAdjustmentOptions()
    opts.refine_focal_length = False
    opts.refine_principal_point = False
    opts.refine_extra_params = bool(a.refine_radial)
    popts = pycolmap.PosePriorBundleAdjustmentOptions()
    cfg = pycolmap.BundleAdjustmentConfig()
    for iid in idx:
        cfg.add_image(iid)
    if not a.refine_radial:
        for cid in rec_pp.cameras:
            cfg.set_constant_cam_intrinsics(cid)
    t0 = time.perf_counter()
    if a.no_priors:
        cfg.fix_gauge(pycolmap.BundleAdjustmentGauge.THREE_POINTS)
        ba = pycolmap.create_default_bundle_adjuster(opts, cfg, rec_pp)
    else:
        ba = pycolmap.create_pose_prior_bundle_adjuster(opts, popts, cfg, priors, rec_pp)
    summary = ba.solve()
    print(f"pose-prior BA: {time.perf_counter()-t0:.1f} s; "
          f"{getattr(summary, 'termination_type', '')} ; "
          f"reprojection {rec.compute_mean_reprojection_error():.3f} -> "
          f"{rec_pp.compute_mean_reprojection_error():.3f} px")
    for cid, cam in rec_pp.cameras.items():
        print(f"camera {cid}: {cam.model} params {np.round(cam.params, 6).tolist()}")
    c1 = np.array([rec_pp.images[i].projection_center() for i in idx])
    if a.no_priors:
        sim1 = umeyama_sim3(c1, dst)
        c1 = sim1.apply(c1)
    res1 = dst - c1
    print(f"after BA: camera-to-prior residual RMSE {np.sqrt((res1**2).sum(1).mean()):.3f} m "
          f"(no similarity applied; the model is now in the prior frame)")

    # ---- dense stereo on the adjusted model, pipeline defaults ---------------
    ws_pp = run / f"colmap_workspace_{a.tag}"
    if ws_pp.exists():
        shutil.rmtree(ws_pp)
    (ws_pp / "sparse").mkdir(parents=True)
    (ws_pp / "images").symlink_to(ws / "images")
    rec_pp.write(str(ws_pp / "sparse"))
    t0 = time.perf_counter()
    dr = mvs.run_colmap(ws_pp, max_image_size=1300, geom_consistency=True,
                        min_num_pixels=4, num_src_images=10, window_step=2,
                        num_iterations=3, cache_size_gb=1, keep_depth_maps=False,
                        log_dir=ws_pp / "logs")
    print(f"dense stereo on adjusted model: {time.perf_counter()-t0:.0f} s, {len(dr.points):,} points")
    pp_pts = np.asarray(dr.points, float)
    pp_utm = (sim1.apply(pp_pts) if a.no_priors else pp_pts) + origin

    # ---- score both ----------------------------------------------------------
    lo = np.minimum(base_utm.min(0), pp_utm.min(0)) - 5
    hi = np.maximum(base_utm.max(0), pp_utm.max(0)) + 5
    ref = sal.load_lidar_in_box(Path(a.truth), lo, hi)
    out = {"run": a.run, "offset_s": offset, "sigma_h": a.sigma_h, "sigma_v": a.sigma_v,
           "baseline_camera_residual_rmse_m": float(np.sqrt((res0**2).sum(1).mean())),
           "pp_camera_residual_rmse_m": float(np.sqrt((res1**2).sum(1).mean())),
           "baseline": score("similarity", base_utm, ref, flat_cell_dz),
           "variant": {"no_priors": a.no_priors, "refine_radial": a.refine_radial},
           "cameras": {int(c): [cam.model.name, [float(v) for v in cam.params]]
                       for c, cam in rec_pp.cameras.items()},
           "pose_prior_ba": score(a.tag, pp_utm, ref, flat_cell_dz)}
    (run / f"trial_{a.tag}.json").write_text(json.dumps(out, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
