#!/usr/bin/env python3
"""One dense-stereo trial on a saved sparse model, timed and made scoreable.

Dense stereo is four fifths of a run (DJI_1003: 1,585 of 1,950 s), so its
settings are what the performance plan
(docs/performance_2026_09_23/OPTIMISATION_PLAN.md, section 4) says to test --
one change at a time, against the *same* sparse model, so a difference is the
setting's and not the SfM's.

Each trial gets a fresh workspace (a stale depth map would be skipped and make
a setting look fast): ``images/`` is linked and ``sparse/`` copied from
``data/runs/<run>/colmap_workspace``, which is never written to. The fused
points are then taken through the same steps the pipeline uses -- the run's
own recon->ENU transform, the sparse points added, ``fusion.fuse`` at the
run's voxel -- and written as ``data/perf/<run>/<trial>/artifacts/cloud.npz``
beside a copy of the run's trajectory, so ``score_against_lidar.py --run``
can score it exactly like a full run.

    .venv/bin/python scripts/dense_trial.py --run usegeo_1__fixedcal --trial B0
    .venv/bin/python scripts/dense_trial.py --run dji_1003__t10 --trial D1 --num-src 12

Dense-only: SfM is not re-run, so these are screening numbers, not
end-to-end runtimes.
"""
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import threading
import time
from pathlib import Path

import numpy as np

APP = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(APP / "reconstruction"))


class GpuSampler(threading.Thread):
    """Peak memory and mean utilisation of the GPU while a trial runs."""

    def __init__(self, every_s: float = 2.0):
        super().__init__(daemon=True)
        self.every, self.samples, self._halt = every_s, [], threading.Event()

    def run(self):
        while not self._halt.is_set():
            try:
                out = subprocess.run(
                    ["nvidia-smi", "--query-gpu=utilization.gpu,memory.used",
                     "--format=csv,noheader,nounits"],
                    capture_output=True, text=True, timeout=10).stdout
                u, m = (float(x) for x in out.strip().splitlines()[0].split(","))
                self.samples.append((u, m))
            except Exception:              # noqa: BLE001
                pass
            self._halt.wait(self.every)

    def stop(self) -> dict:
        # Named _halt: `threading.Thread` has its own `_stop`, and shadowing it
        # crashed the first trial at join() after 20 minutes of stereo.
        self._halt.set()
        self.join(timeout=5)
        if not self.samples:
            return {}
        u = np.array([s[0] for s in self.samples])
        m = np.array([s[1] for s in self.samples])
        return {"gpu_util_mean_pct": round(float(u.mean()), 1),
                "gpu_mem_peak_mib": float(m.max()), "n_samples": len(u)}


def _pm_log_seconds(log: Path) -> dict:
    """PatchMatch pass durations from COLMAP's own log timestamps."""
    import datetime
    import re
    marks = []
    for line in log.read_text().splitlines():
        m = re.match(r"I(\d{8}) (\d\d:\d\d:\d\d\.\d+).*Processing view (\d+) /", line)
        if m:
            marks.append((datetime.datetime.strptime(m.group(1) + m.group(2),
                                                     "%Y%m%d%H:%M:%S.%f"),
                          int(m.group(3))))
        m = re.search(r"Elapsed time: ([\d.]+) \[minutes\]", line)
        if m:
            total = float(m.group(1)) * 60
    starts = [i for i, (_, v) in enumerate(marks) if v == 1] + [len(marks)]
    passes = [round((marks[b - 1][0] - marks[a][0]).total_seconds(), 1)
              for a, b in zip(starts, starts[1:])]
    return {"patch_match_stereo": round(total, 1), "passes": passes}


