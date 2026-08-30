"""Safe upload storage: filename sanitization, path-traversal prevention,
extension/size validation, SHA-256 of immutable originals."""
from __future__ import annotations

import hashlib
import re
import shutil
from pathlib import Path

from fastapi import UploadFile, HTTPException

from .config import (PROJECTS_DIR, MAX_UPLOAD_BYTES,
                     ALLOWED_VIDEO_EXT, ALLOWED_TELEMETRY_EXT)

_SAFE = re.compile(r"[^A-Za-z0-9._-]")


def sanitize_filename(name: str) -> str:
    name = Path(name).name          # strip any directory components
    name = _SAFE.sub("_", name)
    name = name.lstrip(".") or "upload"
    return name[:200]


def project_dir(project_id: str) -> Path:
    # project_id is a server-generated uuid hex; still guard against traversal.
    if not re.fullmatch(r"[a-f0-9]{32}", project_id):
        raise HTTPException(400, "invalid project id")
    return PROJECTS_DIR / project_id


def uploads_dir(project_id: str) -> Path:
    d = project_dir(project_id) / "uploads"
    d.mkdir(parents=True, exist_ok=True)
    return d


def artifacts_dir(project_id: str) -> Path:
    return project_dir(project_id) / "artifacts"


def _check_ext(filename: str, allowed: set[str], kind: str) -> str:
    ext = Path(filename).suffix.lower()
    if ext not in allowed:
        raise HTTPException(
            400, f"unsupported {kind} type '{ext}'. Allowed: {sorted(allowed)}")
    return ext


def save_upload(project_id: str, upload: UploadFile, kind: str) -> tuple[str, str]:
    """Stream an upload to disk with size + extension validation.

    Returns (stored_filename, sha256).  Originals are treated as immutable.
    """
    allowed = ALLOWED_VIDEO_EXT if kind == "video" else ALLOWED_TELEMETRY_EXT
    safe = sanitize_filename(upload.filename or f"{kind}.bin")
    _check_ext(safe, allowed, kind)

    dest = uploads_dir(project_id) / f"{kind}{Path(safe).suffix.lower()}"
    h = hashlib.sha256()
    size = 0
    with open(dest, "wb") as out:
        while True:
            chunk = upload.file.read(1 << 20)
            if not chunk:
                break
            size += len(chunk)
            if size > MAX_UPLOAD_BYTES:
                out.close()
                dest.unlink(missing_ok=True)
                raise HTTPException(413, "file exceeds maximum upload size")
            h.update(chunk)
            out.write(chunk)
    if size == 0:
        dest.unlink(missing_ok=True)
        raise HTTPException(400, "empty file")
    return dest.name, h.hexdigest()


def delete_project_files(project_id: str) -> None:
    d = project_dir(project_id)
    if d.exists():
        shutil.rmtree(d, ignore_errors=True)
