"""Background job runner.

A simple threaded worker abstraction (swappable for Celery/Redis later). A
thread supervises each job, persisting progress to the DB and to an in-memory
state map that the SSE endpoint polls. Keeping progress in memory avoids
cross-thread asyncio plumbing while remaining reliable.

The pipeline itself runs in a child process (:mod:`app.worker`), not on the
thread. On the thread it grew inside the server with no memory cap, so the web
path was the one way to start an 11-minute mission without
``scripts/run_capped.sh``, and that script exists because an uncapped run took
the editor down. The child runs inside the same capped scope the command line
uses whenever systemd is available (see :func:`job_command`).
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import threading
import time
import traceback
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

from .db import SessionLocal
from .models import Job, Project
from . import storage
from .config import BACKEND_DIR, PROJECTS_DIR, REPO_ROOT
from .worker import PREFIX

#: Memory cap for one job, in systemd's notation. The default matches
#: ``run_capped.sh``, whose 6G was measured on this 15 GB laptop. "off" runs the
#: job uncapped, which is also what happens where systemd is not available
#: (a container, for instance).
JOB_MEM_ENV = "DRISHTI_JOB_MEM"
DEFAULT_JOB_MEM = "6G"

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


def _drop_caches(project_id: str) -> None:
    """Release in-memory geometry and lineage for a project, best effort."""
    try:
        from .routers.measurements import invalidate
        invalidate(project_id)
    except Exception:                                      # noqa: BLE001
        pass


#: Request fields passed to :class:`PipelineParams` only when supplied, so an
#: omitted value keeps the pipeline's own default rather than overriding it.
_OPTIONAL_PARAMS = ("max_analyze_frames", "proc_max_width")


def pipeline_params(params: dict) -> dict:
    """The :class:`PipelineParams` fields a job request asks for."""
    out = {
        "preset": params.get("preset", "balanced"),
        "mask_backend": params.get("mask_backend", "none"),
        "do_mesh": params.get("do_mesh", True),
        "engine": params.get("engine", "opencv"),
        "densify": params.get("densify", "none"),
        "intrinsics": params.get("intrinsics"),
    }
    for k in _OPTIONAL_PARAMS:
        if params.get(k) is not None:
            out[k] = params[k]
    return out


def job_command(spec_path: Path) -> tuple[list[str], str | None]:
    """The command that runs one job, and the memory cap it runs under.

    Capped through ``scripts/run_capped.sh`` whenever it can be: the script,
    ``systemd-run`` and a user session must all exist. Otherwise the job runs
    uncapped and the returned cap is None, so the caller can say so.
    """
    base = [sys.executable, "-m", "app.worker", str(spec_path)]
    mem = os.environ.get(JOB_MEM_ENV, DEFAULT_JOB_MEM).strip()
    if mem.lower() in ("", "0", "off", "none"):
        return base, None
    script = REPO_ROOT / "scripts" / "run_capped.sh"
    if (not script.is_file() or shutil.which("systemd-run") is None
            or not os.environ.get("XDG_RUNTIME_DIR")):
        return base, None
    return ["bash", str(script), "--mem", mem, "--", *base], mem


def _worker_env() -> dict:
    """The server's environment, with the backend and pipeline importable."""
    env = dict(os.environ)
    paths = [str(BACKEND_DIR), str(REPO_ROOT / "reconstruction")]
    if env.get("PYTHONPATH"):
        paths.append(env["PYTHONPATH"])
    env["PYTHONPATH"] = os.pathsep.join(paths)
    env["PYTHONUNBUFFERED"] = "1"
    return env


def _run(job_id: str, project_id: str, params: dict) -> None:
    db = SessionLocal()
    try:
        project = db.get(Project, project_id)
        job = db.get(Job, job_id)
        job.status = "running"
        job.message = "starting"
        db.commit()
        _set_state(job_id, status="running", message="starting")

        # A refinement earlier in this process can leave a learned matcher
        # on the GPU; dense stereo in the worker needs that memory more.
        from drishti_recon.refinement import release_gpu_models
        release_gpu_models()

        up = storage.uploads_dir(project_id)
        video = next(up.glob("video.*"))
        telem = next(iter(up.glob("telemetry.*")), None)   # optional (no-GPS mode)

        project_dir = PROJECTS_DIR / project_id
        log_dir = project_dir / "logs"
        log_dir.mkdir(parents=True, exist_ok=True)
        spec_path = log_dir / f"job_{job_id}.json"
        spec_path.write_text(json.dumps({
            "project_dir": str(project_dir),
            "video": str(video),
            "telemetry": str(telem) if telem else None,
            "params": pipeline_params(params),
        }, indent=2))
        cmd, mem = job_command(spec_path)

        last = {"t": 0.0}

        def on_progress(stage, frac, msg=""):
            _set_state(job_id, stage=stage, progress=round(float(frac), 4),
                       message=msg, status="running")
            # throttle DB writes
            if time.time() - last["t"] > 0.5:
                last["t"] = time.time()
                job.stage, job.progress, job.message = stage, float(frac), msg
                db.commit()

        final = None
        log_path = log_dir / f"job_{job_id}.log"
        tail: list[str] = []
        with open(log_path, "w") as log:
            log.write(f"command: {' '.join(cmd)}\nmemory cap: {mem or 'none'}\n\n")
            proc = subprocess.Popen(cmd, stdout=subprocess.PIPE,
                                    stderr=subprocess.STDOUT, text=True,
                                    bufsize=1, cwd=str(REPO_ROOT),
                                    env=_worker_env())
            for line in proc.stdout:
                if line.startswith(PREFIX):
                    ev = json.loads(line[len(PREFIX):])
                    if ev.get("event") == "progress":
                        on_progress(ev["stage"], ev["progress"], ev.get("message", ""))
                    else:
                        final = ev
                        if ev.get("traceback"):
                            log.write(ev["traceback"])
                    continue
                log.write(line)
                log.flush()
                tail = (tail + [line.rstrip()])[-20:]
            rc = proc.wait()

        if final is None or final.get("event") != "done":
            if final is not None:
                raise RuntimeError(final.get("error") or "reconstruction failed")
            # The worker died without a word: killed from outside, or the
            # capped scope could not be created at all.
            killed = rc in (-9, 137)
            why = (f"stopped after exceeding its {mem} memory cap; analyse fewer "
                   f"frames or a smaller processing width, or raise {JOB_MEM_ENV}"
                   if killed and mem else
                   f"worker exited with code {rc} before finishing")
            detail = "; ".join(t for t in tail[-3:] if t)
            raise RuntimeError(f"{why}" + (f" ({detail})" if detail else "")
                               + f". Log: {log_path}")
        warnings = list(final.get("warnings") or [])
        if mem is None:
            warnings.append("job ran without a memory cap (systemd scope unavailable "
                            f"or {JOB_MEM_ENV}=off)")

        # The artifacts on disk have just been replaced. Caches key themselves
        # by artifact revision so a stale read is already impossible, but drop
        # the superseded entries here rather than hold them until someone asks.
        _drop_caches(project_id)

        job.status = "done"
        job.stage = "done"
        job.progress = 1.0
        job.message = "reconstruction complete"
        job.warnings = warnings
        project.status = "done"
        db.commit()
        _set_state(job_id, status="done", stage="done", progress=1.0,
                   message="reconstruction complete", warnings=warnings)
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
        # A failed run can still have written part of an artifact set before
        # stopping, so anything held from before it is not trustworthy either.
        _drop_caches(project_id)
        _set_state(job_id, status="failed", error=str(e), message="failed")
        print("[job] failed:", tb)
    finally:
        db.close()
