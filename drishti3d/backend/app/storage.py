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


#: Artifact files whose contents decide what a measurement means. A change to
#: any of them invalidates geometry, lineage or coverage held in memory.
_REVISION_FILES = ("cloud.npz", "observations.npz", "manifest.json",
                   "trajectory.json", "coverage.npz")


def artifact_revision(project_id: str) -> str:
    """A token that changes whenever the measurable artifacts change.

    Caches used to be keyed by project id alone, with an ``invalidate`` helper
    that the reconstruction and upload paths never called. Replacing
    ``cloud.npz`` and measuring again returned the previous geometry -- the new
    manifest said one thing while the answer came from the old cloud.

    Keying by revision instead makes that failure impossible rather than
    merely discouraged: a cache entry for a superseded artifact set can no
    longer be looked up, whether or not anything remembered to clear it. Size
    and modification time are enough to detect a rewritten artifact; this is a
    cache key, not a tamper seal, and the measurement passport (C05/U05) is
    where content hashes belong.
    """
    art = artifacts_dir(project_id)
    h = hashlib.sha256()
    for name in _REVISION_FILES:
        f = art / name
        try:
            st = f.stat()
            h.update(f"{name}:{st.st_size}:{st.st_mtime_ns}".encode())
        except FileNotFoundError:
            h.update(f"{name}:absent".encode())
    return h.hexdigest()[:16]


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
