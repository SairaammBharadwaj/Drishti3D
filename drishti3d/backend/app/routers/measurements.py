"""Measurement endpoints (operate on the reconstructed cloud in ENU)."""
from __future__ import annotations

import numpy as np
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import Project, Measurement
from ..schemas import MeasurementCreate, MeasurementOut
from .. import storage

from drishti_recon.fusion import PointCloud
from drishti_recon import measure as measmod

router = APIRouter(prefix="/api/projects", tags=["measurements"])

_cache: dict[str, PointCloud] = {}


def load_cloud(project_id: str) -> PointCloud:
    if project_id in _cache:
        return _cache[project_id]
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
    _cache[project_id] = cloud
    return cloud


def invalidate(project_id: str):
    _cache.pop(project_id, None)
    from . import questions as _q
    _q.invalidate(project_id)


@router.post("/{project_id}/measurements", response_model=MeasurementOut)
def create_measurement(project_id: str, body: MeasurementCreate,
                       db: Session = Depends(get_db)):
    if not db.get(Project, project_id):
        raise HTTPException(404, "project not found")
    cloud = load_cloud(project_id)
    pts = body.points
    kind = body.kind
    ai = body.allow_inferred
    if kind == "point" and len(pts) >= 1:
        m = measmod.measure_point(cloud, pts[0], allow_inferred=ai)
    elif kind == "distance" and len(pts) >= 2:
        m = measmod.measure_distance(cloud, pts, allow_inferred=ai)
    elif kind == "height" and len(pts) >= 2:
        m = measmod.measure_height(cloud, pts[0], pts[1], allow_inferred=ai)
    elif kind == "area" and len(pts) >= 3:
        m = measmod.measure_area(cloud, pts, allow_inferred=ai)
    else:
        raise HTTPException(400, f"invalid measurement '{kind}' or too few points")

    row = Measurement(project_id=project_id, kind=m.kind, value=m.value,
                      unit=m.unit,
                      points_enu=[list(map(float, p)) for p in m.points_enu],
                      confidence_note=m.confidence_note,
                      used_inferred=m.used_inferred, warnings=m.warnings)
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
