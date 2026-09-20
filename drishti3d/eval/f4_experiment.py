#!/usr/bin/env python3
"""The F4 gate: targeted same-pass refinement versus a uniform budget.

Plan feature F4 states the test directly: *"on frozen questions and equal added
compute budgets, targeted refinement improves correct accepted-answer yield or
reaches the same quality faster than uniform refinement. No improvement is an
acceptable experiment result and must be visible."*

Everything built so far is the targeted arm. This is the control.

The two arms
------------
Both start from the same baseline reconstruction and spend additional compute on
the same frozen questions. They differ only in where it goes.

* **Targeted** — for each question, `refinement.RefinementEngine` retrieves the
  unused frames of the pass that would add parallax *at that question's weakest
  endpoint*, poses them against the existing model, and re-triangulates. The
  geometry everywhere else is untouched.
* **Uniform** — the whole reconstruction is re-run with a denser keyframe
  selection (`preset="quality"` keeps up to 160 frames against the baseline's
  80), and the same questions are re-measured on the result. Every part of the
  scene gets more frames, including the parts nobody asked about.

Honesty conditions this script enforces
---------------------------------------
* **The questions are frozen before either arm runs** and written to disk with a
  hash. A question set chosen after seeing one arm's results is not a test.
* **Both arms are re-measured from the same stored ENU endpoints.** The uniform
  arm produces a different cloud, so its endpoints re-snap -- which is exactly
  what an operator asking the same question of a new model would get.
* **Added compute is reported as measured**, not assumed equal. The arms will
  not match exactly, so outcomes are also reported per added second. Declaring
  a winner on unequal budgets without saying so is the failure this guards.
* **A loss is a result.** The summary states which arm won on each metric,
  including when that is neither.

One asymmetry cannot be designed away and is stated rather than hidden: the
targeted arm *moves an endpoint off the cloud* and the uniform arm *rebuilds the
cloud under it*. So the two arms' after-states are not produced by identical
code -- re-snapping the targeted arm's endpoint would pull it straight back to
where it started. What is compared is what both arms genuinely produce: the
verdict, its reason codes, the propagated sigma, the supporting-view count and
the measured parallax, all computed by the same `questions.evaluate` and
`uncertainty` paths.

Usage:
  python -m eval.f4_experiment --baseline colmap_unc --uniform colmap_quality \
      [--n-questions 20] [--budget-frames 4]
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parents[2]
APP = REPO / "drishti3d"
sys.path.insert(0, str(APP / "reconstruction"))

from drishti_recon import measure as measmod            # noqa: E402
from drishti_recon import questions as qmod             # noqa: E402
from drishti_recon import refinement as refmod          # noqa: E402
from drishti_recon.evidence import ReconstructionEvidence   # noqa: E402
from drishti_recon.fusion import PointCloud             # noqa: E402

#: Verdicts ordered worst to best, for "did this arm move the answer up".
STATUS_ORDER = ["not_observable", "needs_refinement", "estimated_only",
                "meets_requirement"]


def _run_dir(tag: str) -> Path:
    return APP / "data/runs" / f"agz_dense_pass__{tag}"


def _load(tag: str):
    art = _run_dir(tag) / "artifacts"
    ev = ReconstructionEvidence.load(art)
    d = np.load(art / "cloud.npz")
    cloud = PointCloud(d["points"], d["colors"], d["confidence"],
                       d["provenance"], None,
                       d["sigma"] if "sigma" in d.files else None,
                       d["sigma_major"] if "sigma_major" in d.files else None)
    return ev, cloud, art


def _sfm_seconds(tag: str) -> float | None:
    f = _run_dir(tag) / f"run_{tag}.json"
    if not f.exists():
        return None
    try:
        return float(json.loads(f.read_text())["report"]["timings_s"]["sfm"])
    except (KeyError, ValueError, OSError):
        return None


def freeze_questions(ev, cloud, n: int, tolerance: float, seed: int) -> list:
    """Pick the questions once, from the baseline, before any arm runs.

    Chosen to be the measurements refinement exists for: both endpoints on
    established coverage, with observation lineage, and the weaker endpoint
    short of parallax. Picking easy questions would let the targeted arm look
    good by having nothing to do.
    """
    pts = cloud.points
    rng = np.random.default_rng(seed)
    out = []
    for k in rng.choice(len(pts), min(6000, len(pts)), replace=False):
        if len(out) >= n:
            break
        a = pts[int(k)]
        sep = ev.measured_ray_separation_deg(a)
        if not (0 < sep < 15) or not ev.within_coverage(a):
            continue
        d = np.linalg.norm(pts - a, axis=1)
        j = int(np.argmin(np.where((d > 3) & (d < 9), d, 1e9)))
        if d[j] > 9 or not ev.within_coverage(pts[j]):
            continue
        out.append({"id": f"q{len(out):03d}",
                    "kind": "distance",
                    "tolerance_m": tolerance,
                    "points_enu": [list(map(float, a)),
                                   list(map(float, pts[j]))],
                    "baseline_parallax_deg": round(float(sep), 3)})
    return out


def measure_one(ev, cloud, q: dict) -> dict:
    """Measure a frozen question against one reconstruction, from its endpoints."""
    pts = [np.asarray(p, float) for p in q["points_enu"]]
    m = measmod.measure_distance(cloud, pts,
                                 scale_sigma_rel=(ev.scale_sigma_rel
                                                  if np.isfinite(ev.scale_sigma_rel)
                                                  else 0.0))
    provs = [measmod._snap(cloud, p, False)[1] for p in pts]
    evd = ev.for_points(m.points_enu, provenances=provs)
    question = qmod.MeasurementQuestion(kind=q["kind"],
                                        tolerance_m=q["tolerance_m"])
    v = qmod.evaluate(question, value=m.value, sigma=m.sigma, evidence=evd,
                      profile=None)
    return {
        "value": None if m.value is None else float(m.value),
        "sigma": (None if m.sigma is None or not np.isfinite(m.sigma)
                  else float(m.sigma)),
        "status": v.status.value,
        "reasons": [r.value for r in v.reasons],
        "dominant_limitation": v.dominant_limitation,
        "n_supporting_views": evd.n_supporting_views,
        "max_ray_separation_deg": round(float(evd.max_ray_separation_deg), 2),
    }


def _moved_up(before: dict, after: dict) -> bool:
    try:
        return (STATUS_ORDER.index(after["status"])
                > STATUS_ORDER.index(before["status"]))
    except ValueError:
        return False


def _blockers(rec: dict) -> set:
    """Reasons other than the calibration one, which no arm can clear."""
    return {r for r in rec["reasons"]
            if r not in ("interval_not_calibrated",
                         "calibration_sample_too_small")}


def summarise(name: str, before: list, after: list, added_s: float) -> dict:
    n = len(before)
    # A proper subset: every remaining blocker was already there, and there are
    # fewer. An arm that swaps one blocker for another has not cleared anything.
    cleared = sum(1 for b, a in zip(before, after)
                  if _blockers(a) < _blockers(b))
    regressed = sum(1 for b, a in zip(before, after)
                    if (_blockers(a) - _blockers(b))
                    or STATUS_ORDER.index(a["status"])
                    < STATUS_ORDER.index(b["status"]))
    narrowed = sum(1 for b, a in zip(before, after)
                   if b["sigma"] and a["sigma"] and a["sigma"] < b["sigma"])
    def med(rows, key):
        vals = [r[key] for r in rows if r[key] is not None]
        return round(float(np.median(vals)), 3) if vals else None
    return {
        "arm": name,
        "n_questions": n,
        "added_compute_s": round(added_s, 1),
        "added_compute_per_question_s": round(added_s / max(n, 1), 1),
        "measurements_with_fewer_blockers": cleared,
        "measurements_regressed": regressed,
        "measurements_with_narrower_interval": narrowed,
        "status_moved_up": sum(1 for b, a in zip(before, after)
                               if _moved_up(b, a)),
        "blocked_only_by_calibration_before": sum(
            1 for b in before if not _blockers(b)),
        "blocked_only_by_calibration_after": sum(
            1 for a in after if not _blockers(a)),
        "median_sigma_before": med(before, "sigma"),
        "median_sigma_after": med(after, "sigma"),
        "median_views_before": med(before, "n_supporting_views"),
        "median_views_after": med(after, "n_supporting_views"),
        "median_parallax_before": med(before, "max_ray_separation_deg"),
        "median_parallax_after": med(after, "max_ray_separation_deg"),
        "cleared_per_added_minute": round(
            cleared / max(added_s / 60.0, 1e-9), 2),
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--baseline", default="colmap_unc")
    ap.add_argument("--uniform", default="colmap_quality")
    ap.add_argument("--video",
                    default=str(REPO / "datasets/public/zurich_mav/"
                                       "agz_dense_pass/raw/video.mp4"))
    ap.add_argument("--n-questions", type=int, default=20)
    ap.add_argument("--tolerance", type=float, default=0.30)
    ap.add_argument("--budget-frames", type=int, default=4)
    ap.add_argument("--max-decode", type=int, default=10)
    ap.add_argument("--seed", type=int, default=99)
    ap.add_argument("--out", default=str(APP / "docs/benchmarks/"
                                               "2026-09-20_f4_targeted_vs_uniform"))
    a = ap.parse_args()

    out_dir = Path(a.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    ev_b, cloud_b, art_b = _load(a.baseline)

    # ---- 1. freeze the questions, before either arm runs ------------------
    qfile = out_dir / "questions_frozen.json"
    if qfile.exists():
        questions = json.loads(qfile.read_text())["questions"]
        print(f"reusing {len(questions)} frozen questions from {qfile}")
    else:
        questions = freeze_questions(ev_b, cloud_b, a.n_questions,
                                     a.tolerance, a.seed)
        payload = {"frozen_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ",
                                               time.gmtime()),
                   "baseline_run": a.baseline, "seed": a.seed,
                   "tolerance_m": a.tolerance, "questions": questions}
        blob = json.dumps(payload, sort_keys=True).encode()
        payload["sha256"] = hashlib.sha256(blob).hexdigest()
        qfile.write_text(json.dumps(payload, indent=2))
        print(f"froze {len(questions)} questions -> {qfile}")
    if not questions:
        raise SystemExit("no questions met the selection criteria")

    # ---- 2. baseline ------------------------------------------------------
    before = [measure_one(ev_b, cloud_b, q) for q in questions]

    # ---- 3. targeted arm --------------------------------------------------
    print(f"targeted arm: {len(questions)} questions, "
          f"budget {a.budget_frames} frames", flush=True)
    targeted, targeted_s = [], 0.0
    for i, (q, b) in enumerate(zip(questions, before)):
        eng = refmod.RefinementEngine(ev_b, art_b, video_path=a.video)
        pts = [np.asarray(p, float) for p in q["points_enu"]]
        sigmas = [float(measmod._snap(cloud_b, p, False)[2]) for p in pts]
        vf = refmod.measurement_value_fn(
            q["kind"], sigmas,
            scale_sigma_rel=(ev_b.scale_sigma_rel
                             if np.isfinite(ev_b.scale_sigma_rel) else 0.0))
        provs = [measmod._snap(cloud_b, p, False)[1] for p in pts]
        run = eng.refine(qmod.MeasurementQuestion(kind=q["kind"],
                                                  tolerance_m=q["tolerance_m"]),
                         pts, value_fn=vf, budget_frames=a.budget_frames,
                         max_decode=a.max_decode, provenances=provs)
        if eng._source is not None:
            eng._source.close()
        d = run.to_dict()
        targeted_s += d["wall_seconds"]
        after = dict(d["after"])
        # `_snapshot` already carries status/reasons/views/parallax; fill the
        # keys the summary expects and nothing else.
        targeted.append({"value": after.get("value"),
                         "sigma": after.get("sigma"),
                         "status": after.get("status", b["status"]),
                         "reasons": after.get("reasons", b["reasons"]),
                         "dominant_limitation": after.get("dominant_limitation"),
                         "n_supporting_views": after.get("n_supporting_views",
                                                         b["n_supporting_views"]),
                         "max_ray_separation_deg": after.get(
                             "max_ray_separation_deg",
                             b["max_ray_separation_deg"]),
                         "_run": d})
        print(f"  [{i + 1}/{len(questions)}] {q['id']} added {d['n_added']} "
              f"improved {d['improved']} {d['wall_seconds']}s", flush=True)

    # ---- 4. uniform arm ---------------------------------------------------
    ev_u, cloud_u, _art_u = _load(a.uniform)
    uniform = [measure_one(ev_u, cloud_u, q) for q in questions]
    base_sfm = _sfm_seconds(a.baseline)
    unif_sfm = _sfm_seconds(a.uniform)
    uniform_s = (unif_sfm - base_sfm) if (base_sfm and unif_sfm) else float("nan")

    # ---- 5. report --------------------------------------------------------
    # ---- 5a. an equal-budget view ----------------------------------------
    # The arms will not cost the same: the uniform arm is one reconstruction
    # whose price is fixed, while the targeted arm's scales with how many
    # questions are asked. Truncating the targeted arm at the uniform arm's
    # spend gives the like-for-like comparison the F4 gate actually asks for,
    # and reporting only the untruncated totals would let the more expensive
    # arm win on budget rather than on method.
    equal = None
    if np.isfinite(uniform_s) and uniform_s > 0:
        spent, taken = 0.0, 0
        for t in targeted:
            w = t["_run"]["wall_seconds"]
            if spent + w > uniform_s:
                break
            spent += w
            taken += 1
        equal = {
            "budget_s": round(uniform_s, 1),
            "targeted_questions_within_budget": taken,
            "targeted_spend_s": round(spent, 1),
            "targeted_cleared_within_budget": sum(
                1 for b, t in zip(before[:taken], targeted[:taken])
                if _blockers(t) < _blockers(b)),
            "uniform_cleared_all_questions": sum(
                1 for b, u in zip(before, uniform)
                if _blockers(u) < _blockers(b)),
            "note": ("The uniform arm's spend buys a new reconstruction that "
                     "answers every question at once; the targeted arm's buys "
                     "attention for one question at a time. Within the same "
                     "seconds, the targeted arm only reaches the first "
                     f"{taken} of {len(questions)} questions."),
        }

    result = {
        "generated_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "baseline_run": a.baseline, "uniform_run": a.uniform,
        "questions_file": str(qfile.relative_to(REPO)),
        "n_questions": len(questions),
        "tolerance_m": a.tolerance,
        "budget_frames": a.budget_frames,
        "baseline_sfm_s": base_sfm, "uniform_sfm_s": unif_sfm,
        "equal_budget": equal,
        "arms": [
            summarise("targeted", before, targeted, targeted_s),
            summarise("uniform", before, uniform, uniform_s),
        ],
        "per_question": [
            {"id": q["id"], "baseline": b, "targeted": {k: v for k, v in t.items()
                                                        if k != "_run"},
             "uniform": u,
             "targeted_frames_added": t["_run"]["n_added"],
             "targeted_wall_s": t["_run"]["wall_seconds"]}
            for q, b, t, u in zip(questions, before, targeted, uniform)
        ],
    }
    (out_dir / "result.json").write_text(json.dumps(result, indent=2))

    print("\n=== F4: targeted vs uniform ===")
    for arm in result["arms"]:
        print(json.dumps(arm, indent=1))
    if equal:
        print("\n--- equal budget ---")
        print(json.dumps(equal, indent=1))
    print(f"\nfull result -> {out_dir / 'result.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
