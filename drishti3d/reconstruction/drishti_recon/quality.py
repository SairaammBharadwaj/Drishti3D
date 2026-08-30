"""Quality, confidence and (optional) ground-truth evaluation metrics.

Never confuses GPS alignment residual with independent accuracy: alignment
residual and independent-checkpoint error are reported separately.
"""
from __future__ import annotations

import numpy as np


def cloud_stats(cloud) -> dict:
    if len(cloud) == 0:
        return {"n_points": 0}
    pts = cloud.points
    mn = pts.min(0)
    mx = pts.max(0)
    # point density estimate via nearest-neighbour spacing on a sample
    from scipy.spatial import cKDTree
    sample = pts[np.random.default_rng(0).choice(len(pts), min(2000, len(pts)),
                                                  replace=False)]
    tree = cKDTree(pts)
    d, _ = tree.query(sample, k=2)
    spacing = float(np.median(d[:, 1]))
    return {
        "n_points": len(cloud),
        "bbox_min": mn.tolist(), "bbox_max": mx.tolist(),
        "dimensions_m": (mx - mn).tolist(),
        "median_point_spacing_m": spacing,
        "class_counts": cloud.class_counts(),
        "class_fractions": {k: v / len(cloud) for k, v in cloud.class_counts().items()},
    }


def evaluate_against_ground_truth(cloud_enu, gt_points_enu,
                                  reference_distances=None,
                                  cloud_for_measure=None) -> dict:
    """Independent evaluation when a ground-truth fixture is available.

    Computes cloud-to-surface accuracy/completeness and dimensional error on
    known reference distances (measured on the reconstruction, compared to truth).
    """
    from scipy.spatial import cKDTree
    out = {}
    gt = np.asarray(gt_points_enu, float)
    pts = np.asarray(cloud_enu, float)
    if len(pts) and len(gt):
        tree_gt = cKDTree(gt)
        d_ps, _ = tree_gt.query(pts)          # accuracy: recon -> gt
        tree_ps = cKDTree(pts)
        d_comp, _ = tree_ps.query(gt)         # completeness: gt -> recon
        out["surface_accuracy_m"] = {
            "median": float(np.median(d_ps)),
            "mean": float(np.mean(d_ps)),
            "p90": float(np.percentile(d_ps, 90)),
            "rmse": float(np.sqrt(np.mean(d_ps ** 2))),
        }
        for tol in (0.5, 1.0, 2.0):
            out[f"completeness_at_{tol}m"] = float((d_comp < tol).mean())

    if reference_distances and cloud_for_measure is not None:
        from .measure import measure_distance
        dims = []
        for ref in reference_distances:
            m = measure_distance(cloud_for_measure, [ref["a"], ref["b"]],
                                 allow_inferred=True)
            truth = ref["meters"]
            err = m.value - truth if m.value is not None else None
            dims.append({
                "name": ref["name"], "truth_m": truth,
                "measured_m": m.value,
                "abs_error_m": abs(err) if err is not None else None,
                "pct_error": (abs(err) / truth * 100) if err else None,
            })
        out["dimensional_accuracy"] = dims
    return out


def build_report(*, video_info, telemetry_report, frame_metrics, keyframe_count,
                 recon_stats, align_result, cloud, timings,
                 gt_eval=None, warnings=None, scale_source="gps") -> dict:
    """Assemble the full quality/evidence report (JSON-serialisable)."""
    accepted = sum(1 for m in frame_metrics if m.accepted)
    total = len(frame_metrics)
    align = None
    if align_result is not None:
        align = {
            "scale": float(align_result.transform.scale),
            "n_inliers": align_result.n_inliers,
            "n_total": align_result.n_total,
            "alignment_rmse_3d_m": align_result.rmse,
            "alignment_rmse_horizontal_m": align_result.rmse_h,
            "alignment_rmse_vertical_m": align_result.rmse_v,
            "scale_source": scale_source,
            "note": ("Alignment residual is NOT independent accuracy; it measures "
                     "consistency between reconstructed camera centres and GPS."),
        }
    proc_time = sum(timings.values())
    ratio = proc_time / video_info.duration if video_info.duration else None
    return {
        "input": {
            "video": video_info.to_dict(),
            "telemetry": {
                "n_valid": telemetry_report.n_valid,
                "warnings": telemetry_report.warnings,
                "has_rtk": telemetry_report.has_rtk,
            },
            "scale_source": scale_source,
        },
        "frames": {
            "total_analyzed": total,
            "accepted": accepted,
            "rejected": total - accepted,
            "accepted_fraction": accepted / total if total else None,
            "keyframes": keyframe_count,
        },
        "reconstruction": recon_stats,
        "cloud": cloud_stats(cloud),
        "alignment": align,
        "timings_s": timings,
        "performance": {
            "processing_time_s": proc_time,
            "video_duration_s": video_info.duration,
            "processing_to_video_ratio": ratio,
        },
        "ground_truth_evaluation": gt_eval,
        "warnings": warnings or [],
        "limitations": [
            "Monocular single-pass video cannot measure surfaces never observed.",
            "Absolute accuracy is GPS-limited unless RTK/PPK or GCPs are provided.",
            "AI-assisted geometry is excluded from measurement by default.",
            "Alignment residual is not a certified accuracy statement.",
        ],
    }
