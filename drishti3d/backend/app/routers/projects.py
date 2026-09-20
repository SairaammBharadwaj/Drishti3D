"""Project CRUD + upload endpoints."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from sqlalchemy.orm import Session
from fastapi.responses import FileResponse

from ..db import get_db
from ..models import Project
from ..schemas import ProjectCreate, ProjectOut
from .. import storage

router = APIRouter(prefix="/api/projects", tags=["projects"])


@router.post("", response_model=ProjectOut)
def create_project(body: ProjectCreate, db: Session = Depends(get_db)):
    p = Project(name=body.name, description=body.description)
    db.add(p)
    db.commit()
    db.refresh(p)
    return p


@router.get("", response_model=list[ProjectOut])
def list_projects(db: Session = Depends(get_db)):
    return db.query(Project).order_by(Project.created_at.desc()).all()


@router.get("/{project_id}", response_model=ProjectOut)
def get_project(project_id: str, db: Session = Depends(get_db)):
    p = db.get(Project, project_id)
    if not p:
        raise HTTPException(404, "project not found")
    return p


@router.delete("/{project_id}")
def delete_project(project_id: str, db: Session = Depends(get_db)):
    p = db.get(Project, project_id)
    if not p:
        raise HTTPException(404, "project not found")
    db.delete(p)
    db.commit()
    storage.delete_project_files(project_id)
    return {"deleted": project_id}


@router.post("/{project_id}/video", response_model=ProjectOut)
def upload_video(project_id: str, file: UploadFile = File(...),
                 db: Session = Depends(get_db)):
    p = db.get(Project, project_id)
    if not p:
        raise HTTPException(404, "project not found")
    name, sha = storage.save_upload(project_id, file, "video")
    p.video_filename = name
    p.video_sha256 = sha
    db.commit()
    db.refresh(p)
    return p


@router.get("/{project_id}/video")
def original_video(project_id: str, db: Session = Depends(get_db)):
    """Serve the original capture for the inference presentation."""
    p = db.get(Project, project_id)
    if not p or not p.video_filename:
        raise HTTPException(404, "original video not found")
    path = storage.project_dir(project_id) / "uploads" / p.video_filename
    if not path.is_file():
        raise HTTPException(404, "original video not found")
    return FileResponse(path)


@router.post("/{project_id}/telemetry", response_model=ProjectOut)
def upload_telemetry(project_id: str, file: UploadFile = File(...),
                     db: Session = Depends(get_db)):
    p = db.get(Project, project_id)
    if not p:
        raise HTTPException(404, "project not found")
    name, _ = storage.save_upload(project_id, file, "telemetry")
    p.telemetry_filename = name
    db.commit()
    db.refresh(p)
    return p


@router.post("/{project_id}/intrinsics", response_model=ProjectOut)
def set_intrinsics(project_id: str, fx: float = Form(...), fy: float = Form(...),
                   cx: float = Form(...), cy: float = Form(...),
                   db: Session = Depends(get_db)):
    p = db.get(Project, project_id)
    if not p:
        raise HTTPException(404, "project not found")
    p.intrinsics = {"fx": fx, "fy": fy, "cx": cx, "cy": cy}
    db.commit()
    db.refresh(p)
    return p
