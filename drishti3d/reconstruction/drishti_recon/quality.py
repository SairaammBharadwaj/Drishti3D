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
    from .provenance import Provenance
    out = {}
    gt = np.asarray(gt_points_enu, float)
    pts = np.asarray(cloud_enu, float)

    # Score the geometry the product actually stands behind. Including
    # AI-inferred points here makes densification look like an accuracy
    # regression while the measured cloud is untouched: on the single-pass
    # fixture, surface accuracy read 1.847 m over all points against 0.835 m over
    # observed ones. The inferred layer's real contribution is coverage, so it is
    # reported separately rather than mixed into the accuracy headline.
    prov = getattr(cloud_for_measure, "provenance", None)
    measurable = None
    if prov is not None and len(prov) == len(pts):
        measurable = np.isin(np.asarray(prov),
                             [int(Provenance.OBSERVED_HIGH_CONFIDENCE),
                              int(Provenance.OBSERVED_LOW_CONFIDENCE)])

    def _score(sample):
        tree_gt = cKDTree(gt)
        d_ps, _ = tree_gt.query(sample)        # accuracy: recon -> gt
        d_comp, _ = cKDTree(sample).query(gt)  # completeness: gt -> recon
        res = {"surface_accuracy_m": {
            "median": float(np.median(d_ps)),
            "mean": float(np.mean(d_ps)),
            "p90": float(np.percentile(d_ps, 90)),
            "rmse": float(np.sqrt(np.mean(d_ps ** 2))),
        }}
        for tol in (0.5, 1.0, 2.0):
            res[f"completeness_at_{tol}m"] = float((d_comp < tol).mean())
        return res

    if len(pts) and len(gt):
        obs = pts if measurable is None else pts[measurable]
        if len(obs) >= 3:
            out.update(_score(obs))
            out["scored_on"] = ("observed geometry only" if measurable is not None
                                else "all points (no provenance supplied)")
            out["n_scored"] = int(len(obs))
        if measurable is not None and (~measurable).any():
            # What the inferred layer adds, kept clearly separate.
            out["including_inferred"] = _score(pts)
            out["including_inferred"]["n_scored"] = int(len(pts))
            out["including_inferred"]["note"] = (
                "AI-assisted points included. Higher completeness is a real gain "
                "in coverage; the accuracy figure is NOT the product's measured "
                "accuracy and must not be quoted as such.")

    if reference_distances and cloud_for_measure is not None:
        from .measure import measure_distance
        dims = []
        for ref in reference_distances:
            # Measurements must rest on observed geometry. Allowing inferred
            # points here let the headline dimensional accuracy snap to
            # AI-generated surface -- the exact failure the provenance model
            # exists to prevent.
            m = measure_distance(cloud_for_measure, [ref["a"], ref["b"]],
                                 allow_inferred=False)
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


def _uncertainty_stats(cloud, align) -> dict | None:
    """Summarise propagated positional uncertainty over the shipped cloud.

    Reports how much of the cloud is *observable* at all -- a point whose
    uncertainty is infinite was never constrained in depth, and saying so is more
    useful than quietly averaging it away.
    """
    sig = getattr(cloud, "sigma_major", None)
    if sig is None or len(sig) == 0:
        return None
    sig = np.asarray(sig, float)
    finite = np.isfinite(sig)
    out = {
        "n_points": int(len(sig)),
        "n_with_finite_uncertainty": int(finite.sum()),
        "fraction_observable": float(finite.mean()),
        "scale_sigma_relative": (align or {}).get("scale_sigma_relative"),
        "note": ("1-sigma along each point's worst-constrained axis, propagated "
                 "from pixel noise and camera geometry. Pose and systematic "
                 "error are NOT modelled, so these are optimistic until "
                 "calibrated against independent truth."),
    }
    if finite.any():
        f = sig[finite]
        out["sigma_major_m"] = {
            "median": float(np.median(f)),
            "p90": float(np.percentile(f, 90)),
            "max": float(f.max()),
        }
    return out


def build_report(*, video_info, telemetry_report, frame_metrics, keyframe_count,
                 recon_stats, align_result, cloud, timings,
                 gt_eval=None, warnings=None, scale_source="gps",
                 coverage=None, sensors=None, capture_assessment=None,
                 recapture_plan=None, inferred_verification=None) -> dict:
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
        # Uncertainty and conditioning of the fit.  Without these the scale
        # uncertainty never reaches the measurement layer, and a degenerate
        # trajectory looks identical to a well-conditioned one.
        for key in ("normalized_rmse", "scale_sigma", "degenerate",
                    "degeneracy", "conditioning"):
            val = getattr(align_result, key, None)
            if val is not None:
                align[key] = val
        try:
            align["scale_sigma_relative"] = (
                float(align_result.scale_sigma) / float(align_result.transform.scale))
        except Exception:
            align["scale_sigma_relative"] = None
    proc_time = sum(timings.values())
    ratio = proc_time / video_info.duration if video_info.duration else None
    return {
        "input": {
            "video": video_info.to_dict(),
            "telemetry": {
                "n_valid": telemetry_report.n_valid,
                "warnings": telemetry_report.warnings,
                "has_rtk": telemetry_report.has_rtk,
                "vertical_datum": telemetry_report.vertical_datum,
                "vertical_datum_basis": telemetry_report.vertical_datum_basis,
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
        "uncertainty": _uncertainty_stats(cloud, align),
        "coverage": coverage,
        "sensors": sensors,
        "capture_assessment": capture_assessment,
        "recapture_plan": recapture_plan,
        "inferred_verification": inferred_verification,
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
