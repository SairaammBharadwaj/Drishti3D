#!/usr/bin/env python3
"""Run the reconstruction pipeline on a built mission and score it.

Two roles are kept apart on purpose, because mixing them is how a benchmark
starts flattering itself:

* The **worker** is given ``datasets/public/<set>/<mission>/`` only -- video,
  telemetry, camera calibration.  It never sees ``datasets/truth/``.
* The **evaluator** runs afterwards in this script, loads the reference
  positions from ``datasets/truth/<mission>/``, and compares.  Nothing it reads
  is fed back into the reconstruction.

Scoring is reported twice: as a rigid (Umeyama, scale fixed at 1) comparison,
which is what a georeferenced product must satisfy, and after a similarity fit,
which isolates shape error from scale and placement error.  Reporting only the
second is the usual way to make a drifting reconstruction look accurate.

Usage:
  python scripts/run_mission.py --mission agz_dense_pass [--engine opencv]
      [--max-frames 184] [--tag baseline]
"""
from __future__ import annotations

import argparse
import csv
import json
import platform
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parents[2]
APP = REPO / "drishti3d"
sys.path.insert(0, str(APP / "reconstruction"))

from drishti_recon import pipeline                         # noqa: E402
from drishti_recon.geo import ENUFrame                     # noqa: E402


def _git_commit() -> str:
    try:
        return subprocess.run(["git", "rev-parse", "--short=12", "HEAD"],
                              cwd=REPO, capture_output=True, text=True,
                              check=True).stdout.strip()
    except Exception:                                      # noqa: BLE001
        return "unknown"


def _rigid_and_similarity_error(est: np.ndarray, ref: np.ndarray) -> dict:
    """Per-camera 3D error under (a) translation only and (b) a Sim(3) fit.

    (a) keeps the reconstruction's own scale and orientation, so it measures the
    georeferenced product.  Only the common translation is removed, since it is
    the choice of local origin and carries no information about the geometry.
    (b) removes rotation and scale as well via Umeyama, which answers the
    narrower question "is the *shape* right", and is not an accuracy claim.
    """
    out = {}

    def stats(d):
        e3 = np.linalg.norm(d, axis=1)
        return {"n": int(len(e3)),
                "median_m": float(np.median(e3)),
                "p90_m": float(np.percentile(e3, 90)),
                "max_m": float(e3.max()),
                "rmse_m": float(np.sqrt((e3 ** 2).mean())),
                "horizontal_median_m": float(np.median(
                    np.linalg.norm(d[:, :2], axis=1))),
                "vertical_median_m": float(np.median(np.abs(d[:, 2])))}

    out["as_georeferenced"] = stats(
        (est - est.mean(0)) - (ref - ref.mean(0)))

    ec, rc = est - est.mean(0), ref - ref.mean(0)
    H = ec.T @ rc / len(ec)
    U, S, Vt = np.linalg.svd(H)
    D = np.diag([1, 1, np.sign(np.linalg.det(U @ Vt))])
    R = Vt.T @ D @ U.T
    scale = float((S * np.diag(D)).sum() / (ec ** 2).sum() * len(ec))
    out["after_similarity_fit"] = stats((scale * (R @ ec.T)).T - rc)
    out["after_similarity_fit"]["fitted_scale"] = scale
    out["after_similarity_fit"]["note"] = (
        "shape-only; scale and orientation were solved against the reference, "
        "so this is not an accuracy claim")
    return out


