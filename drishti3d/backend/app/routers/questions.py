"""Measurement questions: ask, answer, and re-evaluate at a new tolerance.

This router is the authoritative acceptance gate described in plan F2.  The
frontend renders what it returns; it must never decide a status itself, because
a status computed from rendered vertices would be a statement about the viewer's
mesh rather than about the evidence.

The flow:

* ``POST   /api/projects/{id}/questions``            ask, and answer immediately
* ``GET    /api/projects/{id}/questions``            list with current verdicts
* ``PATCH  /api/projects/{id}/questions/{qid}``      change the tolerance only
* ``GET    /api/projects/{id}/questions/{qid}/evidence``  supporting frames
* ``DELETE /api/projects/{id}/questions/{qid}``

Changing the tolerance re-runs the *verdict* against the stored measurement. It
never re-runs the geometry, which is the property that makes the Tolerance Lens
meaningful: the answer does not move when the requirement does.
"""
from __future__ import annotations

import json

import numpy as np
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import (Project, Measurement, MeasurementQuestion,
                      RefinementRun)
from ..schemas import (QuestionCreate, QuestionUpdate, QuestionOut,
                       QuestionEvidenceOut, RefineRequest, RefinementOut)
from .. import storage
from .. import results
from .measurements import load_cloud

from drishti_recon import measure as measmod
from drishti_recon import questions as qmod
from drishti_recon import refinement as refmod
from drishti_recon.evidence import ReconstructionEvidence

router = APIRouter(prefix="/api/projects", tags=["questions"])

#: Retained so existing callers keep working; the cache itself now lives in
#: app.results, which is the single owner of evidence loading.
_evidence_cache = results._evidence_cache


def invalidate(project_id: str) -> None:
    results.invalidate(project_id)


def _evidence_for(project_id: str) -> ReconstructionEvidence | None:
    return results.evidence_for(project_id)


def _artifact_version(project_id: str) -> str | None:
    return results.artifact_version(project_id)


def _measure(cloud, kind: str, pts, allow_inferred: bool, scale_sigma_rel: float):
    return results.measure(cloud, kind, pts, allow_inferred, scale_sigma_rel)


def _snapped_provenance(cloud, points, allow_inferred: bool):
    return results.snapped_provenance(cloud, points, allow_inferred)


def _answer(project_id: str, row: MeasurementQuestion,
            db: Session) -> Measurement:
    """Compute the measurement and its verdict, and store both.

    This used to hold its own copy of the whole computation. DEC-021 extracted
    `results.compute` and pointed `/measurements` at it, but left this copy in
    place -- so the decision was written down and only half applied, and the
    two routes still disagreed on the one case the extraction existed to fix:
    an ungeoreferenced reconstruction answered here in "m" and there in
    "reconstruction units".
    """
    cloud = load_cloud(project_id)
    r = results.compute(
        project_id, cloud, kind=row.kind, points=row.points_enu,
        allow_inferred=row.allow_inferred, tolerance_m=row.tolerance_m,
        interval_level=row.interval_level, threshold_m=row.threshold_m,
        threshold_direction=row.threshold_direction, label=row.label or "")
    result = Measurement(
        project_id=project_id, question_id=row.id, kind=r["kind"],
        value=r["value"], unit=r["unit"], points_enu=r["points_enu"],
        confidence_note=r["confidence_note"],
        used_inferred=r["used_inferred"], warnings=r["warnings"],
        sigma=r["sigma"], interval_half_width=r["interval_half_width"],
        interval_level=r["interval_level"],
        interval_basis=r["interval_basis"], status=r["status"],
        status_reasons=r["status_reasons"],
        dominant_limitation=r["dominant_limitation"],
        threshold_result=r["threshold_result"], evidence=r["evidence"],
        artifact_version=r["artifact_version"], calibration_profile=None)
    db.add(result)
    db.commit()
    db.refresh(result)
    return result