def _reuse(ws: Path, out: Path, a):
    """Load a finished trial's fused output instead of running stereo again."""
    from drishti_recon import mvs
    dense = ws / "dense"
    xyz, rgb = mvs._read_ply(dense / "fused.ply")
    counts, flat, off = mvs._read_visibility_csr(dense / "fused.ply.vis", len(xyz))
    pm = _pm_log_seconds(out / "logs" / "patch_match_stereo.log")
    t_fuse = ((out / "logs/stereo_fusion.log").stat().st_mtime
              - (out / "logs/patch_match_stereo.log").stat().st_mtime)
    settings = {"max_image_size": a.max_image_size,
                "num_src_images": a.num_src or 20,
                "window_step": a.window_step or 1,
                "num_iterations": a.iterations or 5,
                "num_samples": a.samples or 15,
                "gpu_index": a.gpu_index or "-1",
                "geom_consistency": not a.no_geom}
    dr = mvs.DenseResult(points=xyz, colors=rgb, n_views=counts,
                         stats={"settings": settings,
                                "timings_s": {**pm, "stereo_fusion": round(t_fuse, 1)},
                                "dense_focal_px": mvs._dense_focal(dense, a.max_image_size),
                                "reused": True})
    return dr, pm["patch_match_stereo"] + t_fuse, {}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--run", required=True, help="directory under data/runs/")
    ap.add_argument("--trial", required=True, help="trial name, e.g. B0 or D1")
    ap.add_argument("--max-image-size", type=int, default=1600)
    ap.add_argument("--num-src", type=int, default=None)
    ap.add_argument("--window-step", type=int, default=None)
    ap.add_argument("--iterations", type=int, default=None)
    ap.add_argument("--samples", type=int, default=None)
    ap.add_argument("--gpu-index", default=None)
    ap.add_argument("--cache-gb", type=float, default=None)
    ap.add_argument("--no-geom", action="store_true",
                    help="photometric only (no geometric consistency pass)")
    ap.add_argument("--min-views", type=int, default=5)
    ap.add_argument("--keep-maps", action="store_true",
                    help="keep depth/normal maps so fusion can be re-run")
    ap.add_argument("--reuse", action="store_true",
                    help="skip stereo; score the fused output already in this "
                         "trial's workspace (timings come from COLMAP's logs)")
    a = ap.parse_args()

    from drishti_recon import mvs, fusion
    import pycolmap

    src = APP / "data/runs" / a.run
    src_ws = src / "colmap_workspace"
    out = APP / "data/perf" / a.run / a.trial
    ws = out / "ws"
    if a.reuse:
        dr, dense_s, gpu_stats = _reuse(ws, out, a)
    else:
        if out.exists():
            shutil.rmtree(out)
        ws.mkdir(parents=True)
        (ws / "images").symlink_to((src_ws / "images").resolve())
        shutil.copytree(src_ws / "sparse", ws / "sparse")

        gpu = GpuSampler()
        gpu.start()
        t0 = time.perf_counter()
        try:
            dr = mvs.run_colmap(ws, max_image_size=a.max_image_size,
                                geom_consistency=not a.no_geom,
                                min_num_pixels=a.min_views,
                                num_src_images=a.num_src,
                                window_step=a.window_step,
                                num_iterations=a.iterations,
                                num_samples=a.samples,
                                gpu_index=a.gpu_index, cache_size_gb=a.cache_gb,
                                keep_depth_maps=a.keep_maps,
                                log_dir=out / "logs")
        finally:
            dense_s = time.perf_counter() - t0
            gpu_stats = gpu.stop()

    # The same path to a metric cloud the pipeline takes.
    man = json.loads((src / "artifacts/manifest.json").read_text())
    tr = man["transforms"]["recon_to_enu"]
    if man["transforms"].get("gravity_leveling"):
        raise SystemExit("run was gravity-levelled; this harness does not "
                         "reapply levelling")
    R, s_, t = np.array(tr["R"]), float(tr["scale"]), np.array(tr["t"])
    rec = pycolmap.Reconstruction(str(src_ws / "sparse"))
    sp = np.array([p.xyz for p in rec.points3D.values()])
    sc = np.array([p.color for p in rec.points3D.values()], np.uint8)
    pts = np.vstack([sp, dr.points])
    cols = np.vstack([sc, dr.colors])
    enu = s_ * (R @ pts.T).T + t
    voxel = float(man["params"].get("voxel", 0.15))
    t1 = time.perf_counter()
    cloud = fusion.fuse(enu, cols, np.ones(len(enu)), voxel=voxel,
                        compute_normals=False)
    fuse_s = time.perf_counter() - t1

    art = out / "artifacts"
    art.mkdir()
    np.savez_compressed(art / "cloud.npz", points=cloud.points,
                        colors=cloud.colors, provenance=cloud.provenance)
    shutil.copy(src / "artifacts/trajectory.json", art / "trajectory.json")
    shutil.rmtree(ws / "dense" / "images", ignore_errors=True)

    rec_out = {
        "run": a.run, "trial": a.trial,
        "kind": "dense-only screening on a fixed sparse model",
        "settings": dr.stats["settings"],
        "dense_s": round(dense_s, 1),
        "substages_s": dr.stats["timings_s"],
        "fuse_s": round(fuse_s, 1),
        "n_dense_points": int(len(dr)),
        "n_cloud_points": int(len(cloud)),
        "dense_focal_px": dr.stats.get("dense_focal_px"),
        "gpu": gpu_stats,
        "commit": subprocess.run(["git", "rev-parse", "--short", "HEAD"],
                                 capture_output=True, text=True,
                                 cwd=APP).stdout.strip(),
    }
    (out / "trial.json").write_text(json.dumps(rec_out, indent=2))
    print(json.dumps(rec_out, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
