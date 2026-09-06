"""Reproducible ablation benchmark: variants x capture regimes x seeds.

Why this exists
---------------
A single favourable run is not evidence.  Field behaviour is described by the
*distribution* over capture geometries and trials -- especially its tail -- so
this driver runs the same code over a matrix and reports median **and worst**
case per cell.  Every run records the provenance needed to re-derive it: the git
commit and dirty flag, the interpreter and platform, a pip freeze, the SHA-256 of
every generated input, and the exact parameter overrides for each variant.

The rule this tool enforces: **no accuracy claim may be published unless it was
generated here.**

Usage
-----
    python -m eval.benchmark --out bench_out                     # full default matrix
    python -m eval.benchmark --variants baseline,ba --seeds 0,1  # a controlled A/B
    python -m eval.benchmark --regimes orbit --frames 40 --quick # fast smoke run

Outputs, under ``--out``:
    benchmark.json      every cell, with provenance
    BENCHMARK.md        median/worst comparison tables
    env.lock.txt        pip freeze of the interpreter that produced the numbers
"""
from __future__ import annotations

import argparse
import hashlib
import json
import platform
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "reconstruction"))
sys.path.insert(0, str(ROOT))

from eval.variants import VARIANTS, describe, resolve   # noqa: E402

DEFAULT_REGIMES = ("oblique_pass", "nadir_grid", "orbit", "low_parallax")

#: Metrics where a *smaller* number is better, used for consistent ranking.
LOWER_IS_BETTER = {"ate_rmse", "ate_median", "ate_max", "scale_error",
                   "cloud_acc_median", "cloud_acc_rmse", "dim_error_pct",
                   "runtime_s", "peak_rss_mb"}


# --------------------------------------------------------------------------- #
# provenance
# --------------------------------------------------------------------------- #
def _git(*args: str) -> str:
    try:
        return subprocess.run(["git", *args], cwd=ROOT, capture_output=True,
                              text=True, timeout=20).stdout.strip()
    except Exception:
        return ""


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _pip_freeze() -> str:
    try:
        return subprocess.run([sys.executable, "-m", "pip", "freeze"],
                              capture_output=True, text=True, timeout=120).stdout
    except Exception:
        return ""


def collect_provenance() -> dict:
    """Everything needed to answer 'what produced this number?'."""
    versions = {}
    for mod in ("numpy", "scipy", "cv2", "pyproj", "open3d"):
        try:
            versions[mod] = __import__(mod).__version__
        except Exception:
            versions[mod] = None
    return {
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "git_commit": _git("rev-parse", "HEAD"),
        "git_branch": _git("rev-parse", "--abbrev-ref", "HEAD"),
        # A dirty tree means the numbers cannot be re-derived from the commit
        # alone; the report says so rather than quietly implying reproducibility.
        "git_dirty": bool(_git("status", "--porcelain")),
        "python": sys.version.split()[0],
        "executable": sys.executable,
        "platform": platform.platform(),
        "cpu_count": __import__("os").cpu_count(),
        "library_versions": versions,
    }


# --------------------------------------------------------------------------- #
# matrix execution
# --------------------------------------------------------------------------- #
def _make_scene(scene_dir: Path, regime: str, seed: int, *, frames: int,
                width: int, height: int, gps_outlier_frac: float) -> dict:
    """Render (once per regime+seed) the synthetic scene shared by all variants.

    Sharing one scene across variants is deliberate: an A/B that also re-rolls
    its inputs measures the input noise, not the change.
    """
    from drishti_recon import synth
    manifest_path = scene_dir / "scene_manifest.json"
    if manifest_path.exists():
        return json.loads(manifest_path.read_text())
    man = synth.generate(scene_dir, n_frames=frames, fps=10,
                         width=width, height=height, seed=seed, regime=regime,
                         gps_outlier_frac=gps_outlier_frac)
    man["input_sha256"] = {
        "video": _sha256(Path(man["video"])),
        "telemetry": _sha256(Path(man["telemetry"])),
        "ground_truth": _sha256(Path(man["ground_truth"])),
    }
    manifest_path.write_text(json.dumps(man, indent=2))
    return man