def _out(row: MeasurementQuestion, result: Measurement | None,
         current_version: str | None = None) -> dict:
    """Serialise a question and its latest answer.

    ``current_version`` is the reconstruction the project holds *now*. A stored
    result belongs to the artifacts that produced it, and after a reprocess
    those are gone -- so a listing that returned the old value with no marker
    let a superseded answer read as current. The PATCH and refine paths already
    re-measured on a version change; plain listing had no way to say anything.
    """
    guidance = []
    if result is not None:
        for code in (result.status_reasons or []):
            try:
                r = qmod.Reason(code)
            except ValueError:
                continue
            text, action = qmod.REASON_GUIDANCE[r]
            guidance.append({"reason": code, "explanation": text,
                             "next_action": action})
    return {
        "id": row.id, "project_id": row.project_id, "kind": row.kind,
        "label": row.label, "points_enu": row.points_enu,
        "tolerance_m": row.tolerance_m, "interval_level": row.interval_level,
        "threshold_m": row.threshold_m,
        "threshold_direction": row.threshold_direction,
        "allow_inferred": row.allow_inferred, "notes": row.notes,
        "created_at": row.created_at, "updated_at": row.updated_at,
        "result": None if result is None else {
            "id": result.id, "value": result.value, "unit": result.unit,
            "sigma": result.sigma,
            "interval_half_width": result.interval_half_width,
            "interval_level": result.interval_level,
            "interval_basis": result.interval_basis,
            "status": result.status,
            "status_reasons": result.status_reasons or [],
            "dominant_limitation": result.dominant_limitation,
            "threshold_result": result.threshold_result,
            "evidence": result.evidence or {},
            "artifact_version": result.artifact_version,
            # True when the reconstruction has been rebuilt since this answer
            # was computed. The value is not wrong; it is about geometry that
            # no longer exists, and re-asking is what makes it current.
            "superseded": bool(
                current_version is not None
                and result.artifact_version is not None
                and result.artifact_version != current_version),
            "warnings": result.warnings or [],
            "created_at": result.created_at,
        },
        "guidance": guidance,
    }


def _latest(db: Session, question_id: str) -> Measurement | None:
    return (db.query(Measurement)
            .filter(Measurement.question_id == question_id)
            .order_by(Measurement.created_at.desc()).first())


#: Minimum selections a question of each kind can be answered from. Enforced at
#: creation so an unanswerable question is never stored.
MIN_POINTS = {"point": 1, "distance": 2, "height": 2, "area": 3}

#: Interval levels the uncertainty layer has a z-factor for; refused at the
#: door so the request fails with a clear message rather than deep in evaluate.
SUPPORTED_INTERVAL_LEVELS = set(qmod.SUPPORTED_INTERVAL_LEVELS)


@router.post("/{project_id}/questions", response_model=QuestionOut)
def create_question(project_id: str, body: QuestionCreate,
                    db: Session = Depends(get_db)):
    if not db.get(Project, project_id):
        raise HTTPException(404, "project not found")
    if body.kind not in ("point", "distance", "height", "area"):
        raise HTTPException(400, f"unsupported question kind '{body.kind}'")
    if body.tolerance_m is not None and body.tolerance_m <= 0:
        raise HTTPException(400, "tolerance must be positive")
    # Checked before the row is committed. The measurement layer rejects a
    # two-point area anyway, but it did so *after* the question was persisted,
    # leaving a stored question that can never be answered and that every later
    # listing has to carry.
    need = MIN_POINTS[body.kind]
    if len(body.points) < need:
        raise HTTPException(
            400, f"a {body.kind} question needs at least {need} "
                 f"point{'s' if need > 1 else ''}; {len(body.points)} given")
    if any(len(p) != 3 for p in body.points):
        raise HTTPException(400, "every point must be [east, north, up]")
    if body.interval_level not in SUPPORTED_INTERVAL_LEVELS:
        raise HTTPException(
            400, f"interval level {body.interval_level} is not supported; "
                 f"choose one of {sorted(SUPPORTED_INTERVAL_LEVELS)}")
    row = MeasurementQuestion(
        project_id=project_id, kind=body.kind, label=body.label,
        points_enu=[list(map(float, p)) for p in body.points],
        tolerance_m=body.tolerance_m, interval_level=body.interval_level,
        threshold_m=body.threshold_m,
        threshold_direction=body.threshold_direction,
        allow_inferred=body.allow_inferred, notes=body.notes)
    db.add(row)
    db.commit()
    db.refresh(row)
    return _out(row, _answer(project_id, row, db),
                _artifact_version(project_id))


@router.get("/{project_id}/questions", response_model=list[QuestionOut])
def list_questions(project_id: str, db: Session = Depends(get_db)):
    rows = (db.query(MeasurementQuestion)
            .filter(MeasurementQuestion.project_id == project_id)
            .order_by(MeasurementQuestion.created_at.desc()).all())
    current = _artifact_version(project_id)
    return [_out(r, _latest(db, r.id), current) for r in rows]


@router.patch("/{project_id}/questions/{question_id}",
              response_model=QuestionOut)
