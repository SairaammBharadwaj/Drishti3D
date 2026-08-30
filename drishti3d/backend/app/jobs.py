"""Background job runner.

A simple threaded worker abstraction (swappable for Celery/Redis later).  The
worker runs the reconstruction pipeline, persisting progress to the DB and to an
in-memory state map that the SSE endpoint polls.  Keeping progress in memory
avoids cross-thread asyncio plumbing while remaining reliable.
"""
from __future__ import annotations

import threading
import traceback
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

from .db import SessionLocal
from .models import Job, Project
from . import storage
from .config import PROJECTS_DIR

from drishti_recon import pipeline

_executor = ThreadPoolExecutor(max_workers=1)  # serialise heavy CV jobs
_states: dict[str, dict] = {}
_lock = threading.Lock()


def get_state(job_id: str) -> dict | None:
    with _lock:
        s = _states.get(job_id)
        return dict(s) if s else None


def _set_state(job_id: str, **kw):
    with _lock:
        s = _states.setdefault(job_id, {})
        s.update(kw)
        s["updated_at"] = datetime.now(timezone.utc).isoformat()


def submit(job_id: str, project_id: str, params: dict) -> None:
    _set_state(job_id, status="queued", stage="", progress=0.0, message="queued",
               error=None, warnings=[])
    _executor.submit(_run, job_id, project_id, params)


def _run(job_id: str, project_id: str, params: dict) -> None:
    db = SessionLocal()
    try:
        project = db.get(Project, project_id)
        job = db.get(Job, job_id)
        job.status = "running"
        job.message = "starting"
        db.commit()
        _set_state(job_id, status="running", message="starting")

        up = storage.uploads_dir(project_id)
        video = next(up.glob("video.*"))
        telem = next(iter(up.glob("telemetry.*")), None)   # optional (no-GPS mode)

        pp = pipeline.PipelineParams(
            preset=params.get("preset", "balanced"),
            mask_backend=params.get("mask_backend", "none"),
            do_mesh=params.get("do_mesh", True),
            engine=params.get("engine", "opencv"),
            densify=params.get("densify", "none"),
            intrinsics=params.get("intrinsics"),
        )

        last = {"t": 0.0}

        def cb(stage, frac, msg=""):
            _set_state(job_id, stage=stage, progress=round(float(frac), 4),
                       message=msg, status="running")
            # throttle DB writes
            import time
            if time.time() - last["t"] > 0.5:
                last["t"] = time.time()
                job.stage, job.progress, job.message = stage, float(frac), msg
                db.commit()

        result = pipeline.run(PROJECTS_DIR / project_id, str(video),
                              str(telem) if telem else None,
                              params=pp, progress=cb)

        job.status = "done"
        job.stage = "done"
        job.progress = 1.0
        job.message = "reconstruction complete"
        job.warnings = result.warnings
        project.status = "done"
        db.commit()
        _set_state(job_id, status="done", stage="done", progress=1.0,
                   message="reconstruction complete", warnings=result.warnings)
    except Exception as e:  # noqa: BLE001
        tb = traceback.format_exc()
        try:
            job = db.get(Job, job_id)
            job.status = "failed"
            job.error = f"{e}"
            project = db.get(Project, project_id)
            if project:
                project.status = "failed"
            db.commit()
        except Exception:
            pass
        _set_state(job_id, status="failed", error=str(e), message="failed")
        print("[job] failed:", tb)
    finally:
        db.close()
