"""Drishti3D FastAPI application entrypoint.

Binds locally by default (offline-friendly).  Serves the JSON API, static
artifact files, and — if a built frontend exists — the SPA.
"""
from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

from .config import CORS_ORIGINS, FRONTEND_DIST
from .db import init_db
from .schemas import CapabilitiesOut
from .routers import projects, processing, artifacts, measurements

from drishti_recon import ai_adapter, colmap_adapter
from drishti_recon import mesh as meshmod

app = FastAPI(title="Drishti3D API", version="0.1.0",
              description="Single-pass drone video to georeferenced 3D (SIH26158).")

app.add_middleware(
    CORSMiddleware, allow_origins=CORS_ORIGINS, allow_credentials=True,
    allow_methods=["*"], allow_headers=["*"])


@app.on_event("startup")
def _startup():
    init_db()


@app.get("/api/health")
def health():
    return {"status": "ok"}


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
        },
    )


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