def run_cell(scene_dir: Path, work_dir: Path, variant: str, *,
             python: str, max_frames: int, cloud_thr: float,
             timeout: float) -> dict:
    """Run one (variant, regime, seed) cell in an isolated subprocess."""
    work_dir.mkdir(parents=True, exist_ok=True)
    spec = {
        "scene_dir": str(scene_dir),
        "work_dir": str(work_dir),
        "params_override": resolve(variant),
        "max_frames": max_frames,
        "cloud_thr": cloud_thr,
        "do_mesh": False,
        # Leave leveling off for the synthetic matrix: it is a post-alignment
        # transform under active review (see the roadmap's georeferencing item),
        # and enabling it would confound every other comparison.
        "gravity_align": False,
    }
    spec_path = work_dir / "job.json"
    res_path = work_dir / "result.json"
    spec_path.write_text(json.dumps(spec))
    proc = subprocess.run(
        [python, "-m", "eval._bench_worker", str(spec_path), str(res_path)],
        cwd=str(ROOT), capture_output=True, text=True, timeout=timeout)
    if res_path.exists():
        return json.loads(res_path.read_text())
    return {"spec": spec, "status": "crashed",
            "error": f"worker exited {proc.returncode}",
            "traceback": (proc.stderr or "")[-4000:],
            "runtime_s": None, "peak_rss_mb": None}


# --------------------------------------------------------------------------- #
# aggregation + reporting
# --------------------------------------------------------------------------- #
def _cell_metrics(cell: dict) -> dict:
    """Flatten one cell into the comparable metric row."""
    if cell.get("status") != "ok":
        return {"failed": True}
    s = cell["score"]
    rec = (cell.get("report") or {}).get("reconstruction") or {}
    align = (cell.get("report") or {}).get("alignment") or {}
    n_img, n_solved = s.get("n_images") or 0, s.get("n_solved") or 0
    return {
        "failed": False,
        "registered_fraction": rec.get("registered_fraction",
                                       (n_solved / n_img) if n_img else None),
        "ate_rmse": s.get("ate_rmse"),
        "ate_median": s.get("ate_median"),
        "ate_max": s.get("ate_max"),
        "scale_error": s.get("scale_error"),
        "cloud_acc_median": s.get("cloud_acc_median"),
        "cloud_completeness": s.get("cloud_completeness"),
        "dim_error_pct": s.get("dim_error_pct"),
        "median_reproj_err": rec.get("median_reproj_err"),
        "mean_tri_angle": rec.get("mean_tri_angle"),
        "n_points": rec.get("n_points"),
        "align_rmse_3d_m": align.get("alignment_rmse_3d_m"),
        "runtime_s": cell.get("runtime_s"),
        "peak_rss_mb": cell.get("peak_rss_mb"),
    }


def _agg(values: list, metric: str) -> dict:
    """Median and worst case over trials; ``None`` entries are dropped."""
    vals = [v for v in values if v is not None and not (
        isinstance(v, float) and np.isnan(v))]
    if not vals:
        return {"median": None, "worst": None, "n": 0}
    worst = max(vals) if metric in LOWER_IS_BETTER else min(vals)
    return {"median": float(np.median(vals)), "worst": float(worst),
            "n": len(vals)}


def summarize(cells: list[dict]) -> dict:
    """Group cells by (variant, regime) and by variant overall."""
    by_cell: dict = {}
    for c in cells:
        key = (c["variant"], c["regime"])
        by_cell.setdefault(key, []).append(_cell_metrics(c))

    metrics = ["registered_fraction", "ate_rmse", "ate_max", "scale_error",
               "cloud_acc_median", "cloud_completeness", "dim_error_pct",
               "median_reproj_err", "n_points", "runtime_s", "peak_rss_mb"]

    per_cell = {}
    for (variant, regime), rows in sorted(by_cell.items()):
        n_fail = sum(r["failed"] for r in rows)
        per_cell[f"{variant}|{regime}"] = {
            "variant": variant, "regime": regime, "n_trials": len(rows),
            "n_failed": n_fail,
            "failure_rate": n_fail / len(rows) if rows else None,
            **{m: _agg([r.get(m) for r in rows if not r["failed"]], m)
               for m in metrics},
        }

    per_variant = {}
    for variant in sorted({c["variant"] for c in cells}):
        rows = [_cell_metrics(c) for c in cells if c["variant"] == variant]
        n_fail = sum(r["failed"] for r in rows)
        per_variant[variant] = {
            "n_trials": len(rows), "n_failed": n_fail,
            "failure_rate": n_fail / len(rows) if rows else None,
            **{m: _agg([r.get(m) for r in rows if not r["failed"]], m)
               for m in metrics},
        }
    return {"per_cell": per_cell, "per_variant": per_variant}


def _f(v, nd=3, pct=False):
    if v is None:
        return "—"
    return f"{v * 100:.1f}%" if pct else f"{v:.{nd}f}"


