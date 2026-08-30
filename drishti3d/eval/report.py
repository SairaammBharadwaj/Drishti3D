"""Render scored cases into a JSON blob and a Markdown scorecard."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from .metrics import CaseScore

PRIORITY = {
    "odm": ("OpenDroneMap / ODMData", "Real aerial reconstruction", "#1"),
    "tartanair": ("TartanAir", "Depth / SLAM / AI testing", "#2"),
    "eth3d": ("ETH3D", "SLAM / reconstruction benchmark", "#3"),
    "tum": ("AGI2P / RTK-SLAM (TUM)", "Aerial localization / cloud eval", "#4"),
    "synthetic": ("Synthetic (held-in GT)", "Harness self-test", "self-test"),
}


def _fmt(v, unit="", nd=3):
    return "—" if v is None else f"{v:.{nd}f}{unit}"


def write_report(scores: list[CaseScore], out_dir: str | Path) -> dict:
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "generated": datetime.now(timezone.utc).isoformat(),
        "cases": [s.to_dict() for s in scores],
    }
    (out_dir / "eval_report.json").write_text(json.dumps(payload, indent=2))

    lines = [
        "# Drishti3D — Ground-Truth Evaluation Scorecard",
        "",
        f"_Generated {payload['generated']}_",
        "",
        "All spatial errors are reported **after a Sim(3) alignment** of estimated",
        "to ground-truth camera centres (the standard ATE protocol). Ground-truth",
        "poses are never fed to the pipeline; datasets without real GPS are anchored",
        "with **synthesised drone-grade noisy GPS**, so these numbers reflect the",
        "conditions of a real single-pass flight.",
        "",
        "| Dataset | Case | Cams (solved/GT) | ATE RMSE | ATE med | Scale err | "
        "Cloud acc (med) | Completeness | Dim err |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    for s in scores:
        label = PRIORITY.get(s.kind, (s.kind, "", ""))[0]
        comp = None if s.cloud_completeness is None else s.cloud_completeness * 100
        lines.append(
            f"| {label} | `{s.name}` | {s.n_solved}/{s.n_matched} | "
            f"{_fmt(s.ate_rmse,' m')} | {_fmt(s.ate_median,' m')} | "
            f"{_fmt(s.scale_error,'',4)} | {_fmt(s.cloud_acc_median,' m')} | "
            f"{_fmt(comp,'%',1)} | {_fmt(s.dim_error_pct,'%',2)} |"
        )
    lines += ["", "## Notes / warnings", ""]
    any_w = False
    for s in scores:
        for w in s.warnings:
            lines.append(f"- `{s.name}`: {w}")
            any_w = True
    if not any_w:
        lines.append("- none")
    lines.append("")
    (out_dir / "eval_scorecard.md").write_text("\n".join(lines), encoding="utf-8")
    return payload


def print_summary(scores: list[CaseScore]) -> None:
    for s in scores:
        print(f"[{s.name}] solved {s.n_solved}/{s.n_matched}  "
              f"ATE_rmse={_fmt(s.ate_rmse,'m')}  scale_err={_fmt(s.scale_error,'',4)}  "
              f"cloud_med={_fmt(s.cloud_acc_median,'m')}  "
              f"complete={_fmt((s.cloud_completeness or 0)*100 if s.cloud_completeness is not None else None,'%',1)}")