def score(mission_dir: Path, truth_dir: Path, art_dir: Path) -> dict:
    ref_csv = truth_dir / "reference_camera_positions.csv"
    if not ref_csv.exists():
        return {"status": "no reference data", "path": str(ref_csv)}
    ref = {int(r["imgid"]): (float(r["x_utm32n_m"]), float(r["y_utm32n_m"]),
                             float(r["z_m"]))
           for r in csv.DictReader(open(ref_csv))}
    gps_ref = {int(r["imgid"]): (float(r["x_gps_utm32n_m"]),
                                 float(r["y_gps_utm32n_m"]),
                                 float(r["z_gps_m"]))
               for r in csv.DictReader(open(ref_csv))}
    idx = {int(r["encoded_frame_index"]): int(r["imgid"])
           for r in csv.DictReader(open(mission_dir / "raw/frame_index.csv"))}

    traj = json.loads((art_dir / "trajectory.json").read_text())
    f = traj["frame"]
    frame = ENUFrame(f["lat0"], f["lon0"], f["alt0"])
    cams = traj["cameras_enu"]
    if not cams:
        return {"status": "no registered cameras"}

    import pyproj
    to_utm = pyproj.Transformer.from_crs("EPSG:4326", "EPSG:32632",
                                         always_xy=True)
    enu = np.array([c["C"] for c in cams], float)
    geo = frame.enu_to_geodetic(enu)                # (lat, lon, alt)
    x, y = to_utm.transform(geo[:, 1], geo[:, 0])
    est_utm = np.column_stack([x, y, geo[:, 2]])

    paired_est, paired_ref, paired_gps, imgids = [], [], [], []
    for row, c in zip(est_utm, cams):
        imgid = idx.get(int(c["frame_index"]))
        if imgid is None or imgid not in ref:
            continue
        paired_est.append(row)
        paired_ref.append(ref[imgid])
        paired_gps.append(gps_ref[imgid])
        imgids.append(imgid)
    if len(paired_est) < 4:
        return {"status": f"only {len(paired_est)} cameras matched a reference"}

    est = np.asarray(paired_est, float)
    rf = np.asarray(paired_ref, float)
    gp = np.asarray(paired_gps, float)
    res = {
        "status": "scored",
        "n_registered_cameras": len(cams),
        "n_scored": len(est),
        "n_reference_available": len(ref),
        "registration_rate": round(len(cams) / max(len(idx), 1), 4),
        "reconstruction_vs_reference": _rigid_and_similarity_error(est, rf),
        # The same comparison for raw onboard GPS, so the reconstruction is
        # judged against the signal it was given, not only against zero.
        "onboard_gps_vs_reference": _rigid_and_similarity_error(gp, rf),
        "reference_independence": "NOT independent (Pix4D photogrammetry by "
                                  "the dataset authors); this is an agreement "
                                  "measure, not a positional accuracy class",
        "imgids_scored": imgids,
    }
    return res


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--mission", required=True)
    ap.add_argument("--set", default="zurich_mav")
    ap.add_argument("--engine", default="opencv",
                    choices=["opencv", "colmap", "auto"])
    ap.add_argument("--max-frames", type=int, default=240)
    ap.add_argument("--proc-width", type=int, default=1280)
    ap.add_argument("--preset", default="balanced",
                    choices=["fast", "balanced", "quality"],
                    help="keyframe density; 'quality' keeps far more frames and "
                         "is the uniform-budget arm of the F4 experiment")
    ap.add_argument("--tag", default="baseline")
    ap.add_argument("--no-mesh", action="store_true")
    ap.add_argument("--densify", default="none", choices=["none", "depth"])
    a = ap.parse_args()

    mission_dir = REPO / "datasets/public" / a.set / a.mission
    truth_dir = REPO / "datasets/truth" / a.mission
    if not mission_dir.exists():
        raise SystemExit(f"no such mission: {mission_dir}")
    manifest = json.loads((mission_dir / "manifest.json").read_text())
    cam = json.loads((mission_dir / "calibration/camera.json").read_text())

    run_dir = APP / "data/runs" / f"{a.mission}__{a.tag}"
    run_dir.mkdir(parents=True, exist_ok=True)

    params = pipeline.PipelineParams(
        engine=a.engine,
        preset=a.preset,
        max_analyze_frames=a.max_frames,
        proc_max_width=a.proc_width,
        do_mesh=not a.no_mesh,
        densify=a.densify,
        intrinsics={"fx": cam["fx"], "fy": cam["fy"],
                    "cx": cam["cx"], "cy": cam["cy"],
                    "distortion": [cam["k1"], cam["k2"], cam["p1"],
                                   cam["p2"], cam["k3"]]},
        # Real, uncorrected-lens imagery: the 1.0 px epipolar band suits exact
        # pinholes only. Distortion is corrected up front here, but residual
        # calibration error on a factory calibration is real, so keep the
        # looser band the pipeline documents for field imagery.
        e_ransac_px=2.0,
    )

    last = {"t": 0.0}

    def progress(stage, frac, msg=""):
        now = time.time()
        if now - last["t"] > 3.0:
            last["t"] = now
            print(f"  [{frac * 100:5.1f}%] {stage:12s} {msg}", flush=True)

    t0 = time.time()
    err = None
    try:
        result = pipeline.run(run_dir, mission_dir / "raw/video.mp4",
                              mission_dir / "raw/telemetry.csv",
                              params=params, progress=progress)
        report, warns = result.report, result.warnings
    except Exception as e:                                 # noqa: BLE001
        err = f"{type(e).__name__}: {e}"
        report, warns = {}, []
    wall = time.time() - t0

    scored = {"status": "reconstruction failed"} if err else \
        score(mission_dir, truth_dir, run_dir / "artifacts")

    out = {
        "mission": a.mission,
        "tag": a.tag,
        "run_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "commit": _git_commit(),
        "platform": platform.platform(),
        "python": platform.python_version(),
        "engine": a.engine,
        "params": {"preset": a.preset,
                   "max_analyze_frames": a.max_frames,
                   "proc_max_width": a.proc_width,
                   "densify": a.densify, "do_mesh": not a.no_mesh,
                   "e_ransac_px": params.e_ransac_px},
        "mission_capture": manifest["capture"],
        "mission_video_sha256": manifest["artifacts"]["video"]["sha256"],
        "wall_seconds": round(wall, 1),
        "error": err,
        "warnings": warns,
        "report": report,
        "score": scored,
    }
    (run_dir / f"run_{a.tag}.json").write_text(json.dumps(out, indent=2,
                                                          default=str))
    print(json.dumps({k: out[k] for k in
                      ("mission", "engine", "wall_seconds", "error")}, indent=2))
    print(json.dumps(scored, indent=2, default=str)[:2400])
    print(f"\nfull result -> {run_dir / f'run_{a.tag}.json'}")
    return 1 if err else 0


if __name__ == "__main__":
    raise SystemExit(main())
