"""Generate the bundled synthetic single-pass drone dataset.

Usage:
    python sample_data/generate_sample.py [out_dir] [--frames N]

Produces a video, telemetry CSV, and ground-truth JSON with known geometry so
the pipeline can compute *real* accuracy.  No network or external assets needed.
"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "reconstruction"))
from drishti_recon import synth  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("out_dir", nargs="?", default="sample_data/synthetic")
    ap.add_argument("--frames", type=int, default=90)
    ap.add_argument("--fps", type=int, default=30)
    args = ap.parse_args()
    manifest = synth.generate(args.out_dir, n_frames=args.frames, fps=args.fps)
    print(json.dumps(manifest, indent=2))
    print(f"\nSample dataset written to {args.out_dir}")


if __name__ == "__main__":
    main()
