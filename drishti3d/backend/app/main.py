"""Drishti3D FastAPI application entrypoint.

Binds locally by default (offline-friendly).  Serves the JSON API, static
artifact files, and — if a built frontend exists — the SPA.
"""
from __future__ import annotations

import logging
import re
import threading
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse
from starlette.concurrency import run_in_threadpool

from . import config, sandbox, showcase, tunnel
from .config import CORS_ORIGINS, FRONTEND_DIST
from .db import init_db
from .schemas import CapabilitiesOut
from .routers import (projects, processing, artifacts, measurements,
                      questions)

from drishti_recon import ai_adapter, colmap_adapter
from drishti_recon import mesh as meshmod

app = FastAPI(title="Drishti3D API", version="0.1.0",
              description="Single-pass drone video to georeferenced 3D (SIH26158).")

app.add_middleware(
    CORSMiddleware, allow_origins=CORS_ORIGINS, allow_credentials=True,
    allow_methods=["*"], allow_headers=["*"])


# uvicorn configures its own loggers and no others, so a line meant for the
# server log goes through one of them.
log = logging.getLogger("uvicorn.error")

#: The only writes a read-only showcase accepts. Each lands in the visitor's
#: own sandbox copy of the database (sandbox.py), so none can change what
#: anyone else sees. Creating, uploading, processing, refining and deleting
#: missions are refused: there is nothing on a showcase server to run them on.
_HEX = r"[a-f0-9]{32}"
_SANDBOXED_WRITES = [
    ("POST", re.compile(rf"/api/projects/{_HEX}/measurements")),
    ("DELETE", re.compile(rf"/api/projects/{_HEX}/measurements/{_HEX}")),
    ("POST", re.compile(rf"/api/projects/{_HEX}/questions")),
    ("PATCH", re.compile(rf"/api/projects/{_HEX}/questions/{_HEX}")),
    ("DELETE", re.compile(rf"/api/projects/{_HEX}/questions/{_HEX}")),
]


@app.middleware("http")
async def _read_only(request: Request, call_next):
    if not config.READ_ONLY:
        return await call_next(request)
    path = request.url.path
    if (request.method not in ("GET", "HEAD", "OPTIONS")
            and not any(m == request.method and rx.fullmatch(path)
                        for m, rx in _SANDBOXED_WRITES)):
        return JSONResponse(status_code=403, content={
            "detail": "This is a read-only showcase of finished missions. "
                      "New reconstructions run on the team's own hardware."})
    sid = request.headers.get(sandbox.HEADER)
    # A write without an id still runs, in a copy nobody can read back.
    request.state.sandbox_id = sid if sandbox.valid(sid) else sandbox.new_id()
    response = await call_next(request)
    if request.method == "GET" and response.status_code == 200:
        cache = _cache_policy(path)
        if cache:
            response.headers["Cache-Control"] = cache
    return response


#: What a showcase's artifacts never do is change, so browsers (and a caching
#: proxy in front, if any) may keep them. An hour, not forever: re-exporting a
#: bundle replaces them under the same URLs. Measurements and questions are per
#: visitor and are never marked cacheable.
_ARTIFACT_GET = re.compile(
    rf"/api/projects/{_HEX}/(model|model\.bin|model\.pack|quality|trajectory|frame_metrics|keyframes|exports(/[a-z_]+)?)")


def _cache_policy(path: str) -> str | None:
    if path.startswith("/assets/"):              # content-hashed file names
        return "public, max-age=31536000, immutable"
    if _ARTIFACT_GET.fullmatch(path):
        return "public, max-age=3600"
    return None


@app.middleware("http")
async def _forward_to_fast_address(request: Request, call_next):
    """Send page visits on the stable address to the fast one (tunnel.py)."""
    if request.method in ("GET", "HEAD"):
        host = request.headers.get("x-forwarded-host") or request.headers.get("host", "")
        navigation = (request.headers.get("sec-fetch-mode") == "navigate"
                      or "text/html" in request.headers.get("accept", ""))
        target = await run_in_threadpool(
            tunnel.redirect_target, host, request.url.path, request.url.query, navigation)
        if target:
            return RedirectResponse(target, status_code=307)
    return await call_next(request)