def update_question(project_id: str, question_id: str, body: QuestionUpdate,
                    db: Session = Depends(get_db)):
    """Change the requirement, then re-decide the stored measurement.

    Only the tolerance, interval level and threshold may change here. The
    selection cannot: moving the endpoints would be a different question, and
    silently reusing the old one's identity would make its history a lie.
    """
    row = db.get(MeasurementQuestion, question_id)
    if not row or row.project_id != project_id:
        raise HTTPException(404, "question not found")

    # Validate everything before touching the row. This used to assign first
    # and validate never: an unsupported interval level was committed, and the
    # failure surfaced as a 500 from evaluate() further down -- leaving the
    # question stored with a level the system cannot answer, so every later
    # read of it failed too. A rejected request must leave the stored question
    # exactly as it was.
    if body.tolerance_m is not None and body.tolerance_m <= 0:
        raise HTTPException(400, "tolerance must be positive")
    if (body.interval_level is not None
            and body.interval_level not in SUPPORTED_INTERVAL_LEVELS):
        raise HTTPException(
            400, f"interval level {body.interval_level} is not supported; "
                 f"choose one of {sorted(SUPPORTED_INTERVAL_LEVELS)}")
    if (body.threshold_direction is not None
            and body.threshold_direction not in ("at_least", "at_most")):
        raise HTTPException(
            400, "threshold_direction must be 'at_least' or 'at_most'")

    if body.tolerance_m is not None:
        row.tolerance_m = body.tolerance_m
    if body.interval_level is not None:
        row.interval_level = body.interval_level
    if body.threshold_m is not None:
        row.threshold_m = body.threshold_m
    if body.threshold_direction is not None:
        row.threshold_direction = body.threshold_direction
    if body.label is not None:
        row.label = body.label
    db.commit()
    db.refresh(row)

    prior = _latest(db, row.id)
    if prior is None or prior.artifact_version != _artifact_version(project_id):
        # Either nothing was measured yet, or the geometry changed underneath.
        # Re-measuring is right in both cases; reusing a stale value would
        # silently answer a question about geometry that no longer exists.
        return _out(row, _answer(project_id, row, db),
                _artifact_version(project_id))

    question = qmod.MeasurementQuestion(
        kind=row.kind, tolerance_m=row.tolerance_m, level=row.interval_level,
        threshold_m=row.threshold_m,
        threshold_direction=row.threshold_direction, label=row.label or "")
    # Filtered, not splatted: the stored record also carries refinement
    # diagnostics, which are not gate inputs and are not Evidence fields.
    ev = qmod.Evidence.from_dict(prior.evidence)
    verdict = qmod.evaluate(question, value=prior.value,
                            sigma=prior.sigma if prior.sigma is not None
                            else float("inf"),
                            evidence=ev, profile=None)
    vd = verdict.to_dict()
    prior.interval_half_width = vd["interval_half_width"]
    prior.interval_level = verdict.interval_level
    prior.interval_basis = verdict.interval_basis
    prior.status = verdict.status.value
    prior.status_reasons = vd["reasons"]
    prior.dominant_limitation = verdict.dominant_limitation
    prior.threshold_result = verdict.threshold_result
    db.commit()
    db.refresh(prior)
    return _out(row, prior, _artifact_version(project_id))


@router.get("/{project_id}/questions/{question_id}/evidence",
            response_model=QuestionEvidenceOut)
