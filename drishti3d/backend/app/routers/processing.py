"""Processing trigger, job status, and SSE progress stream."""
from __future__ import annotations

import asyncio
import json

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import Project, Job
from ..schemas import ProcessRequest, JobOut
from .. import jobs

router = APIRouter(prefix="/api", tags=["processing"])


@router.post("/projects/{project_id}/process", response_model=JobOut)
def start_processing(project_id: str, body: ProcessRequest,
                     db: Session = Depends(get_db)):
    p = db.get(Project, project_id)
    if not p:
        raise HTTPException(404, "project not found")
    if not p.has_video:
        raise HTTPException(400, "upload a video before processing")
    # telemetry is optional: without it the pipeline runs in relative-scale mode
    # (shape only, not georeferenced/metric)

    job = Job(project_id=project_id, status="queued")
    p.status = "processing"
    db.add(job)
    db.commit()
    db.refresh(job)

    params = body.model_dump()
    if body.intrinsics is None and p.intrinsics:
        params["intrinsics"] = p.intrinsics
    elif body.intrinsics is not None:
        params["intrinsics"] = body.intrinsics.model_dump()
    jobs.submit(job.id, project_id, params)
    return job


@router.get("/jobs/{job_id}", response_model=JobOut)
def get_job(job_id: str, db: Session = Depends(get_db)):
    job = db.get(Job, job_id)
    if not job:
        raise HTTPException(404, "job not found")
    state = jobs.get_state(job_id)
    if state:  # prefer live in-memory state
        job.status = state.get("status", job.status)
        job.stage = state.get("stage", job.stage)
        job.progress = state.get("progress", job.progress)
        job.message = state.get("message", job.message)
        job.error = state.get("error", job.error)
        job.warnings = state.get("warnings", job.warnings)
    return job


@router.get("/jobs/{job_id}/events")
async def job_events(job_id: str, db: Session = Depends(get_db)):
    if not db.get(Job, job_id):
        raise HTTPException(404, "job not found")

    async def gen():
        last = None
        while True:
            state = jobs.get_state(job_id)
            if state and state != last:
                last = dict(state)
                yield f"data: {json.dumps(state)}\n\n"
                if state.get("status") in ("done", "failed"):
                    break
            await asyncio.sleep(0.4)

    return StreamingResponse(gen(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache",
                                      "X-Accel-Buffering": "no"})