def write_markdown(payload: dict, out_dir: Path) -> Path:
    prov = payload["provenance"]
    summ = payload["summary"]
    L: list[str] = []
    L += [
        "# Drishti3D — Ablation Benchmark",
        "",
        f"_Generated {prov['generated_utc']}_",
        "",
        "Every number below was produced by `python -m eval.benchmark` on the "
        "inputs and commit recorded in this file. Numbers are reported as "
        "**median / worst** across trials, because a system intended for field "
        "use is described by its tail, not its best run.",
        "",
        "## Provenance",
        "",
        "| Field | Value |",
        "|---|---|",
        f"| Commit | `{prov['git_commit'][:12] or 'unknown'}`"
        f"{' **(dirty tree — not reproducible from this commit alone)**' if prov['git_dirty'] else ''} |",
        f"| Branch | `{prov['git_branch'] or '—'}` |",
        f"| Python | {prov['python']} |",
        f"| Platform | {prov['platform']} |",
        f"| CPU count | {prov['cpu_count']} |",
        f"| numpy / scipy / OpenCV | {prov['library_versions'].get('numpy')} / "
        f"{prov['library_versions'].get('scipy')} / {prov['library_versions'].get('cv2')} |",
        "",
        "### Inputs",
        "",
        "| Scene | Frames | SHA-256 (video) |",
        "|---|---|---|",
    ]
    for key, man in sorted(payload["scenes"].items()):
        L.append(f"| `{key}` | {man.get('n_frames')} | "
                 f"`{man.get('input_sha256', {}).get('video', '')[:16]}` |")

    L += ["", "## Variants compared", "",
          "| Variant | Description | Parameter overrides |", "|---|---|---|"]
    for v in payload["config"]["variants"]:
        ov = resolve(v)
        L.append(f"| `{v}` | {describe(v)} | "
                 f"`{json.dumps(ov) if ov else '(defaults)'}` |")

    L += ["", "## Overall, per variant (all regimes and seeds pooled)", "",
          "| Variant | Trials | Failed | Reg. frac (med/worst) | ATE RMSE m "
          "(med/worst) | Scale err (med/worst) | Cloud acc m (med/worst) | "
          "Complete (med/worst) | Dim err % (med/worst) | Runtime s (med) | "
          "Peak RSS MB (worst) |",
          "|---|---|---|---|---|---|---|---|---|---|---|"]
    for v, r in payload["summary"]["per_variant"].items():
        L.append(
            f"| `{v}` | {r['n_trials']} | {r['n_failed']} | "
            f"{_f(r['registered_fraction']['median'], pct=True)} / {_f(r['registered_fraction']['worst'], pct=True)} | "
            f"{_f(r['ate_rmse']['median'])} / {_f(r['ate_rmse']['worst'])} | "
            f"{_f(r['scale_error']['median'], 4)} / {_f(r['scale_error']['worst'], 4)} | "
            f"{_f(r['cloud_acc_median']['median'])} / {_f(r['cloud_acc_median']['worst'])} | "
            f"{_f(r['cloud_completeness']['median'], pct=True)} / {_f(r['cloud_completeness']['worst'], pct=True)} | "
            f"{_f(r['dim_error_pct']['median'], 2)} / {_f(r['dim_error_pct']['worst'], 2)} | "
            f"{_f(r['runtime_s']['median'], 1)} | {_f(r['peak_rss_mb']['worst'], 0)} |")

    L += ["", "## Per capture regime", "",
          "The regime is the dominant driver of reconstructability. A variant "
          "that only wins on `orbit` has not been shown to help a real mapping "
          "flight.", "",
          "| Variant | Regime | Trials | Failed | Reg. frac | ATE RMSE m "
          "(med/worst) | Scale err | Cloud acc m | Complete | Dim err % |",
          "|---|---|---|---|---|---|---|---|---|---|"]
    for _, r in sorted(payload["summary"]["per_cell"].items(),
                       key=lambda kv: (kv[1]["regime"], kv[1]["variant"])):
        L.append(
            f"| `{r['variant']}` | `{r['regime']}` | {r['n_trials']} | {r['n_failed']} | "
            f"{_f(r['registered_fraction']['median'], pct=True)} | "
            f"{_f(r['ate_rmse']['median'])} / {_f(r['ate_rmse']['worst'])} | "
            f"{_f(r['scale_error']['median'], 4)} | "
            f"{_f(r['cloud_acc_median']['median'])} | "
            f"{_f(r['cloud_completeness']['median'], pct=True)} | "
            f"{_f(r['dim_error_pct']['median'], 2)} |")

    failures = [c for c in payload["cells"] if c.get("status") != "ok"]
    L += ["", "## Failed cells", ""]
    if failures:
        L.append("| Variant | Regime | Seed | Error |")
        L.append("|---|---|---|---|")
        for c in failures:
            L.append(f"| `{c['variant']}` | `{c['regime']}` | {c['seed']} | "
                     f"`{(c.get('error') or '')[:120]}` |")
    else:
        L.append("- none")

    L += ["", "## How to reproduce", "",
          "```bash",
          f"python -m eval.benchmark --variants {','.join(payload['config']['variants'])} \\",
          f"    --regimes {','.join(payload['config']['regimes'])} \\",
          f"    --seeds {','.join(str(s) for s in payload['config']['seeds'])} \\",
          f"    --frames {payload['config']['frames']} --out <dir>",
          "```", ""]

    path = out_dir / "BENCHMARK.md"
    path.write_text("\n".join(L), encoding="utf-8")
    return path


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #
def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--variants", default="baseline",
                    help=f"comma-separated; known: {','.join(sorted(VARIANTS))}")
    ap.add_argument("--regimes", default=",".join(DEFAULT_REGIMES))
    ap.add_argument("--seeds", default="0,1,2")
    ap.add_argument("--frames", type=int, default=60,
                    help="rendered frames per scene")
    ap.add_argument("--width", type=int, default=960)
    ap.add_argument("--height", type=int, default=540)
    ap.add_argument("--max-frames", type=int, default=400)
    ap.add_argument("--cloud-thr", type=float, default=0.5)
    ap.add_argument("--gps-outlier-frac", type=float, default=0.0,
                    help="fraction of GNSS samples degraded (tests weighted alignment)")
    ap.add_argument("--timeout", type=float, default=1800.0,
                    help="per-cell wall-clock limit, seconds")
    ap.add_argument("--out", default="bench_out")
    ap.add_argument("--scene-cache", default=None,
                    help="reuse rendered scenes across benchmark runs")
    ap.add_argument("--quick", action="store_true",
                    help="small/fast matrix for smoke-testing the harness itself")
    args = ap.parse_args(argv)

    if args.quick:
        args.frames = min(args.frames, 24)
        args.width, args.height = 480, 270

    variants = [v.strip() for v in args.variants.split(",") if v.strip()]
    regimes = [r.strip() for r in args.regimes.split(",") if r.strip()]
    seeds = [int(s) for s in args.seeds.split(",") if s.strip()]
    for v in variants:
        resolve(v)                      # fail fast on a typo'd variant name

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    scene_root = Path(args.scene_cache) if args.scene_cache else out / "scenes"

    prov = collect_provenance()
    (out / "env.lock.txt").write_text(_pip_freeze())

    # 1) render every scene once, shared by all variants
    scenes: dict[str, dict] = {}
    for regime in regimes:
        for seed in seeds:
            key = f"{regime}_s{seed}"
            print(f"[scene] {key} ...", flush=True)
            scenes[key] = _make_scene(
                scene_root / key, regime, seed, frames=args.frames,
                width=args.width, height=args.height,
                gps_outlier_frac=args.gps_outlier_frac)

    # 2) run the matrix
    cells: list[dict] = []
    total = len(variants) * len(regimes) * len(seeds)
    t_start = time.perf_counter()
    i = 0
    for variant in variants:
        for regime in regimes:
            for seed in seeds:
                i += 1
                key = f"{regime}_s{seed}"
                label = f"{variant}/{regime}/seed{seed}"
                print(f"[{i}/{total}] {label} ...", end=" ", flush=True)
                try:
                    cell = run_cell(scene_root / key,
                                    out / "work" / f"{variant}__{key}", variant,
                                    python=sys.executable,
                                    max_frames=args.max_frames,
                                    cloud_thr=args.cloud_thr,
                                    timeout=args.timeout)
                except subprocess.TimeoutExpired:
                    cell = {"status": "timeout",
                            "error": f"exceeded {args.timeout}s",
                            "runtime_s": args.timeout, "peak_rss_mb": None}
                cell.update({"variant": variant, "regime": regime, "seed": seed,
                             "scene": key})
                cells.append(cell)
                m = _cell_metrics(cell)
                if cell.get("status") == "ok":
                    print(f"ok  reg={_f(m['registered_fraction'], pct=True)} "
                          f"ATE={_f(m['ate_rmse'])}m  scale_err={_f(m['scale_error'], 4)} "
                          f"({cell['runtime_s']}s)", flush=True)
                else:
                    print(f"FAILED: {cell.get('error')}", flush=True)

    payload = {
        "provenance": prov,
        "config": {"variants": variants, "regimes": regimes, "seeds": seeds,
                   "frames": args.frames, "width": args.width,
                   "height": args.height, "cloud_thr": args.cloud_thr,
                   "gps_outlier_frac": args.gps_outlier_frac,
                   "max_frames": args.max_frames},
        "scenes": scenes,
        "cells": cells,
        "summary": summarize(cells),
        "total_runtime_s": round(time.perf_counter() - t_start, 1),
    }
    (out / "benchmark.json").write_text(json.dumps(payload, indent=2))
    md = write_markdown(payload, out)
    n_ok = sum(c.get("status") == "ok" for c in cells)
    print(f"\n{n_ok}/{len(cells)} cells succeeded in {payload['total_runtime_s']}s")
    print(f"wrote {md} and {out / 'benchmark.json'}")
    return 0 if n_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
