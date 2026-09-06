"""Do the predicted measurement intervals actually contain the truth?

This is the acceptance experiment for decision D-002. A propagated uncertainty is
a claim about the world -- "the true value lies within +/- x, 95% of the time" --
and a claim like that is only worth making once it has been checked against
withheld truth.

The procedure: reconstruct each synthetic scene, measure its known reference
distances on the resulting cloud, and compare the error against the predicted
sigma. Then report **empirical coverage** at 50/80/95%, and the robust scale
factor that would be needed to make the intervals honest.

A factor > 1 means the model is optimistic. That is the expected direction,
because camera-pose uncertainty and systematic error are deliberately not
modelled (see :mod:`drishti_recon.uncertainty`).

    python -m eval.calibrate_uncertainty --scenes <scene-cache-dir> --out cal_out
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "reconstruction"))
sys.path.insert(0, str(ROOT))

from drishti_recon import measure, pipeline, uncertainty as unc   # noqa: E402
from drishti_recon.fusion import PointCloud                       # noqa: E402
from drishti_recon.geo import ENUFrame                            # noqa: E402


def _load_cloud(art: Path) -> PointCloud:
    npz = np.load(art / "cloud.npz")
    return PointCloud(npz["points"], npz["colors"], npz["confidence"],
                      npz["provenance"], None,
                      npz["sigma"] if "sigma" in npz.files else None,
                      npz["sigma_major"] if "sigma_major" in npz.files else None)


def run_scene(scene: Path, work: Path, *, bundle_adjust: bool) -> list[dict]:
    """Reconstruct one scene and measure every known reference distance on it."""
    man = json.loads((scene / "scene_manifest.json").read_text())
    gt = json.loads((scene / "ground_truth.json").read_text())
    k = man["intrinsics"]
    params = pipeline.PipelineParams(
        do_mesh=False, gravity_align=False, bundle_adjust=bundle_adjust,
        intrinsics={"fx": k["fx"], "fy": k["fy"], "cx": k["cx"], "cy": k["cy"]})
    work.mkdir(parents=True, exist_ok=True)
    result = pipeline.run(work, man["video"], man["telemetry"], params=params)

    art = work / "artifacts"
    cloud = _load_cloud(art)
    align = result.report.get("alignment") or {}
    ssr = align.get("scale_sigma_relative") or 0.0

    # Re-anchor the ground-truth endpoints into the pipeline's own ENU frame.
    origin = gt["origin_wgs84"]
    gt_frame = ENUFrame(origin["lat"], origin["lon"], origin["alt"])
    frame = ENUFrame(**json.loads((art / "trajectory.json").read_text())["frame"])

    rows = []
    for rd in gt.get("reference_distances", []):
        wgs = gt_frame.enu_to_geodetic(np.array([rd["a"], rd["b"]]))
        ab = frame.geodetic_to_enu(wgs[:, 0], wgs[:, 1], wgs[:, 2])
        m = measure.measure_distance(cloud, [ab[0], ab[1]], scale_sigma_rel=ssr)
        rows.append({
            "scene": scene.name, "name": rd["name"],
            "true_m": float(rd["meters"]), "measured_m": float(m.value),
            "error_m": float(m.value - rd["meters"]),
            "sigma_m": float(m.sigma) if np.isfinite(m.sigma) else None,
            "scale_sigma_relative": float(ssr),
        })
    return rows


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--scenes", required=True,
                    help="directory of rendered scenes (the benchmark scene cache)")
    ap.add_argument("--out", default="cal_out")
    ap.add_argument("--bundle-adjust", action="store_true")
    ap.add_argument("--limit", type=int, default=0, help="cap the number of scenes")
    args = ap.parse_args(argv)

    scenes = sorted(p for p in Path(args.scenes).iterdir()
                    if (p / "scene_manifest.json").exists())
    if args.limit:
        scenes = scenes[:args.limit]
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    rows: list[dict] = []
    for i, sc in enumerate(scenes, 1):
        print(f"[{i}/{len(scenes)}] {sc.name} ...", end=" ", flush=True)
        try:
            got = run_scene(sc, out / "work" / sc.name,
                            bundle_adjust=args.bundle_adjust)
            rows.extend(got)
            print(f"{len(got)} measurements")
        except Exception as exc:
            # A scene that cannot reconstruct contributes no measurements; that
            # is a reconstruction failure, not a calibration data point.
            print(f"skipped ({type(exc).__name__}: {exc})")

    usable = [r for r in rows if r["sigma_m"] is not None]
    errors = np.array([r["error_m"] for r in usable])
    sigmas = np.array([r["sigma_m"] for r in usable])
    cal = unc.calibrate(errors, sigmas) if len(usable) >= 3 else None

    # Leave-one-out coverage: the only honest number here, because a conformal
    # factor fitted on the same points it scores is guaranteed to look good.
    loo: dict = {}
    if len(usable) >= 5:
        hits = {50: 0, 80: 0, 95: 0}
        for i in range(len(errors)):
            keep = np.ones(len(errors), bool)
            keep[i] = False
            k = unc.conformal_factors(errors[keep], sigmas[keep])
            for lvl in hits:
                if k and abs(errors[i]) <= k[lvl] * sigmas[i]:
                    hits[lvl] += 1
        loo = {lvl: hits[lvl] / len(errors) for lvl in hits}

    payload = {
        "n_measurements": len(rows),
        "n_usable": len(usable),
        "bundle_adjust": bool(args.bundle_adjust),
        "measurements": rows,
        "calibration": cal.to_dict() if cal else None,
        "coverage_leave_one_out": loo,
        "error_summary_m": {
            "median_abs": float(np.median(np.abs(errors))) if len(errors) else None,
            "p90_abs": float(np.percentile(np.abs(errors), 90)) if len(errors) else None,
            "max_abs": float(np.abs(errors).max()) if len(errors) else None,
        },
    }
    (out / "calibration.json").write_text(json.dumps(payload, indent=2))

    print(f"\n{len(usable)}/{len(rows)} measurements with finite uncertainty")
    if cal:
        print(f"median |error|/sigma = {cal.median_abs_z:.3f}")
        print(f"robust scale factor  = {cal.scale_factor:.3f} "
              f"({'optimistic' if cal.scale_factor > 1 else 'conservative'})")
        print(f"{'level':>6s} {'raw':>7s} {'gaussian':>9s} {'conformal':>10s} "
              f"{'k':>7s} {'held-out':>9s}")
        for lvl in (50, 80, 95):
            print(f"{lvl:5d}% {cal.coverage.get(lvl, float('nan')):7.3f} "
                  f"{cal.coverage_calibrated.get(lvl, float('nan')):9.3f} "
                  f"{cal.coverage_conformal.get(lvl, float('nan')):10.3f} "
                  f"{cal.conformal_factors.get(lvl, float('nan')):7.2f} "
                  f"{loo.get(lvl, float('nan')):9.3f}")
        print("\n'conformal' is fitted on this same set, so it is optimistic by "
              "construction.\n'held-out' is leave-one-out: the factor never saw "
              "the measurement it scores.\nTrust the held-out column.")
    print(f"wrote {out/'calibration.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
