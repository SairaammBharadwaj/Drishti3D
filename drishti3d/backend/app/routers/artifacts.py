"""Artifact access: quality, trajectory, model (viewer), files and exports."""
from __future__ import annotations

import json
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse, JSONResponse
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import Project
from ..schemas import ExportRequest
from .. import storage

router = APIRouter(prefix="/api/projects", tags=["artifacts"])

# artifact key -> filename produced by the pipeline
_EXPORT_FILES = {
    "ply": "point_cloud.ply",
    "las": "point_cloud.las",
    "mesh_glb": "mesh.glb",
    "geojson": "trajectory.geojson",
    "trajectory_csv": "trajectory.csv",
    "report_json": "quality_report.json",
    "report_html": "quality_report.html",
    "viewer": "viewer.json",
    # Without this, every cloud export leaves as unreferenced local metres and
    # the origin has to be communicated out of band.
    "georeference": "georeference.json",
}


def _artifact(project_id: str, filename: str) -> Path:
    p = storage.artifacts_dir(project_id) / filename
    if not p.exists():
        raise HTTPException(404, f"artifact '{filename}' not available yet")
    return p


def _load_json(project_id: str, filename: str):
    return json.loads(_artifact(project_id, filename).read_text())


@router.get("/{project_id}/quality")
def get_quality(project_id: str, db: Session = Depends(get_db)):
    return _load_json(project_id, "quality_report.json")


@router.get("/{project_id}/trajectory")
def get_trajectory(project_id: str):
    return _load_json(project_id, "trajectory.json")


@router.get("/{project_id}/model")
def get_model(project_id: str):
    """Viewer point-cloud payload (downsampled, ENU + provenance)."""
    return JSONResponse(_load_json(project_id, "viewer.json"))


@router.get("/{project_id}/keyframes")
def get_keyframes(project_id: str):
    return _load_json(project_id, "keyframes.json")


@router.get("/{project_id}/frame_metrics")
def get_frame_metrics(project_id: str):
    return _load_json(project_id, "frame_metrics.json")


@router.get("/{project_id}/exports")
def list_exports(project_id: str):
    d = storage.artifacts_dir(project_id)
    available = {k: v for k, v in _EXPORT_FILES.items() if (d / v).exists()}
    return {"available": available}


@router.get("/{project_id}/exports/{key}")
def download_export(project_id: str, key: str):
    if key not in _EXPORT_FILES:
        raise HTTPException(404, "unknown export")
    p = _artifact(project_id, _EXPORT_FILES[key])
    return FileResponse(p, filename=p.name)