class _CompressText:
    """gzip JSON, HTML, scripts and styles; pass binary data through untouched.

    Over a slow link the viewer's JSON is most of the wait, and it shrinks
    about 3x (6.5 MB to 2.2 MB for DJI_1001's preview). The binary point cloud
    shrinks only 1.2x for 2.9 s of CPU per request on the server laptop, and
    compressing it would also hide its Content-Length, which the progress bar
    reads. Downloads under /exports/ are skipped by path because some of them
    (PLY, LAS) are served with a generic text type.
    """

    def __init__(self, app):
        self.app = app
        self.gzip = GZipMiddleware(
            app, minimum_size=1024, compresslevel=5,
            exclude_content_types=("text/event-stream", "application/octet-stream",
                                   "image/", "video/", "model/"))

    async def __call__(self, scope, receive, send):
        path = scope.get("path", "")
        if scope["type"] == "http" and not ("/exports/" in path or path.endswith(("/model.bin", "/model.pack", "/video"))):
            return await self.gzip(scope, receive, send)
        return await self.app(scope, receive, send)


app.add_middleware(_CompressText)


@app.on_event("startup")
def _startup():
    init_db()
    if config.READ_ONLY:
        sandbox.reset()
        n = showcase.restore_times(config.DATA_DIR)
        log.info("read-only showcase; restored %d artifact times", n)
        # Pack every mission's cloud now, off the request path, so no visitor
        # waits the ~2 s a large one takes the first time.
        threading.Thread(target=_warm_packs, daemon=True).start()


def _warm_packs():
    m = showcase.load(config.DATA_DIR) or {}
    for pid in m.get("projects", {}):
        try:
            artifacts.pack_for(pid)
        except Exception as exc:              # noqa: BLE001 - warming is optional
            log.warning("could not pre-pack %s: %s", pid, exc)
    log.info("packed %d clouds for model.pack", len(m.get("projects", {})))


@app.get("/api/health")
def health():
    return {"status": "ok"}


@app.get("/api/deployment")
def deployment():
    """What kind of server this is, for the UI to adapt to."""
    return {"read_only": config.READ_ONLY,
            "credits": showcase.credits(config.DATA_DIR)}


@app.get("/api/capabilities", response_model=CapabilitiesOut)
def capabilities():
    """Honest report of which engines/backends are actually available."""
    return CapabilitiesOut(
        engines={
            "opencv_sfm": True,          # always available (verified path)
            "colmap": colmap_adapter.is_available(),
        },
        ai_backends=ai_adapter.status(),
        optional={
            "mesh_open3d": meshmod.available(),
            "las_export": _has("laspy"),
            "torch": _has("torch"),
            # Reported as a dict, not a bool: "dense stereo is unavailable" is
            # not actionable, and the reason is always one of two very
            # different things -- no colmap at all, or a colmap built without
            # CUDA, which no amount of reinstalling pycolmap will fix.
            "dense_mvs": _mvs_status(),
        },
    )


def _mvs_status() -> dict:
    try:
        from drishti_recon import mvs
        return mvs.available()["colmap"]
    except Exception as exc:              # noqa: BLE001 - never fatal
        return {"available": False, "detail": f"{type(exc).__name__}: {exc}"}


def _has(mod: str) -> bool:
    import importlib.util
    try:
        return importlib.util.find_spec(mod) is not None
    except (ImportError, ValueError):
        return False


app.include_router(projects.router)
app.include_router(processing.router)
app.include_router(artifacts.router)
app.include_router(measurements.router)
app.include_router(questions.router)

# Serve the built SPA if present (single-command demo). During development the
# frontend runs on the Vite dev server and talks to this API via CORS.
# A catch-all returns index.html for client-side routes (history fallback) so
# deep links like /projects/:id survive a refresh.
if FRONTEND_DIST.exists() and (FRONTEND_DIST / "index.html").exists():
    _assets = FRONTEND_DIST / "assets"
    if _assets.exists():
        app.mount("/assets", StaticFiles(directory=str(_assets)), name="assets")

    @app.get("/{full_path:path}", include_in_schema=False)
    def spa(full_path: str):
        if full_path.startswith("api/"):
            raise HTTPException(404, "not found")
        candidate = FRONTEND_DIST / full_path
        if full_path and candidate.is_file():
            return FileResponse(candidate)
        return FileResponse(FRONTEND_DIST / "index.html")
