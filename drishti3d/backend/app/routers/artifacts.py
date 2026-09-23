"""Artifact access: quality, trajectory, model (viewer), files and exports."""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse, JSONResponse, Response
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
    # Per-hole record of the inferred fill: what each surface rests on.
    "fill": "fill.json",
}

#: Provenance code of fill points (``Provenance.INFERRED_FILL``). Written here
#: rather than imported so the API does not load the reconstruction package.
_FILL_CODE = 6
#: Fill points added to the capped JSON preview, at most.
_FILL_PREVIEW_MAX = 40000


def _load_fill(project_id: str):
    """(points, colors) of the inferred hole fill, or None if there is none."""
    p = storage.artifacts_dir(project_id) / "fill.npz"
    if not p.exists():
        return None
    d = np.load(p)
    return d["points"], d["colors"]


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
def get_model(project_id: str, fill: bool = True):
    """Viewer point-cloud payload (downsampled, ENU + provenance).

    The inferred hole fill, when there is one, is appended with its own
    provenance code, zero confidence, and in proportion to how much of the
    full cloud it is -- so the preview looks like the full view. ``fill=false``
    returns only what was observed.
    """
    v = _load_json(project_id, "viewer.json")
    f = _load_fill(project_id) if fill else None
    if f is not None and len(f[0]):
        fp, fc = f
        n_cloud = len(np.load(_artifact(project_id, "cloud.npz"), mmap_mode="r")["provenance"])
        ratio = len(v["points"]) / max(n_cloud, 1)
        m = min(len(fp), _FILL_PREVIEW_MAX, max(1, int(round(len(fp) * ratio))))
        keep = np.random.default_rng(0).choice(len(fp), m, replace=False)
        v["points"] += np.round(fp[keep].astype(float), 3).tolist()
        v["colors"] += fc[keep].astype(int).tolist()
        v["confidence"] += [0.0] * m
        v["provenance"] += [_FILL_CODE] * m
        v["fill_count"] = m
    return JSONResponse(v)


#: Header layout for the full-cloud binary. Little-endian throughout, which is
#: what every browser this runs in uses natively.
_CLOUD_MAGIC = b"D3DC"
_CLOUD_VERSION = 1


@router.get("/{project_id}/model.bin")
def get_model_binary(project_id: str, fill: bool = True):
    """The complete point cloud, packed, with no downsampling.

    `viewer.json` caps at 120,000 points because JSON is ruinous for this: a
    2.69 M point cloud is about 148 MB as text, against 6.6 MB for the capped
    preview. The cap was never a rendering limit -- three.js draws millions of
    points comfortably -- it was a transfer and parse limit, and the fix is to
    stop sending numbers as text.

    Packed little-endian:

        magic   4 bytes  'D3DC'
        version 4 bytes  uint32
        count   4 bytes  uint32
        xyz     count * 3 * float32   ENU metres
        rgb     count * 3 * uint8
        prov    count * 1 * uint8     Provenance enum

    That is 16 bytes per point: about 43 MB for the same cloud, a third of the
    JSON and no parsing beyond a typed-array view. The capped JSON stays as the
    first paint; this is what "show every point" loads.

    The inferred hole fill is appended after the cloud with provenance
    ``INFERRED_FILL`` (``fill=false`` leaves it out); ``X-Fill-Count`` says how
    many of the points it is.
    """
    import io
    npz = _artifact(project_id, "cloud.npz")
    d = np.load(npz)
    pts = np.ascontiguousarray(d["points"], dtype="<f4")
    n = len(pts)
    cols = np.ascontiguousarray(
        d["colors"] if "colors" in d.files else np.full((n, 3), 200),
        dtype=np.uint8)
    prov = np.ascontiguousarray(
        d["provenance"] if "provenance" in d.files else np.zeros(n),
        dtype=np.uint8)
    n_fill = 0
    f = _load_fill(project_id) if fill else None
    if f is not None and len(f[0]):
        n_fill = len(f[0])
        pts = np.concatenate([pts, np.asarray(f[0], dtype="<f4")])
        cols = np.concatenate([cols, np.asarray(f[1], dtype=np.uint8)])
        prov = np.concatenate([prov, np.full(n_fill, _FILL_CODE, np.uint8)])
        n = len(pts)

    buf = io.BytesIO()
    buf.write(_CLOUD_MAGIC)
    buf.write(np.uint32(_CLOUD_VERSION).tobytes())
    buf.write(np.uint32(n).tobytes())
    buf.write(pts.tobytes())
    buf.write(cols.tobytes())
    buf.write(prov.tobytes())
    data = buf.getvalue()
    return Response(
        content=data, media_type="application/octet-stream",
        headers={"Content-Length": str(len(data)),
                 "X-Point-Count": str(n),
                 "X-Fill-Count": str(n_fill),
                 "Cache-Control": "no-cache"})


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
