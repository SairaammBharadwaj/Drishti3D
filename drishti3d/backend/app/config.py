"""Backend configuration and paths."""
from __future__ import annotations

import os
from pathlib import Path

# Repository root = two levels up from this file's package.
BACKEND_DIR = Path(__file__).resolve().parents[1]
REPO_ROOT = BACKEND_DIR.parent

DATA_DIR = Path(os.environ.get("DRISHTI_DATA_DIR", REPO_ROOT / "data"))
PROJECTS_DIR = DATA_DIR / "projects"
DB_PATH = DATA_DIR / "drishti3d.db"

MAX_UPLOAD_BYTES = int(os.environ.get("DRISHTI_MAX_UPLOAD_MB", "2048")) * 1024 * 1024
ALLOWED_VIDEO_EXT = {".mp4", ".mov", ".m4v", ".avi", ".mkv", ".webm"}
ALLOWED_TELEMETRY_EXT = {".csv", ".json", ".srt"}

# Bind locally by default (offline / air-gapped friendly).
HOST = os.environ.get("DRISHTI_HOST", "127.0.0.1")
PORT = int(os.environ.get("DRISHTI_PORT", "8000"))

# Frontend origin(s) allowed for CORS during development.
CORS_ORIGINS = os.environ.get(
    "DRISHTI_CORS", "http://localhost:5173,http://127.0.0.1:5173").split(",")

# Optional path to a built frontend (dist) to serve from the API.
FRONTEND_DIST = Path(os.environ.get(
    "DRISHTI_FRONTEND_DIST", REPO_ROOT / "frontend" / "dist"))


def ensure_dirs() -> None:
    PROJECTS_DIR.mkdir(parents=True, exist_ok=True)