def question_evidence(project_id: str, question_id: str,
                      db: Session = Depends(get_db)):
    """The frames behind this measurement, most diverse in direction first.

    ``support_basis`` says what the listing is. With observation lineage it is
    ``triangulated_observations`` -- the frames that actually measured each
    endpoint, each row carrying the pixel it was measured at. Without it the
    rows are candidate frames established from camera geometry, and the
    parallax figures are upper bounds.

    Each endpoint also reports ``observation_kinds``, splitting its support
    into ``sparse_feature_observation`` (a pixel a detector measured in that
    image) and ``dense_fusion_contributor`` (an image `stereo_fusion` recorded
    as contributing, with the pixel obtained by projecting the fused point back
    into it). Both establish that the image contributed; only the first is an
    original image measurement, and the distinction was previously invisible
    because both were stored in the same unlabelled ``uv`` array.
    """
    row = db.get(MeasurementQuestion, question_id)
    if not row or row.project_id != project_id:
        raise HTTPException(404, "question not found")
    rec = _evidence_for(project_id)
    result = _latest(db, row.id)
    if rec is None:
        return {"question_id": question_id, "support_basis": "unavailable",
                "endpoints": [],
                "note": "no reconstruction trajectory artifact for this project"}
    pts = (result.points_enu if result and result.points_enu
           else row.points_enu)
    endpoints = []
    any_fallback = False
    for i, p in enumerate(pts):
        obs = rec.observations_of(p)
        measured = len(obs["frame_index"])
        if not measured:
            any_fallback = True
        endpoints.append({
            "index": i,
            "point_enu": list(map(float, p)),
            "basis": ("triangulated_observations" if measured
                      else "frustum_upper_bound"),
            "n_measuring_views": int(len(set(obs["frame_index"].tolist()))),
            "n_candidate_views": int(len(rec.visible_cameras(p))),
            "measured_ray_separation_deg": (rec.measured_ray_separation_deg(p)
                                            if measured else None),
            "max_ray_separation_deg": rec.max_ray_separation_deg(p),
            "within_established_coverage": rec.within_coverage(p),
            "frames": rec.supporting_frames(p),
            # What kind of record the support is. A projected dense pixel and a
            # measured sparse feature pixel are both genuine evidence of a
            # contributing image, but only one is an original image
            # measurement, and an operator opening the frames should be told
            # which they are looking at rather than inferring it.
            "observation_kinds": rec.observation_kinds_of(p),
        })
    has_lineage = rec.has_lineage and not any_fallback
    return {
        "question_id": question_id,
        "support_basis": ("triangulated_observations" if has_lineage
                          else "frustum_upper_bound"),
        "endpoints": endpoints,
        "note": (
            "Frames are the image observations that produced each endpoint; "
            "`pixel` is where the measurement was made, in the resolution the "
            "reconstruction was solved at."
            if has_lineage else
            "Frames are candidates established from camera geometry and the "
            "coverage grid, not the image observations that produced the "
            "points. Parallax shown is therefore an upper bound."),
    }


@router.post("/{project_id}/questions/{question_id}/refine",
             response_model=RefinementOut)
