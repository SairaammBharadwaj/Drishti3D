"""Measurement endpoints (operate on the reconstructed cloud in ENU)."""
from __future__ import annotations

import numpy as np
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import Project, Measurement
from ..schemas import MeasurementCreate, MeasurementOut
from .. import storage
from .. import results

from drishti_recon.fusion import PointCloud
from drishti_recon import measure as measmod

router = APIRouter(prefix="/api/projects", tags=["measurements"])

#: Keyed by (project_id, artifact revision), so a rebuilt reconstruction can
#: never be answered from the previous cloud.  See storage.artifact_revision.
_cache: dict[tuple[str, str], PointCloud] = {}


def load_cloud(project_id: str) -> PointCloud:
    rev = storage.artifact_revision(project_id)
    key = (project_id, rev)
    if key in _cache:
        return _cache[key]
    # A new revision supersedes every earlier entry for this project; drop them
    # so a long-lived process does not accumulate dead clouds.
    for k in [k for k in _cache if k[0] == project_id]:
        _cache.pop(k, None)
    npz = storage.artifacts_dir(project_id) / "cloud.npz"
    if not npz.exists():
        raise HTTPException(404, "reconstruction not available; process first")
    d = np.load(npz)
    # Carry the propagated per-point uncertainty across. Dropping it made every
    # endpoint report sigma = inf, which the measurement layer correctly reads
    # as "not observable" -- so the whole uncertainty pipeline was computed,
    # written to disk, and then discarded one step before it was used.
    cloud = PointCloud(d["points"], d["colors"], d["confidence"],
                       d["provenance"], None,
                       d["sigma"] if "sigma" in d.files else None,
                       d["sigma_major"] if "sigma_major" in d.files else None)
    _cache[key] = cloud
    return cloud


def invalidate(project_id: str):
    """Drop cached geometry for a project.

    Revision keying already prevents a stale read; this stays as the explicit
    hook for the paths that know an artifact set has been replaced, and to free
    memory rather than wait for the next lookup.
    """
    for k in [k for k in _cache if k[0] == project_id]:
        _cache.pop(k, None)
    results.invalidate(project_id)
    from . import questions as _q
    _q.invalidate(project_id)


@router.post("/{project_id}/measurements", response_model=MeasurementOut)
def create_measurement(project_id: str, body: MeasurementCreate,
                       db: Session = Depends(get_db)):
    """Measure directly, without first stating a requirement.

    This is the exploratory ruler: no tolerance, so no verdict about meeting
    one. Everything else is identical to the question route, because it goes
    through the same result service -- scale uncertainty propagated, sigma and
    interval basis stored, acceptance status recorded, artifact version
    attached. A number obtained here means exactly what a number obtained
    there means.
    """
    if not db.get(Project, project_id):
        raise HTTPException(404, "project not found")
    cloud = load_cloud(project_id)
    r = results.compute(project_id, cloud, kind=body.kind, points=body.points,
                        allow_inferred=body.allow_inferred)
    row = Measurement(
        project_id=project_id, kind=r["kind"], value=r["value"],
        unit=r["unit"], points_enu=r["points_enu"],
        confidence_note=r["confidence_note"], used_inferred=r["used_inferred"],
        warnings=r["warnings"], sigma=r["sigma"],
        interval_half_width=r["interval_half_width"],
        interval_level=r["interval_level"], interval_basis=r["interval_basis"],
        status=r["status"], status_reasons=r["status_reasons"],
        dominant_limitation=r["dominant_limitation"],
        threshold_result=r["threshold_result"], evidence=r["evidence"],
        artifact_version=r["artifact_version"])
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


@router.get("/{project_id}/measurements", response_model=list[MeasurementOut])
def list_measurements(project_id: str, db: Session = Depends(get_db)):
    return (db.query(Measurement)
            .filter(Measurement.project_id == project_id)
            .order_by(Measurement.created_at.desc()).all())


@router.delete("/{project_id}/measurements/{measurement_id}")
def delete_measurement(project_id: str, measurement_id: str,
                       db: Session = Depends(get_db)):
    row = db.get(Measurement, measurement_id)
    if not row or row.project_id != project_id:
        raise HTTPException(404, "measurement not found")
    db.delete(row)
    db.commit()
    return {"deleted": measurement_id}
