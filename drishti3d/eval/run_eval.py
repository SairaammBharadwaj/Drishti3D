"""CLI: run the Drishti3D pipeline on ground-truth datasets and score it.

Examples
--------
    # score every dataset folder under ./eval_data (auto-detected)
    python -m eval.run_eval --root eval_data --out eval_out

    # a single dataset with an explicit kind and frame subsampling
    python -m eval.run_eval --dataset path/to/tartanair/P001 --kind tartanair --stride 2

    # the no-download self-test on the bundled synthetic scene
    python -m eval.run_eval --self-test
"""
from __future__ import annotations

import argparse
import sys
import tempfile
from pathlib import Path

# allow running both as `python -m eval.run_eval` and `python eval/run_eval.py`
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "reconstruction"))

from eval.cases import load_case, detect_dataset            # noqa: E402
from eval.harness import run_case                             # noqa: E402
from eval.metrics import score_case                           # noqa: E402
from eval.report import write_report, print_summary          # noqa: E402


def _progress(stage, frac, msg=""):
    sys.stdout.write(f"\r  {stage:<12} {frac*100:5.1f}%  {msg[:40]:<40}")
    sys.stdout.flush()


def _score_one(root: Path, out: Path, args) -> object:
    case = load_case(root, stride=args.stride, kind=args.kind)
    print(f"\n== {case.name}  ({case.n or 'video'} frames, "
          f"real_gps={case.has_real_gps}) ==")
    work = out / "work" / _safe(case.name)
    est = run_case(case, work, fps=args.fps, gps_sigma_h=args.gps_sigma,
                   gps_sigma_v=args.gps_sigma * 1.6, do_mesh=args.mesh,
                   max_frames=args.max_frames,
                   progress=_progress if not args.quiet else None)
    print()
    return score_case(case, est, cloud_thr=args.cloud_thr)


def _safe(name: str) -> str:
    return "".join(c if c.isalnum() else "_" for c in name)


def main(argv=None):
    ap = argparse.ArgumentParser(description="Drishti3D ground-truth evaluation")
    src = ap.add_mutually_exclusive_group(required=True)
    src.add_argument("--root", help="folder containing one or more dataset dirs")
    src.add_argument("--dataset", help="a single dataset directory")
    src.add_argument("--self-test", action="store_true",
                     help="build a synthetic GT scene and evaluate it (no download)")
    ap.add_argument("--kind", default=None,
                    help="odm|tartanair|eth3d|tum|synthetic (else auto-detect)")
    ap.add_argument("--out", default="eval_out")
    ap.add_argument("--stride", type=int, default=1)
    ap.add_argument("--fps", type=float, default=5.0)
    ap.add_argument("--gps-sigma", type=float, default=2.5,
                    help="synthesised GPS horizontal sigma (m) for no-GPS datasets")
    ap.add_argument("--cloud-thr", type=float, default=0.5,
                    help="completeness distance threshold (m)")
    ap.add_argument("--max-frames", type=int, default=400)
    ap.add_argument("--mesh", action="store_true")
    ap.add_argument("--quiet", action="store_true")
    args = ap.parse_args(argv)

    out = Path(args.out)
    scores = []

    if args.self_test:
        roots = [_make_synthetic(out)]
    elif args.dataset:
        roots = [Path(args.dataset)]
    else:
        root = Path(args.root)
        roots = [p for p in sorted(root.iterdir()) if p.is_dir()
                 and _detectable(p)]
        if not roots and _detectable(root):
            roots = [root]
        if not roots:
            ap.error(f"no detectable dataset dirs under {root}")

    for r in roots:
        try:
            scores.append(_score_one(r, out, args))
        except Exception as e:
            print(f"\n  !! {r.name}: {type(e).__name__}: {e}")

    if not scores:
        print("no cases scored")
        return 1
    write_report(scores, out)
    print(f"\n=== summary ({len(scores)} case(s)) ===")
    print_summary(scores)
    print(f"\nwrote {out/'eval_scorecard.md'} and {out/'eval_report.json'}")
    return 0


def _detectable(p: Path) -> bool:
    try:
        detect_dataset(p)
        return True
    except Exception:
        return False


def _make_synthetic(out: Path) -> Path:
    """Render a small synthetic GT scene for the self-test."""
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "reconstruction"))
    from drishti_recon import synth
    scene = out / "synthetic_scene"
    scene.mkdir(parents=True, exist_ok=True)
    # Match the product's recommended capture profile (the canonical demo):
    # a longer pass gives real triangulation baseline. Short clips undersample
    # depth (height error blows up) even when GPS pins the camera centres.
    synth.generate(scene, n_frames=90, fps=30)
    return scene


if __name__ == "__main__":
    raise SystemExit(main())