def refine_question(project_id: str, question_id: str,
                    body: RefineRequest | None = None,
                    db: Session = Depends(get_db)):
    """Spend a bounded budget recovering evidence for this one measurement.

    Frames of the same pass that the reconstruction never processed are ranked
    by the parallax they would add at the measurement's weakest endpoint, a
    bounded batch is registered against the existing model, and the endpoint is
    re-triangulated from the enlarged ray set.

    A run that recovers nothing is still recorded and still returned, with the
    reason. The feature's claim is that targeted refinement beats a uniform
    budget; a path that only reported its successes could not be used to test
    that.
    """
    body = body or RefineRequest()
    row = db.get(MeasurementQuestion, question_id)
    if not row or row.project_id != project_id:
        raise HTTPException(404, "question not found")
    rec = _evidence_for(project_id)
    if rec is None:
        raise HTTPException(404, "reconstruction artifacts not available")

    prior = _latest(db, row.id)
    if prior is None or prior.artifact_version != _artifact_version(project_id):
        prior = _answer(project_id, row, db)

    proj = db.get(Project, project_id)
    video = None
    if proj is not None and proj.video_filename:
        p = storage.project_dir(project_id) / "uploads" / proj.video_filename
        if p.is_file():
            video = str(p)
    if video is None:
        raise HTTPException(
            409, "the original video is required to recover unused frames from "
                 "the same pass, and it is not on disk for this project")

    cloud = load_cloud(project_id)
    pts = [np.asarray(p, float) for p in (prior.points_enu or row.points_enu)]
    # Endpoint sigmas come from the cloud the measurement was taken on. They are
    # looked up once, here, so the refined endpoint keeps its own uncertainty
    # instead of inheriting whatever point it now sits nearest to.
    sigmas = []
    for p in pts:
        _sp, _prov, sg = measmod._snap(cloud, p, row.allow_inferred)
        sigmas.append(float(sg))
    scale_sigma_rel = (float(rec.scale_sigma_rel)
                       if np.isfinite(rec.scale_sigma_rel) else 0.0)

    question = qmod.MeasurementQuestion(
        kind=row.kind, tolerance_m=row.tolerance_m, level=row.interval_level,
        threshold_m=row.threshold_m,
        threshold_direction=row.threshold_direction, label=row.label or "")
    engine = refmod.RefinementEngine(rec, storage.artifacts_dir(project_id),
                                     video_path=video)
    try:
        run = engine.refine(
            question, pts,
            value_fn=refmod.measurement_value_fn(
                row.kind, sigmas, scale_sigma_rel=scale_sigma_rel),
            budget_frames=int(body.budget_frames),
            max_decode=int(body.max_decode),
            provenances=_snapped_provenance(cloud, pts, row.allow_inferred))
    finally:
        if engine._source is not None:
            engine._source.close()

    detail = run.to_dict()
    result = prior
    if run.added_frames:
        # A refinement produces a new result rather than overwriting the old
        # one: the point of showing a before and after is that both survive.
        after = detail["after"]
        # The endpoints the refined value was computed from -- not the ones the
        # operator originally picked. Storing the originals meant recomputing
        # from the saved row could not reproduce the saved value: the whole
        # point of refinement is that an endpoint moved, and the record has to
        # be of the geometry that produced the answer.
        refined_pts = (detail.get("refined_points_enu")
                       or [list(map(float, p)) for p in pts])
        result = Measurement(
            project_id=project_id, question_id=row.id, kind=prior.kind,
            value=after["value"], unit=prior.unit,
            points_enu=[list(map(float, p)) for p in refined_pts],
            confidence_note=prior.confidence_note,
            used_inferred=prior.used_inferred,
            warnings=list(prior.warnings or []),
            sigma=after["sigma"],
            interval_half_width=after["interval_half_width"],
            interval_level=row.interval_level,
            interval_basis="uncalibrated_sensitivity",
            status=after["status"], status_reasons=after["reasons"],
            dominant_limitation=after["dominant_limitation"],
            # Recomputed against the new value and interval. Copying the prior
            # verdict forward meant a refinement that moved the value across
            # the threshold still reported the old side of it.
            threshold_result=after.get("threshold_result"),
            evidence={**(prior.evidence or {}),
                      "n_supporting_views": after["n_supporting_views"],
                      "max_ray_separation_deg": after["max_ray_separation_deg"],
                      "view_support_basis": after["view_support_basis"],
                      # Diagnostics, kept under their own key so they are
                      # visibly not gate inputs. Evidence.from_dict ignores
                      # them on the way back in either way.
                      "diagnostics": {
                          "endpoints_moved_m": [
                              float(np.linalg.norm(np.asarray(a, float)
                                                   - np.asarray(b, float)))
                              for a, b in zip(refined_pts, pts)]}},
            artifact_version=prior.artifact_version,
            calibration_profile=None, refined_from_id=prior.id)
        db.add(result)
        db.flush()

    rr = RefinementRun(
        project_id=project_id, question_id=row.id,
        parent_measurement_id=prior.id, result_measurement_id=result.id,
        budget_frames=int(body.budget_frames),
        n_considered=detail["n_considered"], n_added=detail["n_added"],
        termination_reason=detail["termination_reason"],
        wall_seconds=detail["wall_seconds"], improved=bool(run.improved),
        detail=detail, artifact_version=prior.artifact_version)
    db.add(rr)
    db.commit()
    db.refresh(rr)

    return {
        "id": rr.id, "question_id": row.id,
        "parent_measurement_id": prior.id,
        "result_measurement_id": result.id,
        "improved": bool(run.improved),
        "n_considered": rr.n_considered, "n_added": rr.n_added,
        "termination_reason": rr.termination_reason,
        "wall_seconds": rr.wall_seconds,
        "before": detail["before"], "after": detail["after"],
        "added_frames": detail["added_frames"],
        "rejected": detail["rejected"], "notes": detail["notes"],
        "created_at": rr.created_at,
    }


@router.get("/{project_id}/questions/{question_id}/refinements",
            response_model=list[RefinementOut])
def list_refinements(project_id: str, question_id: str,
                     db: Session = Depends(get_db)):
    rows = (db.query(RefinementRun)
            .filter(RefinementRun.question_id == question_id,
                    RefinementRun.project_id == project_id)
            .order_by(RefinementRun.created_at.desc()).all())
    return [{
        "id": r.id, "question_id": r.question_id,
        "parent_measurement_id": r.parent_measurement_id,
        "result_measurement_id": r.result_measurement_id,
        "improved": bool(r.improved), "n_considered": r.n_considered,
        "n_added": r.n_added, "termination_reason": r.termination_reason,
        "wall_seconds": r.wall_seconds,
        "before": (r.detail or {}).get("before", {}),
        "after": (r.detail or {}).get("after", {}),
        "added_frames": (r.detail or {}).get("added_frames", []),
        "rejected": (r.detail or {}).get("rejected", []),
        "notes": (r.detail or {}).get("notes", []),
        "created_at": r.created_at,
    } for r in rows]


@router.delete("/{project_id}/questions/{question_id}")
def delete_question(project_id: str, question_id: str,
                    db: Session = Depends(get_db)):
    row = db.get(MeasurementQuestion, question_id)
    if not row or row.project_id != project_id:
        raise HTTPException(404, "question not found")
    for r in db.query(Measurement).filter(
            Measurement.question_id == question_id).all():
        db.delete(r)
    db.delete(row)
    db.commit()
    return {"deleted": question_id}
