#!/usr/bin/env python3
"""Populate a project's Tolerance Lens with measurement questions.

The measurement comparisons in the benchmark record were computed offline,
against `drishti_recon` directly. That leaves the workspace showing an empty
Lens for a reconstruction whose whole point is that it can now be measured, so
the UI understates what the pipeline does.

This samples point pairs from a project's own cloud -- endpoints that are
observed, in coverage, and separated by a spread of baselines -- and asks each
one through the HTTP API, so every result is computed by the same code path the
operator's own clicks would take. Nothing here computes a measurement itself.

Pairs are drawn with a fixed seed, so re-running with the same arguments asks
the same questions again. Pairs come from each project's own cloud, so two
projects built from one flight get comparable bands of baseline, not identical
endpoints.

Usage:
  python scripts/seed_questions.py --project <id> --count 24
"""
from __future__ import annotations

import argparse
import sys
import urllib.error
import urllib.request
import json
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parents[2]
APP = REPO / "drishti3d"
sys.path.insert(0, str(APP / "reconstruction"))

# Baseline bands, in metres, with the tolerance an operator would plausibly
# demand of each. A 3 m span checked to +/-50 mm is a different question from a
# 50 m span checked to +/-500 mm, and the Lens should show both.
BANDS = [
    ("short", 2.0, 6.0, 0.05),
    ("mid", 6.0, 18.0, 0.15),
    ("long", 18.0, 60.0, 0.50),
]


def post(base: str, path: str, body: dict) -> dict:
    req = urllib.request.Request(
        base + path, method="POST",
        data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=300) as r:
        return json.loads(r.read())


def get(base: str, path: str):
    with urllib.request.urlopen(base + path, timeout=300) as r:
        return json.loads(r.read())


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--project", required=True)
    ap.add_argument("--api", default="http://127.0.0.1:8000")
    ap.add_argument("--count", type=int, default=24,
                    help="questions to ask, split evenly across bands")
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--pool", type=int, default=4000,
                    help="candidate points to consider")
    a = ap.parse_args()

    from drishti_recon.evidence import ReconstructionEvidence

    art = APP / "data/projects" / a.project / "artifacts"
    if not art.is_dir():
        raise SystemExit(f"no artifacts at {art}")

    ev = ReconstructionEvidence.load(art)
    pts = np.load(art / "cloud.npz")["points"]
    rng = np.random.default_rng(a.seed)

    # Only endpoints the system can actually stand behind: seen by at least two
    # images, and inside the coverage volume. Sampling blind would mostly ask
    # about points the gate refuses for reasons that say nothing about geometry.
    pool = rng.choice(len(pts), min(a.pool, len(pts)), replace=False)
    good = [int(i) for i in pool
            if len(ev.observations_of(pts[i])["frame_index"]) >= 2
            and ev.within_coverage(pts[i])]
    if len(good) < 4:
        raise SystemExit(f"only {len(good)} measurable points found; "
                         "is this reconstruction georeferenced?")
    print(f"{len(good)} measurable endpoints from a pool of {len(pool)}")

    gp = pts[good]
    per_band = max(1, a.count // len(BANDS))
    asked = 0
    for name, lo, hi, tol in BANDS:
        made = 0
        order = rng.permutation(len(good))
        for i in order:
            if made >= per_band:
                break
            d = np.linalg.norm(gp - gp[i], axis=1)
            cand = np.flatnonzero((d > lo) & (d < hi))
            if not len(cand):
                continue
            j = int(cand[rng.integers(len(cand))])
            p, q = gp[i], gp[j]
            label = f"{name} span {made + 1} — {np.linalg.norm(p - q):.1f} m nominal"
            try:
                res = post(a.api, f"/api/projects/{a.project}/questions", {
                    "kind": "distance",
                    "points": [p.tolist(), q.tolist()],
                    "tolerance_m": tol,
                    "label": label,
                })
            except urllib.error.HTTPError as e:
                print(f"  ! {label}: HTTP {e.code} {e.read()[:200]!r}")
                continue
            r = res.get("result") or {}
            val, hw = r.get("value"), r.get("interval_half_width")
            shown = "—" if val is None else f"{val:.3f} m"
            band = "" if hw is None else f" +/-{hw:.3f}"
            print(f"  {label}: {shown}{band}  {r.get('status')} "
                  f"[{','.join(r.get('status_reasons') or [])}]")
            made += 1
            asked += 1

    qs = get(a.api, f"/api/projects/{a.project}/questions")
    from collections import Counter
    tally = Counter((q.get("result") or {}).get("status", "no result") for q in qs)
    print(f"\nasked {asked}; project now holds {len(qs)} questions")
    for k, v in tally.most_common():
        print(f"  {k:24} {v}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
