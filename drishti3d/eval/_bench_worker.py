"""One benchmark cell, executed in its own process.

Run as a subprocess so that (a) a segfault or OOM in one cell cannot take down
the whole matrix, and (b) ``ru_maxrss`` measures *this cell's* peak resident set
rather than the high-water mark of every case run so far in a shared process.

Reads a JSON job spec on argv[1], writes a JSON result to argv[2].
"""
from __future__ import annotations

import json
import resource
import sys
import time
import traceback
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "reconstruction"))
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def main() -> int:
    spec = json.loads(Path(sys.argv[1]).read_text())
    out_path = Path(sys.argv[2])

    result: dict = {"spec": spec}
    t0 = time.perf_counter()
    try:
        from eval.cases import load_case
        from eval.harness import run_case
        from eval.metrics import score_case

        case = load_case(Path(spec["scene_dir"]), kind="synthetic")
        est = run_case(case, Path(spec["work_dir"]),
                       do_mesh=spec.get("do_mesh", False),
                       max_frames=spec.get("max_frames", 400),
                       gravity_align=spec.get("gravity_align"),
                       params_override=spec.get("params_override") or {})
        score = score_case(case, est, cloud_thr=spec.get("cloud_thr", 0.5))
        result["score"] = score.to_dict()
        result["report"] = _slim_report(est.report)
        result["status"] = "ok"
    except Exception as exc:                      # a failed cell is data, not a crash
        result["status"] = "error"
        result["error"] = f"{type(exc).__name__}: {exc}"
        result["traceback"] = traceback.format_exc()[-4000:]

    result["runtime_s"] = round(time.perf_counter() - t0, 2)
    result["peak_rss_mb"] = round(
        resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024.0, 1)
    out_path.write_text(json.dumps(result))
    return 0


def _slim_report(report: dict) -> dict:
    """Keep the report fields a benchmark reader actually compares."""
    if not report:
        return {}
    keep = ("reconstruction", "alignment", "cloud", "timings_s",
            "ground_truth_evaluation", "performance")
    return {k: report[k] for k in keep if k in report}


if __name__ == "__main__":
    raise SystemExit(main())
