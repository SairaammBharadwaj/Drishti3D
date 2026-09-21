"""One definition of what a stored measurement means.

There used to be two. ``POST /measurements`` computed a length without passing
scale uncertainty, without checking that metric scale existed at all, and
persisted a row with ``sigma`` NULL, no interval basis, no acceptance status
and no artifact identity -- while ``POST /questions`` computed the same
geometry with scale propagated and stored the full verdict. An operator could
therefore read a bare number in metres out of a reconstruction whose scale was
arbitrary, through a route that looked just as official as the other one.

The gate was never accepting bad measurements; the product simply had two
incompatible answers to "what is a measurement". This module is the single
answer. Both routes call :func:`compute` and store every column it returns.
"""
from __future__ import annotations

import json

import numpy as np
from fastapi import HTTPException

from . import storage

from drishti_recon import measure as measmod
from drishti_recon import questions as qmod
from drishti_recon.evidence import ReconstructionEvidence

#: Keyed by (project_id, artifact revision) -- see storage.artifact_revision.
_evidence_cache: dict = {}


def invalidate(project_id: str) -> None:
    for k in [k for k in _evidence_cache if k[0] == project_id]:
        _evidence_cache.pop(k, None)


def evidence_for(project_id: str) -> ReconstructionEvidence | None:
    key = (project_id, storage.artifact_revision(project_id))
    if key in _evidence_cache:
        return _evidence_cache[key]
    for k in [k for k in _evidence_cache if k[0] == project_id]:
        _evidence_cache.pop(k, None)
    art = storage.artifacts_dir(project_id)
    # Without a trajectory there are no camera poses, so nothing can be said
    # about view support -- and an unknown must not be scored as adequate.
    if not (art / "trajectory.json").exists():
        return None
    try:
        ev = ReconstructionEvidence.load(art)
    except (OSError, ValueError, KeyError):
        return None
    _evidence_cache[key] = ev
    return ev


def artifact_version(project_id: str) -> str | None:
    """Identity of the reconstruction a verdict was computed against."""
    man = storage.artifacts_dir(project_id) / "manifest.json"
    if not man.exists():
        return None
    try:
        m = json.loads(man.read_text())
        return f"{m.get('video_sha256', '?')[:12]}@{m.get('created', 0):.0f}"
    except (OSError, ValueError):
        return None


def scale_status(project_id: str) -> dict:
    """What the metric scale of this reconstruction rests on.

    A reconstruction with no georeferencing has arbitrary scale: its "metres"
    are reconstruction units and any length in them is meaningless as a
    physical dimension. That has to reach the result, not just the manifest.
    """
    rec = evidence_for(project_id)
    src = getattr(rec, "scale_source", None) if rec is not None else None
    rel = getattr(rec, "scale_sigma_rel", float("nan")) if rec is not None else float("nan")
    metric = bool(src) and str(src) not in ("none", "relative", "arbitrary")
    return {"scale_source": src,
            "scale_sigma_rel": float(rel) if np.isfinite(rel) else None,
            "is_metric": metric}


def measure(cloud, kind: str, pts, allow_inferred: bool, scale_sigma_rel: float):
    if kind == "distance" and len(pts) >= 2:
        return measmod.measure_distance(cloud, pts, allow_inferred=allow_inferred,
                                        scale_sigma_rel=scale_sigma_rel)
    if kind == "height" and len(pts) >= 2:
        return measmod.measure_height(cloud, pts[0], pts[1],
                                      allow_inferred=allow_inferred,
                                      scale_sigma_rel=scale_sigma_rel)
    if kind == "area" and len(pts) >= 3:
        return measmod.measure_area(cloud, pts, allow_inferred=allow_inferred,
                                    scale_sigma_rel=scale_sigma_rel)
    if kind == "point" and len(pts) >= 1:
        return measmod.measure_point(cloud, pts[0], allow_inferred=allow_inferred)
    raise HTTPException(400, f"invalid measurement '{kind}' or too few points")


def snapped_provenance(cloud, points, allow_inferred: bool):
    """Provenance class of the cloud point each selection resolved onto."""
    out = []
    for p in points:
        sn = measmod.snap(cloud, p, allow_inferred)
        out.append(int(sn.provenance))
    return out


def compute(project_id: str, cloud, *, kind: str, points, allow_inferred: bool,
            tolerance_m: float | None = None, interval_level: int = 95,
            threshold_m: float | None = None,
            threshold_direction: str = "at_least",
            label: str = "") -> dict:
    """Measure, judge, and return every column a stored result must carry.

    The returned dict is the whole contract: value and unit, the propagated
    sigma and what the interval means, the acceptance status and its reasons,
    the evidence, and the artifact version the answer belongs to.
    """
    scale = scale_status(project_id)
    rec = evidence_for(project_id)
    scale_sigma_rel = 0.0
    if rec is not None and np.isfinite(getattr(rec, "scale_sigma_rel", np.nan)):
        scale_sigma_rel = float(rec.scale_sigma_rel)

    m = measure(cloud, kind, points, allow_inferred, scale_sigma_rel)

    provs = snapped_provenance(cloud, points, allow_inferred)
    if rec is not None:
        ev = rec.for_points(m.points_enu, provenances=provs)
    else:
        # No trajectory artifact: nothing is known about view support, and an
        # unknown must not be scored as adequate.
        ev = qmod.Evidence(endpoints_observed=False)

    question = qmod.MeasurementQuestion(
        kind=kind, tolerance_m=tolerance_m, level=interval_level,
        threshold_m=threshold_m, threshold_direction=threshold_direction,
        label=label or "")
    # No validated calibration profile exists for any capture regime yet; see
    # TESTS_AND_RESULTS.md. Passing None is what makes every verdict at most
    # ESTIMATED_ONLY, which is the accurate state of the system.
    verdict = qmod.evaluate(question, value=m.value, sigma=m.sigma,
                            evidence=ev, profile=None)
    vd = verdict.to_dict()

    warnings = list(m.warnings)
    unit = m.unit
    if not scale["is_metric"]:
        # The number is in reconstruction units. Saying "m" here would be the
        # single most misleading thing this API could do.
        unit = "reconstruction units"
        warnings.insert(0, "no metric scale: this reconstruction is not "
                           "georeferenced, so this value is in arbitrary "
                           "reconstruction units, not metres")

    return {
        "kind": m.kind,
        "value": m.value,
        "unit": unit,
        "points_enu": [list(map(float, p)) for p in m.points_enu],
        "confidence_note": m.confidence_note,
        "used_inferred": m.used_inferred,
        "warnings": warnings,
        # Verdict.to_dict() carries the judgement, not the measurement: it has
        # no "sigma" and no "evidence" key. Reading them off it returned the
        # fallback for one and an empty dict for the other, so a stored result
        # would have had no evidence at all.
        "sigma": (float(m.sigma) if m.sigma is not None
                  and np.isfinite(m.sigma) else None),
        "interval_half_width": vd.get("interval_half_width"),
        "interval_level": verdict.interval_level,
        "interval_basis": verdict.interval_basis,
        "status": verdict.status.value,
        # Verdict.to_dict() names this "reasons"; asking for "status_reasons"
        # here returned [] for every measurement, so the refusal was stored but
        # its reasons were not -- the one field that says *why*.
        "status_reasons": vd.get("reasons", []),
        "dominant_limitation": verdict.dominant_limitation,
        "threshold_result": verdict.threshold_result,
        "evidence": ev.to_dict(),
        "artifact_version": artifact_version(project_id),
        "selection": m.extra.get("selection", []),
        "scale": scale,
    }
